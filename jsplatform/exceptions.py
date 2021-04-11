class SubmissionAlreadyTurnedIn(Exception):
    pass


class NotEligibleForTurningIn(Exception):
    pass


class InvalidAnswerException(Exception):
    pass


class ExamNotOverYet(Exception):
    pass


class OutOfCategories(Exception):
    pass


class InvalidCategoryType(Exception):
    pass
