"""Chunker seam: each split strategy on hand-written clean text, with small injected sizes."""

import pytest

from docindex.chunking import FixedSizeChunker, ParagraphChunker, PysbdSentenceSplitter, SentenceChunker


def sentence_chunker(max_chars: int) -> SentenceChunker:
    """A sentence chunker with the real English splitter and a small maximum."""
    return SentenceChunker(PysbdSentenceSplitter(), max_chars=max_chars)


def test_fixed_chunks_end_at_the_last_whitespace_before_the_limit() -> None:
    chunker = FixedSizeChunker(max_chars=12, overlap_chars=0)

    chunks = chunker.split("alpha beta gamma delta epsilon")

    assert chunks == ["alpha beta", "gamma delta", "epsilon"]


def test_fixed_chunk_starts_at_a_word_boundary_about_the_overlap_back() -> None:
    chunker = FixedSizeChunker(max_chars=14, overlap_chars=6)

    chunks = chunker.split("one two three four five six seven")

    # Each chunk repeats the previous chunk's last word: the word boundary within 6 chars of the cut.
    assert chunks == ["one two three", "three four", "four five six", "six seven"]


def test_fixed_hard_cuts_a_window_without_whitespace_at_the_limit() -> None:
    chunker = FixedSizeChunker(max_chars=5, overlap_chars=2)

    chunks = chunker.split("abcdefghijkl")

    # No whitespace means no word boundary to overlap from, so the next chunk starts at the cut.
    assert chunks == ["abcde", "fghij", "kl"]


def test_fixed_never_emits_a_chunk_that_only_repeats_the_overlap() -> None:
    chunker = FixedSizeChunker(max_chars=14, overlap_chars=6)

    chunks = chunker.split("aaaa bbbb cccc ddddddddddddddddddd eee")

    # No whitespace after the cut fits in the window, so the second chunk is hard-cut past it.
    assert chunks == ["aaaa bbbb cccc", "cccc ddddddddd", "dddddddddd eee"]


@pytest.mark.parametrize("overlap_chars", [10, 11], ids=["equal-to-size", "larger-than-size"])
def test_fixed_rejects_an_overlap_not_smaller_than_the_size(overlap_chars: int) -> None:
    with pytest.raises(ValueError, match="overlap_chars"):
        FixedSizeChunker(max_chars=10, overlap_chars=overlap_chars)


def test_fixed_ignores_paragraph_breaks_and_keeps_them_inside_a_chunk() -> None:
    chunker = FixedSizeChunker(max_chars=100, overlap_chars=10)

    chunks = chunker.split("Heading\n\nFirst paragraph.\n\nSecond.")

    assert chunks == ["Heading\n\nFirst paragraph.\n\nSecond."]


def test_fixed_strips_chunks_and_drops_empty_ones() -> None:
    chunker = FixedSizeChunker(max_chars=10, overlap_chars=3)

    assert chunker.split("  \n\n   ") == []
    assert chunker.split("\n\n  lead   \n\n") == ["lead"]


def test_fixed_chunks_never_exceed_the_limit_overlap_and_cover_the_text_in_order() -> None:
    max_chars = 40
    words = [f"w{number:03d}" for number in range(200)]
    chunker = FixedSizeChunker(max_chars=max_chars, overlap_chars=12)

    chunks = chunker.split(" ".join(words))

    assert all(len(chunk) <= max_chars for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        assert current.split()[0] in previous.split()
    words_in_order = list(dict.fromkeys(word for chunk in chunks for word in chunk.split()))
    assert words_in_order == words


def test_sentence_packs_whole_sentences_across_paragraphs_joined_by_one_space() -> None:
    chunker = sentence_chunker(max_chars=40)

    chunks = chunker.split("Bees fly. Bees sting.\n\nHives need care. Queens lay eggs.")

    assert chunks == ["Bees fly. Bees sting. Hives need care.", "Queens lay eggs."]


def test_sentence_detection_runs_per_paragraph_so_a_heading_without_a_period_stays_whole() -> None:
    chunker = sentence_chunker(max_chars=35)

    chunks = chunker.split("Swarm Control\n\nCheck the hive weekly in spring.")

    assert chunks == ["Swarm Control", "Check the hive weekly in spring."]


class PeriodOnlySplitter:
    """A naive splitter that only ends a sentence at '. ', blind to line breaks."""

    def split(self, paragraph: str) -> list[str]:
        """Return the pieces between '. ' boundaries."""
        return [piece.strip() for piece in paragraph.replace(". ", ".\0").split("\0") if piece.strip()]


def test_sentence_chunker_hands_the_splitter_one_paragraph_at_a_time() -> None:
    chunker = SentenceChunker(PeriodOnlySplitter(), max_chars=35)

    chunks = chunker.split("Swarm Control\n\nCheck the hive weekly in spring.")

    # Given the whole text, this splitter would return the heading fused to the sentence (46 chars).
    assert chunks == ["Swarm Control", "Check the hive weekly in spring."]


def test_sentence_abbreviations_do_not_cause_false_splits() -> None:
    chunker = sentence_chunker(max_chars=40)

    chunks = chunker.split("Dr. Smith moved to the U.S. last year. He keeps bees, e.g. Italian ones.")

    assert chunks == ["Dr. Smith moved to the U.S. last year.", "He keeps bees, e.g. Italian ones."]


def test_sentence_longer_than_the_maximum_falls_back_to_the_fixed_split_without_overlap() -> None:
    chunker = sentence_chunker(max_chars=20)

    chunks = chunker.split("Hi. Worker bees forage for nectar all day long. Bye.")

    # The pending "Hi." is flushed first; the long sentence's pieces never share words.
    assert chunks == ["Hi.", "Worker bees forage", "for nectar all day", "long.", "Bye."]
    assert all(len(chunk) <= 20 for chunk in chunks)


def test_sentence_drops_empty_paragraphs() -> None:
    chunker = sentence_chunker(max_chars=40)

    assert chunker.split("  \n\n   ") == []
    assert chunker.split("\n\n  Only one.  \n\n\n\n") == ["Only one."]


def test_sentence_chunks_never_exceed_the_maximum_and_keep_every_sentence_in_order() -> None:
    max_chars = 50
    # Every sentence is 23 chars, so exactly two fit in one chunk (47) and three don't (71).
    sentences = [f"Sentence {number:02d} about bees." for number in range(30)]
    paragraphs = [" ".join(sentences[start : start + 3]) for start in range(0, len(sentences), 3)]
    chunker = sentence_chunker(max_chars=max_chars)

    chunks = chunker.split("\n\n".join(paragraphs))

    assert all(len(chunk) <= max_chars for chunk in chunks)
    assert " ".join(chunks) == " ".join(sentences)
    assert len(chunks) == 15
    # Three sentences per paragraph: the second chunk joins the end of paragraph 1 to the start of paragraph 2.
    assert chunks[1] == "Sentence 02 about bees. Sentence 03 about bees."


def test_paragraph_splits_only_a_long_paragraph_by_sentence_packing_and_never_merges_short_ones() -> None:
    chunker = ParagraphChunker(PysbdSentenceSplitter(), max_chars=40)
    long_paragraph = "Bees fly far for food. They return at dusk. The queen stays inside."

    chunks = chunker.split(f"Foraging\n\nShort note.\n\n{long_paragraph}\n\nThe end.")

    assert chunks == [
        "Foraging",
        "Short note.",
        "Bees fly far for food.",
        "They return at dusk.",
        "The queen stays inside.",
        "The end.",
    ]


def test_paragraph_strips_chunks_and_drops_empty_paragraphs() -> None:
    chunker = ParagraphChunker(PysbdSentenceSplitter(), max_chars=40)

    assert chunker.split("  \n\n   ") == []
    assert chunker.split("\n\n  Title  \n\n\n\nBody.") == ["Title", "Body."]
