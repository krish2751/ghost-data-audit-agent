"""Observation -> data category and reading (what the observation says about the resource's state)."""
import re

from schema import PREFIX_INFO, TREATMENT
from .evidence_index import prefix_of

EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
IDENT_KEYS = ("email", "phone", "email_hash", "full_name", "name", "owner_email", "owner_phone", "customer_email",
              "requester_email", "requester_name", "requester_phone", "display_name")


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes", "enabled", "y")


def category(o):
    a = o.attrs
    rt = str(a.get("record_type") or "").upper()
    if rt in TREATMENT:
        return rt
    pre = prefix_of(o.resource_id)
    cat = PREFIX_INFO.get(pre, (None, None))[1]
    ev0 = str(a.get("event") or "")
    if ev0.startswith("contact_lookup") or "email_opt_in" in a:
        return "MARKETING_PROFILE"
    if pre == "support":
        ev = str(a.get("event") or "")
        if o.source in ("ticket_attachments", "support_platform.attachments") or "attachment" in ev or o.kind == "pdf" or a.get("storage_class"):
            return "SUPPORT_ATTACHMENT"
        if ev.startswith(("contact_query", "deletion_marker")) or a.get("source") == "legacy_contact_index":
            return "SECONDARY_IDENTIFIER"
    return cat


def has_identifiers(a, keys=IDENT_KEYS):
    return any(a.get(k) not in (None, "", "REDACTED") for k in keys)


def reading(o):
    """FOUND, NOT_FOUND, IDENTIFIABLE, REDACTED, ANONYMIZED, ACTIVE/DISABLED, RESTORABLE/BLOCKED, RETAINED or UNKNOWN."""
    a, cat = o.attrs, category(o)
    res = str(a.get("result") or "").upper()
    if res in ("HIT",):
        res = "FOUND"
    if res in ("MISS",):
        res = "NOT_FOUND"
    if cat == "BACKUP_ARCHIVE":
        if res == "ACTIVE":
            return "RESTORABLE"
        if res == "BLOCKED":
            return "BLOCKED"
        if "restore_allowed" in a:
            return "RESTORABLE" if truthy(a["restore_allowed"]) else "BLOCKED"
        if "eligible" in a or "deletion_block" in a:
            return "BLOCKED" if truthy(a.get("deletion_block")) or not truthy(a.get("eligible", "true")) else "RESTORABLE"
        return "RESTORABLE"
    if cat == "DATA_FLOW":
        if res in ("ACTIVE", "DISABLED"):
            return res
        if "enabled" in a:
            return "ACTIVE" if truthy(a["enabled"]) else "DISABLED"
        return "UNKNOWN"
    if res in ("FOUND", "NOT_FOUND", "IDENTIFIABLE", "REDACTED", "ANONYMIZED"):
        return res
    if cat == "USER_PROFILE":
        if "rows" in a and a["rows"] is not None:
            return "FOUND" if str(a["rows"]) not in ("0", "") else "NOT_FOUND"
        if "profile" in a and "status_code" in a:
            return "NOT_FOUND" if a.get("profile") is None else "FOUND"
        return "FOUND"  # a profile row with no explicit miss marker is present
    if cat == "SUPPORT_MESSAGE":
        ev = str(a.get("event") or "")
        if ev == "message_pii_scan" or a.get("matched_value"):
            return "IDENTIFIABLE"
        mt = str(a.get("message_text") or "")
        if "[redacted]" in mt.lower():
            return "REDACTED"
        if has_identifiers(a, ("requester_email", "requester_name", "requester_phone")) or EMAIL_RX.search(mt):
            return "IDENTIFIABLE"
        if "message_text" in a or "message_excerpt" in a or "requester_email" in a:
            return "REDACTED"
        return "IDENTIFIABLE"
    if cat == "ANALYTICS_PROFILE":
        if str(a.get("direct_identifiers") or "0") not in ("0", "") or a.get("matched_value"):
            return "IDENTIFIABLE"
        if has_identifiers(a, ("email", "phone", "email_hash", "user_id", "customer_reference")):
            return "IDENTIFIABLE"
        return "ANONYMIZED"
    if cat == "ACCOUNT_TOMBSTONE":
        return "IDENTIFIABLE" if has_identifiers(a, ("email", "phone", "email_hash", "name", "full_name")) else "REDACTED"
    if cat in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"):
        return "RETAINED"
    if cat in ("SEARCH_INDEX_ENTRY", "USER_EXPORT", "SUPPORT_ATTACHMENT", "SECONDARY_IDENTIFIER", "MARKETING_PROFILE",
               "CACHE_ENTRY", "EMAIL_DELIVERY_LOG"):
        return "FOUND"
    return "UNKNOWN"


def violation(cat, rd, treatment=None):
    """Policy verdict for a category/reading under a treatment: REMAINING, EXPOSED, FLOW, RESTORE or None."""
    t = treatment or TREATMENT.get(cat)
    if t == "DELETE" and rd in ("FOUND", "IDENTIFIABLE") or (t == "DELETE" and treatment and rd in ("REDACTED", "ANONYMIZED", "RETAINED")):
        return "REMAINING"
    if t in ("REDACT", "ANONYMIZE") and rd == "IDENTIFIABLE":
        return "EXPOSED"
    if t == "DISABLE" and rd == "ACTIVE":
        return "FLOW"
    if t == "BLOCK_RESTORE" and rd == "RESTORABLE":
        return "RESTORE"
    return None
