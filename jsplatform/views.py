import json

from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from . import filters, throttles
from .exceptions import InvalidAnswerException, NotEligibleForTurningIn
from .models import (
    Answer,
    Exam,
    ExamProgress,
    ExamReport,
    Exercise,
    FrontendError,
    GivenAnswer,
    Question,
    Submission,
    TestCase,
    User,
)
from .pdf import render_to_pdf
from .permissions import IsTeacherOrReadOnly, IsTeacherOrWriteOnly, TeachersOnly
from .renderers import ReportRenderer
from .serializers import (
    ExamSerializer,
    ExerciseSerializer,
    FrontendErrorSerializer,
    GivenAnswerSerializer,
    QuestionSerializer,
    SubmissionSerializer,
    TestCaseSerializer,
)


class FrontendErrorViewSet(viewsets.ModelViewSet):
    serializer_class = FrontendErrorSerializer
    queryset = FrontendError.objects.all()
    permission_classes = [IsTeacherOrWriteOnly]
    # todo add permissions to prevent users from accessing the errors

    def perform_create(self, serializer):
        if not self.request.user.is_anonymous:
            serializer.save(user=self.request.user)
        else:
            serializer.save()


class QuestionViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing multiple choice questions

    Only staff members can create or update multiple choice questions

    Regular users can only view questions they're currently assigned
    """

    serializer_class = QuestionSerializer
    queryset = Question.objects.all()

    def get_queryset(self):
        """
        Restricts the queryset so users can only see their current question
        """
        if self.request.user.is_teacher:
            return super(QuestionViewSet, self).get_queryset()

        now = timezone.localtime(timezone.now())

        # get exams that are currently in progress
        exams = Exam.objects.filter(begin_timestamp__lte=now, end_timestamp__gt=now)

        # get ExamProgress objects for this user for each exam
        progress_objects = ExamProgress.objects.filter(
            exam__in=exams, user=self.request.user, current_question__isnull=False
        )

        # get default queryset
        queryset = super(QuestionViewSet, self).get_queryset()

        # get questions that appear as `current_question` in one of the ExamProgress object
        queryset = queryset.filter(
            pk__in=list(map(lambda p: p.current_question.pk, progress_objects))
        )
        return queryset.prefetch_related("answers")


class ExamViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exams

    Only staff members can create, update exams, or access all exams
    Regular users can only view current exam(s), that is those whose begin timestamp is
    in the past and end timestamp is in the future, in read-only
    """

    serializer_class = ExamSerializer
    queryset = Exam.objects.all()
    # only allow teachers to access exams' data
    permission_classes = [TeachersOnly]
    # limit exam access for a user to those created by them or to which they've been granted access
    filter_backends = [filters.ExamCreatorAndAllowed, OrderingFilter]
    renderer_classes = (ReportRenderer,) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
    ordering = ["pk"]

    def update(self, request, pk=None):
        exam = self.get_object()
        if exam.locked_by is not None and request.user != exam.locked_by:
            return Response(status=status.HTTP_403_FORBIDDEN)

        return super(ExamViewSet, self).update(request)

    @action(detail=True, methods=["post"])
    def mock(self, request, **kwargs):
        """
        Returns a mock exam representing a simulation of the requested exam, showing a possible combination of questions
        that could be picked according to the exam settings.
        """
        # todo make a constants.py file for stuff like this
        template_name = "exam_pdf_report.html"

        exam = self.get_object()  # get_object_or_404(Exam, pk=kwargs.pop("pk"))
        questions, exercises = exam.get_mock_exam(user=request.user)

        mock_pdf = render_to_pdf(
            template_name,
            {
                "exam": {
                    "name": exam.name,
                    "begin_timestamp": exam.begin_timestamp,
                },
                "questions": questions,
                "exercises": exercises,
            },
        )

        return FileResponse(mock_pdf, as_attachment=True, filename=exam.name)

    @action(detail=True, methods=["post"])
    def all_items(self, request, **kwargs):
        # todo make a constants.py file for stuff like this
        template_name = "exam_pdf_report.html"

        exam = self.get_object()
        questions, exercises = exam.get_all_items()

        all_items_pdf = render_to_pdf(
            template_name,
            {
                "exam": {
                    "name": exam.name,
                    "begin_timestamp": exam.begin_timestamp,
                },
                "questions": questions,
                "exercises": exercises,
            },
        )

        return FileResponse(all_items_pdf, as_attachment=True, filename=exam.name)

    @action(detail=True, methods=["get"])
    def progress_info(self, request, **kwargs):
        """
        Returns a response detailing the info regarding the students' progress
        (to be used while the exam is still open)
        """

        exam = self.get_object()
        data = exam.get_current_progress()

        return Response(data)

    @action(detail=True, methods=["post"], permission_classes=[~TeachersOnly])
    def my_exam(self, request, **kwargs):
        """
        Assigns an exercise from active exam to user if they haven't been assigned one yet;
        returns that exercise

        Only students can access this (access from teachers returns 403)
        """
        now = timezone.localtime(timezone.now())

        # get current exam
        exam = get_object_or_404(Exam, pk=kwargs.pop("pk"))

        if exam.begin_timestamp > now:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"message": "L'esame non è  ancora iniziato"},
            )

        if exam.closed:  # exam.end_timestamp <= now:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"message": "L'esame è terminato"},
            )
        # this will either create a new ExamProgress object and get a random item for
        # the user if this is the first visit, or will return the currently active
        # item (question or coding exercise) if it's not
        item = exam.get_item_for(request.user, force_next=False)  # force_next=True

        # there are no more exercises to show the user; send special http code for frontend to handle this
        if item is None:
            return Response(
                status=status.HTTP_204_NO_CONTENT,
            )

        context = {
            "request": request,
        }

        # determine if the item retrieved is a programming exercise or a question
        if isinstance(item, Exercise):
            # retrieve user's submissions to this exercise and send them along
            student_submissions = item.submissions.filter(user=request.user)
            context["submissions"] = student_submissions
            context["exercise"] = item
        else:
            context["question"] = item

        serializer = ExamSerializer(instance=exam, context=context, **kwargs)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"])
    def terminate(self, request, **kwargs):
        now = timezone.localtime(timezone.now())

        exam = self.get_object()
        exam.closed = True
        exam.closed_at = now
        exam.closed_by = request.user

        exam.save()

        context = {
            "request": request,
        }
        serializer = ExamSerializer(instance=exam, context=context)
        return Response(status=status.HTTP_200_OK, data=serializer.data)

    @action(detail=True, methods=["post"])
    def zip_archive(self, request, **kwargs):
        exam = self.get_object()
        report, _ = ExamReport.objects.get_or_create(exam=exam)
        if not report.zip_report_archive:
            report.generate_zip_archive()
        filename = report.zip_report_archive.name.split("/")[-1]
        return FileResponse(
            report.zip_report_archive, as_attachment=True, filename=filename
        )

    @action(detail=True, methods=["post"])
    def report(self, request, **kwargs):
        exam = self.get_object()
        report, _ = ExamReport.objects.get_or_create(exam=exam)
        return Response(report.details)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_renderer_context(self):
        context = super().get_renderer_context()
        try:
            header = context["view"].get_object().examreport.headers
        except Exception:  #!
            header = None
        context["header"] = header
        return context


class ExerciseViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exercises

    Only staff members can create or update exercises

    Regular users can only view exercises they're currently assigned
    """

    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.all()

    # only allow teachers to create or update exercises
    permission_classes = [IsTeacherOrReadOnly]

    # only allow regular users to see the exercise that's been assigned to them
    # ! filter_backends = [filters.TeacherOrAssignedOnly]

    def get_queryset(self):
        """
        Restricts the queryset so users can only see their current exercise
        """
        if self.request.user.is_teacher:
            return super(ExerciseViewSet, self).get_queryset()

        now = timezone.localtime(timezone.now())

        # get exams that are currently in progress
        exams = Exam.objects.filter(begin_timestamp__lte=now, end_timestamp__gt=now)

        # get ExamProgress objects for this user for each exam
        progress_objects = ExamProgress.objects.filter(
            exam__in=exams, user=self.request.user, current_exercise__isnull=False
        )

        # get default queryset
        queryset = super(ExerciseViewSet, self).get_queryset()

        # get questions that appear as `current_question` in one of the ExamProgress object
        queryset = queryset.filter(
            pk__in=list(map(lambda p: p.current_exercise.pk, progress_objects))
        )
        return queryset.prefetch_related("testcases")


class GivenAnswerViewSet(viewsets.ModelViewSet):
    serializer_class = GivenAnswerSerializer
    queryset = GivenAnswer.objects.all()
    # ! add filter to prevent accessing other people's answers

    # def dispatch(self, request, *args, **kwargs):
    #     # this method prevents users from accessing `questions/id/given_answers` for questions
    #     # they don't have permission to see
    #     parent_view = QuestionViewSet.as_view({"get": "retrieve"})
    #     original_method = request.method

    #     # get the corresponding question
    #     request.method = "GET"
    #     parent_kwargs = {"pk": kwargs["question_pk"]}

    #     parent_response = parent_view(request, *args, **parent_kwargs)
    #     if parent_response.exception:
    #         # user tried accessing a question they didn't have permission to view
    #         return parent_response

    #    request.method = original_method
    #    return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super(GivenAnswerViewSet, self).get_queryset()

        question_id = self.kwargs["question_pk"]
        user_id = self.request.query_params.get("user_id", None)

        # filter given answers for given question
        if question_id is not None:
            question = get_object_or_404(Question, pk=question_id)
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

        question = get_object_or_404(Question, pk=question_id)

        serializer.save(question=question, user=self.request.user)

    @action(detail=False, methods=["post"])
    def multiple(self, request, pk=None, **kwargs):
        """
        Creates multiple answers to a question
        """
        question_id = self.kwargs["question_pk"]
        question = get_object_or_404(Question, pk=question_id)

        answer_pks = request.data["answer"]
        if len(answer_pks) == 0:
            given_answer = GivenAnswer(
                user=request.user, question=question, answer=None
            )
            given_answer.save(get_next_item=False)
        # todo transaction
        for answer_pk in answer_pks:
            answer = get_object_or_404(Answer, pk=answer_pk)
            given_answer = GivenAnswer(
                user=request.user, question=question, answer=answer
            )
            given_answer.save(get_next_item=False)

        # move onto next item
        question.exam.get_item_for(request.user, force_next=True)

        return Response(status=status.HTTP_200_OK)


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    A viewset for listing, retrieving, and creating submissions to a specific exercise, and
    turning in eligible submissions.

    POST requests are limited to one every 30 seconds.

    Staff members can access submissions by all users to a specific exercise, whereas
    normal users can only access theirs
    """

    serializer_class = SubmissionSerializer
    # ! filter_backends = [filters.TeacherOrOwnedOnly]
    queryset = Submission.objects.all()

    #! investigate, this is causing 403
    # def dispatch(self, request, *args, **kwargs):
    #     # this method prevents users from accessing `exercises/id/submissions` for exercises
    #     # they don't have permission to see
    #     parent_view = ExerciseViewSet.as_view({"get": "retrieve"})
    #     original_method = request.method
    #     # get the corresponding Exercise
    #     request.method = "GET"
    #     parent_kwargs = {"pk": kwargs["exercise_pk"]}

    #     parent_response = parent_view(request, *args, **parent_kwargs)
    #     if parent_response.exception:
    #         # user tried accessing an exercise they didn't have permission to view
    #         return parent_response
    #     request.method = original_method
    #     return super().dispatch(request, *args, **kwargs)

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
