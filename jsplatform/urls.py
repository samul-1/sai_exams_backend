from core.settings import base as settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from . import views

router = routers.SimpleRouter()
router.register(r"exercises", views.ExerciseViewSet)
router.register(r"exams", views.ExamViewSet)
router.register(r"questions", views.QuestionViewSet)
router.register(r"frontend_errors", views.FrontendErrorViewSet)

exercise_router = routers.NestedSimpleRouter(router, r"exercises", lookup="exercise")

# maps SubmissionViewSet to `exercises/<id>/submissions`
exercise_router.register(
    r"submissions", views.SubmissionViewSet, basename="exercise-submissions"
)

# question_router = routers.NestedSimpleRouter(router, r"questions", lookup="question")
# maps GivenAnswerViewSet to `questions/<id>/given_answers`
# question_router.register(
#     r"given_answers", views.GivenAnswerViewSet, basename="question-given-answers"
# )


urlpatterns = [
    path("", include(router.urls)),
    path("", include(exercise_router.urls)),
    # path("", include(question_router.urls)),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
