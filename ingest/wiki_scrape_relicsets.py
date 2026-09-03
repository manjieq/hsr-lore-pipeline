"""Scrape relic-set flavor text from the HSR Fandom wiki.

Covers both 4-piece Cavern Relics and 2-piece Planar Ornaments -- the wiki
files both under Category:Relic Sets, and the site treats them as one
"relic_set" category, matching the existing hand-authored sample data.

Unlike light cones, a relic set's own page has no inline flavor text -- its
"Lore" section transcludes a DPL query (Template:Relic Lore) that stitches
together each individual piece page's own "==Description==" section (head,
hand, body, feet -- or planarsphere, linkrope for ornaments) into one
continuous story. This scraper does the same stitching manually: fetch the
set page to find its piece page titles, fetch each piece page, extract and
clean each one's Description section, and join them in piece order.

Usage:
    python ingest/wiki_scrape_relicsets.py [--limit N] [--refresh]

Writes a raw (pre-paraphrase) JSON list to
data/raw_cache/relicsets_wiki_raw.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.wiki_client import get_category_members, get_page_wikitext
from ingest.wikitext_utils import clean_flavor_text, extract_infobox_field, extract_section

CATEGORY = "Category:Relic Sets"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw_cache" / "relicsets_wiki_raw.json"

# A relic set's raw_text is the concatenation of up to 4 piece descriptions
# (vs. a light cone's single description). Calibrated the same way the light
# cone version was: a first full scrape of all 60 sets against an initial
# 6000 guess flagged 9 of them, all spot-checked as legitimate long
# narratives (median ~5100 chars, real max ~7980), so this was raised well
# above that observed max rather than guessed again.
MAX_REASONABLE_FLAVOR_CHARS = 9500

CAVERN_RELIC_PIECES = [("head", "Head"), ("hand", "Hand"), ("body", "Body"), ("feet", "Feet")]
PLANAR_ORNAMENT_PIECES = [("planarsphere", "Planar Sphere"), ("linkrope", "Link Rope")]


def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"relic-set-{slug}"


def piece_page_url(title: str) -> str:
    return "https://honkai-star-rail.fandom.com/wiki/" + title.replace(" ", "_")


def scrape_one(title: str, refresh: bool) -> dict:
    set_wikitext = get_page_wikitext(title, refresh=refresh)
    source_url = piece_page_url(title)

    piece_fields = CAVERN_RELIC_PIECES if extract_infobox_field(set_wikitext, "head") else PLANAR_ORNAMENT_PIECES
    is_ornament = piece_fields is PLANAR_ORNAMENT_PIECES

    piece_texts = []
    qa_flags = []
    for field_name, piece_label in piece_fields:
        piece_title = extract_infobox_field(set_wikitext, field_name)
        if not piece_title:
            qa_flags.append(f"missing_piece_field:{piece_label}")
            continue
        piece_wikitext = get_page_wikitext(piece_title, refresh=refresh)
        section = extract_section(piece_wikitext, "Description")
        if not section:
            qa_flags.append(f"missing_piece_description:{piece_label}")
            continue
        piece_texts.append(clean_flavor_text(section))

    raw_text = " ".join(piece_texts)

    if not raw_text:
        qa_flags.append("no_lore_text")
    else:
        if len(raw_text) > MAX_REASONABLE_FLAVOR_CHARS:
            qa_flags.append("flavor_text_unexpectedly_long")
        if len(raw_text) < 10:
            qa_flags.append("flavor_text_too_short")

    rarity_field = extract_infobox_field(set_wikitext, "rarity") or ""
    digits = [c for c in rarity_field if c.isdigit()]
    top_rarity = max(digits) if digits else None
    kind_label = "Planar Ornament" if is_ornament else "Relic Set"
    subtitle = f"{top_rarity}★ {kind_label}" if top_rarity else kind_label

    return {
        "id": slugify(title),
        "category": "relic_set",
        "name": title,
        "subtitle": subtitle,
        "source_type": "wiki",
        "source_url": source_url,
        "raw_text": raw_text,
        "image_url": None,
        "game_version_seen": None,
        "qa_flags": qa_flags,
        "reviewed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only scrape the first N sets (for spot-checking)")
    parser.add_argument("--refresh", action="store_true", help="Bypass the cache and re-fetch every page")
    args = parser.parse_args()

    titles = get_category_members(CATEGORY, refresh=args.refresh)
    if args.limit:
        titles = titles[: args.limit]

    results = []
    flagged = []
    for i, title in enumerate(titles, 1):
        print(f"[{i}/{len(titles)}] {title}", file=sys.stderr)
        entry = scrape_one(title, refresh=args.refresh)
        results.append(entry)
        if entry.get("qa_flags"):
            flagged.append((title, entry["qa_flags"]))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nScraped {len(results)} sets -> {OUT_PATH}", file=sys.stderr)
    if flagged:
        print(f"{len(flagged)} set(s) flagged for review:", file=sys.stderr)
        for title, flags in flagged:
            print(f"  - {title}: {flags}", file=sys.stderr)


if __name__ == "__main__":
    main()
