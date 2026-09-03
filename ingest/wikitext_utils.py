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


def _split_template_params(content: str) -> list[str]:
    """Split a template's inner content (already stripped of its outer
    ``{{``/``}}``) into raw ``key = value`` chunks on top-level ``|``.
    Both nested ``{{...}}`` templates and ``[[...]]`` links can contain
    their own ``|`` (e.g. ``[[Page|label]]``, ``{{Ref/Mission|...}}``)
    inside a parameter value -- a shared depth counter, incremented by
    either opener and decremented by either closer, keeps those from
    being mistaken for parameter boundaries."""
    parts = []
    depth = 0
    start = 0
    i = 0
    while i < len(content):
        if content.startswith("{{", i) or content.startswith("[[", i):
            depth += 1
            i += 2
        elif content.startswith("}}", i) or content.startswith("]]", i):
            depth -= 1
            i += 2
        elif content[i] == "|" and depth == 0:
            parts.append(content[start:i])
            start = i + 1
            i += 1
        else:
            i += 1
    parts.append(content[start:])
    return parts


def extract_template_params(wikitext: str, template_name: str) -> dict[str, str] | None:
    """Return ``{key: raw_value}`` for the first ``{{TemplateName | key =
    value | ... }}`` occurrence (honoring nested braces/links inside a
    value, like extract_template_arg), for templates with multiple named
    parameters rather than a single positional one (e.g. HSR's
    ``{{Character Story|text1=...|mention1=...|text2=...}}``). Returns
    None if the template isn't present at all; a parameter chunk that
    isn't ``key = value`` shaped (e.g. a leading empty chunk before the
    first ``|``) is silently skipped."""
    marker = "{{" + template_name
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
    inner = wikitext[content_start : pos - 2]
    if inner.startswith("|"):
        inner = inner[1:]

    params = {}
    for chunk in _split_template_params(inner):
        match = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*)", chunk, re.DOTALL)
        if match:
            params[match.group(1)] = match.group(2).strip()
    return params


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


def _strip_color_template(text: str) -> str:
    """Replace {{Color|...}} templates with just their actual displayed
    text, dropping the "keyword" color-name literal and any "nobold=N"
    flag. Real usage on this wiki puts the actual text in different
    positions relative to those two -- e.g.
    {{Color|keyword|"quoted text"|nobold=1}} vs.
    {{Color|keyword|nobold=1|Some Text}} -- so this can't be a
    fixed-position regex; it splits on top-level "|" the same way
    extract_template_params does and keeps whichever part isn't the
    "keyword" literal or a "key=value" flag."""

    def replace(match: re.Match) -> str:
        parts = _split_template_params(match.group(1))
        kept = [p.strip() for p in parts if p.strip() != "keyword" and not re.match(r"^\w+\s*=", p.strip())]
        return kept[0] if kept else ""

    return re.sub(r"\{\{Color\|(.*?)\}\}", replace, text, flags=re.DOTALL)


def _strip_sic_template(text: str) -> str:
    """Replace {{sic|text}} (a [sic]-style "written thus in the original"
    marker) with just its wrapped text -- except {{sic|text|hide=1}},
    which marks the text as meant to not be shown at all, and is dropped
    entirely rather than unwrapped."""

    def replace(match: re.Match) -> str:
        parts = _split_template_params(match.group(1))
        if any(re.match(r"^\s*hide\s*=\s*1\s*$", p) for p in parts[1:]):
            return ""
        return parts[0].strip() if parts else ""

    return re.sub(r"\{\{[Ss]ic\|(.*?)\}\}", replace, text, flags=re.DOTALL)


def clean_flavor_text(raw: str) -> str:
    """Strip common wiki markup out of an extracted flavor-text fragment."""
    text = raw
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"'''?(.*?)'''?", r"\1", text)  # bold/italic markup
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # [[link|label]] -> label
    text = re.sub(r"\{\{w\|(?:[^|}]*\|)?([^}]+)\}\}", r"\1", text)  # {{w|...|label}} -> label
    text = re.sub(r"\{\{Rubi\|([^|}]*)\|[^}]*\}\}", r"\1", text, flags=re.IGNORECASE)  # {{Rubi|base|ruby}} -> base
    # {{MC|m=male text|f=female text}} (named) or {{MC|male text|female
    # text}} (positional) -- Trailblazer's gender-conditional text, in
    # either invocation style used across the wiki. The site has no
    # per-reader gender selection, so this always picks the first/"m"
    # variant; an arbitrary but consistent choice.
    text = re.sub(r"\{\{MC\|m=([^|}]*)\|f=[^}]*\}\}", r"\1", text)  # named form
    text = re.sub(r"\{\{MC\|([^|}]*)\|[^}]*\}\}", r"\1", text)  # positional form
    # {{Obfuscate|N}} -- N deliberately-redacted characters in the
    # original text (e.g. a name withheld for plot reasons). N is usually
    # a digit but sometimes a placeholder like "-" or "----"; render as a
    # single block character whenever it isn't a clean digit count rather
    # than guessing a length from the placeholder's own length.
    text = re.sub(
        r"\{\{Obfuscate\|([^}]*)\}\}", lambda m: "▇" * (int(m.group(1)) if m.group(1).isdigit() else 1), text
    )
    text = _strip_sic_template(text)
    text = re.sub(r"\{\{[Ss]ic\}\}", "", text)  # bare {{sic}} with no wrapped argument
    text = _strip_color_template(text)
    # {{Character Page Link|Name|ref=1}} -- an inline link to another
    # character's page with an optional footnote-reference flag; keep
    # just the name.
    text = re.sub(r"\{\{Character Page Link\|([^|}]*)(?:\|ref=\d+)?\}\}", r"\1", text)
    # {{ja|...}} / {{zh|...}} -- a Japanese/Chinese-language aside (e.g. an
    # etymology note), not part of the English narrative; dropped entirely
    # rather than left as raw non-Latin script for the paraphrase model to
    # potentially echo verbatim into short_text.
    text = re.sub(r"\{\{(?:ja|zh)\|[^}]*\}\}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
