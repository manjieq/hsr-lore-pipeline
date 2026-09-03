"""Orchestrates ingest -> paraphrase -> validate output into the single
canonical dataset the site reads: site/data/entries.json (+ an extended
site/data/daily_cycle.json).

This does NOT run the scraper or call Ollama itself -- those are separate,
slower steps (see ingest/wiki_scrape_*.py and pipeline/paraphrase.py) whose
output already lives under data/raw_cache/. build_dataset.py's only job is
merging that raw_cache output into the live dataset:

- Matches new entries against existing ones by (category, normalized name)
  rather than id, since ids are derived by each scraper's own slugify()
  and can differ from ids used by earlier hand-authored sample data for the
  same real item (e.g. apostrophe handling). The real pipeline-derived id
  always wins once a wiki-scraped counterpart exists.
- Entries with no short_text (nothing to show yet, e.g. an unreleased item
  with an empty wiki description) are left out of the dataset entirely
  rather than included as a blank card.
- reviewed is set automatically: true for entries with a short_text and no
  qa_flags, false otherwise -- flagged entries stay out of the site (both
  rotation and browse-all, per site/js/app.js) until a human clears the
  flag and re-runs this script. This auto-approve policy was a deliberate
  call, not the default; a project with lower quality bar or higher trust
  requirements might want a stricter human-review-every-entry gate instead.
- date_added is preserved for entries that already existed (matched by
  name); date_updated only changes when raw_text_hash actually changed.
- Adding a new category later is meant to be: add its raw_cache path to
  CATEGORY_SOURCES below and everything else here keeps working unchanged.

Usage:
    python pipeline/build_dataset.py
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.select_daily import build_or_extend_cycle

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRIES_PATH = REPO_ROOT / "site" / "data" / "entries.json"
CYCLE_PATH = REPO_ROOT / "site" / "data" / "daily_cycle.json"

# category -> path to that category's paraphrased raw_cache output.
CATEGORY_SOURCES = {
    "light_cone": REPO_ROOT / "data" / "raw_cache" / "lightcones_paraphrased_full.json",
}


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def merge_entries(existing_entries: list[dict], new_raw_entries: list[dict], today: str) -> tuple[list[dict], dict]:
    by_key = {(e["category"], normalize_name(e["name"])): e for e in existing_entries}
    stats = {"added": 0, "updated": 0, "unchanged": 0, "skipped_no_short_text": 0, "held_back_flagged": 0}

    for raw in new_raw_entries:
        if not raw.get("short_text"):
            stats["skipped_no_short_text"] += 1
            continue

        key = (raw["category"], normalize_name(raw["name"]))
        prior = by_key.get(key)

        entry = dict(raw)
        entry["reviewed"] = bool(entry.get("short_text")) and not entry.get("qa_flags")
        if not entry["reviewed"]:
            stats["held_back_flagged"] += 1

        if prior is None:
            entry["date_added"] = today
            entry["date_updated"] = today
            stats["added"] += 1
        elif prior.get("raw_text_hash") != entry.get("raw_text_hash"):
            entry["date_added"] = prior.get("date_added", today)
            entry["date_updated"] = today
            stats["updated"] += 1
        else:
            entry["date_added"] = prior.get("date_added", today)
            entry["date_updated"] = prior.get("date_updated", today)
            stats["unchanged"] += 1

        by_key[key] = entry

    return list(by_key.values()), stats


def main() -> None:
    existing_entries = json.loads(ENTRIES_PATH.read_text(encoding="utf-8")) if ENTRIES_PATH.exists() else []
    today = date.today().isoformat()

    merged = existing_entries
    total_stats = {"added": 0, "updated": 0, "unchanged": 0, "skipped_no_short_text": 0, "held_back_flagged": 0}
    for category, source_path in CATEGORY_SOURCES.items():
        if not source_path.exists():
            print(f"skip {category}: {source_path} not found", file=sys.stderr)
            continue
        raw_entries = json.loads(source_path.read_text(encoding="utf-8"))
        merged, stats = merge_entries(merged, raw_entries, today)
        for k, v in stats.items():
            total_stats[k] += v
        print(f"{category}: {stats}", file=sys.stderr)

    ENTRIES_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(merged)} total entries -> {ENTRIES_PATH}", file=sys.stderr)
    print(f"Totals: {total_stats}", file=sys.stderr)

    existing_cycle = json.loads(CYCLE_PATH.read_text(encoding="utf-8")) if CYCLE_PATH.exists() else None
    cycle_data = build_or_extend_cycle(merged, existing_cycle)
    CYCLE_PATH.write_text(json.dumps(cycle_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Cycle now has {len(cycle_data['cycle'])} eligible entries -> {CYCLE_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
