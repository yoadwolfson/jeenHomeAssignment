"""TextExtractor seam: the real extractors on the committed samples."""

from pathlib import Path

import pytest
from docx import Document

from docindex.domain import PARAGRAPH_SEPARATOR
from docindex.extraction import DocxExtractor, ExtractorRegistry, PdfExtractor, TextCleaner

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
PDF_SAMPLE = SAMPLES_DIR / "urban_beekeeping.pdf"
DOCX_SAMPLE = SAMPLES_DIR / "remote_work_policy.docx"


@pytest.fixture(scope="module")
def pdf_paragraphs() -> list[str]:
    """The beekeeping PDF's clean text, split into paragraphs."""
    return PdfExtractor(TextCleaner()).extract(PDF_SAMPLE).split(PARAGRAPH_SEPARATOR)


@pytest.fixture(scope="module")
def docx_text() -> str:
    """The remote-work DOCX's clean text."""
    return DocxExtractor(TextCleaner()).extract(DOCX_SAMPLE)


def test_pdf_paragraph_gaps_become_blank_lines_and_wrapped_lines_join_with_a_space(
    pdf_paragraphs: list[str],
) -> None:
    assert pdf_paragraphs[0] == "Urban Beekeeping: A Short Field Guide"
    assert pdf_paragraphs[1] == (
        "Keeping honey bees in a city is easier than most people expect. A single hive needs about one "
        "square metre of ground, a water source within a few hundred metres, and a neighbour who does "
        "not mind the occasional visitor on a flowering shrub."
    )


def test_pdf_footer_page_numbers_are_dropped(pdf_paragraphs: list[str]) -> None:
    assert not any(paragraph.startswith("- ") and paragraph.endswith(" -") for paragraph in pdf_paragraphs)
    assert len(pdf_paragraphs) == 11


def test_pdf_word_hyphenated_at_a_line_end_is_rejoined(pdf_paragraphs: list[str]) -> None:
    assert "reduces the colony's overall productivity only slightly" in pdf_paragraphs[2]


def test_pdf_page_break_ends_a_paragraph_even_mid_sentence(pdf_paragraphs: list[str]) -> None:
    last_on_page_one = next(index for index, text in enumerate(pdf_paragraphs) if text.startswith("Many cities"))

    assert pdf_paragraphs[last_on_page_one].endswith("before the infection spreads from one")
    assert pdf_paragraphs[last_on_page_one + 1] == "apiary to the next."


def test_docx_keeps_only_body_paragraphs_so_the_sample_table_is_excluded(docx_text: str) -> None:
    paragraphs = docx_text.split(PARAGRAPH_SEPARATOR)

    assert paragraphs[0] == "Remote Work Policy"
    assert len(paragraphs) == 6
    assert "Desk chair" not in docx_text


def test_docx_header_footer_and_table_text_is_excluded(tmp_path: Path) -> None:
    # The sample's footer is only a page number, which the cleaner drops anyway; this footer is real text.
    document = Document()
    document.add_paragraph("Body text stays.")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Table cell text"
    section = document.sections[0]
    section.header.paragraphs[0].text = "Running header text"
    section.footer.paragraphs[0].text = "Confidential footer text"
    path = tmp_path / "with_furniture.docx"
    document.save(str(path))

    assert DocxExtractor(TextCleaner()).extract(path) == "Body text stays."


def test_docx_soft_line_break_becomes_a_space_inside_its_paragraph(docx_text: str) -> None:
    assert docx_text.split(PARAGRAPH_SEPARATOR)[-1] == (
        "Questions about this policy go to the people team. Requests for exceptions go to your manager first."
    )


def test_docx_text_is_nfkc_normalised_but_curly_apostrophes_are_kept(docx_text: str) -> None:
    assert "The finance team reimburses" in docx_text
    assert "safe workspace and for keeping" in docx_text
    assert "\N{LATIN SMALL LIGATURE FI}" not in docx_text
    assert "\N{NO-BREAK SPACE}" not in docx_text
    assert "the manager\N{RIGHT SINGLE QUOTATION MARK}s agreement" in docx_text


@pytest.mark.parametrize(
    ("sample", "renamed_to", "expected_title"),
    [
        (PDF_SAMPLE, "URBAN_BEEKEEPING.PDF", "Urban Beekeeping: A Short Field Guide"),
        (DOCX_SAMPLE, "Remote_Work_Policy.Docx", "Remote Work Policy"),
    ],
    ids=["upper-case-pdf", "mixed-case-docx"],
)
def test_registry_picks_the_extractor_by_extension_case_insensitively(
    tmp_path: Path, sample: Path, renamed_to: str, expected_title: str
) -> None:
    renamed_copy = tmp_path / renamed_to
    renamed_copy.write_bytes(sample.read_bytes())
    cleaner = TextCleaner()
    registry = ExtractorRegistry({".pdf": PdfExtractor(cleaner), ".docx": DocxExtractor(cleaner)})

    clean_text = registry.extract(renamed_copy)

    assert clean_text.split(PARAGRAPH_SEPARATOR)[0] == expected_title
