"""
Django settings for config project (iBox onboarding platform).
"""

from pathlib import Path

import dj_database_url
from django.urls import reverse_lazy
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Render/Railway/аналоги отдают HTTPS через прокси и пробрасывают протокол в этом заголовке.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    'unfold',  # должен идти перед django.contrib.admin
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'accounts',
    'onboarding',
    'finaltest',
    'practice',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.onboarding_progress',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database: SQLite locally by default; set DATABASE_URL in production (Postgres)
# to avoid losing data on Render/Railway's ephemeral filesystem between deploys.
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization: interface is Russian by default, Uzbek scaffolded for later.
LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', 'Русский'),
    ('uz', 'Oʻzbekcha'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365  # выбор языка запоминается на год

TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Без manifest-хранилища: {% static 'logo.png' %} не падает с 500 при DEBUG=False, пока файла нет.
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'onboarding:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'


# Оформление админки (django-unfold). Основной цвет — фирменный #2663EB.
UNFOLD = {
    'SITE_TITLE': 'iBox — онбординг',
    'SITE_HEADER': 'iBox',
    'SITE_SUBHEADER': 'Онбординг менеджеров',
    'SITE_URL': '/',
    'SITE_SYMBOL': 'school',
    'SITE_ICON': 'config.dashboard.site_icon',
    'SHOW_HISTORY': False,
    'DASHBOARD_CALLBACK': 'config.dashboard.dashboard_callback',
    'COLORS': {
        'primary': {
            '50': '#eff4ff', '100': '#dbe6fe', '200': '#bfd3fe', '300': '#93b6fd',
            '400': '#5f8ffa', '500': '#3b6ff5', '600': '#2663eb', '700': '#1d4fc9',
            '800': '#1c43a3', '900': '#1c3b81', '950': '#162c63',
        },
    },
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': False,
        'navigation': [
            {
                'title': 'Стажёры',
                'separator': False,
                'items': [
                    {
                        'title': 'Ученики',
                        'icon': 'group',
                        'link': reverse_lazy('admin:accounts_student_changelist'),
                        'badge': 'config.dashboard.pending_review_badge',
                        'badge_variant': 'danger',
                    },
                    {
                        'title': 'Приглашения',
                        'icon': 'mail',
                        'link': reverse_lazy('admin:accounts_invitation_changelist'),
                    },
                    {
                        'title': 'Попытки финального теста',
                        'icon': 'fact_check',
                        'link': reverse_lazy('admin:finaltest_finaltestsubmission_changelist'),
                    },
                ],
            },
            {
                'title': 'Контент курса',
                'separator': True,
                'items': [
                    {
                        'title': 'Модули',
                        'icon': 'menu_book',
                        'link': reverse_lazy('admin:onboarding_module_changelist'),
                    },
                    {
                        'title': 'Контрольные вопросы',
                        'icon': 'help',
                        'link': reverse_lazy('admin:onboarding_modulequestion_changelist'),
                    },
                    {
                        'title': 'Вопросы тренировки',
                        'icon': 'sports_esports',
                        'link': reverse_lazy('admin:practice_practicequestion_changelist'),
                    },
                    {
                        'title': 'Вопросы финального теста',
                        'icon': 'quiz',
                        'link': reverse_lazy('admin:finaltest_finaltestitem_changelist'),
                    },
                ],
            },
            {
                'title': 'Система',
                'separator': True,
                'items': [
                    {
                        'title': 'Пользователи',
                        'icon': 'person',
                        'link': reverse_lazy('admin:auth_user_changelist'),
                    },
                    {
                        'title': 'Группы',
                        'icon': 'lock',
                        'link': reverse_lazy('admin:auth_group_changelist'),
                    },
                ],
            },
        ],
    },
}


# Финальный тест: из банка вопросов каждому ученику выпадает случайная выборка
FINAL_TEST_MCQ_COUNT = config('FINAL_TEST_MCQ_COUNT', default=17, cast=int)
FINAL_TEST_OPEN_COUNT = config('FINAL_TEST_OPEN_COUNT', default=3, cast=int)
