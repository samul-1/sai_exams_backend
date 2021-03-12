from rest_framework import serializers

from .models import Exam, Exercise, Submission, TestCase


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super(ExamSerializer, self).__init__(*args, **kwargs)
        print(self)
        if self.context["request"].user.is_teacher:
            # if requesting user is a teacher, show all exercises for this exam
            self.fields["exercises"] = ExerciseSerializer(many=True, **kwargs)
        else:
            # if requesting user isn't a teacher, show only the exercise that's been assigned to them
            self.fields["exercise"] = serializers.SerializerMethodField()

    def get_exercise(self, obj):
        return ExerciseSerializer(
            instance=self.context["exercise"],
            context={"request": self.context["request"]},
        ).data


class TestCaseSerializer(serializers.ModelSerializer):
    """
    A serializer for TestCase model showing its input, output, and public/secret status
    """

    class Meta:
        model = TestCase
        fields = ["id", "input", "output", "is_public"]

    id = serializers.IntegerField(required=False)


class ExerciseSerializer(serializers.ModelSerializer):
    """
    A serializer for Exercise model, which can conditionally show either all test cases
    or public test cases only for the exercise
    """

    def __init__(self, *args, **kwargs):
        super(ExerciseSerializer, self).__init__(*args, **kwargs)

        if self.context["request"].user.is_teacher:
            self.fields["testcases"] = TestCaseSerializer(many=True)
        else:
            # only show public test cases to non-staff users
            self.fields["public_testcases"] = TestCaseSerializer(
                many=True, read_only=True
            )

    class Meta:
        model = Exercise
        fields = ["id", "text"]

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

        testcases = list(instance.testcases.all())
        # update each test case
        for testcase_data in testcases_data:
            t = testcases.pop(0)
            t.input = testcase_data.get("input", t.input)
            t.output = testcase_data.get("output", t.output)
            t.is_public = testcase_data.get("is_public", t.is_public)
            t.save()

        return instance


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
