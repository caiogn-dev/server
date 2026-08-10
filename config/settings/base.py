"""
Django base settings for WhatsApp Business Platform.
"""
import os
from pathlib import Path
from datetime import timedelta
from urllib.parse import parse_qs, unquote, urlparse
from django.templatetags.static import static

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    import secrets as _secrets
    SECRET_KEY = _secrets.token_urlsafe(50)

# Dedicated encryption key for Fernet (token storage).
# If not set, falls back to SECRET_KEY so existing encrypted tokens remain readable.
# Rotate this key (not SECRET_KEY) to re-encrypt tokens without breaking Django sessions.
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')

DEBUG = os.environ.get('DEBUG', os.environ.get('DJANGO_DEBUG', 'False')).lower() == 'true'


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean environment variables consistently."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}

# SECURITY: Don't allow wildcard by default - require explicit configuration
_allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',') if h.strip()] if _allowed_hosts_env else ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'daphne',
    # 'unfold',  # DISABLED: Unfold package v1.2.4 is broken (missing display_for_field, prettify_json, etc)
    # 'unfold.contrib.filters',
    # 'unfold.contrib.inlines',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',
    'django_celery_beat',
    'storages',
    # Local apps
    'apps.core',
    'apps.whatsapp.apps.WhatsAppConfig',
    'apps.conversations',
    # 'apps.langflow',  # DEPRECATED: Replaced by apps.agents (Langchain)
    'apps.agents',  # Langchain AI Agents (replaces Langflow)
    'apps.notifications',
    'apps.audit',
    'apps.campaigns',
    'apps.automation',
    'apps.stores',  # Multi-store management (unified)
    'apps.fiscal',  # NFC-e (Focus NFe hoje, SEFAZ direto quando houver certificado)
    'apps.marketing',  # Email marketing with Resend
    'apps.instagram',  # Instagram Messaging API integration
    'apps.messaging',  # Unified messaging dispatcher (includes Messenger)
    'apps.webhooks',  # Centralized webhook handling
    'apps.handover',  # Handover Protocol (Bot/Human transfer)
    'apps.users',  # Unified user management (NEW)
    'apps.public_api',  # Public read-only API for storefronts (no auth required)
    'apps.panel',  # Pastita Panel — Django-rendered admin UI at /panel/
    'apps.postado',  # Postado — AI social media posts for small businesses
    'apps.orders',  # Uber delivery dispatch
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'apps.core.middleware.CSRFExemptMiddleware',  # Must be before CsrfViewMiddleware
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.TenantMiddleware',
    'apps.core.middleware.TokenExpirationMiddleware',
    'apps.core.middleware.RequestLoggingMiddleware',
    'apps.core.middleware.RateLimitMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Redis (shared)
REDIS_URL = os.environ.get('REDIS_URL', '').strip()

# Channels - use Redis if available, otherwise use in-memory
if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
                'capacity': 3000,
                'expiry': 60,
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL:
    parsed_db = urlparse(DATABASE_URL)
    if parsed_db.scheme in ('postgres', 'postgresql'):
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': parsed_db.path.lstrip('/'),
                'USER': unquote(parsed_db.username or ''),
                'PASSWORD': unquote(parsed_db.password or ''),
                'HOST': parsed_db.hostname or 'localhost',
                'PORT': str(parsed_db.port or 5432),
                'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
                # Obrigatório atrás do pgbouncer em transaction pooling: cursores
                # server-side (.iterator()) podem cair em outra conexão de servidor.
                'DISABLE_SERVER_SIDE_CURSORS': True,
            }
        }
        db_query = parse_qs(parsed_db.query)
        sslmode = db_query.get('sslmode', [None])[0]
        if sslmode:
            DATABASES['default']['OPTIONS'] = {'sslmode': sslmode}
    else:
        # Fallback to SQLite if DATABASE_URL is not PostgreSQL
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    # No DATABASE_URL - use SQLite as fallback
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # Endpoints autenticados e misc não classificados
        'anon': '120/minute',
        'user': '600/minute',
        # Catálogo público (read-only) — storefront pode fazer muitos requests ao navegar
        'public_read': '300/minute',
        # Carrinho (escrita pública) — mais restritivo que leitura, menos que checkout
        'public_write': '60/minute',
        # Checkout: proteção anti-bot real — 20/min por IP (antes era 5, muito restritivo)
        'checkout': '20/minute',
        # Auth: OTP brute-force protection — manter restritivo
        'auth': '10/minute',
        # Lead capture form — low rate to prevent spam
        'lead_create': '10/hour',
        # Webhooks de integrações externas — volume alto esperado
        'webhook': '10000/hour',
        # Agente IA: proteção contra abuso de custo com LLMs externos
        'agent_process': '120/hour',
        # Geo (autosuggest / delivery-zones): proxy não-auth p/ Google Maps PAGO.
        # Protege a conta de billing contra DoS financeiro.
        'geo': '30/minute',
        # Pedido por token: endpoint AllowAny — limita varredura de tokens e DoS no DB.
        # Defesa em profundidade; o token tem 256-bit de entropia (brute-force inviável).
        'order_token': '30/minute',
    },
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

# CORS
# Note: CORS_ALLOW_ALL_ORIGINS cannot be True when CORS_ALLOW_CREDENTIALS is True
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    # Pastita dashboard
    "https://painel.pastita.com.br",
    # Pastita main site / pastita-3d storefront (custom domains)
    "https://pastita.com.br",
    "https://www.pastita.com.br",
    # pastita-3d storefront — Vercel deployment
    "https://pastita-3d.vercel.app",
    # ce-saladas storefront — Vercel deployment
    "https://ce-saladas.vercel.app",
    # ce-saladas dev server (openclaw tunnel + local)
    "https://openclaw.pastita.com.br",
    "http://localhost:3001",
    # postado admin panel dev server
    "http://localhost:3099",
    # Backend / API self-origin (health checks, swagger)
    "https://backend.pastita.com.br",
    "https://api.pastita.com.br",
]
cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if cors_origins:
    CORS_ALLOWED_ORIGINS.extend([o.strip() for o in cors_origins.split(',') if o.strip()])

# Additional CORS settings
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-cart-key',
    'x-requested-with',
    'x-tenant-slug',
    'x-store-slug',
]
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CORS_EXPOSE_HEADERS = [
    'content-type',
    'x-csrftoken',
]

# Monitoring — set to a Slack/Discord incoming-webhook URL to receive DLQ alerts.
# Leave blank to only log (no HTTP request will be made).
MONITORING_WEBHOOK_URL = os.environ.get('MONITORING_WEBHOOK_URL', '')

# Web Push (VAPID) — generate keys with: python manage.py generate_vapid_keys
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'admin@pastita.com.br')

# Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL or 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL or 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_RESULT_EXPIRES = int(os.environ.get('CELERY_RESULT_EXPIRES', '3600'))  # 1 hora

# Cache configuration - use Redis if available, otherwise use local memory
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

# WhatsApp Business API
WHATSAPP_API_VERSION = os.environ.get('WHATSAPP_API_VERSION', 'v22.0')
WHATSAPP_API_BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN', '')
WHATSAPP_APP_SECRET = os.environ.get('WHATSAPP_APP_SECRET', '')
# App ID do Meta — necessário para o Embedded Signup (troca code->token OAuth).
# É o ID público do app (não secreto). Defina META_APP_ID no .env.
META_APP_ID = os.environ.get('META_APP_ID', '').strip()
# App secret do Meta (client_secret do OAuth). Fallback p/ WHATSAPP_APP_SECRET.
META_APP_SECRET = (os.environ.get('META_APP_SECRET', '') or WHATSAPP_APP_SECRET).strip()
# Secret genérico de fallback para webhooks Meta (whatsapp/instagram/messenger)
# quando não há WebhookEndpoint nem secret específico configurado.
META_WEBHOOK_APP_SECRET = os.environ.get('META_WEBHOOK_APP_SECRET', '')
WHATSAPP_ENABLE_LLM_FALLBACK = os.environ.get('WHATSAPP_ENABLE_LLM_FALLBACK', 'false').strip().lower() in {
    '1', 'true', 'yes', 'on'
}
WHATSAPP_FORCE_DISABLE_LLM = os.environ.get('WHATSAPP_FORCE_DISABLE_LLM', 'false').strip().lower() in {
    '1', 'true', 'yes', 'on'
}
WHATSAPP_ORCHESTRATOR_TIMEOUT = int(os.environ.get('WHATSAPP_ORCHESTRATOR_TIMEOUT', '90'))
DEFAULT_STORE_SLUG = os.environ.get('DEFAULT_STORE_SLUG', '').strip()

_websocket_allowed_origins_env = os.environ.get('WEBSOCKET_ALLOWED_ORIGINS', '')
WEBSOCKET_ALLOWED_ORIGINS = [
    origin.strip() for origin in _websocket_allowed_origins_env.split(',') if origin.strip()
]
WEBSOCKET_ALLOW_ALL_ORIGINS = os.environ.get('WEBSOCKET_ALLOW_ALL_ORIGINS', 'false').strip().lower() in {
    '1', 'true', 'yes', 'on'
}

# Default WhatsApp account configuration (existing account lookup + optional auto-create)
DEFAULT_WHATSAPP_ACCOUNT_NAME = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_NAME', 'Pastita WhatsApp Business')
DEFAULT_WHATSAPP_ACCOUNT_ID = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_ID', os.environ.get('ECOMMERCE_DEFAULT_ACCOUNT_ID', '')
).strip()
DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER', os.environ.get('PASTITA_WHATSAPP_NUMBER', '')
).strip()
DEFAULT_WHATSAPP_ACCOUNT_DISPLAY_NUMBER = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_DISPLAY_NUMBER', DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER
).strip()
DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER_ID = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER_ID', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_WABA_ID = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_WABA_ID', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_ACCESS_TOKEN = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_ACCESS_TOKEN', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_OWNER_EMAIL = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_OWNER_EMAIL', os.environ.get('ADMIN_EMAIL', '')
).strip()
DEFAULT_WHATSAPP_ACCOUNT_STATUS = os.environ.get('DEFAULT_WHATSAPP_ACCOUNT_STATUS', 'active').strip().lower()

# WhatsApp phone (with country code, e.g. 5511999999999) that receives lead notifications from /cadastro
OWNER_NOTIFICATION_PHONE = os.environ.get('OWNER_NOTIFICATION_PHONE', '').strip()
DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE = os.environ.get(
    'DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE', 'False'
).strip().lower() == 'true'
_DEFAULT_WHATSAPP_STORE_SLUGS = os.environ.get('DEFAULT_WHATSAPP_STORE_SLUGS', '')
DEFAULT_WHATSAPP_STORE_SLUGS = [
    slug.strip() for slug in _DEFAULT_WHATSAPP_STORE_SLUGS.split(',') if slug.strip()
]
DEFAULT_WHATSAPP_STORE_METADATA_KEY = os.environ.get('DEFAULT_WHATSAPP_STORE_METADATA_KEY', 'whatsapp_account_id')

# Instagram API Configuration
# Approach: Messenger API for Instagram (Facebook Login)
# Docs: https://developers.facebook.com/docs/instagram-platform/
# Required Facebook App permissions:
#   instagram_basic, instagram_manage_messages,
#   pages_manage_metadata, pages_showlist, business_management
# Token needed for /{page_id}/messages: Page Access Token (stored in InstagramAccount.page_access_token)
INSTAGRAM_APP_ID = os.environ.get('INSTAGRAM_APP_ID', '')
INSTAGRAM_APP_SECRET = os.environ.get('INSTAGRAM_APP_SECRET', '')
INSTAGRAM_WEBHOOK_VERIFY_TOKEN = os.environ.get('INSTAGRAM_WEBHOOK_VERIFY_TOKEN', '')

# Maps
GEO_PROVIDER = os.environ.get('GEO_PROVIDER', 'google').strip().lower()
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_KEY', '').strip()
# Chave server-side sem restrição de HTTP referrer (Directions, Geocoding, Routes).
# Se ausente, usa GOOGLE_MAPS_KEY (que pode ter restrição de browser e causar REQUEST_DENIED).
GOOGLE_MAPS_SERVER_KEY = os.environ.get('GOOGLE_MAPS_SERVER_KEY', '').strip()

# Toca Delivery SaaS integration
TOCA_DELIVERY_API_URL = os.environ.get('TOCA_DELIVERY_API_URL', 'https://api.tocadelivery.com.br').strip()
TOCA_DELIVERY_EMAIL = os.environ.get('TOCA_DELIVERY_EMAIL', '').strip()
TOCA_DELIVERY_PASSWORD = os.environ.get('TOCA_DELIVERY_PASSWORD', '').strip()
# Set to 'true' to enable automatic dispatch for all stores
TOCA_DELIVERY_ENABLED = os.environ.get('TOCA_DELIVERY_ENABLED', 'false').strip().lower() == 'true'
# Webhook secret shared with Toca Delivery for validating status callbacks
TOCA_DELIVERY_WEBHOOK_SECRET = os.environ.get('TOCA_DELIVERY_WEBHOOK_SECRET', '').strip()

# Base URL for webhooks and callbacks
BASE_URL = os.environ.get('BASE_URL', 'https://backend.pastita.com.br')
API_BASE_URL = os.environ.get('API_BASE_URL', os.environ.get('BACKEND_URL', 'https://backend.pastita.com.br'))
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'https://painel.pastita.com.br')

# Mercado Pago Integration
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get('MERCADO_PAGO_ACCESS_TOKEN', '')
MERCADO_PAGO_PUBLIC_KEY = os.environ.get('MERCADO_PAGO_PUBLIC_KEY', '')
PASTITA_WHATSAPP_NUMBER = os.environ.get('PASTITA_WHATSAPP_NUMBER', '')
PASTITA_BASE_URL = os.environ.get('PASTITA_BASE_URL', '')

# Meta transport version. Pixel IDs and CAPI credentials are stored per Store.
META_CAPI_VERSION = os.environ.get('META_CAPI_VERSION', 'v25.0').strip()

# ============================================================================
# AI/LLM CONFIGURATION - Unified through LiteLLM Proxy (preferred) or direct
# ============================================================================

# LiteLLM Proxy (RECOMMENDED - centralized management)
LITELLM_PROXY_URL = os.environ.get('LITELLM_PROXY_URL', 'http://litellm-proxy:4000')
LITELLM_PROXY_KEY = os.environ.get('LITELLM_PROXY_KEY', '')

# Direct API Keys (fallback when LiteLLM is not available)
# Kimi API (Primary - Moonshot AI)
KIMI_API_KEY = os.environ.get('KIMI_API_KEY', '')
KIMI_BASE_URL = os.environ.get('KIMI_BASE_URL', 'https://api.kimi.com/coding/')
KIMI_MODEL_NAME = os.environ.get('KIMI_MODEL_NAME', 'kimi-for-coding')

# OpenAI (optional fallback)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_MODEL_NAME = os.environ.get('OPENAI_MODEL_NAME', 'gpt-4o-mini')

# Anthropic (optional fallback)
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
ANTHROPIC_MODEL_NAME = os.environ.get('ANTHROPIC_MODEL_NAME', 'claude-3-5-sonnet-20241022')

# NVIDIA NIM (optional fallback)
NVIDIA_API_KEY = os.environ.get('NVIDIA_API_KEY', '')
NVIDIA_API_BASE_URL = os.environ.get('NVIDIA_API_BASE_URL', 'https://integrate.api.nvidia.com/v1')
NVIDIA_MODEL_NAME = os.environ.get('NVIDIA_MODEL_NAME', 'nvidia/llama-3.1-nemotron-70b-instruct')
# Modelo dos insights do painel (resumo diário/análise de conversas)
NVIDIA_INSIGHTS_MODEL = os.environ.get('NVIDIA_INSIGHTS_MODEL', 'meta/llama-3.1-70b-instruct')

# Unified AI Configuration Helper
def get_ai_config():
    """
    Returns unified AI configuration.
    Prioritizes LiteLLM proxy, falls back to direct API keys.
    """
    if LITELLM_PROXY_KEY:
        return {
            'mode': 'proxy',
            'base_url': LITELLM_PROXY_URL,
            'api_key': LITELLM_PROXY_KEY,
            'model': 'kimi-coder',  # Model name in LiteLLM
        }
    elif KIMI_API_KEY:
        return {
            'mode': 'direct',
            'base_url': KIMI_BASE_URL,
            'api_key': KIMI_API_KEY,
            'model': KIMI_MODEL_NAME,
        }
    elif OPENAI_API_KEY:
        return {
            'mode': 'direct',
            'base_url': OPENAI_BASE_URL,
            'api_key': OPENAI_API_KEY,
            'model': OPENAI_MODEL_NAME,
        }
    elif ANTHROPIC_API_KEY:
        return {
            'mode': 'direct',
            'base_url': ANTHROPIC_BASE_URL,
            'api_key': ANTHROPIC_API_KEY,
            'model': ANTHROPIC_MODEL_NAME,
        }
    elif NVIDIA_API_KEY:
        return {
            'mode': 'direct',
            'base_url': NVIDIA_API_BASE_URL,
            'api_key': NVIDIA_API_KEY,
            'model': NVIDIA_MODEL_NAME,
        }
    return None

# Rate Limiting — disabled automatically during test runs to avoid 429s from shared loopback IP
import sys as _sys
_TESTING = len(_sys.argv) > 1 and _sys.argv[1] == 'test'
RATE_LIMIT_ENABLED = False if _TESTING else os.environ.get('RATE_LIMIT_ENABLED', 'True').lower() == 'true'
RATE_LIMIT_REQUESTS = int(os.environ.get('RATE_LIMIT_REQUESTS', '100'))
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', '60'))
_RATE_LIMIT_WHITELIST = os.environ.get('RATE_LIMIT_WHITELIST_PATHS', '/api/v1/stores/orders/by-token/,/api/v1/stores/stores/,/api/v1/notifications/,/api/v1/automation/')
RATE_LIMIT_WHITELIST_PATHS = [
    path.strip() for path in _RATE_LIMIT_WHITELIST.split(',') if path.strip()
]
RATE_LIMIT_SCOPED_PATHS = [
    {
        'prefix': '/api/v1/stores/print/',
        'requests': int(os.environ.get('RATE_LIMIT_PRINT_REQUESTS', '1200')),
        'window': int(os.environ.get('RATE_LIMIT_PRINT_WINDOW', '60')),
        'key_by': 'print_agent_or_ip',
    },
    {
        'prefix': '/api/v1/stores/orders/',
        'requests': int(os.environ.get('RATE_LIMIT_STORE_ORDERS_REQUESTS', '600')),
        'window': int(os.environ.get('RATE_LIMIT_STORE_ORDERS_WINDOW', '60')),
        'key_by': 'auth_or_ip',
    },
    {
        'prefix': '/api/v1/whatsapp/messages/',
        'requests': int(os.environ.get('RATE_LIMIT_WHATSAPP_MESSAGES_REQUESTS', '600')),
        'window': int(os.environ.get('RATE_LIMIT_WHATSAPP_MESSAGES_WINDOW', '60')),
        'key_by': 'auth_or_ip',
    },
    {
        'prefix': '/api/v1/conversations/',
        'requests': int(os.environ.get('RATE_LIMIT_CONVERSATIONS_REQUESTS', '600')),
        'window': int(os.environ.get('RATE_LIMIT_CONVERSATIONS_WINDOW', '60')),
        'key_by': 'auth_or_ip',
    },
]

# DRF Token TTL — tokens older than this many days are rejected with 401.
# Set AUTH_TOKEN_TTL_DAYS=0 in env to disable expiration entirely (returns None).
_raw_ttl = os.environ.get('AUTH_TOKEN_TTL_DAYS', '30')
AUTH_TOKEN_TTL_DAYS = None if _raw_ttl == '0' else int(_raw_ttl)

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            '()': 'apps.core.logging.JsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'app.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'json',
            'delay': True,  # Don't open file immediately
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# DRF Spectacular (OpenAPI)
SPECTACULAR_SETTINGS = {
    'TITLE': 'WhatsApp Business Platform API',
    'DESCRIPTION': 'API completa para integração com WhatsApp Business',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get('MERCADO_PAGO_ACCESS_TOKEN', '')
MERCADO_PAGO_WEBHOOK_SECRET = os.environ.get('MERCADO_PAGO_WEBHOOK_SECRET', '')
MERCADO_PAGO_STATEMENT_DESCRIPTOR = os.environ.get('MERCADO_PAGO_STATEMENT_DESCRIPTOR', 'CARDAPIDEX')
# Nome do titular da conta coletora exibido no aviso do PIX (o banco do pagador
# mostra o titular real da chave via DICT, não o merchant name do QR).
MERCADO_PAGO_RECIPIENT_NAME = os.environ.get('MERCADO_PAGO_RECIPIENT_NAME', '')
# SaaS billing: cobrança automática no fim do trial (Celery). OFF até validar em sandbox.
# A assinatura iniciada pelo dono (botão "Assinar") NÃO depende deste flag.
BILLING_AUTOCHARGE_ENABLED = os.environ.get('BILLING_AUTOCHARGE_ENABLED', 'false').lower() == 'true'
# URL do painel (back_url do checkout de assinatura). FRONTEND_URL é lista p/ CORS, não serve.
BILLING_PANEL_URL = os.environ.get('BILLING_PANEL_URL', 'https://painel.cardapidex.com.br').rstrip('/')
# Link na Bio: base do storefront (link "Cardápio") e base pública da página bio.cardapidex.com.br/<slug>.
STOREFRONT_BASE_URL = os.environ.get('STOREFRONT_BASE_URL', 'https://cardapidex.com.br')
BIO_BASE_URL = os.environ.get('BIO_BASE_URL', 'https://bio.cardapidex.com.br')
# Dias de carência após o fim do trial antes de suspender a loja.
BILLING_GRACE_DAYS = int(os.environ.get('BILLING_GRACE_DAYS', '3'))
# Dias em past_due (cobrança falhou) antes de suspender.
BILLING_DUNNING_DAYS = int(os.environ.get('BILLING_DUNNING_DAYS', '3'))
# Kill-switch global da cobrança de adesão (além do toggle por plano).
BILLING_SETUP_FEE_ENABLED = os.environ.get('BILLING_SETUP_FEE_ENABLED', 'false').lower() == 'true'
# Kill-switch para trial→carência→suspensão (enforce_subscription_lifecycle).
# Permanece OFF até o go-live do billing para que o deploy seja no-op em produção.
BILLING_ENFORCEMENT_ENABLED = os.environ.get('BILLING_ENFORCEMENT_ENABLED', 'false').lower() == 'true'
# Kill-switch para geração automática de fatura PIX (enforce_subscription_lifecycle).
# Permanece OFF até o go-live do billing PIX para que o deploy seja no-op em produção.
BILLING_PIX_ENABLED = os.environ.get('BILLING_PIX_ENABLED', 'false').lower() == 'true'
# Lojas autorizadas a receber o dinheiro do cliente final na conta da PLATAFORMA.
# São as lojas do próprio dono (grandfather). Qualquer outra precisa cadastrar o
# próprio StorePaymentGateway — sem isso o checkout falha de propósito, em vez de
# rotear silenciosamente a receita de terceiro para a conta da plataforma.
# OAuth do Mercado Pago (conta do lojista). Vazio = fluxo desligado; o lojista
# cadastra o gateway colando o access_token. Ver apps/stores/services/mercadopago_oauth.py
MP_OAUTH_CLIENT_ID = os.environ.get('MP_OAUTH_CLIENT_ID', '')
MP_OAUTH_CLIENT_SECRET = os.environ.get('MP_OAUTH_CLIENT_SECRET', '')
MP_OAUTH_REDIRECT_URI = os.environ.get(
    'MP_OAUTH_REDIRECT_URI',
    'https://backend.pastita.com.br/api/v1/stores/payments/gateways/oauth/callback/',
)
PLATFORM_GATEWAY_STORE_SLUGS = [
    s.strip() for s in os.environ.get('PLATFORM_GATEWAY_STORE_SLUGS', '').split(',') if s.strip()
]
# Token de SANDBOX (TEST-...) só para a assinatura SaaS. Se setado, billing usa ele
# em vez do token de produção — permite testar sem cobrar de verdade e sem mexer
# no token dos pedidos. Vazio = usa produção (cobrança real).
MERCADO_PAGO_SANDBOX_TOKEN = os.environ.get('MERCADO_PAGO_SANDBOX_TOKEN', '')
BACKEND_URL = os.environ.get('BACKEND_URL', 'http://localhost:8000')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
ECOMMERCE_DEFAULT_ACCOUNT_ID = os.environ.get('ECOMMERCE_DEFAULT_ACCOUNT_ID', '').strip()

# AWS S3 Storage (optional)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'sa-east-1')

USE_S3 = _env_bool('USE_S3', False) and bool(
    AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME
)
SERVE_MEDIA_FILES = _env_bool('SERVE_MEDIA_FILES', not USE_S3)

MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media')))
MEDIA_URL = os.environ.get('MEDIA_URL', '/media/').strip() or '/media/'
if not MEDIA_URL.endswith('/'):
    MEDIA_URL = f'{MEDIA_URL}/'
os.makedirs(MEDIA_ROOT, exist_ok=True)

if USE_S3:
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_DEFAULT_ACL = None
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            # Use a classe do WhiteNoise que suporta compressão e manifesto
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ESTA LINHA É CRUCIAL: Impede o erro caso o arquivo de manifesto ainda não exista
WHITENOISE_MANIFEST_STRICT = False

# ─────────────────────────────────────────────────────────────────────────────
# Postado — AI social media posts admin
# ─────────────────────────────────────────────────────────────────────────────
POSTADO_ADMIN_TOKEN = os.environ.get('POSTADO_ADMIN_TOKEN', '')

# ─────────────────────────────────────────────────────────────────────────────
# Admin URL — configurável via env var para segurança
# ─────────────────────────────────────────────────────────────────────────────
ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL', 'django-admin') + '/'

# ─────────────────────────────────────────────────────────────────────────────
# Django Unfold — admin UI moderno
# ─────────────────────────────────────────────────────────────────────────────
UNFOLD = {
    "SITE_TITLE": "Cardapidex Admin",
    "SITE_HEADER": "Cardapidex",
    "SITE_URL": "/",
    "SITE_LOGO": lambda request: static("img/cardapidex-logo.svg"),
    "COLORS": {
        "font": {
            "subtle-light": "107 114 128",
            "subtle-dark": "156 163 175",
            "default-light": "75 85 99",
            "default-dark": "209 213 219",
            "important-light": "17 24 39",
            "important-dark": "243 244 246",
        },
        "primary": {
            "50": "236 253 245",
            "100": "209 250 229",
            "200": "167 243 208",
            "300": "110 231 183",
            "400": "52 211 153",
            "500": "16 185 129",
            "600": "5 150 105",
            "700": "4 120 87",
            "800": "6 95 70",
            "900": "4 78 56",
            "950": "2 44 34",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Lojas",
                "separator": True,
                "items": [
                    {
                        "title": "Lojas",
                        "icon": "store",
                        "link": "/django-admin/stores/store/",
                    },
                    {
                        "title": "Equipe",
                        "icon": "group",
                        "link": "/django-admin/stores/storeteammember/",
                    },
                ],
            },
            {
                "title": "Usuários",
                "items": [
                    {
                        "title": "Usuários Django",
                        "icon": "person",
                        "link": "/django-admin/auth/user/",
                    },
                ],
            },
            {
                "title": "Pedidos",
                "items": [
                    {
                        "title": "Todos os Pedidos",
                        "icon": "shopping_bag",
                        "link": "/django-admin/stores/storeorder/",
                    },
                ],
            },
        ],
    },
}
















