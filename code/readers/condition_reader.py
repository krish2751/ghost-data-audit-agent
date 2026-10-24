"""Rule-condition reader: structured facts about conditions in deletion_rules.csv that need reading text.

Facts only (yes/no/unclear, retain_until date, reason). fallback.py turns them into treatments.
"""
import json
import re

import llm_client
from data import loader
from readers.loop import fence, run_reader
from tools.registry import TOOL_SCHEMAS, CaseTools

MODEL = "claude-sonnet-5-5"
READER_TOOLS = [t for t in TOOL_SCHEMAS if t["name"] in ("read_evidence", "get_resource", "search_evidence")]
RULE_OF = {"SUPPORT_MESSAGE": "rule_05", "SUPPORT_ATTACHMENT": "rule_06", "SECURITY_AUDIT_LOG": "rule_12", "LEGAL_HOLD_RECORD": "rule_13"}
KIND_OF = {"SUPPORT_MESSAGE": "support_shared_context", "SUPPORT_ATTACHMENT": "attachment_ownership",
           "SECURITY_AUDIT_LOG": "retention_window", "LEGAL_HOLD_RECORD": "retention_window"}


def _latest(obs, *keys):
    for o in sorted(obs, key=lambda o: (o.captured_at, o.snap_time), reverse=True):
        for k in keys:
            v = o.attrs.get(k)
            if v and str(v).strip() and "[redacted]" not in str(v).lower():
                return str(v)
    return None


def structured_retention(obs):
    ds = [str(o.attrs.get(k)) for o in obs for k in ("retention_until", "retained_until") if o.attrs.get(k)]
    return max(ds) if ds else None


def build_item(ctx, d, uid, audit_at):
    """Return an item dict for a candidate record needing a text-based condition, else None."""
    cat, rid = d["category"], d["resource_id"]
    if cat not in KIND_OF:
        return None
    obs = [o for o in ctx.ix.by_resource.get(rid, []) if o.captured_at <= audit_at]
    rule = next(r for r in loader.rules() if r["rule_id"] == RULE_OF[cat])
    item = {"item_id": rid, "type": KIND_OF[cat], "rule_condition": rule["condition"], "rule_action": rule["required_action"],
            "audit_time": audit_at, "fields": {}, "documents": []}
    if cat == "SUPPORT_MESSAGE":
        text = _latest(obs, "message_text", "message_excerpt")
        if not text:
            return None
        item["fields"] = {"message": text, "ticket_id": _latest(obs, "ticket_id"), "channel": _latest(obs, "channel")}
    elif cat == "SUPPORT_ATTACHMENT":
        item["fields"] = {k: _latest(obs, k) for k in ("file_name", "uploaded_by", "ticket_id", "storage_class")}
        item["fields"]["deletion_subject_user_id"] = uid
        item["documents"] = [{"evidence_id": o.file_id, "text": o.attrs.get("text", "")[:3000]} for o in obs if o.kind == "pdf"][:1]
    else:  # retention: only ask when a document mentions this record or its subject; otherwise structured dates suffice
        docs = []
        for fid, m in ctx.man.items():
            if m["file_path"].endswith(".pdf") and m["captured_at"] <= audit_at:
                text = ctx.pdf_text(fid)
                if re.search(r"(?<![\w])" + re.escape(rid) + r"(?!\w)", text) or (uid and re.search(r"(?<![\w])" + re.escape(uid) + r"(?!\d)", text)):
                    docs.append({"evidence_id": fid, "text": text[:3000]})
        if not docs:
            return None
        item["fields"] = {"structured_retention_until": structured_retention(obs), "record_id": rid, "subject_user_id": uid}
        item["documents"] = docs[:2]
    return item


def read_conditions(ctx, items, uid, audit_at):
    """One reader run for all items of a case. Returns {item_id: result} plus run info."""
    if not items:
        return {}, {"rounds": 0, "calls": [], "tool_calls": 0, "error": None}
    system = llm_client.load_prompt("condition_reader.md")
    blocks = []
    for it in items:
        body = {k: v for k, v in it.items() if k not in ("fields", "documents")}
        text = json.dumps(body, ensure_ascii=False) + "\n" + fence("untrusted_record", json.dumps({"fields": it["fields"], "documents": it["documents"]}, ensure_ascii=False, indent=1))
        blocks.append(text)
    user = "Answer these items.\n\n" + "\n\n".join(blocks)
    r = run_reader(MODEL, system, user, None, tools=READER_TOOLS, case_tools=CaseTools(ctx, audit_at, uid), effort="low", max_tokens=1500, tag="conditions")
    out = {}
    if r["facts"]:
        for res in r["facts"].get("results", []):
            out[res.get("item_id")] = res
    return out, r
