"""Deterministic baseline for the Claims agent (OfflineProvider)."""

from __future__ import annotations

import re

from ...llm import offline_handler
from ...retrieval.embeddings import HashingEmbedder
from ..identifiers import identifiers
from .core import Evidence
from .schemas import ClaimNarrative, NarrativeCitation, QuantumHead, TimelineEntry, TimelineOut

SIG = [
    ("notice", r"contract notice|notice under|no record of a notice"),
    ("instruction", r"\bplease\b|instruct|go ahead|hold off|confirmed verbally"),
    ("effect", r"standing|idle|stood|lost|delay|slip|turned away|cancelled|waiting|behind|sat since|broken out"),
    ("mitigation", r"moved to|redeployed|diverted|use gate|instead"),
    ("record", r"recorded|depths|photos|records|m3|poured|excavated"),
]


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"(?<!\n)\n(?!\n)", " ", text.strip())  # re-join hard-wrapped lines, keep paragraph breaks
    out = []
    for s in re.split(r"(?<![Nn]o\.)(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", flat):
        s = s.strip()
        if len(s) >= 12 and not re.match(r"^(hi|dear|thanks|regards|kind regards)\b", s, re.I) and not s.endswith(","):
            out.append(s)
    return out or [text.strip()[:160]]


def _best_sentence(text: str, emb: HashingEmbedder, target: list[float], ids: set[str]) -> str:
    """The sentence most related to the claim events (shared identifiers, then lexical similarity)."""
    def score(s: str) -> float:
        noise = 0.5 if re.match(r"^(weather|labour)\s*:", s, re.I) else 0.0
        return sum(a * b for a, b in zip(target, emb.embed(s))) + 0.3 * len(ids & identifiers(s)) - noise
    return max(_sentences(text), key=score)


def _significance(text: str, first: bool) -> str:
    for sig, pat in SIG:
        if re.search(pat, text, re.I):
            return sig
    return "cause" if first else "record"


@offline_handler("claims_agent.timeline")
def _timeline(v: dict) -> TimelineOut:
    evidence: list[Evidence] = v["_evidence"]
    event_text = v["_event_text"]
    emb = HashingEmbedder()
    ev_vec = emb.embed(event_text)
    ev_ids = identifiers(event_text)
    entries = []
    for i, e in enumerate(evidence):
        sim = sum(a * b for a, b in zip(ev_vec, emb.embed(e.text)))
        if not (e.linked or sim >= 0.3 or (ev_ids & identifiers(e.text))):
            continue
        q = _best_sentence(e.text, emb, ev_vec, ev_ids)
        entries.append(TimelineEntry(evidence_id=e.id, description=re.sub(r"\s+", " ", q)[:200],
                                     significance=_significance(q, not entries), quote=q))
    text = " ".join(e.text for e in evidence).lower()
    gaps = [g for g, pat in (
        ("Daywork / labour allocation sheets for the affected work", r"daywork"),
        ("Plant hire records and invoices for standing plant", r"invoice|hire record"),
        ("Dated photographs referenced in the record", r"img_|photo"),
        ("Updated programme showing the effect on the critical path", r"programme"),
    ) if not re.search(pat, text) or g.startswith("Dated photographs")]
    return TimelineOut(entries=entries, gaps=gaps)


@offline_handler("claims_agent.narrative")
def _narrative(v: dict) -> ClaimNarrative:
    events = v["_events"]
    timeline = v["_timeline"]
    compliance = v["_compliance"]
    clauses = v["_clause_refs"]
    cats = {e["category"] for e in events}
    first = timeline[0] if timeline else None
    risky = [r for r in compliance if r["time_bar_risk"]]
    open_ = [r for r in compliance if r["state"] == "not_given_open"]
    notice_pos = "; ".join(f"clause {r['clause_ref']}: {r['text']}" for r in compliance) or "No notice obligations linked."
    effects = [t for t in timeline if t["significance"] == "effect"]
    heads = []
    if "change" in cats:
        heads.append(QuantumHead(head="Additional / changed work", basis="Measured and valued at contract rates or fair rates",
                                 records_needed=["measured quantities", "marked-up drawings", "material invoices"]))
    if effects or cats & {"delay", "disruption"}:
        heads.append(QuantumHead(head="Standing labour and plant", basis="Actual cost from allocation sheets and hire records",
                                 records_needed=["labour allocation sheets", "plant hire records", "site diary entries"]))
    if "delay" in cats:
        heads.append(QuantumHead(head="Time-related preliminaries", basis="Weekly preliminaries for the period of delay",
                                 records_needed=["updated programme", "preliminaries build-up"]))
    risks = [f"Clause {r['clause_ref']} notice for {r['event_ref']} is a condition precedent and was not given in time: "
             "the Employer's Representative is likely to argue the claim is barred." for r in risky]
    if open_:
        risks.append("Notices still open must be issued before their due dates: " + ", ".join(f"clause {r['clause_ref']} by {r['due_date']}" for r in open_))
    if len(timeline) < 3:
        risks.append("Thin contemporaneous record; strengthen with daywork sheets and photographs.")
    cites = [NarrativeCitation(source=t["evidence_id"], quote=t["quote"]) for t in timeline[:4]]
    cites += [NarrativeCitation(source=f"clause {ref}", quote=q) for ref, q in clauses[:2]]
    titles = "; ".join(e["title"] for e in events)
    return ClaimNarrative(
        title=v.get("title") or f"Claim for {', '.join(sorted(cats))}: {events[0]['title'][:80]}",
        executive_summary=(f"This claim concerns {len(events)} event(s) ({titles[:200]}). The record contains "
                           f"{len(timeline)} relevant entries from {timeline[0]['date'][:10] if first else 'n/a'}. "
                           "Quantum is to be completed from the records listed."),
        entitlement="The Contractor relies on " + (", ".join(f"clause {ref}" for ref, _ in clauses) or "[clauses to be confirmed]") +
                    ". These events are at the Employer's risk under the Contract.",
        notice_position=notice_pos,
        cause=" ".join(f"On {t['date'][:10]}, {t['description']}" for t in timeline if t["significance"] in ("cause", "instruction"))[:1500]
              or (f"On {first['date'][:10]}, {first['description']}" if first else "[to be completed]"),
        effect=" ".join(f"On {t['date'][:10]}, {t['description']}" for t in effects)[:1500] or "[effect to be established from records]",
        quantum_heads=heads, risks=risks or ["None identified by the baseline - review manually."], citations=cites,
        confidence=0.6 if len(timeline) >= 3 else 0.45,
    )
