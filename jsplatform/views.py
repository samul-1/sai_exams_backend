import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import filters, throttles
from .exceptions import NotEligibleForTurningIn
from .models import Exercise, Submission, TestCase, User
from .permissions import IsTeacherOrReadOnly
from .serializers import ExerciseSerializer, SubmissionSerializer, TestCaseSerializer


class ExerciseViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exercises

    Only staff members can create or update exercises
    """

    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.all()
    permission_classes = [IsTeacherOrReadOnly]


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    A viewset for listing, retrieving, and creating submissions to a specific exercise

    Staff members can access submissions by all users to a specific exercise, whereas
    normal users can only access theirs
    """

    serializer_class = SubmissionSerializer
    filter_backends = [filters.TeacherOrOwnedOnly]
    # limit submission rate to 2 per minute tops

    def get_throttles(self):
        if self.request.method.lower() == "post":
            # limit POST request rate
            return [throttles.UserSubmissionThrottle()]

        return super(SubmissionViewSet, self).get_throttles()

    def get_queryset(self):
        queryset = Submission.objects.all()

        exercise_id = self.request.query_params.get("exercise_id", None)
        user_id = self.request.query_params.get("user_id", None)

        # filter submissions for given exercise
        if exercise_id is not None:
            exercise = get_object_or_404(Exercise, pk=exercise_id)
            queryset = Submission.objects.filter(exercise=exercise)

        # filter submissions for given user
        if user_id is not None:
            user = get_object_or_404(User, pk=user_id)
            queryset = Submission.objects.filter(user=user)

        return queryset

    def list(self, request):
        # an exercise id must be specified to retrieve submissions to that exercise
        exercise_id = self.request.query_params.get("exercise_id", None)
        if exercise_id is None:
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data="Exercise id required"
            )
        return super(viewsets.ModelViewSet, self).list(request)

    def create(self, request):
        # an exercise id must be specified to create a submission
        exercise_id = self.request.query_params.get("exercise_id", None)
        if exercise_id is None:
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data="Exercise id required"
            )
        return super(viewsets.ModelViewSet, self).create(request)

    def perform_create(self, serializer):
        exercise_id = self.request.query_params.get("exercise_id", None)

        exercise = get_object_or_404(Exercise, pk=exercise_id)
        serializer.save(exercise=exercise, user=self.request.user)

    @action(detail=True, methods=["post"])
    def turn_in(self, request, pk=None):
        """
        Calls turn_in() on specified submission
        """
        submission = get_object_or_404(Submission, pk=pk)

        try:
            submission.turn_in()
        except NotEligibleForTurningIn:
            return Response(status=status.HTTP_403_FORBIDDEN)

        return Response(status=status.HTTP_200_OK)
