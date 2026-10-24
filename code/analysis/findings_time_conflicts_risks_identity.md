# Findings: time, conflicts, risks, identity (from the 32 samples)

All evidence here comes from the 32 sample answers, so every statement is "observed in the samples", not a proven rule. Scripts: `q1_time_ids.py`, `q2_files_per_case.py`, `q3_flows_backups.py`, `q4_identifier_links.py`, `q4b_resource_links.py`, `q4c_time_link.py`, `q1b_inner_times_drift.py`, `q_hash_prefix_lowid.py`.

## 1. Time: file capture vs record timestamp

- Every cited file has `captured_at` <= `audit_at`; equality is used (cases 11, 13, 14, 16, 31, 32 cite files captured exactly at `audit_at`). Lead times range from 0 to about 6 days (case_05: capture 09-02, audit 09-08).
- Files captured after `audit_at` that mention the subject exist and are never cited. Example: evidence_02 (captured 09-17) holds 2-6 of the resources of cases 21 and 23-30, and evidence_06 (09-18) holds all 3 resources of case_09. Because they come after `audit_at`, they must be ignored.
- Inside cited files, observation timestamps (`updated_at`, `observed_at`, `recorded_at`, snapshot `captured_at`) are all <= `audit_at`. The only later timestamps are future-dated fields (`retention_until` 2031-2034, an export `expires_at`), which are attributes, not observations.
- So in the samples the file's `captured_at` decides, and record timestamps never contradicted it. Not tested: a file captured before `audit_at` that contains a record updated after it (none in the cited files; the 518 real cases might have one).

## 2. Conflicts between sources

- In the samples there is almost never a competing pre-audit source: for each case exactly one file (two in case_04) captured before `audit_at` mentions the subject's resources. Other hits are either after `audit_at` or are `evidence_27` (the legal register PDF, identity hits only, no resources) and `evidence_67`.
- Conflicts that do appear are of other kinds:
  - **Claim vs evidence:** the activity stream says things like DELETE SUCCESS, but evidence shows the record. Example: case_05 `account_005` has a DELETE_RECORD SUCCESS claim and a "reported COMPLETE" status, yet the failover replica still holds it, and gold says INCOMPLETE.
  - **Drift between copies in one file:** case_16 `account_994` exists only in the read replica, not in the primary, and is a finding. case_22 `analytics_4440` and `search_8911` are in both. So a copy in any replica counts as remaining.
- Absence is proven by a covering snapshot not containing the resource: case_01/02/04 `account_00N` appear in no table of evidence_54 and are verified ABSENT citing that file; case_31 `account_4857` appears in no evidence file at all.
- Not answerable from the samples: which source wins when two pre-audit sources disagree about the same resource. A rule would be a guess; the full dataset could be searched for such pairs.

## 3. What makes a flow or backup a risk (cases 9, 11, 14, 15, 17, 18, 20, 26-30)

| situation at `audit_at` | activity before audit | evidence state | gold |
|---|---|---|---|
| risk | `CHECK_DATA_FLOW` ("remains enabled") or `CHECK_RESTORE_ACCESS` ("can still be restored"), no later disable/block | `enabled=true`, `restore_allowed=1`, `eligible=true deletion_block=false`, or `DATA_FLOW/BACKUP_ARCHIVE ... ACTIVE` | `REPORT_ACTIVE_DATA_FLOW` / `REPORT_RESTORE_RISK`, then DISABLE / BLOCK, then VERIFY |
| clean | `DISABLE_DATA_FLOW` / `BLOCK_RESTORE` SUCCESS earlier | evidence_92 shows `enabled=false`, `restore_allowed=false` | only `VERIFY_DATA_FLOW_DISABLED` / `VERIFY_RESTORE_BLOCKED` |

- Each risk case has one CHECK event and no DISABLE/BLOCK event for that resource; each clean case has one DISABLE/BLOCK event and no CHECK. The activity and the evidence agreed in every sample, so the samples cannot show what to do when a DISABLE SUCCESS exists but the evidence still reads enabled (the stream says 100% SUCCESS for those events).
- The `RESTORE_BACKUP` row (backup_9287 -> search_4882, 2026-08-22) and the 31 "connector repopulated" rows are not tied to any sample finding; not explained yet.

## 4. Identifier linking

- **email_hash:** `email_hash` = SHA-256 of the email for 850/850 current identities and all 107 audit hash changes (each old/new hash equals the SHA-256 of a known email of that user). All stored emails are lowercase, so "lowercased" is unconfirmed but safe; evidence emails can be upper-case (`H.LIM96@GMAIL.COM`), so lowercase before matching or hashing.
- Which identifiers sit in the resource's own cited record (33 gold resource/file pairs, 15 with an identifier plus 18 with none):
  - current email only: 24; old email: 9 (request email was the old one, cases 10, 29, 30); `user_id`/`customer_reference` only: 17; plus combinations with name, phone, hash in SQL replica rows (the richest records).
  - **18 records contain no subject identifier at all**: ABSENT accounts (no record exists), anonymized analytics (`analytics_5335`, `analytics_901`, all fields null), `support_001`, `analytics_9914`. These are tied to the user only indirectly.
- **Unresolved:** for those 18, I could not find how the resource is tied to the user from participant data.
  - Activity rows carry no user.
  - Only 12 `LINK_RESOURCE_IDENTITY` rows link resource to user.
  - A DELETE_RECORD on the subject's account occurs 23, 47 or 71 hours after `requested_at` (and about 1 hour before `reported_at` for the 4-digit cases, within 0.1 h for the 3-digit ones), but 3-15 other account deletes fall in the same window, so time alone is not unique.
  - `account_4857` (case_31) appears in no evidence file.
  - Candidates not yet checked: the PNGs (account admin console etc.), chains through activity ids, `audit_record` rows carrying `subject_reference = user_N`. This is the biggest open risk for the solver.

## 5. Checks requested after the survey

- **Hash:** see section 4.
- **cache_ / email_delivery_ in gold:** no. The gold answers contain only account, audit_record, analytics, search, support, export, backup, data_flow and tombstone resources. The 9 systems used are account_service, security_service, analytics_platform, search_service, support_platform, export_service, backup_service, integration_service, identity_service. `CACHE_ENTRY` / `EMAIL_DELIVERY_LOG` never appear in the 32 samples (consistent with them not appearing in text evidence).
- **Low-ID samples (case_01, 02, 04, 05, 06, 07, 08, 10; 3-digit ids):** yes, a different family.
  - 2.9 steps per case on average vs 7.1 for the rest; only account/search/support/export/analytics; no backup, data flow, audit-record or tombstone steps; no `VERIFY_RECORD_PRESENT`.
  - Reported status is COMPLETE or PARTIALLY_COMPLETE (never NOT_STARTED).
  - Each cites one individually named file (evidence_54/56/57/58/59/61), whereas the rest rely on shared multi-subject files (92, 94, 03, 01, 05, 51).
  - Their activity uses the different "Target resource: X" wording seen in the overview.
  - Suggests the 518 evaluation cases may contain both families; the solver cannot assume the richer pattern.
