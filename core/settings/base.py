"""
Django settings for core project.

Generated by 'django-admin startproject' using Django 3.1.1.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", None)


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]

AUTH_USER_MODEL = "users.User"

HASHID_FIELD_SALT = os.environ.get("HASHID_SALT")

# make this work in prod.py
DEFAULT_RENDERER_CLASSES = ("rest_framework.renderers.JSONRenderer",)

if DEBUG:
    DEFAULT_RENDERER_CLASSES = DEFAULT_RENDERER_CLASSES + (
        "rest_framework.renderers.BrowsableAPIRenderer",
    )

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "burst": "",
        # empty because the parse_rate() method is overridden in UserSubmissionThrottle to allow
        # 1 request every 30 seconds
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",  # for browsable api
        "oauth2_provider.contrib.rest_framework.OAuth2Authentication",  # django-oauth-toolkit >= 1.0.0
        "rest_framework_social_oauth2.authentication.SocialAuthentication",
    ),
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
    "DEFAULT_RENDERER_CLASSES": DEFAULT_RENDERER_CLASSES,
}

CORS_ORIGIN_ALLOW_ALL = True


CORS_ALLOW_CREDENTIALS = True

# --


# Application definition

INSTALLED_APPS = [
    "jsplatform.apps.JsplatformConfig",
    "rest_framework",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework.authtoken",
    "corsheaders",
    "djoser",
    "users",
    "django.contrib.sites",
    "oauth2_provider",
    "social_django",
    "rest_framework_social_oauth2",
    "channels",
    "django_celery_results",
]

SITE_ID = 1

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.Http4xxErrorLogMiddleware"
    # "django.middleware.common.CommonMiddleware",
]

DJOSER = {
    "SERIALIZERS": {"current_user": "users.serializers.UserSerializer"},
    # "HIDE_USERS": True,
    "PERMISSIONS": {
        "activation": ["users.permissions.Deny"],
        "password_reset": ["users.permissions.Deny"],
        "password_reset_confirm": ["users.permissions.Deny"],
        "set_password": ["users.permissions.Deny"],
        "username_reset": ["users.permissions.Deny"],
        "username_reset_confirm": ["users.permissions.Deny"],
        "set_username": ["users.permissions.Deny"],
        "user_create": ["users.permissions.Deny"],
        "user_delete": ["users.permissions.Deny"],
        # "user": ["users.permissions.ReadOnly"],
        "user_list": ["users.permissions.Deny"],
        "token_create": ["users.permissions.Deny"],
        "token_destroy": ["users.permissions.Deny"],
    },
}

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "social_django.context_processors.backends",
                "social_django.context_processors.login_redirect",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = (
    # Google OAuth2
    "social_core.backends.google.GoogleOAuth2",
    # django-rest-framework-social-oauth2
    "rest_framework_social_oauth2.backends.DjangoOAuth2",
    # Django
    "django.contrib.auth.backends.ModelBackend",
)

SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# SOCIAL_AUTH_GOOGLE_OAUTH2_AUTH_EXTRA_ARGUMENTS = {"hd": "studenti.unipi.it"}
# AUTH_EXTRA_ARGUMENTS = {"hd": "studenti.unipi.it"}

# only allow access to uni emails
SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_DOMAINS = [
    "studenti.unipi.it",
    "phd.unipi.it",
    "unipi.it",
    "gmail.com",
]


SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.environ.get("SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", None)
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.environ.get(
    "SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET", None
)


WSGI_APPLICATION = "core.wsgi.application"

# Channels
ASGI_APPLICATION = "core.asgi.application"

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR + "/db.sqlite3",
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Europe/Rome"

USE_I18N = True

USE_L10N = True

USE_TZ = True

ADMINS = [("Samuele", "s.bonini7@studenti.unipi.it")]
MANAGERS = [("Samuele", "s.bonini7@studenti.unipi.it")]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_ROOT = os.path.join(PROJECT_DIR, "staticfiles")
STATIC_URL = "/static/"

MEDIA_ROOT = os.environ.get("MEDIA_ROOT", os.path.join(PROJECT_DIR, "media"))
MEDIA_URL = os.environ.get("MEDIA_URL", "/media/")


# Celery settings
CELERY_RESULT_BACKEND = "django-db"
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
