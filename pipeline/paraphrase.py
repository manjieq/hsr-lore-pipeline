"""Paraphrase scraped lore entries into short_text via a local Ollama model.

Usage:
    python pipeline/paraphrase.py <input.json> <output.json> [--limit N]

Reads a list of raw entries (as produced by ingest/wiki_scrape_*.py),
paraphrases any that don't already have an up-to-date short_text (compared
by raw_text_hash + PROMPT_VERSION), runs pipeline/validate.py on the result,
and writes the augmented list back out.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ollama

from pipeline.validate import validate_short_text

PROMPT_VERSION = "paraphrase_v1"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.txt"
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")

_PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def paraphrase_one(name: str, category: str, raw_text: str) -> str:
    # Plain string substitution rather than str.format(): the template
    # contains a literal {"short_text": "..."} JSON example, whose braces
    # would otherwise collide with format()'s placeholder syntax.
    prompt = (
        _PROMPT_TEMPLATE.replace("{name}", name)
        .replace("{category}", category)
        .replace("{raw_text}", raw_text)
    )
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0.4},
    )
    content = response["message"]["content"]
    data = json.loads(content)
    return data["short_text"].strip()


# qa_flags that pipeline/validate.py owns and recomputes from scratch each
# time it runs -- as opposed to scrape-level flags (e.g.
# flavor_text_unexpectedly_long) that come from ingest/wiki_scrape_*.py and
# must survive both a paraphrase run and a revalidate-only run untouched.
VALIDATE_OWNED_FLAGS = (
    "empty_short_text",
    "short_text_too_short",
    "short_text_too_long",
    "short_text_identical_to_raw",
    "possible_refusal_artifact",
    "possible_hallucinated_name",
)


def process_entries(entries: list[dict], limit: int | None = None) -> list[dict]:
    processed = 0
    for entry in entries:
        if limit is not None and processed >= limit:
            break
        if entry.get("qa_flags") and "flavor_text_unexpectedly_long" in entry["qa_flags"]:
            # Needs a human to trim/confirm the excerpt before we paraphrase it.
            continue
        if not entry.get("raw_text"):
            continue

        current_hash = _hash(entry["raw_text"])
        if (
            entry.get("raw_text_hash") == current_hash
            and entry.get("prompt_version") == PROMPT_VERSION
            and entry.get("short_text")
        ):
            continue  # unchanged since last paraphrase run

        short_text = paraphrase_one(entry["name"], entry["category"], entry["raw_text"])
        flags = list(entry.get("qa_flags") or [])
        flags = [f for f in flags if f not in VALIDATE_OWNED_FLAGS]
        flags.extend(validate_short_text(short_text, entry["raw_text"], entry["name"]))

        entry["short_text"] = short_text
        entry["prompt_version"] = PROMPT_VERSION
        entry["raw_text_hash"] = current_hash
        entry["qa_flags"] = flags
        processed += 1
        print(f"  paraphrased: {entry['name']} -> flags={flags}", file=sys.stderr)

    print(f"Paraphrased {processed} entr{'y' if processed == 1 else 'ies'} this run.", file=sys.stderr)
    return entries


def revalidate_entries(entries: list[dict]) -> list[dict]:
    """Re-run validate_short_text against each entry's *existing*
    short_text, without calling Ollama again. For when pipeline/validate.py's
    heuristic itself changes (as opposed to the source text or the prompt)
    and already-paraphrased entries just need their qa_flags refreshed, not
    reworded. Scrape-level flags are left untouched."""
    changed = 0
    for entry in entries:
        if not entry.get("short_text"):
            continue
        old_flags = list(entry.get("qa_flags") or [])
        kept = [f for f in old_flags if f not in VALIDATE_OWNED_FLAGS]
        new_flags = kept + validate_short_text(entry["short_text"], entry["raw_text"], entry["name"])
        if new_flags != old_flags:
            changed += 1
            print(f"  revalidated: {entry['name']}: {old_flags} -> {new_flags}", file=sys.stderr)
        entry["qa_flags"] = new_flags

    print(f"Revalidated {len(entries)} entries; {changed} changed.", file=sys.stderr)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Re-run QA checks on existing short_text without calling Ollama again "
        "(use after a pipeline/validate.py change; ignores --limit)",
    )
    args = parser.parse_args()

    entries = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
    entries = revalidate_entries(entries) if args.revalidate else process_entries(entries, limit=args.limit)
    Path(args.output_path).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
