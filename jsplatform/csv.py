import csv
import re
from io import BytesIO, StringIO

from jsplatform.models import Submission


def preprocess_html_for_csv(html):
    """
    Redacts the base64 data for <img> tags and removes unwanted html <p> tags
    """
    ret = re.sub(r'src="([^"]+)"', "", html)
    ret = re.sub(r"<[^>]*/?p[^>]*>", "", ret)

    return ret


def get_header_row(exam):
    headers = ["Corso", "Email"]

    question_count, exercise_count = exam.get_number_of_items_per_exam(as_tuple=True)

    for i in range(0, question_count):
        headers.append(f"Domanda { i+1 } testo")
        headers.append(f"Domanda { i+1 } risposta data")
        headers.append(f"Domanda { i+1 } risposta corretta")
        # headers.append(f"Domanda { i+1 } orario visualizzazione")
        # headers.append(f"Domanda { i+1 } orario risposta")

    for i in range(0, exercise_count):
        headers.append(f"Esercizio JS { i+1 } testo")
        headers.append(f"Esercizio JS { i+1 } sottomissione")
        # headers.append(f"Esercizio JS { i+1 } orario visualizzazione")
        # headers.append(f"Esercizio JS { i+1 } orario consegna")
        headers.append(f"Esercizio JS { i+1 } testcase superati")
        headers.append(f"Esercizio JS { i+1 } testcase falliti")

    return headers


def build_user_row(participation):
    user = participation.user
    row = [user.course, user.email]

    progress = participation.get_progress_as_dict(for_csv=True)

    for question in progress["questions"]:
        row.append(question["text"])

        if question["type"] == "o":  # open question
            row.append(question["answer_text"])
            row.append("-")
        else:  # multiple-choice question
            given_answers = [a for a in question["answers"] if a["selected"]]
            if len(given_answers) == 0:
                row.append("-")
                row.append("false")
            else:
                # write all given answers' texts joined by '\n' into a single string
                row.append(
                    "\n".join(
                        [a["text"] for a in given_answers],
                    )
                )
                # for each given answer, write "true" or "false" depending on whether
                # it's a correct answer
                row.append(
                    "\n".join(
                        [
                            "true" if a["is_right_answer"] else "false"
                            for a in given_answers
                        ]
                    )
                )

    for exercise in progress["exercises"]:
        row.append(exercise["text"])
        try:
            # todo in get_progress_as_dict, to be consistent with questions you'll probably have submission as a key, hence no query needed
            submission = Submission.objects.get(
                exercise__pk=exercise["id"], user=user, has_been_turned_in=True
            )
        except Submission.DoesNotExist:
            submission = Submission()

        row.append(submission.code)
        row.append(submission.get_passed_testcases())
        row.append(submission.get_failed_testcases())

    return row


def get_csv_from_exam(exam):
    participations = exam.participations.all()

    buffer = StringIO()
    writer = csv.writer(buffer)

    writer.writerow(get_header_row(exam))

    for participation in participations:
        writer.writerow(build_user_row(participation))

    return buffer.getvalue()
