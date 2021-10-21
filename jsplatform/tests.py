import json

from _datetime import timedelta
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from users.models import User

from jsplatform.exceptions import (
    ExamCompletedException,
    InvalidAnswerException,
    InvalidCategoryType,
    TooManyAnswers,
)
from jsplatform.models import (
    Answer,
    Category,
    Exam,
    ExamProgress,
    ExamProgressQuestionsThroughModel,
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
        self.maxDiff = None
        self.assertEqual(
            content,
            {
                "id": 1,
                "total_testcases": 3,
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
                "total_testcases": 3,
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
                "total_testcases": 3,
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


class QuestionViewSetTestCase(TestCase):
    pass


class ExamStateTestCase(TestCase):
    """
    Tests that exam items assigned to participants are retrieved correctly in order to generate
    post-exam reports
    """

    def setUp(self):
        now = timezone.localtime(timezone.now())

        self.student1 = User.objects.create(
            username="student1", email="student1@studenti.unipi.it"
        )
        self.student2 = User.objects.create(
            username="student2", email="student2@studenti.unipi.it"
        )
        self.student3 = User.objects.create(
            username="student3", email="student3@studenti.unipi.it"
        )

        self.exam = Exam.objects.create(
            name="Test exam", begin_timestamp=now, end_timestamp=now, draft=False
        )

        cat1 = Category.objects.create(
            exam=self.exam, name="cat1", amount=3, item_type="q", randomize=False
        )

        self.q1 = Question.objects.create(
            exam=self.exam,
            text="question1",
            category=cat1,
            accepts_multiple_answers=True,
        )
        self.q2 = Question.objects.create(
            exam=self.exam, text="question2", category=cat1
        )
        self.q3 = Question.objects.create(
            exam=self.exam, text="question3", category=cat1
        )
        self.q4 = Question.objects.create(
            exam=self.exam, text="question4", category=cat1
        )

        self.q1a1 = Answer.objects.create(question=self.q1, text="abc")
        self.q1a2 = Answer.objects.create(question=self.q1, text="abc")
        self.q2a1 = Answer.objects.create(question=self.q2, text="abc")
        self.q2a2 = Answer.objects.create(question=self.q2, text="abc")

    def test_exam_progress_with_exercises(self):
        now = timezone.localtime(timezone.now())
        tomorrow = now + timedelta(days=1)

        exam = Exam.objects.create(
            name="Test exam",
            begin_timestamp=now,
            end_timestamp=tomorrow,
            draft=False,
        )
        cat2 = Category.objects.create(
            exam=exam, name="cat2", amount=2, item_type="e", randomize=False
        )
        e1 = Exercise.objects.create(
            exam=exam, text="exercise1", category=cat2, min_passing_testcases=0
        )
        TestCase_.objects.create(exercise=e1, assertion="assert.equal(a(1),1)")
        TestCase_.objects.create(exercise=e1, assertion="assert.equal(a(2),2)")

        e2 = Exercise.objects.create(
            exam=exam, text="exercise2", category=cat2, min_passing_testcases=0
        )
        TestCase_.objects.create(exercise=e2, assertion="assert.equal(a(1),1)")
        TestCase_.objects.create(exercise=e2, assertion="assert.equal(a(2),2)")

        exam_progress = ExamProgress.objects.create(user=self.student1, exam=exam)
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertListEqual(
            [e1.pk, e2.pk],
            [e["id"] for e in progress_as_dict1["exercises"]],
        )

        self.assertFalse(progress_as_dict1["exercises"][0]["turned_in"])
        self.assertEqual(progress_as_dict1["exercises"][0]["submission"], "")

        # making a submission without turning it in adds it to the dict but with turned_in=False
        submission1 = Submission.objects.create(
            user=self.student1, exercise=e1, code="function a(n) { return 1 }"
        )
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertFalse(progress_as_dict1["exercises"][0]["turned_in"])
        self.assertEqual(
            progress_as_dict1["exercises"][0]["submission"], submission1.code
        )
        self.assertEqual(progress_as_dict1["exercises"][0]["passed_testcases"], 1)
        self.assertEqual(progress_as_dict1["exercises"][0]["failed_testcases"], 1)

        # making a better submission overwrites the former
        submission2 = Submission.objects.create(
            user=self.student1, exercise=e1, code="function a(n) { return n }"
        )
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertFalse(progress_as_dict1["exercises"][0]["turned_in"])
        self.assertEqual(
            progress_as_dict1["exercises"][0]["submission"], submission2.code
        )
        self.assertEqual(progress_as_dict1["exercises"][0]["passed_testcases"], 2)
        self.assertEqual(progress_as_dict1["exercises"][0]["failed_testcases"], 0)

        # turning in a submission makes that one appear in the dict
        submission1.turn_in()
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertTrue(progress_as_dict1["exercises"][0]["turned_in"])
        self.assertEqual(
            progress_as_dict1["exercises"][0]["submission"], submission1.code
        )
        self.assertEqual(progress_as_dict1["exercises"][0]["passed_testcases"], 1)
        self.assertEqual(progress_as_dict1["exercises"][0]["failed_testcases"], 1)

        # show that submitting a newer solution with the same number of pased test cases
        # overwrites the older one in the dict
        submission3 = Submission.objects.create(
            user=self.student1, exercise=e2, code="function a(n) { return n }"
        )
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertFalse(progress_as_dict1["exercises"][1]["turned_in"])
        self.assertEqual(
            progress_as_dict1["exercises"][1]["submission"], submission3.code
        )
        self.assertEqual(progress_as_dict1["exercises"][1]["passed_testcases"], 2)
        self.assertEqual(progress_as_dict1["exercises"][1]["failed_testcases"], 0)

        submission4 = Submission.objects.create(
            user=self.student1, exercise=e2, code="function a(n) { return n; }"
        )
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertFalse(progress_as_dict1["exercises"][1]["turned_in"])
        self.assertEqual(
            progress_as_dict1["exercises"][1]["submission"], submission4.code
        )
        self.assertEqual(progress_as_dict1["exercises"][1]["passed_testcases"], 2)
        self.assertEqual(progress_as_dict1["exercises"][1]["failed_testcases"], 0)

        # making a newer, worse submission doesn't overwrite the one in the dict
        submission5 = Submission.objects.create(
            user=self.student1, exercise=e2, code="function a(n) { return ; }"
        )
        progress_as_dict1 = exam_progress.get_progress_as_dict(for_pdf=True)
        self.assertFalse(progress_as_dict1["exercises"][1]["turned_in"])
        self.assertEqual(
            progress_as_dict1["exercises"][1]["submission"], submission4.code
        )
        self.assertEqual(progress_as_dict1["exercises"][1]["passed_testcases"], 2)
        self.assertEqual(progress_as_dict1["exercises"][1]["failed_testcases"], 0)

    def test_retrieve_assigned_items_sorted(self):
        exam_progress1 = ExamProgress(user=self.student1, exam=self.exam)
        exam_progress1.save(initialize=False)

        exam_progress2 = ExamProgress(user=self.student2, exam=self.exam)
        exam_progress2.save(initialize=False)

        exam_progress3 = ExamProgress(user=self.student3, exam=self.exam)
        exam_progress3.save(initialize=False)

        # assign to the first participant [q1, q2, q3]
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress1, question=self.q1, ordering=1
        )
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress1,
            question=self.q3,
            # mixing up the order of creation of the through table rows doesn't
            # change the ordering, what matters is the 'ordering` attribute
            ordering=3,
        )
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress1, question=self.q2, ordering=2
        )

        # assign to the second participant [q2, q1, q3]
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress2, question=self.q2, ordering=1
        )
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress2, question=self.q1, ordering=2
        )
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress2, question=self.q3, ordering=3
        )

        # assign to the third participant [q1, q4, q2]
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress3, question=self.q2, ordering=3
        )
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress3, question=self.q4, ordering=2
        )
        ExamProgressQuestionsThroughModel.objects.create(
            exam_progress=exam_progress3, question=self.q1, ordering=1
        )

        # show that all and only the assigned questions are retrieved, in the
        # same order as they were assigned to each participant
        progress_as_dict1 = exam_progress1.get_progress_as_dict(for_pdf=True)
        self.assertListEqual(
            [self.q1.pk, self.q2.pk, self.q3.pk],
            [q["id"] for q in progress_as_dict1["questions"]],
        )

        GivenAnswer.objects.create(
            user=self.student2, question=self.q2, answer=self.q2a1
        )
        GivenAnswer.objects.create(
            user=self.student2, question=self.q1, answer=self.q1a1
        )
        GivenAnswer.objects.create(
            user=self.student2, question=self.q1, answer=self.q1a2
        )
        progress_as_dict2 = exam_progress2.get_progress_as_dict(for_pdf=True)
        self.assertListEqual(
            [self.q2.pk, self.q1.pk, self.q3.pk],
            [q["id"] for q in progress_as_dict2["questions"]],
        )

        # given answers were correctly recorded
        self.assertListEqual(
            [True, False],
            [a["selected"] for a in progress_as_dict2["questions"][0]["answers"]],
        )
        self.assertListEqual(
            [True, True],
            [a["selected"] for a in progress_as_dict2["questions"][1]["answers"]],
        )

        progress_as_dict3 = exam_progress3.get_progress_as_dict(for_pdf=True)
        self.assertListEqual(
            [self.q1.pk, self.q4.pk, self.q2.pk],
            [q["id"] for q in progress_as_dict3["questions"]],
        )


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
            name="Test exam",
            begin_timestamp=now,
            end_timestamp=tomorrow,
            draft=False,
            created_by=self.teacher,
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

    def get_post_request(self, api_url, body):
        factory = APIRequestFactory()
        return factory.post(api_url, body, format="json")

    def test_exam_progress_with_exercises(self):
        now = timezone.localtime(timezone.now())
        tomorrow = now + timedelta(days=1)

        exam = Exam.objects.create(
            name="Test exam",
            begin_timestamp=now,
            end_timestamp=tomorrow,
            draft=False,
            created_by=self.teacher,
        )
        cat2 = Category.objects.create(
            exam=exam, name="cat2", amount=2, item_type="e", randomize=False
        )
        e1 = Exercise.objects.create(
            exam=exam, text="exercise1", category=cat2, min_passing_testcases=0
        )
        e2 = Exercise.objects.create(
            exam=exam, text="exercise2", category=cat2, min_passing_testcases=0
        )

        exam_progress = ExamProgress.objects.create(user=self.student1, exam=exam)
        self.assertTrue(exam_progress.is_initialized)
        self.assertTrue(e1 in exam_progress.exercises.all())
        self.assertEqual(exam_progress.completed_items_count, 0)

        submission = Submission.objects.create(exercise=e1, user=self.student1, code="")
        self.assertTrue(submission.is_eligible)
        self.assertFalse(submission.has_been_turned_in)
        self.assertEqual(exam_progress.completed_items_count, 0)

        submission.turn_in()
        self.assertTrue(submission.has_been_turned_in)
        self.assertEqual(exam_progress.completed_items_count, 1)

        submission2 = Submission.objects.create(
            exercise=e2, user=self.student1, code=""
        )
        self.assertTrue(submission2.is_eligible)
        self.assertFalse(submission2.has_been_turned_in)
        self.assertEqual(exam_progress.completed_items_count, 1)

        submission2.turn_in()
        self.assertTrue(submission2.has_been_turned_in)
        self.assertEqual(exam_progress.completed_items_count, 2)

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
        #  exam as a student, etc.

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

        post_request_body = {
            "questions": [
                {
                    "answers": [],
                    "category_uuid": "582c9244-edb7-4800-a669-53f5f79df2e9",
                    "text": '<p style="display: inline-block">abc</p>',
                    "introduction_text": "",
                    "accepts_multiple_answers": False,
                    "question_type": "o",
                }
            ],
            "exercises": [],
            "categories": [
                {
                    "text": "",
                    "introduction_text": "",
                    "tmp_uuid": "582c9244-edb7-4800-a669-53f5f79df2e9",
                    "item_type": "q",
                    "name": "cat1",
                    "amount": 1,
                    "is_aggregated_question": False,
                    "randomize": True,
                }
            ],
            "name": "test",
            "begin_timestamp": "2021-07-01 00:00:00",
            "end_timestamp": "2021-07-08 00:00:00",
            "randomize_questions": True,
            "randomize_exercises": True,
            "allowed_teachers": [self.teacher.pk],
        }

        # students cannot create exams
        response = client.post(f"/exams/", post_request_body)
        self.assertEqual(response.status_code, 403)

        with self.assertRaises(Exam.DoesNotExist):
            Exam.objects.get(name="test")

        client.force_authenticate(user=self.teacher)
        response = client.post(f"/exams/", post_request_body)
        self.assertEqual(response.status_code, 201)
        # retrieve newly created exam
        new_exam_id = response.data["id"]
        response = client.get(f"/exams/{new_exam_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "abc")

        # non-authorized teachers cannot access exams
        new_teacher = User.objects.create(
            username="teacher2", email="teacher2@unipi.it"
        )
        client.force_authenticate(user=new_teacher)
        response = client.get(f"/exams/{new_exam_id}/")
        self.assertEqual(response.status_code, 404)

        # update exam to add new teacher
        post_request_body.update({"allowed_teachers": [new_teacher.pk]})
        client.force_authenticate(user=self.teacher)
        response = client.put(f"/exams/{new_exam_id}/", post_request_body)
        self.assertEqual(response.status_code, 200)

        # authorized teacher can now access the exam
        client.force_authenticate(user=new_teacher)
        response = client.get(f"/exams/{new_exam_id}/")
        self.assertEqual(response.status_code, 200)

    def test_create_and_update_exam(self):
        # tests creation of new exams and updating existing exams
        cat1_uuid = "13d14bd4-7638-43c1-be16-857995b012f7"
        cat2_uuid = "5957ca81-0155-4ae5-a185-7eedccce3545"
        cat3_uuid = "3d23e04b-0dd3-40ef-ab6b-53e88c9261f9"

        post_request_body = {
            "name": "Test exam 1",
            "draft": False,
            "begin_timestamp": "2021-07-12 09:00:00",
            "end_timestamp": "2021-07-12 10:00:00",
            "allow_going_back": True,
            "randomize_questions": True,
            "randomize_exercises": False,
            "allowed_teachers": [],
            "questions": [
                {
                    "answers": [],
                    "text": "open question in category 1",
                    "question_type": "o",
                    "accepts_multiple_answers": False,
                    "category_uuid": cat1_uuid,
                },
                {
                    "answers": [
                        {
                            "text": "wrong1",
                            "is_right_answer": False,
                        },
                        {
                            "text": "right1",
                            "is_right_answer": True,
                        },
                    ],
                    "text": "multiple choice question 1 in category 1",
                    "question_type": "m",
                    "accepts_multiple_answers": False,
                    "category_uuid": cat1_uuid,
                },
                {
                    "answers": [
                        {
                            "text": "right2",
                            "is_right_answer": True,
                        },
                        {
                            "text": "wrong2",
                            "is_right_answer": False,
                        },
                    ],
                    "text": "question that accepts multiple answers in category 2",
                    "question_type": "m",
                    "accepts_multiple_answers": True,
                    "category_uuid": cat2_uuid,
                },
            ],
            "exercises": [],
            "categories": [
                {
                    "introduction_text": "",
                    "amount": 1,
                    "name": "cat1",
                    "item_type": "q",
                    "is_aggregated_question": False,
                    "randomize": True,
                    "tmp_uuid": cat1_uuid,
                },
                {
                    "introduction_text": "",
                    "name": "cat2",
                    "item_type": "q",
                    "amount": 1,
                    "is_aggregated_question": False,
                    "randomize": True,
                    "tmp_uuid": cat2_uuid,
                },
            ],
        }
        client = APIClient()

        client.force_authenticate(user=self.teacher)
        response = client.post("/exams/", post_request_body)
        self.assertEquals(response.status_code, 201)

        # exam has been created
        new_exam = Exam.objects.get(name="Test exam 1")

        self.assertTrue(new_exam.allow_going_back)
        self.assertTrue(new_exam.randomize_questions)
        self.assertFalse(new_exam.draft)
        self.assertFalse(new_exam.randomize_exercises)
        self.assertEquals(new_exam.created_by, self.teacher)

        categories = new_exam.categories.all()
        cat1 = categories.get(name="cat1")
        cat2 = categories.get(name="cat2")

        # both categories have been created
        self.assertSetEqual(set([c.name for c in categories]), set(["cat1", "cat2"]))

        # all 3 questions have been created
        questions = new_exam.questions.all()
        self.assertEquals(questions.count(), 3)

        # check correct properties of all 3 questions
        q1 = questions.get(text="open question in category 1")
        self.assertEquals(q1.category, categories.get(name="cat1"))
        self.assertEquals(q1.question_type, "o")
        self.assertFalse(q1.accepts_multiple_answers)

        q2 = questions.get(text="multiple choice question 1 in category 1")
        self.assertEquals(q2.category, categories.get(name="cat1"))
        self.assertEquals(q2.question_type, "m")
        self.assertFalse(q2.accepts_multiple_answers)
        q2answers = q2.answers.all()
        self.assertSetEqual(set([a.text for a in q2answers]), set(["wrong1", "right1"]))
        self.assertFalse(q2answers.get(text="wrong1").is_right_answer)
        self.assertTrue(q2answers.get(text="right1").is_right_answer)

        q3 = questions.get(text="question that accepts multiple answers in category 2")
        self.assertEquals(q3.category, categories.get(name="cat2"))
        self.assertEquals(q3.question_type, "m")
        self.assertTrue(q3.accepts_multiple_answers)
        q3answers = q3.answers.all()
        self.assertSetEqual(set([a.text for a in q3answers]), set(["wrong2", "right2"]))
        self.assertTrue(q3answers.get(text="right2").is_right_answer)
        self.assertFalse(q3answers.get(text="wrong2").is_right_answer)

        new_allowed_teacher = User.objects.create(
            username="allowed_teacher", email="allowed_teacher@unipi.it"
        )
        # delete first question, create category 3, move second question to new category, add an
        # `allowed_teacher`, create a new question to add to category 1, and change the exam name
        put_request_body = {
            "name": "Test exam 2.0",  # changed name
            "draft": False,
            "begin_timestamp": "2021-07-12 09:00:00",
            "end_timestamp": "2021-07-12 10:00:00",
            "allow_going_back": True,
            "randomize_questions": True,
            "randomize_exercises": False,
            "allowed_teachers": [new_allowed_teacher.pk],  # new
            "questions": [
                # deleted first question
                {
                    "id": q2.pk,  # you need to include the id when updating an item
                    "answers": [
                        {
                            "text": "wrong1",
                            "is_right_answer": False,
                        },
                        {
                            "text": "right1",
                            "is_right_answer": True,
                        },
                    ],
                    "text": "multiple choice question 1 in category 1",
                    "question_type": "m",
                    "accepts_multiple_answers": False,
                    "category_uuid": cat3_uuid,
                },
                {
                    "id": q3.pk,
                    "answers": [
                        {
                            "text": "right2",
                            "is_right_answer": True,
                        },
                        {
                            "text": "wrong2",
                            "is_right_answer": False,
                        },
                    ],
                    "text": "question that accepts multiple answers in category 2",
                    "question_type": "m",
                    "accepts_multiple_answers": True,
                    "category": cat2.pk,  # reference the already existing category via pk
                },
                {  # new question - no id
                    "answers": [],
                    "text": "new open question in category 2",
                    "question_type": "o",
                    "accepts_multiple_answers": False,
                    "category": cat2.pk,
                },
            ],
            "exercises": [],
            "categories": [
                {
                    "id": cat1.pk,
                    "introduction_text": "",
                    "amount": 1,
                    "name": "cat1",
                    "item_type": "q",
                    "is_aggregated_question": False,
                    "randomize": True,
                },
                {
                    "id": cat2.pk,
                    "introduction_text": "",
                    "name": "cat2",
                    "item_type": "q",
                    "amount": 1,
                    "is_aggregated_question": False,
                    "randomize": True,
                },
                {  # new category
                    "introduction_text": "cat3 introductory text",
                    "name": "cat3-aggregated_question",
                    "item_type": "q",
                    "amount": 1,
                    "is_aggregated_question": True,
                    "randomize": False,
                    "tmp_uuid": cat3_uuid,
                },
            ],
        }

        response = client.put(f"/exams/{new_exam.pk}/", put_request_body)
        self.assertEquals(response.status_code, 200)
        # todo check new properties like you did with the post request
        # todo particularly, make sure the things you didn't change haven't changed
        pass

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

        self.assertFalse(self.q3a1.is_selected_by(self.student3))  # not yet selected
        GivenAnswer.objects.create(
            user=self.student3, question=self.q3, answer=self.q3a1
        )
        self.assertTrue(self.q3a1.is_selected_by(self.student3))
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

        # if going back is disallowed, trying to call the entry point fails
        self.exam.allow_going_back = False
        self.exam.save()
        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 403)

        self.exam.allow_going_back = True
        self.exam.save()

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

        # battery 3 - student ends their exam and cannot perform any more actions
        client.force_authenticate(user=self.student3)
        response = client.post(f"/exams/{self.exam.pk}/current_item/", {})
        self.assertEqual(response.status_code, 200)
        # give an answer so we can try and withdraw it later
        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q1a1.pk,
            },
        )
        self.assertEqual(response.status_code, 200)

        response = client.post(f"/exams/{self.exam.pk}/end_exam/", {})
        self.assertEqual(response.status_code, 204)

        # from now on, no action should succeed by the user regarding this exam
        response = client.post(f"/exams/{self.exam.pk}/current_item/", {})
        self.assertEqual(response.status_code, 204)
        response = client.post(f"/exams/{self.exam.pk}/previous_item/", {})
        self.assertEqual(response.status_code, 204)
        response = client.post(f"/exams/{self.exam.pk}/next_item/", {})
        self.assertEqual(response.status_code, 204)

        response = client.post(
            f"/exams/{self.exam.pk}/give_answer/",
            {
                "answer": self.q1a2.pk,
            },
        )
        self.assertEqual(response.status_code, 403)
        response = client.post(
            f"/exams/{self.exam.pk}/withdraw_answer/",
            {
                "answer": self.q1a1.pk,
            },
        )
        self.assertEqual(response.status_code, 403)

        # battery 4 - exam gets closed, test that no action can be performed
        client.force_authenticate(user=self.teacher)
        response = client.patch(f"/exams/{self.exam.pk}/terminate/", {})
        self.assertEquals(response.status_code, 200)
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.closed)

        exam_progress = ExamProgress.objects.get(exam=self.exam, user=self.student2)
        curr_cursor_val = exam_progress.current_item_cursor

        client.force_authenticate(user=self.student2)
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


class IntegrityTestCase(TestCase):
    """
    Tests database integrity constraints
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
            text="question2",
            category=cat1,
            accepts_multiple_answers=True,
        )
        self.q3 = Question.objects.create(
            exam=self.exam, text="open_question", category=cat1, question_type="o"
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

    def test_category_integrity(self):
        cat_q = Category.objects.create(
            exam=self.exam, name="cat_q", amount=3, item_type="q", randomize=False
        )

        cat_e = Category.objects.create(
            exam=self.exam, name="cat_e", amount=3, item_type="e", randomize=False
        )

        # trying to add a question to an exercise category
        with self.assertRaises(InvalidCategoryType):
            Question.objects.create(exam=self.exam, text="quest", category=cat_e)

        # trying to add an exercise to a question category
        with self.assertRaises(InvalidCategoryType):
            Exercise.objects.create(exam=self.exam, text="ex", category=cat_q)

        now = timezone.localtime(timezone.now())
        tomorrow = now + timedelta(days=1)
        another_exam = Exam.objects.create(
            name="Test exam", begin_timestamp=now, end_timestamp=tomorrow, draft=False
        )

        another_exam_cat_q = Category.objects.create(
            exam=another_exam, name="cat_q", amount=3, item_type="q", randomize=False
        )

        another_exam_cat_e = Category.objects.create(
            exam=another_exam, name="cat_e", amount=3, item_type="e", randomize=False
        )

        # trying to add an item to a category that belongs to an exam other than
        # that of the item itself
        with self.assertRaises(InvalidCategoryType):
            Question.objects.create(
                exam=self.exam, text="quest", category=another_exam_cat_q
            )
        with self.assertRaises(InvalidCategoryType):
            Exercise.objects.create(
                exam=self.exam, text="ex", category=another_exam_cat_e
            )

    def test_given_answers_integrity(self):
        with self.assertRaises(InvalidAnswerException):
            # `q2a1` does not belong to the answer set of `q1`
            GivenAnswer.objects.create(
                user=self.student1, answer=self.q2a1, question=self.q1
            )

        GivenAnswer.objects.create(
            user=self.student1, answer=self.q1a1, question=self.q1
        )

        with self.assertRaises(TooManyAnswers):
            # question doesn't accept multiple answers, and one has been given already by this user
            GivenAnswer.objects.create(
                user=self.student1, answer=self.q1a2, question=self.q1
            )

        # other students can still answer that question
        GivenAnswer.objects.create(
            user=self.student2, answer=self.q1a1, question=self.q1
        )

        # trying to create two GivenAnswers to a question that accepts multiple answers is fine
        GivenAnswer.objects.create(
            user=self.student1, answer=self.q2a1, question=self.q2
        )
        GivenAnswer.objects.create(
            user=self.student1, answer=self.q2a2, question=self.q2
        )

        # however, you can't create multiple GivenAnswers that reference the same answer
        with transaction.atomic():  # need this to keep django transaction manager from complaining
            with self.assertRaises(IntegrityError):
                GivenAnswer.objects.create(
                    user=self.student1, answer=self.q2a2, question=self.q2
                )

        # open questions only accept one answer per user
        GivenAnswer.objects.create(user=self.student1, text="abc", question=self.q3)
        with self.assertRaises(TooManyAnswers):
            GivenAnswer.objects.create(user=self.student1, text="def", question=self.q3)
