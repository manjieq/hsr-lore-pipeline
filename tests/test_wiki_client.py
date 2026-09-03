"""Tests for ingest/wiki_client.py's page_url. No network access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.wiki_client import page_url


def test_page_url_replaces_spaces_with_underscores():
    assert page_url("Night on the Milky Way") == "https://honkai-star-rail.fandom.com/wiki/Night_on_the_Milky_Way"


def test_page_url_leaves_common_title_punctuation_unencoded():
    # Colons, exclamation marks, apostrophes, ampersands, and commas are
    # common in real titles and read better unencoded (and already ship
    # this way for the 228 existing entries) -- e.g. "Talia: Kingdom of
    # Banditry", "Woof! Walk Time!", "Topaz & Numby".
    assert page_url("Talia: Kingdom of Banditry").endswith("Talia:_Kingdom_of_Banditry")
    assert page_url("Woof! Walk Time!").endswith("Woof!_Walk_Time!")
    assert page_url("Topaz & Numby").endswith("Topaz_&_Numby")


def test_page_url_percent_encodes_non_ascii_characters():
    # Some alternate-outfit character pages use a "•" (U+2022) separator,
    # e.g. "Himeko • Nova" -- a raw non-ASCII byte in a URL isn't
    # well-formed and must be percent-encoded.
    url = page_url("Himeko • Nova")
    assert url == "https://honkai-star-rail.fandom.com/wiki/Himeko_%E2%80%A2_Nova"
    assert "•" not in url


def test_page_url_supports_subpage_paths():
    assert page_url("Kafka/Lore") == "https://honkai-star-rail.fandom.com/wiki/Kafka/Lore"
