"""Scrape character-story flavor text from the HSR Fandom wiki.

Unlike light cones (one Description per page) or relic sets (one
description per piece, stitched together), a character's numbered
"Character Stories" all live in a single {{Character Story|text1=...
|mention1=...|text2=...|...}} template on that character's own
"<Name>/Lore" subpage -- see ingest/wikitext_utils.py's
extract_template_params, spot-checked against the live wiki (e.g.
Kafka/Lore) before this scraper was written.

Each numbered story becomes its own dataset entry rather than one entry
per character: the stories are already self-contained vignettes, and
concatenating several of them into one raw_text risks the same
too-long-to-paraphrase problem hit with a dense relic set's lore (see
docs/PLANNING.md history / CLAUDE.md). This also means, unlike the other
two scrapers, scrape_one returns a *list* of entries (0 or more) per
character, not a single entry-or-None.

Usage:
    python ingest/wiki_scrape_character_stories.py [--limit N] [--refresh]

Writes a raw (pre-paraphrase) JSON list to
data/raw_cache/characterstories_wiki_raw.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.wiki_client import get_category_members, get_page_wikitext, page_url
from ingest.wikitext_utils import clean_flavor_text, extract_template_params

CATEGORY = "Category:Playable Characters"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw_cache" / "characterstories_wiki_raw.json"

# A per-story sanity ceiling, not a truncation policy -- same spirit as the
# light-cone and relic-set scrapers' MAX_REASONABLE_FLAVOR_CHARS. Originally
# set to 2000 from a 5-character spot check; a full scrape of all 86
# characters (430 stories) showed that's too low for a lot of real entries
# (median ~1587 chars, real max ~4479), so this was raised well above the
# observed real max to stop flagging genuine content, matching how the
# other two categories' ceilings were calibrated.
MAX_REASONABLE_FLAVOR_CHARS = 5000

# Highest story index to look for per character. HSR characters have had
# up to 5-6 numbered stories as of this writing; scanning a bit past that
# is cheap and future-proofs against characters gaining more later.
MAX_STORY_INDEX = 10

# Write partial progress to OUT_PATH every this many characters, so a crash
# or interrupt partway through a long scrape doesn't discard everything
# fetched so far.
CHECKPOINT_EVERY = 20


def slugify(name: str, index: int) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"character-story-{slug}-{index}"


def scrape_one(character_name: str, refresh: bool) -> list[dict]:
    """Returns one entry per numbered Character Story found for this
    character, or an empty list if the character has no /Lore page or no
    Character Story template on it (e.g. very recently added characters
    whose wiki page isn't fully built out yet)."""
    try:
        wikitext = get_page_wikitext(f"{character_name}/Lore", refresh=refresh)
    except Exception:
        return []

    params = extract_template_params(wikitext, "Character Story")
    if not params:
        return []

    story_indices = [i for i in range(1, MAX_STORY_INDEX + 1) if params.get(f"text{i}")]
    if not story_indices:
        return []

    total = len(story_indices)
    source_url = page_url(f"{character_name}/Lore")
    entries = []
    for position, index in enumerate(story_indices, 1):
        flavor = clean_flavor_text(params[f"text{index}"])

        qa_flags = []
        if len(flavor) > MAX_REASONABLE_FLAVOR_CHARS:
            qa_flags.append("flavor_text_unexpectedly_long")
        if len(flavor) < 10:
            qa_flags.append("flavor_text_too_short")

        entries.append(
            {
                "id": slugify(character_name, index),
                "category": "character_story",
                "name": f"{character_name} — Story {index}",
                "subtitle": f"Character Story {position} of {total} · {character_name}",
                "source_type": "wiki",
                "source_url": source_url,
                "raw_text": flavor,
                "image_url": None,
                "game_version_seen": None,
                "qa_flags": qa_flags,
                "reviewed": False,
            }
        )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only scrape the first N characters (for spot-checking)")
    parser.add_argument("--refresh", action="store_true", help="Bypass the cache and re-fetch every page")
    args = parser.parse_args()

    titles = get_category_members(CATEGORY, refresh=args.refresh)
    if args.limit:
        titles = titles[: args.limit]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = []
    flagged = []
    no_stories = []
    errors = []
    for i, title in enumerate(titles, 1):
        print(f"[{i}/{len(titles)}] {title}", file=sys.stderr)
        try:
            entries = scrape_one(title, refresh=args.refresh)
        except Exception as exc:  # a single malformed/missing page shouldn't lose the whole run
            errors.append((title, str(exc)))
            print(f"  ERROR scraping {title}: {exc}", file=sys.stderr)
            continue

        if not entries:
            no_stories.append(title)
            continue

        results.extend(entries)
        for entry in entries:
            if entry.get("qa_flags"):
                flagged.append((entry["name"], entry["qa_flags"]))

        if i % CHECKPOINT_EVERY == 0:
            OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ...checkpointed {len(results)} stories -> {OUT_PATH}", file=sys.stderr)

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nScraped {len(results)} stories from {len(titles)} characters -> {OUT_PATH}", file=sys.stderr)
    if flagged:
        print(f"{len(flagged)} stor{'y' if len(flagged) == 1 else 'ies'} flagged for review:", file=sys.stderr)
        for name, flags in flagged:
            print(f"  - {name}: {flags}", file=sys.stderr)
    if no_stories:
        print(f"{len(no_stories)} character(s) had no /Lore page or Character Story template:", file=sys.stderr)
        for title in no_stories:
            print(f"  - {title}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} character(s) failed to scrape and were skipped (re-run to retry):", file=sys.stderr)
        for title, err in errors:
            print(f"  - {title}: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
