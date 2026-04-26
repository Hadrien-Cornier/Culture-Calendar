"""Unit tests for the one-liner summary trimmer.

Regression: the old hard slice at 97 chars produced mid-word tails like
``"...desire, and cr..."`` (8 1/2 on mobile). The replacement trims at
the last whitespace before the cap.
"""

from src.summary_generator import _trim_to_word_boundary


def test_short_summary_unchanged():
    s = "A pithy one-liner."
    assert _trim_to_word_boundary(s) == s


def test_long_summary_trims_at_word_boundary():
    fellini = (
        "Fellini's masterpiece follows a blocked director's surreal "
        "descent through dreams, desire, and creative paralysis in "
        "every fevered frame."
    )
    out = _trim_to_word_boundary(fellini, max_len=100)
    assert out.endswith("…")
    last_word = out.rstrip("…").rstrip(",;:.- ").rsplit(" ", 1)[-1]
    assert last_word.isalpha(), f"trim landed mid-word: {out!r}"
    assert "cr…" not in out and "creat…" not in out


def test_no_trim_when_under_cap():
    s = "x" * 50
    assert _trim_to_word_boundary(s, max_len=140) == s


def test_falls_back_to_hard_cut_when_no_space_in_range():
    s = "abcdef" * 30
    out = _trim_to_word_boundary(s, max_len=50, min_word_cut=10)
    assert len(out) <= 50
    assert out.endswith("…")


def test_strips_trailing_punctuation_before_ellipsis():
    s = "alpha beta gamma delta epsilon, zeta eta theta " * 5
    out = _trim_to_word_boundary(s, max_len=60)
    assert not out[:-1].endswith(",")
    assert not out[:-1].endswith(".")
