# Findings: linking an account resource to the user (32 samples)

Scripts: `linkage.py`, `q5_activity_block.py`, `q5b_offsets.py`, `q5c_window_and_sources.py`. Observations from the samples only.

## 1. Consecutive-activity-block hypothesis: rejected
Rule tested: take the activity ids of the resources linkable by identifier, then pick the nearest account `DELETE_RECORD` with a lower activity number.
- 8 right, 15 wrong, 9 cases untestable (no identifier-linkable resource with treatment/check activity).
- Activity numbers are strictly time-ordered (0 inversions in 3,998 adjacent pairs), so ids are usable, but blocks of different users interleave. Cases 27, 28, 29 occupy overlapping ranges (ids 3530-3544); in most wrong cases the gold delete is the 2nd or 3rd previous account delete, not the nearest.
- case_29 (3532 then 3541-3544) happens to fit; case_31 (delete 3682, tombstone 3687) is wrong because three other account deletes sit between them.

## 2. What the timing does show
Relative to the case's `reported_at`, events cluster tightly (minutes), independent of the user:
- Account `DELETE_RECORD`: 3-digit-id cases at reported_at -4..+8 min; 4-digit-id cases at -45..-72 min. Delete happens 23, 47 or 71 hours after `requested_at`.
- Other resources: +39..+112 min for failed/open work (reported not-done), -7..-29 min for completed work.
- But the window is not unique: 8 of 32 samples have exactly one account delete in it, 21 have 2-6 candidates (the gold is always among them when a candidate exists), 3 have none (cases 4, 16, 23). Cases sharing a `reported_at` (24/25/26; 27/28/29; 14/31/32; 18/20) are indistinguishable by time. Caution: the offsets are a property of how the data was generated; using them is a case-family shortcut that should be a conscious decision, not a default.

## 3. Direct identifier links
Of the 32 gold accounts, the cited evidence ties 14 to the subject by an identifier in the account's own row (current email in handover/logs/SQL; name, phone, user_id in replica rows). The other 18 are "no-id" or absent from all text evidence: cases 1, 2, 4, 7, 8, 10, 18, 20, 22, 23, 29, 30, 31, 32 appear in no text evidence; 21, 25-28 appear only with nulled fields in evidence_92 (`profile: null, 404`).
- **Low-ID family:** `account_00N` = `user_0N` for user_01..user_10 in the 8 low-ID cases (e.g. user_10 -> account_010). A numbering convention, not a stored link.
- **Pre-audit rows inside later files:** bundle `evidence_02` (file captured 09-17, after audit_at 09-15) holds an inner snapshot captured 09-09 with the full pre-deletion rows (e.g. `account_5684`, name, email, phone, `user_26`) for cases 24, 26, 27. Its inner `captured_at` is before `audit_at`, but the file is not; whether such rows may be used for identity linking (never for citing) is undecided.

## 4. Other requested sources
- **Readback logs / ledgers:** they link accounts to the subject when present (`lookup_key=<email>` or `subject_reference=<email>` next to `account_N`; evidence_01, 03, 94 cover cases 3, 11-17, 19), but 18 gold accounts are not in them.
- **audit_record and tombstone rows** carry `subject_reference = user_N` (and, in a SQL/JSON tombstone, name/email/phone/hash when not yet redacted). They tie the retained/tombstone resource to the user, but none of the 804 lines mentioning `audit_record_`/`tombstone_` also mentions an `account_` id, so they do not reveal the account.

## Conclusion
No participant text source explains the leftover accounts (18 of 32 in the samples). Remaining candidates: the PNG screenshots (`account_admin_console_20260926` is captured at exactly the `audit_at` of cases 18 and 20, which have no text link), and the use of pre-audit rows inside later bundles.

## Update: PNG extraction (11 files, claude-sonnet-5-5, cached in `code/cache/`)
`q7_png_links.py`. 45 records, 31 distinct resource ids. Only one sample-gold resource appears in a PNG (`data_flow_9846`, case_15, which was already linked). The remaining PNG records map to users of evaluation cases (user_11 -> case_34, user_13 -> 35, user_14 -> 39, user_16 -> 55, user_18 -> 33/52, user_20 -> 50, user_22 -> 53, user_03 -> 45), matching the `LINK_RESOURCE_IDENTITY` activity rows. So the PNGs and those 12 rows are the identity bridge for the evaluation-only cases, and resolve 0 of the 18 unlinked sample accounts (6 low-ID by convention, 12 with no source found). Cost: 11 calls, 37,799 input and 13,917 output tokens.
