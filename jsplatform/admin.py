from django.contrib import admin

from .models import (
    Answer,
    Exam,
    ExamProgress,
    Exercise,
    GivenAnswer,
    MultipleChoiceQuestion,
    Submission,
    TestCase,
    User,
)


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


@admin.register(MultipleChoiceQuestion)
class MultipleChoiceQuestionAdmin(admin.ModelAdmin):
    pass


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    pass


@admin.register(GivenAnswer)
class GivenAnswerAdmin(admin.ModelAdmin):
    pass
