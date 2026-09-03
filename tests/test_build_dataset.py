"""Tests for pipeline/build_dataset.py's merge_entries -- the function that
runs on every rebuild to fold freshly scraped+paraphrased raw_cache output
into the single committed site/data/entries.json."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.build_dataset import merge_entries, normalize_name


def _raw(name="Night on the Milky Way", category="light_cone", short_text="A story.",
         raw_text_hash="hash1", qa_flags=None, **overrides):
    entry = {
        "id": "light-cone-night-on-the-milky-way",
        "category": category,
        "name": name,
        "short_text": short_text,
        "raw_text_hash": raw_text_hash,
        "qa_flags": qa_flags or [],
    }
    entry.update(overrides)
    return entry


def test_normalize_name_strips_case_and_punctuation():
    assert normalize_name("Night on the Milky Way!") == normalize_name("NIGHT ON THE MILKY WAY")


def test_new_entry_is_added_with_both_dates_set_to_today():
    merged, stats = merge_entries([], [_raw()], today="2026-09-03")
    assert len(merged) == 1
    assert merged[0]["date_added"] == "2026-09-03"
    assert merged[0]["date_updated"] == "2026-09-03"
    assert stats["added"] == 1 and stats["updated"] == 0 and stats["unchanged"] == 0


def test_unchanged_hash_keeps_both_original_dates():
    existing = [_raw(date_added="2026-01-01", date_updated="2026-01-01")]
    merged, stats = merge_entries(existing, [_raw()], today="2026-09-03")
    assert merged[0]["date_added"] == "2026-01-01"
    assert merged[0]["date_updated"] == "2026-01-01"
    assert stats["unchanged"] == 1 and stats["added"] == 0


def test_changed_hash_bumps_date_updated_but_preserves_date_added():
    existing = [_raw(raw_text_hash="hash1", date_added="2026-01-01", date_updated="2026-01-01")]
    new_raw = [_raw(raw_text_hash="hash2")]
    merged, stats = merge_entries(existing, new_raw, today="2026-09-03")
    assert merged[0]["date_added"] == "2026-01-01"  # preserved
    assert merged[0]["date_updated"] == "2026-09-03"  # bumped
    assert stats["updated"] == 1


def test_entries_without_short_text_are_skipped_entirely():
    merged, stats = merge_entries([], [_raw(short_text="")], today="2026-09-03")
    assert merged == []
    assert stats["skipped_no_short_text"] == 1


def test_reviewed_true_iff_short_text_present_and_no_qa_flags():
    merged, _ = merge_entries([], [_raw(qa_flags=[])], today="2026-09-03")
    assert merged[0]["reviewed"] is True

    merged, stats = merge_entries([], [_raw(qa_flags=["possible_hallucinated_name"])], today="2026-09-03")
    assert merged[0]["reviewed"] is False
    assert stats["held_back_flagged"] == 1


def test_matches_existing_entry_by_normalized_name_not_by_id():
    # An earlier hand-authored sample entry might use a different id scheme
    # than the real scraper's slugify() for the same real item -- matching
    # must go by (category, normalized name), and the new pipeline-derived
    # id replaces the old one once a real scrape exists.
    existing = [_raw(id="sample-milky-way", date_added="2026-01-01", date_updated="2026-01-01")]
    new_raw = [_raw(id="light-cone-night-on-the-milky-way", raw_text_hash="hash1")]
    merged, stats = merge_entries(existing, new_raw, today="2026-09-03")
    assert len(merged) == 1  # no duplicate
    assert merged[0]["id"] == "light-cone-night-on-the-milky-way"
    assert merged[0]["date_added"] == "2026-01-01"  # history preserved
    assert stats["unchanged"] == 1


def test_same_name_different_category_are_not_merged():
    existing = [_raw(category="light_cone")]
    new_raw = [_raw(category="relic_set", raw_text_hash="hash2")]
    merged, stats = merge_entries(existing, new_raw, today="2026-09-03")
    assert len(merged) == 2
    assert stats["added"] == 1
