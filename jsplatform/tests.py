import json

from _datetime import timedelta
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from users.models import User

from jsplatform.exceptions import ExamCompletedException
from jsplatform.models import (
    Answer,
    Category,
    Exam,
    ExamProgress,
    Exercise,
    GivenAnswer,
    Question,
    Submission,
)
from jsplatform.models import (
    TestCase as TestCase_,
)  # prevent name conflict with django TestCase class
from jsplatform.views import ExamViewSet, ExerciseViewSet, SubmissionViewSet


class ExerciseViewSetTestCase(TestCase):
    def setUp(self):
        User.objects.create(
            username="teacher", is_teacher=True, email="teacher@unipi.it"
        )
        User.objects.create(
            username="student", is_teacher=False, email="student@studenti.unipi.it"
        )

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
                    {
                        "assertion": "assert.strictEqual(max(1,2), 2)",
                        "is_public": True,
                    },
                    {
                        "assertion": "assert.strictEqual(max(-1,0), 0)",
                        "is_public": False,
                    },
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
                    {
                        "assertion": "assert.strictEqual(max(1,2), 1)",
                        "is_public": True,
                    },
                    {
                        "assertion": "assert.strictEqual(max(-1,0), -1)",
                        "is_public": False,
                    },
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
        response_body = json.loads(response.content)

        # ensure the correct updated version is returned
        self.assertEqual(
            response_body["text"],
            "Scrivere una funzione che, presi in input due numeri, restituisca il minimo tra i due.",
        )
        self.assertEqual(response_body["id"], 1)

    """
    def test_testcase_retrieve_permissions(self):
        #
        # Shows that, when retrieving an exercise, a student will only see public test cases,
        whereas a teacher will get all test cases, even secret ones
        # 
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
                    {
                        "id": 1,
                        "assertion": "assert.strictEqual(max(1,2), 2)",
                        "is_public": True,
                    },
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
                    {
                        "id": 1,
                        "assertion": "assert.strictEqual(max(1,2), 2)",
                        "is_public": True,
                    },
                    {
                        "id": 2,
                        "assertion": "assert.strictEqual(max(-1,0), 0)",
                        "is_public": False,
                    },
                ],
            },
        )

    """


class SubmissionViewSetTestCase(TestCase):
    def setUp(self):
        User.objects.create(
            username="teacher", is_teacher=True, email="teacher@unipi.it"
        )
        student1 = User.objects.create(
            username="student1", is_teacher=False, email="student1@studenti.unipi.it"
        )
        student2 = User.objects.create(
            username="student2", is_teacher=False, email="student2@studenti.unipi.it"
        )

        exercise = Exercise.objects.create(
            text="Scrivere una funzione che, presi in input due numeri, restituisca il massimo tra i due",
            min_passing_testcases=3,
        )
        # exercise.assigned_users.add(student1)
        # exercise.assigned_users.add(student2)

        TestCase_.objects.create(
            exercise=exercise,
            assertion="assert.strictEqual(max(1,2), 2)",
            is_public=True,
        )
        TestCase_.objects.create(
            exercise=exercise,
            assertion="assert.strictEqual(max(10,22), 22)",
            is_public=False,
        )
        TestCase_.objects.create(
            exercise=exercise,
            assertion="assert.strictEqual(max(-1,0), 0)",
            is_public=True,
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
                "public_details": {
                    "failed_secret_tests": 0,
                    "tests": [
                        {
                            "id": 1,
                            "assertion": "assert.strictEqual(max(1,2), 2)",
                            "is_public": True,
                            "passed": True,
                        },
                        {
                            "id": 3,
                            "assertion": "assert.strictEqual(max(-1,0), 0)",
                            "is_public": True,
                            "passed": True,
                        },
                    ],
                },  # a student must only see public test case details
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
                    "tests": [
                        {
                            "id": 1,
                            "assertion": "assert.strictEqual(max(1,2), 2)",
                            "is_public": True,
                            "passed": True,
                        },
                        {
                            "id": 3,
                            "assertion": "assert.strictEqual(max(-1,0), 0)",
                            "is_public": True,
                            "passed": True,
                        },
                    ],
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
                    "tests": [
                        {
                            "id": 1,
                            "assertion": "assert.strictEqual(max(1,2), 2)",
                            "is_public": True,
                            "passed": True,
                        },
                        {
                            "id": 2,
                            "assertion": "assert.strictEqual(max(10,22), 22)",
                            "is_public": False,
                            "passed": True,
                        },
                        {
                            "id": 3,
                            "assertion": "assert.strictEqual(max(-1,0), 0)",
                            "is_public": True,
                            "passed": True,
                        },
                    ],
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
        # todo this should work again once line 1228 of models.py has been taken care of
        # request = factory.put(
        #     "/exercises/1/submissions/2/turn_in",
        # )
        # force_authenticate(request, user=student)
        # response = view(request, exercise_pk=1, pk=2)
        # self.assertEqual(response.status_code, 200)

        # # no more submissions can be turned in
        # eligible_submission_2 = Submission.objects.create(
        #     code="function max(a,b) { return a>b?a:b }",
        #     exercise=exercise,
        #     user=student,
        # )
        # request = factory.put(
        #     "/exercises/1/submissions/3/turn_in",
        # )
        # force_authenticate(request, user=student)
        # response = view(request, exercise_pk=1, pk=3)
        # self.assertEqual(response.status_code, 403)


class QuestionViewSetTestCase(TestCase):
    pass


class ExamTestCase(TestCase):
    """
    Tests functionalities of the ExamProgress model and how they relate to
    the ExamViewSet for exposing the correct items to users
    """

    def setUp(self):
        now = timezone.localtime(timezone.now())
        tomorrow = now + timedelta(days=1)

        self.student1 = User.objects.create(
            username="student1", email="student1@studenti.unipi.it"
        )
        self.student2 = User.objects.create(
            username="student2", email="student2@studenti.unipi.it"
        )
        self.student3 = User.objects.create(
            username="student3", email="student3@studenti.unipi.it"
        )

        self.teacher = User.objects.create(username="teacher", email="teacher@unipi.it")

        self.exam = Exam.objects.create(
            name="Test exam", begin_timestamp=now, end_timestamp=tomorrow, draft=False
        )

        cat1 = Category.objects.create(
            exam=self.exam, name="cat1", amount=3, item_type="q", randomize=False
        )
        self.q1 = Question.objects.create(
            exam=self.exam, text="question1", category=cat1
        )
        self.q2 = Question.objects.create(
            exam=self.exam,
            text="question1",
            category=cat1,
            accepts_multiple_answers=True,
        )
        self.q3 = Question.objects.create(
            exam=self.exam, text="question1", category=cat1
        )

        self.q1a1 = Answer.objects.create(question=self.q1, text="abc")
        self.q1a2 = Answer.objects.create(question=self.q1, text="abc")
        self.q1a3 = Answer.objects.create(question=self.q1, text="abc")
        self.q2a1 = Answer.objects.create(question=self.q2, text="abc")
        self.q2a2 = Answer.objects.create(question=self.q2, text="abc")
        self.q2a3 = Answer.objects.create(question=self.q2, text="abc")
        self.q3a1 = Answer.objects.create(question=self.q3, text="abc")
        self.q3a2 = Answer.objects.create(question=self.q3, text="abc")
        self.q3a3 = Answer.objects.create(question=self.q3, text="abc")

        self.max_cursor_value = self.exam.get_number_of_items_per_exam() - 1

    def get_post_request(self, api_url, body):
        factory = APIRequestFactory()
        return factory.post(api_url, body, format="json")

    def test_exam_progress_generation_and_cursor(self):
        """
        Tests the ability of ExamProgress to assign items to a user and to
        expose a single item identified by its `current_item_cursor`
        """

        exam_progress = ExamProgress.objects.create(user=self.student1, exam=self.exam)
        self.assertTrue(exam_progress.is_initialized)
        self.assertTrue(self.q1 in exam_progress.questions.all())
        self.assertTrue(self.q2 in exam_progress.questions.all())
        self.assertTrue(self.q3 in exam_progress.questions.all())

        self.assertFalse(exam_progress.is_there_previous)
        self.assertEqual(exam_progress.current_item_cursor, 0)
        self.assertEqual(exam_progress.current_item, self.q1)

        self.assertEqual(exam_progress.move_cursor_forward(), self.q2)
        self.assertEqual(exam_progress.current_item_cursor, 1)
        self.assertTrue(exam_progress.is_there_previous)

        self.assertEqual(exam_progress.move_cursor_back(), self.q1)
        self.assertEqual(exam_progress.current_item_cursor, 0)

        # trying to go back past the first item has no effect
        self.assertEqual(exam_progress.move_cursor_back(), self.q1)
        self.assertEqual(exam_progress.current_item_cursor, 0)

        self.assertEqual(exam_progress.move_cursor_forward(), self.q2)
        self.assertEqual(exam_progress.current_item_cursor, 1)
        self.assertTrue(exam_progress.is_there_next)

        self.assertEqual(exam_progress.move_cursor_forward(), self.q3)
        self.assertEqual(exam_progress.current_item_cursor, 2)

        # trying to go forward past the last item has no effect
        self.assertFalse(exam_progress.is_there_next)
        self.assertEqual(exam_progress.move_cursor_forward(), self.q3)
        self.assertEqual(exam_progress.current_item_cursor, 2)

        exam_progress.end_exam()
        self.assertTrue(exam_progress.is_done)

        # can't move cursor anymore once the exam is over
        with self.assertRaises(ExamCompletedException):
            exam_progress.move_cursor_back()

        with self.assertRaises(ExamCompletedException):
            exam_progress.move_cursor_forward()

    def test_exam_access(self):
        # todo - test that a student cannot PUT/POST an exam, that a teacher cannot access an
        # todo - exam as a student, etc.
        # shows that accessing an exam fails if unauthenticated, or if the exam is closed or hasn't started yet, etc.
        client = APIClient()

        # no authentication
        response = client.post(f"/exams/{self.exam.pk}/current_item/", {})
        self.assertEqual(response.status_code, 403)
        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 403)
        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 403)
        response = client.post(f"/exams/{self.exam.pk}/give_answer/", {})
        self.assertEqual(response.status_code, 403)
        response = client.post(f"/exams/{self.exam.pk}/withdraw_answer/", {})
        self.assertEqual(response.status_code, 403)

        # auth'd as a student
        client.force_authenticate(user=self.student1)

        # trying to go back or forward before creating the ExamProgress object
        # through `current_item` doesn't work either
        client.force_authenticate(user=self.student1)
        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 404)
        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 404)
        # this will work because we're authenticated
        response = client.post(f"/exams/{self.exam.pk}/current_item/", {})
        self.assertEqual(response.status_code, 200)

        # students can't close an exam
        response = client.patch(f"/exams/{self.exam.pk}/terminate/", {})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.exam.closed, False)

    def test_progress_and_stats(self):
        # shows that as exam participants answer question, their `completed_items_count` increases, and that when
        # an answer is selected by a user, its `selections` count increases
        cat2 = Category.objects.create(
            exam=self.exam, name="cat2", amount=2, item_type="q", randomize=False
        )
        q4multiple_answers = Question.objects.create(
            exam=self.exam,
            text="question4",
            category=cat2,
            accepts_multiple_answers=True,
        )
        q4a1 = Answer.objects.create(question=q4multiple_answers, text="abc")
        q4a2 = Answer.objects.create(question=q4multiple_answers, text="abc")
        q4a3 = Answer.objects.create(question=q4multiple_answers, text="abc")

        exam_progress = ExamProgress.objects.create(user=self.student3, exam=self.exam)

        # let's make sure the tests pass even when there's more than one user taking
        # the exam and with the same assigned items
        student4 = User.objects.create(
            username="student4", email="student4@studenti.unipi.it"
        )
        ExamProgress.objects.create(user=student4, exam=self.exam)
        student5 = User.objects.create(
            username="student5", email="student5@studenti.unipi.it"
        )
        ExamProgress.objects.create(user=student5, exam=self.exam)

        self.assertEqual(exam_progress.completed_items_count, 0)
        self.assertEqual(self.q3a1.selections, 0)
        self.assertEqual(self.q3a2.selections, 0)
        self.assertEqual(self.q3a3.selections, 0)

        GivenAnswer.objects.create(
            user=self.student3, question=self.q3, answer=self.q3a1
        )
        # answering a question increases the count of completed items
        self.assertEqual(exam_progress.completed_items_count, 1)
        # it also increases the amount of selections of the chosen answer
        self.assertEqual(self.q3a1.selections, 1)
        self.assertEqual(self.q3a2.selections, 0)
        self.assertEqual(self.q3a3.selections, 0)

        g1 = GivenAnswer.objects.create(
            user=self.student3, question=q4multiple_answers, answer=q4a1
        )
        self.assertEqual(exam_progress.completed_items_count, 2)
        self.assertEqual(q4a1.selections, 1)
        self.assertEqual(q4a2.selections, 0)
        self.assertEqual(q4a3.selections, 0)
        g2 = GivenAnswer.objects.create(
            user=self.student3, question=q4multiple_answers, answer=q4a2
        )
        # selecting multiple answers for a question that accepts multiple answers doesn't
        # increase the count of completed items more than once
        self.assertEqual(exam_progress.completed_items_count, 2)
        self.assertEqual(q4a1.selections, 1)
        self.assertEqual(q4a2.selections, 1)
        self.assertEqual(q4a3.selections, 0)

        g1.delete()
        # completed items count doesn't go down because there's still a selected
        # answer for the question
        self.assertEqual(exam_progress.completed_items_count, 2)
        self.assertEqual(q4a1.selections, 0)
        self.assertEqual(q4a2.selections, 1)
        self.assertEqual(q4a3.selections, 0)

        g2.delete()
        self.assertEqual(exam_progress.completed_items_count, 1)
        self.assertEqual(q4a1.selections, 0)
        self.assertEqual(q4a2.selections, 0)
        self.assertEqual(q4a3.selections, 0)

    def test_exam_viewset_student(self):
        # exam_progress = ExamProgress.objects.create(user=self.student2, exam=self.exam)

        client = APIClient()
        client.force_authenticate(user=self.student2)

        # battery 1 - tests going forward and back

        response = client.post(f"/exams/{self.exam.pk}/current_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 1)

        # trying to go back past the first item has no effect and keeps returning the first item
        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 1)

        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 2)

        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 3)

        # trying to go past the last item has no effect and keeps returning the last item
        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 3)

        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 2)

        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 1)

        # battery 2 - tests giving answers

        # give an answer
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q1a1.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GivenAnswer.objects.filter(user=self.student2, question=self.q1).count(), 1
        )

        given_ans1 = GivenAnswer.objects.get(user=self.student2, question=self.q1)
        self.assertEqual(
            given_ans1.answer,
            self.q1a1,
        )

        # give another answer to the same question - the question doesn't accept
        # multiple answers, therefore the same GivenAnswer gets updated
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q1a2.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GivenAnswer.objects.filter(user=self.student2, question=self.q1).count(), 1
        )
        # it's still the same object...
        given_ans2 = GivenAnswer.objects.get(user=self.student2, question=self.q1)
        self.assertEqual(given_ans2, given_ans1)
        # ... but its answer has been updated
        self.assertEqual(given_ans2.answer, self.q1a2)

        # try to give an answer that doesn't exist
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": 99999,
            },
        )
        self.assertEqual(response.status_code, 400)
        # the object hasn't been touched
        self.assertEqual(
            GivenAnswer.objects.get(user=self.student2, question=self.q1).answer,
            self.q1a2,
        )

        # try to give an answer that is valid but refers to another question (not the current item)
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q2a1.pk,
            },
        )
        self.assertEqual(response.status_code, 400)
        # the object hasn't been touched
        self.assertEqual(
            GivenAnswer.objects.get(user=self.student2, question=self.q1).answer,
            self.q1a2,
        )

        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"]["id"], 2)

        # current question accepts multiple answers

        # create first answer
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q2a1.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GivenAnswer.objects.filter(user=self.student2, question=self.q2).count(), 1
        )
        # hitting `give_answer` will create a second GivenAnswer this time, because the
        # current question accepts multiple answers
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q2a2.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GivenAnswer.objects.filter(user=self.student2, question=self.q2).count(), 2
        )

        given_ans_lst = list(
            map(
                lambda e: e.answer,
                GivenAnswer.objects.filter(user=self.student2, question=self.q2),
            )
        )
        # both answers have been recorded
        self.assertListEqual([self.q2a1, self.q2a2], given_ans_lst)

        # trying to add the same answer twice results in error 400
        with transaction.atomic():  # this is needed to prevent weird behavior during unit tests
            response = client.post(
                f"/exams/{self.exam.pk}/give_answer/",
                {
                    "answer": self.q2a2.pk,
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            GivenAnswer.objects.filter(user=self.student2, question=self.q2).count(), 2
        )

        # now withdraw a given answer
        response = client.post(
            f"/exams/{self.exam.pk}/withdraw_answer/",
            {
                "answer": self.q2a2.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            GivenAnswer.objects.filter(user=self.student2, question=self.q2).count(), 1
        )
        self.assertEqual(
            self.q2a1,
            GivenAnswer.objects.get(user=self.student2, question=self.q2).answer,
        )

        # try to withdraw an answer that doesn't exist and an answer that wasn't given
        response = client.post(
            f"/exams/{self.exam.pk}/withdraw_answer/",
            {
                "answer": 99999,
            },
        )
        self.assertEqual(response.status_code, 400)
        response = client.post(
            f"/exams/{self.exam.pk}/withdraw_answer/",
            {
                "answer": self.q2a2.pk,
            },
        )
        self.assertEqual(response.status_code, 400)

        # battery 3 - exam gets closed, test that no action can be performed

        self.exam.close_exam(closed_by=self.teacher)
        self.assertTrue(self.exam.closed)

        exam_progress = ExamProgress.objects.get(exam=self.exam, user=self.student2)
        curr_cursor_val = exam_progress.current_item_cursor

        response = client.post(f"/exams/{self.exam.pk}/current_item/", {})
        self.assertEqual(response.status_code, 410)

        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 410)

        # current item cursor hasn't moved
        exam_progress.refresh_from_db()
        self.assertEqual(curr_cursor_val, exam_progress.current_item_cursor)

        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 410)

        # current item cursor hasn't moved
        exam_progress.refresh_from_db()
        self.assertEqual(curr_cursor_val, exam_progress.current_item_cursor)

        # answers cannot be given or withdrawn anymore
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q2a2.pk,
            },
        )
        self.assertEqual(response.status_code, 410)

        response = client.post(
            f"/exams/{self.exam.pk}/withdraw_answer/",
            {
                "answer": self.q2a1.pk,
            },
        )
        self.assertEqual(response.status_code, 410)
