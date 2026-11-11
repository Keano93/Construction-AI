"""Construction identifiers shared by agents: drawing numbers, grid refs, RFIs, sketches, levels.

Used deterministically to cross-reference changes, events and documents
("RA-STR-110 rev C is already on the register as PE-001").
"""

from __future__ import annotations

import re

_ID = re.compile(
    r"\b(?:[A-Z]{1,4}-[A-Z]{1,4}-\d{2,4}"  # drawing numbers RA-STR-110, SK-S-031
    r"|[A-Z]{1,2}\d{1,2}(?:\s?-\s?[A-Z]?\d{1,2})?"  # grid refs B4-B6, P7
    r"|RFI\s?\d+"  # RFI 014
    r"|[A-Z]\s?L\d)\b"  # levels "B L1"
)
_DRAWING = re.compile(r"\b[A-Z]{1,4}-[A-Z]{1,4}-\d{2,4}\b")


_REVISION_CODE = re.compile(r"^[PCR]\d{1,2}$")  # P3, C2: revision codes, too ambiguous to cross-reference on


def identifiers(text: str) -> set[str]:
    ids = {re.sub(r"\s", "", m.group(0)).upper() for m in _ID.finditer(text or "")}
    return {i for i in ids if not _REVISION_CODE.match(i)}


def drawing_numbers(text: str) -> set[str]:
    return {m.group(0).upper() for m in _DRAWING.finditer((text or "").upper())}
