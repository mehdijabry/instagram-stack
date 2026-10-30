"""The data the other bundle carried, loaded once and shared by every skill.

Three files, lifted from Jakeschincariol/instagram-agent-skill, where they sat
inside individual skills and could not be reached from anywhere else. Here they
are a library: `ig-reel` and `ig-caption-writer` score hooks from the same 26
formulas, every writing skill runs the same 199 anti-slop entries, and the
profile rubric is one file instead of one per caller.

Nothing here touches the network. These are static reference tables.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# hooks — 26 formulas, each with the trap that makes it fail
# --------------------------------------------------------------------------


def hooks() -> list[dict[str, Any]]:
    """Every hook formula, in the order the classifier tries them."""
    return _load("hooks")["hooks"]


def hook_rules() -> list[str]:
    """The six rules that apply to any hook, whichever formula it uses."""
    return _load("hooks")["rules"]


def hook_by_id(hook_id: str) -> dict[str, Any] | None:
    return next((h for h in hooks() if h.get("id") == hook_id), None)


def hook_ids() -> list[str]:
    return _load("hooks")["classify_order"]


# --------------------------------------------------------------------------
# slop — 199 entries across five classes
# --------------------------------------------------------------------------

_SLOP_CLASSES = ("invisible", "typographic", "words", "phrases", "structures")


def slop(kind: str | None = None) -> dict[str, list] | list:
    """The anti-slop tables. Pass a class name for just that one."""
    data = _load("slop")
    if kind is None:
        return {k: data[k] for k in _SLOP_CLASSES}
    if kind not in _SLOP_CLASSES:
        raise KeyError(f"unknown slop class {kind!r}; expected one of {_SLOP_CLASSES}")
    return data[kind]


def slop_total() -> int:
    """How many entries the tables hold, all classes together."""
    return sum(len(v) for v in slop().values())


@lru_cache(maxsize=1)
def _invisible_map() -> dict[str, str]:
    """codepoint -> replacement ('' to delete)."""
    out: dict[str, str] = {}
    for entry in slop("invisible"):
        cp = entry.get("cp", "")
        replacement = "" if entry.get("action") == "delete" else entry.get("replacement", "")
        # Entries name either one codepoint ("U+200B") or a whole block
        # ("U+E0000-U+E007F", the tag characters used to hide a payload inside
        # otherwise normal text). Both expand to the same lookup.
        for char in _codepoints(cp):
            out[char] = replacement
    return out


def _codepoints(spec: str) -> list[str]:
    """Expand 'U+200B' or 'U+E0000-U+E007F' into the characters they name."""
    parts = [p.strip() for p in spec.split("-") if p.strip().startswith("U+")]
    try:
        bounds = [int(p[2:], 16) for p in parts]
    except ValueError:
        return []
    if not bounds:
        return []
    if len(bounds) == 1:
        return [chr(bounds[0])]
    lo, hi = min(bounds), max(bounds)
    if hi - lo > 4096:  # refuse to expand an implausible range into memory
        return []
    return [chr(c) for c in range(lo, hi + 1)]


def strip_invisible(text: str) -> tuple[str, int]:
    """Remove zero-width and watermark characters.

    Returns the cleaned text and how many characters were removed. The count is
    the point: a caption that loses 40 invisible characters was pasted out of a
    model, and knowing that is the useful signal.

    This removes a fingerprint; it does not make text undetectable, and no skill
    in this bundle may tell a user that it does. See references/voice-rules.md.
    """
    table = _invisible_map()
    out = []
    removed = 0
    for ch in text:
        if ch in table:
            repl = table[ch]
            removed += 1
            if repl:
                out.append(repl)
        else:
            out.append(ch)
    cleaned = unicodedata.normalize("NFC", "".join(out))
    return cleaned, removed


def scan_slop(text: str) -> list[dict[str, Any]]:
    """Report every slop entry that fires on a draft, with its replacement.

    A report, never an edit — the writer decides. Each finding carries what was
    matched, what the table suggests instead, and which family it belongs to,
    so a draft with nine hits from one family reads as one habit rather than
    nine unrelated notes.
    """
    findings: list[dict[str, Any]] = []

    for cls in ("phrases", "words"):
        for entry in slop(cls):
            term = entry.get("find")
            if not term:
                continue
            pattern = rf"\b{re.escape(term)}\b" if " " not in term else re.escape(term)
            for m in re.finditer(pattern, text, re.IGNORECASE):
                findings.append({
                    "class": cls,
                    "match": m.group(0),
                    "at": m.start(),
                    "suggest": entry.get("replace", ""),
                    "family": entry.get("family", ""),
                })
                break  # one finding per entry; the count that matters is habits

    for entry in slop("structures"):
        rx = entry.get("regex")
        if not rx:
            continue
        m = re.search(rx, text)
        if m:
            findings.append({
                "class": "structures",
                "match": m.group(0)[:80],
                "at": m.start(),
                "suggest": entry.get("fix", ""),
                "family": entry.get("name", entry.get("id", "")),
            })

    for entry in slop("typographic"):
        src = entry.get("from")
        if src and src in text:
            findings.append({
                "class": "typographic",
                "match": src,
                "at": text.index(src),
                "suggest": entry.get("to", ""),
                "family": entry.get("name", ""),
            })

    _, invisible = strip_invisible(text)
    if invisible:
        findings.append({
            "class": "invisible",
            "match": f"{invisible} hidden character(s)",
            "at": 0,
            "suggest": "delete",
            "family": "watermark",
        })

    findings.sort(key=lambda f: f["at"])
    return findings


def desloppify(text: str, *, typographic: bool = True) -> tuple[str, list[dict[str, Any]]]:
    """Apply the table's own replacements and report every change made.

    Longest phrases first, so "in today's fast-paced world" is rewritten whole
    rather than half-caught by a shorter entry inside it. Returns the rewritten
    text and the list of changes, because a humaniser that edits silently is
    worse than one that does nothing — the writer has to see what moved.

    Structural entries are never auto-applied: "say the one thing you actually
    mean" is a judgement, not a substitution. They come back as findings only.
    """
    out = text
    changes: list[dict[str, Any]] = []

    entries = [(e, "phrases") for e in slop("phrases")] + [(e, "words") for e in slop("words")]
    entries.sort(key=lambda pair: -len(pair[0].get("find", "")))

    for entry, cls in entries:
        term = entry.get("find")
        if not term:
            continue
        replacement = entry.get("replace", "")
        pattern = rf"\b{re.escape(term)}\b" if " " not in term else re.escape(term)
        out, n = re.subn(pattern, lambda m: _match_case(m.group(0), replacement), out, flags=re.IGNORECASE)
        if n:
            changes.append({"class": cls, "from": term, "to": replacement, "count": n,
                            "family": entry.get("family", "")})

    if typographic:
        for entry in slop("typographic"):
            src, dst = entry.get("from"), entry.get("to", "")
            if src and src in out:
                n = out.count(src)
                out = out.replace(src, dst)
                changes.append({"class": "typographic", "from": entry.get("name", src),
                                "to": dst, "count": n, "family": "punctuation"})

    out, invisible = strip_invisible(out)
    if invisible:
        changes.append({"class": "invisible", "from": "hidden characters", "to": "",
                        "count": invisible, "family": "watermark"})

    out = _tidy_spacing(out)

    remaining = [f for f in scan_slop(out) if f["class"] == "structures"]
    for f in remaining:
        changes.append({"class": "structures", "from": f["match"], "to": f["suggest"],
                        "count": 0, "family": f["family"]})

    return out, changes


def _tidy_spacing(text: str) -> str:
    """Clean up after a substitution: an em dash that became a comma leaves the
    spaces that surrounded the dash behind it."""
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])\1+", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"[ \t]+\n", "\n", text)


def _match_case(original: str, replacement: str) -> str:
    """Keep the writer's capitalisation when swapping a term."""
    if not replacement:
        return ""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# --------------------------------------------------------------------------
# rubric — the 12-criterion profile score
# --------------------------------------------------------------------------


def rubric() -> list[dict[str, Any]]:
    return _load("rubric")["items"]


def rubric_total() -> int:
    return _load("rubric")["total"]


def score_profile(awarded: dict[str, int]) -> dict[str, Any]:
    """Turn per-criterion points into a score, and name what is costing most.

    `awarded` maps criterion id -> points given. Missing ids score zero, which
    is deliberate: an unassessed criterion is not a passed one.
    """
    items = rubric()
    total = rubric_total()
    got = 0
    losses = []
    for item in items:
        cid = item["id"]
        points = max(0, min(int(awarded.get(cid, 0)), int(item["points"])))
        got += points
        lost = int(item["points"]) - points
        if lost:
            losses.append({"id": cid, "lost": lost, "fix": item.get("full_marks", "")})
    losses.sort(key=lambda x: -x["lost"])
    return {
        "score": got,
        "total": total,
        "biggest_losses": losses[:3],
        "assessed": len([c for c in awarded if c in {i["id"] for i in items}]),
        "criteria": len(items),
    }
