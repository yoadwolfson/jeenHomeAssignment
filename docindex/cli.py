"""Shared CLI runner: argument parsing, logging setup, error messages and exit codes."""

import argparse
import io
import logging
import sys
from collections.abc import Sequence
from enum import IntEnum
from typing import Protocol

from docindex.errors import ConfigurationError, DocIndexError, DocumentError

# google-genai 3.6.1 logs through httpx2, a fork of httpx.
QUIET_LOGGERS = ("httpx", "httpx2", "google_genai")
# pypdf logs a WARNING (e.g. "invalid pdf header") before failing on a bad file; our one Error line already says it.
VERBOSE_ONLY_LOGGERS = ("pypdf",)
OUTPUT_ENCODING = "utf-8"
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
UNEXPECTED_FAILURE_MESSAGE = "unexpected failure (run with --verbose for details)"
INTERRUPTED_MESSAGE = "Interrupted."

logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    """Process exit codes, one per failure category."""

    SUCCESS = 0
    UNEXPECTED = 1
    USAGE = 2
    DOCUMENT = 3
    EMBEDDING = 4
    DATABASE = 5
    INTERRUPTED = 130


# Looked up along the exception's MRO, so a subclass inherits its category's code.
EXIT_CODES_BY_ERROR: dict[type[DocIndexError], ExitCode] = {
    ConfigurationError: ExitCode.USAGE,
    DocumentError: ExitCode.DOCUMENT,
}


class CliCommand(Protocol):
    """One entry script: its arguments and the single service call it makes."""

    def build_parser(self) -> argparse.ArgumentParser:
        """Return the parser for this command's arguments."""
        ...

    def run(self, arguments: argparse.Namespace) -> ExitCode:
        """Execute the command, printing its output to stdout."""
        ...


def run_cli(command: CliCommand, argv: Sequence[str] | None = None) -> int:
    """Run `command`, turning every failure into one stderr line and an exit code."""
    use_utf8_output()
    parser = command.build_parser()
    parser.add_argument("--verbose", action="store_true", help="DEBUG logging and tracebacks on errors")
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exit_request:
        return _exit_status(exit_request)
    configure_logging(verbose=arguments.verbose)
    try:
        return command.run(arguments)
    except KeyboardInterrupt:
        print(INTERRUPTED_MESSAGE, file=sys.stderr)
        return ExitCode.INTERRUPTED
    except DocIndexError as error:
        logger.debug("Failure details", exc_info=True)
        print(f"Error: {error.message}", file=sys.stderr)
        return exit_code_for(error)
    except Exception:
        logger.debug("Failure details", exc_info=True)
        print(f"Error: {UNEXPECTED_FAILURE_MESSAGE}", file=sys.stderr)
        return ExitCode.UNEXPECTED


def exit_code_for(error: DocIndexError) -> ExitCode:
    """Return the exit code for an expected failure's category."""
    for error_type in type(error).__mro__:
        if error_type in EXIT_CODES_BY_ERROR:
            return EXIT_CODES_BY_ERROR[error_type]
    return ExitCode.UNEXPECTED


def use_utf8_output() -> None:
    """Write stdout and stderr as UTF-8 so chunk text never fails to print."""
    # Piped output on Windows defaults to cp1252, which cannot encode many characters found in documents.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding=OUTPUT_ENCODING)


def configure_logging(verbose: bool) -> None:
    """Send logs to stderr at INFO, or DEBUG when verbose; keep HTTP client and parser loggers quiet."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format=LOG_FORMAT, stream=sys.stderr, force=True)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in VERBOSE_ONLY_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET if verbose else logging.ERROR)


def _exit_status(exit_request: SystemExit) -> int:
    # argparse exits 2 on bad usage and 0 for --help.
    return exit_request.code if isinstance(exit_request.code, int) else ExitCode.USAGE
