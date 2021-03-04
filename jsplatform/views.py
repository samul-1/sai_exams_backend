import json
import subprocess

from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import NotEligibleForTurningIn
from .models import Exercise, Submission, TestCase
from .serializers import (
    FullExerciseSerializer,
    PublicExerciseSerializer,
    SubmissionSerializer,
    TestCaseSerializer,
)


class StaffSubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A staff-only, read-only viewset for listing and retrieving user submissions
    to a specific exercise
    """

    # ! staff permissions

    def get_queryset(self):
        exercise_id = self.kwargs["exercise_id"]
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        # filter submissions for given exercise
        queryset = Submission.objects.filter(exercise=exercise)

        user_id = self.kwargs.get("user_id")
        if user_id is not None:
            # filter by user if a user id was optionally given
            user = get_object_or_404(User, pk=user_id)
            queryset = queryset.filter(user=user)

        return queryset

    serializer_class = SubmissionSerializer


class UserSubmissionViewSet(viewsets.ModelViewSet):
    """
    A viewset for listing, retrieving, and creating submissions to
    a specific exercise from the requesting user
    """

    # TODO add throttle to limit rate of submission

    serializer_class = SubmissionSerializer

    def get_queryset(self):
        exercise_id = self.kwargs["exercise_id"]
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        # filter submissions for given exercise
        queryset = Submission.objects.filter(exercise=exercise, user=self.request.user)

        user_id = self.kwargs.get("user_id")
        if user_id is not None:
            # filter by user if a user id was optionally given
            user = get_object_or_404(User, pk=user_id)
            queryset = queryset.filter(user=user)

        return queryset

    def perform_create(self, serializer):
        exercise_id = self.kwargs["exercise_id"]
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        serializer.save(exercise=exercise, user=self.request.user)


class FullExerciseViewSet(viewsets.ModelViewSet):
    """
    A staff-only viewset for viewing, creating, and editing exercises
    """

    #! staff permissions
    serializer_class = FullExerciseSerializer
    queryset = Exercise.objects.all()


class PublicExerciseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Used to access a single exercise or a list of exercises in read-only mode,
    and showing only the public test cases
    """

    serializer_class = PublicExerciseSerializer
    queryset = Exercise.objects.all()


class TurnIn(APIView):
    """
    Accessed via POST by a user to turn in an eligible submission they have previously
    created with UserSubmissionViewSet
    """

    def post(self, request, submission_id):
        """
        Calls turn_in() on specified submission
        """
        submission = get_object_or_404(Submission, pk=submission_id)

        try:
            submission.turn_in()
        except NotEligibleForTurningIn:
            return Response(status=403)

        return Response(status=200)
