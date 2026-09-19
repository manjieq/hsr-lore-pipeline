"""Tests for pipeline/entities.py, the LLM-free entity graph builder.

Several of these pin down real failure shapes found while calibrating the
extractor against the full 658-entry corpus, not hypotheticals -- see the
comments on each.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.entities import (
    MIN_CONNECTION_ENTRIES,
    MIN_ENTRY_MENTIONS,
    build_connection_cycle,
    _canonical_key,
    _strip_honorific,
    build_character_gazetteer,
    build_entities_file,
    build_entity_index,
    collect_confirmed_single_words,
    extract_surface_forms,
    slugify,
)


def entry(entry_id, category, name, raw_text):
    return {"id": entry_id, "category": category, "name": name, "raw_text": raw_text}


# --- canonicalization -------------------------------------------------


def test_canonical_key_folds_case_and_plural():
    # HSR faction names alternate between singular and plural constantly
    # ("a Cloud Knight" / "the Cloud Knights"), so these must be one node.
    assert _canonical_key("Cloud Knights") == _canonical_key("cloud knight")
    assert _canonical_key("Chrysos Heir") == _canonical_key("Chrysos Heirs")


def test_canonical_key_folds_possessive():
    assert _canonical_key("Herta's") == _canonical_key("Herta")


def test_canonical_key_keeps_leading_article():
    """Regression: stripping a leading article collapsed "The Herta" (the
    puppet) into "Herta" (Madam Herta) -- two genuinely different
    characters in this corpus -- producing one node whose display name
    flickered depending on entry processing order."""
    assert _canonical_key("The Herta") != _canonical_key("Herta")


def test_canonical_key_does_not_over_singularize_short_words():
    # Guard the len() floor: a short word ending in "s" must survive.
    assert _canonical_key("Ras") == "ras"


def test_strip_honorific_resolves_to_the_person():
    assert _strip_honorific("Madam Herta") == "Herta"
    assert _strip_honorific("Miss Robin") == "Robin"
    assert _strip_honorific("Dr. Ratio") == "Ratio"


def test_strip_honorific_leaves_bare_honorific_alone():
    # Nothing would remain, so the token is kept rather than blanked.
    assert _strip_honorific("Madam") == "Madam"


def test_slugify_is_url_safe_and_stable():
    assert slugify("Xianzhou Luofu") == "xianzhou-luofu"
    assert slugify("Dan Heng • Imbibitor Lunae") == "dan-heng-imbibitor-lunae"


# --- surface extraction -----------------------------------------------


def test_extract_skips_sentence_initial_single_words_without_corpus_evidence():
    """Ordinary capitalization is the dominant false positive: "However"
    opening a sentence is not an entity. With no corpus evidence to lean
    on, a sentence-initial single word is dropped -- which is safe but
    also costs the real name "Belobog", hence the two-pass design."""
    found = extract_surface_forms("However, the guard left. Belobog stood quiet.")
    assert "However" not in found
    assert "Belobog" not in found


def test_corpus_evidence_rescues_a_sentence_initial_proper_noun():
    """The point of collect_confirmed_single_words: running-prose uses
    elsewhere in the corpus vouch for the word everywhere, so a real name
    is not lost merely to sentence position."""
    entries = [
        entry("a", "light_cone", "One", "They fled toward Belobog before dawn."),
        entry("b", "relic_set", "Two", "A road to Belobog, long since buried."),
        entry("c", "relic_set", "Three", "Belobog stood quiet."),
    ]
    confirmed = collect_confirmed_single_words(entries)
    assert _canonical_key("Belobog") in confirmed

    found = extract_surface_forms("However, the guard left. Belobog stood quiet.", confirmed)
    assert "Belobog" in found
    # The stoplisted word is still rejected even with a confirmed set.
    assert "However" not in found


def test_extract_keeps_multiword_run_even_sentence_initially():
    # A two-word capitalized run opening a sentence is still almost always
    # a real name, unlike a lone capitalized word.
    assert "Cloud Knights" in extract_surface_forms("Cloud Knights patrol the deck.")


def test_extract_captures_lowercase_connectors_inside_names():
    assert "Abominations of Abundance" in extract_surface_forms(
        "They fought the Abominations of Abundance for years."
    )


def test_extract_drops_common_words_appearing_midsentence():
    # "As" and "In" survived the sentence-initial filter in the real
    # corpus (they appear mid-sentence inside quoted dialogue) and showed
    # up as top-ranked "entities" until they were stoplisted.
    found = extract_surface_forms('She said, "As I told you." Then, In truth, he left.')
    assert "As" not in found
    assert "In" not in found


def test_extract_strips_honorific_from_mention():
    found = extract_surface_forms("The crew met Madam Herta aboard the station.")
    assert "Herta" in found
    assert "Madam Herta" not in found


# --- gazetteer --------------------------------------------------------


def test_gazetteer_derives_characters_from_story_entry_names():
    entries = [
        entry("a", "character_story", "Acheron — Story 1", "text"),
        entry("b", "character_story", "Acheron — Story 2", "text"),
        entry("c", "light_cone", "Night on the Milky Way", "text"),
    ]
    gaz = build_character_gazetteer(entries)
    assert gaz[_canonical_key("Acheron")] == "Acheron"
    # A light cone name is not a character.
    assert _canonical_key("Night on the Milky Way") not in gaz


def test_gazetteer_folds_alternate_outfit_variants_onto_base_character():
    """"Dan Heng * Imbibitor Lunae" is the same person as "Dan Heng" for
    lore purposes; keeping them apart splits that person's edges."""
    entries = [
        entry("a", "character_story", "Dan Heng • Imbibitor Lunae — Story 1", "t"),
        entry("b", "character_story", "Dan Heng — Story 1", "t"),
    ]
    gaz = build_character_gazetteer(entries)
    assert gaz[_canonical_key("Dan Heng • Imbibitor Lunae")] == "Dan Heng"
    assert gaz[_canonical_key("Dan Heng")] == "Dan Heng"


# --- index building ---------------------------------------------------


def test_entity_needs_more_than_one_entry_to_be_a_node():
    """An entity in a single entry connects nothing, which is the whole
    point of this file."""
    entries = [
        entry("a", "light_cone", "One", "The Stellaron Hunters struck at dawn."),
        entry("b", "light_cone", "Two", "Nothing relevant here at all."),
    ]
    names = {e["name"] for e in build_entity_index(entries)}
    assert "Stellaron Hunters" not in names


def test_entity_links_entries_across_categories():
    entries = [
        entry("a", "light_cone", "One", "A relic of the Cloud Knights."),
        entry("b", "relic_set", "Two", "Forged for the Cloud Knights."),
        entry("c", "character_story", "X — Story 1", "She joined the Cloud Knights."),
    ]
    found = {e["name"]: e for e in build_entity_index(entries)}
    node = found["Cloud Knights"]
    assert node["entry_count"] == 3
    assert node["category_span"] == 3
    assert node["category_counts"] == {"character_story": 1, "light_cone": 1, "relic_set": 1}
    assert node["entry_ids"] == ["a", "b", "c"]


def test_singular_and_plural_mentions_merge_into_one_node():
    entries = [
        entry("a", "light_cone", "One", "A lone Cloud Knight stood watch."),
        entry("b", "relic_set", "Two", "The Cloud Knights held the line."),
    ]
    names = [e["name"] for e in build_entity_index(entries)]
    assert names.count("Cloud Knights") + names.count("Cloud Knight") == 1


def test_display_name_uses_most_common_surface_form():
    entries = [
        entry("a", "light_cone", "One", "The Cloud Knights marched."),
        entry("b", "relic_set", "Two", "The Cloud Knights returned."),
        entry("c", "character_story", "X — Story 1", "One Cloud Knight fell."),
    ]
    found = {e["name"] for e in build_entity_index(entries)}
    assert "Cloud Knights" in found


def test_known_character_is_exempt_from_the_single_word_threshold():
    """A one-word character name is established by the gazetteer, so the
    noise argument for the higher single-word bar does not apply."""
    entries = [
        entry("a", "character_story", "Blade — Story 1", "A quiet life."),
        entry("b", "light_cone", "One", "He fought Blade at the summit."),
        entry("c", "relic_set", "Two", "A blade forged when Blade was young."),
    ]
    found = {e["name"]: e for e in build_entity_index(entries)}
    assert "Blade" in found
    assert found["Blade"]["kind"] == "character"


def test_unknown_single_word_term_needs_the_higher_threshold():
    entries = [
        entry("a", "light_cone", "One", "It happened at Zephyrus long ago."),
        entry("b", "relic_set", "Two", "Recovered from Zephyrus."),
    ]
    assert "Zephyrus" not in {e["name"] for e in build_entity_index(entries)}
    entries.append(entry("c", "character_story", "X — Story 1", "She left Zephyrus."))
    assert "Zephyrus" in {e["name"] for e in build_entity_index(entries)}


def test_curated_alias_resolves_onto_canonical_entity():
    entries = [
        entry("a", "light_cone", "One", "Bound for the Luofu."),
        entry("b", "relic_set", "Two", "Forged on the Xianzhou Luofu."),
    ]
    found = {e["name"]: e for e in build_entity_index(entries)}
    assert "Xianzhou Luofu" in found
    assert found["Xianzhou Luofu"]["entry_count"] == 2
    assert "Luofu" not in found


def test_entities_sorted_by_span_then_reach():
    entries = [
        entry("a", "light_cone", "One", "The Cloud Knights marched."),
        entry("b", "relic_set", "Two", "The Cloud Knights again."),
        entry("c", "relic_set", "Three", "The Wailing Choir again."),
        entry("d", "relic_set", "Four", "The Wailing Choir once more."),
    ]
    names = [e["name"] for e in build_entity_index(entries)]
    # Both appear in 2 entries, but Cloud Knights bridges two categories
    # while Wailing Choir sits inside one -- the bridge ranks higher.
    assert names.index("Cloud Knights") < names.index("Wailing Choir")


def test_entity_ids_are_unique():
    entries = [
        entry("a", "light_cone", "One", "The Cloud Knights rose."),
        entry("b", "relic_set", "Two", "The Cloud Knights fell."),
        entry("c", "light_cone", "Three", "The Cloud-Knights marched."),
        entry("d", "relic_set", "Four", "The Cloud-Knights held."),
    ]
    ids = [e["id"] for e in build_entity_index(entries)]
    assert len(ids) == len(set(ids))


def test_build_entities_file_shape():
    entries = [
        entry("a", "light_cone", "One", "The Cloud Knights rose."),
        entry("b", "relic_set", "Two", "The Cloud Knights fell."),
    ]
    data = build_entities_file(entries, start_date="2026-01-01")
    assert set(data) == {"generated_at", "entity_count", "connection_cycle", "entities"}
    assert data["entity_count"] == len(data["entities"])
    assert set(data["connection_cycle"]) == {"cycle", "cycle_start_date"}
    assert data["connection_cycle"]["cycle_start_date"] == "2026-01-01"
    assert MIN_ENTRY_MENTIONS == 2


def test_entries_missing_raw_text_do_not_crash():
    entries = [
        {"id": "a", "category": "light_cone", "name": "One"},
        entry("b", "relic_set", "Two", "The Cloud Knights fell."),
    ]
    assert build_entity_index(entries) == []


def test_single_entry_of_evidence_is_not_enough():
    """Regression: a one-entry evidence bar let quoted dialogue mint
    entities. `He said, "Look at that."` puts "Look" after a comma, so the
    sentence-initial test reads it as mid-sentence -- and "Do", "Look",
    "Are" and "You're" became top-ranked entities spanning all three
    categories until evidence required running prose in two entries."""
    entries = [
        entry("a", "light_cone", "One", 'He said, "Zephyrus at last."'),
        entry("b", "relic_set", "Two", "Zephyrus stood quiet."),
    ]
    assert _canonical_key("Zephyrus") not in collect_confirmed_single_words(entries)


def test_bare_honorific_is_never_an_entity():
    """The run regex stops at the period in "Mr. Svarog", so "Mr" arrives
    detached. It ranked as a top-20 three-category entity until a bare
    honorific was rejected outright."""
    entries = [
        entry("a", "light_cone", "One", "They met Mr. Svarog beneath the city."),
        entry("b", "relic_set", "Two", "A gift from Mr. Svarog."),
        entry("c", "character_story", "X — Story 1", "She asked Mr. Svarog for help."),
    ]
    names = {e["name"] for e in build_entity_index(entries)}
    assert "Mr" not in names
    assert "General" not in names
    assert "Svarog" in names


def test_honorific_is_only_stripped_before_an_actual_name():
    """Regression: several honorifics double as ordinary title nouns.
    "Master of Destruction" and "Lord of Destruction" are real HSR
    epithets, and stripping unconditionally reduced both to the fragment
    "of Destruction", which merged into one nonsense cross-category
    entity."""
    assert _strip_honorific("Master of Destruction") == "Master of Destruction"
    assert _strip_honorific("Lord of Destruction") == "Lord of Destruction"
    # Still strips when a real name follows.
    assert _strip_honorific("Master Yang") == "Yang"


# --- connection rotation ----------------------------------------------


def test_connection_cycle_only_features_cross_category_entities():
    """A term confined to one category links fragments of the same kind,
    which is the least surprising thing the graph can show."""
    entities = [
        {"id": "a", "category_span": 1, "entry_count": 9},
        {"id": "b", "category_span": 2, "entry_count": 4},
        {"id": "c", "category_span": 3, "entry_count": 3},
    ]
    cycle = build_connection_cycle(entities, start_date="2026-01-01")["cycle"]
    assert set(cycle) == {"b", "c"}


def test_connection_cycle_applies_a_reach_floor():
    """Two entries in two categories is technically a connection but makes
    a thin feature -- the rotation once led with a department mentioned
    exactly twice."""
    entities = [
        {"id": "thin", "category_span": 2, "entry_count": MIN_CONNECTION_ENTRIES - 1},
        {"id": "solid", "category_span": 2, "entry_count": MIN_CONNECTION_ENTRIES},
    ]
    assert build_connection_cycle(entities, start_date="2026-01-01")["cycle"] == ["solid"]


def test_connection_cycle_is_deterministic():
    entities = [{"id": f"e{i}", "category_span": 2, "entry_count": 5} for i in range(30)]
    first = build_connection_cycle(entities, start_date="2026-01-01")["cycle"]
    second = build_connection_cycle(entities, start_date="2026-01-01")["cycle"]
    assert first == second
    # ...and actually shuffled, not left in input order.
    assert first != [e["id"] for e in entities]
