# Pre-registration: Silver victory-leaf reweighting and concave HP, paired whole A20 runs (2026-10-18)

Status: written before any cohort seed ran. Ledger entry §TBD (the next free number at merge).

Authorization:
- Philipp, 2026-10-18 17:38Z, thread "end-state formula", after the concave-HP probe (PR #665, NOT_SHOWN) and its
  measured prices: "can you try all these things? adjusting the weights, maybe a per potion value, withthe fitted and
  milder curve? maybe in combination all those small things actually do something? and maybe we should measure
  winrate and floors reached, testing should be on only student prior without ooc mcts, so it doesnt take forever.
  on a20."
- Worker count and cohort size: [campaign.manifest](campaign.manifest) `workers` and [units.txt](units.txt), as
  Philipp picks them on the size question in the thread (proposal: 16 workers, 512 seeds).
- Seeds: coordinator reservation (see [README.md](README.md)); cohort = the seeds of `units.txt`.

## Question

Silver's victory leaf (`SilverSearcher::evaluateEndState`) scores a won, non-final fight as
`53 + h + 11·potions − 0.4·turns + 0.25·Δgold + 2·ΔmaxHP + …`. The concave-HP probe (§TBD of PR #665; 2,651 paired
A20 3-fight continuations under the student_sel policy, A20 floor model) did not show an effect of a concave HP term
alone, and priced the other resources well below the formula: non-Fairy potions 5.0 HP-eq [1.8, 8.1] (formula 11),
max HP 1.08 HP per point [0.53, 1.66] (formula 2), gold 0.011 HP per gold [−0.064, 0.070] (formula 0.25). §513
(student C, 128 whole runs, act-3 stop) did not show an effect of lower potion weights alone. Do these changes,
alone or together, make whole A20 runs reach more floors or win more often?

## Arms ([run_unit.sh](run_unit.sh))

Common stack: A20, full runs with keys (`STS_COLLECT_KEYS=1`, `STS_STOP_AFTER_ACT=0`), `STS_OOC_HEART1=student_sel.bin`
(`cf6bf7fb…`, Philipp's A20 OOC policy) taking every out-of-combat decision it encodes, **OOC MCTS off**
(`STS_OOC_MCTS=0`; Philipp: "only student prior without ooc mcts"), exact-10k live Silver on the main defaults at
the code commit (rollout root table, ADR-0036 escape penalty, …). Arms differ only in Silver's victory-leaf research
options; all are unset in `base`:

| arm | gold weight | max HP weight | held potions | HP term |
|---|---|---|---|---|
| `base` | 0.25 | 2 | flat 11 | linear |
| `W` | 0.01 | 1.1 | 5.0 (Fairy, Smoke Bomb 11) | linear |
| `WT` | 0.01 | 1.1 | per type, [WEIGHTS_TYPE](WEIGHTS_TYPE) | linear |
| `K27` | 0.25 | 2 | flat 11 | concave k = 2.7 (fitted) |
| `K135` | 0.25 | 2 | flat 11 | concave k = 1.35 (milder) |
| `WTK27` | 0.01 | 1.1 | per type | concave k = 2.7 |
| `WTK135` | 0.01 | 1.1 | per type | concave k = 1.35 |

- New research options in this change: `STS_SILVER_GOLD_WEIGHT`, `STS_SILVER_MAXHP_WEIGHT` (native Silver; unset =
  0.25 / 2). Existing: `STS_SILVER_POTION_WEIGHTS` (§513), `STS_SILVER_CONCAVE_HP_LEAF` (PR #665). With a concave
  HP term the held-potion term (flat or per type) is scaled by `sqrt(u'(h))`, as in the probe.
- **The weights are fixed here, not tuned on these seeds.** Gold 0.01 and max HP 1.1 are the probe's point prices
  rounded. Potion level 5.0 is the probe's pooled non-Fairy price. `WEIGHTS_TYPE` comes from
  [derive_weights.py](derive_weights.py) on the probe CSVs (the 16 worker tars in
  `/mnt/project-files/silver-leaf-eval/endstate-ab/`): per-type HP-eq price `mean(base − pot:T) / HP slope` on the
  floor model, empirical-Bayes shrinkage toward 5.0 (τ² = 30.8 from the 14 non-Fairy types with n ≥ 100; types with
  n < 30 take 5.0), floored at 0; Fairy and Smoke Bomb stay at 11 as in §513. Result 0.5 (Dexterity) to 10.7
  (Energy).
- Every unit's log must carry the arm's `[silver] research leaf: …` line (none in `base`); the analyzer checks it.

Paired by seed: every seed runs all seven arms on the same worker (`units.txt` is arm-major and the per-arm seed
count is a multiple of the worker count). One-seed `bestbench 10000 1 20 SEED` units through `tools/seed_guard.sh`,
4 at a time per worker, 4 h timeout per unit. **Inference** from §513 (66 s per run to act 3 with student C) and the
smoke: about 1–2 min per full run without OOC MCTS.

## Analysis ([tools/analyze_silver_leaf_combo.py](../../../../tools/analyze_silver_leaf_combo.py))

Each of the six treatment arms vs `base`, on seeds with a counted unit in all seven arms:
- **Floors reached** (CSV `floor`): paired mean difference.
- **Winrate** (CSV `won`, Heart kills): paired difference, plus exact two-sided McNemar.
- Seed-bootstrap CIs, 10,000 resamples, `random.Random(536)`, at 95% and at the Bonferroni level for six contrasts
  (99.17%). Label per contrast and metric: **BETTER** if the 99.17% lower bound > 0, **WORSE** if the 99.17% upper
  bound < 0, otherwise **NOT_SHOWN**. The two metrics are reported side by side; neither is ranked above the other.
- Descriptive: act-3 clears, act-1 deaths, seconds per run, pairs that differ at all.

**Power (Inference).** §513's per-pair floor SD (~10 floors) gives a 95% half-width of about 0.9 floors at 512 pairs
(1.1 at 99.17%). At ~10–15% Heart kills under the student alone, the win difference half-width is roughly 2.5–3 pp.
Small gains (< 1 floor, < 2 pp) would be NOT_SHOWN.

## Validity

A unit counts when its `.done` has rc=0 and its CSV has the seed's row. A seed missing a counted unit in any arm drops
out of all contrasts (counted; no rerun or replacement). INVALID if more than 16 seeds drop, or any unit has the wrong
leaf options in its `.env`, lacks the arm's research-leaf log line (or `base` has one), does not load student_sel,
does not set `STS_OOC_MCTS=0`, is duplicated, or is outside the cohort.

## Decision

- No default changes from this run. A contrast labeled BETTER on either metric (and not WORSE on the other) makes
  that arm a default candidate; Philipp decides, after a confirmation he authorizes (the arm was picked out of six).
- All NOT_SHOWN: the options stay research-only and the weights are not re-tuned on these seeds. Result to the ledger.
- WORSE: that variant stays off; result to the ledger.
- Scope note: OOC MCTS is off here, so the result speaks for Silver's leaf under the student policy alone. Whether it
  carries over to the full stack (OOC MCTS, imagined fights) is not tested.
