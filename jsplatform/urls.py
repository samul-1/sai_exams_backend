from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from . import views

router = routers.SimpleRouter()
router.register(r"exercises", views.ExerciseViewSet)
router.register(r"exams", views.ExamViewSet)

exercise_router = routers.NestedSimpleRouter(router, r"exercises", lookup="exercise")

# maps SubmissionViewSet to `exercises/<id>/submissions`
exercise_router.register(
    r"submissions", views.SubmissionViewSet, basename="exercise-submissions"
)


urlpatterns = [
    path("", include(router.urls)),
    path("", include(exercise_router.urls)),
]
