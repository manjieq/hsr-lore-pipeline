# HSR Lore Pipeline — Implementation Plan

## Context

The user wants a portfolio-grade ETL pipeline: scrape Honkai: Star Rail
in-game lore text (starting with light cones & relic sets), have a local AI
paraphrase each entry into a short, "YT Shorts"-style summary, and surface it
as a digestible daily fact — tappable to reveal the full original text. The
audience is HSR content creators who want lore-video ideas without reading
walls of in-game text. The point of building it is partly the resume value (a
real ingest → transform → store → serve → UI pipeline) and partly that the
user is personally invested in HSR, which should keep them motivated through
the tedious parts (scraper fragility, prompt tuning, etc.).

Hard constraints the user set:
- **Zero cost.** No paid APIs, no paid hosting.
- **Sources:** HSR Fandom wiki as primary, a datamined GitHub repo
  (`Dimbreath/StarRailData`) as backup/cross-check for anything not yet
  written up on the wiki.
- **MVP scope:** light cones & relic sets only. **Expect scope to grow later**
  — character stories, dialogue, and books are explicit future work if the
  MVP proves out, so the ingestion/schema design should stay easy to extend
  per-category rather than being hardcoded to just these two.
- **Delivery: web page only for v1.** No Discord bot for now — ship the site
  first, and only add other distribution channels (Discord or otherwise)
  later if the web page works well.
- **Paraphrasing:** a local Ollama model (free, no usage caps) rather than a
  hosted API.

Also found during scoping: `hsr-lore-pipeline` currently has no files and no
`.git` of its own — git resolves upward to `C:\Users\aiman\.git`, meaning the
whole home directory is an accidental git repo. Investigation confirmed this
is a real clone of `https://github.com/asyraf34/systemd.git` (an unrelated
Java school project, authored by someone else, not the current git identity),
with its working-tree files sitting directly in the home directory. It's
fully preserved on GitHub already, so it will be **moved** (not deleted) into
its own folder as the first phase below, so the home directory stops being a
git root and this — or any future — project can't get tangled up in it again.

## Architecture overview

Because Ollama only runs locally, and to keep everything free, the design
avoids needing any server:

- A **local, user-run pipeline** (Python, run manually or via Windows Task
  Scheduler) scrapes the wiki, cross-checks/backfills from the datamine repo,
  paraphrases new/changed entries via local Ollama, validates them, and
  writes one dataset file: `site/data/entries.json`.
- A **fully static site** (GitHub Pages, no backend) reads that JSON
  client-side, deterministically picks "today's fact," and renders a
  tap-to-expand card UI plus a browsable list of all entries.

Because generation (the pipeline) and delivery (the site) are already
decoupled through one plain JSON dataset, adding another delivery channel
later (Discord, a newsletter, whatever) is just a new small consumer of the
same `entries.json` — nothing in the pipeline needs to change for that.
Likewise, adding a new lore category later is meant to be: add one new
`ingest/wiki_scrape_<category>.py`, extend the `category` enum in the schema,
and everything downstream (paraphrase, validate, site, daily rotation) keeps
working unchanged.

## Repo / project structure

```
hsr-lore-pipeline/
├── .github/workflows/
│   └── deploy-pages.yml          # publish site/ to GitHub Pages on push to main
├── data/raw_cache/               # gitignored: cached wiki + datamine responses
├── ingest/
│   ├── wiki_client.py            # MediaWiki API wrapper (categorymembers, parse)
│   ├── wiki_scrape_lightcones.py
│   ├── wiki_scrape_relicsets.py
│   ├── datamine_client.py        # fetch pinned-commit TextMap/Config JSON from Dimbreath/StarRailData
│   └── merge.py                  # normalize names, merge wiki+datamine, dedupe
├── pipeline/
│   ├── paraphrase.py             # Ollama call + prompt templating + retries
│   ├── validate.py               # length/faithfulness/refusal-artifact QA checks
│   ├── build_dataset.py          # orchestrates ingest → merge → paraphrase → validate → write dataset
│   └── select_daily.py           # pure function: date + cycle → entry id
├── prompts/
│   ├── paraphrase_v1.txt
│   └── CHANGELOG.md
├── scripts/
│   └── run_pipeline.ps1          # one-shot local run (Task Scheduler target)
├── site/
│   ├── index.html
│   ├── css/style.css
│   ├── js/{select-daily.js, app.js}
│   └── data/
│       ├── entries.json          # the single canonical dataset
│       └── daily_cycle.json      # precomputed shuffled ID order + cycle_start_date
├── tests/
│   ├── test_select_daily.py
│   ├── test_merge.py
│   └── test_validate.py
├── docs/
│   └── PLANNING.md                # this plan, committed as project history
├── requirements.txt
├── .gitignore
├── README.md                     # architecture + explicit fair-use/attribution statement
└── LICENSE                       # MIT for code; note game text is HoYoverse IP
```

One dataset file (`site/data/entries.json`) is written directly by the
pipeline and consumed by the site — nothing to keep in sync manually.

## Data schema

```jsonc
{
  "id": "light-cone-night-on-the-milky-way",   // stable slug from category+name, never array index
  "category": "light_cone",                     // "light_cone" | "relic_set" (more categories added later)
  "name": "Night on the Milky Way",
  "subtitle": "5★ · Harmony",
  "source_type": "wiki",                         // "wiki" | "datamine" | "wiki+datamine"
  "source_url": "https://honkai-star-rail.fandom.com/wiki/Night_on_the_Milky_Way",
  "raw_text": "...",                             // cleaned original flavor text, verbatim
  "short_text": "...",                           // AI paraphrase
  "prompt_version": "paraphrase_v1",
  "raw_text_hash": "sha256...",                  // skip re-paraphrasing unchanged entries
  "image_url": "https://static.wikia.nocookie.net/...",
  "game_version_seen": "2.0",
  "date_added": "2026-09-02",
  "date_updated": "2026-09-02",
  "qa_flags": [],                                // e.g. ["possible_hallucinated_name"]
  "reviewed": true                                // human-approved; false = excluded from rotation
}
```

`daily_cycle.json`: `{ "cycle": ["id1", "id2", ...], "cycle_start_date": "2026-01-01", "generated_at": "..." }`

## Ingestion

**Wiki (primary)** — use the MediaWiki API (`api.php`), not raw HTML scraping,
since Fandom wikis expose it and it's far more stable than parsing rendered
pages:
- Enumerate via `action=query&list=categorymembers&cmtitle=Category:Light_Cones`
  (paginate with `cmcontinue`); confirm the exact relic-set category name
  against the live wiki before coding.
- Fetch content via `action=parse&page=<title>&prop=wikitext`, pulling the
  flavor-text template parameter directly. Fall back to HTML parsing
  (`selectolax`, targeting `.mw-parser-output`) only where text isn't cleanly
  templated.
- Be polite: identifying User-Agent, ~1 req/sec with jitter, exponential
  backoff on 429/5xx. **Manually check `honkai-star-rail.fandom.com/robots.txt`
  in a browser before the first real scrape run** — this wasn't verifiable
  automatically during planning.
- Cache every response under `data/raw_cache/` keyed by URL hash; re-runs hit
  cache first, `--refresh` forces a re-fetch.

**Datamine (backup)** — `Dimbreath/StarRailData`: fetch specific files
(`TextMap/TextMapEN.json` + the relevant config table, likely
`EquipmentConfig` for light cones and a `RelicSetConfig`-style table for relic
sets — confirm exact filenames against the live repo before coding, since
layouts shift across patches) via `raw.githubusercontent.com`, pinned to a
commit SHA for reproducibility.

**Merge** (`ingest/merge.py`) — normalize names (lowercase, strip
punctuation), match wiki↔datamine by name. Wiki text wins when both exist;
datamine-only entries (new patch content not yet on the wiki) are created
with `source_type: "datamine"`, `reviewed: false`, staying out of rotation
until manually verified.

## Paraphrasing (Ollama)

- Python `ollama` package against `http://localhost:11434`; model is a config
  value (`OLLAMA_MODEL` env var) — try `qwen2.5:7b-instruct` first, fall back
  to a smaller quantized model if hardware-constrained.
- Request structured output (`format: "json"`, single `short_text` field) to
  avoid parsing free text out of conversational wrapper phrases.
- Prompt (`prompts/paraphrase_v1.txt`): use only facts present in the source,
  no invented names/events, 1–2 sentences, ~40–280 chars, Shorts-style hook
  framing, no hashtags/markdown.
- QA (`pipeline/validate.py`), deterministic, no second LLM call: length
  bounds, non-empty/non-identical check, a proper-noun faithfulness heuristic
  (capitalized tokens in `short_text` must appear in `raw_text`/`name`, else
  flag `possible_hallucinated_name`), refusal-artifact string check. Flagged
  entries stay `reviewed: false` until a human clears them.
- Idempotency: compare `raw_text_hash` + `prompt_version` before calling
  Ollama; skip unchanged entries, so re-runs after new patches are cheap.

## Daily selection

Precompute one shuffled cycle instead of maintaining two independent
date-hash implementations (Python + JS) that could drift apart:

1. `build_dataset.py` computes a seeded deterministic shuffle (fixed seed,
   Fisher-Yates) of all `reviewed && !qa_flags` entry IDs → `daily_cycle.json`.
2. Identical ~5-line lookup in `pipeline/select_daily.py` and
   `site/js/select-daily.js`: `days_since_start mod cycle_length → index`,
   skipping any entry that's since become ineligible.
3. New entries from later pipeline runs are appended to the end of the
   existing cycle (not reshuffled), keeping already-posted history stable.
4. `tests/test_select_daily.py` pins fixed dates → expected IDs; cross-check
   once by hand against the JS version in a browser console.

## Static site

Plain HTML/CSS/vanilla JS — no framework or build step needed; GitHub Pages
serves `site/` as-is.
- `app.js` fetches `entries.json` + `daily_cycle.json`, renders today's card
  (name, category badge, `short_text`, expand-to-reveal `raw_text` +
  `source_url` + `image_url`).
- A **browse-all** section (list/grid of every reviewed entry, independently
  expandable) — this directly serves the "creator hunting for ideas" use
  case, not just the single daily card.
- Deep link via `?id=<entry-id>` query param (read with `URLSearchParams`,
  no router) — keeps individual entries linkable for whenever another
  delivery channel gets added later.
- Deploy: `actions/deploy-pages` workflow on push to `main`; repo Settings →
  Pages → Source: "GitHub Actions." **Repo must be public** (GitHub Pages on
  the free personal plan only supports public repos).

## Future: additional delivery channels

Not part of this build — noted so the design doesn't accidentally block it
later. If the web page proves out, a Discord poster (or similar) can be added
as a small standalone script reading the same `entries.json` +
`select_daily.py` output and posting via a webhook or bot, run on whatever
free schedule makes sense at that point. Nothing in the phases below needs to
change to support that later.

## Working conventions

- **Commit cadence:** commit and push to the GitHub repo after each phase
  below reaches a meaningfully working state (not after every small edit) —
  e.g. once the site renders sample data, once the daily-rotation logic is
  tested, once a real scrape slice works, etc.
- Ordinary commits for this repo do not include the Claude co-authorship
  trailer — flagged to the user directly in chat since it's a standing
  tool-attribution behavior, not a plan detail.

## Phases

- **Phase 1 — Clean up the home-directory git repo.** Create
  `C:\Users\aiman\Desktop\systemd-old-project` (or similar); move `.git`,
  `src/`, `res/`, `teams/`, `README.md`, `.gitattributes`, `.gitignore` out of
  `C:\Users\aiman` into it. Verify from the new folder that `git status`
  works cleanly, and from `C:\Users\aiman` that `git rev-parse
  --show-toplevel` no longer finds any `.git` upward. One-time cleanup, done
  before any HSR project file exists.

- **Phase 2 — Initialize the hsr-lore-pipeline repo.** `git init` inside
  `hsr-lore-pipeline`; add `.gitignore`; `gh repo create hsr-lore-pipeline
  --public --source=. --remote=origin` under the `manjieq` account; commit
  this plan as `docs/PLANNING.md` in the first commit; push.

- **Phase 3 — Sample data.** Hand-author 8–10 real entries (copy-pasted once
  from the wiki) directly into `entries.json` + a manually written
  `daily_cycle.json` — unblocks the site without waiting on the scraper/Ollama.

- **Phase 4 — Static site.** Build the card UI + browse-all + expand/collapse
  + deep link against the sample data; deploy to GitHub Pages; confirm it's
  live and public.

- **Phase 5 — Daily selection logic.** Build `select_daily.py` properly
  (cycle-array approach), replacing the hand-written `daily_cycle.json`; add
  `tests/test_select_daily.py`; port identical logic to `select-daily.js`;
  verify parity by hand once in a browser console.

- **Phase 6 — Wiki ingestion (light cones slice).** Build `wiki_client.py`
  for light cones only, with caching; spot-check output against the live
  wiki.

- **Phase 7 — Paraphrasing.** Build `paraphrase.py` + `prompts/paraphrase_v1.txt`
  + `validate.py` against that slice; iterate on the prompt against ~20 real
  outputs until quality feels right.

- **Phase 8 — Datamine backup + merge.** Build `datamine_client.py` +
  `merge.py`; validate merge/dedupe against the same slice.

- **Phase 9 — Full light-cone run.** Wire everything into `build_dataset.py`
  + `run_pipeline.ps1`; run for all light cones; review `qa_flags`; commit —
  confirm Pages picks it up automatically.

- **Phase 10 — Relic sets.** Repeat ingestion for relic sets; re-run the
  pipeline (incremental — unchanged light cones skipped via hash check);
  append to the cycle; commit.

- **Phase 11 — Polish.** README with fair-use/attribution statement, LICENSE,
  scraper retry/error handling, "last updated" footer on the site.

## Risks flagged to the user

- **Wiki scraping fragility/ToS**: robots.txt needs a manual check before
  the first real scrape; category/page structure can change and will
  occasionally break the scraper — cache aggressively, treat scraping as
  resumable.
- **IP/fair-use posture**: this republishes short excerpts of HoYoverse's
  text. Mitigate by keeping only the specific flavor-text field (not whole
  wiki articles), always linking back to the source, stating clearly in the
  README this is non-commercial fan content, and never monetizing.
- **Ollama output quality**: a local 7–8B model is weaker at faithfulness
  than hosted frontier models. Mitigated by the "only use given facts"
  prompt constraint, the automated proper-noun heuristic, and — most
  importantly — nothing goes live until a human flips `reviewed: true`.
- **Repo must be public** for free GitHub Pages — the code and full lore
  dataset will be visible to anyone.
- **Datamine schema drift**: exact `Dimbreath/StarRailData` file/table names
  need a one-time manual verification pass before coding `datamine_client.py`.

## Verification

- After Phase 1: confirm `git rev-parse --show-toplevel` from
  `C:\Users\aiman` no longer finds a repo, and the relocated old project
  works normally from its new folder.
- After Phase 4: open the deployed Pages URL, confirm the card renders and
  expand/collapse works for sample entries.
- After Phase 5: run `pytest tests/test_select_daily.py`; manually run the JS
  version in a browser console for the same fixed dates and confirm matching
  IDs.
- After Phase 7: manually review ~20 paraphrased entries for faithfulness/tone
  before trusting the pipeline on the full catalog.
- After Phase 9/10: spot-check `entries.json` for duplicate/malformed
  entries; confirm the live site reflects the full light-cone + relic-set
  catalog.
