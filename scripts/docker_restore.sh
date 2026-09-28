#!/usr/bin/env bash
# Восстановление из бэкапа docker_backup.sh на ЭТОМ ИЛИ ЛЮБОМ ДРУГОМ сервере с тем же docker-compose.yml.
# Использование: scripts/docker_restore.sh backups/docker-db-20260101-120000.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:?Укажи путь к файлу бэкапа: scripts/docker_restore.sh backups/docker-db-....sql.gz}"
set -a; source .env; set +a

echo "Это ПЕРЕЗАПИШЕТ текущую базу в контейнере db. Ctrl+C, чтобы отменить."
sleep 5

gunzip -c "$FILE" | docker compose exec -T db psql -U "${POSTGRES_USER:-ibox}" "${POSTGRES_DB:-ibox}"
echo "Восстановлено из $FILE"
