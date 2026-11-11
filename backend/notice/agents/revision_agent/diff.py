"""Deterministic revision diff. The list of changes is computed here, never by a model.

Two methods:
* register — tabular drawing/document registers (keyed by drawing number): added, removed, revised, modified.
* text — specifications and drawing notes split into units (numbered clauses/notes, labelled lines, paragraphs,
  with PDF line-wraps re-joined), aligned by their number/label, then by similarity.

Every change carries character spans into both documents so the UI can show the exact passages.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field

from ..identifiers import identifiers

# --- revision keys (pairing documents) ------------------------------------

_REV_TOKENS = re.compile(r"\b(?:rev(?:ision)?\.?\s*[a-z]?\d{0,3}[a-z]?|[pct]\d{1,2}|r\d{1,2}|v\d{1,2}(?:\.\d+)?)\b", re.I)


def revision_key(filename: str) -> str:
    """Filename with revision markers removed: 'Drawing Register Rev B.xlsx' -> 'drawing register'."""
    stem = re.sub(r"\.[a-z0-9]{2,5}$", "", filename.lower()).replace("_", " ")
    stem = _REV_TOKENS.sub(" ", stem)
    stem = re.sub(r"[_\-\s]+(?:final|issued|current|latest)\b", " ", stem)
    return re.sub(r"[\s_]+", " ", stem).strip(" -_")


# --- change model -----------------------------------------------------------

@dataclass
class Change:
    id: str
    kind: str  # added | removed | modified | revised
    key: str
    label: str
    old_text: str = ""
    new_text: str = ""
    old_span: list[int] | None = None
    new_span: list[int] | None = None
    word_diff: list[dict] = field(default_factory=list)  # [{"old": "72 m3", "new": "110 m3"}]
    fields: dict = field(default_factory=dict)  # register: {"Revision": ["B", "C"]}
    issue_date: str | None = None
    identifiers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_DATES = re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|"
                    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}\b", re.I)


def only_revision_metadata(old: str, new: str) -> bool:
    """True when two texts differ only in revision codes and dates (title blocks, headers)."""
    def strip(t: str) -> str:
        return _norm(_REV_TOKENS.sub(" ", _DATES.sub(" ", t)))
    return bool(old and new) and strip(old) == strip(new)


def word_diff(old: str, new: str) -> list[dict]:
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op != "equal":
            out.append({"old": " ".join(a[i1:i2]), "new": " ".join(b[j1:j2])})
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


# --- registers --------------------------------------------------------------

_KEY_HDR = re.compile(r"(drawing|dwg|document|doc)\.?\s*(no|number|ref|id)", re.I)


@dataclass
class _Row:
    cells: list[str]
    start: int
    end: int


def parse_register(text: str) -> tuple[list[str], dict[str, _Row]]:
    """Return (header, rows by key) from the tab-separated text produced by the XLSX extractor."""
    header: list[str] = []
    rows: dict[str, _Row] = {}
    key_col = None
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        cells = [c.strip() for c in stripped.split("\t")]
        if key_col is None:
            for i, c in enumerate(cells):
                if _KEY_HDR.search(c):
                    header, key_col = cells, i
                    break
        elif stripped.startswith("## Sheet:"):
            key_col = None if not rows else key_col
        elif len(cells) > key_col and cells[key_col]:
            rows.setdefault(cells[key_col].upper(), _Row(cells, pos, pos + len(stripped)))
        pos += len(line)
    return header, rows


def is_register(text: str) -> bool:
    header, rows = parse_register(text)
    return bool(header) and len(rows) >= 2


def diff_registers(base: str, revised: str) -> list[Change]:
    h_old, old = parse_register(base)
    h_new, new = parse_register(revised)
    header = h_new or h_old

    def col(pattern: str) -> int | None:
        return next((i for i, c in enumerate(header) if re.search(pattern, c, re.I)), None)

    rev_col, title_col, date_col = col(r"^rev"), col(r"title|description"), col(r"date")

    def cell(row: _Row | None, i: int | None) -> str:
        return row.cells[i] if row is not None and i is not None and i < len(row.cells) else ""

    changes: list[Change] = []
    for key in list(new) + [k for k in old if k not in new]:
        o, n = old.get(key), new.get(key)
        title = cell(n, title_col) or cell(o, title_col)
        label = f"{key} {title}".strip()
        if o is None:
            kind = "added"
        elif n is None:
            kind = "removed"
        else:
            diffs = {header[i] if i < len(header) else f"col{i}": [cell(o, i), cell(n, i)]
                     for i in range(max(len(o.cells), len(n.cells))) if cell(o, i) != cell(n, i)}
            if not diffs:
                continue
            kind = "revised" if rev_col is not None and cell(o, rev_col) != cell(n, rev_col) else "modified"
        ch = Change(
            id="", kind=kind, key=key, label=label,
            old_text=base[o.start:o.end] if o else "", new_text=revised[n.start:n.end] if n else "",
            old_span=[o.start, o.end] if o else None, new_span=[n.start, n.end] if n else None,
            issue_date=cell(n, date_col) or None, identifiers=sorted({key} | identifiers(title)),
        )
        if o and n:
            ch.fields = {header[i] if i < len(header) else f"col{i}": [cell(o, i), cell(n, i)]
                         for i in range(max(len(o.cells), len(n.cells))) if cell(o, i) != cell(n, i)}
        elif n:
            ch.fields = {header[i]: ["", v] for i, v in enumerate(n.cells) if i < len(header) and v}
        changes.append(ch)
    for i, c in enumerate(changes, 1):
        c.id = f"C{i}"
    return changes


# --- text documents -------------------------------------------------------

_MARKER = re.compile(r"^\s*(?:(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})[.)]?\s+|(?P<lbl>[A-Z][A-Za-z0-9 &/'-]{1,40}):\s*)")


@dataclass
class _Unit:
    text: str
    start: int
    end: int
    key: str | None


def _unit_key(text: str) -> str | None:
    m = _MARKER.match(text)
    if not m:
        return None
    if m.group("num"):
        return m.group("num")
    lbl = _REV_TOKENS.sub(" ", m.group("lbl").lower()).strip()
    return f"label:{lbl}" if lbl else None


def split_units(text: str) -> list[_Unit]:
    """Split into logical units; a wrapped line (previous line not ending in . : ; and no new marker) is joined."""
    units: list[_Unit] = []
    pos = 0
    cur: _Unit | None = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        stripped = body.strip()
        line_start = pos + (len(body) - len(body.lstrip()))
        pos += len(line)
        if not stripped:
            cur = None
            continue
        starts_new = cur is None or _MARKER.match(stripped) or cur.text.rstrip().endswith((".", ":", ";")) and stripped[:1].isupper()
        if starts_new:
            cur = _Unit(stripped, line_start, line_start + len(stripped), None)
            units.append(cur)
        else:
            cur.end = line_start + len(stripped)
            cur.text = text[cur.start:cur.end]
    for u in units:
        u.key = _unit_key(u.text)
    return units


def diff_text(base: str, revised: str) -> list[Change]:
    old, new = split_units(base), split_units(revised)
    pairs: list[tuple[_Unit | None, _Unit | None]] = []
    used_old: set[int] = set()
    used_new: set[int] = set()

    # 1. align by number / label
    old_by_key = {}
    for i, u in enumerate(old):
        if u.key and u.key not in old_by_key:
            old_by_key[u.key] = i
    for j, u in enumerate(new):
        i = old_by_key.get(u.key) if u.key else None
        if i is not None and i not in used_old:
            pairs.append((old[i], u))
            used_old.add(i)
            used_new.add(j)
    # 2. identical text anywhere
    old_norm = {}
    for i, u in enumerate(old):
        if i not in used_old:
            old_norm.setdefault(_norm(u.text), i)
    for j, u in enumerate(new):
        if j in used_new:
            continue
        i = old_norm.get(_norm(u.text))
        if i is not None and i not in used_old:
            pairs.append((old[i], u))
            used_old.add(i)
            used_new.add(j)
    # 3. best similarity >= 0.6
    for j, u in enumerate(new):
        if j in used_new:
            continue
        best, best_r = None, 0.6
        for i, o in enumerate(old):
            if i in used_old:
                continue
            r = difflib.SequenceMatcher(a=_norm(o.text), b=_norm(u.text), autojunk=False).ratio()
            if r >= best_r:
                best, best_r = i, r
        if best is not None:
            pairs.append((old[best], u))
            used_old.add(best)
            used_new.add(j)
        else:
            pairs.append((None, u))
    pairs += [(o, None) for i, o in enumerate(old) if i not in used_old]

    def order(p):
        o, n = p
        return (n.start if n else (o.start if o else 0), 0 if n else 1)

    changes: list[Change] = []
    for o, n in sorted(pairs, key=order):
        if o and n and _norm(o.text) == _norm(n.text):
            continue
        ref = n or o
        flat = re.sub(r"\s+", " ", ref.text)
        label = flat if len(flat) <= 70 else flat[:70].rsplit(" ", 1)[0] + "…"
        kind = "modified" if o and n else ("added" if n else "removed")
        changes.append(Change(
            id="", kind=kind, key=ref.key or "", label=label,
            old_text=o.text if o else "", new_text=n.text if n else "",
            old_span=[o.start, o.end] if o else None, new_span=[n.start, n.end] if n else None,
            word_diff=word_diff(o.text, n.text) if o and n else [],
            identifiers=sorted(identifiers((o.text if o else "") + " " + (n.text if n else ""))),
        ))
    for i, c in enumerate(changes, 1):
        c.id = f"C{i}"
    return changes


def diff_documents(base: str, revised: str) -> tuple[str, list[Change]]:
    if is_register(base) and is_register(revised):
        return "register", diff_registers(base, revised)
    return "text", diff_text(base, revised)
