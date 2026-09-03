"""Deterministic "today's fact" picker, shared logic with
site/js/select-daily.js. Given a precomputed cycle (a shuffled list of entry
ids) and the date that cycle started rotating from, picks one id per calendar
day (UTC), skipping any id that's no longer eligible (e.g. un-reviewed or
flagged since the cycle was built).

Also builds/extends daily_cycle.json:
- First build: a seeded Fisher-Yates shuffle of all eligible entry ids, so
  the rotation order looks random but is reproducible.
- Later builds: newly-eligible ids are appended to the end of the existing
  cycle (not reshuffled), so already-posted history never changes.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timezone
from pathlib import Path

# Fixed seed: the shuffle only needs to look random, not be cryptographically
# unpredictable, and a fixed seed keeps the initial cycle order reproducible
# across environments/runs.
SHUFFLE_SEED = "hsr-lore-pipeline-daily-cycle-v1"

ENTRIES_PATH = Path(__file__).resolve().parent.parent / "site" / "data" / "entries.json"
CYCLE_PATH = Path(__file__).resolve().parent.parent / "site" / "data" / "daily_cycle.json"


def is_eligible(entry: dict) -> bool:
    return bool(entry.get("reviewed")) and not entry.get("qa_flags")


def select_daily_id(cycle_data: dict, entries_by_id: dict[str, dict], today: date) -> str | None:
    """Mirrors site/js/select-daily.js's selectDailyId exactly: any change
    here needs the same change made there, and vice versa.

    cycle_data is the parsed daily_cycle.json shape: {"cycle": [...ids],
    "cycle_start_date": "YYYY-MM-DD"}. today is a plain date (compared at UTC
    day granularity, matching the JS side's UTC-midnight normalization)."""
    cycle = cycle_data.get("cycle")
    if not cycle:
        return None

    start = date.fromisoformat(cycle_data["cycle_start_date"])
    days_since_start = (today - start).days

    length = len(cycle)
    index = days_since_start % length  # Python's % is already non-negative for a positive length

    for _ in range(length):
        entry_id = cycle[index]
        entry = entries_by_id.get(entry_id)
        if entry and is_eligible(entry):
            return entry_id
        index = (index + 1) % length
    return None


def build_or_extend_cycle(entries: list[dict], existing_cycle_data: dict | None) -> dict:
    eligible_ids = [e["id"] for e in entries if is_eligible(e)]

    if existing_cycle_data is None:
        rng = random.Random(SHUFFLE_SEED)
        shuffled = list(eligible_ids)
        rng.shuffle(shuffled)
        return {
            "cycle": shuffled,
            "cycle_start_date": date.today().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    existing_ids = set(existing_cycle_data["cycle"])
    new_ids = [eid for eid in eligible_ids if eid not in existing_ids]
    return {
        "cycle": existing_cycle_data["cycle"] + new_ids,
        "cycle_start_date": existing_cycle_data["cycle_start_date"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Rebuild the cycle from scratch (new shuffle, new cycle_start_date) instead of extending the existing one",
    )
    args = parser.parse_args()

    entries = json.loads(ENTRIES_PATH.read_text(encoding="utf-8"))
    existing = None
    if not args.fresh and CYCLE_PATH.exists():
        existing = json.loads(CYCLE_PATH.read_text(encoding="utf-8"))

    cycle_data = build_or_extend_cycle(entries, existing)
    CYCLE_PATH.write_text(json.dumps(cycle_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cycle_data['cycle'])} eligible entries -> {CYCLE_PATH}")


if __name__ == "__main__":
    main()
