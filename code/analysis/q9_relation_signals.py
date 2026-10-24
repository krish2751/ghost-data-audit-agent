"""Which pairwise relations separate resources of the same sample case from resources of different cases? (evaluation-only; reads gold)"""
import csv, json, re, sys, itertools
from collections import Counter, defaultdict
sys.path.insert(0, "code"); sys.path.insert(0, "code/analysis")
from datetime import datetime
from fallback import Context, solve_all
from data import loader
from readers.intent_reader import prefetch_intents
P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
ctx = Context(); reqs = loader.requests(sample=True); prefetch_intents(ctx, reqs)
gold = {r["case_id"]: json.loads(r["steps_json"]) for r in csv.DictReader(open(loader.DS / "sample_output.csv"))}
res = solve_all(ctx, reqs)
# 1) breakdown of the misses
miss = Counter(); have_by_case = {}
for cid, (r, steps) in res.items():
    have = {(s["resource_id"], s["operation"]) for s in steps}
    for s in gold[cid]:
        if (s["resource_id"], s["operation"]) not in have: miss[(re.sub(r"_\d+$", "", s["resource_id"]), s["operation"])] += 1
print("== remaining missing steps by (kind, operation):"); [print("  ", k, n) for k, n in miss.most_common()]
print("   total", sum(miss.values()), "| cases with any miss:", sum(1 for cid, (r, st) in res.items() if {(s['resource_id'], s['operation']) for s in gold[cid]} - {(s['resource_id'], s['operation']) for s in st}))
# 2) pairwise relation features among all gold resources
NOISE = {"INDEX_RECORD", "UPDATE_RECORD", "SEND_EMAIL", "REFRESH_CACHE", "CREATE_EXPORT", "LINK_RESOURCE_IDENTITY", "CLASSIFY_REQUEST"}
owner = {}
for cid, steps in gold.items():
    for s in steps: owner[s["resource_id"]] = cid
rids = sorted(owner)
def acts(r): return [a for a in ctx.act_by_res.get(r, []) if a["event_type"] not in NOISE]
def idn(a): return int(a["activity_id"].split("_")[1])
feat = []
for a, b in itertools.combinations(rids, 2):
    A, B = acts(a), acts(b)
    f = {"same": owner[a] == owner[b]}
    if A and B:
        f["dt"] = min(abs((P(x["event_time"]) - P(y["event_time"])).total_seconds()) / 60 for x in A for y in B)
        f["did"] = min(abs(idn(x) - idn(y)) for x in A for y in B)
    oa = {(o.file_id) for o in ctx.ix.by_resource.get(a, [])}; ob = {(o.file_id) for o in ctx.ix.by_resource.get(b, [])}
    f["file"] = bool(oa & ob)
    feat.append(f)
pos = [f for f in feat if f["same"]]; neg = [f for f in feat if not f["same"]]
print(f"\n== pairs: {len(pos)} same-case, {len(neg)} cross-case (resources: {len(rids)})")
def table(name, key, thresholds):
    print(f"-- {name}: precision = same-case share among pairs satisfying the condition")
    for t in thresholds:
        p = sum(1 for f in pos if key(f, t)); n = sum(1 for f in neg if key(f, t))
        print(f"   <= {t:<6} same-case {p:4d} cross-case {n:5d} precision {p/(p+n) if p+n else 0:.2f}  recall {p/len(pos):.2f}")
table("activity time gap (min)", lambda f, t: "dt" in f and f["dt"] <= t, [1, 5, 15, 30, 60, 120, 240])
table("activity id gap", lambda f, t: "did" in f and f["did"] <= t, [1, 2, 3, 5, 8, 12])
p = sum(1 for f in pos if f["file"]); n = sum(1 for f in neg if f["file"])
print(f"-- co-observed in the same evidence file: same-case {p}, cross-case {n}, precision {p/(p+n):.2f}, recall {p/len(pos):.2f}")
