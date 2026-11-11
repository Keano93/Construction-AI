"""Deterministic contract-rule extractor used by the OfflineProvider.

Pattern-based: finds sentences with a stated period ("within 10 Working Days
after ...", "not later than the 25th day of each month") and classifies them by
keywords. It is deliberately conservative and reports modest confidence; the
user approves every rule before it goes live either way.
"""

from __future__ import annotations

import re

from ..llm import offline_handler
from .schemas import ContractExtraction, ExtractedRule

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "fourteen": 14, "fifteen": 15, "twenty": 20, "twenty-one": 21, "twenty-eight": 28, "thirty": 30}
_PERIOD = re.compile(
    r"(?:within|not less than|not later than|no later than)\s+(?:(?P<word>[a-z-]+)\s+\()?(?P<num>\d+)?\)?\s*"
    r"(?P<unit>Working Days?|working days?|Business Days?|days?|weeks?|months?)",
    re.I,
)
_SENT_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")
_DAY_OF_MONTH = re.compile(r"(\d{1,2})(?:st|nd|rd|th) day of each month", re.I)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:per cent|%)", re.I)


def _unit(u: str) -> str:
    u = u.lower()
    if "working" in u or "business" in u:
        return "working_days"
    if u.startswith("week"):
        return "weeks"
    if u.startswith("month"):
        return "months"
    return "calendar_days"


def _categories(text: str, title: str) -> list[str]:
    t = re.sub(r"\([^)]*\)", "", f"{title} {text}").lower()  # ignore parentheticals ("whether or not completion is delayed")
    if "claim" in title.lower():
        return ["change", "delay", "disruption"]
    cats = []
    if any(k in t for k in ("change", "site conditions", "discrepanc", "ambiguity", "physical conditions")):
        cats.append("change")
    if any(k in t for k in ("delay", "extension of time")):
        cats.append("delay")
    if any(k in t for k in ("instruction", "direction")):
        cats.append("instruction")
    if "disrupt" in t:
        cats.append("disruption")
    return cats


def _rule_type(sentence: str, title: str) -> str:
    s, t = sentence.lower(), title.lower()
    if "retention" in t or "retain" in s:
        return "retention"
    if any(k in t for k in ("payment", "certificate")) or "payment application" in s:
        return "payment"
    if "particulars" in t and ("delay" in t or "extension of time" in s):
        return "eot"
    if "proposal" in t or "proposal for the adjustment" in s:
        return "variation"
    if any(k in s for k in ("bar the claim", "shall bar")):
        return "time_bar"
    return "notice"


def extract_rules_offline(clauses: list[dict], contract_form: str | None) -> ContractExtraction:
    rules: list[ExtractedRule] = []
    working_def = None
    for c in clauses:
        text, ref, title = c["text"], c["ref"], c["title"]
        if "Working Day" in text and "means" in text and working_def is None:
            m = re.search(r'"Working Day" means[^.]*\.', text)
            working_def = m.group(0) if m else None
        body = text.split("\n", 1)[1] if "\n" in text else text
        flat = re.sub(r"\s+", " ", body)
        for sent in _SENT_SPLIT.split(flat):
            sent = sent.strip()
            if not sent:
                continue
            pm = _PERIOD.search(sent)
            dm = _DAY_OF_MONTH.search(sent)
            if not pm and not dm:
                continue
            lower = sent.lower()
            if not any(k in lower for k in ("contractor shall", "the contractor", "employer shall pay", "shall issue", "released")):
                continue
            if "request any further information" in lower:
                continue  # information requests are not notices with entitlement consequences
            num = None
            unit = None
            if pm:
                num = int(pm.group("num")) if pm.group("num") else _NUM_WORDS.get((pm.group("word") or "").lower())
                unit = _unit(pm.group("unit"))
            rtype = _rule_type(sent, title)
            cp = bool(re.search(r"condition precedent|bar the claim|disentitle|shall not entitle", flat, re.I))
            cats = [] if rtype in ("payment", "retention") else _categories(sent, title)
            trigger = None
            tm = re.search(r"(?:after|of|from)\s+(.+?)(?:,\s|\.\s|\.$|$)", sent[pm.end():] if pm else "", re.I)
            if tm:
                trigger = tm.group(1).strip()
            pct = _PERCENT.search(sent)
            rules.append(ExtractedRule(
                rule_type=rtype,
                clause_ref=ref,
                title=title,
                summary=sent if len(sent) < 280 else sent[:277] + "...",
                trigger_event=trigger,
                event_categories=cats,
                period_value=num,
                period_unit=unit,
                recipient="Employer's Representative" if " ER" in f" {sent}" or "Employer's Representative" in sent else None,
                required_form="In writing" if "writing" in lower else None,
                condition_precedent=cp and rtype not in ("payment", "retention"),
                percentage=float(pct.group(1)) if pct else None,
                day_of_month=int(dm.group(1)) if dm else None,
                source_quote=sent,
                confidence=0.75 if num is not None else 0.6,
            ))
    return ContractExtraction(contract_form=contract_form, working_day_definition=working_def, rules=rules)


@offline_handler("contract_extraction.extract_rules")
def _offline(variables: dict) -> ContractExtraction:
    return extract_rules_offline(variables["_clauses"], variables.get("contract_form"))
