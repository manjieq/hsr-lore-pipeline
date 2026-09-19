"""Builds the entity graph that turns 658 isolated lore entries into a
connected corpus: who and what each entry mentions, and therefore which
entries talk about the same thing.

This is the layer the per-entry paraphrase never provided. A single entry's
flavor text is a fragment; the interesting content is the *join* -- the 36
entries across light cones, relic sets, and character stories that all touch
the Xianzhou Luofu, none of which explains it alone.

Deliberately deterministic and LLM-free. Everything here is a gazetteer
lookup or a regex over text the scrapers already cleaned, so the graph is
reproducible, reviewable, and cheap to rebuild -- the same properties the
rest of the pipeline is built around. A synthesis layer, if one is added
later, should consume this file rather than re-derive it.

Two sources of entities, in descending order of confidence:

1. **Characters**, derived from the dataset's own character_story entry
   names ("Acheron -- Story 1" -> "Acheron"). This is authoritative rather
   than guessed: the scraper already resolved these from real wiki page
   titles, so it costs nothing and cannot hallucinate a character who
   doesn't exist. Alternate-outfit variants ("Dan Heng * Imbibitor Lunae")
   are aliased onto their base character, since for lore purposes they are
   the same person.

2. **Discovered terms**, capitalized runs appearing in enough distinct
   entries to be worth linking. Calibrated against the full corpus rather
   than guessed: at a >=2-entry threshold the top of the list is almost
   entirely real proper nouns (Genius Society, Silvermane Guards,
   Stellaron Hunters, Interastral Peace Corporation), and the recurring
   noise shapes are all handled below -- honorific prefixes ("Madam
   Herta"), singular/plural splits ("Cloud Knight" vs "Cloud Knights"),
   leading articles, and sentence-initial capitalization.

Usage:
    python -m pipeline.entities          # writes site/data/entities.json
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reused rather than reimplemented. This is the same "does this capital
# letter mean a proper noun, or just the start of a sentence?" problem
# validate.py already solved (including the "Mr."-isn't-a-sentence-end
# case), and the repo has already been bitten once by keeping two copies of
# one algorithm in sync (see select_daily.py / select-daily.js). Importing
# the private helper is the lesser evil against duplicating it.
from pipeline.validate import _is_sentence_initial

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRIES_PATH = REPO_ROOT / "site" / "data" / "entries.json"
ENTITIES_PATH = REPO_ROOT / "site" / "data" / "entities.json"

# An entity mentioned in only one entry connects nothing, so it is not a
# useful node -- the whole point of this file is edges between entries.
MIN_ENTRY_MENTIONS = 2

# Single-word candidates clear a higher bar than multi-word ones. A
# two-word capitalized run ("Silvermane Guards") is almost always a real
# name, but a lone capitalized word is far more often ordinary prose that
# happened to survive the sentence-initial filter -- it appears mid-
# sentence inside dialogue, after a dash, or inside a quote. Requiring it
# in more distinct entries trades a few real one-word names for a large
# reduction in noise.
MIN_SINGLE_WORD_MENTIONS = 3

# A capitalized run, allowing the lowercase connectors that show up inside
# real HSR names ("Abominations of Abundance", "Sea of Souls"). Apostrophes
# are included so "Mara-struck"-style possessives don't split a name.
_CAPITALIZED_RUN = re.compile(
    r"[A-Z][a-z’']+(?:\s+(?:of|the|de|and|in|on)\s+[A-Z][a-z’']+|\s+[A-Z][a-z’']+)*"
)

_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

# How many separate entries must show a one-word candidate in running
# prose before it is accepted as a real name everywhere. Evidence from a
# single entry is too easy to come by in quoted dialogue.
MIN_EVIDENCE_ENTRIES = 2


def _is_embedded_in_prose(text: str, start: int) -> bool:
    """True if the token at `start` follows an ordinary lowercase word on
    the same clause -- "fled toward Belobog" -- with no quote, bracket or
    sentence-ending punctuation in between.

    Stricter than "not _is_sentence_initial", and deliberately so: it is
    the gate for corpus-wide promotion of a one-word name, where a false
    positive propagates everywhere. Requiring a preceding lowercase letter
    rules out the dialogue-opening case (`said, "Look`) that the plain
    sentence-initial test misses, at the cost of ignoring perfectly good
    evidence like "of Belobog," -- which is fine, since some other
    sentence in a 658-entry corpus will supply it."""
    j = start - 1
    while j >= 0 and text[j] in " \t\n":
        j -= 1
    return j >= 0 and text[j].islower()

# Titles that precede a name ("Madam Herta", "Miss Robin", "Lord Ravager").
# Stripped so the mention resolves to the person, not to a separate entity
# per honorific.
_HONORIFICS = {
    "madam", "miss", "mister", "mr", "mrs", "ms", "dr", "doctor",
    "lord", "lady", "master", "sir", "dame", "captain", "general",
    "commander", "elder", "saint", "father", "mother", "aunt", "uncle",
    # Rank and title nouns behave identically: they precede a name
    # ("King Gilgamesh") and are not entities standing alone. Bare "King"
    # was otherwise reaching the featured "today's connection" slot.
    "king", "queen", "emperor", "empress", "prince", "princess",
    "duke", "duchess", "baron", "admiral", "marshal", "sergeant",
}

# Capitalized words that are not proper nouns in this corpus. These are
# words that survive the sentence-initial filter because they genuinely
# appear mid-sentence (in dialogue, after a dash, inside a quote) but carry
# no entity meaning.
_NOT_ENTITIES = {
    "i", "i'll", "i've", "i'm", "i'd", "it", "it's", "he", "she", "they",
    "you", "we", "us", "me", "my", "your", "our", "his", "her", "their",
    "the", "a", "an", "and", "but", "or", "if", "so", "then", "than",
    "this", "that", "these", "those", "there", "here", "when", "where",
    "what", "which", "who", "whom", "whose", "why", "how", "all", "any",
    "some", "one", "two", "three", "no", "not", "now", "yes", "oh", "ah",
    "as", "in", "on", "at", "by", "to", "of", "up", "out", "off", "down",
    "welcome", "indeed", "meanwhile", "instead", "besides", "otherwise",
    "finally", "later", "soon", "today", "tomorrow", "yesterday",
    "ever", "never", "always", "often", "again", "away", "back", "very",
    "however", "after", "before", "even", "just", "only", "though",
    "although", "perhaps", "maybe", "like", "once", "every", "each",
    "still", "yet", "also", "because", "since", "while", "until", "for",
    "from", "with", "without", "into", "onto", "upon", "over", "under",
    "through", "during", "against", "between", "among", "about", "above",
    "below", "behind", "beyond", "within", "across", "toward", "towards",
    "let", "let's", "don't", "doesn't", "didn't", "can't", "won't",
    "people", "someone", "everyone", "anyone", "nobody", "something",
    "everything", "anything", "nothing", "day", "time", "year", "years",
    "world", "life", "death", "man", "woman", "child", "god", "gods",
    "well", "good", "great", "long", "many", "much", "more", "most",
    "thank", "thanks", "please", "sorry", "hello", "goodbye", "okay",
}

# Surface forms that should resolve onto one canonical entity but do not
# normalize together mechanically. Kept deliberately small and evidence-
# driven -- each one was confirmed against the real corpus rather than
# assumed -- and meant to grow as new categories surface new aliases.
# Keys and values are compared after _canonical_key() normalization.
_ALIASES = {
    "luofu": "Xianzhou Luofu",
    "the luofu": "Xianzhou Luofu",
    "yaoqing": "Xianzhou Yaoqing",
    "zhuming": "Xianzhou Zhuming",
    "express": "Astral Express",
    "trailblaze": "Trailblazer",
    "ipc": "Interastral Peace Corporation",
}


def _is_non_entity_word(word: str) -> bool:
    """A lone word that can never be an entity on its own.

    Covers the stoplist plus any bare honorific: the scrapers' text writes
    "Mr. Svarog", and the capitalized-run regex stops at the period, so
    "Mr" arrives here detached from the name it belongs to. Left alone it
    ranked as a top-20 entity spanning all three categories. "General" and
    "Madam" leak the same way."""
    bare = word.lower().rstrip(".")
    return bare in _NOT_ENTITIES or bare in _HONORIFICS


def slugify(name: str) -> str:
    """Stable, URL-safe id for an entity. Matches the general shape of the
    scrapers' own slugify so ids look consistent across data files."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unnamed"


def _canonical_key(surface: str) -> str:
    """Fold the surface variations that mean the same entity into one key:
    case, surrounding whitespace, a trailing possessive, and a trailing
    plural "s" ("Cloud Knight" / "Cloud Knights", "Chrysos Heir" /
    "Chrysos Heirs" -- HSR faction names alternate between the two
    constantly).

    Mirrors the intent of validate.py's _normalize_noun_form, but operates
    on a whole multi-word phrase rather than a single token.

    A leading article is deliberately NOT stripped. "The Herta" is a
    different character from "Herta" in this corpus (the puppet and Madam
    Herta are distinct people with distinct stories), and folding the
    article collapsed them into one node whose display name flickered
    between the two depending on entry order. Article variants that really
    are the same entity ("The Luofu" -> "Xianzhou Luofu") are handled
    explicitly in _ALIASES, where the claim is reviewable."""
    key = " ".join(surface.split()).lower()
    key = re.sub(r"[’']s$", "", key)
    if key.endswith("s") and len(key) > 4:
        key = key[:-1]
    return key


def _strip_honorific(surface: str) -> str:
    """"Madam Herta" -> "Herta", so a mention resolves to the person
    rather than to one node per honorific.

    An honorific only counts as one when a *name* follows it, i.e. the
    next word is itself capitalized. Several honorifics here double as
    ordinary title nouns -- "Master of Destruction" and "Lord of
    Destruction" are real HSR epithets -- and stripping unconditionally
    turned both into the fragment "of Destruction", which then merged
    into one nonsense entity spanning two categories."""
    parts = surface.split()
    while (
        len(parts) >= 2
        and parts[0].lower().rstrip(".") in _HONORIFICS
        and parts[1][:1].isupper()
    ):
        parts = parts[1:]
    return " ".join(parts) if parts else surface


def build_character_gazetteer(entries: list[dict]) -> dict[str, str]:
    """Map every character surface form -> canonical display name, derived
    from character_story entry names ("Acheron -- Story 1" -> "Acheron").

    Alternate-outfit variants are folded onto the base character: "Dan Heng
    * Imbibitor Lunae" and "Dan Heng" are one person as far as the lore
    graph is concerned, and keeping them apart would split that person's
    edges across two weakly-connected nodes."""
    gazetteer: dict[str, str] = {}
    for entry in entries:
        if entry.get("category") != "character_story":
            continue
        # subtitle carries the character too, but the name is the field
        # build_dataset.py merges on, so it is the more reliable source.
        display = entry["name"].split(" — ")[0].strip()
        if not display:
            continue
        base = display.split(" • ")[0].strip()
        for surface in {display, base}:
            gazetteer[_canonical_key(surface)] = base
    return gazetteer


def collect_confirmed_single_words(entries: list[dict]) -> set[str]:
    """Canonical keys of one-word names the corpus proves are real, by
    having them appear at least once *away* from the start of a sentence.

    This exists because per-occurrence sentence-initial filtering is too
    blunt on its own: it correctly rejects "However, the guard left" but
    also silently drops "Belobog stood quiet", losing a genuine proper
    noun purely because of where it sat in a sentence. Evidence is
    therefore gathered corpus-wide first, and every occurrence of a
    confirmed word then counts wherever it sits.

    The evidence bar is deliberately strict, because this rule amplifies
    whatever it accepts across the entire corpus. A first attempt merely
    required one not-sentence-initial use, and promoted "Do", "Look",
    "Are" and "You're" to top-ranked entities: HSR lore is full of quoted
    dialogue, and in `He said, "Look at that."` the word "Look" is
    preceded by a comma, so the sentence-initial test says mid-sentence
    while a reader plainly sees a sentence opening. So a mention only
    counts as evidence when it sits in genuine running prose -- directly
    after a lowercase word character, with no quote or bracket between --
    and the word must clear that bar in MIN_EVIDENCE_ENTRIES separate
    entries, so a single odd line cannot mint an entity."""
    evidence: Counter = Counter()
    for entry in entries:
        text = entry.get("raw_text") or ""
        seen_in_entry: set[str] = set()
        for match in _CAPITALIZED_RUN.finditer(text):
            surface = _strip_honorific(" ".join(match.group(0).split()))
            if not surface or len(surface.split()) != 1:
                continue
            if _is_non_entity_word(surface):
                continue
            if _is_embedded_in_prose(text, match.start()):
                seen_in_entry.add(_canonical_key(surface))
        for key in seen_in_entry:
            evidence[key] += 1
    return {key for key, n in evidence.items() if n >= MIN_EVIDENCE_ENTRIES}


def extract_surface_forms(text: str, confirmed_single_words: set[str] | None = None) -> list[str]:
    """Every candidate entity mention in one piece of text, as it appears.

    Multi-word runs are kept even sentence-initially, since "Cloud Knights
    patrol the..." is a real mention and a two-word capitalized run is
    rarely an accident of punctuation. A single word opening a sentence is
    kept only if confirmed_single_words vouches for it (see
    collect_confirmed_single_words); passing None applies the strict
    per-text rule, which is useful in isolation but loses real names."""
    confirmed = confirmed_single_words or set()
    found: list[str] = []
    for match in _CAPITALIZED_RUN.finditer(text):
        surface = _strip_honorific(" ".join(match.group(0).split()))
        if not surface:
            continue
        words = surface.split()
        if len(words) == 1:
            if _is_non_entity_word(surface):
                continue
            if _is_sentence_initial(text, match.start()) and _canonical_key(surface) not in confirmed:
                continue
        else:
            # A run whose every word is a non-entity ("But The", "And Then")
            # is punctuation noise, not a name.
            if all(w.lower() in _NOT_ENTITIES for w in words):
                continue
        found.append(surface)
    return found


def resolve_surface(
    surface: str, gazetteer: dict[str, str], alias_keys: dict[str, str]
) -> tuple[str, str, str]:
    """Resolve one surface form to (canonical_key, display_name, kind).

    Order matters. The articled form is tried against the gazetteer
    *first*, because "The Herta" is a real character distinct from
    "Herta"; only if that fails is a leading article treated as noise, so
    "The Cloud Knights" and "Cloud Knights" land on one node while the two
    Hertas stay apart."""
    key = _canonical_key(surface)
    if key in gazetteer:
        return key, gazetteer[key], "character"

    stripped = _LEADING_ARTICLE.sub("", surface).strip()
    if stripped and stripped != surface:
        stripped_key = _canonical_key(stripped)
        if stripped_key in gazetteer:
            return stripped_key, gazetteer[stripped_key], "character"
        surface, key = stripped, stripped_key

    if key in alias_keys:
        canonical = alias_keys[key]
        resolved = _canonical_key(canonical)
        return resolved, canonical, "character" if resolved in gazetteer else "term"

    return key, surface, "term"


def build_entity_index(entries: list[dict]) -> list[dict]:
    """Entity nodes with the entries that mention them, most-connected
    first. Only entities meeting MIN_ENTRY_MENTIONS survive."""
    gazetteer = build_character_gazetteer(entries)
    alias_keys = {_canonical_key(k): v for k, v in _ALIASES.items()}
    # Pass 1: establish which one-word names the corpus can vouch for,
    # before counting anything. Pass 2 below then counts every mention.
    confirmed = collect_confirmed_single_words(entries)

    entry_ids: dict[str, set[str]] = defaultdict(set)
    surfaces: dict[str, Counter] = defaultdict(Counter)
    kinds: dict[str, str] = {}

    for entry in entries:
        for surface in extract_surface_forms(entry.get("raw_text") or "", confirmed):
            key, canonical, kind = resolve_surface(surface, gazetteer, alias_keys)
            # "character" is sticky: one gazetteer hit outranks any number
            # of generic-term resolutions for the same key.
            kinds[key] = "character" if kinds.get(key) == "character" or kind == "character" else "term"
            entry_ids[key].add(entry["id"])
            surfaces[key][canonical] += 1

    by_id = {e["id"]: e for e in entries}
    entities = []
    for key, ids in entry_ids.items():
        # Display name = the most common surface spelling actually seen,
        # so the UI shows "Cloud Knights" rather than a normalized key.
        display = surfaces[key].most_common(1)[0][0]
        threshold = MIN_SINGLE_WORD_MENTIONS if len(display.split()) == 1 else MIN_ENTRY_MENTIONS
        # A known character is exempt: the gazetteer already established it
        # is a real person, so the noise argument for the higher bar does
        # not apply and a one-word name like "Blade" should not be dropped.
        if kinds[key] != "character" and len(ids) < threshold:
            continue
        if len(ids) < MIN_ENTRY_MENTIONS:
            continue
        counts = Counter(by_id[i]["category"] for i in ids)
        entities.append(
            {
                "id": slugify(display),
                "name": display,
                "kind": kinds[key],
                "entry_ids": sorted(ids),
                "entry_count": len(ids),
                "category_counts": dict(sorted(counts.items())),
                "category_span": len(counts),
            }
        )

    # Most-connected first, and entities bridging more categories ahead of
    # equally-common ones confined to a single category -- a term linking a
    # light cone to a character story is the interesting kind.
    entities.sort(key=lambda e: (-e["category_span"], -e["entry_count"], e["name"]))

    # slugify can collide (e.g. two spellings normalizing alike); keep ids
    # unique so the site can address an entity by id without ambiguity.
    seen_slugs: Counter = Counter()
    for entity in entities:
        seen_slugs[entity["id"]] += 1
        if seen_slugs[entity["id"]] > 1:
            entity["id"] = f"{entity['id']}-{seen_slugs[entity['id']]}"
    return entities


# Fixed seed, same rationale as select_daily.py's: the rotation only needs
# to look arbitrary, not be unpredictable, and a fixed seed keeps the order
# reproducible across machines and runs.
CONNECTION_SHUFFLE_SEED = "hsr-lore-pipeline-connection-cycle-v1"

# Reach required to headline the "today's connection" slot. Two entries in
# two categories is technically a connection but makes a thin feature -- an
# unseeded rotation led with "Marketing Development Department" mentioned
# twice. At three the rotation still runs 196 days before repeating, so
# the quality bar costs nothing worth having.
MIN_CONNECTION_ENTRIES = 3


def build_connection_cycle(entities: list[dict], start_date: str | None = None) -> dict:
    """The rotation behind "today's connection".

    Only entities bridging more than one category are eligible: a term
    confined to character stories links fragments of the same kind, which
    is the least surprising thing the graph can show. A light cone that
    turns out to share a name with a relic set and someone's backstory is
    the reason this feature exists.

    Unlike daily_cycle.json this is rebuilt wholesale each run rather than
    extended. There is no published-history property to preserve here --
    the entity set is derived, not curated -- so stability across rebuilds
    costs more than it is worth."""
    eligible = [
        e["id"]
        for e in entities
        if e["category_span"] >= 2 and e["entry_count"] >= MIN_CONNECTION_ENTRIES
    ]
    shuffled = list(eligible)
    random.Random(CONNECTION_SHUFFLE_SEED).shuffle(shuffled)
    return {
        "cycle": shuffled,
        "cycle_start_date": start_date or date.today().isoformat(),
    }


def build_entities_file(entries: list[dict], start_date: str | None = None) -> dict:
    entities = build_entity_index(entries)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_count": len(entities),
        "connection_cycle": build_connection_cycle(entities, start_date),
        "entities": entities,
    }


def main() -> None:
    entries = json.loads(ENTRIES_PATH.read_text(encoding="utf-8"))
    data = build_entities_file(entries)
    ENTITIES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    entities = data["entities"]
    bridging = [e for e in entities if e["category_span"] >= 2]
    print(f"Wrote {len(entities)} entities -> {ENTITIES_PATH}", file=sys.stderr)
    print(f"  {len(bridging)} span more than one category", file=sys.stderr)
    print(f"  {sum(1 for e in entities if e['kind'] == 'character')} characters", file=sys.stderr)


if __name__ == "__main__":
    main()
