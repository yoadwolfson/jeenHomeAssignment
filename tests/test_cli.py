"""CLI seam: the real pipeline around a fake Embedder and a fake ChunkRepository."""

from pathlib import Path

import pytest

from docindex.bootstrap import ServiceFactory
from docindex.cli import ExitCode, run_cli
from docindex.commands import IndexCommand, SearchCommand
from docindex.config import Settings
from docindex.domain import MAX_CHUNK_CHARS, ChunkRecord, SplitStrategy
from docindex.errors import ConfigurationError
from tests.fakes import FakeChunkRepository, FakeEmbedder, bag_of_letters_vector, constant

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
DOCX_SAMPLE = SAMPLES_DIR / "remote_work_policy.docx"
DOCX_NAME = DOCX_SAMPLE.name
PDF_SAMPLE = SAMPLES_DIR / "urban_beekeeping.pdf"
PDF_PARAGRAPH_COUNT = 11
TEST_SETTINGS = Settings(gemini_api_key="test-key", postgres_url="postgresql://user:pw@localhost:5432/test")


class App:
    """Runs both CLI commands against shared fakes."""

    def __init__(self) -> None:
        self.embedder = FakeEmbedder()
        self.repository = FakeChunkRepository()
        self._factory = ServiceFactory(
            embedder_builder=constant(self.embedder), repository_builder=constant(self.repository)
        )

    def index(self, *args: str) -> int:
        """Run index_documents.py with `args` and return its exit code."""
        return run_cli(IndexCommand(self._factory, constant(TEST_SETTINGS)), list(args))

    def index_docx(self, strategy: str = "paragraph") -> int:
        """Index the DOCX sample with `strategy`."""
        return self.index("--file", str(DOCX_SAMPLE), "--strategy", strategy)

    def search(self, *args: str) -> int:
        """Run search.py with `args` and return its exit code."""
        return run_cli(SearchCommand(self._factory, constant(TEST_SETTINGS)), list(args))


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


def test_a_configuration_error_prints_its_message_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    def missing_settings() -> Settings:
        raise ConfigurationError("POSTGRES_URL")

    exit_code = run_cli(SearchCommand(ServiceFactory(), missing_settings), ["--query", "anything"])

    assert exit_code == ExitCode.USAGE
    assert capsys.readouterr().err.splitlines()[-1] == (
        "Error: Missing environment variable POSTGRES_URL: copy .env.example to .env and fill it in"
    )


def test_ctrl_c_prints_interrupted_and_exits_130(app: App, capsys: pytest.CaptureFixture[str]) -> None:
    app.embedder.failure = KeyboardInterrupt()

    exit_code = app.search("--query", "anything")

    assert exit_code == ExitCode.INTERRUPTED == 130
    assert capsys.readouterr().err.splitlines()[-1] == "Interrupted."
