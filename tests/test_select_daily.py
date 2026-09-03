"""Tests for pipeline/select_daily.py.

The pinned-date tests use a small synthetic fixture rather than the real
committed site/data/daily_cycle.json + entries.json, so they don't churn
every time build_dataset.py legitimately changes the live dataset (learned
the hard way: the first version of this file hardcoded the 10-entry sample
cycle's exact order, which broke the moment Phase 9 grew it to 173 entries).
The real committed files still get a light structural sanity check at the
bottom, and cross-checked once by hand against site/js/select-daily.js via
`node -e` per docs/PLANNING.md -- keep the two implementations in sync
manually if either changes.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.select_daily import build_or_extend_cycle, select_daily_id

REPO_ROOT = Path(__file__).resolve().parent.parent

FIXTURE_CYCLE = {
    "cycle": ["id-a", "id-b", "id-c", "id-d", "id-e"],
    "cycle_start_date": "2026-09-03",
    "generated_at": "2026-09-03T00:00:00Z",
}
FIXTURE_ENTRIES_BY_ID = {eid: {"reviewed": True, "qa_flags": []} for eid in FIXTURE_CYCLE["cycle"]}


def test_cycle_start_date_picks_first_entry():
    assert select_daily_id(FIXTURE_CYCLE, FIXTURE_ENTRIES_BY_ID, date(2026, 9, 3)) == "id-a"


def test_next_day_picks_second_entry():
    assert select_daily_id(FIXTURE_CYCLE, FIXTURE_ENTRIES_BY_ID, date(2026, 9, 4)) == "id-b"


def test_wraps_around_after_full_cycle():
    # 5 days after the start, with a 5-entry cycle, wraps back to index 0.
    assert select_daily_id(FIXTURE_CYCLE, FIXTURE_ENTRIES_BY_ID, date(2026, 9, 8)) == "id-a"


def test_date_before_cycle_start_still_returns_a_valid_id():
    # A day before cycle_start_date shouldn't throw or return None; it wraps
    # to the last entry (days_since_start = -1, Python's % keeps it positive).
    assert select_daily_id(FIXTURE_CYCLE, FIXTURE_ENTRIES_BY_ID, date(2026, 9, 2)) == "id-e"


def test_empty_cycle_returns_none():
    assert select_daily_id({"cycle": [], "cycle_start_date": "2026-09-03"}, FIXTURE_ENTRIES_BY_ID, date(2026, 9, 3)) is None


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


# --- Sanity checks against the real committed dataset ---
# Deliberately not pinning exact ids/order here (see module docstring) --
# just structural invariants that should hold no matter how the dataset
# grows.

def test_committed_dataset_is_well_formed():
    entries = json.loads((REPO_ROOT / "site" / "data" / "entries.json").read_text(encoding="utf-8"))
    cycle_data = json.loads((REPO_ROOT / "site" / "data" / "daily_cycle.json").read_text(encoding="utf-8"))
    entries_by_id = {e["id"]: e for e in entries}

    assert len(entries_by_id) == len(entries), "duplicate ids in entries.json"
    assert len(set(cycle_data["cycle"])) == len(cycle_data["cycle"]), "duplicate ids in daily_cycle.json"
    date.fromisoformat(cycle_data["cycle_start_date"])  # raises if malformed

    for entry_id in cycle_data["cycle"]:
        assert entry_id in entries_by_id, f"{entry_id} in daily_cycle.json has no matching entry"

    for entry in entries:
        if entry["reviewed"] and not entry["qa_flags"]:
            assert entry["id"] in cycle_data["cycle"], f"{entry['id']} is eligible but missing from the cycle"

    # The picker should return a real, currently-eligible id for today.
    todays_id = select_daily_id(cycle_data, entries_by_id, date.today())
    assert todays_id is not None
    assert entries_by_id[todays_id]["reviewed"] and not entries_by_id[todays_id]["qa_flags"]
