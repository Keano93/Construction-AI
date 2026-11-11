"""Deterministic baseline for the Notice agent (used by the OfflineProvider).

Keyword/pattern scoring with role awareness. It exists so the platform works
without network access and to give the eval a baseline the Claude path should
beat. It is intentionally simple and general — not tuned per message.
"""

from __future__ import annotations

import re
from datetime import date

from ...llm import offline_handler
from ...retrieval.embeddings import HashingEmbedder
from .core import EventView, MessageView, RuleView
from .schemas import Classification, DraftCitation, Evidence, NoticeDraftOut, RuleLink

P = lambda *xs: [re.compile(x, re.I) for x in xs]  # noqa: E731

SIGNALS: dict[str, list[re.Pattern]] = {
    "change": P(
        r"\brev(?:ision)?\.?\s*[A-Z]?\d*\b.*\b(?:attached|issued|now)\b", r"\brevised\b", r"\bnow \d", r"\bincreased\b",
        r"\benlarged?\b", r"\bgo(?:es)? (?:up )?from\b.*\bto\b", r"\binstead of\b", r"\brelocat|\bmoved? to\b|\bmove \d+mm",
        r"\bsoft (?:ground|material|spot|silt)|\briver channel|\balluvial|not shown on the site investigation",
        r"\bdon'?t match|\bdoes not match|\bdiscrepan|\bwhich one is right", r"\brejected the connection",
        r"\btriple glazed|\bchange to\b|\bnow (?:needs?|need) to\b", r"\bdeepened?\b", r"\bextra \d+|\badditional\b",
    ),
    "delay": P(
        r"\bdelay(?:ed)?\b", r"\bslip", r"\blost \w+ (?:weeks?|days?)", r"\bstill no\b", r"\bon hold\b", r"\bcan'?t hit\b",
        r"\bat risk\b", r"\bbehind\b", r"\bwere promised\b|\bwas due\b|\bwere due\b", r"\bno record of a notice",
        r"\bwaiting (?:on|for)\b", r"\bextension of time\b",
    ),
    "instruction": P(
        r"\bplease (?:excavate|proceed|hold|go ahead|set|deepen|order|replace|carry out|omit|add)\b", r"\bgo ahead with\b",
        r"\bcan you (?:set|get|move|order)\b", r"\binstructed\b", r"\bconfirmed verbally\b|\bverbally\b|\bas discussed on site\b",
        r"\bhold off\b", r"\btold (?:him|her|them) that'?s fine\b", r"\bwe'?d like to go with\b", r"\bwork to rev\b",
    ),
    "disruption": P(
        r"\bcan'?t get in\b|\bcouldn'?t get (?:in|into)\b", r"\bblocked?\b", r"\btook over\b", r"\bturned away\b", r"\bidle\b",
        r"\bstanding\b", r"\bsat since\b|\bcrew sat\b", r"\bpour .{0,40}cancelled|cancelled.{0,30}pour|pump sent away",
        r"\broad clos|\bclosed .{0,20}road|road closed\b", r"\bhalf idle\b|\blost the afternoon\b",
    ),
}
NOISE = P(
    r"\btoolbox\b", r"\bbbq\b", r"\btoilets?\b", r"\bskip swap\b", r"\bfire alarm test\b", r"\bscaffold inspection\b",
    r"\binterim payment application\b|\bapplication no\.?\s*\d", r"\binterim certificate\b", r"\bminutes of site meeting\b",
    r"\bcashflow\b", r"\bcommercial review\b", r"\bstorm warning\b", r"\bdelivered\b|\bdelivery of\b", r"\bpoured\b",
    r"\bsetting out .{0,30}done\b|\bsurvey .{0,20}complete\b", r"\bconfirming (?:our|we)\b", r"\bchristmas shutdown\b",
)
ER_ROLES = {"employers_representative"}
DESIGN_ROLES = {"architect", "engineer", "consultant", "employer", "utility"}


def _score(text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores, hits = {}, {}
    for cat, pats in SIGNALS.items():
        found = [m.group(0) for p in pats if (m := p.search(text))]
        scores[cat], hits[cat] = len(found), found
    return scores, hits


def _sentence_with(text: str, needle: str) -> str:
    for s in re.split(r"(?<![Nn]o\.)(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", text):
        if needle.lower() in s.lower() and len(s.strip()) >= 8:
            return s.strip()
    return text.strip()[:200]


_ID = re.compile(r"\b(?:[A-Z]{1,4}-[A-Z]{1,4}-\d{2,4}|[A-Z]{1,2}\d{1,2}(?:\s?-\s?[A-Z]?\d{1,2})?|RFI\s?\d+|[A-Z]\s?L\d)\b")
_SUBJ_PREFIX = re.compile(r"^(?:re|fw|fwd):\s*", re.I)


def _ids(text: str) -> set[str]:
    return {re.sub(r"\s", "", m.group(0)).upper() for m in _ID.finditer(text)}


def _related_event(text: str, msg: MessageView, events: list[EventView]) -> str | None:
    """Same event if it shares a specific identifier (grid ref, drawing no., RFI) or is lexically very similar,
    and was raised within the last 30 days."""
    if not events:
        return None
    emb = HashingEmbedder()
    mv = emb.embed(text)
    ids = _ids(text)
    best, best_score = None, 0.0
    for ev in events:
        if msg.timestamp and (msg.timestamp.date() - date.fromisoformat(ev.trigger_date)).days > 30:
            continue
        ev_text = f"{ev.title} {ev.description}"
        sim = sum(a * b for a, b in zip(mv, emb.embed(ev_text)))
        shared = ids & _ids(ev_text)
        score = sim + (0.3 if shared else 0.0)
        if score > best_score:
            best, best_score = ev, score
    return best.ref if best is not None and best_score > 0.45 else None


def classify_offline(msg: MessageView, rules: list[RuleView], events: list[EventView]) -> Classification:
    text = msg.text
    scores, hits = _score(text)
    noise_hits = [m.group(0) for p in NOISE if (m := p.search(text))]
    role = msg.author_role

    # role-aware adjustments
    directive = scores["instruction"] > 0
    if directive and role in ER_ROLES and msg.channel in ("whatsapp", "diary"):
        scores["instruction"] += 2  # oral / informal ER instruction needs written confirmation
    elif directive and role in DESIGN_ROLES:
        scores["instruction"] += 2  # direction from someone other than the ER
    elif directive and role in ER_ROLES and msg.channel == "email":
        scores["change"] += 1  # written ER instruction: a change rather than an instruction to confirm
    if msg.channel == "diary" and re.search(r"\bverbally\b|\basked\b|\binstructed\b", text, re.I) and role != "contractor_internal":
        scores["instruction"] += 1
    if msg.channel == "diary" and re.search(r"\bverbally\b|\binstructed\b", text, re.I):
        scores["instruction"] += 2
    if scores["disruption"] and re.search(r"irish water|esb|network operator|utility|employer'?s own|lvhp", text, re.I):
        scores["disruption"] += 2
    if role == "subcontractor" and re.search(r"\bour (?:galvaniser|supplier|factory)\b", text, re.I):
        scores["delay"] = 0  # subcontractor's own supply chain: contractor risk

    best = max(scores, key=lambda k: (scores[k], ["disruption", "instruction", "delay", "change"].index(k)))
    top = scores[best]
    total = sum(scores.values())
    if top == 0 or (noise_hits and top <= 1 and len(noise_hits) >= 1):
        category, conf = "noise", 0.8 if not top else 0.6
    else:
        category = best
        margin = top - sorted(scores.values())[-2]
        conf = min(0.9, 0.55 + 0.1 * top + 0.05 * margin - (0.1 if noise_hits else 0))

    related = _related_event(text, msg, events) if category != "noise" else None

    links: list[RuleLink] = []
    if category != "noise":
        candidates = [r for r in rules if category in r.event_categories and r.rule_type in ("notice", "time_bar")]
        ground = bool(re.search(r"soft|river channel|alluvial|site investigation|ground", text, re.I))
        discrepancy = bool(re.search(r"match|discrepan|which one is right|inconsisten", text, re.I))

        def pref(r: RuleView) -> tuple:
            t = r.title.lower()
            score = 0
            if category == "instruction":
                if role in ER_ROLES and "oral" in t:
                    score -= 3
                if role not in ER_ROLES and ("other than" in t or "direction" in t):
                    score -= 3
            if category == "change":
                if ground and "site conditions" in t:
                    score -= 3
                if discrepancy and "discrepanc" in t:
                    score -= 3
                if "change" in t:
                    score -= 1
            if "claim" in t:
                score += 2  # generic claim notice ranks after specific notices
            return (score, r.period_value or 99)

        def applies(r: RuleView) -> bool:
            """Specialised notice rules only apply when their specific condition is present."""
            t = r.title.lower()
            if "site conditions" in t or "ground" in t:
                return ground
            if "discrepanc" in t or "ambiguit" in t:
                return discrepancy
            if "oral" in t:
                return role in ER_ROLES
            if "other than" in t or "direction" in t:
                return role not in ER_ROLES and role in DESIGN_ROLES | {"unknown"}
            return True

        candidates = [r for r in candidates if applies(r)]
        for r in sorted(candidates, key=pref)[:2]:
            links.append(RuleLink(rule_id=r.id, clause_ref=r.clause_ref, reason=f"{category} event; clause {r.clause_ref} {r.title}"))

    evid = []
    for cat in (category, *[k for k in scores if k != category]):
        for h in hits.get(cat, [])[:2]:
            q = _sentence_with(text, h)
            if q not in [e.quote for e in evid]:
                evid.append(Evidence(quote=q, why=f"signals {cat}: '{h}'"))
        if len(evid) >= 2:
            break
    first_line = re.sub(r"\s+", " ", text.strip().split("\n")[0])[:90]
    lead = evid[0].quote if evid else first_line
    subject = _SUBJ_PREFIX.sub("", msg.subject or "")
    title = subject if msg.channel == "email" and subject else re.sub(r"\s+", " ", lead)[:110]
    trig = msg.timestamp.date().isoformat() if msg.timestamp else None
    return Classification(
        category=category,
        secondary_categories=[k for k, v in sorted(scores.items(), key=lambda kv: -kv[1]) if v and k != category][:2],
        confidence=round(conf, 2),
        title=title,
        summary=re.sub(r"\s+", " ", text.strip())[:300],
        trigger_date=trig if category != "noise" else None,
        trigger_date_basis="Message date (offline baseline does not infer earlier awareness)",
        evidence=evid if category != "noise" else [],
        linked_rules=links,
        related_event_ref=related,
    )


@offline_handler("notice_agent.classify")
def _classify(v: dict) -> Classification:
    return classify_offline(v["_message"], v["_rules"], v["_events"])


# --- drafting ------------------------------------------------------------

OPENERS = {
    "change": ("The Contractor gives notice under clause {ref} that it considers the following requires a Change for "
               "which no Change Order has been issued."),
    "delay": ("The Contractor gives notice under clause {ref} that the progress of the Works is being or is likely to be "
              "delayed by a Delay Event."),
    "instruction": "The Contractor gives notice under clause {ref} in respect of the following instruction or direction.",
    "disruption": ("The Contractor gives notice under clause {ref} that the progress of the Works has been disrupted by "
                   "an act or omission for which the Employer is responsible."),
}
NEXT_STEPS = {
    "change": "The Contractor will submit its proposal for the adjustment of the Contract Sum and any extension of time in accordance with the Contract.",
    "delay": "The Contractor will submit full particulars of the delay and the extension of time claimed in accordance with the Contract.",
    "instruction": "The Contractor requests that the Employer's Representative confirm the instruction in writing, or confirm that it is withdrawn, before the Contractor acts on it further.",
    "disruption": "The Contractor is keeping contemporaneous records of the labour and plant affected and will submit them with its claim.",
}


@offline_handler("notice_agent.draft_notice")
def _draft(v: dict) -> NoticeDraftOut:
    ref, cat = v["clause_ref"], v["category"]
    quote = v["_evidence_quote"] or v["text"][:200]
    clause_sentence = v["_clause_quote"]
    recipient = v["_recipient"] or "The Employer's Representative"
    body = "\n\n".join([
        f"Dear {recipient.split(',')[0]},",
        f"{v['project_name']} - CONTRACT NOTICE under clause {ref} ({v['clause_title']})",
        "This letter is a notice under the Contract.",
        OPENERS.get(cat, OPENERS["change"]).format(ref=ref),
        f"Event: {v['title']}.",
        f"On {v['trigger_date']} the Contractor became aware of the following ({v['channel']} from {v['author']}, "
        f"{v['timestamp'][:10]}): \"{quote}\"",
        f"The Contractor relies on clause {ref}, which provides: \"{clause_sentence}\"",
        NEXT_STEPS.get(cat, ""),
        "Quantum and time effects: [to be confirmed].",
        "This notice is given without prejudice to the Contractor's other rights and entitlements under the Contract, "
        "including under clauses 8 (Time) and 10 (Claims).",
        f"Yours faithfully,\n\n{v['signatory']}",
    ])
    return NoticeDraftOut(
        subject=f"CONTRACT NOTICE - Clause {ref} - {v['title'][:80]}",
        recipient=recipient,
        body=body,
        citations=[DraftCitation(source="message", quote=quote), DraftCitation(source="clause", quote=clause_sentence)],
        assumptions=[f"Confirm the date of awareness ({v['trigger_date']}).", "Confirm the description of the event is complete.",
                     f"Confirm notice due date {v['due_date']} has not passed before sending."],
    )

