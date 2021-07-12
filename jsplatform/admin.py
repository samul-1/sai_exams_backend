from django.contrib import admin

from .models import (
    Answer,
    Category,
    Exam,
    ExamProgress,
    ExamReport,
    Exercise,
    FrontendError,
    GivenAnswer,
    Question,
    Submission,
    TestCase,
    User,
)


@admin.register(FrontendError)
class FrontendErrorAdmin(admin.ModelAdmin):
    readonly_fields = ("timestamp",)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )


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
    # list_display = ("pdf_report",)
    # list_display_links = ("pdf_report",)
    # list_editable = ("pdf_report",)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    pass


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )


@admin.register(GivenAnswer)
class GivenAnswerAdmin(admin.ModelAdmin):
    pass


@admin.register(ExamReport)
class ExamReportAdmin(admin.ModelAdmin):
    pass
