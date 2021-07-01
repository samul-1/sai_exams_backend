from .base import *

INTERNAL_IPS = [
    # ...
    "127.0.0.1",
    # ...
]
INSTALLED_APPS = INSTALLED_APPS + [
    "django_extensions",
]
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE
INSTALLED_APPS = [
    "debug_toolbar",
] + INSTALLED_APPS
