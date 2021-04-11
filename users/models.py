from django.contrib.auth.models import AbstractUser
from django.db import models

# class CustomUser(AbstractUser):
#     name = models.CharField(blank=True, max_length=255)

#     def __str__(self):
#         return self.email


class User(AbstractUser):
    COURSES = (
        ("a", "Corso A"),
        ("b", "Corso B"),
        ("c", "Corso C"),
    )
    is_teacher = models.BooleanField(default=False)
    course = models.CharField(max_length=1, blank=True, null=True, choices=COURSES)
