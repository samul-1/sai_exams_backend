from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.UserListView.as_view()),
    path("login/", views.google_login, name="google_login"),
]
