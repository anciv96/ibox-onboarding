#!/usr/bin/env bash
# Публичный тест с ноутбука: gunicorn + туннель ngrok. Отдельная база db_public.sqlite3
# (не смешивается с демо-данными разработки).
#   scripts/public.sh start   — запустить и показать публичную ссылку
#   scripts/public.sh restart — перезапустить только сайт (после обновления кода; ссылка ngrok не меняется)
#   scripts/public.sh stop    — остановить всё
#   scripts/public.sh status  — работает ли и какая ссылка
#   scripts/public.sh url     — только ссылка
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8001
LOG_DIR=logs
ENV_FILE=.env.public
ADMIN_PASSWORD_FILE=.public_admin_password
mkdir -p "$LOG_DIR"

public_url() {
    curl -s --max-time 3 http://127.0.0.1:4040/api/tunnels 2>/dev/null \
        | python3 -c "import sys,json
try:
    t = json.load(sys.stdin)['tunnels']
    print(next((x['public_url'] for x in t if x['public_url'].startswith('https')), ''))
except Exception:
    print('')"
}

is_running() { pgrep -f "gunicorn config.wsgi --bind 127.0.0.1:$PORT" >/dev/null; }

prepare_env() {
    source venv/bin/activate
    if [ ! -f "$ENV_FILE" ]; then
        python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(60))" > "$ENV_FILE"
        chmod 600 "$ENV_FILE"
    fi
    set -a; source "$ENV_FILE"; set +a
    export DEBUG=False
    export ALLOWED_HOSTS=".ngrok-free.app,.ngrok-free.dev,.ngrok.app,.ngrok.dev,.ngrok.io,localhost,127.0.0.1${EXTRA_HOST:+,$EXTRA_HOST}"
    export CSRF_TRUSTED_ORIGINS="https://*.ngrok-free.app,https://*.ngrok-free.dev,https://*.ngrok.app,https://*.ngrok.dev,https://*.ngrok.io${EXTRA_HOST:+,https://$EXTRA_HOST}"
    export DATABASE_URL="sqlite:///$PWD/db_public.sqlite3"
}

backup_db() {
    # Перед каждым запуском/перезапуском — копия базы (реальные данные стажёров). Храним последние 15.
    if [ -f db_public.sqlite3 ]; then
        mkdir -p backups
        sqlite3 db_public.sqlite3 ".backup 'backups/auto-db_public-$(date +%Y%m%d-%H%M%S).sqlite3'"
        ls -1t backups/auto-db_public-*.sqlite3 2>/dev/null | tail -n +16 | xargs -I{} rm -f {}
    fi
}

first_run_setup() {
    backup_db
    python manage.py migrate --noinput >/dev/null
    python manage.py collectstatic --noinput >/dev/null
    if ! python manage.py shell -c "import sys; from django.contrib.auth import get_user_model as g; sys.exit(0 if g().objects.filter(is_superuser=True).exists() else 1)" >/dev/null 2>&1; then
        python manage.py seed_demo_data --content-only >/dev/null
        password="$(python3 -c "import secrets; print(secrets.token_urlsafe(14))")"
        ADMIN_PASSWORD="$password" python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
get_user_model().objects.create_superuser('admin', 'admin@salesdoctor.local', os.environ['ADMIN_PASSWORD'])" >/dev/null
        umask 077
        printf 'login: admin\npassword: %s\n' "$password" > "$ADMIN_PASSWORD_FILE"
        echo "Создан админ. Логин и пароль лежат в файле $ADMIN_PASSWORD_FILE"
    fi
}

case "${1:-status}" in
    start)
        prepare_env
        first_run_setup
        if ! is_running; then
            nohup caffeinate -i gunicorn config.wsgi --bind 127.0.0.1:$PORT --workers 2 \
                --access-logfile "$LOG_DIR/gunicorn-access.log" --error-logfile "$LOG_DIR/gunicorn-error.log" \
                >/dev/null 2>&1 &
            sleep 2
        fi
        if [ -z "$(public_url)" ]; then
            nohup ngrok http $PORT ${NGROK_URL:+--url="$NGROK_URL"} --log=stdout > "$LOG_DIR/ngrok.log" 2>&1 &
            for _ in $(seq 1 20); do [ -n "$(public_url)" ] && break; sleep 1; done
        fi
        echo "Локально: http://127.0.0.1:$PORT  (через туннель: https)"
        echo "Публичная ссылка: $(public_url)"
        ;;
    restart)
        pkill -f "gunicorn config.wsgi --bind 127.0.0.1:$PORT" 2>/dev/null || true
        sleep 1
        exec "$0" start
        ;;
    stop)
        pkill -f "ngrok http $PORT" 2>/dev/null || true
        pkill -f "gunicorn config.wsgi --bind 127.0.0.1:$PORT" 2>/dev/null || true
        echo "Остановлено."
        ;;
    url)
        public_url
        ;;
    status)
        if is_running; then echo "gunicorn: работает"; else echo "gunicorn: остановлен"; fi
        url="$(public_url)"
        if [ -n "$url" ]; then echo "ngrok: $url"; else echo "ngrok: не запущен"; fi
        ;;
    *)
        echo "Использование: $0 {start|restart|stop|status|url}"; exit 1 ;;
esac
