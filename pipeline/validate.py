"""Deterministic QA checks for an AI-paraphrased short_text, run without a
second LLM call. Returns a list of qa_flags; an empty list means it passed
every check (though it still needs a human to flip reviewed=True before it
enters daily rotation)."""

from __future__ import annotations

import re

MIN_LENGTH = 40
MAX_LENGTH = 280
REFUSAL_MARKERS = (
    "as an ai",
    "i cannot",
    "i can't",
    "i'm not able to",
    "i am not able to",
    "sorry, but",
)


def _strip_possessive(word: str) -> str:
    """Normalize a trailing possessive marker so "Herta's" and "Herta"
    compare as the same name: the source text and the AI paraphrase don't
    always agree on whether to carry a possessive "'s" (or the bare
    trailing "'" used after a name already ending in "s") through a
    rewrite, and that shouldn't by itself count as a hallucinated name."""
    if word.endswith("'s"):
        return word[:-2]
    if word.endswith("'"):
        return word[:-1]
    return word


def _is_sentence_initial(text: str, start: int) -> bool:
    """True if the token starting at `start` opens a sentence: either it's
    the very first thing in `text`, or the nearest preceding non-space,
    non-quote/paren character is sentence-ending punctuation."""
    j = start - 1
    while j >= 0 and text[j] in " \t\n\"'“”‘’()":
        j -= 1
    return j < 0 or text[j] in ".!?"


def _proper_nouns(text: str, *, skip_sentence_initial: bool) -> set[str]:
    """Very rough heuristic: capitalized words, normalized for trailing
    possessives.

    When skip_sentence_initial is True (prose: raw_text / short_text), a
    word that merely opens a sentence is excluded, to cut down on false
    positives from ordinary capitalization ("Then", "She", ...) rather
    than genuine proper nouns -- note this only checks the *previous*
    character, not "is this the first word of a sentence" in the token
    list, so it correctly re-checks every sentence in the text, not just
    the very first word of the whole string.

    A `name` (an item's title) isn't a sentence, so pass
    skip_sentence_initial=False for it: its own first word is just as
    legitimate a source token as any other word in it."""
    nouns = set()
    for m in re.finditer(r"[A-Za-z][a-zA-Z']*", text):
        tok = m.group(0)
        if skip_sentence_initial and _is_sentence_initial(text, m.start()):
            continue
        if tok[0].isupper() and tok.lower() not in _COMMON_WORDS:
            nouns.add(_strip_possessive(tok))
    return nouns


_COMMON_WORDS = {
    "i", "the", "a", "an", "he", "she", "they", "it", "you", "we",
}


def validate_short_text(short_text: str, raw_text: str, name: str) -> list[str]:
    flags: list[str] = []

    if not short_text or not short_text.strip():
        flags.append("empty_short_text")
        return flags

    if len(short_text) < MIN_LENGTH:
        flags.append("short_text_too_short")
    if len(short_text) > MAX_LENGTH:
        flags.append("short_text_too_long")

    if short_text.strip() == raw_text.strip():
        flags.append("short_text_identical_to_raw")

    lowered = short_text.lower()
    if any(marker in lowered for marker in REFUSAL_MARKERS):
        flags.append("possible_refusal_artifact")

    source_nouns = _proper_nouns(raw_text, skip_sentence_initial=True) | _proper_nouns(
        name, skip_sentence_initial=False
    )
    short_nouns = _proper_nouns(short_text, skip_sentence_initial=True)
    unmatched = {n for n in short_nouns if n not in source_nouns}
    if unmatched:
        flags.append("possible_hallucinated_name")

    return flags
