# History

On 2026-10-30 this repository's history was rewritten to collapse the HackerRank starter commits into one import commit and to remove co-author trailers; file contents did not change. `log.txt`, the reports and older commit messages cite the old hashes; this table maps them to the new ones.

## Solution commits

| old | new | date | subject |
|---|---|---|---|
| `191a91f` | `4777302` | 2026-10-24 | feat: deterministic audit pipeline, intent reader, evaluation scorer |
| `48b0b6a` | `a010cd4` | 2026-10-24 | feat: rule-condition reader, parallel solving, robust JSON parsing |
| `47e775c` | `2ca7671` | 2026-10-24 | feat: link reader (off by default), late-snapshot existence for retained records |
| `3103df7` | `3f4daee` | 2026-10-24 | feat: joint account assignment, session backend (no API credits), relation analysis |
| `cf4ca18` | `91d2ae5` | 2026-10-24 | feat: learn account-delete window from identifier-linked pairs, label-free hold-out, multi-email ablation |
| `4e961c0` | `e4d058d` | 2026-10-24 | chore: cleanup - remove link reader, session backend, dead code, stale caches; document rule evidence |
| `571ed4b` | `6564980` | 2026-10-24 | fix: one account per case when several are identifier-linked |
| `a49c15a` | `31632d4` | 2026-10-24 | fix: learn unlinked-analytics window per outcome from all non-account kinds |
| `32d0d67` | `c706730` | 2026-10-24 | docs: record the search behind the unrecoverable sample misses |
| `0b98d69` | `ebca278` | 2026-10-25 | docs: generated mismatch review of the 11 non-exact samples |
| `245ad2d` | `a0391c4` | 2026-10-25 | fix: COMPLETE-evidence tie-break in the joint account assignment |
| `059a58c` | `4b0ebe9` | 2026-10-25 | chore: usage summary from the client's usage log (code freeze for the final run) |
| `83dad15` | `1c98ba5` | 2026-10-25 | docs: final API run cache, evaluation and usage reports |
| `d026534` | `725f50b` | 2026-10-25 | docs: generated extraction review of the 11 screenshots and 4 PDFs |
| `7a42fdf` | `ee0f438` | 2026-10-25 | fix: drop link-row claims contradicted by the record's observed identifiers |
| `355b369` | `b340b26` | 2026-10-25 | revert: link-contradiction rule (7a42fdf) |
| `5ace497` | `0834de0` | 2026-10-25 | fix: catalog-link evidence for case_39 / case_61; reject COMPLETE with no steps |
| `9bc252f` | `5769f89` | 2026-10-25 | chore: packaging - requirements.txt, README setup and zip contents |
| `381553d` | `15e54c9` | 2026-10-25 | fix: official clarifications - COMPLETE [] warning, contract validator, input row order |
| `06c0db6` | `c43f04d` | 2026-10-25 | chore: final audit - README env vars and API run, explicit report totals, remove failure_diff.py |
| `e23fecd` | `df49fab` | 2026-10-30 | docs: log GitHub publication turn |

## Starter commits (HackerRank)

All 41 starter commits, ending at `acb3dfc`, are collapsed into the new root commit `32ecc5e` ("Import HackerRank Orchestrate (Oct 2026) starter repository"). It has the same files as `acb3dfc`. The originals are at https://github.com/interviewstreet/hackerrank-orchestrate-october26.

| old | new | date | subject |
|---|---|---|---|
| `4c9a41f` | `32ecc5e` | 2026-10-19 | feat: add the initial problem statement |
| `1eaa37b` | `32ecc5e` | 2026-10-19 | chore: add initial csv files |
| `cfe56d1` | `32ecc5e` | 2026-10-20 | chore: update problem statement |
| `8828fea` | `32ecc5e` | 2026-10-20 | chore: add README |
| `2045f12` | `32ecc5e` | 2026-10-21 | chore: update the output csv format |
| `4455884` | `32ecc5e` | 2026-10-21 | chore: add user identity csv |
| `355dc1d` | `32ecc5e` | 2026-10-21 | chore: update problem statement & readme |
| `85c5407` | `32ecc5e` | 2026-10-21 | chore: update user identity |
| `0112619` | `32ecc5e` | 2026-10-21 | chore: update problem statement & readme |
| `0d57fa7` | `32ecc5e` | 2026-10-21 | chore: update user identity |
| `b9fa84a` | `32ecc5e` | 2026-10-21 | chore: add deletion rules |
| `5901931` | `32ecc5e` | 2026-10-21 | chore: add user audit log |
| `6274eb1` | `32ecc5e` | 2026-10-21 | chore: add user audit log |
| `8b1b0a2` | `32ecc5e` | 2026-10-22 | chore: update problem statement |
| `e66a68c` | `32ecc5e` | 2026-10-22 | chore: update problem statement |
| `2260d30` | `32ecc5e` | 2026-10-22 | chore: add system activity |
| `d754d5f` | `32ecc5e` | 2026-10-22 | chore: add JSON files in the evidence |
| `b10693b` | `32ecc5e` | 2026-10-22 | chore: add log files in the evidence |
| `426c47c` | `32ecc5e` | 2026-10-23 | chore: add sql files in the evidence |
| `65f9901` | `32ecc5e` | 2026-10-23 | chore: update README & problem statement |
| `c4e6401` | `32ecc5e` | 2026-10-23 | chore: update system activity |
| `a1e1de7` | `32ecc5e` | 2026-10-23 | chore: add evidence file |
| `d48ae53` | `32ecc5e` | 2026-10-23 | chore: dataset updates |
| `f07332f` | `32ecc5e` | 2026-10-23 | chore: add hidden requests |
| `7bd1a8c` | `32ecc5e` | 2026-10-23 | chore: add more assets |
| `5d42798` | `32ecc5e` | 2026-10-23 | chore: add code/ folder |
| `25d36a2` | `32ecc5e` | 2026-10-23 | chore: update problem statement |
| `cfc7b5d` | `32ecc5e` | 2026-10-23 | chore: update dataset |
| `25c1e10` | `32ecc5e` | 2026-10-23 | chore: update problem statement with definition |
| `71cd82d` | `32ecc5e` | 2026-10-23 | chore: enhance README with quick start and layout sections |
| `5f2f701` | `32ecc5e` | 2026-10-23 | chore: update README |
| `1f977e3` | `32ecc5e` | 2026-10-23 | chore: update evidence dataset |
| `593a138` | `32ecc5e` | 2026-10-23 | chore: update problem statement |
| `e71cd39` | `32ecc5e` | 2026-10-24 | chore: add AGENTS.md |
| `0e07b3d` | `32ecc5e` | 2026-10-24 | chore: dataset updates |
| `5195962` | `32ecc5e` | 2026-10-24 | chore: dataset updates |
| `4427602` | `32ecc5e` | 2026-10-24 | chore: update the problem statement |
| `11576c9` | `32ecc5e` | 2026-10-24 | docs: align evaluation report paths with code.zip packaging in README |
| `6e456cc` | `32ecc5e` | 2026-10-24 | chore: add agent trace |
| `9731f2a` | `32ecc5e` | 2026-10-24 | docs: explain trace submission for unlisted harnesses |
| `acb3dfc` | `32ecc5e` | 2026-10-24 | chore: add CLAUDE.md |
