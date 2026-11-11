"""Deterministic baseline assessor for the Revision agent (OfflineProvider)."""

from __future__ import annotations

import re

from ...llm import offline_handler
from .diff import only_revision_metadata
from .schemas import ChangeAssessment, RevisionAssessment

UPGRADE = re.compile(
    r"\b(triple|standby|duty and standby|diesel|additional|extra|enlarged|increased|upgraded?|acoustic|witnessed|"
    r"remote monitoring|including|fire[- ]rated|steel|stainless|deepened|thicker|category \d)\b", re.I)
DOWNPLAY = re.compile(r"\b(coordination|minor|no cost|tidy|numbering|clarification)\b", re.I)
PACKAGES = {
    "M&E": r"sprinkler|pump|tank|alarm|mep|mechanical|electrical|lighting|plant",
    "windows": r"window|glazing|glazed|W\d\d",
    "groundworks": r"foundation|pad|excavat|drainage|lift pit|civ-",
    "structure": r"str-|steel|core wall|lintel|slab|embed",
    "architectural": r"arc-|elevation|layout|partition|door|brick|balcony",
}
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _packages(text: str) -> list[str]:
    return [k for k, pat in PACKAGES.items() if re.search(pat, text, re.I)][:3] or ["unknown"]


def _numeric_increase(word_diff: list[dict]) -> float:
    best = 0.0
    for d in word_diff:
        a, b = _NUM.findall(d["old"]), _NUM.findall(d["new"])
        if a and b:
            try:
                fa, fb = float(a[0]), float(b[0])
            except ValueError:
                continue
            if fa > 0:
                best = max(best, fb / fa - 1)
    return best


def assess_one(c: dict) -> ChangeAssessment:
    old, new = c.get("old_text", ""), c.get("new_text", "")
    changed_words = " ".join(d["new"] for d in c.get("word_diff", [])) or new
    removed_words = " ".join(d["old"] for d in c.get("word_diff", []))
    pk = _packages(f"{c.get('label', '')} {new} {old}")

    def mk(**kw) -> ChangeAssessment:
        base = dict(change_id=c["id"], affected_packages=pk, evidence_quote_old=None, evidence_quote_new=None)
        base.update(kw)
        return ChangeAssessment(**base)

    # registers
    if c.get("fields"):
        f = c["fields"]
        if c["kind"] == "added":
            return mk(summary=f"New document issued: {c['label']}.", change_type="new_information", cost_impact="unknown",
                      time_impact="possible", potential_variation=True, confidence=0.55,
                      rationale="A document not in the previous register; check whether it adds or changes work.",
                      evidence_quote_new=c["key"])
        if c["kind"] == "removed":
            return mk(summary=f"Document withdrawn: {c['label']}.", change_type="unclear", cost_impact="unknown",
                      time_impact="unknown", potential_variation=False, confidence=0.5,
                      rationale="Withdrawn from the register; confirm whether the work it showed is omitted.")
        if c["kind"] == "revised":
            rev = f.get("Revision") or next(iter(f.values()))
            title_changed = "Title" in f
            return mk(summary=f"{c['key']} revised {rev[0]} → {rev[1]}" + (" and retitled" if title_changed else "") + ".",
                      change_type="unclear", cost_impact="unknown", time_impact="possible", potential_variation=True,
                      confidence=0.5, rationale="The register shows a new revision but not its content; compare the drawing revisions.",
                      evidence_quote_new=c["key"])
        return mk(summary=f"Register details changed for {c['key']}.", change_type="administrative", cost_impact="none",
                  time_impact="none", potential_variation=False, confidence=0.6, rationale="Only non-revision fields changed.")

    # text units
    if c["kind"] == "modified" and only_revision_metadata(old, new):
        return mk(summary="Revision/date details updated.", change_type="administrative", cost_impact="none", time_impact="none",
                  potential_variation=False, confidence=0.8, rationale="Only revision identifiers and dates changed.",
                  affected_packages=[])
    if c["kind"] == "added" and DOWNPLAY.search(new):
        return mk(summary="Revision note added.", change_type="administrative", cost_impact="none", time_impact="none",
                  potential_variation=False, confidence=0.7, rationale="Describes the revision rather than changing work.",
                  affected_packages=[], evidence_quote_new=new[:80])
    inc = _numeric_increase(c.get("word_diff", []))
    upg = UPGRADE.search(changed_words)
    if c["kind"] == "removed":
        return mk(summary=f"Removed: {c['label']}", change_type="scope_decrease", cost_impact="low", time_impact="none",
                  potential_variation=True, confidence=0.6, rationale="Text removed from the document; possible omission.",
                  evidence_quote_old=old[:120])
    if upg or inc > 0.15:
        band = "medium" if (upg and inc > 0.15) or inc > 0.3 or (upg and re.search(r"diesel|standby|triple|category", changed_words, re.I)) else "low"
        ctype = "specification_change" if upg else "quantity_change"
        quote_new = upg.group(0) if upg else next((d["new"] for d in c["word_diff"] if _NUM.search(d["new"])), None)
        quote_old = next((d["old"] for d in c.get("word_diff", []) if d["old"]), None)
        return mk(summary=f"{c['label']}: " + "; ".join(f"{d['old'] or '—'} → {d['new'] or '—'}" for d in c.get("word_diff", [])[:3]),
                  change_type=ctype, cost_impact=band, time_impact="possible", potential_variation=True,
                  confidence=0.7 if band == "medium" else 0.6,
                  rationale=("Upgraded specification" if upg else f"Quantity/dimension up by about {inc:.0%}") + "; priced on the earlier revision.",
                  evidence_quote_new=quote_new if quote_new and len(quote_new) >= 1 else None,
                  evidence_quote_old=quote_old if quote_old and len(quote_old) >= 1 else None)
    if removed_words and not changed_words.strip():
        return mk(summary=f"Text removed in {c['label']}", change_type="scope_decrease", cost_impact="low", time_impact="none",
                  potential_variation=True, confidence=0.55, rationale="Possible omission.")
    return mk(summary=f"{c['label']} changed.", change_type="unclear", cost_impact="unknown", time_impact="unknown",
              potential_variation=True, confidence=0.45, rationale="Wording changed; impact not clear from the text alone.")


@offline_handler("revision_agent.assess_changes")
def _assess(v: dict) -> RevisionAssessment:
    changes = v["_changes"]
    out = [assess_one(c) for c in changes]
    flags = []
    pv = [a for a in out if a.potential_variation]
    for c in changes:
        m = DOWNPLAY.search(c.get("new_text", ""))
        if m and pv and c["kind"] in ("added", "modified"):
            flags.append(f"The revision describes itself as '{c['new_text'][:80].strip()}', but {len(pv)} change(s) look like potential variations.")
            break
    n_admin = sum(1 for a in out if a.change_type == "administrative")
    summary = (f"{len(changes)} change(s) between revisions: {len(pv)} potential variation(s), {n_admin} administrative. "
               "Offline baseline assessment; review each change against the drawings.")
    return RevisionAssessment(overall_summary=summary, downplaying_flags=flags, assessments=out)
