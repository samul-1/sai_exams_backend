import json
import subprocess

from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

#!
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

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
    A read-only viewset for listing and retrieving submissions to
    a specific exercise from the requesting user
    """

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

    serializer_class = FullExerciseSerializer
    queryset = Exercise.objects.all()


class PublicExerciseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Used to access a single exercise or a list of exercises in read-only mode,
    and showing only the public test cases
    """

    serializer_class = PublicExerciseSerializer
    queryset = Exercise.objects.all()


# -----------------------------------------------------------
@csrf_exempt  #!
@api_view(["POST"])
def evaluate_program(request):
    # if request.method == "GET":
    program = request.data  # ! handle post data better
    print(program)

    #    program = "function max(a) { return a.map(r=>r.nick!=='aaa' )}"
    #    test_cases = [
    #     {
    #         "input": "[{username: 'john', age: 22, nick: 'aaa'}, {username: 'alice', age: 32, nick: 'bb'}]"
    #     }
    # ]

    test_cases = [{"input": "1%%2"}, {"input": "-1%%0"}, {"input": "22%%2"}]

    res = subprocess.check_output(
        [
            "node",
            "jsplatform/node/runUserProgram.js",
            program,
            json.dumps(test_cases),
        ]
    )
    res = json.loads(res)
    return HttpResponse(res)
