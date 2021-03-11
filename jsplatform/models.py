import json
import os
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import JSONField

from .exceptions import NotEligibleForTurningIn, SubmissionAlreadyTurnedIn
from .utils import run_code_in_vm


class User(AbstractUser):
    is_teacher = models.BooleanField(default=False)


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


class Exercise(models.Model):
    """
    An exercise, with an assignment text. Exercises are generally tied to an exam
    """

    exam = models.ForeignKey(
        Exam, null=True, on_delete=models.SET_NULL, related_name="exercises"
    )
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    min_passing_testcases = models.PositiveIntegerField(default=0)
    creator = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="exercises"
    )
    assigned_users = models.ManyToManyField(
        User, blank=True, related_name="assigned_exercises"
    )

    def __str__(self):
        return self.text

    def public_testcases(self):
        """
        Returns all the *public* test cases for this question
        """
        return self.testcases.filter(is_public=True)


class TestCase(models.Model):
    """
    A TestCase for an exercise

    User-submitted code is ran using inputs from test cases and its output is compared against
    the test cases'
    """

    exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="testcases"
    )
    input = models.TextField()
    output = models.TextField()
    is_public = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = models.Manager()  # ?

    def __str__(self):
        return str(self.exercise) + " | " + self.input + " -> " + self.output


class Submission(models.Model):
    """
    A program that was submitted by a user

    Once created, the code in a submission is ran in node against the exercise test cases
    and the output is saved to a JSONField, determining if the submission passes enough test
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

    # JSON dict containing the id, input, and given output for each test case of the exercise
    details = JSONField(null=True, blank=True)

    # True if enough test cases were passed and the code can be confirmed by user
    # as their final submission
    is_eligible = models.BooleanField(default=False)

    # True if marked by user as their final submission
    has_been_turned_in = models.BooleanField(default=False)

    # TODO add constraint to make sure there isn't more than one turned in submission per exercise per user

    def __str__(self):
        return self.code

    def public_details(self):
        """
        Returns a subset of the details field dict containing information about public tests only,
        and the number of secret tests that were failed
        """

        # filter for public tests only
        dict = {
            id: details for id, details in self.details.items() if details["is_public"]
        }

        failed_secret_tests = len(
            {
                id: details
                for id, details in self.details.items()
                if not details["is_public"] and not details["passed"]
            }.keys()
        )

        dict["failed_secret_tests"] = failed_secret_tests

        return dict

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

        # collect id and input from test cases to pass them onto node
        testcases_json = [
            {
                "id": t.id,
                "input": t.input,
            }
            for t in testcases
        ]

        outcome = run_code_in_vm(self.code, testcases_json)

        # compare user's code outputs to expected test case outputs
        passed_testcases = 0

        for testcase in testcases:
            testcase_outcome = outcome[str(testcase.pk)]
            testcase_outcome["is_public"] = testcase.is_public
            if passed := str(testcase_outcome.get("output", "None")) == str(
                testcase.output
            ):
                passed_testcases += 1

            testcase_outcome["passed"] = passed

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
