"""Deterministic investigation tools for the agent, bound to one case so nothing after audit_at is visible.

State-bearing tools only return files captured at or before audit_at. `identity_links` is the one exception
(identity facts may come from any capture date) and flags files that must not be cited.
"""
import json
import re
import sqlite3

from data import loader
from data.evidence_index import prefix_of
from data.identity import hash_email
from data.states import category, reading, violation
from schema import TREATMENT

MAX_ROWS = 40

TOOL_SCHEMAS = [
    {"name": "lookup_identity", "description": "Resolve an email or user_id to the subject's identifiers (all historical emails, phones, hashes) as of audit_at.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "hash_email", "description": "SHA-256 of the lower-cased email, to match email_hash / correlation_key values.",
     "input_schema": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]}},
    {"name": "search_evidence", "description": "Find observations (files captured at or before audit_at) whose content contains a token (email, user_id, hash, resource_id, phone).",
     "input_schema": {"type": "object", "properties": {"token": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["token"]}},
    {"name": "get_resource", "description": "All observations of one resource at or before audit_at, with the derived reading, plus its activity rows.",
     "input_schema": {"type": "object", "properties": {"resource_id": {"type": "string"}}, "required": ["resource_id"]}},
    {"name": "query_sql", "description": "Run a read-only SELECT on one SQL snapshot file (captured at or before audit_at).",
     "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}, "sql": {"type": "string"}}, "required": ["file_id", "sql"]}},
    {"name": "list_activity", "description": "System activity rows at or before audit_at, filtered by resource_id, event_type and/or an ISO time window.",
     "input_schema": {"type": "object", "properties": {"resource_id": {"type": "string"}, "event_type": {"type": "string"},
                                                      "start": {"type": "string"}, "end": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "get_rule", "description": "Deletion rules for a data category (or all categories when omitted).",
     "input_schema": {"type": "object", "properties": {"category": {"type": "string"}}}},
    {"name": "read_evidence", "description": "Raw text of an evidence file captured at or before audit_at (PDF text, text ledger, log), truncated.",
     "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["file_id"]}},
    {"name": "identity_links", "description": "IDENTITY ONLY, any capture date: which users' identifiers appear with a resource anywhere. Never cite results from files captured after audit_at.",
     "input_schema": {"type": "object", "properties": {"resource_id": {"type": "string"}}, "required": ["resource_id"]}},
]


def _brief(o):
    a = {k: v for k, v in o.attrs.items() if v is not None and k not in ("text", "instance", "pod", "region", "duration_ms", "trace_id", "level", "service")}
    return {"file_id": o.file_id, "captured_at": o.captured_at, "snap_time": o.snap_time, "resource_id": o.resource_id,
            "source": o.source, "category": category(o), "reading": reading(o), "attrs": {k: (str(v)[:80]) for k, v in list(a.items())[:10]}}


class CaseTools:
    def __init__(self, ctx, audit_at, uid=None):
        self.ctx, self.audit_at, self.uid = ctx, audit_at, uid

    def _visible(self, o):
        return o.captured_at <= self.audit_at

    def call(self, name, args):
        try:
            return getattr(self, name)(**args)
        except Exception as e:  # tool errors go back to the model as data
            return {"error": f"{type(e).__name__}: {e}"}

    def lookup_identity(self, query):
        ids = self.ctx.ids
        uids = [query] if query in ids.users else ids.resolve_email(query)
        return [{"user_id": u, "name": ids.users[u]["name"], "identifiers": {k: sorted(v) for k, v in ids.identifiers(u, self.audit_at).items()},
                 "audit_changes_applied": [a["audit_id"] for a in ids.audit.get(u, []) if a["event_time"] <= self.audit_at]} for u in uids]

    def hash_email(self, email):
        return {"sha256": hash_email(email)}

    def search_evidence(self, token, limit=25):
        t = token.lower()
        rx = re.compile(r"(?<![\w.+-])" + re.escape(t) + r"(?![\w])")
        hits = [o for o in self.ctx.ix.obs if self._visible(o) and rx.search(o.text)]
        hits.sort(key=lambda o: (o.captured_at, o.snap_time), reverse=True)
        return {"count": len(hits), "results": [_brief(o) for o in hits[:min(limit, MAX_ROWS)]]}

    def get_resource(self, resource_id):
        obs = sorted((o for o in self.ctx.ix.by_resource.get(resource_id, []) if self._visible(o)), key=lambda o: (o.captured_at, o.snap_time))
        act = [a for a in self.ctx.act_by_res.get(resource_id, []) if a["event_time"] <= self.audit_at]
        cat = category(obs[-1]) if obs else None
        return {"resource_id": resource_id, "observations": [_brief(o) for o in obs[-12:]],
                "activity": [{k: a[k] for k in ("activity_id", "event_time", "event_type", "reported_result")} for a in act][-12:],
                "category": cat, "treatment": TREATMENT.get(cat)}

    def query_sql(self, file_id, sql):
        m = self.ctx.man[file_id]
        if m["captured_at"] > self.audit_at or not m["file_path"].endswith(".sql"):
            return {"error": "not a visible SQL snapshot"}
        if not re.match(r"\s*select\b", sql, re.I) or ";" in sql.strip().rstrip(";"):
            return {"error": "only a single SELECT is allowed"}
        con = sqlite3.connect(":memory:")
        con.executescript((loader.DS / m["file_path"]).read_text(encoding="utf-8"))
        cur = con.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
        return {"columns": cols, "rows": [[(str(v)[:120] if v is not None else None) for v in r] for r in rows]}

    def list_activity(self, resource_id=None, event_type=None, start=None, end=None, limit=30):
        out = []
        for a in self.ctx.act:
            if a["event_time"] > self.audit_at:
                continue
            if resource_id and a["resource_id"] != resource_id:
                continue
            if event_type and a["event_type"] != event_type:
                continue
            if start and a["event_time"] < start or end and a["event_time"] > end:
                continue
            out.append({k: a[k] for k in ("activity_id", "event_time", "event_type", "resource_id", "reported_result", "details")})
        return {"count": len(out), "rows": out[:min(limit, MAX_ROWS)]}

    def get_rule(self, category=None):
        return [r for r in loader.rules() if not category or r["data_category"] == category]

    def read_evidence(self, file_id, max_chars=4000):
        m = self.ctx.man[file_id]
        if m["captured_at"] > self.audit_at:
            return {"error": "file captured after audit_at"}
        p = m["file_path"]
        if p.endswith(".pdf"):
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(loader.DS / p)).pages)
        elif p.endswith(".png"):
            text = json.dumps([_brief(o) for o in self.ctx.ix.obs if o.file_id == file_id])
        else:
            text = (loader.DS / p).read_text(encoding="utf-8", errors="replace")
        return {"file_id": file_id, "length": len(text), "text": text[:max_chars]}

    def identity_links(self, resource_id):
        claims = self.ctx.claims().get(resource_id, set())
        files = sorted({(o.file_id, o.captured_at, o.captured_at <= self.audit_at) for o in self.ctx.ix.by_resource.get(resource_id, [])})
        return {"resource_id": resource_id, "users_linked": sorted(claims),
                "files": [{"file_id": f, "captured_at": c, "citable": ok} for f, c, ok in files]}
