# Issue #379 preflight and sealed DECISION audit

Baseline: `a59d7e47f7fc0faee3015e824b267f6bf2961adc`, verified against remote main.

## Scope and status

TRAIN/VALIDATION custody and public-screen audit PASS. No model was selected or trained, no DECISION TEST numerical rows were parsed, and no gameplay-quality comparison was run. Full S0 requires exact frozen trajectory reconstruction; the CSV is not a complete simulator snapshot. Native screen-leaf inference is not implemented.

`GITHUB_CI_NOT_USED_BILLING_LIMIT`.

## Custody

Corpus SHA-256 `ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00`; 696 TRAIN, 155 VALIDATION, 173 sealed TEST sources. All 1,024 component-manifest and DECISION table hashes match. TEST tables were hashed as opaque bytes only, with zero headers or numerical rows parsed. Full historical corpus validation was not repeated.

X2-B native SHA-256 `a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf`; source UBJ identity `99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd` from its frozen manifest. Native artifact hashed locally; no default changed.

## DECISION audit

| Screen | TRAIN rows | VALIDATION rows | TRAIN row win rate | VALIDATION row win rate |
|---|---:|---:|---:|---:|
| boss_relic | 28,361 | 6,170 | 0.76912 | 0.78088 |
| event | 92,930 | 20,016 | 0.77109 | 0.78552 |
| rest | 124,883 | 27,443 | 0.77288 | 0.78355 |
| rewards | 1,002,326 | 220,331 | 0.77657 | 0.79010 |
| selector | 88,488 | 19,100 | 0.78266 | 0.80377 |
| shop | 122,356 | 25,231 | 0.77420 | 0.79208 |
| treasure | 49,670 | 11,134 | 0.77502 | 0.77834 |

Every screen has all 696/155 sources. Row-weighted win rates are descriptive, not model results. All emitted rows have complete supported enumeration. Event captures omitted for unsupported/incomplete enumeration: 14,370 TRAIN and 3,930 VALIDATION. `rewards` includes public reward screens, not just card choices. See `audit-reviewed.json` for source versus branch counts, candidate distributions, identities, structural variants, bytes per row, and the exact access seal. Initial `audit.json` is preserved; the reviewed report clarifies observed versus captured source counts.

## Current-main timing

Both runs select X2-B explicitly, use one thread, exact 10k Silver and OOC2048 with existing CPU attribution. These different seeds/configurations are separate profiles, not an A/B or a CTM speed comparison.

- `baseline3`: historical seed 12002032 and explicit historical attention CTM. Process CPU 225.67 s, MCTS 170.5306 s, leaf evaluation inclusive 52.9275 s.
- `current-default`: seed 12002033, current default DeepSets + Brew fallback + active-Lizard stack. Process CPU about 102.1 s, MCTS 62.6637 s. This is the current-default baseline to retain for any future matched timing comparison.

| Current-default bucket | Calls | Inclusive CPU s | Exclusive CPU s |
|---|---:|---:|---:|
| mcts | 125 | 62.663420 | 0.728419 |
| evaluate_leaf | 121894 | 33.616922 | 16.981830 |
| leaf_features | 121891 | 0.249580 | 0.249580 |
| leaf_predict | 121891 | 1.186017 | 1.186017 |
| prior_build | 113932 | 10.391274 | 0.193393 |
| combat_prepare | 23227 | 9.401651 | 9.401651 |
| combat_resolve | 23805 | 1.202226 | 1.202226 |
| real_combat | 26 | 39.267332 | 39.267332 |

Inclusive scopes overlap; do not sum them. Projection steps, ownership/fallback and additional counters are retained in the raw MCTS CSV. Two initial startup-only attempts rejected removed historical Silver telemetry/reuse flags before running a seed; their logs and receipts are preserved.

## Exact S0 recovery gate

The frozen DECISION sink retains rich run features, public screen contents and candidates, but not full RNG/pool/map state or executable continuation callbacks. The frozen generator kept its full state and combat action trace in memory. Original frozen producers and models remain available.

The derived exporter is reconstructed with `git archive` in an ignored build directory, without another linked worktree. It wraps original callbacks without changing their bodies and exports full snapshots. The current-main importer maps their identities to current continuation behavior, then calls the actual adapter `evaluateLeaf`. It does not replace S0 with a heuristic.

Estimated VALIDATION reconstruction cost from historical metadata: 44.11 branch core-hours across 5,169 branches; approximately 45.87 core-hours including extrapolated source/setup work, before S0. Hardware and exporter overhead remain unmeasured. Canary source 13001315 is VALIDATION, with 1,774 recorded DECISION states. Its all-seven-CSV exact-parity gate must pass before S0.

Review repaired exclusive snapshot output creation and an inactive Dead Adventurer relic read. Full snapshot roundtrip and all 17 callback-family comparisons passed constructed-state tests. These do not replace replay parity.

Knowledge impact: exact reconstruction and current timing evidence are recorded here; no model qualification, default promotion, or gameplay conclusion.


## Replay and current-candidate compatibility

VALIDATION source 13001315 was reconstructed with the derived first frozen
producer in 212.56 seconds. All seven CSV outputs match their original hashes
byte-for-byte. Snapshot SHA-256:
`dbc972012225ea72542035c25255d9a040ab50d9783984a31e0292711cd145c3`.
The first startup-only replay attempt failed because the launcher omitted
`STS_REST_WIN=0`; the repaired launcher uses the exact preserved runtime
environment with its frozen hash. Original data and failed attempts are preserved.

The first S0 pilot stopped after five states on a shop candidate-set mismatch.
Physical screen contents and rich features were identical. Current-main commit
`a666d719` added public potion replacement/discard choices after the frozen
producer: this full-belt shop state has exactly three added discard keys for
its three held potions, with no removed historical actions. Independent science
review approved only that known compatibility case: keep physical-screen and
rich-feature parity; independently construct exact legal discard additions
from public state; reject all other candidate changes. Log both candidate sets.
No rows, labels or splits are filtered or changed. The candidate predictive
representation may omit historical candidate-key strings, as allowed by the
handoff, while preserving visible choices/targets and held-potion state.
Historical labels remain outcomes of the historical policy, not evidence about
new discard-action trajectories. This is a VALIDATION implementation repair;
TEST remains sealed.


## Reviewed public-state coverage and S0 pilot

Both frozen-producer canaries PASS all seven CSV hashes: first source 13001315
in 212.56 seconds; second source 13001638 in 285.69 seconds. Full state recovery
is now demonstrated for both frozen producer versions, not universally proven
for all sources. Any later replay mismatch remains a hard stop.

The repaired first-source 512-state pilot PASS used 0.7991 leaf CPU seconds.
The two-producer 1,024-state pilot PASS used 1.6796 leaf CPU seconds in 2.5174
wall seconds; every observed screen family is represented. Shops averaged
7.234 ms/state; other families averaged 0.208–0.783 ms/state. Full VALIDATION
leaf evaluation is cheap compared with trajectory reconstruction. Receipts and
raw result summaries are adjacent. These are cost measurements, not quality.

Independent public-input audit fixes the provisional candidate families to
`boss_relic`, `rest`, `shop`, and `treasure`. All still require numerical
qualification. `event`, `selector`, and `rewards` retain the old continuation:

- Event rows omit public random offers/costs (for example Falling card targets,
  N'loth relic targets and We Meet Again demands), despite complete option IDs.
- Selector rows omit publicly promised parent effects. Designer's removal-only
  and removal-plus-upgrade choices can yield identical active REMOVE rows.
- Reward rows omit suspended known parent rewards or shop inventory. Cauldron
  can open five potions while the callback preserves unclaimed original rewards;
  shop Cauldron/Orrery reward pages similarly hide the known remaining shop.

These are representation limitations, not sparse data or model quality results.
The remaining four families' active screen contents cover their public offers
and actions under the accepted X2-B rich-state approximation. Closed-chest
pre-rolled contents and future Dream Catcher/dig rewards are not public input.
The fallback mask was chosen before training, with independent scientific
review confirming the handoff permits multiple problematic fallback families.
No rows, splits or labels are altered. No numerical TEST access has occurred.


## Temporal reconstruction and fixed training preparation

The temporal-export revision passed new canaries on the same two VALIDATION
sources in 216.19 and 293.18 seconds. Original seven-file CSV hashes remain
identical. It records all observed screen states, links the last captured
supported non-singleton decision across all families to the next observed MAP,
and captures actual post-forced-action states for potential sibling joins.
Python independently rechecks the timeline against the original MAP table.
Only the documented forced initial MAP-branch row is outside the observation
hook. Prior snapshots without temporal evidence cannot qualify this new gate.

Eligible calibration counts in these two canaries are: boss relic 30/24,
shop 44/35, rest 1/12 and treasure 1/1. Later captured reward or selector pages
exclude earlier decisions; no nearest-row or last-qualified-family substitution
is permitted. Full VALIDATION coverage still needs verification.

The reviewed fixed training run started at `28969b6e` with the four-family
mask, seeds 0/1/2 for each arm, TRAIN-only normalization, BCE/AdamW 1e-4,
weight decay 1e-3, batch 8,192, max 60 epochs and patience 8. The common small
embedding/pooling encoder feeds a 64/32 GELU trunk with dropout 0.1. S1 uses
four linear heads; S2 one. Their encoder/trunk initialization matches per seed.
Historical/current shop candidate sets are canonicalized using exact public
potion-discard rules; no hidden inputs, selected actions or source IDs enter
the model. Frozen feature ordering and cache/source/row custody are enforced.
Training is not model selection or offline qualification.

The full S0 recovery resource protocol is 155 fixed VALIDATION sources, one
S0 replicate/state, at most six source workers, at most 3,600 seconds/source
and 12 hours overall. No retry or output overwrite is allowed. Existing temporal
canaries are reused only after rehashing their CSVs, snapshots and links. Every
source replay uses the original producer/model/runtime identities and exact
seven-file parity. Failure stops further scheduling and preserves active jobs.
Independent reviews approved this bounded scope and the pretraining tools.

Resource diagnostics will use 1,024 VALIDATION states: 256 per candidate family,
covering all 155 sources per family before additional deterministic hashed rows.
HP +/-5 (denominator 10), gold +/-25 (actual clipped interval), Feed-like +1 HP
and maxHP, maxHP-only +1, and one removal per distinct held potion ID preserve
exogenous offers. Duplicated inventory and derived legal actions are regenerated;
paired S0 keeps original identity-based RNG. No probe is a qualification gate.

The first full-cohort launcher preflight stopped before creating its output
directory or running any seed: 26 cloud-source manifests retain cloud teacher
paths. Their teacher SHA is identical to the preserved local second-producer
teacher. The repaired resolver permits only the two known frozen teacher hashes
and verifies identical bytes before relocating a missing path. Existing paths
with changed bytes still fail. Original paths remain in receipts; model and
runtime-environment hash checks remain mandatory. No original manifest changes.

## Fixed fits and first full-recovery failure

All six fixed training fits completed; checkpoint and training-code hashes
were verified. `fixed-training-completed.json` records their identities and
individual VALIDATION NLLs. No candidate has been selected or qualified.

The first actual full recovery used source `39f8d681` and finished with FAIL
after 3,104.47 seconds. All 14 scheduled source replays passed exact seven-file
parity; 13 S0 evaluations passed, and source 13001065 failed strict public
parity at branch `s13001065-d25-e4060641b190`, row 1. Scheduling stopped and
active workers finished normally. The protocol, aggregate result and raw
failure are preserved beside this document.

Golden Idol's frozen option enumeration uses held relic ID 143 to distinguish
offer `[0,1]` from trap `[2,3,4]`. Current main uses `info.phase`, introduced
by `a666d719`. The recorded branch moves from no Idol to held Idol while its
historical phase remains zero. Current import therefore sees the initial
offer. Independent diagnosis confirms field-semantic drift, not an omitted
snapshot field. A bounded repair must explicitly bind the historical producer,
translate only this phase, retain original bytes and require exact public,
candidate and rich-feature parity. No generic legality relaxation is allowed.

The reviewed recovery design uses a new binary/protocol/output directory and
rehashes reusable replays, including the failed S0 source's successful replay.
The first 12 successful S0 jobs cost 55.79 wall seconds collectively; repeating
S0 once under the repaired binary is regression evidence, while the expensive
historical replay remains reusable. Compare existing values, RNG seeds and
projection steps exactly wherever adaptation is inactive. No retry occurs
inside the failed run, and no TEST numerical content has been opened.

Before learned calibration inspection, independent review selected per-act
point limits `min(absolute_cap, S0_statistic + margin)` with absolute caps
0.05 signed-mean magnitude / 0.10 MAE / 0.25 p95 and margins 0.01 / 0.01 /
0.025. These are explicit materiality judgments, not empirical facts. Require
at least 30 sources and 200 exact links per act and pooled replacement family.
Compute every eligible subset's limits on its own exact matched population
before inspecting learned calibration. Paired uncertainty and act-family
cells remain diagnostics. Full S0 evidence is still missing, so no numerical
subset limits or calibration PASS exists yet.

## Second full-recovery failure: stale Colosseum Smoke Bomb flag

The repaired recovery (`full-validation-import-v1`, source `22c2be2c`) reused
16 replays, passed the regression barrier, and finished with FAIL: 58 sources
scheduled, 57 PASS. Source 13001297's replay passed exact seven-file parity,
but S0 aborted after 1,683 of 2,476 rows with the CTM support exclusion
`pre_smoke_bomb_used`. Raw failure: `full-validation-smoke-bomb-failure.txt`.

All seven affected rows are the Colosseum event (event 12, screen state 1)
at floor 27 with `smokeBombUsed=true`; no other completed source has the flag.
The Colosseum slaver fight installs its own regain-control callback that
reopens the event without `afterBattle()`, the only place that clears the flag
(`GameContext.cpp` Colosseum case vs `afterBattle`). `BattleContext::init`
resets the flag, so it has no simulator effect outside combat; only the CTM
contract reads it. Current main has the same behavior, so live OOC MCTS can
reach this state too; that is tracked as a separate main fix, not changed here.

Philipp approved clearing the stale flag outside combat. Independent review
found the same callback pattern in three more event fights (Dead Adventurer,
Masked Bandits, Mushrooms) and that the flag survives Colosseum Cowardice into
later rooms, so unreplayed sources may carry it on other screens. Outside
combat the flag also disables initial Smoke Bomb masking in the OOC adapter;
rich features ignore it. The rule therefore applies to historical frozen-334
rows on every non-BATTLE screen: clear `smokeBombUsed`, require that no other
snapshot field changes, record rule `frozen334_stale_smoke_bomb_flag_clear_v1`
with screen state and event in `snapshotImportHistory`, and reject the flag
inside BATTLE. The Python projection oracle mirrors the rule. Constructed
self-test (`smoke-bomb-import-selftest.txt`) covers Colosseum, Mushrooms and a
shop, clean controls, idempotent re-import and the BATTLE rejection. Rerunning
S0 on the preserved 13001297 input gives 2,476 rows; the first 1,683 match the
failed run's partial predictions exactly apart from CPU timing and audit
metadata, and seven rows carry the new audit record. Recovery resumes in a new
protocol directory reusing all verified replays. No TEST numerical content has
been opened.

Philipp raised the source-worker cap from six to ten for the resumed run
(`full-validation-import-v2`). Workers are independent single-threaded source
jobs, so this changes wall time only; per-source and global budgets are
unchanged.
