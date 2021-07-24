import json
import logging
from functools import wraps

from core import constants
from django.db.utils import IntegrityError
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

logger = logging.getLogger(__name__)


class FrontendErrorViewSet(viewsets.ModelViewSet):
    serializer_class = FrontendErrorSerializer
    queryset = FrontendError.objects.all()
    permission_classes = [IsTeacherOrWriteOnly]

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
    permission_classes = [IsAuthenticated, TeachersOnly]
    queryset = (
        Question.objects.all().select_related("category").prefetch_related("answers")
    )


class ExamViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exams

    Only staff members can create, update exams, or access all exams
    Regular users can only view current exam(s), that is those whose begin timestamp is
    in the past and end timestamp is in the future, in read-only
    """

    serializer_class = ExamSerializer
    queryset = (
        Exam.objects.all()
        .select_related("locked_by", "created_by", "closed_by")
        .prefetch_related(
            "questions",
            "exercises",
            "categories",
            "allowed_teachers",
        )
    )
    # only allow teachers to access exams' data
    permission_classes = [IsAuthenticated, TeachersOnly]
    # limit exam access for a user to those created by them or to which they've been granted access
    filter_backends = [filters.ExamCreatorAndAllowed, OrderingFilter]
    ordering = ["pk"]

    def get_queryset(self):
        """
        Restricts the queryset so non-teacher users can only see exams in progress
        """
        queryset = super(ExamViewSet, self).get_queryset()
        if self.request.user.is_anonymous or not self.request.user.is_teacher:
            now = timezone.localtime(timezone.now())
            # filter for exams that are currently in progress
            queryset = queryset.filter(begin_timestamp__lte=now, draft=False)

        return queryset

    def get_student_serializer_context(self, request, item):
        """
        Returns a dictionary to be passed as context to an ExamSerializer
        """
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

        return context

    def update(self, request, pk=None):
        exam = self.get_object()
        if exam.locked_by is not None and request.user != exam.locked_by:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "È in corso una modifica da un altro insegnante."},
            )

        return super(ExamViewSet, self).update(request)

    @action(detail=True, methods=["post"])
    def mock(self, request, **kwargs):
        """
        Returns a mock exam representing a simulation of the requested exam, showing a possible combination of questions
        that could be picked according to the exam settings.
        """
        template_name = constants.PDF_REPORT_TEMPLATE_NAME

        exam = self.get_object()  # get_object_or_404(Exam, pk=kwargs.pop("pk"))
        questions, exercises = exam.get_mock_exam(user=request.user)

        # probably export the logic in this method (and in `all_items`) to a separate module
        mock_pdf = render_to_pdf(
            template_name,
            {
                "exam": {
                    "name": exam.name,
                    "begin_timestamp": exam.begin_timestamp,
                },
                "questions": [q.format_for_pdf() for q in questions],
                "exercises": [e.format_for_pdf() for e in exercises],
            },
        )

        return FileResponse(mock_pdf, as_attachment=True, filename=exam.name)

    @action(detail=True, methods=["post"])
    def all_items(self, request, **kwargs):
        template_name = constants.PDF_REPORT_TEMPLATE_NAME

        exam = self.get_object()
        questions, exercises = exam.get_all_items()

        all_items_pdf = render_to_pdf(
            template_name,
            {
                "exam": {
                    "name": exam.name,
                    "begin_timestamp": exam.begin_timestamp,
                },
                "questions": [q.format_for_pdf() for q in questions],
                "exercises": [e.format_for_pdf() for e in exercises],
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

        # with this query parameter, the specific info for each participant isn't fetched
        # and only general data about the average progress (et similia) is returned
        global_only = "global_only" in request.query_params
        data = exam.get_current_progress(global_data_only=global_only)

        return Response(status=status.HTTP_200_OK, data=data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, ~TeachersOnly],
    )
    def give_answer(self, request, **kwargs):
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))
        user = request.user
        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )

        try:
            exam_progress = ExamProgress.objects.get(user=user, exam=exam)
        except ExamProgress.DoesNotExist:
            return Response(status=status.HTTP_403_FORBIDDEN)

        current_question = exam_progress.current_item

        if not isinstance(current_question, Question):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if current_question.question_type == "o":  # open question
            try:
                text = request.data["text"]
                GivenAnswer.objects.update_or_create(
                    user=user,
                    question=current_question,
                    defaults={"text": text},
                )
            except KeyError:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                answer_id = request.data["answer"]
                answer = Answer.objects.get(pk=answer_id)
            except (KeyError, Answer.DoesNotExist):
                return Response(status=status.HTTP_400_BAD_REQUEST)

            if current_question.accepts_multiple_answers:
                try:
                    GivenAnswer.objects.create(
                        user=user, question=current_question, answer=answer
                    )
                except (InvalidAnswerException, IntegrityError):
                    return Response(status=status.HTTP_400_BAD_REQUEST)
            else:
                try:
                    GivenAnswer.objects.update_or_create(
                        user=user,
                        question=current_question,
                        defaults={"answer": answer},
                    )
                except InvalidAnswerException:
                    return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, ~TeachersOnly],
    )
    def withdraw_answer(self, request, **kwargs):
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))
        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )

        user = request.user

        try:
            exam_progress = ExamProgress.objects.get(user=user, exam=exam)
        except ExamProgress.DoesNotExist:
            return Response(status=status.HTTP_403_FORBIDDEN)

        current_question = exam_progress.current_item

        if not isinstance(current_question, Question):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            answer_id = request.data["answer"]
            answer = Answer.objects.get(pk=answer_id)
        except (KeyError, Answer.DoesNotExist):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not current_question.accepts_multiple_answers:
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            withdrawn_answer = GivenAnswer.objects.get(
                user=user, question=current_question, answer=answer
            )
            withdrawn_answer.delete()
        except GivenAnswer.DoesNotExist:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, ~TeachersOnly],
    )
    def current_item(self, request, **kwargs):
        # get current exam
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))

        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )
        # this is the first entry point that the frontend will call upon a student entering
        # an exam for the first time, so the student's ExamProgress might not exist yet and
        # thus needs to be created
        exam_progress, _ = ExamProgress.objects.get_or_create(
            user=request.user, exam=exam
        )
        if exam_progress.is_done:
            return Response(status=status.HTTP_204_NO_CONTENT)

        item = exam_progress.current_item

        assert item is not None

        context = self.get_student_serializer_context(request, item)

        serializer = ExamSerializer(instance=exam, context=context, **kwargs)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, ~TeachersOnly],
    )
    def next_item(self, request, **kwargs):
        # get current exam
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))

        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )

        exam_progress = get_object_or_404(ExamProgress, exam=exam, user=request.user)
        if exam_progress.is_done:
            return Response(status=status.HTTP_204_NO_CONTENT)

        item = exam_progress.move_cursor_forward()

        assert item is not None

        context = self.get_student_serializer_context(request, item)

        serializer = ExamSerializer(instance=exam, context=context, **kwargs)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, ~TeachersOnly],
    )
    def previous_item(self, request, **kwargs):
        # get current exam
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))

        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )
        if not exam.allow_going_back:
            return Response(status=status.HTTP_403_FORBIDDEN)

        exam_progress = get_object_or_404(ExamProgress, exam=exam, user=request.user)

        if exam_progress.is_done:
            return Response(status=status.HTTP_204_NO_CONTENT)
        item = exam_progress.move_cursor_back()

        assert item is not None

        context = self.get_student_serializer_context(request, item)

        serializer = ExamSerializer(instance=exam, context=context, **kwargs)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, ~TeachersOnly],
    )
    def end_exam(self, request, **kwargs):
        """
        Reached by a student when they are done with their exam
        """
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))

        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )

        exam_progress = get_object_or_404(ExamProgress, exam=exam, user=request.user)
        exam_progress.end_exam()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"])
    def terminate(self, request, **kwargs):
        """
        Used by a teacher to close the exam for everybody
        """
        exam = self.get_object()
        exam.close_exam(closed_by=request.user)

        context = {
            "request": request,
        }
        serializer = ExamSerializer(instance=exam, context=context)
        return Response(status=status.HTTP_200_OK, data=serializer.data)

    @action(detail=True, methods=["post"])
    def zip_archive(self, request, **kwargs):
        # from core.celery import generate_zip_archive

        exam = self.get_object()
        report, created = ExamReport.objects.get_or_create(exam=exam)
        if created or (not report.zip_report_archive and not report.in_progress):
            # report hasn't been generated yet - schedule its creation
            logger.warning("NEW VERSION")
            # generate_zip_archive.delay(
            #     exam_id=exam.pk, user_id=request.user.pk
            # )  # todo make sure the task actually got scheduled
            logger.warning("NOT SCHEDULING A DAMN THING")
            return Response(status=status.HTTP_202_ACCEPTED)

        logger.warning(
            f"IN PROGRESS: {str(report.in_progress)} - ARCHIVE {report.zip_report_archive}"
        )
        if report.in_progress:
            return Response(
                status=status.HTTP_206_PARTIAL_CONTENT,
                data={
                    "processed": report.generated_reports_count,
                    "total": exam.participations.count(),
                },
            )
        else:
            logger.warning(
                "EXAM_REPORT EXISTS AND ISN'T IN PROGRESS, IT ALSO HAS A ZIP FILE"
            )
            filename = report.zip_report_archive.name.split("/")[-1]
            return FileResponse(
                report.zip_report_archive, as_attachment=True, filename=filename
            )

    # todo rename to csv
    @action(detail=True, methods=["post"])
    def report(self, request, **kwargs):
        exam = self.get_object()
        report, _ = ExamReport.objects.get_or_create(exam=exam)
        filename = report.csv_report.name.split("/")[-1]

        return FileResponse(report.csv_report, as_attachment=True, filename=filename)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ExerciseViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing, creating, and editing exercises

    Only staff members can create or update exercises

    Regular users can only view exercises they're currently assigned
    """

    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.all().prefetch_related("testcases")

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
        exams = Exam.objects.filter(begin_timestamp__lte=now, closed=False)

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
        return queryset


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    A viewset for listing, retrieving, and creating submissions to a specific exercise, and
    turning in eligible submissions.

    POST requests are limited to one every 30 seconds.

    Staff members can access submissions by all users to a specific exercise, whereas
    normal users can only access theirs
    """

    serializer_class = SubmissionSerializer
    filter_backends = [filters.TeacherOrOwnedOnly]
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
