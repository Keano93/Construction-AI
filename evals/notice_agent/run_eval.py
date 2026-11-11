"""Notice agent eval: classification precision/recall and clause-linking accuracy.

    cd backend && python ../evals/notice_agent/run_eval.py [--provider offline|claude] [--limit N]

Runs without a database. Pipeline per run:
  1. Extract rules from the demo contract with the chosen provider and approve
     notice/time-bar rules whose source quotes verify (same policy as the seed).
  2. Classify every labelled message independently (no open events), verify the
     output exactly as the production pipeline does, and score it.

Scores
  * notifiable recall / precision — did we catch every message that needs a notice?
    (the number that matters most: a miss can cost a time-barred claim)
  * per-category precision / recall / F1 (strict label)
  * lenient accuracy — prediction in {label} + acceptable alternatives
  * clause-link accuracy — for true notifiable messages flagged as notifiable, is the
    primary linked clause one of the labelled acceptable clauses
  * trigger-date accuracy where the label gives an earlier awareness date
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "demo_data"))

from notice.agents.citations import locate_quote  # noqa: E402
from notice.agents.notice_agent import offline as _na_offline  # noqa: E402,F401
from notice.agents.notice_agent.core import MessageView, RuleView, classify_variables, verify_classification  # noqa: E402
from notice.agents.notice_agent.schemas import Classification  # noqa: E402
from notice.contract import offline as _c_offline  # noqa: E402,F401
from notice.contract.clauses import split_clauses  # noqa: E402
from notice.contract.schemas import ContractExtraction  # noqa: E402
from notice.ingestion.extractors import extract  # noqa: E402
from notice.llm import ClaudeProvider, OfflineProvider, load_prompt  # noqa: E402
from riverside_messages import P, ROLES  # noqa: E402

CATS = ["change", "delay", "instruction", "disruption", "noise"]
CONTRACT_PDF = ROOT / "demo_data" / "riverside" / "contract" / "Riverside Apartments - Conditions of Contract.pdf"


def build_rules(provider) -> list[RuleView]:
    doc = extract(CONTRACT_PDF.name, CONTRACT_PDF.read_bytes(), "contract")
    spans = split_clauses(doc.text)
    prompt = load_prompt("contract_extraction", "extract_rules")
    res = provider.structured(
        task="contract_extraction.extract_rules", prompt=prompt, schema=ContractExtraction,
        variables={"contract_form": "PWC-style", "clauses": "\n\n".join(f"[{c.ref}] {c.text}" for c in spans),
                   "_clauses": [{"ref": c.ref, "title": c.title, "text": c.text} for c in spans]},
    )
    rules = []
    for i, r in enumerate(res.output.rules):
        if r.rule_type in ("notice", "time_bar", "eot", "variation") and locate_quote(doc.text, r.source_quote):
            rules.append(RuleView(id=f"r{i + 1}", clause_ref=r.clause_ref, title=r.title, rule_type=r.rule_type,
                                  event_categories=list(r.event_categories), period_value=r.period_value,
                                  period_unit=r.period_unit, summary=r.summary, condition_precedent=r.condition_precedent))
    return rules


def role_for(author: str) -> str:
    for key, (name, email) in P.items():
        if name in author or email in author:
            return ROLES[key][0]
    return "unknown"


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["offline", "claude"], default="offline")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    provider = ClaudeProvider() if args.provider == "claude" else OfflineProvider()

    rows = [json.loads(line) for line in (HERE / "dataset.jsonl").read_text().splitlines() if line.strip()]
    if args.limit:
        rows = rows[: args.limit]

    t0 = time.time()
    rules = build_rules(provider)
    prompt = load_prompt("notice_agent", "classify")
    project = "Riverside Apartments, Co. Cork. Contract form: PWC-style. We are the main contractor."
    parties = "\n".join(f"- {n} ({ROLES[k][1]}) <{e}>: {ROLES[k][0]}" for k, (n, e) in P.items())

    results = []
    for row in rows:
        msg = MessageView(text=row["text"], channel={"wa_site": "whatsapp", "wa_design": "whatsapp"}.get(row["channel"], row["channel"]),
                          timestamp=datetime.fromisoformat(row["timestamp"]), author=row["author"],
                          author_role=role_for(row["author"]), subject=row["subject"])
        try:
            out = provider.structured(task="notice_agent.classify", prompt=prompt, schema=Classification, max_tokens=4000,
                                      variables=classify_variables(project, parties, rules, [], msg)).output
            v = verify_classification(out, msg, rules)
            pred, clause, trig, conf, err = v.category, (v.primary_rule.clause_ref if v.primary_rule else None), v.trigger_date, v.confidence, None
            linked = [r.clause_ref for r in v.rules]
        except Exception as e:  # noqa: BLE001 - record and continue
            pred, clause, trig, conf, err, linked = "error", None, None, 0.0, str(e), []
        results.append({**row, "pred": pred, "pred_clause": clause, "pred_linked": linked,
                        "pred_trigger": trig.isoformat() if trig else None, "confidence": conf, "error": err})

    # --- scoring --------------------------------------------------------
    n = len(results)
    notif_tp = sum(1 for r in results if r["label"] != "noise" and r["pred"] not in ("noise", "error"))
    notif_fp = sum(1 for r in results if r["label"] == "noise" and r["pred"] not in ("noise", "error"))
    notif_fn = sum(1 for r in results if r["label"] != "noise" and r["pred"] in ("noise", "error"))
    np_, nr, nf = prf(notif_tp, notif_fp, notif_fn)
    strict = sum(r["pred"] == r["label"] for r in results) / n
    lenient = sum(r["pred"] == r["label"] or r["pred"] in r["alt"] for r in results) / n

    per_cat = {}
    for c in CATS:
        tp = sum(1 for r in results if r["pred"] == c and r["label"] == c)
        fp = sum(1 for r in results if r["pred"] == c and r["label"] != c)
        fn = sum(1 for r in results if r["pred"] != c and r["label"] == c)
        per_cat[c] = dict(zip(("precision", "recall", "f1"), prf(tp, fp, fn))) | {"support": tp + fn}

    link_cases = [r for r in results if r["label"] != "noise" and r["clauses"] and r["pred"] not in ("noise", "error")]
    link_primary = sum(1 for r in link_cases if r["pred_clause"] in r["clauses"]) / len(link_cases) if link_cases else 0.0
    link_any = sum(1 for r in link_cases if set(r["pred_linked"]) & set(r["clauses"])) / len(link_cases) if link_cases else 0.0
    trig_cases = [r for r in results if r["trigger"] and r["pred"] not in ("noise", "error")]
    trig_acc = sum(1 for r in trig_cases if r["pred_trigger"] == r["trigger"]) / len(trig_cases) if trig_cases else 0.0
    trig_safe = sum(1 for r in trig_cases if r["pred_trigger"] and r["pred_trigger"] <= r["trigger"]) / len(trig_cases) if trig_cases else 0.0
    confusion = defaultdict(Counter)
    for r in results:
        confusion[r["label"]][r["pred"]] += 1

    # --- report ---------------------------------------------------------
    line = "-" * 78
    print(line)
    print(f"NOTICE AGENT EVAL  provider={provider.name} model={provider.model}  messages={n}  rules approved={len(rules)}  "
          f"time={time.time() - t0:.1f}s")
    print(line)
    print(f"Notifiable vs noise   precision {np_:.2f}   recall {nr:.2f}   F1 {nf:.2f}   (tp={notif_tp} fp={notif_fp} fn={notif_fn})")
    print(f"Category accuracy     strict {strict:.2f}   lenient {lenient:.2f}")
    print(f"Clause linking        primary clause correct {link_primary:.2f}   any linked clause correct {link_any:.2f}   (n={len(link_cases)})")
    print(f"Trigger date          exact {trig_acc:.2f}   safe (on/before true date) {trig_safe:.2f}   (n={len(trig_cases)})")
    print(line)
    print(f"{'category':<12}{'precision':>10}{'recall':>10}{'f1':>8}{'support':>9}")
    for c, m in per_cat.items():
        print(f"{c:<12}{m['precision']:>10.2f}{m['recall']:>10.2f}{m['f1']:>8.2f}{m['support']:>9}")
    print(line)
    print("Confusion (rows = label, cols = predicted)")
    cols = CATS + (["error"] if any(r["pred"] == "error" for r in results) else [])
    print(f"{'':<12}" + "".join(f"{c[:8]:>10}" for c in cols))
    for c in CATS:
        print(f"{c:<12}" + "".join(f"{confusion[c][p]:>10}" for p in cols))
    print(line)
    misses = [r for r in results if r["label"] != "noise" and r["pred"] in ("noise", "error")]
    print(f"MISSED notifiable messages ({len(misses)}):")
    for r in misses:
        print(f"  {r['key']:<4} [{r['label']}] {r['text'][:90].replace(chr(10), ' ')}")
    wrong_clause = [r for r in link_cases if r["pred_clause"] not in r["clauses"]]
    print(f"Wrong primary clause ({len(wrong_clause)}):")
    for r in wrong_clause:
        print(f"  {r['key']:<4} expected {r['clauses']} got {r['pred_clause']}")
    print(line)

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}-{provider.name}.json"
    path.write_text(json.dumps({
        "provider": provider.name, "model": provider.model, "n": n,
        "notifiable": {"precision": np_, "recall": nr, "f1": nf},
        "accuracy": {"strict": strict, "lenient": lenient}, "per_category": per_cat,
        "clause_linking": {"primary": link_primary, "any": link_any, "n": len(link_cases)},
        "trigger_date": {"exact": trig_acc, "safe": trig_safe, "n": len(trig_cases)},
        "results": results,
    }, indent=2, default=str))
    print(f"Saved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
