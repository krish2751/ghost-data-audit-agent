"""Joint assignment of records that carry no identifier (account DELETE events, analytics ANONYMIZE events) to cases.

Relations used (all derived from the data, none from labels):
  * exclusivity: each case has one account and each account belongs to one case (propagated like sudoku);
  * claims: accounts already tied to another user by an identifier are removed;
  * timing: the DELETE_RECORD event lies within a window of the case's reported_at;
  * claim consistency: the DELETE result must be a (reported_status, result) pair seen among identifier-linked cases.
"""
from collections import Counter

from data import loader
from data.evidence_index import prefix_of


MAD_K = 10      # offsets further than MAD_K median-absolute-deviations from the median are unrelated events (see data_findings.md)
PAD_SHARE = 0.1  # learned range padded by this share of its width on each side (see data_findings.md)


REMEDIATION_EVENTS = ("DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE")


def robust_bounds(xs):
    """(lo, hi) of offsets after dropping values more than MAD_K median absolute deviations from the median; None if empty."""
    if not xs:
        return None
    xs = sorted(xs)
    med = xs[len(xs) // 2]
    mad = sorted(abs(x - med) for x in xs)[len(xs) // 2] or 1.0
    inl = [x for x in xs if abs(x - med) <= MAD_K * mad]
    lo, hi = min(inl), max(inl)
    pad = PAD_SHARE * (hi - lo)
    return (lo - pad, hi + pad)


def learn_bounds(ctx, by_case, pairs, event_type):
    """(lo, hi) minutes of event_time - reported_at, learned from identifier-linked (case, resource) pairs; None without pairs."""
    from fallback import P
    xs = []
    for cid, rid in pairs:
        for a in ctx.act_by_res.get(rid, []):
            if a["event_type"] == event_type:
                xs.append((P(a["event_time"]) - P(by_case[cid]["reported_at"])).total_seconds() / 60)
    return robust_bounds(xs)


def outcome_model(ctx, base, by_case, min_share, skip_kind=None):
    """Per outcome ('clean' / 'violation' at audit_at): offset bounds and compatible (reported_status, result) pairs of
    remediation events, learned from identifier-linked non-account records. Timing follows the outcome, not the kind
    (data_findings.md), so records that can never carry an identifier (anonymized analytics) borrow it from other kinds."""
    from fallback import P
    xs, pair, tot = {"clean": [], "violation": []}, Counter(), Counter()
    for c, (res, _) in base.items():
        for d in res["resources"]:
            kind = prefix_of(d["resource_id"])
            if kind == "account" or kind == skip_kind:
                continue
            o = "violation" if d["violation"] else "clean"
            st = by_case[c]["reported_status"]
            for a in ctx.act_by_res.get(d["resource_id"], []):
                if a["event_type"] in REMEDIATION_EVENTS:
                    xs[o].append((P(a["event_time"]) - P(by_case[c]["reported_at"])).total_seconds() / 60)
                    pair[(o, st, a["reported_result"])] += 1
                    tot[(o, st)] += 1
    return {o: {"bounds": robust_bounds(xs[o]),
                "compat": {(st, rs) for (oo, st, rs), n in pair.items() if oo == o and n / tot[(o, st)] >= min_share}} for o in xs}


def outcome_of(ctx, rid, audit_at):
    """'clean' or 'violation' from the record's own observations captured by audit_at; None without one."""
    from fallback import _decide
    d = _decide(ctx, rid, "", audit_at)
    return None if not d else ("violation" if d["violation"] else "clean")


def assign_unlinked(ctx, reqs, uid_of, known, kind, event_type, model, claims):
    """Assign unlinked `kind` records to cases when record and case pick each other uniquely.

    A record's event fits a case when the record's own outcome at the case's audit_at selects a learned window and
    status/result set that the event satisfies, the record is not taken and no other user claims it. Only cases without a
    `kind` record yet take part."""
    from fallback import P
    evs = [a for a in ctx.act if a["event_type"] == event_type and prefix_of(a["resource_id"]) == kind]
    have = {cid for cid, rid in known if prefix_of(rid) == kind}
    taken = {rid for _, rid in known}
    open_cases = [r for r in reqs if r["case_id"] in uid_of and r["case_id"] not in have]
    outcome = {}

    def fits(r, a):
        if a["event_time"] > r["audit_at"] or a["resource_id"] in taken or (claims.get(a["resource_id"], set()) - {uid_of[r["case_id"]]}):
            return False
        key = (a["resource_id"], r["audit_at"])
        if key not in outcome:
            outcome[key] = outcome_of(ctx, a["resource_id"], r["audit_at"])
        m = model.get(outcome[key])
        if not m or not m["bounds"]:
            return False
        off = (P(a["event_time"]) - P(r["reported_at"])).total_seconds() / 60
        return m["bounds"][0] <= off <= m["bounds"][1] and (r["reported_status"], a["reported_result"]) in m["compat"]
    out = {}
    for r in open_cases:
        cs = sorted({a["resource_id"] for a in evs if fits(r, a)})
        if len(cs) != 1:
            continue
        owners = [o["case_id"] for o in open_cases if any(fits(o, a) and a["resource_id"] == cs[0] for a in evs)]
        if owners == [r["case_id"]]:
            out[r["case_id"]] = (cs[0], "joint_mutual")
    return out


def evidenced(ctx, rid, audit_at):
    """True when the record's own observation captured by audit_at shows a compliant state, so a COMPLETE case can cite it
    (problem statement: a COMPLETE case's verification must cite the evidence proving the compliant state)."""
    from fallback import _decide
    d = _decide(ctx, rid, "", audit_at)
    return bool(d and d["verify_evidence"] and not d["violation"])


def compute(ctx, window_min=None, min_share=0.05, hide=frozenset(), base=None, analytics=True, complete_evidence="tiebreak"):
    """`hide`: case ids whose identifier-linked account is treated as unknown (hold-out testing against evidence-derived
    truth, no labels needed). `base`: precomputed identifier-only solve_all result, to avoid recomputing it.
    `complete_evidence`: 'tiebreak' (after the plain passes, a case that is COMPLETE without the account only keeps
    candidates it can cite, see `evidenced`), 'hard' (that filter in every pass) or None (off)."""
    from fallback import P, solve_all
    reqs = loader.requests(sample=True) + loader.requests()
    base = base or solve_all(ctx, reqs, heuristics=False)
    claims = ctx.claims()
    by_case = {r["case_id"]: r for r in reqs}
    if hide:  # the hidden accounts must not stay claimed by their own user either
        claims = {k: set(v) for k, v in claims.items()}
        for cid in hide:
            res = base[cid][0]
            for d in res["resources"]:
                if d["resource_id"].startswith("account") and "uid" in res:
                    claims.get(d["resource_id"], set()).discard(res["uid"])
    dels = [a for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
    assigned, uid_of, need = {}, {}, {}
    for r in reqs:
        res = base[r["case_id"]][0]
        if res["status"] == "NOT_APPLICABLE" or "uid" not in res:
            continue
        uid_of[r["case_id"]] = res["uid"]
        accs = [d["resource_id"] for d in res["resources"] if d["resource_id"].startswith("account")]
        if accs and r["case_id"] not in hide:
            assigned[r["case_id"]] = accs[0]
        else:
            need[r["case_id"]] = r
    bounds = (-float(window_min), float(window_min)) if window_min else learn_bounds(ctx, by_case, assigned.items(), "DELETE_RECORD")
    out = {}
    pair = Counter()
    for cid, acc in assigned.items():
        ev = [a for a in ctx.act_by_res.get(acc, []) if a["event_type"] == "DELETE_RECORD"]
        if ev:
            pair[(by_case[cid]["reported_status"], ev[0]["reported_result"])] += 1
    tot = Counter()
    for (st, _), n in pair.items():
        tot[st] += n
    compat = {k for k, n in pair.items() if n / tot[k[0]] >= min_share}
    taken = set(assigned.values()) | {a for a, _ in out.values()}

    def cands(r, strict, need_ev=False):
        rep = P(r["reported_at"]); uid = uid_of[r["case_id"]]
        found = set()
        if not bounds:
            return []
        for a in dels:
            if a["event_time"] > r["audit_at"] or not bounds[0] <= (P(a["event_time"]) - rep).total_seconds() / 60 <= bounds[1]:
                continue
            if a["resource_id"] in taken or (claims.get(a["resource_id"], set()) - {uid}):
                continue
            if strict and (r["reported_status"], a["reported_result"]) not in compat:
                continue
            if need_ev and base[r["case_id"]][0]["status"] == "COMPLETE" and not evidenced(ctx, a["resource_id"], r["audit_at"]):
                continue
            found.add(a["resource_id"])
        return sorted(found)

    passes = {"hard": [(True, True), (False, True)], "tiebreak": [(True, False), (False, False), (True, True), (False, True)],
              None: [(True, False), (False, False)]}[complete_evidence]
    for strict, need_ev in passes:
        changed = True
        while changed:
            changed = False
            for cid, r in list(need.items()):
                c = cands(r, strict, need_ev)
                if len(c) == 1:
                    out[cid] = (c[0], ("joint_strict" if strict else "joint_relaxed") + ("_evidence" if need_ev else ""))
                    taken.add(c[0]); del need[cid]; changed = True
    extra, model = {}, None
    if analytics:
        known = [(c, a) for c, a in assigned.items()] + [(c, a) for c, (a, _) in out.items()]
        for c, d in base.items():
            for x in d[0]["resources"]:
                known.append((c, x["resource_id"]))
        model = outcome_model(ctx, base, by_case, min_share)
        extra = assign_unlinked(ctx, reqs, uid_of, known, "analytics", "ANONYMIZE_RECORD", model, claims)
    return {"account": out, "analytics": extra}, {"ambiguous": len(need), "assigned": len(out), "analytics": len(extra),
                                                 "bounds": {"account": bounds, "outcome_model": model}}
