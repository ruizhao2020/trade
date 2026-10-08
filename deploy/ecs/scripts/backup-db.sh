#!/usr/bin/env bash
# ============================================================================
# 备份 MySQL 到 deploy/ecs/backups/（gzip，保留最近 7 份）
# ============================================================================
#
# 建议挂到 crontab（凌晨 3 点）：
#   0 3 * * * /root/trade/deploy/ecs/scripts/backup-db.sh >> /var/log/signal-backup.log 2>&1
#
# 恢复方式见 deploy/ecs/README.md「备份与恢复」。

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# 取值用 grep 而不是 source：.env 里的值若含 $ 或空格，被 shell 展开后会变成
# 另一个字符串，而报错只会说"密码错误"，很难查到原因。
read_env() {
  grep -E "^$1=" .env | head -1 | cut -d= -f2-
}

ROOT_PW="$(read_env MYSQL_ROOT_PASSWORD)"
DB="$(read_env SIGNAL_MYSQL_DATABASE)"
DB="${DB:-signal_layer}"

if [ -z "$ROOT_PW" ]; then
  echo "错误：deploy/ecs/.env 里没有 MYSQL_ROOT_PASSWORD" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="backups"
OUT_FILE="${OUT_DIR}/${DB}-${STAMP}.sql.gz"

mkdir -p "$OUT_DIR"

# 用 MYSQL_PWD 传密码：不会出现在容器内的命令行参数里
docker compose --env-file .env exec -T \
  -e MYSQL_PWD="$ROOT_PW" mysql \
  mysqldump --single-transaction --routines --events --default-character-set=utf8mb4 \
  -uroot "$DB" | gzip > "$OUT_FILE"

# 只留最近 7 份，避免把磁盘写满（行情数据表会持续增长）
ls -1t "$OUT_DIR"/*.sql.gz | tail -n +8 | xargs -r rm -f

echo "[$(date '+%F %T')] 备份完成：$OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"
