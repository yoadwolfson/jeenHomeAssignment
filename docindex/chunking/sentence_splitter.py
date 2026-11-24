"""Sentence detection, behind a protocol so another language could be added as a new class."""

from typing import Protocol

import pysbd

ENGLISH = "en"


class SentenceSplitter(Protocol):
    """Splits one paragraph into its sentences."""

    def split(self, paragraph: str) -> list[str]:
        """Return the stripped, non-empty sentences of `paragraph` in order."""
        ...


class PysbdSentenceSplitter:
    """English sentence detection with pysbd, which knows abbreviations such as `Dr.` and `e.g.`."""

    def __init__(self) -> None:
        # clean=False keeps the text exactly as given; the clean-text rules have already run.
        self._segmenter = pysbd.Segmenter(language=ENGLISH, clean=False)

    def split(self, paragraph: str) -> list[str]:
        """Return the stripped, non-empty sentences of `paragraph` in order."""
        sentences = (sentence.strip() for sentence in self._segmenter.segment(paragraph))
        return [sentence for sentence in sentences if sentence]
