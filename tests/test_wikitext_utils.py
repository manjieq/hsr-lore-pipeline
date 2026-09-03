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


def test_clean_flavor_text_picks_the_m_variant_of_mc_template():
    assert clean_flavor_text("{{MC|m=He|f=She}} walked in.") == "He walked in."
    assert clean_flavor_text("{{MC|m=man|f=woman}}") == "man"


def test_clean_flavor_text_renders_obfuscate_as_block_characters():
    assert clean_flavor_text("Agent {{Obfuscate|3}} arrived.") == "Agent ▇▇▇ arrived."
    assert clean_flavor_text("Agent {{Obfuscate|-}} arrived.") == "Agent ▇ arrived."


def test_clean_flavor_text_unwraps_sic_template():
    assert clean_flavor_text("wondered if {{sic|the}} answer was near.") == "wondered if the answer was near."
    assert clean_flavor_text("qualifying on the {{sic|Herta space station}} is rare.") == (
        "qualifying on the Herta space station is rare."
    )


def test_clean_flavor_text_drops_hidden_sic_template():
    assert clean_flavor_text("Researchers at the {{sic|space station Herta|hide=1}} agree.") == (
        "Researchers at the agree."
    )


def test_clean_flavor_text_extracts_color_template_text_regardless_of_param_order():
    # Real usage puts the text in different positions relative to
    # "keyword" and "nobold=1" across different pages.
    assert clean_flavor_text('{{Color|keyword|"Rule 1: Be prepared."|nobold=1}}') == '"Rule 1: Be prepared."'
    assert clean_flavor_text("{{Color|keyword|nobold=1|Dazzling Ninja Hero}}") == "Dazzling Ninja Hero"


def test_clean_flavor_text_picks_positional_mc_variant():
    assert clean_flavor_text("{{MC|boy|girl}} ran home.") == "boy ran home."


def test_clean_flavor_text_treats_non_digit_obfuscate_arg_as_one_block():
    assert clean_flavor_text("Agent {{Obfuscate|----}} arrived.") == "Agent ▇ arrived."


def test_clean_flavor_text_strips_bare_sic_template():
    assert clean_flavor_text("A pack of {{sic}} direwolves.") == "A pack of direwolves."


def test_clean_flavor_text_extracts_character_page_link_name():
    assert clean_flavor_text("As noted by {{Character Page Link|Sampo|ref=1}}, it's true.") == (
        "As noted by Sampo, it's true."
    )


def test_clean_flavor_text_drops_ja_and_zh_asides():
    assert clean_flavor_text("A pun on {{ja|魔法使い}} meaning magician.") == "A pun on meaning magician."
    assert clean_flavor_text("Grandmother, or {{zh|外婆|wàipó}} in Chinese.") == "Grandmother, or in Chinese."


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
