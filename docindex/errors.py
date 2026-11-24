"""Exceptions that carry a user-facing message."""


class DocIndexError(Exception):
    """Base for every expected failure; `message` is safe to show the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(DocIndexError):
    """A required environment variable is missing."""

    def __init__(self, variable_name: str) -> None:
        super().__init__(f"Missing environment variable {variable_name}: copy .env.example to .env and fill it in")
        self.variable_name = variable_name
