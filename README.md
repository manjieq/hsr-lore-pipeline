# HSR Lore Connections

[![Tests](https://github.com/manjieq/hsr-lore-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/manjieq/hsr-lore-pipeline/actions/workflows/tests.yml)

Honkai: Star Rail tells one story in fragments, scattered across light cone
descriptions, relic set flavor text, and character backstories that never
reference each other. This project scrapes those fragments, finds the names
that appear in more than one of them, and puts the real in-game text side by
side so you can read the connection yourself.

Live site: https://manjieq.github.io/hsr-lore-pipeline/

## What it does

A **connection** is a name — a person, place, faction, or concept — that
turns up in several entries. The site leads with one featured connection a
day, and lets you browse all of them.

The interesting ones bridge categories: "Xianzhou Luofu" appears in 31
entries spread across all three kinds of lore, and no single entry explains
it. Nothing here rewrites or summarizes the source material; every claim the
site makes is "these N entries mention this name", and every excerpt links
back to the wiki page it came from.

The entity graph is deliberately **deterministic and LLM-free** — a
gazetteer of characters derived from the dataset's own entry names, plus
capitalized runs that clear a calibrated evidence bar. It is reproducible
and reviewable, and no model is invited to invent a connection that isn't
in the text.

## Fair use / attribution

This project quotes short excerpts of Honkai: Star Rail's in-game text for
non-commercial, fan-made educational/reference purposes. Every entry links
back to its source, and longer in-game passages are trimmed to a short
excerpt rather than reproduced in full. All game text, names, and imagery
belong to COGNOSPHERE / HoYoverse — this project is not affiliated with or
endorsed by them, and is not monetized.

The pipeline and site code (everything else in this repo) is MIT-licensed;
see [`LICENSE`](LICENSE).

## Running it

Use the project's venv rather than a bare system `python`; dependencies are
pinned in `requirements.txt`. Some tests also need `node` on PATH and skip
themselves without it.

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # .venv\Scripts\ on Windows

.venv/bin/python -m pytest                    # all tests
.venv/bin/python -m pipeline.build_dataset    # raw_cache -> site/data/*.json
.venv/bin/python -m pipeline.entities         # rebuild just the entity graph
```

`build_dataset.py` is the only thing that writes the two committed data
files the site reads: `entries.json` (the corpus) and `entities.json` (the
connection graph and its daily rotation).

The site is static HTML/CSS/vanilla JS with no build step — open
`site/index.html` directly, or serve the folder:

```
python -m http.server -d site
```

Scraping and paraphrasing are separate, slower steps; see
[`CLAUDE.md`](CLAUDE.md) for those and for the architecture in detail, and
[`docs/PLANNING.md`](docs/PLANNING.md) for the original design doc (a
historical record — not everything in it was built).

## Status

658 entries are live — 168 light cones, 60 relic sets, and 430 character
stories — scraped from the wiki and all passing the automated QA checks.
The entity graph over them finds **454 connections, 232 of which bridge
more than one category.**

Earlier versions of this site led with an Ollama-generated paraphrase of a
single entry. That has been retired: compressing one passage and then
showing the original directly beneath it added nothing a reader couldn't get
better by reading the original. The paraphrases still exist in
`entries.json` as `short_text`, but the site no longer displays them.
