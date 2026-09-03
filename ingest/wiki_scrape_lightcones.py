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

from ingest.wiki_client import get_category_members, get_page_wikitext, page_url
from ingest.wikitext_utils import clean_flavor_text, extract_infobox_field, extract_template_arg

CATEGORY = "Category:Light Cones"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw_cache" / "lightcones_wiki_raw.json"

# Sanity ceiling, not a truncation policy — if a page's Description template
# comes back far longer than any real light cone description, something's
# wrong with the extraction and it's better to flag it than silently ingest.
# Originally set to 700 assuming flavor text was always a handful of
# sentences; a full scrape of all 169 light cones showed that's wrong for a
# lot of real entries (median ~475 chars, but many narrative-style 5-star
# descriptions legitimately run 1000-2000+ chars), so this was raised well
# above the observed real max (~2030 chars) to stop flagging genuine content.
MAX_REASONABLE_FLAVOR_CHARS = 3000

# Write partial progress to OUT_PATH every this many pages, so a crash or
# interrupt partway through a long scrape doesn't discard everything fetched
# so far (each page fetch is itself cached by wiki_client, but the raw_cache
# *output list* was previously only written once, at the very end).
CHECKPOINT_EVERY = 20


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
            "source_url": page_url(title),
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
        "source_url": page_url(title),
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

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = []
    flagged = []
    errors = []
    for i, title in enumerate(titles, 1):
        print(f"[{i}/{len(titles)}] {title}", file=sys.stderr)
        try:
            entry = scrape_one(title, refresh=args.refresh)
        except Exception as exc:  # a single malformed/missing page shouldn't lose the whole run
            errors.append((title, str(exc)))
            print(f"  ERROR scraping {title}: {exc}", file=sys.stderr)
            continue
        if entry is None:
            continue
        results.append(entry)
        if entry.get("qa_flags"):
            flagged.append((title, entry["qa_flags"]))

        if i % CHECKPOINT_EVERY == 0:
            OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ...checkpointed {len(results)} pages -> {OUT_PATH}", file=sys.stderr)

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nScraped {len(results)} pages -> {OUT_PATH}", file=sys.stderr)
    if flagged:
        print(f"{len(flagged)} page(s) flagged for review:", file=sys.stderr)
        for title, flags in flagged:
            print(f"  - {title}: {flags}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} page(s) failed to scrape and were skipped (re-run to retry):", file=sys.stderr)
        for title, err in errors:
            print(f"  - {title}: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
