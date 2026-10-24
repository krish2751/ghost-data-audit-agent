"""Shared loaders for exploratory analysis scripts (not the solver)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "dataset"


def rows(name):
    with open(DS / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evidence_text(path):
    """Plain text of an evidence file; PDFs via pypdf, PNGs return ''."""
    p = DS / path
    if p.suffix == ".pdf":
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    if p.suffix == ".png":
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def manifest():
    return {m["file_id"]: m for m in rows("evidence_files.csv")}


def identities():
    """user_id -> dict(current fields, emails/phones sets including historical, audit rows)."""
    users = {u["user_id"]: u for u in rows("user_identities.csv")}
    hist = {}
    for u, rec in users.items():
        hist[u] = {"emails": {rec["email"].lower()}, "phones": {rec["phone"]}, "hashes": {rec["email_hash"]},
                   "names": {rec["name"]}, "audit": []}
    for a in rows("user_audit_log.csv"):
        h = hist.get(a["user_id"])
        if h is None:
            continue
        h["audit"].append(a)
        for v in (a["old_value"], a["new_value"]):
            if a["field_name"] == "email" and v:
                h["emails"].add(v.lower())
            elif a["field_name"] == "phone" and v:
                h["phones"].add(v)
            elif a["field_name"] == "name" and v:
                h["names"].add(v)
    return users, hist


def email_to_user(hist):
    out = {}
    for u, h in hist.items():
        for e in h["emails"]:
            out.setdefault(e, set()).add(u)
    return out


def sample_cases():
    req = {r["case_id"]: r for r in rows("sample_deletion_requests.csv")}
    out = {}
    for r in rows("sample_output.csv"):
        out[r["case_id"]] = (r["deletion_status"], json.loads(r["steps_json"]))
    return req, out
