"""Small helpers for pulling structured fields out of Fandom wikitext, without
needing a full wikitext parser."""

from __future__ import annotations

import re


def extract_template_arg(wikitext: str, template_name: str) -> str | None:
    """Return the single positional argument of the first
    ``{{TemplateName|...}}`` occurrence, honoring nested ``{{...}}`` braces
    inside the argument (e.g. a nested link template)."""
    marker = "{{" + template_name + "|"
    start = wikitext.find(marker)
    if start == -1:
        return None
    pos = start + len(marker)
    depth = 1
    content_start = pos
    while pos < len(wikitext) and depth > 0:
        if wikitext.startswith("{{", pos):
            depth += 1
            pos += 2
        elif wikitext.startswith("}}", pos):
            depth -= 1
            pos += 2
        else:
            pos += 1
    return wikitext[content_start : pos - 2]


def extract_infobox_field(wikitext: str, field_name: str) -> str | None:
    """Return the value of ``|field_name = ...`` from the first infobox
    template at the top of the page (stops at end of line)."""
    match = re.search(rf"\|\s*{re.escape(field_name)}\s*=\s*(.+)", wikitext)
    return match.group(1).strip() if match else None


def extract_section(wikitext: str, heading_name: str) -> str | None:
    """Return the wikitext body of a level-2 ``==Heading==`` section, up to
    (but not including) the next level-2 heading or end of page. A level-3+
    subheading (``===...===``) inside the section is included as part of the
    body, not treated as a stopping point. Returns None if the heading isn't
    present at all."""
    start_match = re.search(rf"^==\s*{re.escape(heading_name)}\s*==\s*$", wikitext, re.MULTILINE | re.IGNORECASE)
    if not start_match:
        return None
    content_start = start_match.end()
    next_heading_match = re.search(r"^==[^=].*==\s*$", wikitext[content_start:], re.MULTILINE)
    content_end = content_start + next_heading_match.start() if next_heading_match else len(wikitext)
    return wikitext[content_start:content_end].strip()


def clean_flavor_text(raw: str) -> str:
    """Strip common wiki markup out of an extracted flavor-text fragment."""
    text = raw
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"'''?(.*?)'''?", r"\1", text)  # bold/italic markup
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # [[link|label]] -> label
    text = re.sub(r"\{\{w\|(?:[^|}]*\|)?([^}]+)\}\}", r"\1", text)  # {{w|...|label}} -> label
    text = re.sub(r"\s+", " ", text).strip()
    return text
