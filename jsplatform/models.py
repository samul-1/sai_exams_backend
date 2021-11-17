import json
import logging
import os
import subprocess
import zipfile
from io import BytesIO

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core import constants
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.db.models import Count, Exists, F, JSONField, OuterRef, Q
from django.utils import timezone
from hashid_field import HashidAutoField
from users.models import User

from jsplatform.exceptions import (
    ExamCompletedException,
    NoGoingBackException,
    TooManyAnswers,
)

from .exceptions import (
    ExamNotOverYet,
    InvalidAnswerException,
    InvalidCategoryType,
    NotEligibleForTurningIn,
    OutOfCategories,
    SubmissionAlreadyTurnedIn,
)
from .pdf import preprocess_html_for_pdf, render_to_pdf
from .tex import tex_to_svg
from .utils import run_code_in_vm

logger = logging.getLogger(__name__)


def get_pdf_upload_path(instance, filename):
    return "exam_reports/{0}/{1}".format(instance.exam.pk, filename)


class FrontendError(models.Model):
    """
    Errors occurring on the frontend are logged to the backend using this model
    """

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(auto_now_add=True)
    error_details = models.JSONField(null=True, blank=True)
    component_data = models.JSONField(null=True, blank=True)
    component_name = models.TextField(null=True, blank=True)
    route = models.TextField(null=True, blank=True)
    additional_info = models.TextField(null=True, blank=True)

    def __str__(self):
        username = self.user.full_name if self.user is not None else "Anonymous"
        return f"{username} ({self.timestamp:%Y-%m-%d %H:%M:%S})"


class Exam(models.Model):
    """
    An exam, represented by a name and a begin/end datetime
    """

    id = HashidAutoField(primary_key=True)
    name = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    draft = models.BooleanField(default=True)
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exams_locked_by",
    )
    begin_timestamp = models.DateTimeField()
    end_timestamp = models.DateTimeField()
    closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exams_closed_by",
    )
    randomize_questions = models.BooleanField(default=True)
    randomize_exercises = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="exams_created_by",
    )
    allowed_teachers = models.ManyToManyField(
        User,
        blank=True,
        limit_choices_to={"is_teacher": True},
        related_name="exams_referred_by",
    )
    allow_going_back = models.BooleanField(default=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super(Exam, self).save(*args, **kwargs)

        action = "unlock" if self.locked_by is None else "lock"

        message = {
            "id": self.pk,
            "type": "receive",
            "action": action,
        }

        if self.locked_by is not None:
            message["by"] = self.locked_by.full_name

        # send update to exam list consumer about exam's locked status
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)("exam_list", message)

    def close_exam(self, closed_by):
        now = timezone.localtime(timezone.now())

        self.closed = True
        self.closed_at = now
        self.closed_by = closed_by

        self.save()

    def get_number_of_items_per_exam(self, as_tuple=False):
        """
        Returns the total number of items (questions + JS exercises) that will appear in
        each instance of the exam, regardless of the randomization. This can be calculated
        by adding the `amount` field of all the categories of the exam.

        If `as_tuple` is True, returns a tuple (num_q, num_e) where the first member is the
        number of questions shown to each user during an exam, and the second is the number
        of JS exercises shown to each user during an exam
        """
        num_questions = sum(
            list(self.categories.filter(item_type="q").values_list("amount", flat=True))
        )

        num_exercises = sum(
            list(self.categories.filter(item_type="e").values_list("amount", flat=True))
        )

        if as_tuple:
            return (num_questions, num_exercises)

        return num_questions + num_exercises

    def get_current_progress(self, global_data_only=False):
        """
        Returns a dict detailing the current number of participants to the exam and their
        current progress in terms of how many items they've completed
        """
        # total_items = self.get_number_of_items_per_exam()
        participants = self.participations.all().select_related("user")
        participants_count = participants.count()
        total_items_count = self.get_number_of_items_per_exam()
        progress_sum = 0
        completed_count = 0

        ret = {
            "participants_count": participants_count,
            "participants_progress": [],
            "total_items_count": total_items_count,
        }

        for participant in participants:
            participant_progress = participant.completed_items_count
            progress_sum += participant_progress
            # todo add correct_answers_count (in ExamProgress as a @property and then here)

            if participant_progress == total_items_count:
                completed_count += 1

            if not global_data_only:
                ret["participants_progress"].append(
                    {
                        "id": participant.user.pk,
                        "email": participant.user.email,
                        "full_name": participant.user.full_name,
                        "course": participant.user.course,
                        "progress": participant_progress,
                    }
                )

        ret["average_progress"] = (
            round(progress_sum / float(participants_count), 2)
            if participants_count > 0
            else 0
        )
        ret["completed_count"] = completed_count
        return ret

    def get_mock_exam(self, user):
        """
        Returns a couple <questions, exercises> representing a mock exam
        """
        progress = ExamProgress.objects.create(exam=self, user=user)

        # save the m2m fields as lists as the related object will be deleted
        questions = [
            q
            for q in progress.questions.all()
            .order_by("examprogressquestionsthroughmodel__ordering")
            .filter(examprogressquestionsthroughmodel__exam_progress=progress)
        ]
        exercises = [
            e
            for e in progress.exercises.all()
            .order_by("examprogressexercisesthroughmodel__ordering")
            .filter(examprogressexercisesthroughmodel__exam_progress=progress)
        ]

        progress.delete()
        return (questions, exercises)

    def get_all_items(self):
        questions = []
        exercises = []

        for question in self.questions.order_by("category__pk", "pk"):
            questions.append(question)

        for exercise in self.exercises.order_by("category__pk", "pk"):
            exercises.append(exercise)

        return (questions, exercises)


class Category(models.Model):
    EXAM_ITEMS = (
        ("q", "QUESTIONS"),
        ("e", "EXERCISES"),
    )

    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="categories"
    )
    name = models.TextField()

    # holds the number of questions belonging to this category that appear in each exam
    amount = models.PositiveIntegerField(default=1)

    # determines whether this category is used for JS exercises or questions
    item_type = models.CharField(max_length=1, choices=EXAM_ITEMS)

    # determines whether this category is logically seen as a set of related questions
    # that appear together in an exam
    is_aggregated_question = models.BooleanField(default=False)

    # if the category is an aggregated question, this field holds the introductory text
    # that is shown together with the questions that make up this category
    introduction_text = models.TextField(blank=True, null=True)
    rendered_introduction_text = models.TextField(blank=True, null=True, default="")

    randomize = models.BooleanField(default=True)

    # temporarily stores the uuid provided by the frontend for this category to allow
    # for referencing during the creation of categories and questions/exercises all at once
    tmp_uuid = models.UUIDField(verbose_name="frontend_uuid", null=True, blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["pk"]

    def __str__(self):
        return self.exam.name + " - " + self.name

    def save(self, render_tex=True, *args, **kwargs):
        text_changed = self.pk is None or (
            self.introduction_text != Category.objects.get(pk=self.pk).introduction_text
        )
        super(Category, self).save(*args, **kwargs)
        if render_tex and text_changed:
            self.rendered_introduction_text = tex_to_svg(self.introduction_text)
            self.save(render_tex=False)


class ExamReport(models.Model):
    """
    A report generated at the end of an exam detailing the submissions and answers
    given by the students
    """

    exam = models.OneToOneField(Exam, null=True, on_delete=models.SET_NULL)
    generated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL
    )
    created = models.DateTimeField(auto_now_add=True)
    in_progress = models.BooleanField(default=False)
    generated_reports_count = models.PositiveIntegerField(default=0)

    zip_report_archive = models.FileField(
        upload_to=get_pdf_upload_path, null=True, blank=True
    )

    csv_report = models.FileField(upload_to=get_pdf_upload_path, null=True, blank=True)

    def __str__(self):
        return self.exam.name

    def save(self, *args, **kwargs):
        if not self.exam.closed:
            # prevent creation of report if exam is still undergoing
            raise ExamNotOverYet

        creating = (
            self.pk is None
        )  # see if the objects exists already or is being created
        super(ExamReport, self).save(*args, **kwargs)  # create the object
        if creating:
            self.generate_csv()

    def generate_zip_archive(self):
        # delete the previous zip archive and reset the report count to make
        # this method idempotent (allows easy retrying in celery task)
        if self.zip_report_archive:
            self.zip_report_archive.delete()
        self.generated_reports_count = 0

        self.in_progress = True
        self.save()
        # first generate pdf files for all exam participants
        participations = self.exam.participations.all()
        for participation in participations:
            participation.generate_pdf()
            self.generated_reports_count += 1
            self.save()

        zip_subdir = "reports"
        zip_filename = "%s.zip" % self.exam.name

        # get path of files to zip
        filenames = [f.path for f in map(lambda p: p.pdf_report, participations)]
        # logger.warning(filenames)
        s = BytesIO()
        zf = zipfile.ZipFile(s, "w")

        for fpath in filenames:
            # Calculate path for file in zip
            fdir, fname = os.path.split(fpath)
            zip_path = os.path.join(zip_subdir, fname)

            # Add file, at correct path
            zf.write(fpath, zip_path)

        zf.close()

        in_memory_file = InMemoryUploadedFile(
            s, None, zip_filename, "application/zip", s.__sizeof__(), None
        )
        self.zip_report_archive.save("%s.zip" % self.exam.name, in_memory_file)
        self.in_progress = False
        self.save()
        # for debugging
        return self.zip_report_archive

    def generate_csv(self):
        from .csv import get_csv_from_exam

        self.csv_report.save(
            "%s.csv" % self.exam.name, ContentFile(get_csv_from_exam(self.exam))
        )


class Question(models.Model):
    """
    A question shown in exams
    """

    QUESTION_TYPES = (
        ("o", "OPEN QUESTION"),
        ("m", "MULTIPLE CHOICE QUESTION"),
    )

    text = models.TextField()
    rendered_text = models.TextField(null=True, blank=True, default="")
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="questions"
    )
    question_type = models.CharField(default="m", choices=QUESTION_TYPES, max_length=1)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    accepts_multiple_answers = models.BooleanField(default=False)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.text[:100]

    def save(self, render_tex=True, *args, **kwargs):
        if self.category is not None and (
            self.category.item_type != "q" or self.category.exam != self.exam
        ):
            raise InvalidCategoryType
        text_changed = self.pk is None or (
            self.text != Question.objects.get(pk=self.pk).text
        )

        super(Question, self).save(*args, **kwargs)

        if render_tex and text_changed:
            self.rendered_text = tex_to_svg(self.text)
            self.save(render_tex=False)

    @property
    def num_appearances(self):
        return ExamProgress.objects.filter(questions__in=[self]).count()

    @property
    def introduction_text(self):
        """
        If the question belongs to an "aggregated question" category, returns the introduction text
        of that category
        """
        return self.category.rendered_introduction_text

    def format_for_pdf(self):
        return {
            "text": preprocess_html_for_pdf(self.rendered_text),
            "introduction_text": preprocess_html_for_pdf(self.introduction_text),
            "type": self.question_type,
            "answers": [
                {
                    "text": preprocess_html_for_pdf(a.rendered_text),
                    "is_right_answer": a.is_right_answer,
                }
                for a in self.answers.all()
            ],
        }


class Exercise(models.Model):
    """
    An exercise, with an assignment text. Exercises are generally tied to an exam
    """

    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="exercises"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exercises",
    )
    text = models.TextField()
    rendered_text = models.TextField(null=True, blank=True, default="")
    starting_code = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    min_passing_testcases = models.PositiveIntegerField(default=0)
    creator = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="exercises"
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.text

    def save(self, render_tex=True, *args, **kwargs):
        if self.category is not None and (
            self.category.item_type != "e" or self.category.exam != self.exam
        ):
            raise InvalidCategoryType

        text_changed = self.pk is None or (
            self.text != Exercise.objects.get(pk=self.pk).text
        )

        super(Exercise, self).save(*args, **kwargs)

        if render_tex and text_changed:
            self.rendered_text = tex_to_svg(self.text)
            self.save(render_tex=False)

    def public_testcases(self):
        """
        Returns all the *public* test cases for this question
        """
        return self.testcases.filter(is_public=True)

    @property
    def num_appearances(self):
        return ExamProgress.objects.filter(exercises__in=[self]).count()

    def format_for_pdf(self):
        return {
            "text": preprocess_html_for_pdf(self.rendered_text),
            "starting_code": self.starting_code,
            "testcases": [
                {
                    "assertion": t.assertion,
                    # "is_right_answer": a.is_right_answer,
                }
                for t in self.testcases.all()
            ],
        }


class ExamProgress(models.Model):
    """
    Represents the progress of a user during an exam, that is the exercises they've already
    completed and the current one they're doing
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="exams_progress",
        on_delete=models.CASCADE,
    )
    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="participations"
    )

    pdf_report = models.FileField(upload_to=get_pdf_upload_path, null=True, blank=True)

    questions = models.ManyToManyField(
        Question,
        through="ExamProgressQuestionsThroughModel",
        related_name="question_assigned_in_exams",
        blank=True,
    )

    exercises = models.ManyToManyField(
        Exercise,
        through="ExamProgressExercisesThroughModel",
        related_name="exercise_assigned_in_exams",
        blank=True,
    )

    current_item_cursor = models.PositiveIntegerField(
        default=0
    )  # current item being displayed

    is_done = models.BooleanField(default=False)
    is_initialized = models.BooleanField(default=False)

    begun_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.exam}"

    def save(self, initialize=True, *args, **kwargs):
        creating = self.pk is None
        super(ExamProgress, self).save(*args, **kwargs)
        if creating and initialize:
            self.generate_items()

    @property
    def completed_items_count(self):
        # returns the number of questions assigned to `self` referenced by at least
        # one GivenAnswer from this user (there could be more if the question
        # accepts multiple answers) plus the number of exercises referenced by one
        # turned in submission from this user
        exists_given_answer = GivenAnswer.objects.filter(
            user=self.user, question=OuterRef("pk")
        )
        exists_eligible_submission = Submission.objects.filter(
            user=self.user, is_eligible=True, exercise=OuterRef("pk")
        )
        return (
            self.questions.all()
            .annotate(given_answer_exists=Exists(exists_given_answer))
            .filter(given_answer_exists=True)
            .count()
            + self.exercises.all()
            .annotate(eligible_submission_exists=Exists(exists_eligible_submission))
            .filter(eligible_submission_exists=True)
            .count()
        )

    @property
    def current_item(self):
        try:
            return ExamProgressQuestionsThroughModel.objects.get(
                exam_progress=self, ordering=self.current_item_cursor
            ).question
        except ExamProgressQuestionsThroughModel.DoesNotExist:
            return ExamProgressExercisesThroughModel.objects.get(
                exam_progress=self, ordering=self.current_item_cursor
            ).exercise

    @property
    def is_there_previous(self):
        return self.current_item_cursor > 0

    @property
    def is_there_next(self):
        return self.current_item_cursor < self.exam.get_number_of_items_per_exam() - 1

    def generate_items(self):
        if self.is_initialized:
            return

        question_categories = self.exam.categories.filter(item_type="q")
        if self.exam.randomize_questions:
            question_categories = question_categories.order_by("?")

        item_count = 0

        # for each category, add `category.amount` questions to `self.questions`, incrementing
        # `item_count` at each iteration. follow randomization rules etc.
        for category in question_categories:
            items = category.questions.all()
            if category.randomize:
                items = items.order_by("?")

            items = items[: category.amount]

            for item in items:
                through_row = ExamProgressQuestionsThroughModel(
                    exam_progress=self, question=item, ordering=item_count
                )
                through_row.save()
                item_count += 1

        exercise_categories = self.exam.categories.filter(item_type="e")
        if self.exam.randomize_exercises:
            exercise_categories = exercise_categories.order_by("?")

        # for each category, add `category.amount` exercises to `self.exercises`, incrementing
        # `item_count` at each iteration. follow randomization rules etc.
        for category in exercise_categories:
            items = category.exercises.all()
            if category.randomize:
                items = items.order_by("?")

            items = items[: category.amount]

            for item in items:
                through_row = ExamProgressExercisesThroughModel(
                    exam_progress=self, exercise=item, ordering=item_count
                )
                through_row.save()
                item_count += 1

        self.is_initialized = True
        self.save()

    def end_exam(self):
        if self.is_done:
            return

        now = timezone.localtime(timezone.now())
        self.ended_at = now
        self.is_done = True
        self.save()

    def move_cursor_back(self):
        if not self.exam.allow_going_back:
            raise NoGoingBackException
        if self.is_done:
            raise ExamCompletedException
        if self.is_there_previous:
            self.current_item_cursor -= 1
            self.save()

        return self.current_item

    def move_cursor_forward(self):
        if self.is_done:
            raise ExamCompletedException

        if self.is_there_next:
            self.current_item_cursor += 1
            self.save()

            # update seen_at time for new current item
            try:
                new_current_through_row = ExamProgressQuestionsThroughModel.objects.get(
                    exam_progress=self, ordering=self.current_item_cursor
                )
            except ExamProgressQuestionsThroughModel.DoesNotExist:
                new_current_through_row = ExamProgressExercisesThroughModel.objects.get(
                    exam_progress=self, ordering=self.current_item_cursor
                )
            now = timezone.localtime(timezone.now())
            if new_current_through_row.seen_at is None:
                new_current_through_row.seen_at = now
                new_current_through_row.save()

        return self.current_item

    def get_progress_as_dict(self, for_csv=False, for_pdf=False):
        """
        Returns the user's seen questions/exercises and the given answers and submitted solutions as a dict
        that can be used to generate a pdf (it gets passed as context to the template that is rendered to pdf)
        """
        from .csv import preprocess_html_for_csv

        # for_csv xor for_pdf
        assert (for_csv or for_pdf) and (not for_csv or not for_pdf)

        if for_csv:
            preprocess_fn = preprocess_html_for_csv
        else:
            preprocess_fn = preprocess_html_for_pdf

        ret = {
            "user": self.user,
            "exam": {
                "name": self.exam.name,
                "begin_timestamp": self.exam.begin_timestamp,
            },
            "questions": [],
            "exercises": [],
        }

        exercises = (
            self.exam.exercises.filter(pk__in=self.exercises.all())
            .order_by("examprogressexercisesthroughmodel__ordering")
            .filter(examprogressexercisesthroughmodel__exam_progress=self)
            .prefetch_related("testcases")
        )

        questions = (
            self.exam.questions.filter(pk__in=self.questions.all())
            .order_by("examprogressquestionsthroughmodel__ordering")
            .filter(
                examprogressquestionsthroughmodel__exam_progress=self
            )  # MAJOR BREAKTHROUGH
            .prefetch_related("answers")
            .prefetch_related("given_answers")
        )

        for question in questions:
            given_answers = question.given_answers.filter(user=self.user)
            question_through_row = self.examprogressquestionsthroughmodel_set.get(
                question=question
            )

            q = {
                "id": question.pk,
                "text": preprocess_fn(
                    question.rendered_text if for_pdf else question.text
                ),  # we don't want the TeX as svg in csv
                "type": question.question_type,
                "introduction_text": preprocess_fn(question.introduction_text),
                "seen_at": timezone.localtime(question_through_row.seen_at)
                if question_through_row.ordering > 0
                else timezone.localtime(self.begun_at)
                # "accepts_multiple_answers": question.accepts_multiple_answers,
            }
            if question.question_type == "m":
                q["answers"] = [
                    {
                        "text": preprocess_fn(a.rendered_text if for_pdf else a.text),
                        "is_right_answer": a.is_right_answer,
                        "selected": a.is_selected_by(user=self.user),
                    }
                    for a in question.answers.all()
                ]
            else:  # open question
                q["answer_text"] = (
                    (
                        escape_unsafe_text(given_answers[0].text)
                        if for_pdf
                        else preprocess_fn(given_answers[0].text)
                    )
                    if given_answers.exists()
                    else ""
                )
            ret["questions"].append(q)

        for exercise in exercises:
            submissions = exercise.submissions.filter(user=self.user)
            exercise_through_row = self.examprogressexercisesthroughmodel_set.get(
                exercise=exercise
            )
            e = {
                "id": exercise.pk,
                "text": preprocess_fn(
                    exercise.rendered_text if for_pdf else exercise.text
                ),  # we don't want the TeX as svg in csv
                "starting_code": escape_unsafe_text(exercise.starting_code)
                if for_pdf
                else preprocess_fn(exercise.starting_code)
                if len(exercise.starting_code) > 0
                else None,
                "testcases": [t.assertion for t in exercise.testcases.all()],
                "seen_at": timezone.localtime(exercise_through_row.seen_at)
                if exercise_through_row.ordering > 0
                else timezone.localtime(self.begun_at),
            }

            submissions = sorted(
                list(submissions),
                key=lambda s: (s.get_passed_testcases(), s.timestamp),
                reverse=True,
            )

            try:
                relevant_submission = submissions[0]
                turned_in = True
            except IndexError:  # no submissions for this exercise from this user
                relevant_submission = Submission(code="", exercise=exercise)
                turned_in = False

            e.update(
                {
                    "submission": escape_unsafe_text(relevant_submission.code)
                    if for_pdf
                    else preprocess_fn(relevant_submission.code)
                    if for_pdf
                    else relevant_submission.code,
                    "submitted_at": timezone.localtime(relevant_submission.timestamp)
                    if turned_in
                    else None,
                    "passed_testcases": relevant_submission.get_passed_testcases(),
                    "failed_testcases": relevant_submission.get_failed_testcases(),
                    "submission_details": relevant_submission.details,
                },
            )
            ret["exercises"].append(e)
        return ret

    def generate_pdf(self):
        """
        Generate a pdf file containing the seen questions/exercises from this user and the given answers
        or submitted solutions
        """
        if self.pdf_report:
            self.pdf_report.delete()

        template_name = constants.PDF_REPORT_TEMPLATE_NAME
        # get the pdf file's binary data
        pdf_binary = render_to_pdf(
            template_name, self.get_progress_as_dict(for_pdf=True)
        )

        # save pdf to disk and associate it to student's exam progress
        self.pdf_report.save("%s.pdf" % self.user.full_name, (pdf_binary))


class ExamProgressQuestionsThroughModel(models.Model):
    ordering = models.PositiveIntegerField()
    exam_progress = models.ForeignKey(ExamProgress, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["ordering"]


class ExamProgressExercisesThroughModel(models.Model):
    ordering = models.PositiveIntegerField()
    exam_progress = models.ForeignKey(ExamProgress, on_delete=models.CASCADE)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(null=True, blank=True)
    draft_code = models.TextField(
        blank=True
    )  # contains what's currently in the user code editor

    class Meta:
        ordering = ["ordering"]


class TestCase(models.Model):
    """
    A TestCase for an exercise

    Assertions in test cases are ran against user submitted code to determine if it's correct
    """

    exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="testcases"
    )
    assertion = models.TextField()
    is_public = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.exercise) + " | " + self.assertion


class Submission(models.Model):
    """
    A program that was submitted by a user

    Once created, the code in a submission is ran in node against the exercise test cases
    and the result is saved to a JSONField, determining if the submission passes enough test
    cases to be eligible for turning in
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions"
    )
    exercise = models.ForeignKey(
        Exercise,
        null=True,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    code = models.TextField()  # user-submitted code

    # JSON dict containing the id, assertion, and status for each test case of corresponding exercise
    details = JSONField(null=True, blank=True)

    # True if enough test cases were passed and the code can be confirmed by user
    # as their final submission
    is_eligible = models.BooleanField(default=False)

    # True if marked by user as their final submission
    # TODO remove has_been_turned_in = models.BooleanField(default=False)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return self.user.full_name + " - " + self.code

    def get_passed_testcases(self):
        if self.details is None or "error" in self.details:
            return 0
        return len([t for t in self.details["tests"] if t["passed"]])

    def get_failed_testcases(self):
        ret = self.exercise.testcases.count()
        return ret - self.get_passed_testcases()

    @property
    def public_details(self):
        """
        Returns a subset of the details field dict containing information about public tests only,
        and the number of secret tests that failed
        """

        if "tests" not in self.details:
            # this happens if an error occurred during execution of the user code; in this case, there is no
            # data about the test cases and the details object contains only info about the error
            return self.details

        # filter for public tests only
        public_tests = [t for t in self.details["tests"] if t["is_public"]]

        # count failed secret tests
        # failed_secret_tests = len(
        #     [t for t in self.details["tests"] if not t["is_public"] and not t["passed"]]
        # )

        return {
            "tests": public_tests,
            # "failed_secret_tests": failed_secret_tests,
        }

    def save(self, *args, **kwargs):
        creating = (
            self.pk is None
        )  # see if the objects exists already or is being created
        super(Submission, self).save(*args, **kwargs)  # create the object
        if creating:  # AFTER the object has been created, run code
            # doing things in this order prevent the calls to save() inside eval_submission()
            # from creating and endless loop
            if self.exercise is None:
                raise ValidationError
            self.eval_submission()

    def eval_submission(self):
        # if self.has_been_turned_in:
        #     raise SubmissionAlreadyTurnedIn

        testcases = self.exercise.testcases.all()

        # collect testcases and pass them onto node
        testcases_json = [
            {
                "id": t.id,
                "assertion": t.assertion,
                "is_public": t.is_public,
            }
            for t in testcases
        ]

        outcome = run_code_in_vm(self.code, testcases_json)

        passed_testcases = 0
        # count passed tests
        if "error" not in outcome.keys():
            for testcase in outcome["tests"]:
                if testcase["passed"]:
                    passed_testcases += 1

        # save details object to Submission instance
        self.details = outcome

        # determine if the submission is eligible for turning in based on how many tests it passed
        self.is_eligible = passed_testcases >= self.exercise.min_passing_testcases
        self.save()

    # TODO remove
    # def turn_in(self):
    #     if (
    #         not self.is_eligible
    #         or self.exercise.submissions.filter(
    #             user=self.user, has_been_turned_in=True
    #         ).exists()
    #     ):
    #         raise NotEligibleForTurningIn

    #     if self.user.is_teacher:
    #         # fake turning in the submission for teachers using student mode
    #         return

    #     self.has_been_turned_in = True
    #     self.save()


class Answer(models.Model):
    """
    An answer to a multiple choice question
    """

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="answers"
    )
    text = models.TextField()
    rendered_text = models.TextField(null=True, blank=True, default="")
    is_right_answer = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    # selections = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.text

    def save(self, render_tex=True, *args, **kwargs):
        text_changed = self.pk is None or (
            self.text != Answer.objects.get(pk=self.pk).text
        )
        super(Answer, self).save(*args, **kwargs)
        if render_tex and text_changed:
            self.rendered_text = tex_to_svg(self.text)
            self.save(render_tex=False)

    @property
    def selections(self):
        return GivenAnswer.objects.filter(answer=self).count()

    def is_selected_by(self, user):
        return GivenAnswer.objects.filter(user=user, answer=self).exists()


class GivenAnswer(models.Model):
    """
    An answer to a question given by a user during an exam
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="given_answers"
    )

    # used if the referenced question is a multiple-choice one
    answer = models.ForeignKey(
        Answer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    # used if the referenced question is an open-ended one
    text = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # we can't enforce uniqueness of the couple <user, question_id> at db level, because
            # some questions accept multiple answers - we can however make sure, that the
            # same *answer* doesn't somehow end up being given multiple times by the same user
            models.UniqueConstraint(
                fields=["user", "answer_id"], name="same_user_same_answer_unique"
            )
        ]

    def __str__(self):
        return self.user.full_name + " - " + str(self.question) + " " + str(self.answer)

    def save(self, *args, **kwargs):
        if self.answer is not None and self.answer not in self.question.answers.all():
            raise InvalidAnswerException

        if (  # maybe could achieve this with a partial unique constraint with condition on self.question
            self.pk is None  # trying to create a new object
            and not self.question.accepts_multiple_answers
            and GivenAnswer.objects.filter(
                question=self.question, user=self.user
            ).exists()
        ):
            raise TooManyAnswers

        super(GivenAnswer, self).save(*args, **kwargs)


"""
To automatically remove files in model's FileField upon deletion
"""

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from jsplatform.pdf import escape_unsafe_text

""" Whenever ANY model is deleted, if it has a file field on it, delete the associated file too"""


@receiver(post_delete)
def delete_files_when_row_deleted_from_db(sender, instance, **kwargs):
    for field in sender._meta.concrete_fields:
        if isinstance(field, models.FileField):
            instance_file_field = getattr(instance, field.name)
            delete_file_if_unused(sender, instance, field, instance_file_field)


""" Only delete the file if no other instances of that model are using it"""


def delete_file_if_unused(model, instance, field, instance_file_field):
    dynamic_field = {}
    dynamic_field[field.name] = instance_file_field.name
    other_refs_exist = (
        model.objects.filter(**dynamic_field).exclude(pk=instance.pk).exists()
    )
    if not other_refs_exist:
        instance_file_field.delete(False)
