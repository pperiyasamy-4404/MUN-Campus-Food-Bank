"""Problems the person can fix, with a message in words they can read.

Any code can raise one. main.py turns it into an answer with the right status,
like 409 and {"detail": "There's already an item called Pasta."}.
"""


class Problem(Exception):
    """Something the person can fix. The message is shown to them as it is."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(Problem):
    status_code = 404


class NameTaken(Problem):
    status_code = 409
