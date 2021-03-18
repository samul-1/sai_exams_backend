from django.contrib import admin

from .models import Exam, ExamProgress, Exercise, Submission, TestCase, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    pass


@admin.register(ExamProgress)
class ExamProgressAdmin(admin.ModelAdmin):
    pass


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    pass


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    pass


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    pass
