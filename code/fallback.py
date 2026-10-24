"""Deterministic case solver: identity -> linked resources -> state at audit_at -> policy verdicts -> steps.

Also the source of the dossier the agent receives. Every decision is derived from files captured at or
before audit_at; identity links may come from any file (see CLAUDE.md decisions).
"""
import re
from collections import Counter
from datetime import datetime, timedelta

from data import loader
from data.evidence_index import EvidenceIndex, prefix_of
from data.identity import IdentityStore
from data.states import category, reading, violation
import intent as intent_mod
from intent import wants_deletion
from planner import plan
from schema import PREFIX_INFO, TREATMENT

P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
WINDOW_MIN = 120  # generic search window around reported_at for activity-based account discovery


class Context:
    def __init__(self, use_png=True, intent_mode="model", conditions_mode="model"):
        self.intent_mode = intent_mode
        self.conditions_mode = conditions_mode
        self._pdf = {}
        self.intent_cache = {}
        self.ids = IdentityStore()
        self.ix = EvidenceIndex(use_png=use_png)
        self.man = self.ix.man
        self.act = loader.activity()
        self.links = loader.activity_links(self.act)
        self.act_by_res = {}
        for a in self.act:
            self.act_by_res.setdefault(a["resource_id"], []).append(a)
        self._claims = None

    def pdf_text(self, fid):
        if fid not in self._pdf:
            from pypdf import PdfReader
            self._pdf[fid] = "\n".join((p.extract_text() or "") for p in PdfReader(str(loader.DS / self.man[fid]["file_path"])).pages)
        return self._pdf[fid]

    def classify_nondeletion(self, uid, audit_at):
        """True if an intake CLASSIFY_REQUEST (non-deletion) row at or before audit_at belongs to a resource linked to the user."""
        claims = self.claims()
        return any(a["event_type"] == "CLASSIFY_REQUEST" and a["event_time"] <= audit_at and uid in claims.get(a["resource_id"], ())
                   for a in self.act)

    def intent(self, req, uid=None):
        """(wants_deletion, info) using the model reader when enabled, else the regex baseline."""
        text = req["request_text"]
        if self.intent_mode == "model":
            if text not in self.intent_cache:
                from readers.intent_reader import read_intent
                try:
                    self.intent_cache[text] = read_intent(text)
                except RuntimeError as e:  # no cache entry and no API key
                    self.intent_cache[text] = {"facts": None, "rounds": 0, "error": str(e)}
            r = self.intent_cache[text]
            cls = self.classify_nondeletion(uid, req["audit_at"]) if uid else None
            wants, flags = intent_mod.decide(r["facts"], cls)
            if wants is not None:
                return wants, {"source": "model", "flags": flags, "facts": r["facts"], "rounds": r["rounds"]}
        return wants_deletion(text), {"source": "regex", "flags": ["regex_fallback"] if self.intent_mode == "model" else []}

    def claims(self):
        """resource_id -> set of users whose identifiers appear in any observation / link row (any capture date)."""
        if self._claims is None:
            em = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"); us = re.compile(r"\buser_\d+\b"); hs = re.compile(r"\b[0-9a-f]{64}\b")
            hash_user = {u["email_hash"]: uid for uid, u in self.ids.users.items()}
            c = {}
            for o in self.ix.obs:
                if not o.resource_id:
                    continue
                for e in em.findall(o.text):
                    c.setdefault(o.resource_id, set()).update(self.ids.by_email.get(e.lower(), ()))
                for u in us.findall(o.text):
                    if u in self.ids.users:
                        c.setdefault(o.resource_id, set()).add(u)
                for h in hs.findall(o.text):
                    if h in hash_user:
                        c.setdefault(o.resource_id, set()).add(hash_user[h])
            for _, rid, email, uid, _ in self.links:
                c.setdefault(rid, set()).add(uid)
            self._claims = c
        return self._claims


def _matcher(tokens):
    alts = "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))
    return re.compile(r"(?<![\w.+-])(?:" + alts + r")(?![\w])")


def solve(ctx, req, heuristics=True):
    audit_at = req["audit_at"]
    out = {"case_id": req["case_id"], "status": None, "resources": [], "notes": []}
    uids = ctx.ids.resolve_email(req["email"])
    wants, info = ctx.intent(req, uids[0] if uids else None)
    out["intent"] = info
    if not wants:
        out["status"] = "NOT_APPLICABLE"
        return out
    if not uids:
        out["notes"].append("no identity for email")
        out["status"] = "INCOMPLETE"
        return out
    uid = uids[0]
    out["uid"] = uid
    rx = _matcher(ctx.ids.tokens(uid, audit_at))

    cand = {}  # resource_id -> why it is linked
    for o in ctx.ix.obs:
        if o.resource_id and rx.search(o.text):
            cand.setdefault(o.resource_id, "evidence")
    for _, rid, email, luid, _ in ctx.links:
        if luid == uid or email in ctx.ids.tokens(uid, audit_at):
            cand.setdefault(rid, "link_row")

    def seen_before(rid):
        return (any(o.captured_at <= audit_at for o in ctx.ix.by_resource.get(rid, []))
                or any(a["event_time"] <= audit_at for a in ctx.act_by_res.get(rid, [])))

    cand = {r: w for r, w in cand.items() if prefix_of(r) in PREFIX_INFO and seen_before(r)}

    if heuristics and not any(prefix_of(r) == "account" for r in cand):
        acc = _discover_account(ctx, req, uid, audit_at)
        if acc:
            cand[acc[0]] = acc[1]

    decisions = []
    for rid, why in sorted(cand.items()):
        decisions.append(_decide(ctx, rid, why, audit_at))
    decisions = [d for d in decisions if d]
    if ctx.conditions_mode == "model":
        out["conditions"] = _apply_conditions(ctx, uid, decisions, audit_at)
    anchor = _anchor(ctx, decisions, audit_at)
    for d in decisions:
        if not d["verify_evidence"]:
            d["verify_evidence"] = anchor
    out["resources"] = decisions
    out["status"] = "INCOMPLETE" if any(d["violation"] for d in decisions) else "COMPLETE"
    return out


def _discover_account(ctx, req, uid, audit_at):
    """Accounts are often tied to a user only through activity. Generic, unit-free signals."""
    rep = P(req["reported_at"])
    claims = ctx.claims()
    cands = []
    for a in ctx.act:
        if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service" and a["event_time"] <= audit_at:
            if abs((P(a["event_time"]) - rep).total_seconds()) <= WINDOW_MIN * 60:
                others = claims.get(a["resource_id"], set()) - {uid}
                if not others:
                    cands.append(a["resource_id"])
    cands = sorted(set(cands))
    return (cands[0], "activity:time_window") if len(cands) == 1 else None


def _decide(ctx, rid, why, audit_at):
    obs = [o for o in ctx.ix.by_resource.get(rid, []) if o.captured_at <= audit_at]
    pre = prefix_of(rid)
    sysid, default_cat = PREFIX_INFO[pre]
    if not obs:
        if pre != "account":
            return None
        return {"resource_id": rid, "system_id": sysid, "category": "USER_PROFILE", "reading": "NOT_FOUND",
                "treatment": "DELETE", "violation": None, "finding_evidence": None, "verify_evidence": None, "why": why}
    key = lambda o: (o.captured_at, o.snap_time)
    top = max(key(o) for o in obs)
    group = [o for o in obs if key(o) == top]
    scored = [(o, reading(o)) for o in group]
    pick = next(((o, r) for o, r in scored if violation(category(o), r)), None) or max(scored, key=lambda x: key(x[0]))
    o, rd = pick
    cat = category(o)
    if cat not in TREATMENT or rd == "UNKNOWN":
        return None
    return {"resource_id": rid, "system_id": sysid, "category": cat, "reading": rd, "treatment": TREATMENT[cat],
            "violation": violation(cat, rd), "finding_evidence": o.file_id, "verify_evidence": o.file_id, "why": why}


def _anchor(ctx, decisions, audit_at):
    c = Counter(d["verify_evidence"] for d in decisions if d["verify_evidence"])
    if c:
        return max(c, key=lambda f: (c[f], ctx.man[f]["captured_at"]))
    pre = [f for f, m in ctx.man.items() if m["captured_at"] <= audit_at]
    return max(pre, key=lambda f: ctx.man[f]["captured_at"]) if pre else None


def build_row(ctx, req, heuristics=True):
    res = solve(ctx, req, heuristics)
    steps = plan(res["status"], res["resources"])
    return res, steps


def _apply_conditions(ctx, uid, decisions, audit_at):
    """Ask the condition reader about text-dependent rule conditions, then set each record's treatment in code."""
    from readers.condition_reader import build_item, read_conditions
    items = [it for d in decisions for it in [build_item(ctx, d, uid, audit_at)] if it]
    results, run = read_conditions(ctx, items, uid, audit_at)
    log = {"items": len(items), "rounds": run["rounds"], "tool_calls": run["tool_calls"], "error": run["error"], "applied": []}
    by_id = {d["resource_id"]: d for d in decisions}
    for it in items:
        d, res = by_id[it["item_id"]], results.get(it["item_id"])
        if not res:
            continue
        ans, cat, new = res.get("answer"), d["category"], None
        if cat == "SUPPORT_MESSAGE" and ans == "no":
            new = "DELETE"
        elif cat == "SUPPORT_ATTACHMENT" and ans == "no":
            new = "REDACT"
        elif cat in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"):
            ru = res.get("retain_until")
            if ru and ru <= audit_at:
                new = "DELETE"
        d["condition"] = {"type": it["type"], "answer": ans, "reason": res.get("reason"), "retain_until": res.get("retain_until")}
        if new and new != d["treatment"]:
            d["treatment"] = new
            d["violation"] = violation(cat, d["reading"], new)
            log["applied"].append((d["resource_id"], new))
    return log


def solve_all(ctx, reqs, heuristics=True, workers=8):
    """Solve many requests concurrently (model reads are I/O bound). Returns {case_id: (result, steps)}."""
    from concurrent.futures import ThreadPoolExecutor
    ctx.claims()  # build shared lazy state before threads start

    def one(req):
        res = solve(ctx, req, heuristics)
        return req["case_id"], (res, plan(res["status"], res["resources"]))
    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, reqs))
