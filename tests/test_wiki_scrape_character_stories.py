"""Tests for ingest/wiki_scrape_character_stories.py's scrape_one, with
get_page_wikitext mocked out -- no network access."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ingest.wiki_scrape_character_stories as scraper_module

LORE_WIKITEXT = (
    "{{Character Tabs}}\n"
    "==Character Introduction==\n"
    "{{Description|A drifter.}}\n"
    "==Character Stories==\n"
    "{{Character Story\n"
    "|text1    = A story about [[Elio]] and the Stellaron Hunters.\n"
    "|mention1 = Elio\n"
    "\n"
    "|text2    = A second, much longer story. " + ("Filler text. " * 400) + "\n"
    "|mention2 = \n"
    "}}\n"
)

NO_TEMPLATE_WIKITEXT = "{{Character Tabs}}\n==Character Introduction==\n{{Description|Just a blurb.}}\n"


@pytest.fixture
def mock_wikitext(monkeypatch):
    def _apply(wikitext=None, raises=None):
        def fake_get_page_wikitext(title, refresh=False):
            if raises is not None:
                raise raises
            return wikitext

        monkeypatch.setattr(scraper_module, "get_page_wikitext", fake_get_page_wikitext)

    return _apply


def test_scrape_one_returns_one_entry_per_numbered_story(mock_wikitext):
    mock_wikitext(LORE_WIKITEXT)

    entries = scraper_module.scrape_one("Kafka", refresh=False)

    assert len(entries) == 2
    assert entries[0]["id"] == "character-story-kafka-1"
    assert entries[1]["id"] == "character-story-kafka-2"
    assert entries[0]["category"] == "character_story"
    assert "Elio" in entries[0]["raw_text"]
    assert entries[0]["subtitle"] == "Character Story 1 of 2 · Kafka"


def test_scrape_one_names_are_unique_for_build_dataset_merge_key(mock_wikitext):
    # build_dataset.py's merge_entries keys existing entries by
    # (category, normalized name) -- if two stories from the same
    # character shared a name, one would silently clobber the other.
    import pipeline.build_dataset as build_dataset_module

    mock_wikitext(LORE_WIKITEXT)
    entries = scraper_module.scrape_one("Kafka", refresh=False)
    keys = {(e["category"], build_dataset_module.normalize_name(e["name"])) for e in entries}
    assert len(keys) == len(entries)


def test_scrape_one_flags_a_too_long_story(mock_wikitext):
    mock_wikitext(LORE_WIKITEXT)

    entries = scraper_module.scrape_one("Kafka", refresh=False)

    long_story = next(e for e in entries if e["id"].endswith("-2"))
    assert "flavor_text_unexpectedly_long" in long_story["qa_flags"]
    short_story = next(e for e in entries if e["id"].endswith("-1"))
    assert short_story["qa_flags"] == []


def test_scrape_one_returns_empty_list_when_no_lore_page(mock_wikitext):
    mock_wikitext(raises=RuntimeError("page not found"))
    assert scraper_module.scrape_one("Kafka", refresh=False) == []


def test_scrape_one_returns_empty_list_when_no_character_story_template(mock_wikitext):
    mock_wikitext(NO_TEMPLATE_WIKITEXT)
    assert scraper_module.scrape_one("Kafka", refresh=False) == []
