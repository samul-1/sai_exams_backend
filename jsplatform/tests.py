import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from jsplatform.models import Exercise, Submission
from jsplatform.models import (
    TestCase as TestCase_,
)  # prevent name conflict with django TestCase class
from jsplatform.models import User
from jsplatform.views import ExerciseViewSet, SubmissionViewSet


class ExerciseViewSetTestCase(TestCase):
    def setUp(self):
        User.objects.create(username="teacher", is_teacher=True)
        User.objects.create(username="student", is_teacher=False)

    def get_post_request(self):
        """
        Returns a sample POST request for creating an exercise, used in other test cases
        """
        factory = APIRequestFactory()
        return factory.post(
            "/exercises/",
            {
                "text": "Scrivere una funzione che, presi in input due numeri, restituisca il massimo tra i due.",
                "min_passing_testcases": 2,
                "testcases": [
                    {"input": "1%%2", "output": "2", "is_public": True},
                    {"input": "-1%%0", "output": "0", "is_public": False},
                ],
            },
            format="json",
        )

    def test_create_exercise(self):
        """
        Shows that teachers, and only teachers, are able to create new exercises
        """
        teacher = User.objects.get(username="teacher")
        student = User.objects.get(username="student")

        request = self.get_post_request()
        view = ExerciseViewSet.as_view({"get": "list", "post": "create"})

        # request must fail as requesting user isn't a teacher
        force_authenticate(request, user=student)
        response = view(request)
        self.assertEqual(response.status_code, 403)

        # request must succeed as requesting user is a teacher
        force_authenticate(request, user=teacher)
        response = view(request)
        self.assertEqual(response.status_code, 201)

    def test_update_exercise(self):
        teacher = User.objects.get(username="teacher")
        student = User.objects.get(username="student")

        request = self.get_post_request()

        # create new exercise
        view = ExerciseViewSet.as_view({"post": "create", "put": "update"})
        force_authenticate(request, user=teacher)
        view(request)

        # update the exercise
        factory = APIRequestFactory()
        request = factory.put(
            "/exercises/1",
            {
                "text": "Scrivere una funzione che, presi in input due numeri, restituisca il minimo tra i due.",
                "min_passing_testcases": 2,
                "testcases": [
                    {"input": "1%%2", "output": "1", "is_public": True},
                    {"input": "-1%%0", "output": "-1", "is_public": False},
                ],
            },
            format="json",
        )

        # request must fail as requesting user isn't a teacher
        force_authenticate(request, user=student)
        response = view(request, pk=1)
        self.assertEqual(response.status_code, 403)

        # request must succeed as requesting user is a teacher
        force_authenticate(request, user=teacher)
        response = view(request, pk=1)
        self.assertEqual(response.status_code, 200)

        response.render()

        # ensure the correct updated version is returned
        self.assertEqual(
            json.loads(response.content),
            {
                "id": 1,
                "text": "Scrivere una funzione che, presi in input due numeri, restituisca il minimo tra i due.",
                "testcases": [
                    {"id": 1, "input": "1%%2", "output": "1", "is_public": True},
                    {"id": 2, "input": "-1%%0", "output": "-1", "is_public": False},
                ],
            },
        )

    def test_testcase_retrieve_permissions(self):
        """
        Shows that, when retrieving an exercise, a student will only see public test cases,
        whereas a teacher will get all test cases, even secret ones
        """
        teacher = User.objects.get(username="teacher")
        student = User.objects.get(username="student")
        view = ExerciseViewSet.as_view({"get": "retrieve", "post": "create"})

        # create a new exercise
        post_request = self.get_post_request()
        force_authenticate(post_request, user=teacher)
        view(post_request)

        # enable user to see the newly created exercise
        Exercise.objects.get(pk=1).assigned_users.add(student)

        factory = APIRequestFactory()
        get_request = factory.get("/exercises/1", format="json")

        # students must see public test cases only
        force_authenticate(get_request, user=student)
        response = view(get_request, pk=1)
        response.render()

        self.assertEqual(
            json.loads(response.content),
            {
                "id": 1,
                "text": "Scrivere una funzione che, presi in input due numeri, restituisca il massimo tra i due.",
                "public_testcases": [
                    {"id": 1, "input": "1%%2", "output": "2", "is_public": True},
                ],
            },
        )

        # teachers must see all public cases
        force_authenticate(get_request, user=teacher)
        response = view(get_request, pk=1)
        response.render()

        self.assertEqual(
            json.loads(response.content),
            {
                "id": 1,
                "text": "Scrivere una funzione che, presi in input due numeri, restituisca il massimo tra i due.",
                "testcases": [
                    {"id": 1, "input": "1%%2", "output": "2", "is_public": True},
                    {"id": 2, "input": "-1%%0", "output": "0", "is_public": False},
                ],
            },
        )


class SubmissionViewSetTestCase(TestCase):
    def setUp(self):
        User.objects.create(username="teacher", is_teacher=True)
        student1 = User.objects.create(username="student1", is_teacher=False)
        student2 = User.objects.create(username="student2", is_teacher=False)

        exercise = Exercise.objects.create(
            text="Scrivere una funzione che, presi in input due numeri, restituisca il massimo tra i due",
            min_passing_testcases=3,
        )
        exercise.assigned_users.add(student1)
        exercise.assigned_users.add(student2)

        TestCase_.objects.create(
            exercise=exercise, input="1%%2", output="2", is_public=True
        )
        TestCase_.objects.create(
            exercise=exercise, input="10%%22", output="22", is_public=False
        )
        TestCase_.objects.create(
            exercise=exercise, input="-1%%0", output="0", is_public=True
        )

    def get_post_request(self, code, pk):
        """
        Returns a sample POST request for creating a submission with given code
        """
        factory = APIRequestFactory()
        return factory.post(
            "/exercises/" + str(pk) + "/submissions/",
            {
                "code": code,
            },
            format="json",
            pk=pk,
        )

    def get_get_request(self, exercise_pk, submission_pk):
        """
        Returns a sample GET request for accessing a submission
        """
        factory = APIRequestFactory()
        get_request = factory.get(
            "/exercises/" + str(exercise_pk) + "/submissions/" + str(submission_pk),
            format="json",
        )

        return get_request

    def test_submission_processing(self):
        """
        Shows the code of a submission is ran in node and the details object is compiled correctly
        """
        teacher = User.objects.get(username="teacher")
        student1 = User.objects.get(username="student1")
        student2 = User.objects.get(username="student2")

        view = SubmissionViewSet.as_view(
            {
                "post": "create",
            }
        )

        # submit a solution to the exercise as student1
        request = self.get_post_request(
            code="function max(a,b) { return a>b?a:b }", pk=1
        )
        force_authenticate(request, user=student1)

        response = view(request, exercise_pk=1)

        # POST request must succeed
        self.assertEqual(response.status_code, 201)

        # submitted code must pass all test cases
        response.render()
        content = json.loads(response.content)
        content.pop("timestamp")  # remove timestamp as it's non-deterministic

        self.assertEqual(
            content,
            {
                "id": 1,
                "user": 2,
                "code": "function max(a,b) { return a>b?a:b }",
                "is_eligible": True,
                "has_been_turned_in": False,
                "public_details": {  # a student must only see public test case details
                    "1": {
                        "parameters": ["1", "2"],
                        "output": 2,
                        "is_public": True,
                        "passed": True,
                    },
                    "3": {
                        "parameters": ["-1", "0"],
                        "output": 0,
                        "is_public": True,
                        "passed": True,
                    },
                    "failed_secret_tests": 0,
                },
            },
        )

    def test_submission_detail_permissions(self):
        """
        Shows students can only see the details of public test cases only regarding their submissions,
        whereas teachers can see the details of secret test cases as well
        """

        teacher = User.objects.get(username="teacher")
        student = User.objects.get(username="student1")
        exercise = Exercise.objects.get(pk=1)
        view = SubmissionViewSet.as_view({"get": "retrieve"})

        Submission.objects.create(
            code="function max(a,b) { return a>b?a:b }", exercise=exercise, user=student
        )

        # students can only see public test case details
        request = self.get_get_request(exercise_pk=1, submission_pk=1)
        force_authenticate(request, user=student)
        response = view(request, exercise_pk=1, pk=1)

        response.render()
        content = json.loads(response.content)
        content.pop("timestamp")  # remove timestamp as it's non-deterministic
        self.assertEqual(
            content,
            {
                "id": 1,
                "user": 2,
                "code": "function max(a,b) { return a>b?a:b }",
                "is_eligible": True,
                "has_been_turned_in": False,
                "public_details": {  # a student must only see public test case details
                    "1": {
                        "parameters": ["1", "2"],
                        "output": 2,
                        "is_public": True,
                        "passed": True,
                    },
                    "3": {
                        "parameters": ["-1", "0"],
                        "output": 0,
                        "is_public": True,
                        "passed": True,
                    },
                    "failed_secret_tests": 0,
                },
            },
        )

        # a teacher can see all details, including secret test cases
        request = self.get_get_request(exercise_pk=1, submission_pk=1)
        force_authenticate(request, user=teacher)
        response = view(request, exercise_pk=1, pk=1)

        response.render()
        content = json.loads(response.content)
        content.pop("timestamp")  # remove timestamp as it's non-deterministic

        self.assertEqual(
            content,
            {
                "id": 1,
                "user": 2,
                "code": "function max(a,b) { return a>b?a:b }",
                "is_eligible": True,
                "has_been_turned_in": False,
                "details": {  # all details are shown
                    "1": {
                        "parameters": ["1", "2"],
                        "output": 2,
                        "is_public": True,
                        "passed": True,
                    },
                    "2": {
                        "parameters": ["10", "22"],
                        "output": 22,
                        "is_public": False,
                        "passed": True,
                    },
                    "3": {
                        "parameters": ["-1", "0"],
                        "output": 0,
                        "is_public": True,
                        "passed": True,
                    },
                },
            },
        )

    def test_submission_owner_permissions(self):
        """
        Shows students can only access their own submissions, whereas teachers can access
        everybody's submissions to an exercise
        """
        teacher = User.objects.get(username="teacher")
        student1 = User.objects.get(username="student1")
        student2 = User.objects.get(username="student2")
        exercise = Exercise.objects.get(pk=1)
        view = SubmissionViewSet.as_view({"get": "retrieve"})

        Submission.objects.create(
            code="function max(a,b) { return a>b?a:b }",
            exercise=exercise,
            user=student1,
        )

        # a student can access their own submissions
        request = self.get_get_request(exercise_pk=1, submission_pk=1)
        force_authenticate(request, user=student1)
        response = view(request, exercise_pk=1, pk=1)
        self.assertEqual(response.status_code, 200)

        # a student cannot access somebody else's submissions
        request = self.get_get_request(exercise_pk=1, submission_pk=1)
        force_authenticate(request, user=student2)
        response = view(request, exercise_pk=1, pk=1)
        self.assertEqual(response.status_code, 404)

        # a teacher can access everybody's submissions
        request = self.get_get_request(exercise_pk=1, submission_pk=1)
        force_authenticate(request, user=teacher)
        response = view(request, exercise_pk=1, pk=1)
        self.assertEqual(response.status_code, 200)

    def test_submission_turn_in(self):
        """
        Shows only eligible submissions can be turned in, and after one submission has been turned in,
        no more submissions can be turned in
        """
        student = User.objects.get(username="student1")
        exercise = Exercise.objects.get(pk=1)
        view = SubmissionViewSet.as_view({"put": "turn_in"})

        noneligible_submission = Submission.objects.create(
            code="function max(a,b) { return a<b?a:b }",
            exercise=exercise,
            user=student,
        )

        eligible_submission = Submission.objects.create(
            code="function max(a,b) { return a>b?a:b }",
            exercise=exercise,
            user=student,
        )

        factory = APIRequestFactory()

        # non-eligible submissions cannot be turned in
        request = factory.put(
            "/exercises/1/submissions/1/turn_in",
        )
        force_authenticate(request, user=student)
        response = view(request, exercise_pk=1, pk=1)
        self.assertEqual(response.status_code, 403)

        # eligible submissions can be turned in
        request = factory.put(
            "/exercises/1/submissions/2/turn_in",
        )
        force_authenticate(request, user=student)
        response = view(request, exercise_pk=1, pk=2)
        self.assertEqual(response.status_code, 200)

        # no more submissions can be turned in
        eligible_submission_2 = Submission.objects.create(
            code="function max(a,b) { return a>b?a:b }",
            exercise=exercise,
            user=student,
        )
        request = factory.put(
            "/exercises/1/submissions/3/turn_in",
        )
        force_authenticate(request, user=student)
        response = view(request, exercise_pk=1, pk=3)
        self.assertEqual(response.status_code, 403)
