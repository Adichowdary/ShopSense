"""
Test settings for ShopSense project.
Uses SQLite for fast, isolated test execution.
"""


from .settings import *

# Override database to use SQLite for tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    }
}

# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True
    
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Disable password hashing for faster tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Use fast password validator for tests
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 3,
        }
    },
]

# Disable CSRF for test client
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# Use console email backend for tests
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Disable CSP for tests
CONTENT_SECURITY_POLICY = {'DIRECTIVES': {}}

# Disable axes for tests
AXES_ENABLED = False

# Use faster password hashers
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable caching for tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Media files for tests
MEDIA_ROOT = BASE_DIR / 'test_media'
MEDIA_URL = '/media/'

# Static files for tests
STATIC_ROOT = BASE_DIR / 'test_staticfiles'

# Disable logging during tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

# Disable axes for tests
AXES_ENABLED = False

# Test runner
TEST_RUNNER = 'django.test.runner.DiscoverRunner'