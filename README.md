# HSR Lore Bites

A small pipeline that turns Honkai: Star Rail's in-game lore text (light
cones and relic sets, for now) into short, easy-to-read daily facts — with a
tap to reveal the real original text and where it came from. Built as a
portfolio project; see [`docs/PLANNING.md`](docs/PLANNING.md) for the full
design and build plan.

Live site: https://manjieq.github.io/hsr-lore-pipeline/ (once Pages is enabled)

## Fair use / attribution

This project quotes short excerpts of Honkai: Star Rail's in-game text for
non-commercial, fan-made educational/reference purposes. Every entry links
back to its source, and longer in-game passages are trimmed to a short
excerpt rather than reproduced in full. All game text, names, and imagery
belong to COGNOSPHERE / HoYoverse — this project is not affiliated with or
endorsed by them, and is not monetized.

## Status

The full light cone catalog (168 entries) is now live, scraped from the wiki
and paraphrased locally via Ollama (`qwen2.5:7b-instruct`); 19 entries are
held back pending human review of an automated faithfulness flag. Relic sets
are still the original 5 hand-authored samples — see the phases in
`docs/PLANNING.md` for what's next.
