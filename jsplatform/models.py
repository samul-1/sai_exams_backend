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
    InvalidCategoryType,
    NotEligibleForTurningIn,
    OutOfCategories,
    SubmissionAlreadyTurnedIn,
)
from .utils import run_code_in_vm


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


class Category(models.Model):
    EXAM_ITEMS = (
        ("q", "QUESTIONS"),
        ("e", "EXERCISES"),
    )

    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="categories"
    )
    name = models.TextField()
    amount = models.PositiveIntegerField(default=1)
    # determines whether this category is used for JS exercises or questions
    item_type = models.CharField(max_length=1, choices=EXAM_ITEMS)

    # temporarily stores the uuid provided by the frontend for this category to allow
    # for referencing during the creation of categories and questions/exercises all at once
    tmp_uuid = models.UUIDField(verbose_name="frontend_uuid", null=True, blank=True)

    def __str__(self):
        return self.name


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
    headers = models.JSONField(null=True, blank=True)
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
            self.generate_headers()
            self.populate()

    def generate_headers(self):
        """
        Fills in the `headers` field with the appropriate headers for the report
        """
        headers = ["email", "corso"]

        exercise_count = self.exam.exercises.count()
        question_count = self.exam.questions.count()

        for i in range(0, exercise_count):
            headers.append(f"Esercizio { i+1 } testo")
            headers.append(f"Esercizio { i+1 } sottomissione")
            headers.append(f"Esercizio { i+1 } orario consegna")
            headers.append(f"Esercizio { i+1 } testcase superati")
            headers.append(f"Esercizio { i+1 } testcase falliti")

        for i in range(0, question_count):
            headers.append(f"Domanda { i+1 } testo")
            headers.append(f"Domanda { i+1 } risposta data")
            headers.append(f"Domanda { i+1 } orario risposta")
            headers.append(f"Domanda { i+1 } risposta corretta")

        self.headers = headers
        self.save()

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
                "corso": participant.course,
            }

            # get submission data for this participant for each exercise in the exam
            exerciseCount = 1
            for exercise in exercises:
                exercise_details = {f"Esercizio { exerciseCount } testo": exercise.text}
                try:
                    submission = exercise.submissions.get(
                        user=participant, has_been_turned_in=True
                    )
                except Submission.DoesNotExist:  # no submission was turned in
                    submission = Submission()  # dummy submission

                exercise_details[
                    f"Esercizio { exerciseCount } sottomissione"
                ] = submission.code
                exercise_details[f"Esercizio {exerciseCount} orario consegna"] = str(
                    submission.timestamp
                )
                exercise_details[
                    f"Esercizio {exerciseCount} testcase superati"
                ] = submission.get_passed_testcases()
                exercise_details[f"Esercizio {exerciseCount} testcase falliti"] = (
                    exercise.testcases.count() - submission.get_passed_testcases()
                )
                participant_details.update(exercise_details)
                exerciseCount += 1

            # get submission data for this participant for each question in the exam
            questionCount = 0
            for question in questions:
                question_details = {
                    f"Domanda { questionCount } testo": question.text
                }  # question.text
                try:
                    given_answer = question.given_answers.get(user=participant)

                except GivenAnswer.DoesNotExist:  # no answer was given (not even skip)
                    given_answer = GivenAnswer(answer=None)  # dummy answer

                question_details[f"Domanda { questionCount } risposta data"] = (
                    given_answer.answer.text  # given_answer.answer.text
                    if given_answer.answer is not None
                    else None
                )
                question_details[f"Domanda { questionCount } orario risposta"] = str(
                    given_answer.timestamp
                )
                question_details[f"Domanda { questionCount } risposta corretta"] = (
                    given_answer.answer.is_right_answer  # given_answer.answer.text
                    if given_answer.answer is not None
                    else False
                )

                participant_details.update(question_details)
                questionCount += 1

            details.append(participant_details)

        self.details = details
        self.save()


class MultipleChoiceQuestion(models.Model):
    """
    A multiple choice question shown in exams
    """

    text = models.TextField()
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
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        if self.category is not None and self.category.item_type != "q":
            raise InvalidCategoryType
        super(MultipleChoiceQuestion, self).save(*args, **kwargs)


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
    starting_code = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    min_passing_testcases = models.PositiveIntegerField(default=0)
    creator = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="exercises"
    )

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        if self.category is not None and self.category.item_type != "e":
            raise InvalidCategoryType
        super(Exercise, self).save(*args, **kwargs)

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

    # determines which category the exercises/questions that are being served must belong to
    current_category = models.ForeignKey(
        Category, null=True, on_delete=models.SET_NULL, related_name="current_in_exams"
    )
    # holds the counter of exercises/questions that have been served for the current category
    served_for_current_category = models.PositiveIntegerField(default=0)
    # lists the categories for which questions/exercises have been served already
    exhausted_categories = models.ManyToManyField(Category, blank=True)

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

    def move_to_next_category(self):
        """
        Resets the `served_for_current_category` counter, adds current category to list of
        `exhausted_categories`, and randomly picks a new category
        """
        print("RESETTING CATEGORY")
        self.served_for_current_category = 0

        if self.current_category is not None:
            self.exhausted_categories.add(self.current_category)
        self.current_category = None
        self.save()
        print("CATEGORY SUCCESSFULLY RESET")

        remaining_categories = self.exam.categories.filter(
            item_type=self.currently_serving
        ).exclude(id__in=self.exhausted_categories.all())

        if remaining_categories.count() == 0:  # exhausted all categories
            raise OutOfCategories

        random_category = remaining_categories.order_by("?")[0]  # pick a new category

        self.current_category = random_category
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

        item = self._get_item(type=self.currently_serving)

        # all items of the current type have been completed already; move onto the next type
        if item is None:
            self.move_to_next_type()
            return self.get_next_item(force_next=force_next)
        if self.current_category is not None:
            print(
                f"CURRENTLY SERVED {self.served_for_current_category} FOR {self.current_category}: SHOULD SERVE {self.current_category.amount - self.served_for_current_category} MORE"
            )
        return item

    def _get_item(self, type):
        """
        Sets the current item (question or exercise, as per the parameter `type`) as completed
        and returns a random one among the remaining ones that the user hasn't completed yet
        """
        # if this is the first item we're getting or we've gotten as many item for this
        # category as we wanted to, move onto next category
        if (
            self.current_category is None
            or self.served_for_current_category == self.current_category.amount
        ):
            try:
                self.move_to_next_category()
                print("SUCCESSFULLY MOVED TO NEXT CAT")
            except OutOfCategories:  # we exhausted all the categories; there are no more questions to return
                print("OUT OF QUESTION CAT")
                return None

        verbose_type = "question" if type == "q" else "exercise"
        verbose_type_plural = verbose_type + "s"

        current_item_attr = f"current_{verbose_type}"
        completed_items_attr = f"completed_{verbose_type_plural}"
        available_items_attr = f"available_{verbose_type_plural}"

        if getattr(self, current_item_attr) is not None:
            # mark current item as completed
            getattr(self, completed_items_attr).add(getattr(self, current_item_attr))
            # reset current item
            setattr(self, current_item_attr, None)
            self.save()

        # get remaining items of current category
        available_items = (
            getattr(self.exam, verbose_type_plural)
            .filter(category=self.current_category)
            .exclude(id__in=getattr(self, completed_items_attr).all())
        )

        if available_items.count() == 0:
            # user has completed all items of this type
            return None

        random_item = available_items.order_by("?")[0]

        self.served_for_current_category += 1
        setattr(self, current_item_attr, random_item)
        self.save()
        return random_item


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
        if self.details is None:
            return 0
        return len([t for t in self.details["tests"] if t["passed"]])

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
