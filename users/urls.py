from django.urls import include, path, re_path

from . import views

urlpatterns = [
    re_path(r"^auth/", include("rest_framework_social_oauth2.urls")),
]
