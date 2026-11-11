"""Unit tests that need no database: extraction, citations, prompts, clause splitting, Claude request shape."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from notice.agents.citations import locate_quote
from notice.agents.notice_agent.core import MessageView, RuleView, verify_classification
from notice.agents.notice_agent.schemas import Classification, Evidence, RuleLink
from notice.contract.clauses import split_clauses
from notice.ingestion.extractors import ExtractionError, extract, extract_diary, extract_whatsapp, looks_like_whatsapp
from notice.llm import ClaudeProvider, load_prompt
from notice.retrieval import HashingEmbedder, chunk_spans

WA = """17/08/2026, 07:42 - Tadhg O'Leary: Rebar delivered
second line of the same message
17/08/2026, 08:01 - Declan Murphy: <Media omitted>
[18/08/2026, 09:15:02] Rory Nagle: Rev C attached
"""


def test_whatsapp_parsing_android_and_ios():
    assert looks_like_whatsapp(WA)
    items = extract_whatsapp(WA)
    assert [i.author for i in items] == ["Tadhg O'Leary", "Rory Nagle"]
    assert items[0].text == "Rebar delivered\nsecond line of the same message"
    assert WA[items[0].char_start:items[0].char_end] == items[0].text
    assert items[1].timestamp.isoformat().startswith("2026-08-18T09:15:02")


def test_diary_parsing():
    text = "SITE DIARY — 2026-08-20 — Declan Murphy\nSoft ground at B4.\n\nSITE DIARY — 2026-08-21\nRain.\n"
    items = extract_diary(text)
    assert len(items) == 2 and items[0].author == "Declan Murphy"
    assert text[items[0].char_start:items[0].char_end] == "Soft ground at B4."


def test_eml_extraction():
    eml = (b"From: Rory Nagle <r@x.example>\nTo: Declan <d@x.example>\nSubject: Rev C\n"
           b"Date: Tue, 18 Aug 2026 10:14:00 +0100\n\nPlease work to rev C.\n")
    ex = extract("m.eml", eml)
    assert ex.kind == "email" and ex.items[0].subject == "Rev C"
    assert ex.text[ex.items[0].char_start:ex.items[0].char_end].strip() == "Please work to rev C."


def test_unsupported_extension():
    with pytest.raises(ExtractionError):
        extract("drawing.dwg", b"xx")


def test_locate_quote_tolerates_wrapping_and_case():
    hay = "The Contractor shall give notice to the ER within 10 Working\nDays after receiving it."
    s, e = locate_quote(hay, "within 10 working days after receiving it")
    assert hay[s:e] == "within 10 Working\nDays after receiving it"
    assert locate_quote(hay, "within 99 working days") is None
    assert locate_quote(hay, "short") is None  # too short to be a meaningful citation


def test_clause_splitter_skips_wrapped_numbers():
    text = "8 TIME\n8.3 Notice of delay\nGive notice within\n15 Working Days after becoming aware.\n9 CHANGES\n9.2 Notice of a Change\nWithin 10 days.\n"
    refs = [c.ref for c in split_clauses(text)]
    assert refs == ["8.3", "9.2"]


def test_prompts_load_and_render():
    p = load_prompt("notice_agent", "classify")
    assert p.version >= 1 and p.ref.startswith("notice_agent.classify@v")
    system, user = p.render(project="P", parties="-", rules="-", open_events="-", channel="email", timestamp="t",
                            author="a", author_role="r", subject="s", text="hello world")
    assert "hello world" in user and "Notice agent" in system
    with pytest.raises(KeyError):
        p.render(project="P")


def test_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder()
    a, b = e.embed("soft ground at grid B4"), e.embed("soft ground at grid B4")
    assert a == b and abs(sum(x * x for x in a) - 1) < 1e-9
    assert sum(x * y for x, y in zip(a, e.embed("soft ground B4"))) > sum(x * y for x, y in zip(a, e.embed("invoice payment")))


def test_chunk_spans_cover_text():
    text = "x" * 3000
    spans = chunk_spans(text, 0, len(text))
    assert spans[0][0] == 0 and spans[-1][1] == 3000


RULES = [RuleView("r1", "9.2", "Contractor's notice of a Change", "notice", ["change"], 10, "working_days", "...")]


def _cls(**kw):
    base = dict(category="change", secondary_categories=[], confidence=0.9, title="t", summary="s", trigger_date="2026-08-18",
                trigger_date_basis="b", evidence=[Evidence(quote="pads now 2.4m x 2.4m", why="bigger")],
                linked_rules=[RuleLink(rule_id="r1", clause_ref="9.2", reason="r")], related_event_ref=None)
    base.update(kw)
    return Classification(**base)


MSG = MessageView(text="Revised drawing: pads now 2.4m x 2.4m.", channel="email",
                  timestamp=datetime(2026, 8, 18, 10, 0), author="Engineer", author_role="engineer")


def test_verify_accepts_good_output():
    v = verify_classification(_cls(), MSG, RULES)
    assert v.confidence == 0.9 and v.primary_rule.clause_ref == "9.2" and not v.issues


def test_verify_penalises_fabricated_quote_and_unknown_rule():
    v = verify_classification(_cls(evidence=[Evidence(quote="something never said", why="x")],
                                   linked_rules=[RuleLink(rule_id="nope", clause_ref="99", reason="x")]), MSG, RULES)
    assert v.confidence < 0.5 and v.low_confidence
    assert v.auto_linked and v.rules[0].id == "r1"  # fell back to category-matched approved rule


def test_verify_rejects_future_trigger_date():
    v = verify_classification(_cls(trigger_date="2026-09-30"), MSG, RULES)
    assert v.trigger_date.isoformat() == "2026-08-18"


def test_claude_provider_request_shape(monkeypatch):
    """The Claude call uses structured outputs, explicit effort and server-side refusal fallbacks."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = ClaudeProvider()
    captured = {}

    def fake_parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=_cls(), model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5), _request_id="req_1")

    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=fake_parse)))
    p = load_prompt("notice_agent", "classify")
    res = provider.structured(task="notice_agent.classify", prompt=p, schema=Classification, max_tokens=4000,
                              variables=dict(project="P", parties="-", rules="-", open_events="-", channel="email", timestamp="t",
                                             author="a", author_role="r", subject="s", text="msg"))
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_format"] is Classification
    assert captured["output_config"] == {"effort": "medium"}
    assert captured["fallbacks"] == "default" and captured["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in captured
    assert res.output.category == "change" and res.usage["input_tokens"] == 10


def test_claude_provider_refusal_raises(monkeypatch):
    from notice.llm import LLMError

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = ClaudeProvider()
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
        parse=lambda **_: SimpleNamespace(stop_reason="refusal", parsed_output=None))))
    with pytest.raises(LLMError):
        provider.structured(task="t", prompt=load_prompt("notice_agent", "classify"), schema=Classification,
                            variables=dict(project="", parties="", rules="", open_events="", channel="", timestamp="",
                                           author="", author_role="", subject="", text=""))
