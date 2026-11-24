"""CLI seam with the real PostgresChunkRepository: psycopg failures become exit 5 and never leak secrets."""

import logging
from types import TracebackType
from typing import Any

import psycopg
import psycopg.errors
import pytest

from docindex.bootstrap import ServiceFactory
from docindex.cli import ExitCode, run_cli
from docindex.commands import SearchCommand
from docindex.config import Settings
from docindex.storage import PostgresChunkRepository
from docindex.storage.postgres import Connector
from tests.fakes import FakeEmbedder, constant

API_KEY = "AIza-very-secret-api-key"
DB_PASSWORD = "very-secret-db-password"
VALID_URL = f"postgresql://postgres:{DB_PASSWORD}@db.example:5432/docindex"
# No "://": libpq rejects it while parsing, and its message quotes the whole string, password included.
MALFORMED_URL = f"postgresql//postgres:{DB_PASSWORD}@db.example:5432/docindex"
CONNECTION_ERROR_LINE = (
    "Error: Cannot connect to PostgreSQL: check POSTGRES_URL in .env and that the database is running"
)
OPERATION_ERROR_LINE = "Error: Database operation failed; no changes were saved"


class FailingConnection:
    """A psycopg connection stand-in that fails like psycopg does: in a statement, or in the commit."""

    def __init__(self, statement_failure: psycopg.Error | None = None, commit_failure: psycopg.Error | None = None) -> None:
        self._statement_failure = statement_failure
        self._commit_failure = commit_failure
        self.exited_with: BaseException | None = None
        self.closed = False

    def __enter__(self) -> FailingConnection:
        return self

    def __exit__(
        self, _error_type: type[BaseException] | None, error: BaseException | None, _traceback: TracebackType | None
    ) -> None:
        self.exited_with = error
        if error is not None:
            # psycopg rolls back here; on a dropped connection the rollback fails and psycopg logs this warning.
            logging.getLogger("psycopg").warning("error ignored in rollback on <psycopg.Connection [BAD]>")
            return
        if self._commit_failure is not None:
            # psycopg commits here and, when the commit raises, never reaches its own close().
            raise self._commit_failure
        self.closed = True

    def execute(self, *_args: Any) -> None:
        """Run nothing; raise the configured statement failure, if any."""
        if self._statement_failure is not None:
            raise self._statement_failure

    def close(self) -> None:
        """Record that the connection was closed."""
        self.closed = True

    @property
    def info(self) -> Any:
        """Connection details, as psycopg's `ConnectionInfo` exposes them for logging."""
        return type("Info", (), {"host": "db.example", "dbname": "docindex"})()


def connect_to(connection: FailingConnection) -> Connector:
    """A connect function that always returns `connection`."""
    return lambda *_args, **_options: connection


def refuse_connection(_conninfo: str, **_options: Any) -> psycopg.Connection[Any]:
    """A connect function that fails the way libpq does when the server is unreachable."""
    raise psycopg.OperationalError('connection to server at "db.example", port 5432 failed: Connection refused')


def run_search(connect: Connector, postgres_url: str, *extra_args: str) -> tuple[int, FakeEmbedder]:
    """Run search.py against the real repository built with `connect`; return the exit code and the embedder."""
    embedder = FakeEmbedder()
    factory = ServiceFactory(
        embedder_builder=constant(embedder),
        repository_builder=lambda settings: PostgresChunkRepository(settings.postgres_url, connect=connect),
    )
    settings = Settings(gemini_api_key=API_KEY, postgres_url=postgres_url)
    exit_code = run_cli(SearchCommand(factory, constant(settings)), ["--query", "anything", *extra_args])
    return exit_code, embedder


def test_a_refused_connection_exits_5_before_the_query_is_embedded(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code, embedder = run_search(refuse_connection, VALID_URL)

    assert exit_code == ExitCode.DATABASE == 5
    assert capsys.readouterr().err == f"{CONNECTION_ERROR_LINE}\n"
    assert embedder.embedded_texts == []


def test_a_malformed_url_exits_5_without_echoing_the_password_even_under_verbose(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, _embedder = run_search(psycopg.connect, MALFORMED_URL, "--verbose")

    captured = capsys.readouterr()
    assert exit_code == ExitCode.DATABASE == 5
    assert captured.err.splitlines()[-1] == CONNECTION_ERROR_LINE
    assert DB_PASSWORD not in captured.out + captured.err


def test_a_failed_statement_exits_5_with_one_error_line_and_leaves_through_the_rollback_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = psycopg.errors.InsufficientPrivilege("permission denied to create extension")
    connection = FailingConnection(statement_failure=failure)

    exit_code, embedder = run_search(connect_to(connection), VALID_URL)

    assert exit_code == ExitCode.DATABASE == 5
    # Exactly one line: psycopg's own rollback warning is kept for --verbose.
    assert capsys.readouterr().err == f"{OPERATION_ERROR_LINE}\n"
    assert connection.exited_with is failure
    assert connection.closed
    assert embedder.embedded_texts == []


def test_a_failed_commit_exits_5_and_still_closes_the_connection(capsys: pytest.CaptureFixture[str]) -> None:
    connection = FailingConnection(commit_failure=psycopg.OperationalError("server closed the connection unexpectedly"))

    exit_code, embedder = run_search(connect_to(connection), VALID_URL)

    assert exit_code == ExitCode.DATABASE == 5
    assert capsys.readouterr().err == f"{OPERATION_ERROR_LINE}\n"
    assert connection.closed
    assert embedder.embedded_texts == []
