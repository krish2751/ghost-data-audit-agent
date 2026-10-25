"""Mismatch report for manual review: every sample that is not an exact match, generated from the current pipeline.

Usage: .venv/bin/python code/evaluation/mismatch_review.py   (writes code/evaluation/mismatch_review.md)

The predictions are recomputed in-process exactly as code/main.py --sample does, and the joint-assignment state of
code/joint.py (identifier-linked accounts, learned window, status/result compatibility, outcome model) is rebuilt with
the same rules so every candidate record can be listed with the reason it was taken, rejected or left tied. The rebuild
is checked against joint.compute's own assignments and the script stops if they differ. Reads no pipeline answers from
memory; sample_output.csv is read only to compare.
"""
import csv
import difflib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joint  # noqa: E402
import screenshots  # noqa: E402
from data import loader  # noqa: E402
from data.evidence_index import prefix_of  # noqa: E402
from data.states import reading  # noqa: E402
from fallback import Context, P, _matcher, solve_all  # noqa: E402
from readers.intent_reader import prefetch_intents  # noqa: E402
from validator import dumps  # noqa: E402

ROOT = loader.ROOT
DS = loader.DS
OUT = ROOT / "code" / "evaluation" / "mismatch_review.md"
FIELDS = ("phase", "operation", "system_id", "resource_id", "state", "evidence_id")
ANSWER_FILE = "sample_output.csv"
NEAREST = 3  # events just outside a learned window listed for the reviewer (display only)


def mins(t, ref):
    return (P(t) - P(ref)).total_seconds() / 60


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------- participant-file search (path + line number)

def search_corpus(ctx):
    """[(display path, [lines])] for every participant file; PDFs by page, screenshots by their cached extraction."""
    docs = []
    for p in sorted(DS.glob("*.csv")):
        docs.append((f"dataset/{p.name}", p.read_text(encoding="utf-8").splitlines()))
    for fid, m in sorted(ctx.man.items(), key=lambda x: x[1]["file_path"]):
        path = DS / m["file_path"]
        name = f"dataset/{m['file_path']}"
        if path.suffix == ".pdf":
            from pypdf import PdfReader
            for i, pg in enumerate(PdfReader(str(path)).pages, 1):
                docs.append((f"{name} (page {i} text)", (pg.extract_text() or "").splitlines()))
        elif path.suffix == ".png":
            try:
                data, _ = screenshots.extract({"file_id": fid, "file_path": m["file_path"]})
            except Exception:
                data = None
            docs.append((f"{name} (cached screenshot extraction)", json.dumps(data, indent=1, sort_keys=True).splitlines()))
        else:
            docs.append((name, path.read_text(encoding="utf-8", errors="replace").splitlines()))
    return docs


def find(docs, pattern):
    rx = re.compile(pattern)
    hits = []
    for name, lines in docs:
        for n, line in enumerate(lines, 1):
            m = rx.search(line)
            if m:
                tok = re.search(r"[\w.@+-]*" + re.escape(m.group(0)) + r"[\w.@+-]*", line[max(0, m.start() - 80):m.end() + 80])
                a, b = max(0, m.start() - 50), m.end() + 50
                hits.append((name, n, tok.group(0) if tok else m.group(0),
                             ("…" if a else "") + line[a:b].strip() + ("…" if b < len(line) else "")))
    return hits


def occurrences(docs, rid):
    num = rid.rsplit("_", 1)[1]
    exact = find(docs, r"(?<![A-Za-z0-9_])" + re.escape(rid) + r"(?![0-9])")
    seen = {(h[0], h[1]) for h in exact}
    bare = [h for h in find(docs, r"(?<![0-9])" + num + r"(?![0-9])") if (h[0], h[1]) not in seen]
    return exact, bare


# ---------------------------------------------------------------- rebuild of joint.py's state

class JointState:
    """Same inputs and rules as joint.compute; asserted equal to its output."""

    def __init__(self, ctx, base, reqs):
        self.ctx, self.base = ctx, base
        self.by_case = {r["case_id"]: r for r in reqs}
        self.claims = ctx.claims()
        self.uid_of, self.assigned, need = {}, {}, {}
        for r in reqs:
            res = base[r["case_id"]][0]
            if res["status"] == "NOT_APPLICABLE" or "uid" not in res:
                continue
            self.uid_of[r["case_id"]] = res["uid"]
            accs = [d["resource_id"] for d in res["resources"] if d["resource_id"].startswith("account")]
            if accs:
                self.assigned[r["case_id"]] = accs[0]
            else:
                need[r["case_id"]] = r
        self.out = ctx._joint["account"]
        self.bounds = ctx._joint_info["bounds"]["account"]
        pair = Counter()
        for cid, acc in self.assigned.items():
            ev = [a for a in ctx.act_by_res.get(acc, []) if a["event_type"] == "DELETE_RECORD"]
            if ev:
                pair[(self.by_case[cid]["reported_status"], ev[0]["reported_result"])] += 1
        tot = Counter()
        for (st, _), n in pair.items():
            tot[st] += n
        self.compat = {k for k, n in pair.items() if n / tot[k[0]] >= 0.05}
        self.holder = {acc: (cid, "identifier-linked") for cid, acc in self.assigned.items()}
        self.holder.update({acc: (cid, how) for cid, (acc, how) in self.out.items()})
        self.unresolved = sorted(c for c in need if c not in self.out)
        assert len(self.unresolved) == ctx._joint_info["ambiguous"], "account state rebuild differs from joint.compute"
        self.dels = [a for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
        # analytics (assign_unlinked)
        known = list(self.assigned.items()) + [(c, a) for c, (a, _) in self.out.items()]
        for c, d in base.items():
            for x in d[0]["resources"]:
                known.append((c, x["resource_id"]))
        self.known_holder = {}
        for c, rid in known:
            self.known_holder.setdefault(rid, c)
        self.have_an = {c: rid for c, rid in known if prefix_of(rid) == "analytics"}
        self.model = ctx._joint_info["bounds"]["outcome_model"]
        self.an_evs = [a for a in ctx.act if a["event_type"] == "ANONYMIZE_RECORD" and prefix_of(a["resource_id"]) == "analytics"]
        self.open_an = [r for r in reqs if r["case_id"] in self.uid_of and r["case_id"] not in self.have_an]
        self._outcome = {}
        rebuilt = {}
        for r in self.open_an:
            cs = sorted({a["resource_id"] for a in self.an_evs if not self.an_reasons(r, a)})
            if len(cs) == 1 and self.an_owners(cs[0]) == [r["case_id"]]:
                rebuilt[r["case_id"]] = cs[0]
        assert rebuilt == {c: v[0] for c, v in ctx._joint["analytics"].items()}, "analytics state rebuild differs from joint.compute"

    # accounts
    def acc_reasons(self, r, a, strict):
        """Reasons the account DELETE event `a` cannot fill case r's account slot (empty list: it fits)."""
        why = []
        off = mins(a["event_time"], r["reported_at"])
        if a["event_time"] > r["audit_at"]:
            why.append("event after audit_at")
        if not self.bounds[0] <= off <= self.bounds[1]:
            why.append(f"outside learned window {self.bounds[0]:.0f}..{self.bounds[1]:.0f} min")
        h = self.holder.get(a["resource_id"])
        if h and h[0] != r["case_id"]:
            why.append(f"taken by {h[0]} ({h[1]})")
        other = self.claims.get(a["resource_id"], set()) - {self.uid_of.get(r["case_id"])}
        if other:
            why.append("claimed by " + ", ".join(sorted(other)) + " through an identifier")
        if strict and (r["reported_status"], a["reported_result"]) not in self.compat:
            why.append(f"({r['reported_status']}, {a['reported_result']}) not a compatible status/result pair (strict pass only)")
        return why

    def acc_competitors(self, a, cid):
        out = []
        for c in self.unresolved:
            if c == cid:
                continue
            r = self.by_case[c]
            if not self.acc_reasons(r, a, False):
                out.append(c + ("" if not self.acc_reasons(r, a, True) else " (relaxed pass only)"))
        return out

    # analytics
    def outcome(self, rid, audit_at):
        k = (rid, audit_at)
        if k not in self._outcome:
            self._outcome[k] = joint.outcome_of(self.ctx, rid, audit_at)
        return self._outcome[k]

    def an_reasons(self, r, a):
        """Reasons, in joint.assign_unlinked's terms, why ANONYMIZE event `a` does not fit case r (empty: it fits)."""
        why = []
        if a["event_time"] > r["audit_at"]:
            why.append("event after audit_at")
        h = self.known_holder.get(a["resource_id"])
        if h is not None:
            why.append(f"already linked to {h}")
        other = self.claims.get(a["resource_id"], set()) - {self.uid_of.get(r["case_id"])}
        if other:
            why.append("claimed by " + ", ".join(sorted(other)) + " through an identifier")
        if why:
            return why
        o = self.outcome(a["resource_id"], r["audit_at"])
        m = self.model.get(o)
        if not m or not m["bounds"]:
            return ["no observation of the record captured by audit_at (outcome unknown)"]
        off = mins(a["event_time"], r["reported_at"])
        if not m["bounds"][0] <= off <= m["bounds"][1]:
            why.append(f"outcome {o}: outside its window {m['bounds'][0]:.0f}..{m['bounds'][1]:.0f} min")
        if (r["reported_status"], a["reported_result"]) not in m["compat"]:
            why.append(f"outcome {o}: ({r['reported_status']}, {a['reported_result']}) not compatible")
        return why

    def an_owners(self, rid):
        return [o["case_id"] for o in self.open_an if any(a["resource_id"] == rid and not self.an_reasons(o, a) for a in self.an_evs)]


# ---------------------------------------------------------------- report sections

def align(exp, pred):
    """Rows (mark, e, p, differing fields) aligning expected and predicted steps on (phase, operation, resource_id)."""
    key = lambda s: (s["phase"], s["operation"], s["resource_id"])
    sm = difflib.SequenceMatcher(None, [key(s) for s in exp], [key(s) for s in pred], autojunk=False)
    rows = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for e, p in zip(exp[i1:i2], pred[j1:j2]):
                diff = [f for f in FIELDS if e[f] != p[f]]
                rows.append(("DIFFERENT" if diff else "MATCH", e, p, diff))
        else:
            rows += [("MISSING", e, None, []) for e in exp[i1:i2]]
            rows += [("EXTRA", None, p, []) for p in pred[j1:j2]]
    return rows


def step_table(rows):
    L = ["| Mark | exp # | pred # | phase | operation | system_id | resource_id | state | evidence_id |",
         "|---|---|---|---|---|---|---|---|---|"]
    for mark, e, p, diff in rows:
        s = e or p
        vals = []
        for f in FIELDS:
            if f in diff:
                vals.append(f"**{cell(e[f]) or '\"\"'} → {cell(p[f]) or '\"\"'}**")
            else:
                vals.append(f"`{cell(s[f])}`" if s[f] else '""')
        m = f"**{mark}**" if mark != "MATCH" else mark
        L.append(f"| {m} | {e['step_no'] if e else ''} | {p['step_no'] if p else ''} | " + " | ".join(vals) + " |")
    return L


def identity_section(ctx, req, uid, linked):
    u = ctx.ids.users[uid]
    used = ctx.ids.identifiers(uid, req["audit_at"])
    rows = [("email", u["email"].lower(), f"current snapshot (updated {u.get('updated_at', '')})".replace(" (updated )", "")),
            ("phone", u["phone"], "current snapshot"), ("email_hash", u["email_hash"], "current snapshot"),
            ("user_id", uid, "current snapshot")]
    for a in ctx.ids.audit.get(uid, []):
        for side in ("old_value", "new_value"):
            v = a[side]
            if v and a["field_name"] != "name":
                v = v.lower() if a["field_name"] == "email" else v
                rows.append((a["field_name"], v, f"{a['audit_id']} {side.split('_')[0]} value, changed {a['event_time']}"))
    seen, L = set(), ["| field | value | source | used at audit_at | observations containing it | linked records it hits |",
                      "|---|---|---|---|---|---|"]
    for f, v, src in rows:
        if (f, v) in seen:
            continue
        seen.add((f, v))
        rx = _matcher({v.lower()})
        hit = [o for o in ctx.ix.obs if o.resource_id and rx.search(o.text)]
        res = sorted({o.resource_id for o in hit} & set(linked))
        L.append(f"| {f} | `{cell(v)}` | {cell(src)} | {'yes' if v in used.get(f, ()) else 'no'} | {len(hit)} | "
                 f"{', '.join(res) if res else '-'} |")
    req_email = req["email"].strip().lower()
    note = "current" if req_email == u["email"].lower() else "historical"
    return L, note


def citation(ctx, eid, audit_at, act, audits):
    if not eid:
        return "empty evidence_id (future work step)"
    if eid in ctx.man:
        m = ctx.man[eid]
        ok = "captured by audit_at" if m["captured_at"] <= audit_at else "**captured after audit_at**"
        return f"`{eid}`: `dataset/{m['file_path']}`, origin `{m['origin']}`, captured_at {m['captured_at']} ({ok})"
    if eid in act:
        a = act[eid]
        return f"`{eid}` (system_activity.csv): {a['event_time']} {a['event_type']} {a['resource_id']} result {a['reported_result']}"
    if eid in audits:
        a = audits[eid]
        return f"`{eid}` (user_audit_log.csv): {a['event_time']} {a['user_id']} {a['field_name']}"
    return f"`{eid}`: **not found in the manifest, system_activity.csv or user_audit_log.csv**"


def account_slot(js, req, rid, pred_res):
    cid = req["case_id"]
    L, diag = [], None
    have = [d["resource_id"] for d in pred_res if prefix_of(d["resource_id"]) == "account"]
    rep = req["reported_at"]
    L.append(f"Slot: the case's account (one account per case). Learned DELETE window: "
             f"{js.bounds[0]:.0f}..{js.bounds[1]:.0f} min from reported_at; compatible (reported_status, result) pairs: "
             + ", ".join(f"({s}, {r})" for s, r in sorted(js.compat)) + ".")
    if have:
        L.append(f"The slot is already filled in our prediction by {', '.join(have)} ({pred_res[0]['why'] if pred_res else ''}).")
    elif cid in js.unresolved:
        L.append("Our code left this case unresolved after propagation (no single remaining candidate).")
    elif cid in js.out:
        L.append(f"Joint assignment gave this case {js.out[cid][0]} ({js.out[cid][1]}).")
    inside = lambda a: js.bounds[0] <= mins(a["event_time"], rep) <= js.bounds[1]
    gap = lambda a: max(js.bounds[0] - mins(a["event_time"], rep), mins(a["event_time"], rep) - js.bounds[1])
    near = sorted((a for a in js.dels if not inside(a)), key=gap)[:NEAREST]
    evs = sorted({a["activity_id"]: a for a in [a for a in js.dels if inside(a)] + near
                  + [a for a in js.ctx.act_by_res.get(rid, []) if a["event_type"] == "DELETE_RECORD"]}.values(),
                 key=lambda a: (a["event_time"], a["activity_id"]))
    L.append(f"Listed: every account DELETE_RECORD event inside the window, the {NEAREST} nearest outside it, and any "
             "event on the expected record.")
    exp_has_event = any(a["resource_id"] == rid for a in evs)
    L += ["", "| activity | resource | min from reported_at | result | strict pass | relaxed pass | competing open cases |",
          "|---|---|---|---|---|---|---|"]
    fit_strict, fit_relaxed = [], []
    for a in evs:
        rs, rr = js.acc_reasons(req, a, True), js.acc_reasons(req, a, False)
        if not rs:
            fit_strict.append(a["resource_id"])
        if not rr:
            fit_relaxed.append(a["resource_id"])
        comp = js.acc_competitors(a, cid) if not rr else []
        name = f"**{a['resource_id']}** (expected)" if a["resource_id"] == rid else a["resource_id"]
        L.append(f"| {a['activity_id']} | {name} | {mins(a['event_time'], rep):+.0f} | {a['reported_result']} | "
                 f"{'fits' if not rs else cell('; '.join(rs))} | {'fits' if not rr else cell('; '.join(rr))} | "
                 f"{', '.join(comp) if comp else '-'} |")
    if not any(inside(a) for a in evs):
        L.append("| - | no account DELETE_RECORD event inside the window | | | | | |")
    if not exp_has_event:
        L.append(f"\n`{rid}` has no DELETE_RECORD event in system_activity.csv, so it is not a candidate.")
    elif rid in fit_relaxed:
        comp = sorted({c for a in evs if a["resource_id"] == rid for c in js.acc_competitors(a, cid)})
        fs, fr = sorted(set(fit_strict)), sorted(set(fit_relaxed))
        parts = [f"strict pass: {cid} fits {len(fs)} accounts ({', '.join(fs) or 'none'})",
                 f"relaxed pass: {len(fr)} ({', '.join(fr)})"]
        if comp:
            parts.append(f"{rid} also fits open cases {', '.join(comp)}")
        if len(fr) > 1 or comp:
            diag = ("tie", "; ".join(parts))
    else:
        reasons = sorted({r for a in evs if a["resource_id"] == rid for r in js.acc_reasons(req, a, False)})
        diag = ("other", f"{rid} rejected: " + "; ".join(reasons))
    return L, diag


def analytics_slot(js, req, rid, pred_res):
    cid = req["case_id"]
    rep = req["reported_at"]
    L, diag = [], None
    mb = {o: v for o, v in js.model.items()}
    L.append("Slot: an analytics record with no identifier, assigned when record and case pick each other uniquely. "
             "Learned windows by the record's own outcome at audit_at: "
             + "; ".join(f"{o} {v['bounds'][0]:.0f}..{v['bounds'][1]:.0f} min" for o, v in sorted(mb.items()) if v["bounds"]) + ".")
    have = [d["resource_id"] for d in pred_res if prefix_of(d["resource_id"]) == "analytics"]
    if have:
        L.append(f"This case already has analytics record(s) {', '.join(have)}, so it does not take part.")
    lo = min(v["bounds"][0] for v in mb.values() if v["bounds"])
    hi = max(v["bounds"][1] for v in mb.values() if v["bounds"])
    gap = lambda a: max(lo - mins(a["event_time"], rep), mins(a["event_time"], rep) - hi)
    near = sorted((a for a in js.an_evs if gap(a) > 0), key=gap)[:NEAREST]
    evs = sorted({a["activity_id"]: a for a in [a for a in js.an_evs if gap(a) <= 0 or a["resource_id"] == rid] + near}.values(),
                 key=lambda a: (a["event_time"], a["activity_id"]))
    L.append(f"Listed: every analytics ANONYMIZE_RECORD event inside {lo:.0f}..{hi:.0f} min (union of both windows), "
             f"the {NEAREST} nearest outside it, and any event on the expected record.")
    L += ["", "| activity | resource | min from reported_at | result | outcome at audit_at | fits this case | other open cases it fits |",
          "|---|---|---|---|---|---|---|"]
    fits = []
    for a in evs:
        why = js.an_reasons(req, a)
        if not why:
            fits.append(a["resource_id"])
        owners = [c for c in js.an_owners(a["resource_id"]) if c != cid] if not why else []
        name = f"**{a['resource_id']}** (expected)" if a["resource_id"] == rid else a["resource_id"]
        L.append(f"| {a['activity_id']} | {name} | {mins(a['event_time'], rep):+.0f} | {a['reported_result']} | "
                 f"{js.outcome(a['resource_id'], req['audit_at']) or '-'} | {'fits' if not why else cell('; '.join(why))} | "
                 f"{', '.join(owners) if owners else '-'} |")
    if not any(a["resource_id"] == rid for a in evs):
        L.append(f"\n`{rid}` has no ANONYMIZE_RECORD event in system_activity.csv, so it is not a candidate.")
    elif rid in fits:
        others = sorted(set(fits) - {rid})
        owners = [c for c in js.an_owners(rid) if c != cid]
        if others or owners:
            parts = ([f"{cid} also fits {', '.join(others)}"] if others else []) + \
                    ([f"{rid} also fits open cases {', '.join(owners)}"] if owners else [])
            diag = ("tie", "; ".join(parts))
    else:
        reasons = sorted({r for a in evs if a["resource_id"] == rid for r in js.an_reasons(req, a)})
        diag = ("other", f"{rid} rejected: " + "; ".join(reasons))
    return L, diag


def other_slot(js, req, rid, pred_res):
    kind = prefix_of(rid)
    rep = req["reported_at"]
    linked = [d["resource_id"] for d in pred_res if prefix_of(d["resource_id"]) == kind]
    lo, hi = js.bounds
    evs = [a for a in js.ctx.act if prefix_of(a["resource_id"]) == kind and a["event_time"] <= req["audit_at"]
           and lo <= mins(a["event_time"], rep) <= hi]
    L = [f"Slot: none. The code links `{kind}` records only when their own content carries one of the subject's "
         f"identifiers (or a LINK_RESOURCE_IDENTITY row); there is no assignment of unlinked `{kind}` records.",
         f"Our linked `{kind}` records for this case: {', '.join(linked) if linked else 'none'}.",
         f"For reference only (not used by the code): activity rows on `{kind}` resources inside the account window "
         f"{lo:.0f}..{hi:.0f} min of reported_at and by audit_at: "
         + (", ".join(f"{a['activity_id']} {a['event_type']} {a['resource_id']} ({mins(a['event_time'], rep):+.0f} min, "
                      f"{a['reported_result']})" for a in sorted(evs, key=lambda a: a["event_time"])) if evs else "none") + "."]
    return L, None


SLOTS = {"account": account_slot, "analytics": analytics_slot}


def main():
    samples = loader.requests(sample=True)
    reqs = samples + loader.requests()
    ctx = Context()
    prefetch_intents(ctx, reqs)
    base = solve_all(ctx, reqs, heuristics=False)
    ctx._joint, ctx._joint_info = joint.compute(ctx, base=base)
    js = JointState(ctx, base, reqs)
    solved = solve_all(ctx, samples)
    with open(DS / ANSWER_FILE, newline="", encoding="utf-8") as f:
        gold = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(f)}
    pred = {cid: (res["status"], json.loads(dumps(steps))) for cid, (res, steps) in solved.items()}
    saved = ROOT / "code" / "runs" / "sample_pred.csv"
    same_as_saved = None
    if saved.exists():
        with open(saved, newline="", encoding="utf-8") as f:
            same_as_saved = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(f)} == pred
    act = {a["activity_id"]: a for a in ctx.act}
    audits = {a["audit_id"]: a for rows in ctx.ids.audit.values() for a in rows}
    docs = search_corpus(ctx)
    by_case = {r["case_id"]: r for r in samples}
    bad = sorted((c for c in gold if gold[c] != pred.get(c)), key=lambda c: int(c.split("_")[1]))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    summary, body = [], []
    for cid in bad:
        req = by_case[cid]
        (gs, gsteps), (ps, psteps) = gold[cid], pred[cid]
        res = solved[cid][0]
        uid = res.get("uid")
        rows = align(gsteps, psteps)
        nm = Counter(r[0] for r in rows)
        missing_rids = sorted({r[1]["resource_id"] for r in rows if r[0] == "MISSING"})
        extra_rids = sorted({r[2]["resource_id"] for r in rows if r[0] == "EXTRA"})
        B = [f"## {cid}", ""]
        B += ["| field | value |", "|---|---|",
              f"| request email | `{req['email']}` |",
              f"| resolved user_id | `{uid or 'none'}` |",
              f"| requested_at | {req['requested_at']} |", f"| reported_status | {req['reported_status']} |",
              f"| reported_at | {req['reported_at']} |", f"| audit_at | {req['audit_at']} |",
              f"| status: ours vs expected | {ps} vs {gs}{'' if ps == gs else ' (**differs**)'} |",
              f"| steps: matched / missing / extra / different | {nm['MATCH']} / {nm['MISSING']} / {nm['EXTRA']} / {nm['DIFFERENT']} |", ""]
        if uid:
            idl, note = identity_section(ctx, req, uid, [d["resource_id"] for d in res["resources"]])
            B += [f"Identifiers of `{uid}` (the request email is its {note} email). \"Used at audit_at\" is the set the code "
                  "matches for this case; the name is never used as a link token.", ""] + idl + [""]
        B += ["### Expected vs predicted steps", "",
              "Rows are aligned on (phase, operation, resource_id). A step-number shift caused by a missing or extra "
              "step is not counted as DIFFERENT.", ""] + step_table(rows) + [""]
        diags = []
        for rid in missing_rids:
            kind = prefix_of(rid)
            steps = [r[1] for r in rows if r[0] == "MISSING" and r[1]["resource_id"] == rid]
            B += [f"### Missing `{rid}`", "", "**Cited evidence in the expected answer:**", ""]
            for s in steps:
                B.append(f"- step {s['step_no']} {s['operation']}: {citation(ctx, s['evidence_id'], req['audit_at'], act, audits)}")
            obs = ctx.ix.by_resource.get(rid, [])
            B += ["", f"**Observations of `{rid}` in our evidence index:** "
                  + ("; ".join(f"{o.file_id} captured {o.captured_at}, snapshot {o.snap_time}, reading {reading(o)}" for o in obs)
                     if obs else "none") + "."]
            exact, bare = occurrences(docs, rid)
            num = rid.rsplit("_", 1)[1]
            B += ["", f"**Where `{rid}` appears in participant files** ({len(exact)} lines):", ""]
            B += [f"- `{n}:{ln}` — {cell(snip)}" + (" *(the answer file)*" if n.endswith(ANSWER_FILE) else "")
                  for n, ln, _, snip in exact] or ["- nowhere"]
            B += ["", f"**Where the bare number `{num}` appears elsewhere** ({len(bare)} lines; the token around it shows what it names):", ""]
            if bare:
                B += ["| file:line | token | text |", "|---|---|---|"]
                B += [f"| `{n}:{ln}` | `{cell(tok)}` | {cell(snip)} |" for n, ln, tok, snip in bare]
            else:
                B.append("- nowhere")
            B += ["", "**Candidates our code considered for this slot:**", ""]
            sl, d = SLOTS.get(kind, other_slot)(js, req, rid, res["resources"])
            B += sl + [""]
            in_data = [h for h in exact if not h[0].endswith(ANSWER_FILE)]
            if not in_data:
                d = ("not in data", f"{rid} appears in no participant file except {ANSWER_FILE}")
            elif d is None:
                d = ("other", f"{rid} is in the data ({len(in_data)} lines) but no rule of the code links it to this case")
            diags.append((rid, d))
            B += [f"**Diagnosis for `{rid}`:** {d[0]} — {d[1]}.", ""]
        for rid in extra_rids:
            d = next((x for x in res["resources"] if x["resource_id"] == rid), {})
            diags.append((rid, ("other", f"extra {rid}, linked by {d.get('why', '?')}")))
            B += [f"### Extra `{rid}`", "", f"Linked by `{d.get('why', '?')}`; reading {d.get('reading')}, treatment {d.get('treatment')}.", ""]
        if ps != gs:
            diags.append(("status", ("other", f"status {ps} vs {gs}")))
        kinds = sorted({d[0] for _, d in diags})
        line = "; ".join(f"{d[0]}: {d[1]}" for _, d in diags) or "no step-level difference found"
        B += [f"### Diagnosis", "", line, ""]
        body += B
        summary.append(f"| [{cid}](#{cid}) | {nm['MISSING']} | {nm['EXTRA']} | {nm['DIFFERENT']} | {', '.join(kinds)} | "
                       f"{cell('; '.join(f'{rid}: {d[1]}' for rid, d in diags))} |")

    head = ["# Mismatch review: samples that are not an exact match", "",
            f"Generated by `code/evaluation/mismatch_review.py` from the pipeline at commit `{commit}`. Predictions were "
            "recomputed in-process (same code path as `code/main.py --sample`); "
            + ("they are identical to `code/runs/sample_pred.csv`." if same_as_saved else
               "**they differ from `code/runs/sample_pred.csv`**." if same_as_saved is False else "no saved prediction file to compare.")
            + f" {len(gold) - len(bad)} of {len(gold)} samples are exact matches; the {len(bad)} below are not.", "",
            "Diagnosis rules (applied by the script): **not in data** = the expected resource_id appears in no participant "
            f"file other than `{ANSWER_FILE}`; **tie** = the expected record fits this case under the code's rules, but "
            "another record also fits the case or another open case also fits the record; **other** = anything else, with "
            "the reason. Searches cover every file under `dataset/`, PDF text page by page, and the cached extraction of "
            "each screenshot; line numbers count a CSV header as line 1. Minutes are event_time minus the case's "
            "reported_at.", "",
            "| case | missing steps | extra steps | different steps | diagnosis | detail |", "|---|---|---|---|---|---|"]
    OUT.write_text("\n".join(head + summary + [""] + body), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(bad)} cases; identical to saved predictions: {same_as_saved}")


if __name__ == "__main__":
    main()
