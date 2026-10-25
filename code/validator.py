"""Validate and canonically order case results, and check a whole output.csv against the submission contract.

Usage: .venv/bin/python code/validator.py [PATH] [--sample]
    PATH defaults to output.csv (checked against dataset/deletion_requests.csv); --sample checks
    code/runs/sample_pred.csv against dataset/sample_deletion_requests.csv. Exit code 1 when there are errors.
Errors break the contract; warnings are reported but allowed (COMPLETE with no steps: an authorized request with no
observed violation and no evidence-backed check, per the official clarification).
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import OP_INDEX, OP_META, PHASES, STATUSES, STEP_FIELDS  # noqa: E402

HEADER = ["case_id", "deletion_status", "steps_json"]


def sort_steps(steps):
    """Phase -> operation order -> system_id -> resource_id; renumber from 1."""
    ordered = sorted(steps, key=lambda s: (PHASES.index(s["phase"]), OP_INDEX[s["operation"]], s["system_id"], s["resource_id"]))
    return [dict(s, step_no=i) for i, s in enumerate(ordered, 1)]


def validate(status, steps, manifest=None, audit_at=None, activity_times=None, audit_times=None):
    """Return a list of errors (empty when valid). Citation checks run only when context is supplied."""
    probs = []
    if status not in STATUSES:
        probs.append(f"invalid status {status!r}")
    if status == "NOT_APPLICABLE" and steps:
        probs.append("NOT_APPLICABLE must have no steps")
    well_formed = True
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or set(s) != set(STEP_FIELDS):
            probs.append(f"step {i}: wrong fields")
            well_formed = False
            continue
        if s["step_no"] != i or not isinstance(s["step_no"], int):
            probs.append(f"step {i}: step_no {s['step_no']!r}")
        if s["phase"] not in PHASES:
            probs.append(f"step {i}: unknown phase {s['phase']!r}")
            well_formed = False
        if s["operation"] not in OP_META:
            probs.append(f"step {i}: unknown operation {s['operation']!r}")
            well_formed = False
            continue
        phase, state = OP_META[s["operation"]]
        if s["phase"] != phase or s["state"] != state:
            probs.append(f"step {i}: phase/state do not match {s['operation']}")
        if status == "COMPLETE" and s["phase"] != "VERIFICATION":
            probs.append(f"step {i}: COMPLETE may only contain VERIFICATION steps")
        ev = s["evidence_id"]
        if not isinstance(ev, str):
            probs.append(f"step {i}: evidence_id must be a string")
            continue
        needs_ev = s["phase"] == "FINDING" or (s["phase"] == "VERIFICATION" and status == "COMPLETE")
        if needs_ev and not ev:
            probs.append(f"step {i}: missing evidence_id")
        if not needs_ev and ev:
            probs.append(f"step {i}: evidence_id must be empty ({s['phase']} step of an {status} case)")
        if ev and audit_at:
            if manifest and ev in manifest:
                if manifest[ev]["captured_at"] > audit_at:
                    probs.append(f"step {i}: {ev} captured after audit_at")
            elif ev.startswith("activity_") and activity_times is not None:
                if activity_times.get(ev, "9") > audit_at:
                    probs.append(f"step {i}: {ev} after audit_at or unknown")
            elif ev.startswith("audit_") and audit_times is not None:
                if audit_times.get(ev, "9") > audit_at:
                    probs.append(f"step {i}: {ev} after audit_at or unknown")
            elif manifest is not None:
                probs.append(f"step {i}: unknown evidence id {ev}")
    if [s.get("step_no") if isinstance(s, dict) else None for s in steps] != list(range(1, len(steps) + 1)):
        probs.append("step numbers are not consecutive from 1")
    if well_formed and steps != sort_steps([dict(s) for s in steps]):
        probs.append("steps are not in phase order and within-phase operation / system_id / resource_id order")
    return probs


def row_warnings(status, steps):
    """Allowed but worth reporting."""
    return ["COMPLETE with no steps (allowed: no observed violation and no evidence-backed check)"] if status == "COMPLETE" and not steps else []


def validate_file(path, requests_path, manifest, activity_times, audit_times):
    """(errors, warnings) for a whole prediction file: header, one row per request in the request file's order,
    valid JSON arrays, and every row checked by `validate` against its own case's audit_at."""
    errors, warnings = [], []
    with open(requests_path, newline="", encoding="utf-8") as f:
        reqs = list(csv.DictReader(f))
    audit = {r["case_id"]: r["audit_at"] for r in reqs}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = list(reader)
    if header != HEADER:
        errors.append(f"header is {header}, expected {HEADER}")
    ids = [r[0] if r else "" for r in rows]
    want = [r["case_id"] for r in reqs]
    dup = sorted({c for c in ids if ids.count(c) > 1})
    if dup:
        errors.append(f"duplicate case_id: {dup}")
    missing, extra = [c for c in want if c not in set(ids)], [c for c in ids if c not in audit]
    if missing:
        errors.append(f"{len(missing)} request(s) missing: {missing[:10]}")
    if extra:
        errors.append(f"{len(extra)} row(s) not in the request file: {extra[:10]}")
    if not dup and not missing and not extra and ids != want:
        i = next(k for k, (a, b) in enumerate(zip(ids, want)) if a != b)
        errors.append(f"row order differs from the request file at row {i + 1}: {ids[i]} vs {want[i]}")
    for n, r in enumerate(rows, 2):
        if len(r) != 3:
            errors.append(f"line {n}: {len(r)} columns")
            continue
        cid, status, raw = r
        try:
            steps = json.loads(raw)
        except ValueError as e:
            errors.append(f"{cid}: steps_json is not valid JSON ({e})")
            continue
        if not isinstance(steps, list):
            errors.append(f"{cid}: steps_json is not a JSON array")
            continue
        errors += [f"{cid}: {p}" for p in validate(status, steps, manifest, audit.get(cid), activity_times, audit_times)]
        warnings += [f"{cid}: {w}" for w in row_warnings(status, steps)]
    return errors, warnings


def dumps(steps):
    return json.dumps(steps, separators=(",", ":"), sort_keys=True)


def main():
    from data import loader
    sample = "--sample" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else (loader.ROOT / "code" / "runs" / "sample_pred.csv" if sample else loader.ROOT / "output.csv")
    req = loader.DS / ("sample_deletion_requests.csv" if sample else "deletion_requests.csv")
    act = {a["activity_id"]: a["event_time"] for a in loader.activity()}
    aud = {a["audit_id"]: a["event_time"] for a in loader.read_csv("user_audit_log.csv")}
    errors, warnings = validate_file(path, req, loader.manifest(), act, aud)
    print(f"{path}: checked against {req.name}: {len(errors)} error(s), {len(warnings)} warning(s)")
    for e in errors:
        print("  ERROR", e)
    for w in warnings:
        print("  WARN ", w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
