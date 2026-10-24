# Data overview

Survey of `dataset/system_activity.csv` and `dataset/evidence/`, produced by `code/analysis/survey_activity.py` and `code/analysis/survey_evidence.py` (re-run them to regenerate the numbers). This is description only; no solver rules are proposed here. Items marked **(hypothesis)** are readings of the text that have not been checked against the sample answers.

## 1. system_activity.csv

4,011 rows, 2026-01-04 to 2026-10-01. Columns: `activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details`.

Two general facts:

- **No row names a user.** Each row has only a `resource_id` (`account_N`, `search_N`, `analytics_N`, `support_N`, `email_delivery_N`, `cache_N`, `audit_record_N`, `export_N`, `data_flow_N`, `backup_N`, `tombstone_N`, `legal_hold_N`). The only rows that tie a resource to a person are the 12 `LINK_RESOURCE_IDENTITY` rows. Everything else has to be tied to a user through the evidence files.
- **`reported_result` (SUCCESS / FAILED / PARTIAL) is a claim.** The details text often only says that a worker *submitted* or *received a result*, which is not a readback of the resulting state.

### Event types

| event_type | rows | source -> target | results (S/F/P) | details pattern (ids as N) |
|---|---|---|---|---|
| DELETE_RECORD | 890 | deletion_worker -> account_service 539, search_service 289, export_service 32, support_platform 29, analytics_platform 1 | 302 / 368 / 220 | "Deletion worker submitted primary profile account_N to account_service." (532); "...received the final result for search_N / export_N / support_N from <service>." (347); "...reported the requested operation as completed. Target resource: account_N." (6) |
| UPDATE_RECORD | 672 | profile_service -> account_service 440; support_platform -> search_service 232 | 587 / 53 / 32 | "Profile preference update processed account_N."; "Support-case index update processed support_N." |
| SYNC_RECORD | 447 | account_service -> analytics_platform 360; -> account_replication_cluster 55; -> account_failover_replica 1; integration_service -> search_service 31 | 381 / 20 / 46 | "Customer profile synchronization processed analytics_N."; "Replication worker reported its final checkpoint for account_N." (and one "...checkpoint. Target resource: account_N."); "Active connector repopulated downstream resource search_N." (31) |
| INDEX_RECORD | 400 | account_service -> search_service | 348 / 32 / 20 | "Customer search-index refresh processed search_N." |
| SEND_EMAIL | 368 | notification_service -> email_delivery_service | 333 / 21 / 14 | "Transactional email delivery processed email_delivery_N." |
| REFRESH_CACHE | 284 | account_service -> cache_service | 246 / 22 / 16 | "Profile cache refresh processed cache_N." |
| RETAIN_RECORD | 206 | security_service -> archive_service 196; deletion_worker -> legal_service 10 | 185 / 15 / 6 | "Security-event archival processed audit_record_N."; "Policy action completed for legal_hold_N." |
| ANONYMIZE_RECORD | 204 | deletion_worker -> analytics_platform | 132 / 64 / 8 | "Policy action completed for analytics_N." (125); "...received the final result for analytics_N from analytics_platform." (78); one "...reported the requested operation as completed. Target resource: analytics_N." |
| REDACT_RECORD | 173 | deletion_worker -> support_platform 163; -> identity_service 10 | 47 / 117 / 9 | "...received the final result for support_N / tombstone_N from <service>."; "Policy action completed for support_N / tombstone_N." |
| CREATE_EXPORT | 155 | export_service -> object_store | 141 / 9 / 5 | "Scheduled account export processed export_N." |
| CHECK_DATA_FLOW | 89 | deletion_worker -> integration_service | 89 / 0 / 0 | "Connector status check confirmed that data flow data_flow_N remains enabled." |
| DISABLE_DATA_FLOW | 36 | deletion_worker -> integration_service | 36 / 0 / 0 | "Policy action completed for data_flow_N." |
| BLOCK_RESTORE | 36 | deletion_worker -> backup_service | 36 / 0 / 0 | "Policy action completed for backup_N." |
| CHECK_RESTORE_ACCESS | 28 | deletion_worker -> backup_service | 28 / 0 / 0 | "Restore-access check confirmed that archive backup_N can still be restored." |
| LINK_RESOURCE_IDENTITY | 12 | data_catalog -> export 2, account 1, search 1, integration 1, analytics 1, support 1, ... | 12 / 0 / 0 | "Data catalog linked <resource> (<resource>) to <email> and user_N." (12 distinct rows) |
| CLASSIFY_REQUEST | 10 | privacy_intake -> privacy_case_management | 10 / 0 / 0 | "Privacy intake classified request for account_N as non-deletion; no destructive action was authorized." |
| RESTORE_BACKUP | 1 | backup_service -> search_service | 1 / 0 / 0 | "Restore job repopulated downstream resource search_N." |

### What each type means and how it could matter

**Claims about deletion or treatment (verify against evidence, never accept as proof):**
`DELETE_RECORD`, `ANONYMIZE_RECORD`, `REDACT_RECORD`, `RETAIN_RECORD`, `DISABLE_DATA_FLOW`, `BLOCK_RESTORE`. Each says a worker attempted or reported an action. The results are noisy: 368 of 890 deletes and 117 of 173 redactions are FAILED, and many "SUCCESS" rows carry wording like "submitted" or "policy action completed" that does not say what the target now looks like. `DISABLE_DATA_FLOW` and `BLOCK_RESTORE` are 100% SUCCESS, which makes them the least informative results in the file. The evidence (readbacks, snapshots) is what shows whether the state actually changed.

**Background activity that creates or refreshes copies (ordinary traffic, but it matters when it happens after a deletion):**
`INDEX_RECORD` (search documents), `REFRESH_CACHE` (cache entries), `SEND_EMAIL` (delivery logs that contain an address), `CREATE_EXPORT` (export files), `UPDATE_RECORD`, and the `SYNC_RECORD` rows into analytics or replicas. Most of this is probably unrelated noise from other people; it is evidence of a copy only when the resource can be tied to the subject, and a later event could re-create something removed earlier (hypothesis).

**Risk signals (something can bring data back):**
- `CHECK_DATA_FLOW` ("remains enabled", 89 rows): an active connector. Whether it is still active at `audit_at` depends on whether a later `DISABLE_DATA_FLOW` exists and whether evidence agrees.
- `SYNC_RECORD` from `integration_service` ("Active connector repopulated downstream resource search_N", 31 rows): the connector actually re-created a search record. This is the closest thing to proof that a flow recreates data.
- `CHECK_RESTORE_ACCESS` ("can still be restored", 28 rows): a backup that is restorable, i.e. a restore risk until `BLOCK_RESTORE` is established.
- `SYNC_RECORD` to `account_replication_cluster` / `account_failover_replica` (56 rows): data is copied to replicas, which is where "deleted from primary but still on replica" can appear.

**Rows that link a resource to a user:**
Only `LINK_RESOURCE_IDENTITY` (12 rows; resource, email and `user_N` in the details). Everything else needs evidence content (emails, `customer_reference`/`user_id`, hashes) to be tied to a subject.

**Rows that bear on whether deletion was requested:**
`CLASSIFY_REQUEST` (10 rows, all "non-deletion", all about `account_N` resources). They are only a corroborating signal at most; whether they map to any request in `deletion_requests.csv` has not been joined yet.

**Unusual:**
- `RESTORE_BACKUP` (a single row, 2026-08-22): `backup_9287` "repopulated downstream resource `search_4882`". It is the only explicit case of a restore job bringing back deleted data, and the only restore in the file.
- The "...reported the requested operation as completed. Target resource: X." wording and "final checkpoint. Target resource: X." appear on only 8 rows in total, on low-numbered ids such as `account_001`, `account_005`, `analytics_901`. Every other row uses a different phrasing, so these look like a separate group generated differently (hypothesis; worth checking against the sample cases).
- Resource prefixes `cache_` and `email_delivery_` occur many times in the activity stream but, in the text evidence (SQL, JSON, logs, TXT), they never appear. `CACHE_ENTRY` and `EMAIL_DELIVERY_LOG` rules exist in `deletion_rules.csv`, so either the evidence for them is only in the images/PDFs, or these resources are noise that never becomes part of an answer. Unresolved.
- `tombstone_` and `legal_hold_` ids appear in SQL/JSON/log evidence but there are only 10 activity rows for each kind.

## 2. Evidence files (`evidence_files.csv`: 94 files)

Manifest: `file_id, file_path, origin, captured_at`; captured 2026-01-29 to 2026-10-01. Every manifest path exists on disk and every file on disk is in the manifest. By type: 24 SQL, 28 JSON, 26 logs, 11 PNG, 4 PDF, 1 TXT. The manifest does not say which person a file concerns.

### SQL (24 files, 7 schemas, all execute cleanly in SQLite)

Each begins with comment lines: "point-in-time database snapshot", dialect, `Captured at`, `Database topology` (e.g. `read_replica`) and "Compare the primary and any replica tables for replication drift."

- **Replica families (11 files: 5 read, 3 regional, 2 reporting, 1 failover):** `customer_data_primary` plus one or more replica tables (`customer_data_read_replica`, `..._replica_ap_south`, `..._replica_eu_west`, `..._reporting_replica`, `..._failover_replica`). Columns: `resource_id, origin_system, collection_name, record_json, updated_at`. `record_json` holds the full record for collections such as `customer_analytics_reports`, `customer_search_documents`, `support_conversations`, `connector_configurations`, `backup_catalog`, `security_audit_events`. They show whether a record exists in the primary but also (or only) in a replica, which is the replication-drift pattern.
- **Account failover capture (1 file, evidence_54):** `customer_profiles_primary` and `customer_profiles_failover_replica` with `user_id, full_name, email, phone, account_status` - a profile can be gone from primary yet still present on the failover (4 rows vs 3 in this file).
- **Search capture (1 file, evidence_57):** `search_documents_primary(resource_id, display_name, email, source_resource_id, indexed_at)`.
- **Inventory snapshots (11 files):** one table per category (`customer_profiles`, `customer_search_documents`, `customer_analytics_profiles`, `customer_exports`, `support_records`, `backup_restore_entries` with `restore_allowed`, `connector_subscriptions` with `enabled`, `security_audit_records` with `retention_until`) plus `snapshot_scope(origin_system, captured_at)`, a per-service capture time. Emails appear in odd case (e.g. `H.LIM96@GMAIL.COM`).

What SQL tells us: existence of a row for a given resource at a snapshot time, identifiers still present in it, `restore_allowed`, `enabled`, `account_status`, `retention_until`. Per-service capture times in `snapshot_scope` may differ from the file's overall capture time.

### JSON (28 files)

- **Snapshot bundles (12 files, `records_assurance_snapshot_bundle`):** `snapshots[]` with `captured_at`, `data_store`, `collection`, `records`. Collections are `customer_profiles`, `customer_search_documents`, `customer_analytics_reports`, `backup_catalog`, `customer_export_jobs`, `connector_configurations`, `security_audit_events`, `support_conversations`. Each snapshot has its own `captured_at`.
- **Lookup ledgers (3 files: `connector_configurations`, `customer_export_manifest`, `security_audit_ledger`; the handover TXT below has the same shape):** rows of `recorded_at, system, resource_id, record_type, result, subject_reference`, where `record_type` is a policy category (`USER_PROFILE`, `SEARCH_INDEX_ENTRY`, `SECURITY_AUDIT_LOG`, `SUPPORT_MESSAGE`, `ANALYTICS_PROFILE`, `DATA_FLOW`, ...) and `result` is a readback verdict (`FOUND`, `NOT_FOUND`, `IDENTIFIABLE`, `ANONYMIZED`, `ACTIVE`, ...). `subject_reference` is an email here. These are explicit state statements.
- **Service resource exports (11 files, `service_resource_export_*`):** `service_exports` per service - `account_service.profile_lookups` (profile or null, `status_code` 404), `analytics_platform.profiles`, `backup_service.restore_entries` (`restore_allowed`), `export_service.exports`, `integration_service.connectors` (`enabled`), `search_service.index_queries`, `security_service.audit_records`, `support_platform.tickets`. Fields are nulled when redacted, so "identifiers still present" can be read from non-null fields.
- **Single-collection files (2):** `customer_analytics_report_20260907.json`, `customer_export_jobs_20260914.json`.

### TXT (1 file)

`customer_account_handover_20261001.txt`: a shift handover list of `timestamp | system | resource | category | result | email` lines (e.g. `NOT_FOUND`). Same shape as the lookup ledgers.

### Logs (26 files)

- **Platform logs from `central_observability_export` (12 files):** several syntaxes (key=value, JSON per line, syslog, bracketed, pipe-separated, cloud-runtime). Mostly routine DEBUG/INFO lines from many services with many distinct line patterns; the useful lines are probably a small share (hypothesis).
- **Service readback logs (`resource_lookup_trace_*`, 11 files):** paired `*_started` / `*_completed` events per resource, e.g. `profile_lookup_completed resource_id=account_N rows=0 http_status=404`, `connector_config_read_*`, `index_query_*`, `audit_record_read_*`, `analytics_profile_read_*`. `rows=` and `http_status` give the state; `lookup_key` can be a `user_N` or an email.
- **Others:** `search_index_diagnostic`, `notification_delivery`, `support_replica` (`contact_query_*` events with `lookup_key=<email>` and a legacy contact index), each a different dialect.

### PDF (4 files) - ordinary business documents with no verdict

- `account_history_report_20260718.pdf`: customer statement with name, `user_N`, email, order details.
- `legal_retention_register_20260529.pdf`: disputed-orders/tax register listing `ORD-... | user_NN | ... | Retain until <date>` rows.
- `security_retention_extract.pdf`: signed compliance journal extract.
- `delivery_correction_attachment.pdf`: delivery-address correction request referencing `support_N`.

Extractable with pypdf (text length 600-1000 characters each). They tie people to retention periods, support attachments and account facts.

### PNG (11 files, not read yet)

From names and manifest origins only: `account_admin_console` (account/profile screen), `search_index_inspector`, `connector_management_console` (data-flow state), `analytics_profile_view`, `customer_export_console`, `support_ticket_console`, `backup_restore_console` (restore state), `security_audit_explorer`, `deleted_account_reference` (identity_service, likely the tombstone), `object_storage_browser`, `marketing_profile_console` (the only PNG with no date in its name; captured 2026-09-16). Each likely shows one system's record at a point in time.

### Coverage observations

- Every category in `deletion_rules.csv` has a likely source except `CACHE_ENTRY` and `EMAIL_DELIVERY_LOG`, which were not found in the SQL/JSON/log/TXT evidence (see Unusual above); `MARKETING_PROFILE` and `ACCOUNT_TOMBSTONE` appear to come from PNGs, JSON or SQL (tombstone ids appear in JSON and SQL).
- Evidence has different capture times, and each record may carry its own timestamp (`updated_at`, `observed_at`, `recorded_at`, per-snapshot `captured_at`) besides the file's `captured_at`. Which of these defines "available at `audit_at`" is an open question.
- Identifiers differ by source: emails (sometimes upper-cased or a historical address), `user_N` references, `customer_reference`, hashes, or none at all, so evidence matching to a user will need all of them.
