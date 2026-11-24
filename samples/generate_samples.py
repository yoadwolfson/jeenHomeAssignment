"""Generate the sample documents in this folder.

Dev-only tool, not part of the docindex package. Needs: fpdf2 2.9.0, pillow, python-docx 1.2.0.
Run from the repo root:  python samples/generate_samples.py
"""

from pathlib import Path

from docx import Document
from fpdf import FPDF
from PIL import Image, ImageDraw

SAMPLES_DIR = Path(__file__).parent

FONT_FAMILY = "Helvetica"
FONT_SIZE_PT = 11
LINE_HEIGHT_MM = 6
PARAGRAPH_GAP_MM = 6
PAGE_MARGIN_MM = 20
FOOTER_OFFSET_MM = -15
SCAN_DPI_SIZE = (1240, 1754)  # A4 at 150 dpi
SCAN_TEXT_ORIGIN = (120, 160)
SCAN_LINE_STEP_PX = 40

# Each paragraph is either a string (wrapped automatically) or a list of
# explicit lines, used where a line must end in a hyphen.
PDF_PARAGRAPHS: list[str | list[str]] = [
    "Urban Beekeeping: A Short Field Guide",
    "Keeping honey bees in a city is easier than most people expect. A single hive "
    "needs about one square metre of ground, a water source within a few hundred metres, "
    "and a neighbour who does not mind the occasional visitor on a flowering shrub.",
    [
        "The most important decision is where the hive entrance faces. An entrance turned",
        "towards a wall or a tall hedge forces foragers to climb steeply as they leave, which",
        "keeps their flight path above head height and reduces the colony's overall pro-",
        "ductivity only slightly while avoiding almost every conflict with people walking past.",
    ],
    "Inspections should happen every seven to ten days during spring and early summer. "
    "During each inspection the keeper looks for eggs, which prove the queen is laying, "
    "for queen cells, which warn that the colony is preparing to swarm, and for signs of "
    "disease such as discoloured or sunken brood cappings.",
    "Swarming is the natural way a colony reproduces. The old queen leaves with roughly "
    "half of the workers and settles on a branch or a lamp post while scouts search for "
    "a new home. In a city this frightens people, so urban keepers prevent swarms by "
    "giving the colony more space before it feels crowded, or by splitting it into two "
    "hives on purpose. A well timed split also replaces an ageing queen and gives the "
    "keeper a spare colony to fall back on if the original one fails over the winter.",
    "Varroa mites are the greatest threat to honey bee health worldwide. The mites feed "
    "on developing bees and spread viruses that deform wings and shorten lives. Most "
    "keepers count mites once a month by washing a sample of bees in alcohol or by "
    "counting the mites that fall onto a sticky board placed under the hive. When the "
    "count rises above a threshold the keeper treats the colony, ideally in late summer "
    "after the honey harvest and before the winter bees are raised. Treatments based on "
    "organic acids are popular because they leave no residue in wax, but they work best "
    "when there is little or no sealed brood in the hive, which is why many keepers "
    "repeat the treatment in midwinter when the colony is broodless.",
    "Harvesting honey is the reward for a season of care. Frames are removed only when "
    "most of their cells are capped with wax, because uncapped honey still contains too "
    "much water and may ferment in the jar.",
    "Many cities require hives to be registered with a local authority, and some limit "
    "the number of colonies per garden or demand a minimum distance from the property "
    "boundary. Registration is usually free and has a practical benefit: inspectors can "
    "warn nearby keepers quickly when a notifiable disease such as foulbrood is found in "
    "the area, which gives every colony within a few kilometres a better chance of "
    "being checked and treated before the infection spreads from one apiary to the next.",
    "Forage matters more than the hive itself. Parks, railway embankments, cemeteries "
    "and private gardens together offer a long flowering season, often longer than in "
    "farmland where a single crop blooms for two weeks and then nothing else follows. "
    "Lime trees in early summer and ivy in autumn are two of the most valuable sources "
    "of nectar for city bees, and planting either one helps every colony nearby.",
    "Winter is a quiet season. The colony clusters around the queen and keeps her warm "
    "by shivering its flight muscles, slowly eating the stores it gathered in summer. "
    "The keeper's only tasks are to keep the entrance clear and to lift the back of the "
    "hive now and then to judge, by its weight, whether food is running low.",
]

DOCX_HEADING = "Remote Work Policy"
DOCX_PARAGRAPHS: list[str] = [
    "This policy explains how employees may work away from the office, what equipment "
    "the company provides, and how teams stay in touch across time zones.",
    "Eligibility depends on the role rather than the person. Roles that need physical "
    "presence, such as laboratory work or reception, are not eligible. Every other role "
    "may be performed remotely for up to four days a week with the manager’s agreement.",
    "The company provides a laptop, a headset and a monthly allowance towards internet "
    "costs. Employees are responsible for a safe workspace and for keeping company "
    "devices locked when unattended. The ﬁnance team reimburses approved purchases "
    "within thirty days.",
    "Core hours run from ten in the morning until three in the afternoon in the team’s "
    "home time zone. Outside core hours people may arrange their day freely, as long as "
    "meetings are announced at least one working day in advance.",
]
DOCX_LINE_BREAK_PARAGRAPH = (
    "Questions about this policy go to the people team.",
    "Requests for exceptions go to your manager first.",
)
DOCX_TABLE_ROWS = [("Item", "Provided"), ("Laptop", "Yes"), ("Desk chair", "No")]
DOCX_FOOTER_TEXT = "Page 1 of 1"

SCAN_LINES = [
    "This page was scanned from paper.",
    "It contains no text layer, only an image.",
]


class SamplePdf(FPDF):
    """A4 PDF with a centred '- N -' page number in the footer."""

    def footer(self) -> None:
        self.set_y(FOOTER_OFFSET_MM)
        self.set_font(FONT_FAMILY, size=FONT_SIZE_PT)
        self.cell(0, LINE_HEIGHT_MM, f"- {self.page_no()} -", align="C")


def build_text_pdf(target: Path) -> None:
    """Write a two-page text PDF exercising wrapping, hyphenation and page breaks."""
    pdf = SamplePdf(format="A4")
    pdf.set_margins(PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM)
    pdf.set_auto_page_break(auto=True, margin=PAGE_MARGIN_MM + LINE_HEIGHT_MM)
    pdf.add_page()
    pdf.set_font(FONT_FAMILY, size=FONT_SIZE_PT)
    for paragraph in PDF_PARAGRAPHS:
        if isinstance(paragraph, list):
            for line in paragraph:
                pdf.cell(0, LINE_HEIGHT_MM, line, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, LINE_HEIGHT_MM, paragraph, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(PARAGRAPH_GAP_MM)
    pdf.output(str(target))


def build_scanned_pdf(target: Path) -> None:
    """Write a PDF whose only page is an image of text, with no text layer."""
    page_image = Image.new("L", SCAN_DPI_SIZE, color=255)
    drawing = ImageDraw.Draw(page_image)
    x_position, y_position = SCAN_TEXT_ORIGIN
    for line in SCAN_LINES:
        drawing.text((x_position, y_position), line, fill=0, font_size=32)
        y_position += SCAN_LINE_STEP_PX
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.image(page_image, x=0, y=0, w=pdf.w, h=pdf.h)
    pdf.output(str(target))


def build_text_docx(target: Path) -> None:
    """Write a DOCX with a heading, body paragraphs, a soft line break, a table and a footer."""
    document = Document()
    document.add_heading(DOCX_HEADING, level=1)
    for paragraph in DOCX_PARAGRAPHS:
        document.add_paragraph(paragraph)
        document.add_paragraph("")
    first_line, second_line = DOCX_LINE_BREAK_PARAGRAPH
    run = document.add_paragraph().add_run(first_line)
    run.add_break()
    run.add_text(second_line)
    table = document.add_table(rows=0, cols=2)
    for left, right in DOCX_TABLE_ROWS:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = left, right
    document.sections[0].footer.paragraphs[0].text = DOCX_FOOTER_TEXT
    document.save(str(target))


def build_empty_docx(target: Path) -> None:
    """Write a DOCX with no body text."""
    Document().save(str(target))


def main() -> None:
    """Regenerate every sample document."""
    build_text_pdf(SAMPLES_DIR / "urban_beekeeping.pdf")
    build_scanned_pdf(SAMPLES_DIR / "scanned_no_text.pdf")
    build_text_docx(SAMPLES_DIR / "remote_work_policy.docx")
    build_empty_docx(SAMPLES_DIR / "empty.docx")


if __name__ == "__main__":
    main()
