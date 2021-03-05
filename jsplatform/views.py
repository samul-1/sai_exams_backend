import json

from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import NotEligibleForTurningIn
from .models import Exercise, Submission, TestCase
from .serializers import ExerciseSerializer, SubmissionSerializer, TestCaseSerializer


class ExerciseViewSet(viewsets.ModelViewSet):
    """
    A staff-only viewset for viewing, creating, and editing exercises
    """

    #! staff permissions
    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.all()


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    A viewset for listing, retrieving, and creating submissions to
    a specific exercise from the requesting user
    """

    # TODO add throttle to limit rate of submission

    serializer_class = SubmissionSerializer

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
            return Response(status=status.HTTP_400_BAD_REQUEST)
        return super(viewsets.ModelViewSet, self).list(request)

    def create(self, request):
        # an exercise id must be specified to create a submission
        exercise_id = self.request.query_params.get("exercise_id", None)
        if exercise_id is None:
            return Response(status=status.HTTP_400_BAD_REQUEST)
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
