import os

import debug_toolbar
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions
from rest_framework.schemas import get_schema_view

urlpatterns = [
    path(os.environ.get("ADMIN_URL", "admin/"), admin.site.urls),
    path("", include("jsplatform.urls")),
    path("users/", include("users.urls")),
    path("api-auth/", include("rest_framework.urls")),
    path("api/v1/", include("djoser.urls")),
    path("api/v1/", include("djoser.urls.authtoken")),
    # path("__debug__/", include(debug_toolbar.urls)),
    # url(r"^silk/", include("silk.urls", namespace="silk")),
]
