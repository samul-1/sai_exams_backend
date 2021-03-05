from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r"submissions", views.SubmissionViewSet, basename="submissions")
router.register(r"exercises", views.ExerciseViewSet)


urlpatterns = [
    path("", include(router.urls)),
]
