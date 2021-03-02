from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class Exercise(models.Model):
    text = models.TextField()
    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text


class TestCase(models.Model):
    exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="testcases"
    )
    input = models.TextField()
    output = models.TextField()
    is_public = models.BooleanField(default=True)

    def __str__(self):
        return str(self.exercise) + " | " + self.input + " -> " + self.output


class Submission(models.Model):
    exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="submissions"
    )
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text
