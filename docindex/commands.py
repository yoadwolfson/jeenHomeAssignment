"""The two entry-script commands: index a document, search the index."""

import argparse
from collections.abc import Callable
from pathlib import Path

from docindex.bootstrap import ServiceFactory
from docindex.cli import ExitCode
from docindex.config import Settings
from docindex.domain import IndexingReport, SearchResult, SplitStrategy

type SettingsLoader = Callable[[], Settings]

RESULT_TEXT_INDENT = "    "


class IndexCommand:
    """`index_documents.py`: index one PDF or DOCX file with one split strategy."""

    def __init__(self, factory: ServiceFactory, load_settings: SettingsLoader = Settings.from_env) -> None:
        self._factory = factory
        self._load_settings = load_settings

    def build_parser(self) -> argparse.ArgumentParser:
        """Return the parser for --file and --strategy."""
        parser = argparse.ArgumentParser(description="Index a PDF or DOCX file for semantic search.")
        parser.add_argument("--file", required=True, type=Path, help="path to a .pdf or .docx file")
        parser.add_argument("--strategy", required=True, choices=[strategy.value for strategy in SplitStrategy])
        return parser

    def run(self, arguments: argparse.Namespace) -> ExitCode:
        """Index the file and print the summary line."""
        service = self._factory.build_indexing_service(self._load_settings())
        report = service.index(arguments.file, SplitStrategy(arguments.strategy))
        print(render_indexing_report(report))
        return ExitCode.SUCCESS


class SearchCommand:
    """`search.py`: print the stored chunks most similar to a query."""

    def __init__(self, factory: ServiceFactory, load_settings: SettingsLoader = Settings.from_env) -> None:
        self._factory = factory
        self._load_settings = load_settings

    def build_parser(self) -> argparse.ArgumentParser:
        """Return the parser for --query."""
        parser = argparse.ArgumentParser(description="Search the indexed documents.")
        parser.add_argument("--query", required=True, type=non_blank_query, help="a natural-language question")
        return parser

    def run(self, arguments: argparse.Namespace) -> ExitCode:
        """Search and print the ranked search results, or a no-results message."""
        service = self._factory.build_search_service(self._load_settings())
        results = service.search(arguments.query)
        print(render_search_results(arguments.query, results, service.top_k))
        return ExitCode.SUCCESS


def non_blank_query(raw_query: str) -> str:
    """Argparse type for --query: reject blank input as a usage error, stripped of surrounding whitespace."""
    query = raw_query.strip()
    # Gemini rejects empty content with a 400, which would wrongly surface as an embedding failure.
    if not query:
        raise argparse.ArgumentTypeError("query must not be empty")
    return query


def render_indexing_report(report: IndexingReport) -> str:
    """Format the one-line indexing summary."""
    return (
        f"Indexed {report.filename} with strategy '{report.strategy}': {report.chunk_count} chunks stored "
        "(replaced previous chunks for this file and strategy, if any)."
    )


def render_search_results(query: str, results: list[SearchResult], top_k: int) -> str:
    """Format search results as numbered blocks with the full, indented chunk text."""
    if not results:
        return f'No results found for "{query}". Index a document first with index_documents.py.'
    blocks = [f'Results for "{query}" (top {top_k}):']
    for rank, result in enumerate(results, start=1):
        indented_text = "\n".join(f"{RESULT_TEXT_INDENT}{line}" for line in result.text.splitlines())
        blocks.append(f"[{rank}] {result.filename} · {result.strategy} · chunk {result.chunk_index}\n{indented_text}")
    return "\n\n".join(blocks)
