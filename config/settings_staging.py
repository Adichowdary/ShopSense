"""
Staging PostgreSQL settings for ShopSense project.
Connects to an isolated staging PostgreSQL environment on port 5433.
Never touches or modifies the Supabase production database.
"""
from .settings import *

# Explicitly configure staging PostgreSQL database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'shopsense_staging',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': '127.0.0.1',
        'PORT': 5433,
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Ensure standard migrations are enabled so all 38 migrations run against PostgreSQL
MIGRATION_MODULES = {}

# Staging security & test flags
SHOPSENSE_DEMO_DATABASE_APPROVED = True

# Cache configuration for staging
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'shopsense-staging-cache',
    }
}

# Email backend for staging
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

