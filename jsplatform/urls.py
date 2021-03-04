from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()


# used by staff to list and retrieve exercises and their full data,
# including secret test cases
router.register(r"staff/exercises", views.FullExerciseViewSet)

# used by staff to list the submissions made to an exercise,
# optionally filtering by user too
staff_submission_list = views.StaffSubmissionViewSet.as_view(
    {
        "get": "list",
    }
)

# lists the submissions made to an exercise by the requesting user when accessed via GET,
# creates a new submission for that user to the an exercise when POSTed to
user_submissions = views.UserSubmissionViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)

# used to retrieve a single exercise, displaying only its public test cases
public_exercise_details = views.PublicExerciseViewSet.as_view(
    {
        "get": "retrieve",
    }
)


urlpatterns = [
    path("", include(router.urls)),
    path("exercises/<int:pk>/", public_exercise_details, name="exercises"),
    path(
        "submissions/<int:exercise_id>/",
        user_submissions,
        name="user-submissions",
    ),
    path(
        "submissions/turn_in/<int:submission_id>/",
        views.TurnIn.as_view(),
        name="turn-in",
    ),
    path(
        "staff/submissions/<int:exercise_id>/",
        staff_submission_list,
        name="staff-submissions",
    ),
    path(
        "staff/submissions/<int:exercise_id>/<int:user_id>",
        staff_submission_list,
        name="staff-submissions-user-filtered",
    ),
]
