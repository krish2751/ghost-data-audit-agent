"""Joint assignment of unlinked account DELETE events to cases.

Relations used (all derived from the data, none from labels):
  * exclusivity: each case has one account and each account belongs to one case (propagated like sudoku);
  * claims: accounts already tied to another user by an identifier are removed;
  * timing: the DELETE_RECORD event lies within a window of the case's reported_at;
  * claim consistency: the DELETE result must be a (reported_status, result) pair seen among identifier-linked cases.
"""
from collections import Counter

from data import loader


def learn_bounds(ctx, by_case, pairs, event_type, fallback_min=120, margin=0.1):
    """(lo, hi) minutes of event_time - reported_at, learned from identifier-linked (case, resource) pairs.

    Offsets far from the median (more than 10 median-absolute-deviations) are treated as unrelated events and dropped, then the
    range is padded by `margin` of its width (at least 5 minutes). With too few pairs, falls back to +-fallback_min."""
    from fallback import P
    xs = []
    for cid, rid in pairs:
        for a in ctx.act_by_res.get(rid, []):
            if a["event_type"] == event_type:
                xs.append((P(a["event_time"]) - P(by_case[cid]["reported_at"])).total_seconds() / 60)
    if len(xs) < 10:
        return (-float(fallback_min), float(fallback_min))
    xs.sort()
    med = xs[len(xs) // 2]
    mad = sorted(abs(x - med) for x in xs)[len(xs) // 2] or 1.0
    inl = [x for x in xs if abs(x - med) <= 10 * mad]
    lo, hi = min(inl), max(inl)
    pad = max(5.0, margin * (hi - lo))
    return (lo - pad, hi + pad)


def _mutual_unique(ctx, base, reqs, uid_of, assigned_any, kind_prefix, event_type, target, bounds, min_share, claims):
    """Assign events of one kind (e.g. analytics ANONYMIZE) to cases when event and case pick each other uniquely.

    Candidates for a case: events in its window, unclaimed, not taken, with a learned-compatible (status, result).
    Only cases without such a resource yet take part."""
    from fallback import P
    by_case = {r["case_id"]: r for r in reqs}
    evs = [a for a in ctx.act if a["event_type"] == event_type and a["target_system"] == target]
    pair, tot = Counter(), Counter()
    for cid, rid in assigned_any:
        if rid.startswith(kind_prefix):
            for a in ctx.act_by_res.get(rid, []):
                if a["event_type"] == event_type:
                    pair[(by_case[cid]["reported_status"], a["reported_result"])] += 1; tot[by_case[cid]["reported_status"]] += 1
    compat = {k for k, n in pair.items() if n / tot[k[0]] >= min_share}
    have = {cid for cid, rid in assigned_any if rid.startswith(kind_prefix)}
    taken = {rid for _, rid in assigned_any}
    open_cases = [r for r in reqs if r["case_id"] in uid_of and r["case_id"] not in have]
    def fits(r, a):
        return (a["event_time"] <= r["audit_at"] and bounds[0] <= (P(a["event_time"]) - P(r["reported_at"])).total_seconds() / 60 <= bounds[1]
                and (r["reported_status"], a["reported_result"]) in compat and a["resource_id"] not in taken
                and not (claims.get(a["resource_id"], set()) - {uid_of[r["case_id"]]}))
    out = {}
    for r in open_cases:
        cs = sorted({a["resource_id"] for a in evs if fits(r, a)})
        if len(cs) != 1:
            continue
        owners = [o["case_id"] for o in open_cases if any(fits(o, a) and a["resource_id"] == cs[0] for a in evs)]
        if owners == [r["case_id"]]:
            out[r["case_id"]] = (cs[0], "joint_mutual")
    return out


def compute(ctx, window_min=None, min_share=0.05, hide=frozenset(), base=None, analytics=True):
    """`hide`: case ids whose identifier-linked account is treated as unknown (hold-out testing against evidence-derived
    truth, no labels needed). `base`: precomputed identifier-only solve_all result, to avoid recomputing it."""
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
    user_acc = {uid_of[c]: a for c, a in assigned.items()}
    out = {}
    for cid in list(need):  # same user in several requests: reuse the account already tied to them
        if uid_of[cid] in user_acc:
            out[cid] = (user_acc[uid_of[cid]], "same_user")
            del need[cid]
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

    def cands(r, strict):
        rep = P(r["reported_at"]); uid = uid_of[r["case_id"]]
        found = set()
        for a in dels:
            if a["event_time"] > r["audit_at"] or not bounds[0] <= (P(a["event_time"]) - rep).total_seconds() / 60 <= bounds[1]:
                continue
            if a["resource_id"] in taken or (claims.get(a["resource_id"], set()) - {uid}):
                continue
            if strict and (r["reported_status"], a["reported_result"]) not in compat:
                continue
            found.add(a["resource_id"])
        return sorted(found)

    for strict in (True, False):
        changed = True
        while changed:
            changed = False
            for cid, r in list(need.items()):
                c = cands(r, strict)
                if len(c) == 1:
                    out[cid] = (c[0], "joint_strict" if strict else "joint_relaxed")
                    taken.add(c[0]); del need[cid]; changed = True
    extra = {}
    if analytics:
        known = [(c, a) for c, a in assigned.items()] + [(c, a) for c, (a, _) in out.items()]
        for c, d in base.items():
            for x in d[0]["resources"]:
                known.append((c, x["resource_id"]))
        a_pairs = sorted({(c, r) for c, r in known if r.startswith("analytics")})
        a_bounds = (-float(window_min), float(window_min)) if window_min else learn_bounds(ctx, by_case, a_pairs, "ANONYMIZE_RECORD")
        extra = _mutual_unique(ctx, base, reqs, uid_of, known, "analytics", "ANONYMIZE_RECORD", "analytics_platform", a_bounds, min_share, claims)
    return {"account": out, "analytics": extra}, {"ambiguous": len(need), "assigned": len(out), "analytics": len(extra),
                                                 "bounds": {"account": bounds, "analytics": a_bounds if analytics else None}}
