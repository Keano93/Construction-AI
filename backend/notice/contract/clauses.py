"""Split contract text into numbered clauses."""

from __future__ import annotations

import re
from dataclasses import dataclass

# "9.2 Contractor's notice of a Change"  /  "8 TIME"  /  "Clause 10.1 Claim notice"
_HEADING = re.compile(r"^(?:Clause\s+)?(?P<ref>\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+(?P<title>[A-Z][^\n]{1,120})$", re.M)


@dataclass
class ClauseSpan:
    ref: str
    title: str
    text: str
    char_start: int
    char_end: int


def _is_heading(h: re.Match) -> bool:
    title = h.group("title").rstrip()
    if title.endswith((",", ";")):
        return False
    if "." not in h.group("ref"):
        # top-level headings are upper case ("8 TIME"); avoids wrapped lines like "20 Working Days after..."
        letters = [c for c in title if c.isalpha()]
        return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8
    return len(title.split()) <= 12


def split_clauses(text: str) -> list[ClauseSpan]:
    heads = [h for h in _HEADING.finditer(text) if _is_heading(h)]
    out: list[ClauseSpan] = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.start():end].rstrip()
        out.append(ClauseSpan(h.group("ref"), h.group("title").strip(), body, h.start(), h.start() + len(body)))
    # drop top-level headings with no body of their own (e.g. "8 TIME" followed directly by 8.2)
    return [c for c in out if "." in c.ref or len(c.text.splitlines()) > 1]
