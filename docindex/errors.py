"""Exceptions that carry a user-facing message."""

from collections.abc import Sequence
from pathlib import Path


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


class DocumentError(DocIndexError):
    """The input document cannot be indexed."""


class NoExtractableTextError(DocumentError):
    """A readable document whose clean text has no letters or digits."""

    def __init__(self, filename: str, may_be_scanned: bool) -> None:
        hint = " (it may be a scanned image; OCR is not supported)" if may_be_scanned else ""
        super().__init__(f"No extractable text in {filename}{hint}")
        self.filename = filename
        self.may_be_scanned = may_be_scanned


class UnreadableDocumentError(DocumentError):
    """A file with a supported extension that the PDF or DOCX library cannot open or parse."""

    def __init__(self, filename: str) -> None:
        super().__init__(
            f"Could not read {filename}: the file is corrupt, password-protected, or not a real PDF/DOCX"
        )
        self.filename = filename


class MissingFileError(DocumentError):
    """The document path does not exist or is not a regular file."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"File not found: {path}")
        self.path = path


class UnsupportedFileTypeError(DocumentError):
    """The document's extension has no registered extractor."""

    def __init__(self, extension: str, supported_extensions: Sequence[str]) -> None:
        super().__init__(
            f"Unsupported file type '{extension}': only {' and '.join(supported_extensions)} are supported"
        )
        self.extension = extension
        self.supported_extensions = tuple(supported_extensions)
