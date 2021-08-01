import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import User
from .views import TeacherList


class UsersTestCase(TestCase):
    def setUp(self):
        self.teacher1 = User.objects.create(
            username="teacher1", email="teacher1@unipi.it"
        )
        self.teacher2 = User.objects.create(
            username="teacher2", email="teacher2@unipi.it"
        )
        self.student1 = User.objects.create(
            username="student1", email="student1@studenti.unipi.it"
        )
        self.student2 = User.objects.create(
            username="student2", email="student2@studenti.unipi.it"
        )

    def test_teacher_detection(self):
        """
        Tests ability to detect teachers based on their email address
        """
        self.assertTrue(self.teacher1.is_teacher)
        self.assertFalse(self.student1.is_teacher)

    def test_teachers_list_view(self):
        """
        Tests permissions and response from TeacherList API view
        """
        factory = APIRequestFactory()
        request = factory.get("teachers")

        view = TeacherList.as_view()

        # unauthenticated users cannot access this view
        response = view(request)
        self.assertEqual(response.status_code, 403)

        # non-teacher users cannot access this view
        force_authenticate(request, user=self.student1)
        response = view(request)
        self.assertEqual(response.status_code, 403)

        # teachers can access this view
        force_authenticate(request, user=self.teacher1)
        response = view(request)
        self.assertEqual(response.status_code, 200)

        response.render()

        self.assertContains(response, "teacher1")
        self.assertContains(response, "teacher2")
        self.assertNotContains(response, "student1")
        self.assertNotContains(response, "student2")
