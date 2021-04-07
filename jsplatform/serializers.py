from rest_framework import serializers

from .models import (
    Answer,
    Exam,
    Exercise,
    GivenAnswer,
    MultipleChoiceQuestion,
    Submission,
    TestCase,
)


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = ["id", "name", "begin_timestamp", "end_timestamp"]

    def __init__(self, *args, **kwargs):
        super(ExamSerializer, self).__init__(*args, **kwargs)
        if self.context["request"].user.is_teacher:
            # if requesting user is a teacher, show all exercises and questions for this exam
            self.fields["exercises"] = ExerciseSerializer(many=True, **kwargs)
            self.fields["questions"] = MultipleChoiceQuestionSerializer(
                many=True, **kwargs
            )
        else:
            # if requesting user isn't a teacher, show only the exercise/question that's
            # currently assigned to them
            self.fields["exercise"] = serializers.SerializerMethodField()
            self.fields["submissions"] = serializers.SerializerMethodField()
            self.fields["question"] = serializers.SerializerMethodField()

    def create(self, validated_data):
        questions = validated_data.pop("questions")
        exercises = validated_data.pop("exercises")

        exam = Exam.objects.create(**validated_data)

        # create objects for each question and exercise
        for question in questions:
            q = MultipleChoiceQuestionSerializer(data=question, context=self.context)
            q.is_valid(raise_exception=True)
            q.save(exam=exam)
        for exercise in exercises:
            e = ExerciseSerializer(data=exercise, context=self.context)
            e.is_valid(raise_exception=True)
            e.save(exam=exam)

        return exam

    def update(self, instance, validated_data):
        # get data about exercises and questions
        questions_data = validated_data.pop("questions")
        exercises_data = validated_data.pop("exercises")

        # update Exam instance
        instance = super(ExamSerializer, self).update(instance, validated_data)

        questions = instance.questions.all()
        exercises = instance.exercises.all()

        # update each question
        for question_data in questions_data:
            question, _ = MultipleChoiceQuestion.objects.get_or_create(
                pk=question_data["id"], exam=instance
            )

            save_id = question_data.pop("id")  # get rid of frontend generated id

            serializer = MultipleChoiceQuestionSerializer(
                question, data=question_data, context=self.context
            )
            serializer.is_valid(raise_exception=True)

            # update question
            serializer.update(instance=question, validated_data=question_data)

            # remove question from the list of those still to process
            questions = questions.exclude(pk=save_id)

        # remove any questions for which data wasn't sent (i.e. user deleted them)
        for question in questions:
            question.delete()

        # update each exercise
        for exercise_data in exercises_data:
            exercise, _ = Exercise.objects.get_or_create(
                pk=exercise_data["id"], exam=instance
            )

            save_id = exercise_data.pop("id")  # get rid of frontend generated id

            serializer = ExerciseSerializer(
                exercise, data=exercise_data, context=self.context
            )
            serializer.is_valid(raise_exception=True)

            # update exercise
            serializer.update(instance=exercise, validated_data=exercise_data)

            # remove exercise from the list of those still to process
            exercises = exercises.exclude(pk=save_id)

        # remove any exercises for which data wasn't sent (i.e. user deleted them)
        for exercise in exercises:
            exercise.delete()

        return instance

    def get_exercise(self, obj):
        try:
            return ExerciseSerializer(
                instance=self.context["exercise"],
                context={"request": self.context["request"]},
            ).data
        except Exception:
            return None

    def get_question(self, obj):
        try:
            return MultipleChoiceQuestionSerializer(
                instance=self.context["question"],
                context={"request": self.context["request"]},
            ).data
        except Exception:
            return None

    def get_submissions(self, obj):
        try:
            return SubmissionSerializer(
                instance=self.context["submissions"],
                context={"request": self.context["request"]},
                many=True,
            ).data
        except Exception:
            return None


class TestCaseSerializer(serializers.ModelSerializer):
    """
    A serializer for TestCase model showing its associated assertion and public/secret status
    """

    class Meta:
        model = TestCase
        fields = ["id", "assertion", "is_public"]

    def __init__(self, *args, **kwargs):
        super(TestCaseSerializer, self).__init__(*args, **kwargs)
        self.fields["id"] = serializers.IntegerField(required=False)

    def create(self, validated_data):
        instance = TestCase.objects.create(**validated_data)
        print(instance.pk)
        return instance


class MultipleChoiceQuestionSerializer(serializers.ModelSerializer):
    """
    A serializer for a multiple choice question, showing its text and answers
    """

    class Meta:
        model = MultipleChoiceQuestion
        fields = ["id", "text"]

    def __init__(self, *args, **kwargs):
        super(MultipleChoiceQuestionSerializer, self).__init__(*args, **kwargs)
        self.fields["answers"] = AnswerSerializer(many=True, **kwargs)
        # ! keep an eye on this
        self.fields["id"] = serializers.IntegerField(required=False)

    def create(self, validated_data):
        answers = validated_data.pop("answers")

        question = MultipleChoiceQuestion.objects.create(**validated_data)

        # create objects for each answer
        for answer in answers:
            Answer.objects.create(question=question, **answer)

        return question

    def update(self, instance, validated_data):
        # get data about answers
        answers_data = validated_data.pop("answers")

        # update question instance
        instance = super(MultipleChoiceQuestionSerializer, self).update(
            instance, validated_data
        )

        answers = instance.answers.all()

        # update each answer
        for answer_data in answers_data:
            answer, _ = Answer.objects.get_or_create(
                pk=answer_data["id"], question=instance
            )

            save_id = answer_data.pop("id")  # get rid of frontend generated id

            serializer = AnswerSerializer(
                answer, data=answer_data, context=self.context
            )
            serializer.is_valid(raise_exception=True)
            serializer.update(instance=answer, validated_data=answer_data)

            # remove answer from the list of those still to process
            answers = answers.exclude(pk=save_id)

        # remove any answers for which data wasn't sent (i.e. user deleted them)
        for answer in answers:
            answer.delete()

        return instance


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ["id", "text"]

    def __init__(self, *args, **kwargs):
        super(AnswerSerializer, self).__init__(*args, **kwargs)
        self.fields["id"] = serializers.IntegerField(required=False)
        if self.context["request"].user.is_teacher:
            # only show whether this is the right answer to teachers
            self.fields["is_right_answer"] = serializers.BooleanField()


class ExerciseSerializer(serializers.ModelSerializer):
    """
    A serializer for Exercise model, which can conditionally show either all test cases
    or public test cases only for the exercise
    """

    def __init__(self, *args, **kwargs):
        super(ExerciseSerializer, self).__init__(*args, **kwargs)

        if self.context["request"].user.is_teacher:
            self.fields["testcases"] = TestCaseSerializer(many=True)
            # !
            self.fields["id"] = serializers.IntegerField(required=False)
        else:
            # only show public test cases to non-staff users
            self.fields["public_testcases"] = TestCaseSerializer(
                many=True, read_only=True
            )

    class Meta:
        model = Exercise
        fields = ["id", "text", "starting_code", "min_passing_testcases"]

    def create(self, validated_data):
        testcases = validated_data.pop("testcases")

        exercise = Exercise.objects.create(**validated_data)

        # create TestCase objects for each test case
        for testcase in testcases:
            TestCase.objects.create(exercise=exercise, **testcase)

        return exercise

    def update(self, instance, validated_data):
        # get data about test cases
        testcases_data = validated_data.pop("testcases")

        # update Exercise instance
        instance = super(ExerciseSerializer, self).update(instance, validated_data)

        testcases = instance.testcases.all()

        # update each test case
        for testcase_data in testcases_data:
            testcase, _ = TestCase.objects.get_or_create(
                pk=testcase_data["id"], exercise=instance
            )

            save_id = testcase_data.pop("id")  # get rid of frontend generated id

            serializer = TestCaseSerializer(
                testcase, data=testcase_data, context=self.context
            )
            serializer.is_valid(raise_exception=True)
            serializer.update(instance=testcase, validated_data=testcase_data)

            # remove testcase from the list of those still to process
            testcases = testcases.exclude(pk=save_id)

        # remove any testcases for which data wasn't sent (i.e. user deleted them)
        for testcase in testcases:
            testcase.delete()

        return instance


class GivenAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = GivenAnswer
        fields = ["id", "user", "answer", "timestamp"]
        read_only_fields = ["user", "timestamp"]


class SubmissionSerializer(serializers.ModelSerializer):
    """
    A serializer for Submission model showing the submitted code, the timestamp, and the
    details of the submission regarding the test cases
    """

    def __init__(self, *args, **kwargs):
        super(SubmissionSerializer, self).__init__(*args, **kwargs)

        if self.context["request"].user.is_teacher:
            self.fields["details"] = serializers.JSONField(read_only=True)
        else:
            # only show public test case details to non-staff users
            self.fields["public_details"] = serializers.JSONField(read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "user",
            "code",
            "timestamp",
            "is_eligible",
            "has_been_turned_in",
        ]
        read_only_fields = ["is_eligible", "user", "has_been_turned_in"]

    def create(self, validated_data):
        submission = Submission.objects.create(**validated_data)

        return submission
