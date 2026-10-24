"""Normalize every evidence file (SQL, JSON, TXT, logs, PDF, PNG extraction) into observations.

An Obs is one record about one resource as seen in one file. `captured_at` is the file's manifest time,
`snap_time` is the time of the snapshot/line/record inside the file (used to order observations).
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field

from schema import PREFIX_INFO
from .loader import DS, manifest

RES_RX = re.compile(r"\b(account|search|support|analytics|export|backup|data_flow|audit_record|tombstone|legal_hold|marketing|cache|email_delivery)_\d+\b")
KV_RX = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s"]+)')
TS_RX = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
TRACE_RX = re.compile(r"\b(?:tr|rb)-[\w-]+")


def prefix_of(resource_id):
    m = re.match(r"([a-z_]+?)_\d+$", resource_id or "")
    return m.group(1) if m else None


def norm_null(v):
    return None if isinstance(v, str) and v.strip().lower() in ("null", "none", "") else v


def flatten(d):
    """Top-level keys plus one level of nested dict keys (outer keys win)."""
    out = dict(d)
    for k, v in d.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out.setdefault(kk, vv)
    return {k: norm_null(v) for k, v in out.items()}


@dataclass
class Obs:
    file_id: str
    captured_at: str
    snap_time: str
    kind: str
    source: str
    resource_id: str
    attrs: dict
    text: str = field(default="", repr=False)

    @property
    def system_id(self):
        info = PREFIX_INFO.get(prefix_of(self.resource_id))
        return info[0] if info else None


def _mk(fid, cap, snap, kind, source, rid, attrs):
    attrs = flatten(attrs)
    text = "\n".join(f"{k}: {json.dumps(v, default=str) if isinstance(v, (dict, list)) else v}" for k, v in attrs.items() if v is not None)
    return Obs(fid, cap, snap or cap, kind, source, rid, attrs, text.lower())


def _sql(fid, cap, path):
    con = sqlite3.connect(":memory:")
    con.executescript((DS / path).read_text(encoding="utf-8"))
    out = []
    for (t,) in con.execute("select name from sqlite_master where type='table' order by 1"):
        cur = con.execute(f'select * from "{t}"')
        cols = [c[0] for c in cur.description]
        if "resource_id" not in cols:
            continue
        for row in cur:
            d = dict(zip(cols, row))
            rj = d.pop("record_json", None)
            if rj:
                d.update(json.loads(rj))
            d["table"] = t
            out.append(_mk(fid, cap, None, "sql", t, d.get("resource_id"), d))
    return out


def _json(fid, cap, path):
    d = json.loads((DS / path).read_text(encoding="utf-8"))
    out = []
    if "snapshots" in d:  # records-assurance bundles: each snapshot has its own capture time
        for s in d["snapshots"]:
            for r in s["records"]:
                rec = dict(r); rec["data_store"] = s["data_store"]
                out.append(_mk(fid, cap, rec.get("recorded_at") or s["captured_at"], "json", s["collection"], r.get("resource_id"), rec))
    elif "service_exports" in d:
        for svc, lists in d["service_exports"].items():
            for lname, items in lists.items():
                for it in items:
                    if lname == "index_queries":
                        for doc in it.get("hits", {}).get("documents", []):
                            rec = dict(doc); rec["query"] = it.get("query")
                            out.append(_mk(fid, cap, it.get("observed_at"), "json", f"{svc}.{lname}", doc.get("resource_id"), rec))
                    else:
                        out.append(_mk(fid, cap, it.get("observed_at"), "json", f"{svc}.{lname}", it.get("resource_id"), it))
    else:
        for r in d.get("records", []):
            out.append(_mk(fid, cap, r.get("recorded_at") or r.get("created_at"), "json", d.get("collection") or d.get("origin") or "records", r.get("resource_id"), r))
    return [o for o in out if o.resource_id]


def _txt(fid, cap, path):
    out = []
    for line in (DS / path).read_text(encoding="utf-8").splitlines():
        p = [x.strip() for x in line.lstrip("- ").split("|")]
        if len(p) == 6 and TS_RX.match(p[0]):
            out.append(_mk(fid, cap, p[0], "txt", "text_ledger", p[2], {"system": p[1], "record_type": p[3], "result": p[4], "subject_reference": p[5]}))
    return out


def _parse_log_line(line):
    m = TS_RX.match(line)
    if not m:
        return None
    ts, rest = m.group(0), line[m.end():].strip()
    if rest.startswith("{"):
        try:
            return ts, {k: str(v) if v is not None else None for k, v in json.loads(rest).items()}
        except ValueError:
            return None
    inner = re.search(r'message="(.*)"\s*$', rest)
    if inner:  # cloud-runtime export wraps the real record in an escaped message
        rest = rest[:inner.start()] + " " + inner.group(1).replace('\\"', '"')
    attrs = {k: v.strip('"') for k, v in KV_RX.findall(rest)}
    if "event" not in attrs:
        e = re.search(r"\]\s+(\w+):", rest) or re.search(r"\|\s*(\w+_\w+)\s*\|\s*instance", rest)
        if e:
            attrs["event"] = e.group(1)
    tr = TRACE_RX.search(line)
    if tr and "trace_id" not in attrs:
        attrs["trace_id"] = tr.group(0)
    return ts, attrs


def _log(fid, cap, path):
    merged, parsed = {}, []
    by_trace = {}
    for line in (DS / path).read_text(encoding="utf-8", errors="replace").splitlines():
        pl = _parse_log_line(line)
        if not pl:
            continue
        parsed.append(pl)
        if not pl[1].get("resource_id") and pl[1].get("trace_id"):
            by_trace.setdefault(pl[1]["trace_id"], {}).update({k: v for k, v in pl[1].items() if v is not None})
    for ts, attrs in parsed:
        if not attrs.get("resource_id"):
            continue
        for k, v in by_trace.get(attrs.get("trace_id"), {}).items():
            attrs.setdefault(k, v)
        key = (attrs.get("trace_id"), attrs["resource_id"]) if attrs.get("trace_id") else (ts, attrs["resource_id"], len(merged))
        if key in merged:
            merged[key][1].update({k: v for k, v in attrs.items() if v is not None})
            merged[key][0] = max(merged[key][0], ts)
        else:
            merged[key] = [ts, dict(attrs)]
    return [_mk(fid, cap, ts, "log", a.get("event", "log"), a["resource_id"], a) for ts, a in merged.values()]


def _pdf(fid, cap, path):
    from pypdf import PdfReader
    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(DS / path)).pages)
    ids = sorted({m.group(0) for m in RES_RX.finditer(text)})
    name = path.split("/")[-1]
    out = [_mk(fid, cap, None, "pdf", name, rid, {"text": text, "file_name": name}) for rid in ids]
    if not out:  # still useful for identity links (customer statement, retention registers)
        out = [_mk(fid, cap, None, "pdf", name, None, {"text": text, "file_name": name})]
    return out


def _png(fid, cap, path):
    try:
        import screenshots
        data, _ = screenshots.extract({"file_id": fid, "file_path": path})
    except Exception:  # no cached extraction and no API key: skip the screenshot
        return []
    out = []
    for rec in (data or {}).get("records", []):
        rid = rec.get("resource_id")
        attrs = {}
        for k in ("identifiers", "status_fields", "timestamps", "other_fields"):
            attrs.update({kk.lower().replace(" ", "_"): vv for kk, vv in (rec.get(k) or {}).items()})
        attrs["screen_title"] = (data or {}).get("screen_title")
        if rid:
            out.append(_mk(fid, cap, (data or {}).get("screen_timestamp"), "png", "screenshot", rid, attrs))
    return out


class EvidenceIndex:
    def __init__(self, use_png=True):
        self.man = manifest()
        self.obs = []
        for fid, m in self.man.items():
            p, cap = m["file_path"], m["captured_at"]
            if p.endswith(".sql"):
                self.obs += _sql(fid, cap, p)
            elif p.endswith(".json"):
                self.obs += _json(fid, cap, p)
            elif p.endswith(".txt"):
                self.obs += _txt(fid, cap, p)
            elif p.endswith(".log"):
                self.obs += _log(fid, cap, p)
            elif p.endswith(".pdf"):
                self.obs += _pdf(fid, cap, p)
            elif p.endswith(".png") and use_png:
                self.obs += _png(fid, cap, p)
        self.by_resource = {}
        for o in self.obs:
            if o.resource_id:
                self.by_resource.setdefault(o.resource_id, []).append(o)
