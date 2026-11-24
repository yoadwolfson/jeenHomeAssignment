"""The clean-text rules shared by every extractor."""

import re
import unicodedata
from collections.abc import Iterable, Iterator
from typing import Final, Literal

from docindex.domain import PARAGRAPH_SEPARATOR

LINE_BREAK = "\n"
LINE_END_HYPHEN = "-"
# Compatibility composition folds ligatures, NBSP and full-width forms, while keeping curly quotes and dashes.
UNICODE_FORM: Final[Literal["NFKC"]] = "NFKC"
# pypdf pads page numbers with spaces, so this is matched against the stripped line.
PAGE_NUMBER_LINE = re.compile(r"-\s*\d+\s*-|(?:page\s+)?\d+(?:\s+of\s+\d+)?", re.IGNORECASE)
# The line break is excluded because it is what separates lines and paragraphs.
INLINE_WHITESPACE = re.compile(r"[^\S\n]+")
ANY_WHITESPACE = re.compile(r"\s+")
CARRIAGE_RETURN = re.compile(r"\r\n?")
# Cf covers the zero-width characters (spaces, joiners, BOM) along with the Cc control characters.
REMOVED_CATEGORIES = frozenset({"Cc", "Cf"})
# A tab is a word separator: removing it would glue words together, so it is collapsed to a space later instead.
KEPT_CONTROLS = frozenset({LINE_BREAK, "\t"})


class TextCleaner:
    """Turns raw extracted text into clean text: paragraphs separated by exactly one blank line."""

    def clean_pages(self, pages: Iterable[str]) -> str:
        """Clean line-oriented page texts; blank lines and page boundaries end a paragraph."""
        return self._clean_blocks(pages)

    def clean_paragraphs(self, paragraphs: Iterable[str]) -> str:
        """Clean one text per paragraph; line breaks and tabs inside a paragraph are only whitespace."""
        return self._clean_blocks(ANY_WHITESPACE.sub(" ", paragraph) for paragraph in paragraphs)

    def _clean_blocks(self, raw_blocks: Iterable[str]) -> str:
        # A block boundary (page or paragraph) always ends a paragraph.
        return PARAGRAPH_SEPARATOR.join(
            paragraph for raw_block in raw_blocks for paragraph in self._paragraphs_of(raw_block)
        )

    def _paragraphs_of(self, raw_block: str) -> Iterator[str]:
        current_lines: list[str] = []
        for line in _normalise_unicode(raw_block).split(LINE_BREAK):
            stripped = INLINE_WHITESPACE.sub(" ", line).strip()
            if PAGE_NUMBER_LINE.fullmatch(stripped):
                continue
            if stripped:
                current_lines.append(stripped)
                continue
            if current_lines:
                yield _join_wrapped_lines(current_lines)
            current_lines = []
        if current_lines:
            yield _join_wrapped_lines(current_lines)


def _normalise_unicode(text: str) -> str:
    normalised = unicodedata.normalize(UNICODE_FORM, CARRIAGE_RETURN.sub(LINE_BREAK, text))
    return "".join(
        character
        for character in normalised
        if character in KEPT_CONTROLS or unicodedata.category(character) not in REMOVED_CATEGORIES
    )


def _join_wrapped_lines(lines: list[str]) -> str:
    joined = lines[0]
    for line in lines[1:]:
        if _is_broken_word(joined, line):
            joined = joined.removesuffix(LINE_END_HYPHEN) + line
        else:
            joined = f"{joined} {line}"
    return joined


def _is_broken_word(previous: str, following: str) -> bool:
    # A letter before the hyphen keeps a spaced dash ("word -") from gluing two words together.
    return previous.endswith(LINE_END_HYPHEN) and previous[:-1][-1:].isalpha() and following[0].islower()
