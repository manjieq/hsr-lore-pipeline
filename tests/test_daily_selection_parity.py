"""Automated parity check between pipeline/select_daily.py and
site/js/select-daily.js.

The two files implement the exact same "today's fact" picker in two
languages on purpose (Python for build_dataset.py, JS for the static
site), and both their own docstrings say they must be kept in sync by
hand -- previously the only cross-check was a one-off manual run in a
browser console (see docs/PLANNING.md, Phase 5 verification). This test
automates that check via `node`, so any future drift between the two
implementations fails CI instead of only surfacing as a live-site bug.

Skips (rather than fails) if `node` isn't on PATH, since it's a real
runtime dependency of this test file, not of the project itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.select_daily import select_daily_id

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER_PATH = Path(__file__).resolve().parent / "_daily_selection_driver.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")


def _js_select_daily_id(cycle_data: dict, entries_by_id: dict, d: date) -> str | None:
    payload = json.dumps({"cycleData": cycle_data, "entriesById": entries_by_id, "dateStr": d.isoformat()})
    proc = subprocess.run(
        ["node", str(DRIVER_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node driver failed (exit {proc.returncode}): {proc.stderr}")
    return json.loads(proc.stdout)["result"]


def test_python_and_js_agree_across_a_full_rotation_with_ineligible_entries():
    cycle_data = {
        "cycle": ["a", "b", "c", "d", "e"],
        "cycle_start_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00Z",
    }
    entries_by_id = {
        "a": {"reviewed": True, "qa_flags": []},
        "b": {"reviewed": False, "qa_flags": []},  # not reviewed
        "c": {"reviewed": True, "qa_flags": ["possible_hallucinated_name"]},  # flagged
        "d": {"reviewed": True, "qa_flags": []},
        "e": {"reviewed": True, "qa_flags": []},
    }
    start = date.fromisoformat(cycle_data["cycle_start_date"])
    # A few days before the cycle starts, through a couple of full wraps --
    # exercises negative offsets, the ineligible-skip loop, and the modulo
    # wraparound identically in both implementations.
    for offset in range(-3, 3 * len(cycle_data["cycle"])):
        d = start + timedelta(days=offset)
        py_result = select_daily_id(cycle_data, entries_by_id, d)
        js_result = _js_select_daily_id(cycle_data, entries_by_id, d)
        assert py_result == js_result, f"mismatch on {d.isoformat()}: python={py_result!r} js={js_result!r}"


def test_python_and_js_agree_on_the_real_committed_dataset_for_today():
    entries = json.loads((REPO_ROOT / "site" / "data" / "entries.json").read_text(encoding="utf-8"))
    cycle_data = json.loads((REPO_ROOT / "site" / "data" / "daily_cycle.json").read_text(encoding="utf-8"))
    entries_by_id = {e["id"]: e for e in entries}

    today = date.today()
    py_result = select_daily_id(cycle_data, entries_by_id, today)
    js_result = _js_select_daily_id(cycle_data, entries_by_id, today)
    assert py_result == js_result
