"""Tests for pipeline/paraphrase.py's crash resilience: a single bad Ollama
response must flag that one entry and let the rest of the batch proceed,
and checkpointing must persist progress before the run finishes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline.paraphrase as paraphrase_module

GOOD_SHORT_TEXT = "A perfectly good paraphrase of the given lore text, well within the length limits."


def _fake_chat(raise_for: str):
    def fake_chat(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if raise_for in prompt:
            raise RuntimeError("simulated Ollama failure")
        return {"message": {"content": json.dumps({"short_text": GOOD_SHORT_TEXT})}}

    return fake_chat


def test_one_entry_erroring_does_not_abort_the_batch(monkeypatch):
    monkeypatch.setattr(paraphrase_module.ollama, "chat", _fake_chat(raise_for="Bad Entry"))

    entries = [
        {"name": "Bad Entry", "category": "light_cone", "raw_text": "Some raw text."},
        {"name": "Good Entry", "category": "light_cone", "raw_text": "Some other raw text."},
    ]
    result = paraphrase_module.process_entries(entries)

    bad = next(e for e in result if e["name"] == "Bad Entry")
    good = next(e for e in result if e["name"] == "Good Entry")

    assert "paraphrase_error" in bad["qa_flags"]
    assert not bad.get("short_text")
    assert good.get("short_text") == GOOD_SHORT_TEXT
    assert "paraphrase_error" not in (good.get("qa_flags") or [])


def test_a_later_successful_run_clears_a_stale_paraphrase_error_flag(monkeypatch):
    monkeypatch.setattr(paraphrase_module.ollama, "chat", _fake_chat(raise_for="__nothing__"))

    entries = [{"name": "Recovered Entry", "category": "light_cone", "raw_text": "Some raw text.",
                "qa_flags": ["paraphrase_error"]}]
    result = paraphrase_module.process_entries(entries)

    assert result[0].get("short_text") == GOOD_SHORT_TEXT
    assert "paraphrase_error" not in result[0]["qa_flags"]


def test_checkpoint_is_written_before_the_run_finishes(monkeypatch, tmp_path):
    monkeypatch.setattr(paraphrase_module.ollama, "chat", _fake_chat(raise_for="__nothing__"))

    entries = [
        {"name": "Entry One", "category": "light_cone", "raw_text": "Text one."},
        {"name": "Entry Two", "category": "light_cone", "raw_text": "Text two."},
    ]
    checkpoint_path = tmp_path / "checkpoint.json"
    paraphrase_module.process_entries(entries, checkpoint_path=checkpoint_path, checkpoint_every=1)

    assert checkpoint_path.exists()
    checkpointed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert all(e.get("short_text") == GOOD_SHORT_TEXT for e in checkpointed)
