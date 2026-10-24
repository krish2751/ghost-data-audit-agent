"""How requests relate to identities: current vs historical request email, ambiguity, users with several emails."""
from collections import Counter
from common import rows, identities, email_to_user, sample_cases

users, hist = identities()
e2u = email_to_user(hist)
cur = {u["email"].lower(): uid for uid, u in users.items()}

def classify(reqs, label):
    c = Counter()
    ex = {}
    for r in reqs:
        e = r["email"].lower()
        us = e2u.get(e, set())
        if not us:
            k = "email unknown to identity data"
        elif len(us) > 1:
            k = "email maps to >1 user"
        elif e in cur:
            k = "current email"
        else:
            k = "historical email"
        c[k] += 1
        ex.setdefault(k, r["case_id"])
    print(f"{label}: n={len(reqs)}")
    for k, n in c.most_common():
        print(f"   {k:34s} {n:4d}  e.g. {ex[k]}")

classify(rows("sample_deletion_requests.csv"), "samples")
classify(rows("deletion_requests.csv"), "evaluation")
print("users with >1 distinct email over time:", sum(1 for h in hist.values() if len(h["emails"]) > 1), "of", len(hist))
print("emails shared by >1 user:", sum(1 for s in e2u.values() if len(s) > 1))

# case_10 detail
req, gold = sample_cases()
r = next(x for x in rows("sample_deletion_requests.csv") if x["case_id"] == "case_10")
uid = next(iter(e2u[r["email"].lower()]))
print("\ncase_10 user", uid, "current:", users[uid]["email"], "all emails:", sorted(hist[uid]["emails"]))
for a in hist[uid]["audit"]:
    print("  audit", a["audit_id"], a["field_name"], a["old_value"], "->", a["new_value"], a["event_time"])
print("gold steps for case_10:", [(s["system_id"], s["resource_id"], s["operation"], s["evidence_id"]) for s in gold["case_10"][1]][:6])
