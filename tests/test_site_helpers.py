"""Tests for the site's own JavaScript helpers, run through `node`.

site/js/ had no test coverage at all before this, and the gap was not
theoretical: building the connections UI shipped "9 character storys" into
the summary line (naive "+ s" pluralization) and an HTML escaper that left
quotes intact while being interpolated into href and class attributes.
Both are pure functions over plain data, so both are cheap to pin down
here rather than catching them by eye in a browser.

Follows the same shape as test_daily_selection_parity.py: a small JS
driver invoked as a subprocess, skipped rather than failed when `node`
isn't available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER_PATH = Path(__file__).resolve().parent / "_site_helpers_driver.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")


def call_js(op: str, *args):
    proc = subprocess.run(
        ["node", str(DRIVER_PATH)],
        input=json.dumps({"op": op, "args": list(args)}),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)["result"]


# --- pluralization ----------------------------------------------------


def test_plural_uses_singular_for_one():
    assert call_js("plural", 1, "entry", "entries") == "1 entry"


def test_plural_uses_explicit_plural_form():
    assert call_js("plural", 4, "entry", "entries") == "4 entries"


def test_plural_falls_back_to_appending_s():
    assert call_js("plural", 3, "connection") == "3 connections"


def test_describe_spread_single_category():
    assert call_js("describeSpread", {"light_cone": 2}) == "2 light cones"


def test_describe_spread_joins_two_categories():
    assert (
        call_js("describeSpread", {"light_cone": 1, "relic_set": 3})
        == "1 light cone and 3 relic sets"
    )


def test_describe_spread_pluralizes_character_story_correctly():
    """Regression: appending "s" to the lowercased label produced
    "9 character storys" on every card with more than one story."""
    assert (
        call_js("describeSpread", {"light_cone": 4, "relic_set": 2, "character_story": 9})
        == "4 light cones, 2 relic sets and 9 character stories"
    )


def test_describe_spread_uses_a_fixed_category_order():
    # Not whatever order the JSON object happened to be built in.
    assert (
        call_js("describeSpread", {"character_story": 1, "light_cone": 1})
        == "1 light cone and 1 character story"
    )


# --- escaping ---------------------------------------------------------


def test_escape_html_neutralizes_attribute_breakout():
    """escapeHtml is interpolated into href and class attributes, so a
    quote must not survive it."""
    got = call_js("escapeHtml", 'https://x.test/a" onerror="alert(1)')
    assert '"' not in got
    assert got == "https://x.test/a&quot; onerror=&quot;alert(1)"


def test_escape_html_escapes_ampersand_first():
    # Wrong ordering double-escapes: "&lt;" rather than "&amp;lt;".
    assert call_js("escapeHtml", "&lt;") == "&amp;lt;"


def test_escape_html_handles_missing_values():
    assert call_js("escapeHtml", None) == ""


# --- daily rotation over the real dataset -----------------------------


def test_connection_rotation_is_showable_every_day_for_a_year():
    """Walks the committed entities.json day by day: every pick must
    resolve to an entity that bridges categories and whose cited entries
    all exist in entries.json."""
    result = call_js("rotation", date.today().isoformat(), 365)
    assert result["problems"] == []


def test_connection_rotation_visits_every_entry_in_its_cycle():
    result = call_js("rotation", date.today().isoformat(), 365)
    # A year is longer than the cycle, so every id should come up.
    assert result["distinct"] == result["cycleLength"]
