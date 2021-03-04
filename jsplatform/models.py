import json
import os
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import models
from django.db.models import JSONField

from .exceptions import NotEligibleForTurningIn, SubmissionAlreadyTurnedIn
from .utils import run_code_in_vm


class Exercise(models.Model):
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    min_passing_testcases = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.text

    def public_testcases(self):
        """
        Returns all the *public* test cases for this question
        """
        return self.testcases.filter(is_public=True)


class TestCase(models.Model):
    exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="testcases"
    )
    input = models.TextField()
    output = models.TextField()
    is_public = models.BooleanField(default=True)

    objects = models.Manager()

    def __str__(self):
        return str(self.exercise) + " | " + self.input + " -> " + self.output


class Submission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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

    def __str__(self):
        return self.code

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
        testcases_json = [{"id": t.id, "input": t.input} for t in testcases]

        outcome = run_code_in_vm(self.code, testcases_json)

        # compare user's code outputs to expected test case outputs
        passed_testcases = 0

        for testcase in testcases:
            print(testcase)
            testcase_outcome = outcome[str(testcase.pk)]
            if passed := str(testcase_outcome.get("output", "None")) == str(
                testcase.output
            ):
                passed_testcases += 1

            testcase_outcome["passed"] = passed

        self.details = outcome

        # determine if enough test cases were passed and add that info to the JSON details
        self.is_eligible = passed_testcases >= self.exercise.min_passing_testcases
        self.save()

    def turn_in(self):
        if not self.is_eligible:
            raise NotEligibleForTurningIn

        if not self.has_been_turned_in:
            self.has_been_turned_in = True
            self.save()
