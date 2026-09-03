"""Tests for ingest/wikitext_utils.py. No network access -- fixtures are
small synthetic wikitext snippets shaped like real HSR Fandom wiki pages
(spot-checked interactively against the live wiki when each extractor was
written), not live fetches."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.wikitext_utils import (
    clean_flavor_text,
    extract_infobox_field,
    extract_section,
    extract_template_arg,
    extract_template_params,
)


def test_extract_template_arg_handles_nested_braces():
    wikitext = "intro {{Description|A tale of {{w|Kafka|the Hunter}} and her coats.}} outro"
    assert extract_template_arg(wikitext, "Description") == "A tale of {{w|Kafka|the Hunter}} and her coats."


def test_extract_template_arg_returns_none_when_absent():
    assert extract_template_arg("no template here", "Description") is None


def test_extract_infobox_field_reads_to_end_of_line():
    wikitext = "{{Infobox\n|rarity = 5\n|effect_path = Erudition\n}}"
    assert extract_infobox_field(wikitext, "rarity") == "5"
    assert extract_infobox_field(wikitext, "effect_path") == "Erudition"


def test_extract_section_stops_at_next_level_2_heading():
    wikitext = "intro\n==Description==\nBody text here.\n===Subheading===\nMore body.\n==Next Section==\nnot included"
    section = extract_section(wikitext, "Description")
    assert "Body text here." in section
    assert "More body." in section  # level-3 subheading is part of the body
    assert "not included" not in section


def test_extract_section_returns_none_when_heading_absent():
    assert extract_section("no headings here", "Description") is None


def test_clean_flavor_text_strips_common_markup():
    raw = "'''Bold''' and [[Some Page|a link]] with a<br/>line break and {{w|Other Page|another link}}."
    cleaned = clean_flavor_text(raw)
    assert cleaned == "Bold and a link with a line break and another link."


def test_clean_flavor_text_strips_rubi_annotations():
    # {{Rubi|base|ruby}} is a ruby/furigana-style gloss (e.g. a name with
    # its title as a small annotation) -- found leaking into the live
    # dataset's raw_text unstripped before this fix (e.g. relic set lore
    # containing literal "{{Rubi|Cerces|Reason Titan}}").
    raw = "The thoughts of {{Rubi|Cerces|Reason Titan}} became enhanced."
    assert clean_flavor_text(raw) == "The thoughts of Cerces became enhanced."


def test_extract_template_params_reads_numbered_fields():
    # Shaped like the real {{Character Story|...}} template on
    # <Character>/Lore pages (see ingest/wiki_scrape_character_stories.py).
    wikitext = (
        "{{Character Tabs}}\n"
        "==Character Stories==\n"
        "{{Character Story\n"
        "|text1    = A story about [[Elio]] and the [[Stellaron Hunters]].\n"
        "|mention1 = Elio\n"
        "\n"
        "|text2    = A second story, quoted: ''\"Hello there.\"''\n"
        "|mention2 = \n"
        "}}\n"
    )
    params = extract_template_params(wikitext, "Character Story")
    assert params["text1"] == "A story about [[Elio]] and the [[Stellaron Hunters]]."
    assert params["mention1"] == "Elio"
    assert "text2" in params and "A second story" in params["text2"]


def test_extract_template_params_pipe_inside_a_link_is_not_a_boundary():
    wikitext = "{{Character Story|text1=See [[Some Page|a labeled link]] for more.|mention1=Someone}}"
    params = extract_template_params(wikitext, "Character Story")
    assert params["text1"] == "See [[Some Page|a labeled link]] for more."
    assert params["mention1"] == "Someone"


def test_extract_template_params_pipe_inside_a_nested_template_is_not_a_boundary():
    wikitext = "{{Character Story|text1=A quote {{Ref/Mission|Some Mission|quote=Hello|other=World}} here.}}"
    params = extract_template_params(wikitext, "Character Story")
    assert params["text1"] == "A quote {{Ref/Mission|Some Mission|quote=Hello|other=World}} here."


def test_extract_template_params_returns_none_when_template_absent():
    assert extract_template_params("nothing here", "Character Story") is None
