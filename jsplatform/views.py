import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import filters, throttles
from .exceptions import InvalidAnswerException, NotEligibleForTurningIn
from .models import (
    Exam,
    ExamProgress,
    Exercise,
    GivenAnswer,
    MultipleChoiceQuestion,
    Submission,
    TestCase,
    User,
)
from .permissions import IsTeacherOrReadOnly, TeachersOnly
from .serializers import (
    ExamSerializer,
    ExerciseSerializer,
    GivenAnswerSerializer,
    MultipleChoiceQuestionSerializer,
    SubmissionSerializer,
    TestCaseSerializer,
)


class MultipleChoiceQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = MultipleChoiceQuestionSerializer
    queryset = MultipleChoiceQuestion.objects.all()

    def get_queryset(self):
        """
        Restricts the queryset so users can only see their current question
        """
        # ? what if there can be multiple active exams at the same time?
        now = timezone.localtime(timezone.now())
        # get current exam
        exam = get_object_or_404(Exam, begin_timestamp__lte=now, end_timestamp__gt=now)
        progress = ExamProgress.objects.get(exam=exam, user=self.request.user)

        queryset = super(MultipleChoiceQuestionViewSet, self).get_queryset()
        queryset = queryset.filter(pk=progress.current_question.pk)
        return queryset.prefetch_related("answers")


class ExamViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exams

    Only staff members can create, update, or access arbitrary exam entries
    Regular users can only access the current exam, defined as the only exam whose begin date is in the past
    and end date is in the future
    ! this definition might need to change to allow multiple active exams at once
    """

    serializer_class = ExamSerializer
    queryset = Exam.objects.all()
    # only allow teachers to access exams' data
    permission_classes = [TeachersOnly]

    @action(detail=False, methods=["post"], permission_classes=[~TeachersOnly])
    def my_exam(self, request, **kwargs):
        """
        Assigns an exercise from active exam to user if they haven't been assigned one yet;
        returns that exercise

        Only students can access this (access from teachers returns 403)
        """
        now = timezone.localtime(timezone.now())

        # get current exam
        exam = get_object_or_404(Exam, begin_timestamp__lte=now, end_timestamp__gt=now)

        # this will either create a new ExamProgress object and get a random item for
        # the user if this is the first visit, or will return the currently active
        # item (question or coding exercise) if it's not
        item = exam.get_item_for(request.user)  # force_next=True

        # there are no more exercises to show the user; send special http code for frontend to handle this
        if item is None:
            return Response(
                status=status.HTTP_204_NO_CONTENT,
            )

        context = {
            "request": request,
        }

        # determine if the item retrieved is a coding exercise or a multiple choice question
        if isinstance(item, Exercise):
            # retrieve user's submissions to this exercise and send them along
            student_submissions = item.submissions.filter(user=request.user)
            context["submissions"] = student_submissions
            context["exercise"] = item
        else:
            context["question"] = item

        serializer = ExamSerializer(instance=exam, context=context, **kwargs)
        return Response(serializer.data)


class ExerciseViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exercises

    Only staff members can create or update exercises
    """

    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.all()

    # only allow teachers to create or update exercises
    permission_classes = [IsTeacherOrReadOnly]

    # only allow regular users to see the exercise that's been assigned to them
    # ! filter_backends = [filters.TeacherOrAssignedOnly]

    def get_queryset(self):
        queryset = super(ExerciseViewSet, self).get_queryset()
        return queryset.prefetch_related("testcases")


class GivenAnswerViewSet(viewsets.ModelViewSet):
    serializer_class = GivenAnswerSerializer
    queryset = GivenAnswer.objects.all()

    def dispatch(self, request, *args, **kwargs):
        # this method prevents users from accessing `questions/id/given_answers` for questions
        # they don't have permission to see
        parent_view = MultipleChoiceQuestionViewSet.as_view({"get": "retrieve"})
        original_method = request.method

        # get the corresponding Exercise
        request.method = "GET"
        parent_kwargs = {"pk": kwargs["question_pk"]}

        parent_response = parent_view(request, *args, **parent_kwargs)
        if parent_response.exception:
            # user tried accessing a question they didn't have permission to view
            return parent_response

        request.method = original_method
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super(GivenAnswerViewSet, self).get_queryset()

        question_id = self.kwargs["question_pk"]
        user_id = self.request.query_params.get("user_id", None)

        # filter given answers for given question
        if question_id is not None:
            question = get_object_or_404(MultipleChoiceQuestion, pk=question_id)
            queryset = queryset.filter(question=question)

        # filter given answers for given user
        if user_id is not None:
            user = get_object_or_404(User, pk=user_id)
            queryset = queryset.filter(user=user)

        return queryset

    def create(self, request, **kwargs):
        try:
            return super(GivenAnswerViewSet, self).create(request, **kwargs)
        except InvalidAnswerException:
            return Response(status=status.HTTP_403_FORBIDDEN)

    def perform_create(self, serializer):
        question_id = self.kwargs["question_pk"]

        question = get_object_or_404(MultipleChoiceQuestion, pk=question_id)

        serializer.save(question=question, user=self.request.user)


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    A viewset for listing, retrieving, and creating submissions to a specific exercise, and
    turning in eligible submissions.

    POST requests are limited to once every 30 seconds.

    Staff members can access submissions by all users to a specific exercise, whereas
    normal users can only access theirs
    """

    serializer_class = SubmissionSerializer
    # ! filter_backends = [filters.TeacherOrOwnedOnly]
    queryset = Submission.objects.all()

    def dispatch(self, request, *args, **kwargs):
        # this method prevents users from accessing `exercises/id/submissions` for exercises
        # they don't have permission to see
        parent_view = ExerciseViewSet.as_view({"get": "retrieve"})
        original_method = request.method

        # get the corresponding Exercise
        request.method = "GET"
        parent_kwargs = {"pk": kwargs["exercise_pk"]}

        parent_response = parent_view(request, *args, **parent_kwargs)
        if parent_response.exception:
            # user tried accessing an exercise they didn't have permission to view
            return parent_response

        request.method = original_method
        return super().dispatch(request, *args, **kwargs)

    # ! uncomment
    # def get_throttles(self):
    #     if self.request.method.lower() == "post":
    #         # limit POST request rate
    #         return [throttles.UserSubmissionThrottle()]

    #     return super(SubmissionViewSet, self).get_throttles()

    def get_queryset(self):
        queryset = super(SubmissionViewSet, self).get_queryset()

        exercise_id = self.kwargs["exercise_pk"]
        user_id = self.request.query_params.get("user_id", None)

        # filter submissions for given exercise
        if exercise_id is not None:
            exercise = get_object_or_404(Exercise, pk=exercise_id)
            queryset = queryset.filter(exercise=exercise)

        # filter submissions for given user
        if user_id is not None:
            user = get_object_or_404(User, pk=user_id)
            queryset = queryset.filter(user=user)

        return queryset

    def perform_create(self, serializer):
        # exercise_id = self.request.query_params.get("exercise_id", None)
        exercise_id = self.kwargs["exercise_pk"]

        exercise = get_object_or_404(Exercise, pk=exercise_id)

        serializer.save(exercise=exercise, user=self.request.user)

    @action(detail=True, methods=["put"])
    def turn_in(self, request, pk=None, **kwargs):
        """
        Calls turn_in() on specified submission
        """
        submission = get_object_or_404(Submission, pk=pk)

        try:
            submission.turn_in()
        except NotEligibleForTurningIn:
            return Response(status=status.HTTP_403_FORBIDDEN)

        return Response(status=status.HTTP_200_OK)
