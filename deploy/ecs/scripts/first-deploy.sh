#!/usr/bin/env bash
# ============================================================================
# SignalLayer 首次部署（一条命令跑完整套）
# ============================================================================
#
# 在 ECS 上、仓库根目录执行：
#
#   bash deploy/ecs/scripts/first-deploy.sh --check    # 只做前置检查，什么都不改
#   bash deploy/ecs/scripts/first-deploy.sh            # 真正部署（会问两三个问题）
#
# 前提：已装好 docker + compose v2（`docker compose version` 有输出），
#       当前用户在 docker 组或用 root 执行。
#
# 脚本会做（幂等，可以反复跑）：
#   1  检查 docker/compose/文件是否齐备
#   2  准备 deploy/ecs/.env：不存在就生成随机密钥，并把残留的占位符补上
#   3  前置检查：域名解析、80/443 是否被别的程序占用
#   4  构建镜像并启动 mysql / redis / backend
#   5  等后端就绪，并用一个**真的读库**的请求确认数据库通了（关键门槛）
#   6  签发证书（已有证书则跳过）
#   7  启动 nginx 与自动续期容器
#   8  验收两个域名，并打印后续要做的两件事
#
# 注意：第 5 步是整份脚本的重点。后端连不上 MySQL 时 /health 仍然返回 200、
#       页面也能打开，但所有接口都 500 —— 所以这里不看 /health。
#
# 兼容 bash 3.2（macOS 上也能 --check），不用 bash 4 的语法。
# ============================================================================

set -euo pipefail

PUBLIC_HOST="caopan.me"
PRIVATE_HOST="work.caopan.me"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ECS_DIR="${REPO_ROOT}/deploy/ecs"
ENV_FILE="${ECS_DIR}/.env"
ENV_EXAMPLE="${ECS_DIR}/.env.example"
COMPOSE_FILE="${ECS_DIR}/docker-compose.yml"

CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg（支持 --check / --help）" >&2; exit 2 ;;
  esac
done

C=(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}")

MAJOR=0
step() { MAJOR=$((MAJOR + 1)); printf '\n\033[1;36m[%d/8]\033[0m %s\n' "${MAJOR}" "$1"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# 读取 .env 里的值（用 grep 而不是 source：值里若有 $ 或空格会被 shell 展开）
read_env() {
  [ -f "${ENV_FILE}" ] || return 1
  grep -E "^$1=" "${ENV_FILE}" | head -1 | cut -d= -f2-
}

# 写入/替换 .env 里某个键（awk 避免 sed 对 / + = 等字符的转义问题）
set_env() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  awk -v k="${key}" -v v="${val}" -F'=' 'BEGIN{OFS="="} $1==k {print k "=" v; next} {print}' \
    "${ENV_FILE}" > "${tmp}"
  mv "${tmp}" "${ENV_FILE}"
}

rand_secret() { openssl rand -base64 "${1:-32}" | tr -d '\n'; }

# ============================================================================
step "检查运行环境"
# ============================================================================

command -v docker >/dev/null 2>&1 \
  || die "没有 docker。先按 deploy/ecs/README.md 第 2 节安装（大陆机器建议用阿里云 docker-ce 源）"
docker compose version >/dev/null 2>&1 \
  || die "docker 有了，但 compose v2 不可用（缺 docker-compose-plugin）。本文档全部依赖 \`docker compose\`"
docker info >/dev/null 2>&1 \
  || die "docker 守护进程没跑，或者当前用户不在 docker 组：sudo systemctl start docker / sudo usermod -aG docker \$USER"

for f in "${COMPOSE_FILE}" "${ENV_EXAMPLE}" \
         "${ECS_DIR}/Dockerfile.backend" "${ECS_DIR}/Dockerfile.frontend" \
         "${ECS_DIR}/nginx/edge.conf" "${ECS_DIR}/nginx/api-proxy.conf"; do
  [ -f "${f}" ] || die "缺文件：${f}（是不是没在仓库根目录跑，或者 clone 不完整）"
done
ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')，compose 可用，配置文件齐备"
info "仓库根目录：${REPO_ROOT}"

# ============================================================================
step "准备 deploy/ecs/.env"
# ============================================================================

ADMIN_PW_GENERATED=""
PLACEHOLDER_MARK="请替换成"

# 值还是占位符（或为空）就替换掉；返回 0=本来就填好了，1=被替换
fill_placeholder() {
  local key="$1" val
  val="$(read_env "${key}" || true)"
  case "${val}" in
    ""|*"${PLACEHOLDER_MARK}"*|*"你的邮箱"*)
      set_env "${key}" "$2"
      return 1
      ;;
    *) return 0 ;;
  esac
}

ENV_READY=1
if [ ! -f "${ENV_FILE}" ]; then
  if [ "${CHECK_ONLY}" = "1" ]; then
    ENV_READY=0
    warn ".env 还不存在。真正部署时这一步会从 .env.example 生成它，自动填随机密钥，并问你要管理员密码与证书邮箱"
  else
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    ok "从 .env.example 生成了 .env"
  fi
else
  ok ".env 已存在（保留你已有的值，只补还空着的）"
fi

if [ "${ENV_READY}" = "1" ] && [ "${CHECK_ONLY}" = "0" ]; then
  FILLED=0
  fill_placeholder SIGNAL_TOKEN_SECRET "$(rand_secret 48)"      || FILLED=1
  fill_placeholder MYSQL_ROOT_PASSWORD "$(rand_secret 24)"      || FILLED=1
  fill_placeholder SIGNAL_MYSQL_PASSWORD "$(rand_secret 24)"    || FILLED=1

  # 这两个不生成随机值：一个是你要记住的密码，一个是会收到续期提醒的邮箱
  cur="$(read_env SIGNAL_BOOTSTRAP_ADMIN_PASSWORD || true)"
  case "${cur}" in
    ""|*"${PLACEHOLDER_MARK}"*)
      printf '  首个管理员密码（直接回车 = 自动生成 24 位随机串）: '
      read -r ADMIN_PW || true
      if [ -z "${ADMIN_PW}" ]; then
        ADMIN_PW="$(rand_secret 18)"
        ADMIN_PW_GENERATED="${ADMIN_PW}"
      fi
      set_env SIGNAL_BOOTSTRAP_ADMIN_PASSWORD "${ADMIN_PW}"
      FILLED=1
      ;;
  esac

  cur="$(read_env ACME_EMAIL || true)"
  case "${cur}" in
    ""|*"${PLACEHOLDER_MARK}"*|*"你的邮箱"*)
      printf '  证书通知邮箱（Let'"'"'s Encrypt 到期提醒用）: '
      read -r ACME_MAIL || true
      [ -n "${ACME_MAIL}" ] || die "邮箱不能为空（签发时要用它同意服务条款）"
      set_env ACME_EMAIL "${ACME_MAIL}"
      FILLED=1
      ;;
  esac

  chmod 600 "${ENV_FILE}"
  [ "${FILLED}" = "1" ] \
    && ok "已补上随机密钥/密码，并把 .env 权限设为 600" \
    || ok "所有必填值都已就位"
fi

# 校验：留着占位符、值为空或开关不对，都会导致启动失败或安全问题
if [ -f "${ENV_FILE}" ] && { [ "${ENV_READY}" = "1" ] || [ "${CHECK_ONLY}" = "0" ]; }; then
  for key in SIGNAL_TOKEN_SECRET SIGNAL_BOOTSTRAP_ADMIN_PASSWORD MYSQL_ROOT_PASSWORD SIGNAL_MYSQL_PASSWORD ACME_EMAIL; do
    val="$(read_env "${key}" || true)"
    [ -n "${val}" ] || die ".env 里 ${key} 是空的"
    case "${val}" in
      *"${PLACEHOLDER_MARK}"*) die ".env 里 ${key} 还是占位符内容（${val}），改成真实值" ;;
    esac
  done
  [ "$(read_env SIGNAL_DEBUG)" = "false" ] || die ".env 里 SIGNAL_DEBUG 必须是 false（生产环境）"
  secret="$(read_env SIGNAL_TOKEN_SECRET)"
  [ "${#secret}" -ge 32 ] || die "SIGNAL_TOKEN_SECRET 太短（${#secret} 字符），至少 32 位"
  [ "${secret}" != "change-this-secret-before-production" ] || die "SIGNAL_TOKEN_SECRET 还是默认值"
  info "库名 $(read_env SIGNAL_MYSQL_DATABASE)，后端连 $(read_env SIGNAL_MYSQL_HOST):$(read_env SIGNAL_MYSQL_PORT)"
  ok "必填项与生产开关校验通过"
fi

# ============================================================================
step "前置检查：域名解析 与 80/443 占用"
# ============================================================================

resolve() {
  local host="$1"
  if command -v getent >/dev/null 2>&1; then
    getent hosts "${host}" | awk '{print $1}' | tr '\n' ' '
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import socket,sys; print(socket.gethostbyname(sys.argv[1]))" "${host}" 2>/dev/null || true
  else
    echo "（本机没有 getent/python3，跳过解析检查）"
  fi
}

for host in "${PUBLIC_HOST}" "${PRIVATE_HOST}"; do
  ip="$(resolve "${host}")"
  if [ -z "${ip}" ]; then
    warn "${host} 解析不到地址 —— 证书签发会失败。去 DNS 加 A 记录指向本机公网 IP"
  else
    ok "${host} → ${ip}"
  fi
done

# 端口占用：如果占着的是我们自己的 nginx 容器，那属于重复执行，不算冲突
OWN_NGINX=0
if "${C[@]}" ps --status running --services 2>/dev/null | grep -qx nginx; then
  OWN_NGINX=1
fi
if [ "${OWN_NGINX}" = "0" ] && command -v ss >/dev/null 2>&1; then
  BUSY="$(ss -lntp 2>/dev/null | grep -E ':(80|443)\b' || true)"
  if [ -n "${BUSY}" ]; then
    printf '%s\n' "${BUSY}" | sed 's/^/    /'
    die "80/443 被上面的进程占用（常见是系统自带 nginx/apache）。停掉它再跑：sudo systemctl stop nginx"
  fi
  ok "80/443 空闲"
else
  [ "${OWN_NGINX}" = "1" ] && ok "80/443 由本项目 nginx 容器占用（重复执行，正常）" || info "跳过端口检查（本机没有 ss）"
fi

if [ "${CHECK_ONLY}" = "1" ]; then
  printf '\n\033[1;32m--check 完成：环境与配置看起来可用。\033[0m\n'
  echo "接下来执行会做：构建镜像 → 起 mysql/redis/backend → 验证数据库连通 → 签证书 → 起 nginx → 验收"
  echo "去掉 --check 即开始真正部署。"
  exit 0
fi

# ============================================================================
step "构建镜像并启动 mysql / redis / backend"
# ============================================================================

"${C[@]}" up -d --build mysql redis backend
ok "容器已启动"

# ============================================================================
step "确认后端真的连上了 MySQL（不看 /health）"
# ============================================================================

# 用不存在的账号登录：401 = 库通（查得到 users 表）；500 = 库不通。
# /health 恒为 200，不能作为判据。
probe_login() {
  local code
  # curl 连接失败时 -w 本身就会输出 000，这里不要再 echo 一个，否则会得到 "000000"
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 \
    -X POST -H 'Content-Type: application/json' \
    -d '{"username":"__deploy_probe__","password":"__nope__"}' \
    "http://127.0.0.1:8000/api/v1/auth/login" 2>/dev/null)" || true
  [ -n "${code}" ] || code=000
  printf '%s' "${code}"
}

printf '  等待后端起来（首次启动要建表 + 预热行情，最多 3 分钟）'
READY=0
for _ in $(seq 1 60); do
  printf '.'
  code="$(probe_login)"
  if [ "${code}" = "401" ]; then READY=1; break; fi
  if "${C[@]}" logs backend 2>/dev/null | grep -q "Database init failed"; then
    printf '\n'
    echo "  后端日志（最后 30 行）："
    "${C[@]}" logs --tail=30 backend | sed 's/^/    /'
    die "后端连不上数据库：看上面日志里的 MySQL 报错，以及 .env 里的 SIGNAL_MYSQL_* 是否与 compose 里的一致"
  fi
  sleep 3
done
printf '\n'

if [ "${READY}" != "1" ]; then
  echo "  后端日志（最后 40 行）："
  "${C[@]}" logs --tail=40 backend | sed 's/^/    /'
  die "等了 3 分钟仍拿不到预期的 401（当前探测返回 ${code}）。上面日志里通常能看到原因"
fi
ok "数据库已连通（login 探测返回 401 = 查得到 users 表）"

# 交叉确认：启动时创建的管理员确实落在 MySQL 里
ROOT_PW="$(read_env MYSQL_ROOT_PASSWORD)"
DB_NAME="$(read_env SIGNAL_MYSQL_DATABASE)"; DB_NAME="${DB_NAME:-signal_layer}"
USERS="$("${C[@]}" exec -T mysql mysql -uroot -p"${ROOT_PW}" -N -B \
  -e "select username from ${DB_NAME}.users" 2>/dev/null || true)"
if [ -n "${USERS}" ]; then
  ok "MySQL ${DB_NAME}.users 里已有账号：$(echo "${USERS}" | tr '\n' ' ')"
else
  warn "users 表里还没有账号（如果 SIGNAL_BOOTSTRAP_ADMIN_USERNAME 对应的账号不存在，检查后端日志里的 bootstrap 相关报错）"
fi

# ============================================================================
step "签发证书"
# ============================================================================

CERT_EXISTS=0
if "${C[@]}" run --rm --entrypoint certbot certbot certificates 2>/dev/null | grep -q "${PUBLIC_HOST}"; then
  CERT_EXISTS=1
fi

if [ "${CERT_EXISTS}" = "1" ]; then
  ok "证书已存在，跳过签发（续期由 certbot 容器自动做）"
else
  # 让出 80 端口：nginx 起来之前 80 是空的，用 standalone 直接签
  "${C[@]}" stop nginx >/dev/null 2>&1 || true
  ACME_MAIL="$(read_env ACME_EMAIL)"
  info "certbot standalone 用 80 端口做 HTTP 校验，两个域名在同一张证书里"
  # --entrypoint certbot 不能省：certbot 服务的 entrypoint 被改成了续期循环，
  # 不覆盖它，后面的参数会被那个 shell 循环忽略（命令看着在跑，证书根本没签）
  if ! "${C[@]}" run --rm --entrypoint certbot -p 80:80 certbot certonly --standalone \
      -d "${PUBLIC_HOST}" -d "${PRIVATE_HOST}" \
      --email "${ACME_MAIL}" --agree-tos --no-eff-email; then
    die "签发失败。常见原因：DNS 还没生效 / 安全组或系统防火墙没放行 80 / 大陆机器连 ACME 偶发超时（见 README 第 0 节的阿里云免费证书备用方案）"
  fi
  ok "证书已签发"
fi

# ============================================================================
step "启动 nginx 与自动续期"
# ============================================================================

"${C[@]}" up -d nginx certbot

# 容器刚起来时 exec 可能还进不去，重试几次再判定失败，避免误报
NGINX_OK=0
for _ in $(seq 1 10); do
  if "${C[@]}" exec -T nginx nginx -t >/dev/null 2>&1; then NGINX_OK=1; break; fi
  sleep 2
done
if [ "${NGINX_OK}" = "1" ]; then
  ok "nginx 配置语法通过"
else
  "${C[@]}" logs --tail=30 nginx | sed 's/^/    /'
  die "nginx 没起来（看上面的日志）。最常见原因：证书文件不存在 —— 检查 /etc/letsencrypt/live/ 下的目录名是否与 edge.conf 里的 ssl_certificate 路径一致"
fi

# ============================================================================
step "验收"
# ============================================================================

FAILED=0
check_url() {
  local url="$1" expect="$2" code
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 "${url}" 2>/dev/null)" || true
  [ -n "${code}" ] || code=000
  if [ "${code}" = "${expect}" ]; then
    ok "${url} → ${code}"
  else
    warn "${url} → ${code}（期望 ${expect}）"
    FAILED=1
  fi
}
check_url "https://${PUBLIC_HOST}" 200
check_url "https://${PRIVATE_HOST}" 200

# 公开站的行情接口：确认 /api 反代确实接到了后端（而不是把 index.html 当接口返回）
API_BODY="$(curl -s -m 20 "https://${PUBLIC_HOST}/api/v1/symbols/markets" 2>/dev/null || true)"
case "${API_BODY}" in
  *'"markets"'*) ok "公开站 /api 反代正常（返回了 markets JSON）" ;;
  *) warn "公开站 /api 返回的内容不像接口响应：$(printf '%s' "${API_BODY}" | head -c 120)"; FAILED=1 ;;
esac

printf '\n\033[1;32m部署完成\033[0m\n'
echo "  公开站：https://${PUBLIC_HOST}"
echo "  私有站：https://${PRIVATE_HOST}   （管理员：$(read_env SIGNAL_BOOTSTRAP_ADMIN_USERNAME)）"
if [ -n "${ADMIN_PW_GENERATED}" ]; then
  printf '\n  管理员密码（随机生成，记下来后登录并立即修改）：\033[1;33m%s\033[0m\n' "${ADMIN_PW_GENERATED}"
  printf '  \033[1;33m注意\033[0m：该密码只在"库里还没有这个管理员"时生效。如果你是在已有数据库上重跑，\n        原有管理员的密码不会被覆盖，请用原密码登录。\n'
fi
if [ "${FAILED}" = "1" ]; then
  printf '\n  \033[1;33m有验收项没通过，按 README 第 9 节排障；日志：\033[0m\n'
  echo "    ${C[*]} logs --tail=100 nginx"
  echo "    ${C[*]} logs --tail=100 backend"
fi

cat <<'NEXT'

还要做两件事（脚本不代做，避免悄悄改你的系统）：

  1) 加两条 crontab：证书续期后重载 nginx + 每天备份数据库
     sudo crontab -e
     30 4 * * * cd <仓库路径> && docker compose -f deploy/ecs/docker-compose.yml --env-file deploy/ecs/.env exec -T nginx nginx -s reload
     0 3 * * * <仓库路径>/deploy/ecs/scripts/backup-db.sh >> /var/log/signal-backup.log 2>&1

  2) 登录私有站后：改管理员密码 → 「系统 → 用户管理」建号/审核 → 确认模块权限都在
NEXT
