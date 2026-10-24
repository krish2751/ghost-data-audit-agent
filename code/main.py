"""Ghost Data Still Exists - deletion audit.

Usage (from the repo root):
    .venv/bin/python code/main.py                 # all requests -> output.csv
    .venv/bin/python code/main.py --sample        # 32 sample requests -> code/runs/sample_pred.csv
Options: --out PATH, --cases ID1,ID2, --no-heuristics
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import loader  # noqa: E402
from fallback import Context, solve_all  # noqa: E402
from readers.intent_reader import prefetch_intents  # noqa: E402
from validator import dumps, validate  # noqa: E402

ROOT = loader.ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="run the 32 public sample requests")
    ap.add_argument("--out")
    ap.add_argument("--cases")
    ap.add_argument("--no-heuristics", action="store_true")
    ap.add_argument("--links", choices=["model", "off"], default="off", help="model link reader for unlinked records")
    ap.add_argument("--min-link-conf", choices=["low", "medium", "high"], default="high", help="lowest link-reader confidence accepted")
    ap.add_argument("--conditions", choices=["model", "default"], default="model", help="rule-condition source")
    ap.add_argument("--intent", choices=["model", "regex"], default="model", help="intent source (model reads are cached)")
    args = ap.parse_args()

    reqs = loader.requests(sample=args.sample)
    if args.cases:
        want = set(args.cases.split(","))
        reqs = [r for r in reqs if r["case_id"] in want]
    out_path = Path(args.out) if args.out else (ROOT / "code" / "runs" / "sample_pred.csv" if args.sample else ROOT / "output.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ctx = Context(intent_mode=args.intent, conditions_mode=args.conditions, link_mode=args.links, min_link_conf=args.min_link_conf)
    if args.intent == "model":
        prefetch_intents(ctx, reqs)
    act_times = {a["activity_id"]: a["event_time"] for a in ctx.act}
    audit_times = {a["audit_id"]: a["event_time"] for rows in ctx.ids.audit.values() for a in rows}
    rows, bad = [], 0
    solved = solve_all(ctx, reqs, heuristics=not args.no_heuristics)
    for req in sorted(reqs, key=lambda r: r["case_id"]):
        res, steps = solved[req["case_id"]]
        probs = validate(res["status"], steps, ctx.man, req["audit_at"], act_times, audit_times)
        if probs:
            bad += 1
            print(f"[validator] {req['case_id']}: {probs[:3]}", file=sys.stderr)
        rows.append({"case_id": req["case_id"], "deletion_status": res["status"], "steps_json": dumps(steps)})
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out_path} ({bad} with validator problems)")


if __name__ == "__main__":
    main()
