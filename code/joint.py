"""Joint assignment of unlinked account DELETE events to cases.

Relations used (all derived from the data, none from labels):
  * exclusivity: each case has one account and each account belongs to one case (propagated like sudoku);
  * claims: accounts already tied to another user by an identifier are removed;
  * timing: the DELETE_RECORD event lies within a window of the case's reported_at;
  * claim consistency: the DELETE result must be a (reported_status, result) pair seen among identifier-linked cases.
"""
from collections import Counter

from data import loader


def _mutual_unique(ctx, base, reqs, uid_of, assigned_any, kind_prefix, event_type, target, window_min, min_share, claims):
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
        return (a["event_time"] <= r["audit_at"] and abs((P(a["event_time"]) - P(r["reported_at"])).total_seconds()) <= window_min * 60
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


def compute(ctx, window_min=120, min_share=0.05):
    from fallback import P, solve_all
    reqs = loader.requests(sample=True) + loader.requests()
    base = solve_all(ctx, reqs, heuristics=False)
    claims = ctx.claims()
    by_case = {r["case_id"]: r for r in reqs}
    dels = [a for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
    assigned, uid_of, need = {}, {}, {}
    for r in reqs:
        res = base[r["case_id"]][0]
        if res["status"] == "NOT_APPLICABLE" or "uid" not in res:
            continue
        uid_of[r["case_id"]] = res["uid"]
        accs = [d["resource_id"] for d in res["resources"] if d["resource_id"].startswith("account")]
        if accs:
            assigned[r["case_id"]] = accs[0]
        else:
            need[r["case_id"]] = r
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
            if a["event_time"] > r["audit_at"] or abs((P(a["event_time"]) - rep).total_seconds()) > window_min * 60:
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
    if getattr(ctx, "joint_analytics", True):
        known = [(c, a) for c, a in assigned.items()] + [(c, a) for c, (a, _) in out.items()]
        for c, d in base.items():
            for x in d[0]["resources"]:
                known.append((c, x["resource_id"]))
        extra = _mutual_unique(ctx, base, reqs, uid_of, known, "analytics", "ANONYMIZE_RECORD", "analytics_platform", window_min, min_share, claims)
    return {"account": out, "analytics": extra}, {"ambiguous": len(need), "assigned": len(out), "analytics": len(extra)}
