"""Turn per-resource decisions into the ordered findings / remediation / verification steps."""
from schema import PREFIX_INFO, TREATMENT
from validator import sort_steps

FINDING_OP = {"REMAINING": "REPORT_REMAINING_RECORD", "EXPOSED": "REPORT_EXPOSED_PII",
              "FLOW": "REPORT_ACTIVE_DATA_FLOW", "RESTORE": "REPORT_RESTORE_RISK"}
FINDING_STATE = {"REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
                 "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE"}
REMEDIATION_OP = {"DELETE": ("DELETE_RECORD", "ABSENT"), "REDACT": ("REDACT_RECORD", "REDACTED"),
                  "ANONYMIZE": ("ANONYMIZE_RECORD", "ANONYMIZED"), "DISABLE": ("DISABLE_DATA_FLOW", "DISABLED"),
                  "BLOCK_RESTORE": ("BLOCK_RESTORE", "BLOCKED")}
VERIFY_OP = {"DELETE": ("VERIFY_RECORD_ABSENT", "ABSENT"), "REDACT": ("VERIFY_RECORD_REDACTED", "REDACTED"),
             "ANONYMIZE": ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"), "RETAIN": ("VERIFY_RECORD_PRESENT", "PRESENT"),
             "DISABLE": ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"), "BLOCK_RESTORE": ("VERIFY_RESTORE_BLOCKED", "BLOCKED")}


def system_of(resource_id):
    from data.evidence_index import prefix_of
    return PREFIX_INFO[prefix_of(resource_id)][0]


def _step(phase, r, op, state, ev):
    return {"step_no": 0, "phase": phase, "system_id": r["system_id"], "resource_id": r["resource_id"],
            "operation": op, "state": state, "evidence_id": ev or ""}


def plan(status, resources):
    """resources: dicts with resource_id, system_id, category, violation (or None), finding_evidence, verify_evidence."""
    if status == "NOT_APPLICABLE":
        return []
    steps = []
    for r in resources:
        treat = TREATMENT[r["category"]]
        vop, vstate = VERIFY_OP[treat]
        if status == "COMPLETE":
            steps.append(_step("VERIFICATION", r, vop, vstate, r.get("verify_evidence")))
            continue
        if r.get("violation"):
            fop = FINDING_OP[r["violation"]]
            steps.append(_step("FINDING", r, fop, FINDING_STATE[fop], r.get("finding_evidence")))
            rop, rstate = REMEDIATION_OP[treat]
            steps.append(_step("REMEDIATION", r, rop, rstate, ""))
        steps.append(_step("VERIFICATION", r, vop, vstate, ""))
    return sort_steps(steps)
