# Usage report: final full-dataset run

The final run produced the submitted `output.csv` (518 rows):

```bash
LLM_BACKEND=api .venv/bin/python code/main.py
```

| | |
|---|---|
| started / finished (UTC) | 2026-10-25T08:01:48Z / 2026-10-25T08:04:52Z |
| code | frozen at commit `059a58c` |
| model cache | emptied before the run, except the 11 screenshot extractions (pinned, see below), so every intent and rule-condition read was a fresh API call |
| result | 518 rows, 0 validator problems; byte-identical to the previous run from cached answers |
| afterwards | two evidence fixes were added (`evaluation_report.md` step 8) and `output.csv` was regenerated from this run's cached answers: 0 new model calls, 2 rows changed (case_39, case_61) |

The numbers come from the client's per-call usage log, saved as `code/evaluation/final_run_usage_log.jsonl` (key, model,
reader, tokens; no request content). To recompute them:

```bash
.venv/bin/python code/evaluation/usage_summary.py --log code/evaluation/final_run_usage_log.jsonl
```

## Provider and model

| provider | model | used for |
|---|---|---|
| Anthropic (Claude API, Messages) | `claude-sonnet-5-5` | intent reader, rule-condition reader (with time-gated tools), screenshot extraction |

This is the only model. Every decision (identity, state, policy, steps, status) is made by code.

Prices: $2.00 per million input tokens, $10.00 per million output tokens (Claude API list price). No prompt-cache reads
or writes occurred.

## Model calls in the final run

| reader | calls | input tokens | output tokens | total tokens | cost (USD) |
|---|---|---|---|---|---|
| intent | 398 | 496,363 | 43,459 | 539,822 | 1.4273 |
| rule conditions | 125 | 228,077 | 11,926 | 240,003 | 0.5754 |
| **run total** | **523** | **724,440** | **55,385** | **779,825** | **2.0027** |

- **Intent reader:** one call per unique request text. The joint assignment solves all 550 requests (518 plus the 32
  samples) to propagate its exclusivity constraints, so the run reads every unique text among the 550.
- **Rule conditions:** 115 reader runs for 125 condition items, averaging 1.09 rounds per run.

## Screenshot extractions reused by the run

| reader | calls | input tokens | output tokens | total tokens | cost (USD) | when |
|---|---|---|---|---|---|---|
| screenshot | 11 | 36,799 | 13,917 | 50,716 | 0.2128 | 2026-10-24T18:13-18:14Z |

- **Coverage:** each of the 11 evidence PNGs was read once through the API (each entry is in the client's usage log
  with its token counts). Re-extracting is avoided because the screenshot prompt and its outputs are pinned (`data_findings.md`, "Flagged").
- **PDFs:** the 4 PDFs (7 pages) have a text layer on every page and no embedded images, so none is scanned. They are
  read by `pypdf` with no model call.

## Totals

| | calls | tokens | cost (USD) | per request (518) | per request (550 solved) |
|---|---|---|---|---|---|
| final run (API calls made) | 523 | 779,825 (724,440 in / 55,385 out) | 2.0027 | 1,505 tokens, $0.0039 | 1,418 tokens, $0.0036 |
| final run + reused screenshot extractions | 534 | 830,541 (761,239 in / 69,302 out) | 2.2155 | 1,603 tokens, $0.0043 | 1,510 tokens, $0.0040 |

Per model and overall (final run, API calls made):

| | calls | input tokens | output tokens | total tokens | avg tokens / request (518) | cost (USD) | avg cost / request (518) |
|---|---|---|---|---|---|---|---|
| `claude-sonnet-5-5` (Anthropic) | 523 | 724,440 | 55,385 | 779,825 | 1,505 | 2.0027 | 0.0039 |
| **overall** | 523 | 724,440 | 55,385 | 779,825 | 1,505 | 2.0027 | 0.0039 |

The two rows are equal because only one model was used.

## Calls outside the final run

These were evaluation runs after the final run, reading custom texts that are not in the dataset. They are in
`code/cache/usage_log.jsonl` but not in the final-run log:
- `intent_eval.py` (15 custom intent cases) and `custom_cases.py` (2 new request texts);
- 19 calls in total (17 intent, 2 rule conditions): 24,610 input / 2,050 output tokens, $0.0697.
