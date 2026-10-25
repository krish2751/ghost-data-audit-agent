# Data findings: what each rule in the solver rests on

Every rule in the solver either comes from `problem_statement.md` or from a pattern measured in the data, listed here with
its numbers and the script that prints them (`.venv/bin/python code/analysis/<script>.py`). The solver imports nothing from
this folder. Scripts that read `sample_output.csv` do so only to measure a pattern; the solver never reads it.

Survey of the activity stream and evidence formats: `data_overview.md` (`survey_activity.py`, `survey_evidence.py`).

## 1. Rules taken from the problem statement

- Statuses, phases, the 15 operations and their states, phase order FINDING -> REMEDIATION -> VERIFICATION, within a
  phase the problem-statement operation order then `system_id` then `resource_id`, step numbers from 1 (`schema.py`,
  `validator.py`).
- NOT_APPLICABLE when the request does not authorize deletion, with `[]` (`intent.py`, intent reader).
- COMPLETE only verification steps, citing evidence; INCOMPLETE findings cite evidence, remediation and verification use
  `""` (`planner.py`).
- Category -> treatment from `deletion_rules.csv` (`schema.TREATMENT`); rule conditions for rule_05, rule_06, rule_12
  and rule_13 are read by the rule-condition reader and mapped in code (`fallback._apply_conditions`).
- Only evidence captured at or before `audit_at` decides state or is cited; reported statuses and activity results are
  claims (`fallback._decide`, `validator.validate`).
- Identity: current and historical identifiers (`data/identity.py`).

## 2. Rules measured in the data

### Time and citations (`q1_time_ids.py`, `q1b_inner_times_drift.py`)
- Every file cited by the 32 sample answers has `captured_at` <= `audit_at`; 6 cases cite a file captured exactly at
  `audit_at` (cases 11, 13, 14, 16, 31, 32), so equality counts as "before".
- Files captured after `audit_at` that mention the subject are never cited (evidence_02 and evidence_06 hold resources of
  10 sample cases and are never cited).
- Owner decision (not a measurement): identity links may come from any file regardless of capture date; a resource counts
  only if it also appears in a file or activity row at or before `audit_at`.

### Identity (`q_hash_prefix_lowid.py`, `q11_multi_email.py`, `q12_email_ablation.py`, `q13_name_only.py`, `q4_identifier_links.py`)
- `email_hash` = SHA-256 of the lowercased email: 850 of 850 current identities and 107 of 107 audit-log hash changes.
- 105 of 850 users have more than one email over time; no email belongs to two users. 103 of 550 requests use a
  historical email (100 of the 518).
- Matching on all historical identifiers links extra resources for 84 of 550 requests (169 links). With current-only
  identifiers the samples drop to status 30/32, exact 17/32, F1 91.16% (case_10 and case_12 wrongly COMPLETE).
- Names are not link tokens: the 5 records that carry a subject's name and no other identifier all belong to other people
  with similar names.
- In the sample answers' own records the subject appears as: current email 24, user id only 17, historical email 9,
  richer combinations 7; 18 records carry no subject identifier (absent accounts, anonymized analytics).

### Replicas and conflicting observations (`q1b_inner_times_drift.py`, `q18_rule_evidence.py` part 5)
- A copy in any replica table counts as remaining: case_16 `account_994` exists only in the read replica and is a finding.
- The latest pre-audit observation wins; within the latest file the worst reading. Across the 550 outputs older
  observations disagree with the latest one for 7 of 1,361 resource decisions.

### Flows and backups (`q3_flows_backups.py`)
- Risk when the evidence reads `enabled=true`, `restore_allowed=1`, `eligible=true` with `deletion_block=false`, or a
  ledger `ACTIVE`; clean when it reads disabled/blocked. In every sample case the activity agrees (a `CHECK_*` row for
  risks, a `DISABLE_DATA_FLOW` / `BLOCK_RESTORE` SUCCESS row for clean ones).

### Category overrides in `data/states.py` (`q18_rule_evidence.py` part 4)
Observations without a `record_type` field whose category differs from the resource prefix default:

| override | observations | sample resources: override agrees with answer | default would agree |
|---|---|---|---|
| analytics `contact_lookup` / `email_opt_in` -> MARKETING_PROFILE (DELETE) | 1 | 1 of 1 | 0 |
| support `contact_query` / `deletion_marker` / legacy contact index -> SECONDARY_IDENTIFIER (DELETE) | 3 | 1 of 1 | 0 |
| support attachment source / PDF / `storage_class` -> SUPPORT_ATTACHMENT (DELETE) | 30 | 2 of 2 | 0 |

These rest on 1-2 sample resources each, so they are the weakest measured rules.

### Records with no identifier: joint assignment (`code/joint.py`)
- One account per case and one case per account, propagated over all 550 requests; accounts claimed by another user's
  identifier are excluded.
- Status/result agreement among identifier-linked cases (`q18_rule_evidence.py` part 1):

  | reported_status | account DELETE result | pairs | share |
  |---|---|---|---|
  | COMPLETE | SUCCESS | 134 | 99.3% |
  | COMPLETE | FAILED | 1 | 0.7% |
  | PARTIALLY_COMPLETE | PARTIAL | 69 | 100% |
  | NOT_STARTED | FAILED | 50 | 96.2% |
  | NOT_STARTED | PARTIAL / SUCCESS | 1 / 1 | 1.9% each |

  `min_share=0.05` keeps the three majority pairs; any value in (1.9%, 96.2%] gives the same set.
- Time window: the problem statement gives none. Account DELETE minus `reported_at` lies in -75..+8 min for 252 of 262
  identifier-linked pairs (median -59, 5th percentile -74); the other 10 are days to months away (`q14_window_evidence.py`).
  The window is learned at run time from those pairs: drop offsets more than `MAD_K=10` median absolute deviations from the
  median, take min..max, pad each side by `PAD_SHARE=0.1` of the width. Learned now for accounts: -83..+16 min.
- Label-free hold-out (`q16_holdout_accounts.py`, `q18_rule_evidence.py` part 2): the 254 identifier-linked accounts with
  a DELETE event are hidden in 5 folds grouped by user and must be recovered from activity alone.

  | window | correct | wrong | unresolved |
  |---|---|---|---|
  | fixed +-90 | 211 | 0 | 43 |
  | fixed +-120 | 177 | 0 | 77 |
  | learned (MAD_K 10, PAD_SHARE 0.1) | 213 | 0 | 41 |
  | learned, PAD_SHARE 0 / 0.05 / 0.25 | 212 / 213 / 213 | 0 | 42 / 41 / 41 |
  | learned, MAD_K 5 / 20 | 217 / 213 | 0 | 37 / 41 |
  | learned, no outlier removal | 1 | 0 | 253 |

  The constants are not sensitive within these ranges; outlier removal itself is what matters.
- Result on all 550: 164 of 285 cases lacking an account get one (162 strict, 2 relaxed); 121 stay ambiguous, mostly ties
  between same-status cases that share `reported_at`.
- Cross-kind order is not a relation: within a `reported_at` group, two cases keep the same relative order in two event
  blocks in 68 of 137 comparisons (49.6%, chance) (`q20_cross_kind_order.py`), so these ties are genuine.

### Unlinked analytics: timing follows the outcome, not the kind (`q19_offsets_by_result.py`, `q21_leave_kind_out.py`)
- Remediation events of identifier-linked non-account records, minutes from `reported_at`, by the record's outcome at `audit_at`:

  | kind | clean: n, range, before report | violation: n, range, before report |
  |---|---|---|
  | backup | 35, -8..-3, 35/35 | 1, -8, 1/1 |
  | data_flow | 36, -15..-7, 36/36 | none |
  | support | 39, -22..+83, 36/39 | 151, +1..+113, 0/151 |
  | tombstone | 5, -29..-28, 5/5 | 5, +42..+60, 0/5 |
  | search | none | 281, +10..+98, 0/281 |
  | export | none | 31, +5..+65, 0/31 |
  | analytics | 1, +49, 0/1 | 77, +38..+133, 0/77 |
  | account (separate block) | 194, -75..-44 | 58, -75..+8 |

- So a window learned from identifier-linked analytics alone is biased: anonymized analytics never carry an identifier, and
  the linkable ones are violations after the report. All 7 analytics records the sample answers verify ANONYMIZED have
  SUCCESS events 6-29 min before the report, outside that window (+29..+142).
- Rule (`joint.outcome_model`, `joint.assign_unlinked`): learn per outcome, from all identifier-linked non-account records,
  the offset window (same MAD_K / PAD_SHARE rule) and the compatible (reported_status, result) pairs; an unlinked analytics
  event fits a case when the record's own pre-audit reading gives its outcome and the event satisfies that outcome's window
  and pairs; assign on mutual uniqueness. Learned now: clean -37..+59 min with SUCCESS for every status; violation
  -22..+147 min.
- Leave-one-kind-out hold-out (each kind's identifier links hidden, model learned from the other kinds): 41 hidden records
  recovered, 0 wrong, 597 unresolved (competing events); 23 assignments went to cases that had no identifier-linked record of
  that kind and cannot be checked without labels.
- Effect: analytics assignments over 550 requests 6 -> 21. Samples: recall 93.26 -> 93.78, F1 96.51 -> 96.79, exact 21/32
  unchanged (the new record, case_04 `analytics_901`, sits in a case that also misses `account_004`); 20 of 518 outputs gain
  steps, no status changes. The other 6 sample analytics records are ties (cases 25/26 and 27/28 share `reported_at`;
  case_03 and case_21 each compete with another open case).

### One account per case (`fallback.solve`)
- Every sample case has exactly one account (32 of 32), and the joint assignment already assumes it. When identifier
  linking finds several accounts, only those whose DELETE event lies inside the learned account window are kept (all are
  kept if none is). This applies to 1 of 550 cases (case_17: `account_4092` deleted at -46 min is kept; `account_6523`,
  linked by a March lookup and deleted 24 days after the report, is dropped). Samples: exact 20 -> 21, precision 99.45 -> 100.

### Retained records seen only in a later export (`LATE_OK`, `q18_rule_evidence.py` part 3)
- The problem statement requires every policy-required retained record to remain available. 5 sample audit records that
  the answers verify PRESENT have no pre-audit file, only a later-captured export whose own record time is <= `audit_at`;
  17 others have a pre-audit file; 2 have no observation at all. The code accepts the 5 (verified with `""`, never cited);
  in the samples every record accepted this way is in the answers (5 of 5, 0 extra). Across the 550 outputs 123 records
  rely on this rule. Limited to audit and legal-hold records.

### Intent (`code/evaluation/intent_eval.py`)
- The 10 `CLASSIFY_REQUEST` intake rows join to cases 533-542 through ledger evidence_50; all 10 are non-deletion
  requests and the reader already says so, so the intake tie-break never changes an output.

## 3. Flagged: kept, but not backed by a measurement

- **Verify-evidence anchor fallback** (`fallback._anchor`): a record with no observation of its own (an absent account)
  cites the case's most-cited file; when the case cites nothing, the latest pre-audit manifest file. The second branch is
  a guess, used 3 times in 550 cases (case_01, case_02 match the answers by coincidence of capture times).
- **Rule-condition reader prompt** was corrected after its first version flipped 3 sample cases, so the samples are not an
  independent test of it. On all 550 requests its answers agree with the rule defaults (0 treatment changes); kept
  because it is the only code that checks rule_05/06/12/13 conditions at all.
- **Screenshot prompt** shows example ids in its output format line; pinned because editing it invalidates the cached
  extractions (a re-extraction once changed a case's status).
- **Regex intent fallback** (`intent.py`): used only when the reader has no cached answer and no API key; disagrees with
  the reader on 1 of 550 requests.
- **Input-size limits** (not decisions): reader loop 4 rounds (owner's cap), 40 rows and 12,000 characters per tool
  result, 3,000 characters per document in condition items.

## 4. Removed in the cleanup

- Link reader (`readers/link_reader.py`, its prompt, `evaluation/link_eval.py`): no code-produced evidence that it adds
  anything beyond the timing rules; its API run on the samples lowered F1.
- Session backend and the 30 in-session answers (`session_answers.py`, `cache_session/`): results judged in the session
  are not evidence. The client now has two modes: cache only (default) and `LLM_BACKEND=api`.
- `_discover_account` fallback and the joint `same_user` shortcut (never changed an output), the fixed `WINDOW_MIN=120`,
  the `+-120` fallback window, `PAD_MIN`, unused tools (6 of 9), dead reading branches (`http_status`,
  `account_status=DELETED`), `build_row`, `planner.system_of`, `Obs.system_id`, `identity.hash_email`.
- 614 stale cache entries (superseded prompts and the link reader), old prediction files, and 15 exploration scripts and
  notes for rejected hypotheses (activity blocks, PNG links, pairwise relation signals, fixed-window sweeps).

## 5. Known unrecoverable sample misses

- `account_004`, `audit_record_5569`, `audit_record_6645` appear in no participant file or activity row. Checked: exact ids
  and bare numbers in all 99 sources (every evidence file incl. PDF text, the 11 cached screenshot extractions, activity,
  identities, audit log, requests); the only exact hits are in `sample_output.csv`; number hits are other records
  (`support_5569`, ticket `CS-5569`, `account_6645`) and pod names (`account-4`).
- Ties: accounts `account_410` (case_23, 3 FAILED deletes for 3 open NOT_STARTED cases), `account_5482` / `account_7012`
  (cases 28/29, both NOT_STARTED, both FAILED); analytics records of cases 3, 21, 25-28 (each event fits two open cases).
