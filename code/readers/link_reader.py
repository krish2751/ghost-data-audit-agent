"""Link reader: facts about which unlinked candidate records belong to the subject. Code applies acceptance checks."""
import json
import re
from datetime import datetime

import llm_client
from data.evidence_index import prefix_of
from readers.loop import fence, run_reader
from schema import PREFIX_INFO
from tools.registry import TOOL_SCHEMAS, CaseTools

MODEL = "claude-sonnet-5-5"
TOOLS = [t for t in TOOL_SCHEMAS if t["name"] in ("list_activity", "get_resource", "search_evidence", "identity_links")]
POOL_WINDOW_MIN = 180            # generic window either side of the workflow's reported_at
MAX_POOL = 40
NOISE = {"INDEX_RECORD", "UPDATE_RECORD", "SEND_EMAIL", "REFRESH_CACHE", "CREATE_EXPORT", "LINK_RESOURCE_IDENTITY", "CLASSIFY_REQUEST"}
P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def _mins(a, b):
    return round((P(a) - P(b)).total_seconds() / 60)


def build_pool(ctx, uid, linked_ids, req):
    """Unlinked, unclaimed resources with activity inside the window around reported_at (generic, all prefixes)."""
    audit_at, rep = req["audit_at"], req["reported_at"]
    claims = ctx.claims()
    pool = {}
    for a in ctx.act:
        rid = a["resource_id"]
        if a["event_type"] in NOISE or a["event_time"] > audit_at or prefix_of(rid) not in PREFIX_INFO:
            continue
        if rid in linked_ids or (claims.get(rid, set()) - {uid}):
            continue
        if abs(_mins(a["event_time"], rep)) <= POOL_WINDOW_MIN:
            pool.setdefault(rid, []).append(a)
    return pool


def _describe(ctx, rid, events, rep, audit_at):
    ev = [{"type": a["event_type"], "result": a["reported_result"], "min_from_report": _mins(a["event_time"], rep),
           "activity_id": a["activity_id"]} for a in sorted(events, key=lambda a: a["event_time"])]
    obs = [{"file_id": o.file_id, "source": o.source, "min_from_report": _mins(o.snap_time, rep) if re.match(r"\d{4}-", o.snap_time or "") else None}
           for o in ctx.ix.by_resource.get(rid, []) if o.captured_at <= audit_at][:3]
    return {"resource_id": rid, "events": ev, "evidence": obs}


def read_links(ctx, req, uid, linked, decisions=None):
    """Returns ({resource_id: result}, run_info, pool_ids)."""
    audit_at, rep = req["audit_at"], req["reported_at"]
    linked_ids = set(linked)
    pool = build_pool(ctx, uid, linked_ids, req)
    if not pool:
        return {}, {"rounds": 0, "calls": [], "tool_calls": 0, "error": None}, []
    ranked = sorted(pool, key=lambda r: min(abs(_mins(a["event_time"], rep)) for a in pool[r]))[:MAX_POOL]
    known = []
    for rid in sorted(linked_ids):
        evs = [a for a in ctx.act_by_res.get(rid, []) if a["event_type"] not in NOISE and a["event_time"] <= audit_at]
        known.append(_describe(ctx, rid, evs, rep, audit_at))
    cands = [_describe(ctx, rid, pool[rid], rep, audit_at) for rid in sorted(ranked)]
    brief = {"subject_user_id": uid, "requested_at": req["requested_at"], "reported_at": rep, "audit_at": audit_at,
             "reported_status": req["reported_status"], "already_linked_records": known, "candidates": cands}
    system = llm_client.load_prompt("link_reader.md")
    user = "Report for each candidate whether it belongs to the subject.\n\n" + fence("untrusted_record", json.dumps(brief, ensure_ascii=False, indent=1))
    r = run_reader(MODEL, system, user, None, tools=TOOLS, case_tools=CaseTools(ctx, audit_at, uid), effort="low", max_tokens=2500, tag="links")
    out = {}
    if r["facts"]:
        for x in r["facts"].get("links", []):
            if x.get("resource_id") in pool:   # the model cannot introduce resources outside the pool
                out[x["resource_id"]] = x
    return out, r, ranked
