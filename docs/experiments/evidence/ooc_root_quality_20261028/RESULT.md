# Root quality at card rewards — phase 1 result (§TBD)

Pre-registration: [PREREG.md](PREREG.md) (frozen before data). Definitions:
[root-quality.md](../../../knowledge-base/research/ooc/root-quality.md). Campaign `ooc-root-quality-p1`: RUN_COMMIT
f9fd31a0, binary dc0a5fa3, 32 cloud workers × 4 lanes, 2026-10-28 21:37Z – 10-29 04:36Z. Raw unit tars:
data branch `claude/ooc-root-quality-data` (`results/ooc_root_quality_20261028/`, 143 tars, SHA256SUMS).

## Sample

- 144 probe units (128 + 16 spares), replays of the used §712 arm-A seeds 111387000–255. No new seeds.
- 143 units delivered and verified (`verify_campaign.py`: OK 143, BAD 0, duplicates 0).
- 111387111/119 failed 4 times with rc=90 (no probe row). Reproduced locally: on the run commit that game dies on
  floor 33 after 111 decisions, so it never reaches root 119 (the §712 record reached floor 37). It is invalid by the
  frozen rule.
- 7 delivered roots are invalid by the frozen rule (candidates must include Skip and Take card):
  - 111387043/45 is an event and 111387072/74 a campfire, because main diverges from the §712 record;
  - 5 roots are Singing Bowl card rewards (Bowl replaces Skip): 111387020/62, 050/159, 091/93, 106/110, 112/130.
    The rule was applied as written; these roots are excluded, not reclassified.
- 136 valid roots. The first 128 in seed order are the sample.
- Offers match the §712 record at all 128 sample roots.
- K > 5 candidates (multi-group act-4 or potion rewards): 12 roots.

## Pre-registered results

Uniform root, best mean Q, 4 search seeds, cross-fitted P_self (seeds {1,2} at 16,384 define ā∞, seeds {3,4} are
scored, then swapped). CI = root bootstrap, 10,000 resamples. Source: [phase1.json](phase1.json) from
[analyze_phase1.py](analyze_phase1.py).

| config | P_self 1,024 | P_self 8,192 [95% CI] | resolved-only 8,192 | unresolved share | P_self 16,384 | median \|seen gap\| | σ_D RMS (16,384) | ρ_eff median | core-s/root |
|---|---|---|---|---|---|---|---|---|---|
| X2-B h0 | 0.400 | 0.309 [0.250, 0.371] | 0.141 | 0.24 | 0.262 | 0.53 pp | 0.22 pp | 1.23 | 121 |
| X2-B h1 | 0.443 | 0.289 [0.232, 0.348] | 0.104 | 0.30 | 0.256 | 0.62 pp | 0.53 pp | 1.09 | 243 |
| **X2-B h3** | 0.414 | **0.250 [0.197, 0.305]** | 0.077 | 0.28 | 0.223 | 0.76 pp | 0.78 pp | 0.97 | 492 |
| X2-B h5 | 0.475 | 0.281 [0.230, 0.336] | 0.141 | 0.25 | 0.225 | 0.94 pp | 0.93 pp | 0.87 | 734 |
| SR h0 | 0.172 | 0.096 [0.061, 0.135] | 0.034 | 0.09 | 0.088 | 1.86 pp | 0.70 pp | 1.33 | 165 |
| SR h1 | 0.248 | 0.156 [0.111, 0.203] | 0.060 | 0.14 | 0.146 | 1.81 pp | 1.31 pp | 1.20 | 294 |
| **SR h3** | 0.326 | **0.207 [0.152, 0.264]** | 0.068 | 0.18 | 0.189 | 1.68 pp | 0.95 pp | 1.08 | 538 |
| SR h5 | 0.352 | 0.219 [0.166, 0.275] | 0.051 | 0.21 | 0.213 | 1.62 pp | 0.90 pp | 0.93 | 776 |

- **Decision rule (h = 3 primary): both leaves are "variance-limited at 8,192".**
  - X2-B: 0.250, lower bound 0.197.
  - SR: 0.207, lower bound 0.152.
  - Both pass the rule (mean > 0.20, lower bound > 0.10). The pre-registered next step is swkeyed rollouts in search
    (§703). See the exploratory section for how much this costs.
  - Not pre-registered (from the reviewer): on the 116 roots with K ≤ 5, SR's P_self(8,192) is 0.168 [0.119, 0.220],
    which is inconclusive by the same rule; X2-B's is 0.211 [0.162, 0.261]. SR's verdict therefore comes from the
    12 multi-group roots (0.58). The pre-registered all-128 verdict stands.
- Unresolved roots stay in the primary mean, as pre-registered. Resolved-only P_self(8,192) is 0.05–0.14.
- ρ_eff ≈ 1 (0.87–1.33): the seed-to-seed spread of Q differences matches the iid prediction from per-simulation
  moments. Common rollouts neither help nor hurt much.
- Horizon (share of simulation endpoints by floors past the root):
  - h0: 93–94% within 2 floors;
  - h1: 45–46% within 2 floors;
  - h3 and h5: 8% within 2 floors; the X2-B h3 mode is 5–7 floors.
  - Endpoint floors per root are in phase1.json (`horizon_floors`).
- K > 5 stratum (12 roots), P_self(8,192) at h3: X2-B 0.63, SR 0.58, against 0.21 and 0.17 for K ≤ 5.
- **Phase-2 gate: FAILED.** Projected SE(β_SR) = 0.393 > 0.35 over the 96 selected roots (SR h3 seen spread,
  per-salt SD 0.45, DEFF 3, M 4; [phase2_gate.selection.json](phase2_gate.selection.json)). By the frozen rule there
  is no phase-2 campaign, and β is "not measurable at this scale". Δ, B_rel, the advantage curves, the c bracket and
  q stay unmeasured. No forks were run.

## Exploratory (written after the data, not pre-registered)

[explore_self_regret.py](explore_self_regret.py) → [explore.json](explore.json).

**Self-regret.** The search's own regret, in its leaf's value scale: Q̄(ā∞) − Q̄(â_N), where Q̄ is the other half's
2-seed mean (cross-fitted). Mean over roots, in pp:

| config | 256 | 1,024 | 4,096 | 8,192 [95% CI] | 16,384 |
|---|---|---|---|---|---|
| X2-B h0 | 0.16 | 0.09 | 0.06 | 0.05 [0.03, 0.07] | 0.03 |
| X2-B h3 | 0.39 | 0.24 | 0.15 | 0.12 [0.06, 0.21] | 0.09 |
| X2-B h5 | 0.50 | 0.34 | 0.21 | 0.13 [0.09, 0.19] | 0.10 |
| SR h0 | 0.16 | 0.07 | 0.03 | 0.01 [0.01, 0.02] | 0.03 |
| SR h3 | 0.47 | 0.25 | 0.15 | 0.11 [0.06, 0.18] | 0.10 |
| SR h5 | 0.64 | 0.35 | 0.18 | 0.13 [0.08, 0.20] | 0.13 |

Picks disagree often, but the disagreements are among options the search itself rates within about 0.1 pp at 8,192.
Q̄ is noisy, so this regret has a small upward bias.

**Clear roots.** Roots where the reference half's best option leads the second by > 1 pp:

| | X2-B h3 | SR h3 |
|---|---|---|
| share of clear roots (mean over the two halves) | 20% | 46% |
| roots clear in at least one half (P_self scored there) | 29 | 64 |
| P_self(8,192) on clear roots | 0.07 [0.00, 0.17] | 0.06 [0.02, 0.11] |

Most of the headline P_self comes from near-ties.

**Leaf agreement.** Root shares where the 4-seed final argmax is the same:

| pair | agreement |
|---|---|
| X2-B h3 vs SR h3 | 59% |
| X2-B h3 vs production (student_sel) | 52% |
| SR h3 vs production | 64% |
| X2-B h0 vs X2-B h3 | 59% |
| SR h0 vs SR h3 | 76% |

The leaf and the horizon change the answer far more than the seed does. The SR head sees about 2–3× larger sibling
differences than X2-B. This fits §715's finding that the heads' sibling differences are over-dispersed.

## Reading

- At card rewards, search variance at 8,192 simulations is large in pick terms: P_self is 0.21–0.25 at h3, and 1 in
  4 picks differs from a 2-seed reference.
- It is small in the search's own value terms: about 0.1 pp.
- Which option wins is decided mostly by the leaf (X2-B vs SR agree on 59%) and the horizon, i.e. by bias, not by
  variance.
- Bias against the true Q (B_rel, β) needs the forks. At this scale and with the observed SR spread they cannot reach
  SE 0.35, so phase 2 stopped by the frozen gate.
- Variance-reduction work in search (swkeyed rollouts, the formal next step) is worth at most about 0.1 pp per card
  decision by the search's own measure.

## Deviations

- `analyze_phase1.py`: the offer parser crashed on "Leave rewards" candidates (key without `reward=`). The fix skips
  them and changes no statistic.
- `make_fork_units.py`: the pool was every probe row (143, invalid roots included). PREREG says "96 of the 128", so
  it now reads the 128-root sample from phase1.json. The old version could not run on this data (it stopped on an
  invalid root).
- Both fixes come after the data and before the gate was computed. The gate was computed once, with the fixed script.
