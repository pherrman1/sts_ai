# #883 phase 3 result: survival weighting plus keyed streams cut rollout3 sibling-difference variance about 5× per CPU (2026-10-27/28)

Pre-registration: [PREREG.md](PREREG.md). Smoke: [SMOKE.md](SMOKE.md). Analysis: `analyze.py result.json V-*.sib.jsonl`
→ [result.json](result.json).

## Run
- Run commit `2ed59b94` (code `8ece111d` plus the arm-order shuffle), v3 binary `c8f8d0e9…`, student_sel `cf6bf7fb…`.
  One 4-CPU cloud container, started 21:19Z.
- Seeds: the used §683 seeds 111374100–111374107, replayed at today's A20 default plus `STS_OOC_MCTS_SCREENS=map,rewards`.
  Each game stops at its first Act-4 state. No new seeds.
- **Deviation:** the container restarted twice (23:12Z and ~23:55Z). Five games ran to completion:
  - 100 and 102 reached Act 4;
  - 101, 103 and 104 died (floors 42, 16, 38).
  Games 105–107 were cut off twice, at floors 26–31 (acts 2–3), and are used up to the last complete row.
  - The replays are deterministic: each rerun's capture rows match the first attempt's prefix exactly apart from CPU
    fields (243/243, 172/172 and 162/162 rows).
  - For each seed, the longer file is used.
- Raw capture: `/mnt/project-files/ooc-variance-arms/` ([tars.sha256](tars.sha256); `final-capture.tgz` is the
  analysed set).

## Result
2,649 capture rows, all arms valid. 315 roots: 120 map, 195 rewards, of which 164 are card rewards. R = 128 repeats
per child and arm. Base death rate per rollout: 6.7%. With survival weighting, 0.1% (Act-4 fights and fights without a
CTM expectation only).

Variance of the R-repeat sibling difference relative to base (today's common seeds), with root-bootstrap 95% CI.
"Work" is variance × CPU, i.e. the ratio at equal CPU (lower is better):

| roots | arm | variance | 95% CI | CPU | work |
|---|---|---|---|---|---|
| card reward (164) | indep | 3.79 | [2.96, 5.47] | 1.32 | 5.02 |
| | sw | 0.282 | [0.214, 0.361] | 1.24 | 0.350 |
| | keyed | 0.618 | [0.508, 0.777] | 1.03 | 0.638 |
| | **swkeyed** | **0.162** | [0.110, 0.221] | 1.29 | **0.209** |
| rewards (195) | swkeyed | 0.158 | [0.111, 0.217] | 1.29 | 0.204 |
| map (120) | indep | 1.15 | [1.09, 1.24] | 1.29 | 1.49 |
| | sw | 0.224 | [0.192, 0.259] | 1.21 | 0.270 |
| | keyed | 0.579 | [0.504, 0.663] | 1.05 | 0.607 |
| | **swkeyed** | **0.142** | [0.116, 0.175] | 1.26 | **0.179** |

Bias check, each arm against base over 2,648 children:

| arm | pooled mean diff (root-clustered SE) | \|z\| > 2 | z < −2 / z > 2 |
|---|---|---|---|
| indep | +0.0006 (0.0009) | 4.3% | 1.9% / 2.4% |
| sw | −0.0001 (0.0007) | **29.8%** | 29.4% / 0.4% |
| keyed | −0.0002 (0.0012) | 4.0% | 1.9% / 2.2% |
| swkeyed | +0.0003 (0.0009) | 4.5% | 3.5% / 0.9% |

## Decision (pre-registered rule, rewards roots)
- **swkeyed: USEFUL.** Work ratio 0.20 (≤ 0.5), and no bias flag on either the pooled mean or the per-child z rule.
- **sw: INVALID by the letter of the rule:** 29.8% of children have |z| > 2, against a limit of 8%.
  - Exploratory, not pre-registered: the flags are one-sided (29.4% negative, 0.4% positive). The pooled mean
    difference is −0.0001 ± 0.0007.
  - Against keyed instead of base, only 6.3% have |z| > 2.
  - **Inference:** this is an artefact of the test, not a bias. sw shares base's draws until a death, so the
    per-repeat difference is a small negative (W − 1)·V almost everywhere, plus rare large positive terms where base
    died. With few deaths in 128 repeats the t statistic is skewed.
  - swkeyed decouples those draws and passes. The rule stands as written: sw alone is not recommended.
- **keyed: WEAK** (work 0.64, between 0.5 and 0.8), with no bias.
- **indep** (control): today's common seeds are worth 3.8× variance at card rewards and 1.15× at map roots.

## Reading
- At equal CPU, survival weighting plus keyed streams give about 5× as many effective repeats per CPU-hour for
  rollout3 sibling differences: 4.8× at card rewards, 5.6× at map roots. The mean does not move detectably
  (|pooled diff| ≤ 0.0003 against an SE of 0.0009).
- Most of the gain is survival weighting, which removes the death Bernoulli (§699). Keyed streams add coupling where
  the shared stream desynchronised. Their gain over base is largest at map roots: indep is only 1.15× base there, and
  keyed gives 0.58×.
- CPU +29%: `expectation()` costs a forward pass per rollout fight, and rollouts no longer stop at a death. A
  survival-only accessor would cut part of that.
- Scope: rollout3 values at depth-1 children of real map and reward roots, acts 1–3, 8 replayed games (5 complete).
  Not measured: in-tree MCTS (one rollout per simulation), Act 4, other screens, and longer horizons (campfire act-end
  price).

## Follow-up (proposal only; no default change)
Candidates where swkeyed would apply directly, each a separate pre-registered step for Philipp to choose:
1. Sibling-label captures (value-head data, §644 style) with swkeyed on. This needs no play change.
2. §695's campfire act-end price: same rollout machinery with a longer horizon; that stage failed on precision at
   N = 32.
3. As the live MCTS leaf. This changes play, so it needs a paired A20 A/B at matched CPU. Survival weighting also
   changes how the tree sees risk: the leaf mean is the same, but individual simulations no longer return 0.

Seeds: none new; 111374100–111374107 (§683, used) replayed.
