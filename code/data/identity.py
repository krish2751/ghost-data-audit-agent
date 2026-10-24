"""Identity resolution: email/user_id -> subject identifiers as of audit_at."""
import hashlib

from .loader import read_csv


class IdentityStore:
    def __init__(self):
        self.users = {u["user_id"]: u for u in read_csv("user_identities.csv")}
        self.audit = {}
        for a in read_csv("user_audit_log.csv"):
            self.audit.setdefault(a["user_id"], []).append(a)
        for rows in self.audit.values():
            rows.sort(key=lambda a: a["event_time"])
        self.by_email = {}
        for uid in self.users:
            for e in self._all_emails(uid):
                self.by_email.setdefault(e, set()).add(uid)

    def _all_emails(self, uid):
        out = {self.users[uid]["email"].lower()}
        for a in self.audit.get(uid, []):
            if a["field_name"] == "email":
                out.update(v.lower() for v in (a["old_value"], a["new_value"]) if v)
        return out

    def resolve_email(self, email):
        """user_ids whose current or historical email equals `email` (any date)."""
        return sorted(self.by_email.get(email.strip().lower(), set()))

    def identifiers(self, uid, audit_at):
        """Identifiers for the user as of audit_at: audit-log changes after audit_at are not applied."""
        cur = self.users[uid]
        vals = {"email": {cur["email"].lower()}, "phone": {cur["phone"]}, "email_hash": {cur["email_hash"]},
                "name": {cur["name"]}, "user_id": {uid}}
        for a in reversed(self.audit.get(uid, [])):
            f = a["field_name"]
            norm = (lambda v: v.lower()) if f == "email" else (lambda v: v)
            if a["event_time"] <= audit_at:
                vals[f].update(norm(v) for v in (a["old_value"], a["new_value"]) if v)
            else:  # change happened after the audit: the subject held the old value at audit_at
                vals[f].discard(norm(a["new_value"]))
                if a["old_value"]:
                    vals[f].add(norm(a["old_value"]))
        return vals

    def tokens(self, uid, audit_at):
        t = set()
        for f, vs in self.identifiers(uid, audit_at).items():
            if f != "name":
                t.update(v.lower() for v in vs if v)
        return t


def hash_email(email):
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
