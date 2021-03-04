from rest_framework import serializers

from .models import Exercise, Submission, TestCase


class TestCaseSerializer(serializers.ModelSerializer):
    """
    A serializer for TestCase model showing its input, output, and public/secret status
    """

    class Meta:
        model = TestCase
        fields = ["id", "input", "output", "is_public"]

    id = serializers.IntegerField(required=False)


class PublicExerciseSerializer(serializers.ModelSerializer):
    """
    A serializer for Exercise model showing only the public test cases
    """

    public_testcases = TestCaseSerializer(many=True)

    class Meta:
        model = Exercise
        fields = ["id", "text", "public_testcases"]


class FullExerciseSerializer(serializers.ModelSerializer):
    """
    A serializer for Exercise model showing both public and secret test cases
    """

    testcases = TestCaseSerializer(many=True)

    class Meta:
        model = Exercise
        fields = ["text", "testcases"]

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
        instance = super(FullExerciseSerializer, self).update(instance, validated_data)

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
    outcome of the submission regarding the test cases
    """

    class Meta:
        model = Submission
        fields = [
            "id",
            "code",
            "timestamp",
            "details",
            "is_eligible",
            "has_been_turned_in",
        ]
        read_only_fields = ["details", "is_eligible", "has_been_turned_in"]

    def create(self, validated_data):
        submission = Submission.objects.create(**validated_data)

        return submission
