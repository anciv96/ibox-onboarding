#!/usr/bin/env bash
# Бэкап Postgres из docker-compose стека: pg_dump внутри контейнера db → файл на хосте.
# Портируется на любой сервер: `docker compose exec -T db psql ... < backup.sql` восстановит куда угодно.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="backups/docker-db-$STAMP.sql.gz"

set -a; source .env; set +a

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-ibox}" "${POSTGRES_DB:-ibox}" | gzip > "$OUT"
echo "Бэкап сохранён: $OUT"

# Оставляем последние 14 бэкапов, старые удаляем
ls -1t backups/docker-db-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
