#!/usr/bin/env bash
# SignalLayer 公开入口一键启动脚本（前端 + 后端）
#
# 用法: ./start-public.sh [start|stop|restart|status]
#       ./start-public.sh backend  start|stop
#       ./start-public.sh frontend start|stop
#
# 前端 npm run dev:public (127.0.0.1:4174)；后端 uvicorn app.main:app (0.0.0.0:8000)。
# 日志与 PID 文件写入 /tmp，不污染 git。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT/signal-layer"
BACKEND_DIR="$ROOT/signal-layer-server"

BACKEND_PORT=8000
FRONTEND_HOST=127.0.0.1
FRONTEND_PORT=4174

BACKEND_PID_FILE=/tmp/signal-layer-backend.pid
FRONTEND_PID_FILE=/tmp/signal-layer-frontend-public.pid
BACKEND_LOG=/tmp/signal-layer-server.log
FRONTEND_LOG=/tmp/signal-layer-frontend-public.log

log()  { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; }

port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
pid_of_port() { lsof -tnP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1; }

backend_launcher() {
  if python3 -c 'import uvicorn' >/dev/null 2>&1; then
    echo "python3 -m uvicorn"
  elif command -v poetry >/dev/null 2>&1; then
    echo "poetry run uvicorn"
  else
    echo "uvicorn"
  fi
}

wait_http() {
  local url="$1" tries="${2:-60}" interval="${3:-2}"
  local i
  for ((i = 0; i < tries; i++)); do
    if curl -sf -m 2 "$url" >/dev/null 2>&1; then return 0; fi
    sleep "$interval"
  done
  return 1
}

stop_by_port() {
  local port="$1" name="$2" pidfile="$3"
  if ! port_in_use "$port"; then
    log "$name 未运行"
    rm -f "$pidfile"
    return 0
  fi
  local pid; pid="$(pid_of_port "$port")"
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null && log "已停止 $name (PID $pid)"
    local i
    for ((i = 0; i < 10; i++)); do
      port_in_use "$port" || break
      sleep 0.5
    done
  fi
  rm -f "$pidfile"
}

start_backend() {
  if port_in_use "$BACKEND_PORT"; then
    if wait_http "http://127.0.0.1:$BACKEND_PORT/health" 3; then
      log "后端已在运行 (PID $(pid_of_port "$BACKEND_PORT"))，跳过启动"
      return 0
    fi
    err "端口 $BACKEND_PORT 被占用且未就绪，请先释放端口"
    return 1
  fi

  local launcher; launcher="$(backend_launcher)"
  log "启动后端: $launcher app.main:app --host 0.0.0.0 --port $BACKEND_PORT"
  log "日志: $BACKEND_LOG"
  (
    cd "$BACKEND_DIR"
    nohup $launcher app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
      >>"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )

  # 后端初始化（连远程 MySQL + 启动预热）约需 1 分钟，超时放宽到 90 次 * 2 秒
  if wait_http "http://127.0.0.1:$BACKEND_PORT/health" 90 2; then
    log "后端就绪: http://127.0.0.1:$BACKEND_PORT/health"
  else
    err "后端启动超时，请查看日志: $BACKEND_LOG"
    return 1
  fi
}

start_frontend() {
  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    err "未找到 node_modules，请先在 $FRONTEND_DIR 执行 npm install"
    return 1
  fi

  if port_in_use "$FRONTEND_PORT"; then
    if wait_http "http://$FRONTEND_HOST:$FRONTEND_PORT/" 3; then
      log "前端已在运行 (PID $(pid_of_port "$FRONTEND_PORT"))，跳过启动"
      return 0
    fi
    err "端口 $FRONTEND_PORT 被占用且未就绪，请先释放端口"
    return 1
  fi

  log "启动前端: npm run dev:public -- --host $FRONTEND_HOST --port $FRONTEND_PORT"
  log "日志: $FRONTEND_LOG"
  (
    cd "$FRONTEND_DIR"
    nohup npm run dev:public -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
      >>"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )

  if wait_http "http://$FRONTEND_HOST:$FRONTEND_PORT/" 30 1; then
    log "前端就绪: http://$FRONTEND_HOST:$FRONTEND_PORT/ (public)"
  else
    err "前端启动超时，请查看日志: $FRONTEND_LOG"
    return 1
  fi
}

stop_backend()   { stop_by_port "$BACKEND_PORT"   "后端" "$BACKEND_PID_FILE"; }
stop_frontend()  { stop_by_port "$FRONTEND_PORT"  "前端" "$FRONTEND_PID_FILE"; }

status() {
  echo "--- SignalLayer 公开入口 ---"
  if port_in_use "$BACKEND_PORT"; then
    echo "后端:  运行中 (PID $(pid_of_port "$BACKEND_PORT"))  http://127.0.0.1:$BACKEND_PORT"
  else
    echo "后端:  未运行"
  fi
  if port_in_use "$FRONTEND_PORT"; then
    echo "前端:  运行中 (PID $(pid_of_port "$FRONTEND_PORT"))  http://$FRONTEND_HOST:$FRONTEND_PORT  [public]"
  else
    echo "前端:  未运行"
  fi
}

case "${1:-start}" in
  start)    start_backend && start_frontend ;;
  stop)     stop_frontend; stop_backend ;;
  restart)  stop_frontend; stop_backend; sleep 1; start_backend && start_frontend ;;
  status)   status ;;
  backend)  case "${2:-start}" in start) start_backend ;; stop) stop_backend ;; *) status ;; esac ;;
  frontend) case "${2:-start}" in start) start_frontend ;; stop) stop_frontend ;; *) status ;; esac ;;
  *)        err "用法: $0 {start|stop|restart|status|backend start|stop|frontend start|stop}"; exit 1 ;;
esac
