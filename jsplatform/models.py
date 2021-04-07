import json
import os
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from users.models import User

from .exceptions import (
    ExamNotOverYet,
    InvalidAnswerException,
    NotEligibleForTurningIn,
    SubmissionAlreadyTurnedIn,
)
from .utils import run_code_in_vm

# class User(AbstractUser):
#     is_teacher = models.BooleanField(default=False)


class Exam(models.Model):
    """
    An exam, represented by a name and a begin/end datetime
    """

    name = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    begin_timestamp = models.DateTimeField()
    end_timestamp = models.DateTimeField()

    def __str__(self):
        return self.name

    def get_item_for(self, user, force_next=False):
        """
        If called for the first time: creates an ExamProgress object for user and returns a random item for them
        If called subsequently and `force_next` IS NOT explicitly set to True, returns the current item for the
        requesting user
        If called with `force_next` explicitly set to True, returns a random item that the user hasn't completed
        yet and updates their ExamProgress object
        If all items of a category (coding exercises or multiple choice questions) have been completed and a new item
        is requested, the next type of items will be set as the current one if there are any left, or the ExamProgress
        will be set as COMPLETED and None will be returned
        """

        # get user's ExamProgress object or create it
        progress, created = ExamProgress.objects.get_or_create(exam=self, user=user)

        item = progress.get_next_item(force_next=(created or force_next))
        return item


class ExamReport(models.Model):
    """
    A report generated at the end of an exam detailing the submissions and answers
    given by the students
    """

    exam = models.OneToOneField(Exam, null=True, on_delete=models.SET_NULL)
    details = models.JSONField(null=True, blank=True)
    generated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL
    )
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        now = timezone.localtime(timezone.now())

        if self.exam.end_timestamp > now:
            # prevent creation of report if exam is still undergoing
            raise ExamNotOverYet

        creating = not self.pk  # see if the objects exists already or is being created
        super(ExamReport, self).save(*args, **kwargs)  # create the object
        if creating:
            # populate report
            self.populate()

    def populate(self):
        """
        Populates the report, adding all the needed details
        """

        # get all users who participated into the exam
        participations = self.exam.participations.all()
        participants = list(map(lambda p: p.user, participations))

        # get all exercises and questions for this exam
        questions = self.exam.questions.all().prefetch_related("given_answers")
        exercises = self.exam.exercises.all().prefetch_related("submissions")

        details = []

        for participant in participants:
            # process each participant

            participant_details = {
                "email": participant.email,
                "submissions": [],  # data about exercise submission
                "answers": [],  # data about question answers
            }

            # get submission data for this participant for each exercise in the exam
            for exercise in exercises:
                exercise_details = {"exercise": exercise.pk}  # exercise.text
                try:
                    submission = exercise.submissions.get(
                        user=participant, has_been_turned_in=True
                    )
                    exercise_details["code"] = submission.code
                    exercise_details[
                        "passed_testcases"
                    ] = submission.get_passed_testcases()
                except Submission.DoesNotExist:  # no submission was turned in
                    exercise_details["code"] = None

                participant_details["submissions"].append(exercise_details)

            # get submission data for this participant for each question in the exam
            for question in questions:
                question_details = {"question": question.pk}  # question.text
                try:
                    given_answer = question.given_answers.get(user=participant)
                    question_details["given_answer"] = (
                        given_answer.answer.pk  # given_answer.answer.text
                        if given_answer.answer is not None
                        else None
                    )
                except GivenAnswer.DoesNotExist:  # no answer was given (not even skip)
                    question_details["given_answer"] = None

                participant_details["answers"].append(question_details)

            details.append(participant_details)

        self.details = details
        self.save()


class MultipleChoiceQuestion(models.Model):
    """
    A multiple choice question shown in exams
    """

    text = models.TextField()
    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="questions"
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.text


class Exercise(models.Model):
    """
    An exercise, with an assignment text. Exercises are generally tied to an exam
    """

    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="exercises"
    )
    text = models.TextField()
    starting_code = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    min_passing_testcases = models.PositiveIntegerField(default=0)
    creator = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="exercises"
    )

    def __str__(self):
        return self.text

    def public_testcases(self):
        """
        Returns all the *public* test cases for this question
        """
        return self.testcases.filter(is_public=True)


class ExamProgress(models.Model):
    """
    Represents the progress of a user during an exam, that is the exercises they've already
    completed and the current one they're doing
    """

    EXAM_ITEMS = (
        ("q", "QUESTIONS"),
        ("e", "EXERCISES"),
        ("c", "ALL COMPLETED"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="exams_progress",
        on_delete=models.CASCADE,
    )
    exam = models.ForeignKey(
        Exam, on_delete=models.CASCADE, related_name="participations"
    )

    # ! make this settable on a per-exam basis instead of hard-coding a default
    # determines what the first type of exam items that should be served is
    initial_item_type = models.CharField(max_length=1, default="q", choices=EXAM_ITEMS)

    # determines whether the user is to be served multiple choice questions or coding exercises,
    # depending on whether they have completed all items of the other category
    currently_serving = models.CharField(max_length=1, default="q", choices=EXAM_ITEMS)

    current_exercise = models.ForeignKey(
        Exercise,
        related_name="current_in_exams",
        null=True,
        default=None,
        blank=True,
        on_delete=models.CASCADE,
    )
    completed_exercises = models.ManyToManyField(
        Exercise,
        related_name="completed_in_exams",
        blank=True,
    )

    current_question = models.ForeignKey(
        MultipleChoiceQuestion,
        related_name="question_current_in_exams",
        null=True,
        default=None,
        blank=True,
        on_delete=models.CASCADE,
    )

    completed_questions = models.ManyToManyField(
        MultipleChoiceQuestion,
        related_name="question_completed_in_exams",
        blank=True,
    )

    def move_to_next_type(self):
        """
        Updates the type of items that are currently being served to this user
        """
        # ! by all means refactor
        if self.currently_serving == "c":
            return

        if self.currently_serving == "q":
            if self.initial_item_type == "q":
                self.currently_serving = "e"
            else:
                self.currently_serving = "c"
        elif self.initial_item_type == "e":
            self.currently_serving = "q"
        else:
            self.currently_serving = "c"
        self.save()

    def get_next_item(self, force_next=False):
        """
        If called with `force_next` set to False, returns the current item of current category
        If `force_next` is True, a new random item of current category is returned if there are any left;
        otherwise, the current category of items is updated to the next one and the function is called
        again to recursively get a new item of the new category and return it
        """
        if self.currently_serving == "c":
            # exam was completed
            return None

        if not force_next:
            # no state update required; just return current item of current category
            return (
                self.current_exercise
                if self.currently_serving == "e"
                else self.current_question
            )

        if self.currently_serving == "e":
            item = self.get_next_exercise()
        if self.currently_serving == "q":
            item = self.get_next_question()

        # all items of the current type have been completed already; move onto the next type
        if item is None:
            self.move_to_next_type()
            item = self.get_next_item(force_next=force_next)

        return item

    def get_next_question(self):
        """
        Sets the current question as completed and returns a random question among the
        remaining ones that the user hasn't completed yet
        """
        if self.current_question is not None:
            # mark current question as completed
            self.completed_questions.add(self.current_question)
            self.current_question = None
            self.save()

        available_questions = self.exam.questions.exclude(
            id__in=self.completed_questions.all()
        )

        if available_questions.count() == 0:
            # user has completed all questions for this exam
            return None

        random_question = available_questions.order_by("?")[0]

        self.current_question = random_question
        self.save()
        return random_question

    def get_next_exercise(self):
        """
        Sets the current exercise as completed and returns a random exercise among the
        remaining ones that the user hasn't completed yet
        """
        if self.current_exercise is not None:
            # mark current exercise as completed
            self.completed_exercises.add(self.current_exercise)
            self.current_exercise = None
            self.save()

        available_exercises = self.exam.exercises.exclude(
            id__in=self.completed_exercises.all()
        )

        if available_exercises.count() == 0:
            # user has completed all exercises for this exam
            return None

        random_exercise = available_exercises.order_by("?")[0]

        self.current_exercise = random_exercise
        self.save()
        return random_exercise


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
        Exercise, on_delete=models.CASCADE, related_name="submissions"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    code = models.TextField()  # user-submitted code

    # JSON dict containing the id, assertion, and status for each test case of corresponding exercise
    details = JSONField(null=True, blank=True)

    # True if enough test cases were passed and the code can be confirmed by user
    # as their final submission
    is_eligible = models.BooleanField(default=False)

    # True if marked by user as their final submission
    has_been_turned_in = models.BooleanField(default=False)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return self.code

    def get_passed_testcases(self):
        return len([t for t in self.details["tests"] if t["passed"]])

    def public_details(self):
        """
        Returns a subset of the details field dict containing information about public tests only,
        and the number of secret tests that failed
        """

        if "tests" not in self.details:
            # this happens if an error occurred during execution of code; in this case, there is no
            # data about the test cases and the details object contains only info about the error
            return self.details

        # filter for public tests only
        public_tests = [t for t in self.details["tests"] if t["is_public"]]

        # count failed secret tests
        failed_secret_tests = len(
            [t for t in self.details["tests"] if not t["is_public"] and not t["passed"]]
        )

        return {
            "tests": public_tests,
            "failed_secret_tests": failed_secret_tests,
        }

    def save(self, *args, **kwargs):
        creating = not self.pk  # see if the objects exists already or is being created
        super(Submission, self).save(*args, **kwargs)  # create the object
        if creating:  # AFTER the object has been created, run code
            # doing things in this order prevent the calls to save() inside eval_submission()
            # from creating and endless loop
            self.eval_submission()

    def eval_submission(self):
        # submission has already been confirmed
        if self.has_been_turned_in:
            raise SubmissionAlreadyTurnedIn

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

    def turn_in(self):
        if (
            not self.is_eligible
            or self.exercise.submissions.filter(
                user=self.user, has_been_turned_in=True
            ).count()
            > 0
        ):
            raise NotEligibleForTurningIn

        self.has_been_turned_in = True
        self.save()

        # mark exercise as completed and update ExamProgress' current exercise to a random new exercise
        self.exercise.exam.get_item_for(self.user, force_next=True)


class Answer(models.Model):
    """
    An answer to a multiple choice question
    """

    question = models.ForeignKey(
        MultipleChoiceQuestion, on_delete=models.CASCADE, related_name="answers"
    )
    text = models.TextField()
    is_right_answer = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    selections = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.text


class GivenAnswer(models.Model):
    """
    An answer to a multiple choice question given by a user during an exam
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(
        MultipleChoiceQuestion, on_delete=models.CASCADE, related_name="given_answers"
    )
    answer = models.ForeignKey(Answer, null=True, blank=True, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.question) + " " + str(self.answer)

    def save(self, *args, **kwargs):
        if self.answer not in self.question.answers.all() and self.answer is not None:
            raise InvalidAnswerException

        creating = not self.pk  # see if the objects exists already or is being created
        super(GivenAnswer, self).save(*args, **kwargs)  # create the object
        if creating:
            if self.answer is not None:
                # increment number of selections for selected answer
                self.answer.selections += 1
                self.answer.save()

            # get next exam item
            self.question.exam.get_item_for(self.user, force_next=True)
