"""Shared constants for the audit pipeline: step operations, resource kinds, and policy actions."""

PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
# (phase, operation, state) in the order the problem statement lists them.
OPERATIONS = [
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
]
OP_INDEX = {op: i for i, (_, op, _) in enumerate(OPERATIONS)}
OP_META = {op: (phase, state) for phase, op, state in OPERATIONS}
STEP_FIELDS = ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
STATUSES = ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")

# resource-id prefix -> (system_id, default data category)
PREFIX_INFO = {
    "account": ("account_service", "USER_PROFILE"),
    "search": ("search_service", "SEARCH_INDEX_ENTRY"),
    "support": ("support_platform", "SUPPORT_MESSAGE"),
    "analytics": ("analytics_platform", "ANALYTICS_PROFILE"),
    "export": ("export_service", "USER_EXPORT"),
    "backup": ("backup_service", "BACKUP_ARCHIVE"),
    "data_flow": ("integration_service", "DATA_FLOW"),
    "audit_record": ("security_service", "SECURITY_AUDIT_LOG"),
    "tombstone": ("identity_service", "ACCOUNT_TOMBSTONE"),
    "legal_hold": ("legal_service", "LEGAL_HOLD_RECORD"),
    "marketing": ("marketing_platform", "MARKETING_PROFILE"),
    "cache": ("cache_service", "CACHE_ENTRY"),
    "email_delivery": ("email_delivery_service", "EMAIL_DELIVERY_LOG"),
}

# category -> policy treatment (mirrors deletion_rules.csv)
TREATMENT = {
    "USER_PROFILE": "DELETE", "SECONDARY_IDENTIFIER": "DELETE", "SEARCH_INDEX_ENTRY": "DELETE",
    "CACHE_ENTRY": "DELETE", "SUPPORT_ATTACHMENT": "DELETE", "USER_EXPORT": "DELETE",
    "MARKETING_PROFILE": "DELETE", "SUPPORT_MESSAGE": "REDACT", "EMAIL_DELIVERY_LOG": "REDACT",
    "ACCOUNT_TOMBSTONE": "REDACT", "ANALYTICS_PROFILE": "ANONYMIZE", "PRODUCT_TELEMETRY": "ANONYMIZE",
    "SECURITY_AUDIT_LOG": "RETAIN", "LEGAL_HOLD_RECORD": "RETAIN", "BACKUP_ARCHIVE": "BLOCK_RESTORE",
    "DATA_FLOW": "DISABLE",
}
