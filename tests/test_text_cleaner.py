"""TextCleaner seam: the clean-text rules on hand-written inputs the samples don't cover."""

import pytest

from docindex.extraction import TextCleaner


@pytest.fixture
def cleaner() -> TextCleaner:
    """A fresh cleaner."""
    return TextCleaner()


@pytest.mark.parametrize("page_number", ["3", "- 3 -", "-3-", "Page 3", "page 3 of 10", "   PAGE 12 OF 40   "])
def test_lines_that_are_only_a_page_number_are_dropped(cleaner: TextCleaner, page_number: str) -> None:
    assert cleaner.clean_pages([f"First line\n{page_number}\nsecond line"]) == "First line second line"


def test_a_number_inside_a_sentence_is_kept(cleaner: TextCleaner) -> None:
    assert cleaner.clean_pages(["Hives need 3\nmetres of space."]) == "Hives need 3 metres of space."


def test_runs_of_blank_lines_collapse_to_one_paragraph_break_and_the_text_is_trimmed(cleaner: TextCleaner) -> None:
    raw_page = "\n\n   First  paragraph,\n\twrapped.   \n\n\n\n\nSecond\t\tparagraph.\n\n\n"

    assert cleaner.clean_pages([raw_page]) == "First paragraph, wrapped.\n\nSecond paragraph."


def test_a_page_boundary_ends_a_paragraph(cleaner: TextCleaner) -> None:
    assert cleaner.clean_pages(["spreads from one", "apiary to the next."]) == (
        "spreads from one\n\napiary to the next."
    )


@pytest.mark.parametrize(
    ("raw_lines", "expected"),
    [
        ("overall pro-\nductivity", "overall productivity"),
        ("the North-\nEast region", "the North- East region"),
        ("a pause -\nthen more", "a pause - then more"),
    ],
    ids=["lowercase-rejoins", "uppercase-keeps-hyphen", "spaced-dash-is-not-a-break"],
)
def test_a_line_end_hyphen_rejoins_only_before_a_lowercase_letter(
    cleaner: TextCleaner, raw_lines: str, expected: str
) -> None:
    assert cleaner.clean_pages([raw_lines]) == expected


def test_nfkc_folds_ligatures_nbsp_and_full_width_forms(cleaner: TextCleaner) -> None:
    raw = "\N{LATIN SMALL LIGATURE FI}nance\N{NO-BREAK SPACE}team \N{FULLWIDTH LATIN CAPITAL LETTER A}\N{FULLWIDTH DIGIT ONE}"

    assert cleaner.clean_pages([raw]) == "finance team A1"


def test_control_and_zero_width_characters_are_removed(cleaner: TextCleaner) -> None:
    raw = "\N{BYTE ORDER MARK}bee\N{ZERO WIDTH SPACE}hive\N{ZERO WIDTH JOINER} keeper\x07s"

    assert cleaner.clean_pages([raw]) == "beehive keepers"


def test_curly_quotes_and_dashes_are_kept(cleaner: TextCleaner) -> None:
    text = "\N{LEFT DOUBLE QUOTATION MARK}Swarms\N{RIGHT DOUBLE QUOTATION MARK} \N{EM DASH} the keeper\N{RIGHT SINGLE QUOTATION MARK}s view"

    assert cleaner.clean_pages([text]) == text


def test_paragraph_soft_breaks_and_tabs_become_one_space_and_empty_paragraphs_vanish(cleaner: TextCleaner) -> None:
    paragraphs = ["Title", "", "  ", "one line\nsoft break", "", "tab\tinside\n\nstill one"]

    assert cleaner.clean_paragraphs(paragraphs) == "Title\n\none line soft break\n\ntab inside still one"
