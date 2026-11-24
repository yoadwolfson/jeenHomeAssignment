"""The check that extracted clean text is worth indexing."""

from pathlib import Path

from docindex.errors import NoExtractableTextError


def require_extractable_text(clean_text: str, path: Path, may_be_scanned: bool) -> str:
    """Return `clean_text`, or raise NoExtractableTextError when it has no letters or digits."""
    # Punctuation or symbols alone carry no meaning to embed, so they count as no text; there is no minimum length.
    if not any(character.isalnum() for character in clean_text):
        raise NoExtractableTextError(path.name, may_be_scanned)
    return clean_text
