# HSR Lore Bites

[![Tests](https://github.com/manjieq/hsr-lore-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/manjieq/hsr-lore-pipeline/actions/workflows/tests.yml)

A small pipeline that turns Honkai: Star Rail's in-game lore text (light
cones and relic sets, for now) into short, easy-to-read daily facts — with a
tap to reveal the real original text and where it came from. Built as a
portfolio project; see [`docs/PLANNING.md`](docs/PLANNING.md) for the full
design and build plan.

Live site: https://manjieq.github.io/hsr-lore-pipeline/

## Fair use / attribution

This project quotes short excerpts of Honkai: Star Rail's in-game text for
non-commercial, fan-made educational/reference purposes. Every entry links
back to its source, and longer in-game passages are trimmed to a short
excerpt rather than reproduced in full. All game text, names, and imagery
belong to COGNOSPHERE / HoYoverse — this project is not affiliated with or
endorsed by them, and is not monetized.

The pipeline and site code (everything else in this repo) is MIT-licensed;
see [`LICENSE`](LICENSE).

## Status

The full light cone and relic set catalogs (228 entries total) are live,
scraped from the wiki and paraphrased locally via Ollama
(`qwen2.5:7b-instruct`) — all 228 have passed the automated QA checks and
human review. See the phases in `docs/PLANNING.md` for what's next.
