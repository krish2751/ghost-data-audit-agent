"""Validate and canonically order a case result before it is written to output.csv."""
import json

from schema import OP_INDEX, OP_META, PHASES, STATUSES, STEP_FIELDS


def sort_steps(steps):
    """Phase -> operation order -> system_id -> resource_id; renumber from 1."""
    ordered = sorted(steps, key=lambda s: (PHASES.index(s["phase"]), OP_INDEX[s["operation"]], s["system_id"], s["resource_id"]))
    return [dict(s, step_no=i) for i, s in enumerate(ordered, 1)]


def validate(status, steps, manifest=None, audit_at=None, activity_times=None, audit_times=None):
    """Return a list of problems (empty when valid). Citation checks run only when context is supplied."""
    probs = []
    if status not in STATUSES:
        probs.append(f"invalid status {status!r}")
    if status == "NOT_APPLICABLE" and steps:
        probs.append("NOT_APPLICABLE must have no steps")
    if status == "COMPLETE" and any(s["phase"] != "VERIFICATION" for s in steps):
        probs.append("COMPLETE may only contain VERIFICATION steps")
    if status == "COMPLETE" and not steps:
        probs.append("COMPLETE with no steps: COMPLETE requires evidence-backed verification")
    for i, s in enumerate(steps, 1):
        if set(s) != set(STEP_FIELDS):
            probs.append(f"step {i}: wrong fields")
            continue
        if s["step_no"] != i:
            probs.append(f"step {i}: step_no {s['step_no']}")
        if s["operation"] not in OP_META:
            probs.append(f"step {i}: unknown operation {s['operation']}")
            continue
        phase, state = OP_META[s["operation"]]
        if s["phase"] != phase or s["state"] != state:
            probs.append(f"step {i}: phase/state do not match {s['operation']}")
        ev = s["evidence_id"]
        needs_ev = s["phase"] == "FINDING" or (s["phase"] == "VERIFICATION" and status == "COMPLETE")
        if needs_ev and not ev:
            probs.append(f"step {i}: missing evidence_id")
        if not needs_ev and ev:
            probs.append(f"step {i}: evidence_id must be empty")
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
            elif manifest is not None and ev not in manifest:
                probs.append(f"step {i}: unknown evidence id {ev}")
    if [s["step_no"] for s in steps] != list(range(1, len(steps) + 1)):
        probs.append("step numbers are not consecutive")
    if steps != sort_steps([{k: v for k, v in s.items()} for s in steps]):
        probs.append("steps are not in canonical order")
    return probs


def dumps(steps):
    return json.dumps(steps, separators=(",", ":"), sort_keys=True)
