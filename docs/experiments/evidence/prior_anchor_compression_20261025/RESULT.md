# Prior-anchored compression: Stage A result

**PRIOR_ANCHOR_NOT_SEPARABLE. Stage B did not run.** The three fixed gates
cannot admit the five successful historical skips and reject the known
destructive floor-0 skip. No compression beam was implemented, no challenge
game was run, and default OOC search is unchanged. #844 stayed read-only.

Baseline current main: `8cce22b4d5d54733330e323b3065ca687fbcbfc5` (advanced from
the user's original observation). Reviewed evaluator source:
`fb03ef6649bb9010cd66e1577cf744bd2e32fd1a`; binary SHA-256
`ec6ceb73d475c70430c3c5ce3ea13257e7f631d6739b05ae0c614a6ce6589945`.
[FREEZE.json](FREEZE.json) contains all source/model/input/budget identities.

## Fixed gates

| Gate | Five successful skips | Destructive floor-0 skip | Separation |
|---|---|---|---|
| P4: rank <=4 | 5/5 eligible | Eligible, rank 2 | FAIL |
| P2: log-prior gap <=2 | 0/5 eligible | Rejected, gap 16.6604 | FAIL |
| V5: within max(0.05,2 combined SE) | Values unavailable | Eligible | FAIL |

The adapter first applies its existing forced-gold and tree-rule reward collection on its detached root. These ordinary steps preserve deck size and cycle burden in all audited states. Prior inference and action enumeration then use that current-policy decision state. Every audited native action set has four candidates (three cards and one skip),
so P4 admits every audited skip. P2 rejects every audited skip. The successful
skips have log gaps 11.47–23.78; there is no threshold search in this task.

For the exactly reconstructible initial Neow reward, the CRN mean is
0.150275570 ± 0.009061740 SE for skip and 0.155508972 ± 0.009312500 for
Headbutt (both prior and value argmax). The gap 0.005233402 and paired SE
0.001902978 give a V5 tolerance of max(0.05,0.003805956)=0.05. V5 therefore
admits the known destructive skip. That alone fails its separation condition,
regardless of missing positive-state values.

The [full 18-decision table](audit.md) covers five 032/11111 skips, six
326/13-skip skips and seven 326/R1 skips. [audit.json](audit.json) retains all
72 legal semantic candidates, normalized prior probabilities, ranks, log gaps,
CRN means/SE/value gaps when qualified, before/after deck and cycle counts,
coverage checks, loaded model identities and per-particle arrays. Later 326
skips are not individually proven negatives and are not labeled as such.

## Models and information boundary

- Prior: current deployed student_sel (`cf6bf7fb7c3147dcc5b106b1a946486e40bf27fee87c57bcc3262b5869d507c7`),
  loaded from the installed frozen release; 18/18 native reconstructed public
  records match, 18/18 heart1 prior builds, zero prior fallbacks.
- Leaf: current-main deployed rollout3 under student_sel, public X2-B
  (`e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90`),
  M0 per-act calibration `-2.5384,-2.9227,-3.6523,-3.6334:1.0535`.
  #853's SR-head blend was an unqualified experimental head and was not
  substituted for the deployed leaf.
- Current-main A20 CTM: HP-finetuned native model `bdbfafa6823adc52ff240dae5cbd2ba224aca145f2182bedf79fe0dc8cf6571b`,
  A20 Brew fallback `e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d`,
  calibrated table `8c226f23d80ff1cd2d9d1f87a14af3b5098a710ef88c6428f3fe0e70b3283653`,
  and the deployed Act-4 survival overlay. All base-stack, V4/floor, overlay and
  calibration hashes are in FREEZE.json. Startup logs confirm actual loading.

Historical records lack full replay snapshots, RNG/counters, latent pools,
continuation callbacks, and path/policy history. Later public projections were
used only for prior inference and semantic enumeration; all their CRN values
are null. Only seed 111101326's initial Neow choice was reconstructed from the
current native initializer on copies, with complete restored public-record
identity required. No historical run or combat was replayed. This is enough to
fail V5, not enough to estimate its five positive-state values or generalize
value quality. Main's A20 MAP-only real-root routing remains unchanged.

## Cycle burden

Count permanent cards except Powers, cards that exhaust when played according
to the simulator with their upgrade status, and guaranteed unplayable Ethereal
cards (Ascender's Bane, Dazed, Void, Clumsy). Add two persistent Wounds for Mark
of Pain. No learned feature, oracle, future acquisition knowledge, targeted
exhaust, Corruption synergy or draw-availability estimate. Card-generated
future inserts are not modeled in this deliberately simple quantity.

For the historical 14-card target, five Powers and Ascender's Bane are
excluded, giving burden **8**, versus observed combat minimum **9**. The
absolute error is 1 rather than raw deck size's 5. See [cycle-sanity.json](cycle-sanity.json).
This is a useful approximation, not proof that all exclusions can be played
safely or that an infinity is accessible. All frozen skips leave current deck
size and burden unchanged; the artifact records the counterfactual card-take
counts alongside them.

## Resources and verification

One local lane, OMP_NUM_THREADS=1. The existing particle root stage used
64 particles × four actions = **256 leaf evaluations**, 256 root transitions,
zero terminal root particles, **1.160120286 thread CPU seconds**; launch wall
1.416195275 seconds including model loading and all 18 prior audits. The
3-combat leaf may resolve CTM combats internally; their count was not
separately instrumented. No whole-game campaign, threshold sweep or scientific
retry occurred. No Stage B positive/negative challenge results exist.

Checks: Release build of one_combat PASS; CTest ooc_particle_planner,
ooc_mcts_adapter, heart1_public_record_invariance **3/3 PASS**; Python syntax,
18-row native public parity, six historical custody hashes, frozen binary/model
hashes and deterministic analysis regeneration PASS. Raw logs and receipts are
adjacent. Full all-target build/full CTest and gameplay challenges were not run;
authoritative GitHub Linux GCC CI remains a separate publication check.

An independent reviewer passed the launch after fixing normalization and
fail-closed configuration/coverage checks. Early plumbing previews exposed an
inactive select-screen field and a public Emerald-key offer; both were
restored before values ran. Two attempted previews hit an executable still
being linked and produced no observations. After evaluation, the analyzer's
canonical expected-key check caught the reversed misc/upgrade order in one
derived identity string. [analysis-correction.json](analysis-correction.json)
records that metadata-only repair; inputs-evaluated.jsonl preserves the exact
consumed bytes. All native record/trace inputs and raw outputs are unchanged;
no evaluator rerun was needed. No thresholds or decisions changed.

**Knowledge impact:** current research records the failed separation and stop;
CODE_MAP/build-and-debugging route the offline diagnostic. No production
baseline/model/search behavior changed.

ELI5: “Allow the top four” lets through the harmful skip too. “Stay close to the
favorite” blocks the successful skips as well. The current value estimate sees
too little harm in the bad skip for the fixed tolerance to reject it. These
three safety rules do not give compression search the required safe region.
