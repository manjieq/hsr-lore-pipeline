"""Tests for pipeline/validate.py, in particular the possible_hallucinated_name
heuristic's three known false-positive sources that were fixed together:

1. Sentence-initial capitalization in raw_text/short_text (e.g. "Then",
   "She" opening a non-first sentence) used to be treated as a proper
   noun, because the original code only skipped token index 0 of the
   *whole* string rather than re-checking at every sentence boundary.
2. The item's own `name` is a title, not a sentence -- its first word was
   being excluded from the "known" source-noun set for the same reason,
   so a paraphrase that echoed the item's own name could get flagged.
3. A trailing possessive ("Herta's") didn't match the bare noun
   ("Herta") the paraphrase used instead, or vice versa.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.validate import validate_short_text


def test_sentence_initial_capitalization_is_not_flagged():
    # "Then" opens the source's second sentence and the paraphrase's
    # first sentence -- ordinary capitalization, not a hallucinated name.
    raw_text = "A hero once lived quietly. Then war came to the valley."
    short_text = "Then war swept through, changing everything in its path."
    assert "possible_hallucinated_name" not in validate_short_text(short_text, raw_text, "A Quiet Hero")


def test_name_first_word_counts_as_a_known_source_token():
    # The item's own name ("Destiny's Threads Forewoven") is a title, not
    # a sentence -- its first word must still count as legitimate.
    raw_text = "Fate weaves every ending before it is lived."
    short_text = "Destiny's threads were woven long before the end."
    assert "possible_hallucinated_name" not in validate_short_text(short_text, raw_text, "Destiny's Threads Forewoven")


def test_possessive_form_matches_bare_noun():
    raw_text = "Herta's station drifts quietly through the void."
    short_text = "Herta oversees the station from afar."
    assert "possible_hallucinated_name" not in validate_short_text(short_text, raw_text, "Space Sealing Station")


def test_bare_noun_in_source_matches_possessive_in_short_text():
    raw_text = "Herta oversees the station from afar."
    short_text = "Herta's station drifts quietly through the void."
    assert "possible_hallucinated_name" not in validate_short_text(short_text, raw_text, "Space Sealing Station")


def test_title_abbreviation_period_does_not_start_a_new_sentence():
    # "Mr." ends in "." without ending the sentence -- "Svarog" must still
    # count as a known source noun both times it follows "Mr.".
    raw_text = '"Please, Mr. Svarog, can you help?" Without a word, Mr. Svarog complied.'
    short_text = "Hook begs Mr. Svarog for help, and Svarog obliges without a word."
    assert "possible_hallucinated_name" not in validate_short_text(short_text, raw_text, "Dance! Dance! Dance!")


def test_genuinely_invented_name_is_still_flagged():
    raw_text = "A hero once lived quietly in the valley."
    short_text = "Then Zylorath the Undying arrived to claim the throne."
    assert "possible_hallucinated_name" in validate_short_text(short_text, raw_text, "A Quiet Hero")
