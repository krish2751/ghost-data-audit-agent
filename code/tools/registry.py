"""Deterministic investigation tools for the agent, bound to one case so nothing after audit_at is visible.

Tools only return files captured at or before audit_at. Used by the rule-condition reader.
"""
import json
import re

from data import loader
from data.states import category, reading
from schema import TREATMENT

MAX_ROWS = 40

TOOL_SCHEMAS = [
    {"name": "search_evidence", "description": "Find observations (files captured at or before audit_at) whose content contains a token (email, user_id, hash, resource_id, phone).",
     "input_schema": {"type": "object", "properties": {"token": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["token"]}},
    {"name": "get_resource", "description": "All observations of one resource at or before audit_at, with the derived reading, plus its activity rows.",
     "input_schema": {"type": "object", "properties": {"resource_id": {"type": "string"}}, "required": ["resource_id"]}},
    {"name": "read_evidence", "description": "Raw text of an evidence file captured at or before audit_at (PDF text, text ledger, log), truncated.",
     "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["file_id"]}},
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
