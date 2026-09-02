"""Scrape light cone flavor text from the HSR Fandom wiki.

Usage:
    python ingest/wiki_scrape_lightcones.py [--limit N] [--refresh]

Writes a raw (pre-paraphrase) JSON list to
data/raw_cache/lightcones_wiki_raw.json — one entry per light cone with the
fields the pipeline schema needs except short_text/prompt_version, which are
added later by pipeline/paraphrase.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.wiki_client import get_category_members, get_page_wikitext
from ingest.wikitext_utils import clean_flavor_text, extract_infobox_field, extract_template_arg

CATEGORY = "Category:Light Cones"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw_cache" / "lightcones_wiki_raw.json"

# In-game flavor text is inherently short (a handful of sentences); this is a
# sanity ceiling, not a truncation policy — if a page's Description template
# comes back far longer than any real light cone description, something's
# wrong with the extraction and it's better to flag it than silently ingest.
MAX_REASONABLE_FLAVOR_CHARS = 700


def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"light-cone-{slug}"


def scrape_one(title: str, refresh: bool) -> dict | None:
    wikitext = get_page_wikitext(title, refresh=refresh)

    flavor_raw = extract_template_arg(wikitext, "Description")
    if not flavor_raw:
        return {
            "id": slugify(title),
            "category": "light_cone",
            "name": title,
            "subtitle": "Light Cone",
            "source_type": "wiki",
            "source_url": "https://honkai-star-rail.fandom.com/wiki/" + title.replace(" ", "_"),
            "raw_text": "",
            "image_url": None,
            "game_version_seen": None,
            "qa_flags": ["no_description_template"],
            "reviewed": False,
        }
    flavor = clean_flavor_text(flavor_raw)

    rarity = extract_infobox_field(wikitext, "rarity")
    path = extract_infobox_field(wikitext, "effect_path")
    subtitle_bits = []
    if rarity and rarity.isdigit():
        subtitle_bits.append(f"{rarity}★ Light Cone")
    else:
        subtitle_bits.append("Light Cone")
    if path:
        subtitle_bits.append(path)
    subtitle = " · ".join(subtitle_bits)

    qa_flags = []
    if len(flavor) > MAX_REASONABLE_FLAVOR_CHARS:
        qa_flags.append("flavor_text_unexpectedly_long")
    if len(flavor) < 10:
        qa_flags.append("flavor_text_too_short")

    return {
        "id": slugify(title),
        "category": "light_cone",
        "name": title,
        "subtitle": subtitle,
        "source_type": "wiki",
        "source_url": "https://honkai-star-rail.fandom.com/wiki/" + title.replace(" ", "_"),
        "raw_text": flavor,
        "image_url": None,
        "game_version_seen": None,
        "qa_flags": qa_flags,
        "reviewed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only scrape the first N pages (for spot-checking)")
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
        if entry is None:
            continue
        results.append(entry)
        if entry.get("qa_flags"):
            flagged.append((title, entry["qa_flags"]))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nScraped {len(results)} pages -> {OUT_PATH}", file=sys.stderr)
    if flagged:
        print(f"{len(flagged)} page(s) flagged for review:", file=sys.stderr)
        for title, flags in flagged:
            print(f"  - {title}: {flags}", file=sys.stderr)


if __name__ == "__main__":
    main()
