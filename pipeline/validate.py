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


def _proper_nouns(text: str) -> set[str]:
    """Very rough heuristic: capitalized words that aren't the first word of
    a sentence (to cut down on false positives from normal capitalization)."""
    tokens = re.findall(r"[A-Za-z][a-zA-Z']*", text)
    nouns = set()
    for i, tok in enumerate(tokens):
        if i == 0:
            continue
        if tok[0].isupper() and tok.lower() not in _COMMON_WORDS:
            nouns.add(tok)
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

    source_nouns = _proper_nouns(raw_text) | _proper_nouns(name)
    short_nouns = _proper_nouns(short_text)
    unmatched = {n for n in short_nouns if n not in source_nouns}
    if unmatched:
        flags.append("possible_hallucinated_name")

    return flags
