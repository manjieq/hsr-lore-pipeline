# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A zero-cost pipeline that scrapes Honkai: Star Rail lore text (light cones
and relic sets) from the Fandom wiki, paraphrases it into short hooks via a
local Ollama model, QA-checks the result deterministically, and serves it as
a static site (GitHub Pages) with a daily rotating fact plus a browsable
archive. See `README.md` for the fair-use/attribution posture and
`docs/PLANNING.md` for the full original design doc and phase history
(useful for "why does this work this way" context, but it's a historical
record — e.g. the datamine-backup step it describes in Phase 8 was never
built, so don't assume everything in it reflects current reality).

## Commands

Use the project's venv, not a bare system `python` — dependencies
(`pytest`, `ollama`, `requests`, `selectolax`, versions pinned in
`requirements.txt`) live there. `tests/test_daily_selection_parity.py` also
needs `node` on PATH (it skips itself if missing; CI's `ubuntu-latest`
already has it):

```
.venv/Scripts/python.exe -m pytest                        # all tests
.venv/Scripts/python.exe -m pytest tests/test_validate.py -k some_test  # one test
.venv/Scripts/python.exe -m pipeline.build_dataset         # merge raw_cache -> site/data/{entries,daily_cycle}.json
.venv/Scripts/python.exe -m pipeline.select_daily [--fresh]
.venv/Scripts/python.exe -m pipeline.paraphrase <in.json> <out.json> [--limit N] [--revalidate]
python ingest/wiki_scrape_lightcones.py [--limit N] [--refresh]
python ingest/wiki_scrape_relicsets.py [--limit N] [--refresh]
```

`--revalidate` on `paraphrase.py` re-runs QA against existing `short_text`
without calling Ollama — use this whenever `pipeline/validate.py`'s
heuristic changes, so already-paraphrased entries get their `qa_flags`
refreshed without being reworded. Paraphrasing (without `--revalidate`)
requires a local Ollama server running the model named by `OLLAMA_MODEL`
(default `qwen2.5:7b-instruct`); check with `curl http://localhost:11434/api/tags`.

The site itself is static HTML/CSS/vanilla JS with no build step — open
`site/index.html` directly or serve `site/` with any static file server.

CI (`.github/workflows/tests.yml`) runs `pytest` on every push/PR to
`master`. `.github/workflows/deploy-pages.yml` deploys `site/` on pushes
that touch `site/**`.

## Architecture

**Pipeline (local, run manually) → one committed dataset → static site.**
Nothing in `site/` talks to a backend; `pipeline/build_dataset.py` is the
only thing that writes `site/data/entries.json` and
`site/data/daily_cycle.json`, and the site just fetches those two files.

Data flows through three stages, each gated by a hash/version check so
re-runs are cheap:

1. `ingest/wiki_scrape_lightcones.py` / `wiki_scrape_relicsets.py` (via the
   cached `ingest/wiki_client.py` MediaWiki client) write raw, pre-paraphrase
   JSON to `data/raw_cache/*_wiki_raw.json` (gitignored, regenerable).
   Relic sets need extra stitching: a set's own page has no flavor text —
   it's assembled by fetching each piece's page and concatenating their
   `==Description==` sections in piece order.
2. `pipeline/paraphrase.py` reads that raw JSON, calls Ollama for any entry
   whose `raw_text_hash`/`prompt_version` changed or is missing, runs
   `pipeline/validate.py`'s deterministic QA, and writes
   `data/raw_cache/*_paraphrased_full.json` (also gitignored).
3. `pipeline/build_dataset.py` merges those paraphrased files into the
   single committed `site/data/entries.json`, matching entries by
   **`(category, normalized name)`, not `id`** — each scraper derives `id`
   via its own `slugify()`, which can drift from an earlier id for the same
   real item. It also (re)computes `reviewed` for every entry (`True` iff
   `short_text` is present and `qa_flags` is empty) and calls
   `pipeline/select_daily.py`'s `build_or_extend_cycle` to update
   `daily_cycle.json`.

**`reviewed` is never hand-edited in the JSON.** It's a pure function of
`qa_flags`, recomputed by `build_dataset.py` on every run. To "approve" a
flagged entry, clear the specific flag in the raw_cache paraphrased file
(after actually checking it against the source) and rerun `build_dataset.py`
— that flag-clearing *is* the human-review step the design relies on.

**`qa_flags` come from two different owners** — don't conflate them when
editing pipeline code:
- Scrape-level flags (e.g. `flavor_text_unexpectedly_long`,
  `missing_piece_description:*`) are set once by `ingest/wiki_scrape_*.py`
  and persist across paraphrase/revalidate runs.
- Validate-owned flags (`empty_short_text`, `short_text_too_short/long`,
  `short_text_identical_to_raw`, `possible_refusal_artifact`,
  `possible_hallucinated_name` — enumerated as `VALIDATE_OWNED_FLAGS` in
  `pipeline/paraphrase.py`) are wiped and recomputed from scratch by
  `pipeline/validate.py` every time an entry is (re)paraphrased or
  revalidated.

**The `possible_hallucinated_name` heuristic is deliberately rough** (its
own docstring says so): it compares capitalized-word tokens between
`short_text` and `raw_text`/`name`, skipping sentence-initial words (to
avoid flagging ordinary capitalization) and normalizing trailing
possessives. Known false-positive shapes worth recognizing before "fixing"
another one: a verbatim quote whose opening word happens to be
sentence-initial in the source won't match the same word reused mid-sentence
in the paraphrase; a faithful reword can fail to match morphologically
(e.g. source "Ascetics of Lotophagism" vs paraphrase "Lotophagists"). It
also does **not** check factual/lore accuracy — a wrong acronym expansion or
a fourth-wall break (e.g. paraphrase naming the game itself, which
`prompts/paraphrase_v1.txt` explicitly forbids) won't trip any automated
flag and needs an actual read against the source.

**The daily-selection algorithm is intentionally duplicated** in
`pipeline/select_daily.py` (Python, used by `build_dataset.py` and by
`tests/test_select_daily.py`) and `site/js/select-daily.js` (JS, used by
`site/js/app.js`). Both implement the same `days_since_start mod
cycle_length → index, skipping ineligible ids` logic against
`daily_cycle.json`. **Any change to one must be mirrored exactly in the
other** — there's no shared source of truth between Python and JS here.
`tests/test_daily_selection_parity.py` runs both implementations (the JS
side via a `node` subprocess, see `tests/_daily_selection_driver.js`) against
the same inputs and fails if they ever disagree — a real safety net, but the
two files still have to be edited in tandem by hand.

**A single bad entry doesn't abort a whole scrape/paraphrase run.**
`ingest/wiki_scrape_*.py` and `pipeline/paraphrase.py`'s `process_entries`
each wrap their per-item work in try/except (recording a `scrape_error` /
`paraphrase_error` qa_flag and moving on) and checkpoint their output to
disk periodically instead of only writing once at the end. A failed item is
retried automatically on the next run since its hash/short_text is left
unset.

**The wiki's `robots.txt` cannot be checked from a script or agent** — it's
behind a Cloudflare challenge that returns a JS-challenge page (or a bare
403) to any non-browser client, `curl` and `WebFetch` included. This is a
platform fact, not a bug to work around; a real compliance check needs a
human in an actual browser, which `docs/PLANNING.md` already flagged as a
manual, one-time step before the first real scrape.

**Adding a new lore category** is meant to be additive: write a new
`ingest/wiki_scrape_<category>.py`, add its raw_cache path to
`CATEGORY_SOURCES` in `pipeline/build_dataset.py`, add a label to
`CATEGORY_LABELS` and a `.card-badge.<category>` color in
`site/js/app.js`/`site/css/style.css`, and everything else (paraphrase,
validate, site rendering, daily rotation) keeps working unchanged.
`character_story` (`ingest/wiki_scrape_character_stories.py`) is the first
category built this way after light cones and relic sets, and is a useful
reference for the next one:
- Its wiki structure needed a genuinely new extractor —
  `ingest/wikitext_utils.py`'s `extract_template_params` — because a
  character's numbered stories live in one `{{Character Story|text1=...
  |mention1=...|text2=...}}` template on a `<Name>/Lore` subpage, a
  multi-named-parameter shape neither `extract_template_arg` (single
  positional arg) nor `extract_infobox_field` (one `|field = value` per
  line) handles. Don't assume a new category reuses the existing helpers
  unscoped — check the real wikitext first, the way this one and relic
  sets' piece-page stitching both did.
- Each numbered story is its own dataset entry (`scrape_one` returns a
  *list*, unlike the other two scrapers), not one entry per character —
  concatenating a character's ~4-5 stories into one `raw_text` risked the
  same too-long-to-paraphrase problem as a dense relic set's lore. Entry
  `name` includes the story index (`"<Character> — Story <N>"`) since
  `build_dataset.py` merges by `(category, normalized name)` — several
  same-named entries would silently collide.
- `MAX_REASONABLE_FLAVOR_CHARS` in the new scraper is a starting guess
  from a 5-character spot check, not a full-scrape calibration like the
  other two categories' — expect it to need raising (see those two
  scrapers' own comments for how that calibration was done last time).
- Scraping all ~86 characters × ~4-5 stories (roughly 300-400 entries, on
  top of the existing 228) hasn't been run yet — only spot-checked against
  a handful of characters — pending the `robots.txt` check above given
  it'd be the largest scrape by far.

Fixing `extract_template_params` also surfaced a real, separate bug:
`clean_flavor_text` wasn't stripping `{{Rubi|base|ruby}}` (a ruby/furigana
-style gloss), which had leaked into the *live* dataset's `raw_text` for
two already-shipped relic-set entries. Fixed and backfilled directly into
the affected raw_cache entries (not just the scraper) — a reminder that a
markup-stripping bug can sit unnoticed in already-published `raw_text`
since it's not validated as strictly as `short_text` is.

**Hard project constraints** (see `docs/PLANNING.md` for the full
reasoning): zero cost — no paid APIs or hosting; wiki is the primary and
only currently-implemented source (a `Dimbreath/StarRailData` datamine
backup was planned but never built — no `ingest/merge.py` or
`datamine_client.py` exist); paraphrasing must go through local Ollama, not
a hosted API; the repo must stay public for free GitHub Pages, which means
the full lore dataset is publicly visible.
