from django.contrib import admin

from .models import (
    Answer,
    Category,
    Exam,
    ExamProgress,
    ExamReport,
    Exercise,
    GivenAnswer,
    Question,
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


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    pass


class CompletedQuestionsInline(admin.TabularInline):
    model = ExamProgress.completed_questions.through


class CompletedExercisesInline(admin.TabularInline):
    model = ExamProgress.completed_exercises.through


@admin.register(ExamProgress)
class ExamProgressAdmin(admin.ModelAdmin):
    inlines = [CompletedQuestionsInline, CompletedExercisesInline]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    pass


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    pass


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    pass


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    pass


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    pass


@admin.register(GivenAnswer)
class GivenAnswerAdmin(admin.ModelAdmin):
    pass


@admin.register(ExamReport)
class ExamReportAdmin(admin.ModelAdmin):
    pass
