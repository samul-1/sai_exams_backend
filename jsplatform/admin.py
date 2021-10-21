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


class ExamProgressQuestionsInline(admin.TabularInline):
    model = ExamProgress.questions.through


class ExamProgressExercisesInline(admin.TabularInline):
    model = ExamProgress.exercises.through


@admin.register(ExamProgress)
class ExamProgressAdmin(admin.ModelAdmin):
    pass
    inlines = [ExamProgressQuestionsInline, ExamProgressExercisesInline]
    # list_display = ("pdf_report",)
    # list_display_links = ("pdf_report",)
    # list_editable = ("pdf_report",)


class TestCaseInline(admin.TabularInline):
    model = TestCase


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )
    inlines = [TestCaseInline]


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    pass


class AnswerInline(admin.TabularInline):
    model = Answer
    exclude = ["rendered_text"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    readonly_fields = (
        "created",
        "updated",
    )
    inlines = [AnswerInline]


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
