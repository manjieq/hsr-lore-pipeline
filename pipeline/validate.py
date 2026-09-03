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


def _normalize_noun_form(word: str) -> str:
    """Normalize a token for comparison so minor, non-meaningful surface
    differences don't by themselves count as a hallucinated name:

    - A trailing possessive ("Herta's", or the bare trailing "'" used
      after a name already ending in "s") is stripped in a loop rather
      than a single pass, since a possessive can end up with a second
      trailing "'" from an enclosing stylistic quote (e.g. paraphrase
      output styled as "'Sparxie's'" -- the tokenizer captures the
      closing quote as part of the word).
    - A plain trailing "s" is then also stripped, so a plural in the
      source ("Cloud Knights", "Stellaron Hunters", "Silvermane Guards"
      -- HSR's own faction/group names are very often plural) matches a
      singular reference in the paraphrase ("a Cloud Knight"), or vice
      versa. This is deliberately approximate: it can also conflate two
      genuinely different words that happen to differ only by a trailing
      "s", but that's judged less likely than the plural/singular and
      possessive mismatches it fixes, which recur constantly in practice."""
    while word.endswith("'s") or word.endswith("'"):
        word = word[:-2] if word.endswith("'s") else word[:-1]
    if word.endswith("s") and len(word) > 3:
        word = word[:-1]
    return word


# CJK Unified Ideographs, Hiragana, Katakana, Hangul syllables -- any of
# these appearing in an English short_text is a sign the local model
# partially reverted to (or never left) Chinese/Japanese/Korean rather
# than fully paraphrasing in English, a real failure mode observed in
# production (e.g. "...reveals the代价 of a prophet's warnings...").
_NON_LATIN_SCRIPT_RE = re.compile(
    "[一-鿿぀-ヿ가-힯]"  # CJK ideographs, hiragana/katakana, hangul
)



# Title abbreviations end in "." without ending the sentence -- without this,
# "Mr. Svarog" reads as "Mr." (sentence end) + "Svarog" (sentence-initial),
# wrongly excluding "Svarog" from the known-source-noun set.
_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "prof"}


def _is_sentence_initial(text: str, start: int) -> bool:
    """True if the token starting at `start` opens a sentence: either it's
    the very first thing in `text`, or the nearest preceding non-space,
    non-quote/paren character is sentence-ending punctuation that isn't
    itself the end of a title abbreviation like "Mr."."""
    j = start - 1
    while j >= 0 and text[j] in " \t\n\"'“”‘’()":
        j -= 1
    if j < 0:
        return True
    if text[j] not in ".!?":
        return False
    if text[j] == ".":
        word_end = j
        word_start = word_end
        while word_start > 0 and text[word_start - 1].isalpha():
            word_start -= 1
        if text[word_start:word_end].lower() in _ABBREVIATIONS:
            return False
    return True


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
            nouns.add(_normalize_noun_form(tok))
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

    if _NON_LATIN_SCRIPT_RE.search(short_text):
        flags.append("possible_untranslated_text")

    source_nouns = _proper_nouns(raw_text, skip_sentence_initial=True) | _proper_nouns(
        name, skip_sentence_initial=False
    )
    short_nouns = _proper_nouns(short_text, skip_sentence_initial=True)
    unmatched = {n for n in short_nouns if n not in source_nouns}
    if unmatched:
        flags.append("possible_hallucinated_name")

    return flags
