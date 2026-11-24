"""
Configurações do Django para o FastLine.

Todas as informações sensíveis ou dependentes do ambiente são lidas de
variáveis de ambiente (arquivo .env na raiz do projeto). Veja .env.example.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    valor = os.environ.get(name)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "sim", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Chave apenas para desenvolvimento local. Nunca use em produção.
        SECRET_KEY = "dev-only-insecure-key-defina-DJANGO_SECRET_KEY-no-arquivo-env"
    else:
        raise ImproperlyConfigured(
            "Defina DJANGO_SECRET_KEY no arquivo .env (ou DJANGO_DEBUG=True para desenvolvimento)."
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Render define este host automaticamente (ex.: fastline.onrender.com).
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    "core",
    "usuarios",
    "estabelecimentos",
    "produtos",
    "pedidos",
    "painel",
    "administracao",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fastline.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.fastline",
            ],
        },
    },
]

WSGI_APPLICATION = "fastline.wsgi.application"

# Banco de dados: SQLite por padrão; para PostgreSQL basta definir DATABASE_URL
# (ex.: postgres://usuario:senha@localhost:5432/fastline) e instalar psycopg.
DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.environ.get("DATABASE_CONN_MAX_AGE", "0")),
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Usuário personalizado (o banco original já foi criado com este modelo: a
# tabela de log do admin aponta para usuarios_usuario).
AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "usuarios:login"
LOGIN_REDIRECT_URL = "core:inicio"
LOGOUT_REDIRECT_URL = "usuarios:login"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Uploads de imagem de produto: limite de tamanho (bytes).
FASTLINE_IMAGEM_MAX_BYTES = 3 * 1024 * 1024

# Regras de negócio
FASTLINE_RESERVA_MINUTOS = int(os.environ.get("FASTLINE_RESERVA_MINUTOS", "15"))
FASTLINE_TAXA_SERVICO = os.environ.get("FASTLINE_TAXA_SERVICO", "0.00")
FASTLINE_MAX_ITENS_POR_PRODUTO = int(os.environ.get("FASTLINE_MAX_ITENS_POR_PRODUTO", "20"))

# PagSeguro / PagBank
PAGSEGURO_AMBIENTE = os.environ.get("PAGSEGURO_AMBIENTE", "sandbox")  # sandbox | producao
PAGSEGURO_TOKEN = os.environ.get("PAGSEGURO_TOKEN", "")
PAGSEGURO_URL_PUBLICA = os.environ.get("PAGSEGURO_URL_PUBLICA", "").rstrip("/")
PAGSEGURO_TIMEOUT = int(os.environ.get("PAGSEGURO_TIMEOUT", "20"))
# Sem token, o sistema usa o modo "pagamento no balcão": o pedido fica
# aguardando pagamento até um funcionário confirmar o recebimento.
PAGAMENTO_BALCAO_HABILITADO = env_bool("PAGAMENTO_BALCAO_HABILITADO", True)

# Segurança
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # o JavaScript lê o token CSRF do formulário, não do cookie
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "fastline": {"handlers": ["console"], "level": os.environ.get("FASTLINE_LOG_LEVEL", "CRITICAL" if "test" in sys.argv[1:2] else "INFO")},
    },
}

# E-mail (formato novo do Django 6.1, mantido do projeto original)
#DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "FastLine <no-reply@localhost>")
#EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
#EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
#EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
#EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
#EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
#EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)

MAILERS = {
    "default": {
        "BACKEND": os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"),
    },
}
