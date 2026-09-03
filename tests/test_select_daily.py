"""Tests for pipeline/select_daily.py.

Pins fixed dates against the real committed site/data/daily_cycle.json +
entries.json so a test failure here would also mean the deployed JS version
(site/js/select-daily.js) is producing the wrong id for that date -- the two
implementations are meant to be exact mirrors of each other. Cross-checked
once by hand in a browser console per docs/PLANNING.md; keep them in sync
manually if the JS changes.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.select_daily import build_or_extend_cycle, select_daily_id

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRIES = json.loads((REPO_ROOT / "site" / "data" / "entries.json").read_text(encoding="utf-8"))
CYCLE_DATA = json.loads((REPO_ROOT / "site" / "data" / "daily_cycle.json").read_text(encoding="utf-8"))
ENTRIES_BY_ID = {e["id"]: e for e in ENTRIES}

# All 10 committed sample entries are reviewed with no qa_flags, so the cycle
# order below is exactly cycle[index] for days_since_start = index.
EXPECTED_CYCLE_ORDER = [
    "light-cone-night-on-the-milky-way",
    "light-cone-but-the-battle-isnt-over",
    "light-cone-something-irreplaceable",
    "light-cone-in-the-night",
    "light-cone-time-waits-for-no-one",
    "relic-set-genius-of-brilliant-stars",
    "relic-set-pioneer-diver-of-dead-waters",
    "relic-set-talia-kingdom-of-banditry",
    "relic-set-firmament-frontline-glamoth",
    "relic-set-knight-of-purity-palace",
]


def test_committed_cycle_matches_expected_order():
    # Sanity check that the fixtures below still match what's on disk; if
    # this fails, daily_cycle.json changed and the pinned dates need updating.
    assert CYCLE_DATA["cycle"] == EXPECTED_CYCLE_ORDER
    assert CYCLE_DATA["cycle_start_date"] == "2026-09-03"


def test_cycle_start_date_picks_first_entry():
    assert select_daily_id(CYCLE_DATA, ENTRIES_BY_ID, date(2026, 9, 3)) == EXPECTED_CYCLE_ORDER[0]


def test_next_day_picks_second_entry():
    assert select_daily_id(CYCLE_DATA, ENTRIES_BY_ID, date(2026, 9, 4)) == EXPECTED_CYCLE_ORDER[1]


def test_wraps_around_after_full_cycle():
    # 10 days after the start, with a 10-entry cycle, wraps back to index 0.
    assert select_daily_id(CYCLE_DATA, ENTRIES_BY_ID, date(2026, 9, 13)) == EXPECTED_CYCLE_ORDER[0]


def test_date_before_cycle_start_still_returns_a_valid_id():
    # A day before cycle_start_date shouldn't throw or return None; it wraps
    # to the last entry (days_since_start = -1, Python's % keeps it positive).
    assert select_daily_id(CYCLE_DATA, ENTRIES_BY_ID, date(2026, 9, 2)) == EXPECTED_CYCLE_ORDER[-1]


def test_empty_cycle_returns_none():
    assert select_daily_id({"cycle": [], "cycle_start_date": "2026-09-03"}, ENTRIES_BY_ID, date(2026, 9, 3)) is None


def test_skips_ineligible_entries():
    cycle_data = {"cycle": ["a", "b", "c"], "cycle_start_date": "2026-01-01"}
    entries_by_id = {
        "a": {"reviewed": False, "qa_flags": []},  # not reviewed
        "b": {"reviewed": True, "qa_flags": ["possible_hallucinated_name"]},  # flagged
        "c": {"reviewed": True, "qa_flags": []},  # eligible
    }
    # days_since_start = 0 would normally pick "a", but it's ineligible, then
    # "b" is also ineligible, so it falls through to "c".
    assert select_daily_id(cycle_data, entries_by_id, date(2026, 1, 1)) == "c"


def test_all_ineligible_returns_none():
    cycle_data = {"cycle": ["a", "b"], "cycle_start_date": "2026-01-01"}
    entries_by_id = {
        "a": {"reviewed": False, "qa_flags": []},
        "b": {"reviewed": True, "qa_flags": ["possible_hallucinated_name"]},
    }
    assert select_daily_id(cycle_data, entries_by_id, date(2026, 1, 1)) is None


def test_build_cycle_from_scratch_includes_only_eligible_ids_exactly_once():
    entries = [
        {"id": "x", "reviewed": True, "qa_flags": []},
        {"id": "y", "reviewed": False, "qa_flags": []},
        {"id": "z", "reviewed": True, "qa_flags": ["possible_hallucinated_name"]},
        {"id": "w", "reviewed": True, "qa_flags": []},
    ]
    cycle_data = build_or_extend_cycle(entries, existing_cycle_data=None)
    assert sorted(cycle_data["cycle"]) == ["w", "x"]


def test_build_cycle_from_scratch_is_deterministic():
    entries = [{"id": f"e{i}", "reviewed": True, "qa_flags": []} for i in range(20)]
    first = build_or_extend_cycle(entries, existing_cycle_data=None)
    second = build_or_extend_cycle(entries, existing_cycle_data=None)
    assert first["cycle"] == second["cycle"]


def test_extend_appends_new_ids_without_reshuffling_existing_order():
    existing = {"cycle": ["b", "a"], "cycle_start_date": "2026-01-01", "generated_at": "..."}
    entries = [
        {"id": "a", "reviewed": True, "qa_flags": []},
        {"id": "b", "reviewed": True, "qa_flags": []},
        {"id": "c", "reviewed": True, "qa_flags": []},  # newly eligible
    ]
    result = build_or_extend_cycle(entries, existing_cycle_data=existing)
    assert result["cycle"][:2] == ["b", "a"]  # existing order untouched
    assert result["cycle"][2:] == ["c"]  # new id appended at the end
    assert result["cycle_start_date"] == "2026-01-01"  # unchanged


def test_extend_does_not_duplicate_already_present_ids():
    existing = {"cycle": ["a"], "cycle_start_date": "2026-01-01", "generated_at": "..."}
    entries = [{"id": "a", "reviewed": True, "qa_flags": []}]
    result = build_or_extend_cycle(entries, existing_cycle_data=existing)
    assert result["cycle"] == ["a"]


def test_extend_prunes_orphaned_ids_but_keeps_ineligible_existing_ones():
    # "old" no longer corresponds to any entry at all (e.g. it was replaced
    # by a differently-slugged id) and should be dropped. "b" still exists
    # but is currently ineligible (unreviewed) and must be kept in place,
    # since select_daily_id relies on cycle positions staying stable.
    existing = {"cycle": ["old", "a", "b"], "cycle_start_date": "2026-01-01", "generated_at": "..."}
    entries = [
        {"id": "a", "reviewed": True, "qa_flags": []},
        {"id": "b", "reviewed": False, "qa_flags": []},
        {"id": "c", "reviewed": True, "qa_flags": []},  # newly eligible
    ]
    result = build_or_extend_cycle(entries, existing_cycle_data=existing)
    assert result["cycle"] == ["a", "b", "c"]
