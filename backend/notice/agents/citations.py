"""Citation validation: every quote an agent relies on must exist in the source.

Quotes are matched whitespace- and case-insensitively (PDF extraction wraps
lines; models normalise spacing) and mapped back to exact character offsets in
the stored document text so the UI can highlight the passage.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def _normalise_with_map(s: str) -> tuple[str, list[int]]:
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(s.translate(_QUOTES)):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def locate_quote(haystack: str, quote: str, *, min_len: int = 8) -> tuple[int, int] | None:
    """Return (start, end) offsets of `quote` in `haystack`, or None."""
    q = _WS.sub(" ", quote.translate(_QUOTES)).strip().lower().strip(".…\"' ")
    if len(q) < min_len:
        return None
    norm, idx = _normalise_with_map(haystack)
    pos = norm.find(q)
    if pos < 0:
        # tolerate a model trimming an ellipsis-joined quote: try the longest fragment
        parts = [p.strip() for p in re.split(r"\.\.\.|…", q) if len(p.strip()) >= min_len]
        if len(parts) > 1:
            best = max(parts, key=len)
            pos = norm.find(best)
            q = best
        if pos < 0:
            return None
    start = idx[pos]
    end = idx[pos + len(q) - 1] + 1
    return start, end


@dataclass
class Citation:
    document_id: str
    quote: str
    char_start: int
    char_end: int
    item_id: str | None = None
    clause_ref: str | None = None
    label: str | None = None  # e.g. "Triggering message", "Clause 9.2"
    verified: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def cite(document_id: uuid.UUID, doc_text: str, quote: str, *, item_id=None, clause_ref=None, label=None,
         window: tuple[int, int] | None = None) -> Citation | None:
    """Build a verified citation, searching only inside `window` (e.g. one item) if given."""
    lo, hi = window or (0, len(doc_text))
    span = locate_quote(doc_text[lo:hi], quote)
    if span is None:
        return None
    s, e = span[0] + lo, span[1] + lo
    return Citation(document_id=str(document_id), quote=doc_text[s:e], char_start=s, char_end=e,
                    item_id=str(item_id) if item_id else None, clause_ref=clause_ref, label=label)
