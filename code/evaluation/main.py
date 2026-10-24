"""Score a predictions CSV against the public sample answers.

Usage (from the repo root):
    .venv/bin/python code/evaluation/main.py [predictions.csv] [--gold PATH] [--max-diffs N]

Defaults: predictions = <repo root>/output.csv, gold = dataset/sample_output.csv.
Only cases present in the gold file are scored; format checks run on every
predicted row. Standard library only.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ["case_id", "deletion_status", "steps_json"]
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
STEP_FIELDS = ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
KEY_FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
# Operation order from problem_statement.md, with the state each one implies.
OPERATIONS = [
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
]
OP_INDEX = {op: i for i, (_, op, _) in enumerate(OPERATIONS)}
OP_META = {op: (phase, state) for phase, op, state in OPERATIONS}


def load_csv(path):
    """Return (header, {case_id: row}, duplicate_ids)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        rows, dups = {}, []
        for r in reader:
            if not r:
                continue
            row = dict(zip(header, r))
            cid = row.get("case_id", "")
            if cid in rows:
                dups.append(cid)
            rows[cid] = row
    return header, rows, dups


def parse_steps(raw):
    """Return (steps, error). steps is None when the JSON is unusable."""
    try:
        steps = json.loads(raw)
    except (TypeError, ValueError) as e:
        return None, f"invalid JSON ({e})"
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        return None, "steps_json is not a JSON array of objects"
    return steps, None


def key(step):
    return tuple(step.get(f) for f in KEY_FIELDS)


def fmt(step):
    return "{phase} {system_id}/{resource_id} {operation}->{state} ev={evidence_id!r}".format(
        **{f: step.get(f) for f in KEY_FIELDS})


def check_format(case_id, status, steps, err):
    """Return a list of human-readable format problems for one predicted row."""
    probs = []
    if status not in STATUSES:
        probs.append(f"invalid deletion_status {status!r}")
    if steps is None:
        probs.append(err)
        return probs
    if status == "NOT_APPLICABLE" and steps:
        probs.append("NOT_APPLICABLE must have steps_json []")
    last_phase, last_op = -1, -1
    for i, s in enumerate(steps, 1):
        if set(s) != set(STEP_FIELDS):
            probs.append(f"step {i}: fields {sorted(s)} != required fields")
            continue
        if s["step_no"] != i:
            probs.append(f"step {i}: step_no is {s['step_no']!r}, expected {i}")
        if s["phase"] not in PHASES:
            probs.append(f"step {i}: invalid phase {s['phase']!r}")
        if s["operation"] not in OP_META:
            probs.append(f"step {i}: invalid operation {s['operation']!r}")
        else:
            phase, state = OP_META[s["operation"]]
            if s["phase"] != phase:
                probs.append(f"step {i}: operation {s['operation']} belongs to {phase}, got {s['phase']}")
            if s["state"] != state:
                probs.append(f"step {i}: operation {s['operation']} needs state {state}, got {s['state']!r}")
        if s["phase"] in PHASES and s["operation"] in OP_INDEX:
            p, o = PHASES.index(s["phase"]), OP_INDEX[s["operation"]]
            if (p, o) < (last_phase, last_op):
                probs.append(f"step {i}: phase/operation order violated")
            last_phase, last_op = p, o
    # Within a phase+operation, rows must be sorted by (system_id, resource_id).
    for a, b in zip(steps, steps[1:]):
        if (a.get("phase"), a.get("operation")) == (b.get("phase"), b.get("operation")):
            if (str(a.get("system_id")), str(a.get("resource_id"))) > (str(b.get("system_id")), str(b.get("resource_id"))):
                probs.append(f"steps {a.get('step_no')}-{b.get('step_no')}: system_id/resource_id not ascending")
                break
    return probs


def align(gold, pred):
    """Pair each gold step with a distinct predicted step.

    Exact (6-field) matches pair first; remaining gold steps then take the unused
    predicted step sharing the most fields (at least system_id+resource_id or 3 fields).
    Returns a list of (gold_step, pred_step_or_None).
    """
    used = set()
    pairs = {}
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            if pi not in used and key(g) == key(p):
                used.add(pi)
                pairs[gi] = pi
                break
    for gi, g in enumerate(gold):
        if gi in pairs:
            continue
        best, best_score = None, 0
        for pi, p in enumerate(pred):
            if pi in used:
                continue
            score = sum(g.get(f) == p.get(f) for f in KEY_FIELDS)
            same_res = g.get("system_id") == p.get("system_id") and g.get("resource_id") == p.get("resource_id")
            if (same_res or score >= 3) and score > best_score:
                best, best_score = pi, score
        if best is not None:
            used.add(best)
            pairs[gi] = best
    return [(g, pred[pairs[gi]] if gi in pairs else None) for gi, g in enumerate(gold)]


def diff_case(gold_steps, pred_steps):
    """Return (missing, extra, order_only) lists of formatted steps."""
    gc, pc = Counter(map(key, gold_steps)), Counter(map(key, pred_steps))
    missing = [fmt(dict(zip(KEY_FIELDS, k))) for k, n in (gc - pc).items() for _ in range(n)]
    extra = [fmt(dict(zip(KEY_FIELDS, k))) for k, n in (pc - gc).items() for _ in range(n)]
    order_only = not missing and not extra and list(map(key, gold_steps)) != list(map(key, pred_steps))
    return missing, extra, order_only


def pct(n, d):
    return f"{100.0 * n / d:6.2f}%" if d else "   n/a "


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("predictions", nargs="?", default=str(ROOT / "output.csv"))
    ap.add_argument("--gold", default=str(ROOT / "dataset" / "sample_output.csv"))
    ap.add_argument("--max-diffs", type=int, default=10, help="failing cases to detail (default 10)")
    args = ap.parse_args()

    pred_path, gold_path = Path(args.predictions), Path(args.gold)
    if not pred_path.exists():
        print(f"error: predictions file not found: {pred_path}")
        return 2
    p_header, p_rows, p_dups = load_csv(pred_path)
    _, g_rows, _ = load_csv(gold_path)

    # ---- format checks (all predicted rows) --------------------------------
    format_problems = []
    if p_header != HEADER:
        format_problems.append(f"header is {p_header}, expected {HEADER}")
    for cid in p_dups:
        format_problems.append(f"{cid}: duplicate case_id")
    if list(p_rows) != sorted(p_rows):
        format_problems.append("rows are not sorted by case_id")
    parsed = {}
    for cid, row in p_rows.items():
        steps, err = parse_steps(row.get("steps_json", ""))
        parsed[cid] = steps
        for prob in check_format(cid, row.get("deletion_status"), steps, err):
            format_problems.append(f"{cid}: {prob}")

    # ---- scoring (gold cases only) -----------------------------------------
    scored = sorted(g_rows)
    absent = [c for c in scored if c not in p_rows]
    present = [c for c in scored if c in p_rows]
    status_ok = seq_ok = 0
    tp = n_pred = n_gold = 0
    field_hits = Counter()
    failing = []
    for cid in scored:
        g_steps, _ = parse_steps(g_rows[cid]["steps_json"])
        g_status = g_rows[cid]["deletion_status"]
        n_gold += len(g_steps)
        if cid not in p_rows:
            failing.append((cid, "row missing from predictions", [fmt(s) for s in g_steps], [], False))
            continue
        p_steps = parsed[cid] if parsed[cid] is not None else []
        n_pred += len(p_steps)
        s_ok = p_rows[cid].get("deletion_status") == g_status
        status_ok += s_ok
        gc, pc = Counter(map(key, g_steps)), Counter(map(key, p_steps))
        tp += sum((gc & pc).values())
        for g, p in align(g_steps, p_steps):
            if p is not None:
                for f in KEY_FIELDS:
                    field_hits[f] += g.get(f) == p.get(f)
        exact = parsed[cid] is not None and parsed[cid] == g_steps
        seq_ok += s_ok and exact
        if not (s_ok and exact):
            missing, extra, order_only = diff_case(g_steps, p_steps)
            head = "" if s_ok else f"status {p_rows[cid].get('deletion_status')!r} != gold {g_status!r}"
            failing.append((cid, head, missing, extra, order_only))

    n = len(scored)
    prec = tp / n_pred if n_pred else 0.0
    rec = tp / n_gold if n_gold else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    print(f"Predictions: {pred_path}  ({len(p_rows)} rows)")
    print(f"Gold:        {gold_path}  ({n} cases scored, {len(present)} present in predictions)")
    if not present:
        print("WARNING: no overlap between predictions and gold case_ids; all metrics are 0.")
    print("\n== Accuracy ==")
    print(f"case-level status accuracy : {pct(status_ok, n)}  ({status_ok}/{n})")
    print(f"exact sequence match       : {pct(seq_ok, n)}  ({seq_ok}/{n})  [status + full steps_json identical in order]")
    print(f"step precision             : {prec * 100:6.2f}%  ({tp}/{n_pred})")
    print(f"step recall                : {rec * 100:6.2f}%  ({tp}/{n_gold})")
    print(f"step F1                    : {f1 * 100:6.2f}%")
    print("field-level accuracy (aligned gold steps; unmatched gold steps count as wrong):")
    for f in KEY_FIELDS:
        print(f"  {f:<12}: {pct(field_hits[f], n_gold)}  ({field_hits[f]}/{n_gold})")

    print("\n== Format checks ==")
    if format_problems:
        print(f"{len(format_problems)} problem(s):")
        for prob in format_problems[:20]:
            print("  -", prob)
        if len(format_problems) > 20:
            print(f"  ... {len(format_problems) - 20} more")
    else:
        print("OK: header, ordering, JSON arrays, step_no, phases, operations, states")

    if failing:
        print(f"\n== Failing cases ({len(failing)}; showing {min(len(failing), args.max_diffs)}) ==")
        for cid, head, missing, extra, order_only in failing[: args.max_diffs]:
            print(f"{cid}: {head}".rstrip(": "))
            for m in missing:
                print("  - missing:", m)
            for e in extra:
                print("  + extra:  ", e)
            if order_only:
                print("  ! same steps, wrong order")
            if not (missing or extra or order_only or head):
                print("  ! step fields (e.g. step_no) differ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
