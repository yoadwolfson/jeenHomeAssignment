"""CLI seam: the real pipeline around a fake Embedder and a fake ChunkRepository."""

from collections.abc import Callable
from pathlib import Path

import pytest

from docindex.bootstrap import ServiceFactory
from docindex.cli import ExitCode, run_cli
from docindex.commands import IndexCommand, SearchCommand
from docindex.config import Settings
from docindex.domain import MAX_CHUNK_CHARS, ChunkRecord, SplitStrategy
from docindex.errors import (
    DatabaseConnectionError,
    DatabaseOperationError,
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingQuotaError,
    EmbeddingServiceError,
)
from tests.fakes import FakeChunkRepository, FakeEmbedder, bag_of_letters_vector, constant

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
DOCX_SAMPLE = SAMPLES_DIR / "remote_work_policy.docx"
DOCX_NAME = DOCX_SAMPLE.name
PDF_SAMPLE = SAMPLES_DIR / "urban_beekeeping.pdf"
PDF_PARAGRAPH_COUNT = 11
TEST_API_KEY = "AIza-test-secret-api-key"
TEST_DB_PASSWORD = "test-secret-db-password"
TEST_SETTINGS = Settings(
    gemini_api_key=TEST_API_KEY, postgres_url=f"postgresql://user:{TEST_DB_PASSWORD}@localhost:5432/test"
)
CONNECTION_ERROR_LINE = (
    "Error: Cannot connect to PostgreSQL: check POSTGRES_URL in .env and that the database is running"
)
OPERATION_ERROR_LINE = "Error: Database operation failed; no changes were saved"


class App:
    """Runs both CLI commands against shared fakes."""

    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        self.repository = FakeChunkRepository()
        self.factory = ServiceFactory(
            embedder_builder=constant(self.embedder), repository_builder=constant(self.repository)
        )

    def index(self, *args: str) -> int:
        """Run index_documents.py with `args` and return its exit code."""
        return run_cli(IndexCommand(self.factory, constant(TEST_SETTINGS)), list(args))

    def index_docx(self, strategy: str = "paragraph") -> int:
        """Index the DOCX sample with `strategy`."""
        return self.index("--file", str(DOCX_SAMPLE), "--strategy", strategy)

    def search(self, *args: str) -> int:
        """Run search.py with `args` and return its exit code."""
        return run_cli(SearchCommand(self.factory, constant(TEST_SETTINGS)), list(args))


@pytest.fixture
def app() -> App:
    """A fresh App with empty fakes."""
    return App()


def test_indexing_a_docx_by_paragraph_stores_its_chunks_and_prints_a_summary(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = app.index_docx()

    stored = app.repository.records_for(DOCX_NAME, SplitStrategy.paragraph)
    assert exit_code == ExitCode.SUCCESS
    assert len(stored) > 1
    assert [record.chunk_index for record in stored] == list(range(len(stored)))
    assert stored[0].text == "Remote Work Policy"
    assert capsys.readouterr().out == (
        f"Indexed {DOCX_NAME} with strategy 'paragraph': {len(stored)} chunks stored "
        "(replaced previous chunks for this file and strategy, if any).\n"
    )


def test_indexing_a_pdf_with_an_upper_case_extension_stores_one_chunk_per_paragraph(
    app: App, tmp_path: Path
) -> None:
    upper_case_copy = tmp_path / "URBAN_BEEKEEPING.PDF"
    upper_case_copy.write_bytes(PDF_SAMPLE.read_bytes())

    exit_code = app.index("--file", str(upper_case_copy), "--strategy", "paragraph")

    stored = app.repository.records_for(upper_case_copy.name, SplitStrategy.paragraph)
    assert exit_code == ExitCode.SUCCESS
    assert stored[0].text == "Urban Beekeeping: A Short Field Guide"
    assert len(stored) == PDF_PARAGRAPH_COUNT


def test_search_prints_ranked_results_in_the_contract_format(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.repository.replace_chunks(
        "notes.docx",
        SplitStrategy.paragraph,
        [
            ChunkRecord("notes.docx", SplitStrategy.paragraph, 0, "zzz qqq", bag_of_letters_vector("zzz qqq")),
            ChunkRecord("notes.docx", SplitStrategy.paragraph, 1, "laptop\nmonitor", bag_of_letters_vector("laptop monitor")),
        ],
    )

    exit_code = app.search("--query", "laptop monitor")

    assert exit_code == ExitCode.SUCCESS
    assert capsys.readouterr().out == (
        'Results for "laptop monitor" (top 5):\n'
        "\n"
        "[1] notes.docx · paragraph · chunk 1\n"
        "    laptop\n"
        "    monitor\n"
        "\n"
        "[2] notes.docx · paragraph · chunk 0\n"
        "    zzz qqq\n"
    )
    assert app.repository.schema_ensured


def test_searching_an_empty_index_prints_the_no_results_message_and_exits_0(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = app.search("--query", "anything at all")

    assert exit_code == ExitCode.SUCCESS
    assert capsys.readouterr().out == (
        'No results found for "anything at all". Index a document first with index_documents.py.\n'
    )


def test_reindexing_the_same_file_and_strategy_replaces_its_chunks(app: App) -> None:
    stale_set = [
        ChunkRecord(DOCX_NAME, SplitStrategy.paragraph, index, f"stale chunk {index}", bag_of_letters_vector("x"))
        for index in range(20)
    ]
    app.repository.replace_chunks(DOCX_NAME, SplitStrategy.paragraph, stale_set)

    exit_code = app.index_docx()

    stored = app.repository.records_for(DOCX_NAME, SplitStrategy.paragraph)
    assert exit_code == ExitCode.SUCCESS
    assert not any(record.text.startswith("stale chunk") for record in stored)
    assert [record.chunk_index for record in stored] == list(range(len(stored)))
    assert len(stored) < len(stale_set)


def test_indexing_with_another_strategy_keeps_the_existing_set_side_by_side(app: App) -> None:
    fixed_set = [ChunkRecord(DOCX_NAME, SplitStrategy.fixed, 0, "earlier fixed chunk", bag_of_letters_vector("x"))]
    app.repository.replace_chunks(DOCX_NAME, SplitStrategy.fixed, fixed_set)

    app.index_docx("paragraph")

    assert app.repository.records_for(DOCX_NAME, SplitStrategy.fixed) == fixed_set
    assert app.repository.records_for(DOCX_NAME, SplitStrategy.paragraph)


def test_indexing_a_pdf_with_fixed_stores_bounded_chunks_beside_the_paragraph_set(app: App) -> None:
    app.index("--file", str(PDF_SAMPLE), "--strategy", "paragraph")

    exit_code = app.index("--file", str(PDF_SAMPLE), "--strategy", "fixed")

    fixed_set = app.repository.records_for(PDF_SAMPLE.name, SplitStrategy.fixed)
    assert exit_code == ExitCode.SUCCESS
    assert len(fixed_set) > 1
    assert all(len(record.text) <= MAX_CHUNK_CHARS for record in fixed_set)
    assert [record.chunk_index for record in fixed_set] == list(range(len(fixed_set)))
    # Positional, not structural: the first chunk runs past the title into the next paragraph.
    assert fixed_set[0].text.startswith("Urban Beekeeping: A Short Field Guide\n\n")
    assert len(app.repository.records_for(PDF_SAMPLE.name, SplitStrategy.paragraph)) == PDF_PARAGRAPH_COUNT


@pytest.mark.parametrize("strategy", list(SplitStrategy))
def test_every_split_strategy_indexes_the_docx(app: App, strategy: SplitStrategy) -> None:
    exit_code = app.index_docx(strategy.value)

    assert exit_code == ExitCode.SUCCESS
    assert app.repository.records_for(DOCX_NAME, strategy)


def test_indexing_a_pdf_with_sentence_packs_whole_sentences_up_to_the_maximum(app: App) -> None:
    exit_code = app.index("--file", str(PDF_SAMPLE), "--strategy", "sentence")

    sentence_set = app.repository.records_for(PDF_SAMPLE.name, SplitStrategy.sentence)
    assert exit_code == ExitCode.SUCCESS
    assert 1 < len(sentence_set) < PDF_PARAGRAPH_COUNT
    assert all(len(record.text) <= MAX_CHUNK_CHARS for record in sentence_set)
    assert [record.chunk_index for record in sentence_set] == list(range(len(sentence_set)))
    # Packed across paragraphs: the title shares the first chunk with the sentences that follow it.
    assert sentence_set[0].text.startswith("Urban Beekeeping: A Short Field Guide ")
    assert all(record.text.endswith((".", "!", "?")) for record in sentence_set)


def test_an_unexpected_exception_prints_a_generic_message_and_exits_1(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.embedder.failure = RuntimeError("boom: internal detail")

    exit_code = app.index_docx()

    captured = capsys.readouterr()
    assert exit_code == ExitCode.UNEXPECTED == 1
    assert captured.err.splitlines()[-1] == "Error: unexpected failure (run with --verbose for details)"
    assert "Traceback" not in captured.err
    assert "internal detail" not in captured.err


def test_verbose_adds_the_traceback_and_the_underlying_error_text(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.embedder.failure = RuntimeError("boom: internal detail")

    exit_code = app.index("--file", str(DOCX_SAMPLE), "--strategy", "paragraph", "--verbose")

    captured = capsys.readouterr()
    assert exit_code == ExitCode.UNEXPECTED
    assert "Traceback" in captured.err
    assert "internal detail" in captured.err


@pytest.mark.parametrize(
    "arguments",
    [
        ("--file", str(DOCX_SAMPLE), "--strategy", "chapter"),
        ("--file", str(DOCX_SAMPLE)),
    ],
    ids=["unknown-strategy", "missing-strategy"],
)
def test_argparse_rejects_a_bad_strategy_with_exit_2(app: App, arguments: tuple[str, ...]) -> None:
    exit_code = app.index(*arguments)

    assert exit_code == ExitCode.USAGE == 2
    assert app.embedder.embedded_texts == []


@pytest.mark.parametrize(
    ("environ", "missing_variable"),
    [
        ({"GEMINI_API_KEY": "test-key"}, "POSTGRES_URL"),
        ({"POSTGRES_URL": "postgresql://localhost/test"}, "GEMINI_API_KEY"),
    ],
    ids=["no-postgres-url", "no-api-key"],
)
def test_a_missing_environment_variable_names_it_and_exits_2_before_any_service_runs(
    app: App, capsys: pytest.CaptureFixture[str], tmp_path: Path, environ: dict[str, str], missing_variable: str
) -> None:
    def load_settings() -> Settings:
        return Settings.from_env(env_file=tmp_path / "absent.env", environ=environ)

    exit_code = run_cli(IndexCommand(app.factory, load_settings), ["--file", str(DOCX_SAMPLE), "--strategy", "fixed"])

    assert exit_code == ExitCode.USAGE == 2
    assert capsys.readouterr().err == (
        f"Error: Missing environment variable {missing_variable}: copy .env.example to .env and fill it in\n"
    )
    assert app.embedder.embedded_texts == []
    assert not app.repository.schema_ensured


def test_ctrl_c_prints_interrupted_and_exits_130(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.embedder.failure = KeyboardInterrupt()

    exit_code = app.search("--query", "anything")

    assert exit_code == ExitCode.INTERRUPTED == 130
    assert capsys.readouterr().err.splitlines()[-1] == "Interrupted."


def _corrupt_pdf(directory: Path) -> Path:
    path = directory / "corrupt.pdf"
    # No PDF header, so pypdf also logs its own "invalid pdf header" warning, which must not reach stderr.
    path.write_bytes(b"this is not a pdf at all")
    return path


def _text_file(directory: Path) -> Path:
    path = directory / "notes.txt"
    path.write_text("Plain text is not a supported format.", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("make_document", "expected_error"),
    [
        (lambda directory: directory / "missing.docx", "File not found: {path}"),
        (lambda directory: directory, "File not found: {path}"),
        (_text_file, "Unsupported file type '.txt': only .pdf and .docx are supported"),
        (_corrupt_pdf, "Could not read corrupt.pdf: the file is corrupt, password-protected, or not a real PDF/DOCX"),
        (
            lambda _directory: SAMPLES_DIR / "scanned_no_text.pdf",
            "No extractable text in scanned_no_text.pdf (it may be a scanned image; OCR is not supported)",
        ),
        (lambda _directory: SAMPLES_DIR / "empty.docx", "No extractable text in empty.docx"),
    ],
    ids=["missing-file", "directory", "unsupported-type", "unreadable", "scanned-pdf", "empty-docx"],
)
def test_a_document_error_prints_one_error_line_exits_3_and_never_reaches_gemini_or_the_database(
    app: App,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    make_document: Callable[[Path], Path],
    expected_error: str,
) -> None:
    path = make_document(tmp_path)

    exit_code = app.index("--file", str(path), "--strategy", "paragraph")

    assert exit_code == ExitCode.DOCUMENT == 3
    assert capsys.readouterr().err == f"Error: {expected_error.format(path=path)}\n"
    assert app.embedder.embedded_texts == []
    assert not app.repository.schema_ensured
    assert app.repository.chunk_sets == {}


@pytest.mark.parametrize(
    "failure",
    [EmbeddingAuthError(), EmbeddingQuotaError(), EmbeddingServiceError("503")],
    ids=["auth", "quota", "service"],
)
def test_an_embedding_error_prints_its_message_exits_4_and_leaves_stored_chunks_untouched(
    app: App, capsys: pytest.CaptureFixture[str], failure: EmbeddingError
) -> None:
    earlier_set = [ChunkRecord(DOCX_NAME, SplitStrategy.paragraph, 0, "earlier chunk", bag_of_letters_vector("x"))]
    app.repository.replace_chunks(DOCX_NAME, SplitStrategy.paragraph, earlier_set)
    app.embedder.failure = failure

    exit_code = app.index_docx()

    assert exit_code == ExitCode.EMBEDDING == 4
    assert capsys.readouterr().err.splitlines()[-1] == f"Error: {failure.message}"
    assert app.repository.chunk_sets == {(DOCX_NAME, SplitStrategy.paragraph): earlier_set}


def test_an_embedding_error_shows_its_cause_only_under_verbose(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    failure = EmbeddingServiceError("500")
    failure.__cause__ = RuntimeError("500 INTERNAL. secret upstream detail")
    app.embedder.failure = failure

    quiet_exit = app.search("--query", "anything")
    quiet_err = capsys.readouterr().err
    verbose_exit = app.search("--query", "anything", "--verbose")
    verbose_err = capsys.readouterr().err

    assert quiet_exit == verbose_exit == ExitCode.EMBEDDING
    assert "secret upstream detail" not in quiet_err
    assert "secret upstream detail" in verbose_err


@pytest.mark.parametrize(
    "run_script",
    [App.index_docx, lambda app: app.search("--query", "anything")],
    ids=["index", "search"],
)
def test_an_unreachable_database_exits_5_before_anything_is_embedded(
    app: App, capsys: pytest.CaptureFixture[str], run_script: Callable[[App], int]
) -> None:
    app.repository.connection_failure = DatabaseConnectionError()

    exit_code = run_script(app)

    assert exit_code == ExitCode.DATABASE == 5
    assert capsys.readouterr().err.splitlines()[-1] == CONNECTION_ERROR_LINE
    assert app.embedder.embedded_texts == []


def test_a_failed_write_exits_5_and_keeps_the_earlier_chunks(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    earlier_set = [ChunkRecord(DOCX_NAME, SplitStrategy.paragraph, 0, "earlier chunk", bag_of_letters_vector("x"))]
    app.repository.replace_chunks(DOCX_NAME, SplitStrategy.paragraph, earlier_set)
    app.repository.write_failure = DatabaseOperationError()

    exit_code = app.index_docx()

    assert exit_code == ExitCode.DATABASE == 5
    assert capsys.readouterr().err.splitlines()[-1] == OPERATION_ERROR_LINE
    assert app.repository.chunk_sets == {(DOCX_NAME, SplitStrategy.paragraph): earlier_set}


def _fail_to_connect(app: App) -> None:
    app.repository.connection_failure = DatabaseConnectionError()


def _fail_the_write(app: App) -> None:
    app.repository.write_failure = DatabaseOperationError()


def _fail_the_embedding(app: App) -> None:
    app.embedder.failure = EmbeddingAuthError()


def _crash_unexpectedly(app: App) -> None:
    app.embedder.failure = RuntimeError("internal bug")


def _break_nothing(_app: App) -> None:
    pass


@pytest.mark.parametrize(
    ("break_something", "index_exit", "search_exit"),
    [
        (_break_nothing, ExitCode.SUCCESS, ExitCode.SUCCESS),
        (_fail_to_connect, ExitCode.DATABASE, ExitCode.DATABASE),
        # Search never writes, so a failing write only breaks indexing.
        (_fail_the_write, ExitCode.DATABASE, ExitCode.SUCCESS),
        (_fail_the_embedding, ExitCode.EMBEDDING, ExitCode.EMBEDDING),
        (_crash_unexpectedly, ExitCode.UNEXPECTED, ExitCode.UNEXPECTED),
    ],
    ids=["success", "connection-failure", "write-failure", "embedding-failure", "unexpected-failure"],
)
def test_a_verbose_run_of_either_script_never_prints_the_api_key_or_the_database_password(
    app: App,
    capsys: pytest.CaptureFixture[str],
    break_something: Callable[[App], None],
    index_exit: ExitCode,
    search_exit: ExitCode,
) -> None:
    break_something(app)

    exit_codes = (
        app.index("--file", str(DOCX_SAMPLE), "--strategy", "paragraph", "--verbose"),
        app.search("--query", "laptop", "--verbose"),
    )

    captured = capsys.readouterr()
    assert exit_codes == (index_exit, search_exit)
    for secret in (TEST_API_KEY, TEST_DB_PASSWORD):
        assert secret not in captured.out
        assert secret not in captured.err
