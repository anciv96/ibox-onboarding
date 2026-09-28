#!/usr/bin/env bash
# Выгрузка ВСЕХ данных (админы и ученики, модули, шаги, вопросы, приглашения, ответы, попытки)
# в один JSON-файл. Читает базу только на чтение — ничего не меняет.
#   scripts/export_data.sh                    — публичная копия с ноутбука (db_public.sqlite3)
#   scripts/export_data.sh db.sqlite3         — любая другая sqlite-база
# Загрузка на новом сервере: python manage.py migrate && python manage.py loaddata <файл>
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
DB="${1:-db_public.sqlite3}"
mkdir -p backups
OUT="backups/export-$(date +%Y%m%d-%H%M).json"
DATABASE_URL="sqlite:///$PWD/$DB" python manage.py dumpdata --natural-foreign --natural-primary \
    --exclude contenttypes --exclude auth.permission --exclude sessions --exclude admin.logentry \
    --indent 1 -o "$OUT"
echo "Выгружено в $OUT"
