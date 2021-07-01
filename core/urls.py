"""core URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os

import debug_toolbar
from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions
from rest_framework.schemas import get_schema_view

urlpatterns = [
    path(os.environ.get("ADMIN_URL", "admin/"), admin.site.urls),
    path("", include("jsplatform.urls")),
    path("users/", include("users.urls")),
    path("api-auth/", include("rest_framework.urls")),
    # path("__debug__/", include(debug_toolbar.urls)),
    path("api/v1/", include("djoser.urls")),
    path("api/v1/", include("djoser.urls.authtoken")),
    path("__debug__/", include(debug_toolbar.urls)),
]
