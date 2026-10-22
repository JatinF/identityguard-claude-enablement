"""Process-local failures. These are not HTTP responses until the API maps them."""


class LabError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
