# Деплой

Проект готов к деплою на **Render** или **Railway**. Оба варианта ниже
эквивалентны — выбирай по вкусу. Статика отдаётся через WhiteNoise
(отдельный CDN не нужен), сессии/куки настроены на HTTPS автоматически,
когда `DEBUG=False`.

## Обязательно: сначала переключись на Postgres

⚠️ **Не деплой на SQLite.** У Render и Railway файловая система
эфемерна между деплоями — SQLite-файл может обнулиться, и ты потеряешь
данные всех учеников. Оба сервиса дают Postgres бесплатно/за копейки —
инструкции ниже уже включают его.

`config/settings.py` уже читает `DATABASE_URL` через `dj-database-url` —
достаточно просто задать переменную окружения, код менять не нужно.

---

## Вариант A: Render

### Способ 1 — через `render.yaml` (проще всего)

В репозитории уже лежит [`render.yaml`](render.yaml) — Render поймёт его
как Blueprint и сам создаст веб-сервис + Postgres.

1. Запушь код в GitHub (см. раздел «Git» ниже).
2. На [render.com](https://render.com) → **New** → **Blueprint** →
   выбери репозиторий.
3. Render создаст сервис `ibox-onboarding` и базу `ibox-onboarding-db`,
   свяжет их через `DATABASE_URL` автоматически.
4. Перед первым деплоем задай в Environment ещё две переменные (Render
   попросит их, так как в `render.yaml` они помечены `sync: false`):
   - `ALLOWED_HOSTS` = `ibox-onboarding.onrender.com` (или твой домен)
   - `CSRF_TRUSTED_ORIGINS` = `https://ibox-onboarding.onrender.com`
5. Deploy. Render сам выполнит `collectstatic` и `migrate` (это часть
   `buildCommand` в `render.yaml`).

### Способ 2 — вручную через дашборд

1. **New** → **Web Service** → подключи репозиторий.
2. Runtime: **Python 3**.
3. Build Command:
   ```bash
   pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput
   ```
4. Start Command:
   ```bash
   gunicorn config.wsgi --log-file -
   ```
5. **New** → **PostgreSQL** — создай базу отдельно, скопируй Internal
   Database URL.
6. В Environment веб-сервиса задай:
   - `SECRET_KEY` — сгенерируй случайную строку (например,
     `python -c "import secrets; print(secrets.token_urlsafe(50))"`)
   - `DEBUG` = `False`
   - `ALLOWED_HOSTS` = `<твой-сервис>.onrender.com`
   - `CSRF_TRUSTED_ORIGINS` = `https://<твой-сервис>.onrender.com`
   - `DATABASE_URL` = Internal Database URL из шага 5
7. Deploy.

---

## Вариант B: Railway

1. Запушь код в GitHub.
2. На [railway.app](https://railway.app) → **New Project** →
   **Deploy from GitHub repo**.
3. Railway сам распознает Django-проект (Nixpacks) и найдёт
   [`Procfile`](Procfile) для команды запуска (`web: gunicorn config.wsgi`).
4. В этом же проекте: **New** → **Database** → **Add PostgreSQL**.
   Railway автоматически создаст переменную `DATABASE_URL` и подставит
   её в сервис (Variable Reference) — руками копировать не нужно.
5. В Variables веб-сервиса добавь:
   - `SECRET_KEY` — случайная строка
   - `DEBUG` = `False`
   - `ALLOWED_HOSTS` = `<твой-сервис>.up.railway.app`
   - `CSRF_TRUSTED_ORIGINS` = `https://<твой-сервис>.up.railway.app`
6. После первого деплоя выполни миграции разово через Railway CLI (или
   Shell в дашборде):
   ```bash
   railway run python manage.py migrate
   ```
   (Если хочешь, чтобы миграции гонялись автоматически при каждом
   деплое, добавь `python manage.py migrate --noinput &&` в начало
   Start Command в настройках сервиса.)

---

## Вариант C: Docker на своём VPS

Свой сервер (Timeweb, Selectel, Hetzner, DigitalOcean — любой с Ubuntu/Debian
и Docker). Стек: `docker-compose.yml` — три контейнера: **db** (Postgres 16,
данные в именованном томе `pgdata`), **web** (Django/gunicorn, сам собирается
из [`Dockerfile`](Dockerfile)), **caddy** (реверс-прокси, сам получает
HTTPS-сертификат Let's Encrypt по домену).

**Правило, которое делает перенос на другой сервер безопасным: данные живут
только в томе `pgdata`, а не в образе.** Образ — это просто код, его можно
пересобирать и выбрасывать; сервер можно менять — данные при этом не трогают.

### Первый запуск

1. На сервере: поставь Docker и Docker Compose
   (`curl -fsSL https://get.docker.com | sh`, Compose v2 идёт в комплекте).
2. Направь A-запись домена на IP сервера (нужно для Caddy — без домена
   HTTPS не получится, но можно временно оставить `DOMAIN=IP-адрес` в
   `.env` и открыть по http).
3. Склонируй репозиторий на сервер, скопируй `.env.docker.example` → `.env`
   и заполни (`SECRET_KEY`, `POSTGRES_PASSWORD`, `ALLOWED_HOSTS`, `DOMAIN`).
4. Подними стек:
   ```bash
   docker compose up -d --build
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```
5. Открой `https://<домен>/admin/` — сертификат Caddy получит сам при первом
   обращении (может занять минуту).

### Бэкапы

`scripts/docker_backup.sh` — `pg_dump` из контейнера `db` в
`backups/docker-db-<дата>.sql.gz` (хранит последние 14, старые чистит сам).
Запускай по крону на сервере (`crontab -e`):
```
0 3 * * * cd /путь/к/проекту && scripts/docker_backup.sh >> logs/backup.log 2>&1
```
**Важно**: сами файлы бэкапа тоже нужно периодически скачивать с сервера
себе на компьютер или в облако (`scp`/`rsync`) — если сервер физически
недоступен, локальная папка `backups/` на нём не поможет.

### Перенос на другой сервер без потери данных

Docker-образ переносить не нужно — он просто пересобирается из кода. Нужно
перенести только данные:

```bash
# На старом сервере
scripts/docker_backup.sh                 # создаёт backups/docker-db-*.sql.gz
scp backups/docker-db-*.sql.gz новый-сервер:/путь/к/проекту/backups/

# На новом сервере
git clone <репозиторий> && cd проект     # или просто скопировать файлы
cp .env.docker.example .env && nano .env # тот же SECRET_KEY/пароль, если хочешь сохранить сессии
docker compose up -d --build
docker compose exec web python manage.py migrate
scripts/docker_restore.sh backups/docker-db-<дата>.sql.gz
```

Это тот же принцип, что уже применяется для тестового сервера на ноутбуке
(см. «Перенос данных с ноутбука на сервер» ниже) — только вместо
`dumpdata`/`loaddata` используется `pg_dump`/`psql`, потому что данные сразу
живут в Postgres, а не в SQLite.

### Что теряется при смене сервера

- **IP-адрес** — если домен уже настроен на новый IP, ничего менять не
  нужно; если домена нет, ссылки-приглашения (они строятся от текущего
  адреса в браузере) придётся выдать заново.
- **Ничего из данных** — ученики, ответы, попытки, вопросы, приглашения:
  всё восстанавливается из бэкапа `pg_dump` один в один.

---

## После первого деплоя (общее для всех вариантов)

1. Создай своего админа (замени `<platform-shell>` на способ зайти в
   консоль сервиса — у Render это **Shell** в дашборде, у Railway —
   `railway run`):
   ```bash
   python manage.py createsuperuser
   ```
2. Наполни курс реальными модулями и вопросами через `/admin/` — либо
   вручную, либо адаптируй `seed_demo_data` под реальный контент
   (команда сделана для тестовых данных, для продакшена лучше не
   гонять её как есть — она создаёт демо-учеников с известными
   паролями).
3. Зайди на `https://<твой-домен>/admin/` и проверь, что всё работает.

## Переменные окружения — шпаргалка

| Переменная            | Значение в проде                          |
|------------------------|--------------------------------------------|
| `SECRET_KEY`           | случайная строка, никому не показывать     |
| `DEBUG`                 | `False`                                    |
| `ALLOWED_HOSTS`         | домен сервиса, без `https://`              |
| `CSRF_TRUSTED_ORIGINS`  | `https://` + домен сервиса                 |
| `DATABASE_URL`          | подставляется платформой автоматически     |

## Перенос данных с ноутбука на сервер (после публичного теста)

Данные, которые вносились на публичной копии (`db_public.sqlite3`), переносятся
без повторного ввода: выгрузка в JSON и загрузка в базу сервера.

1. **На ноутбуке** (ничего не меняет, только читает):
   ```bash
   scripts/export_data.sh
   ```
   Появится файл `backups/export-<дата>.json` — админы и ученики (с хэшами паролей,
   пароли переносятся и работают), модули, шаги, вопросы, финальный тест, приглашения,
   попытки и заметки.
2. Скопируй этот файл на сервер (scp/sftp) в папку проекта.
3. **На сервере** в пустой базе (НЕ запускай `seed_demo_data` — он создаёт демо-данные):
   ```bash
   python manage.py migrate
   python manage.py loaddata export-<дата>.json
   ```
   Не нужно делать `createsuperuser` — админ переедет вместе с данными.
4. Проверь вход в `/admin/`.

Что важно знать:
- **PostgreSQL на сервере должен быть версии 15 или новее** (Django 6.1 не работает с 14 и
  старше; на локальном ноутбуке 14.19, поэтому там проверить перенос в Postgres нельзя).
  Драйвер `psycopg` уже в `requirements.txt`.
- **Ссылки-приглашения** содержат домен. Уже использованные (стажёр зарегистрировался)
  ничего не теряют. Неиспользованные придётся скопировать заново из админки нового
  сайта — старый ngrok-адрес перестанет работать.
- Регистрации по старому ngrok-адресу, сделанные ПОСЛЕ выгрузки, в файл не попадут:
  выгружай непосредственно перед переключением и не вноси данные на старой копии
  после этого.
- Копии на всякий случай: `scripts/public.sh` сам делает копию базы в `backups/` перед
  каждым запуском/перезапуском, а перед переездом сделай ещё и `scripts/export_data.sh`.

## Опционально: усиление безопасности (HSTS)

`python manage.py check --deploy` после включения прод-настроек покажет
одно предупреждение про `SECURE_HSTS_SECONDS` — это осознанно оставлено
выключенным (Django сам предупреждает: включать HSTS невнимательно
может необратимо сломать доступ по HTTP). Если хочешь включить, добавь
в `config/settings.py` внутри блока `if not DEBUG:`:
```python
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # неделя для начала, потом увеличить
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
```

## Git

Если ещё не закоммитил:
```bash
git add -A
git commit -m "Initial commit"
git remote add origin <ссылка-на-твой-github-репозиторий>
git push -u origin master
```
(В `/Users/h` уже есть отдельный git-репозиторий верхнего уровня — он
никак не связан с этим проектом, для деплоя используется git-репозиторий
именно в этой папке, инициализированный на Этапе 1.)
