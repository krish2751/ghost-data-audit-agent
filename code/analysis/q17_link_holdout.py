"""Blind, label-free hold-out of the link reader.

Truth is the account an identifier ties to the user (never sample_output.csv). For each fold the truth is hidden, the joint
rules run, and the cases they cannot resolve become reader tasks. Dossiers use opaque labels (no resource ids, no case ids) and
a shuffled order so the answerer cannot lean on remembered answers. Candidates already taken by other cases are removed.

    q17_link_holdout.py build OUTDIR   -> OUTDIR/dossiers.txt (printable) and OUTDIR/truth.json (do not print)
    q17_link_holdout.py score OUTDIR ANSWERS.json   ANSWERS: {"T07": {"chosen": "C3" | null, "confidence": "high|medium|low"}, ...}
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joint
from data import loader
from fallback import Context, P, solve_all
from readers.link_reader import NOISE, POOL_WINDOW_MIN

K = 5


def mins(a, b):
    return round((P(a) - P(b)).total_seconds() / 60)


def build(outdir):
    ctx = Context(intent_mode="regex", conditions_mode="default")
    reqs = loader.requests(sample=True) + loader.requests()
    base = solve_all(ctx, reqs, heuristics=False)
    by_case = {r["case_id"]: r for r in reqs}
    del_res = {a["resource_id"] for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"}
    truth, uid_of = {}, {}
    for r in reqs:
        res = base[r["case_id"]][0]
        if "uid" in res:
            uid_of[r["case_id"]] = res["uid"]
            accs = [d["resource_id"] for d in res["resources"] if d["resource_id"].startswith("account") and d["resource_id"] in del_res]
            if len(accs) == 1:
                truth[r["case_id"]] = accs[0]
    users = sorted({uid_of[c] for c in truth})
    fold_of = {u: i % K for i, u in enumerate(users)}
    claims = ctx.claims()
    tasks = []
    for k in range(K):
        hide = frozenset(c for c in truth if fold_of[uid_of[c]] == k)
        got, _ = joint.compute(ctx, hide=hide, base=base, analytics=False)
        out = got["account"]
        taken = {truth[c] for c in truth if c not in hide} | {a for a, _ in out.values()}
        taken |= {d["resource_id"] for c, (res, _) in base.items() if c not in hide for d in res["resources"] if d["resource_id"].startswith("account")}
        for c in sorted(hide):
            if c in out:
                continue
            r, uid = by_case[c], uid_of[c]
            cand = {}
            for a in ctx.act:
                rid = a["resource_id"]
                if (a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service" and a["event_time"] <= r["audit_at"]
                        and abs(mins(a["event_time"], r["reported_at"])) <= POOL_WINDOW_MIN and rid not in taken
                        and not (claims.get(rid, set()) - {uid} - ({uid} if False else set()))):
                    cand.setdefault(rid, []).append(a)
            # own hidden account is in cand because claims only name this user; other users' claims removed it
            linked = []
            for d in base[c][0]["resources"]:
                if d["resource_id"].startswith("account"):
                    continue
                evs = [a for a in ctx.act_by_res.get(d["resource_id"], []) if a["event_type"] not in NOISE and a["event_time"] <= r["audit_at"]]
                if evs:
                    linked.append((d["resource_id"], evs))
            tasks.append((c, r, cand, linked))
    random.Random(7).shuffle(tasks)
    lines, tr = [], {}
    for i, (c, r, cand, linked) in enumerate(tasks, 1):
        tid = f"T{i:02d}"
        order = sorted(cand, key=lambda x: random.Random(f"{tid}{x}").random())
        labels = {rid: f"C{j}" for j, rid in enumerate(order, 1)}
        tr[tid] = {"case": c, "truth": truth[c], "labels": labels, "in_pool": truth[c] in cand}
        lines.append(f"=== {tid}  reported_status={r['reported_status']}  audit is {mins(r['audit_at'], r['reported_at'])} min after the workflow report")
        for j, (rid, evs) in enumerate(linked, 1):
            kind = rid.split("_")[0]
            lines.append(f"  already-linked L{j} ({kind}): " + "; ".join(f"{a['event_type']}/{a['reported_result']} @{mins(a['event_time'], r['reported_at']):+d}m id={a['activity_id'].split('_')[-1]}" for a in sorted(evs, key=lambda a: a['event_time'])))
        for rid in order:
            lines.append(f"  candidate {labels[rid]} (account): " + "; ".join(f"{a['event_type']}/{a['reported_result']} @{mins(a['event_time'], r['reported_at']):+d}m id={a['activity_id'].split('_')[-1]}" for a in sorted(cand[rid], key=lambda a: a['event_time'])))
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    (out / "dossiers.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "truth.json").write_text(json.dumps(tr, indent=1), encoding="utf-8")
    print(f"{len(tasks)} reader tasks; truth in pool for {sum(v['in_pool'] for v in tr.values())}; "
          f"candidates per task: {Counter(len(v['labels']) for v in tr.values())}")


def score(outdir, answers):
    tr = json.loads((Path(outdir) / "truth.json").read_text())
    ans = json.loads(Path(answers).read_text())
    res = Counter()
    for tid, t in tr.items():
        a = ans.get(tid, {})
        ch = a.get("chosen")
        inv = {v: k for k, v in t["labels"].items()}
        if ch is None:
            res["abstained"] += 1
        elif inv.get(ch) == t["truth"]:
            res["correct"] += 1
        else:
            res["wrong"] += 1
    n = len(tr)
    print(dict(res), f"of {n}; precision of answers given: {res['correct'] / max(1, res['correct'] + res['wrong']):.1%}")
    print("chance level for a random pick among candidates:", f"{sum(1 / len(t['labels']) for t in tr.values() if t['labels']) / n:.1%}")


if __name__ == "__main__":
    build(sys.argv[2]) if sys.argv[1] == "build" else score(sys.argv[2], sys.argv[3])
