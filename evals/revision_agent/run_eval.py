"""Revision agent eval: change detection (deterministic diff) and potential-variation flagging.

    cd backend && python ../evals/revision_agent/run_eval.py [--provider offline|claude]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from notice.agents.revision_agent import offline as _offline  # noqa: E402,F401
from notice.agents.revision_agent.agent import _changes_block  # noqa: E402
from notice.agents.revision_agent.diff import diff_documents  # noqa: E402
from notice.agents.revision_agent.schemas import RevisionAssessment  # noqa: E402
from notice.ingestion.extractors import extract  # noqa: E402
from notice.llm import ClaudeProvider, OfflineProvider, load_prompt  # noqa: E402

DEMO = ROOT / "demo_data" / "riverside"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["offline", "claude"], default="offline")
    args = ap.parse_args()
    provider = ClaudeProvider() if args.provider == "claude" else OfflineProvider()
    labels = json.loads((HERE / "labels.json").read_text())["pairs"]
    prompt = load_prompt("revision_agent", "assess_changes")

    found = expected = 0
    tp = fp = fn = tn = 0
    flags_ok = 0
    print("-" * 78)
    for pair in labels:
        a, b = DEMO / pair["base"], DEMO / pair["revised"]
        ta, tb = extract(a.name, a.read_bytes()).text, extract(b.name, b.read_bytes()).text
        method, changes = diff_documents(ta, tb)
        cd = [c.to_dict() | {"cross_refs": {"events": [], "documents": []}} for c in changes]
        out = provider.structured(task="revision_agent.assess_changes", prompt=prompt, schema=RevisionAssessment,
                                  variables={"project": "Riverside Apartments, Co. Cork", "base_filename": a.name,
                                             "revised_filename": b.name, "method": method, "changes": _changes_block(cd),
                                             "_changes": cd}).output
        by_id = {x.change_id: x for x in out.assessments}
        keyed = {(c["key"] or "<revision note>"): by_id.get(c["id"]) for c in cd}
        expected += len(pair["changes"])
        found += sum(1 for k in pair["changes"] if k in keyed)
        print(f"{b.name}: {len(cd)} changes found ({method})")
        for k, truth in pair["changes"].items():
            a_ = keyed.get(k)
            pred = bool(a_ and a_.potential_variation)
            tp += truth and pred
            fp += (not truth) and pred
            fn += truth and not pred
            tn += (not truth) and not pred
            mark = "ok " if pred == truth else "XX "
            print(f"  {mark}{k:<20} truth={truth!s:<5} pred={pred!s:<5} {(a_.change_type + ' / ' + a_.cost_impact) if a_ else 'NOT FOUND'}")
        flagged = bool(out.downplaying_flags)
        flags_ok += flagged == pair["downplaying"]
        print(f"  downplaying flag: expected {pair['downplaying']}, got {flagged}")
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    print("-" * 78)
    print(f"REVISION AGENT EVAL provider={provider.name}")
    print(f"Change detection recall (diff, code)        {found}/{expected} = {found / expected:.2f}")
    print(f"Potential variation precision / recall      {p:.2f} / {r:.2f}   (tp={tp} fp={fp} fn={fn} tn={tn})")
    print(f"Downplaying flags correct                   {flags_ok}/{len(labels)}")
    print("-" * 78)


if __name__ == "__main__":
    main()
