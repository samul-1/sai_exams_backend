import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from jsplatform.models import Exercise, Submission, User
from jsplatform.views import ExerciseViewSet


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
