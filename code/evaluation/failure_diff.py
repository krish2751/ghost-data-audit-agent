"""Side-by-side predicted vs expected steps for every sample that is not an exact match, with a label per difference.

Usage: .venv/bin/python code/evaluation/failure_diff.py code/runs/sample_pred.csv
Labels: wrong order (same steps, different order), missing step, extra step, wrong field value (same resource and
operation, another field differs). Whether a missing step is recoverable is decided separately (see data_findings.md)."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(p):
    with open(p, newline="", encoding="utf-8") as f:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(f)}


def short(s):
    return f"{s['step_no']:>2} {s['phase'][:5]:5} {s['operation']:26} {s['resource_id']:18} {s['evidence_id'] or '-'}" if s else ""


def main(pred_path):
    gold, pred = load(ROOT / "dataset" / "sample_output.csv"), load(pred_path)
    for cid in sorted(gold, key=lambda c: int(c.split("_")[1])):
        g, p = gold[cid], pred.get(cid, (None, []))
        if g == p:
            continue
        key = lambda s: (s["resource_id"], s["operation"])
        gk, pk = {key(s): s for s in g[1]}, {key(s): s for s in p[1]}
        strip = lambda s: {k: v for k, v in s.items() if k != "step_no"}
        labels = []
        if p[0] != g[0]:
            labels.append(f"status {p[0]} vs {g[0]}")
        labels += [f"missing step {k[1]} {k[0]}" for k in gk if k not in pk]
        labels += [f"extra step {k[1]} {k[0]}" for k in pk if k not in gk]
        labels += [f"wrong field value {k[1]} {k[0]}" for k in gk if k in pk and strip(gk[k]) != strip(pk[k])]
        if not labels and [strip(s) for s in g[1]] != [strip(s) for s in p[1]]:
            labels.append("wrong order")
        print(f"=== {cid}  predicted {p[0]} / expected {g[0]}")
        print(f"   {'predicted':70} | expected")
        n = max(len(g[1]), len(p[1]))
        for i in range(n):
            a = short(p[1][i]) if i < len(p[1]) else ""
            b = short(g[1][i]) if i < len(g[1]) else ""
            print(f"   {a:70} | {b}{'' if a == b else '   <'}")
        for lab in labels:
            print("   ->", lab)


if __name__ == "__main__":
    main(sys.argv[1])
