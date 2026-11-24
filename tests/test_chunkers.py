"""Chunker seam: each split strategy on hand-written clean text, with small injected sizes."""

import pytest

from docindex.chunking import FixedSizeChunker


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


