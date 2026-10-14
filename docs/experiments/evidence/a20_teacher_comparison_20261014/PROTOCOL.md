# A20 combat teacher pilot — frozen design before collection

Status: preparation; no scientific seed has been run. The executable, reviewed
source SHA, complete environment and artifact custody must be frozen in
`freeze.json` before the canary. This is a small diagnostic, not qualification
of a model, a controller, an OOC teacher or a production default.

## Question and competing explanations

Can simulated Silver combats provide useful offline OOC teacher transitions
at a tolerable cost compared with the PR #524 A20 CTM used in #507? A learned
prior might improve Silver at a fixed search budget; additional simulations
might improve it independently. Alternatively, a stronger controller may
produce more optimistic outcomes than the controller the CTM approximates.
Forecast fidelity, controller outcomes and CPU cost therefore have separate
analyses. None establishes OOC decision quality or student learning.

## Artifact inventory and reuse

- §471 preserves four exact inherited early MAP leaves and repeats, but all
  are correlated floor-zero variants. It cannot answer combat teacher quality
  across fights. The 286 §461 feature rows are not portable full snapshots.
- §§408/410 preserve a CTM versus Silver forecast comparison at A0, with an
  older CTM. Its corrected RAW post-combat HP metric and full-state replay
  mechanism are reusable; its data are not an A20 qualification cohort.
  Prelaunch inspection also found that ordinary battle initialization resets
  four combat streams from `gc.seed + floorNum`, overwriting the harness's
  attempted redraw. The old forecasts share part of the source hidden future;
  their numerical accuracy advantage is not independent-future evidence.
- §411 measured an A0 online Silver resolver at a short leaf horizon. It is
  useful cost evidence, not a full-strength A20 offline teacher comparison.
- §§455/460 tested general MLP tree priors at A0. Generation 3 at 2k improved
  fight score relative to plain 2,300 simulations at slightly lower CPU.
  Generation 3 was not shown better than generation 1. §403's A20 transfer
  concerned an older GBM prior and does not qualify this MLP at A20.
- The PR #524 CTM's exact FAST4L/STD2 files and candidate manifest are present
  under `build/issue507-pilot/run/ctm/`. Keep these unchanged. The newer §470
  boss-calibrated CTM is a different artifact and is not substituted here.
- The general generation-3 prior is identified by §460 but was absent from
  the inspected local model/build directories and tracked Git trees at design
  time. Its documented source is
  `/mnt/project-files/silver-az-mlp/gen3/model/combat_policy_mlp_gen3.txt`.
  Collection requires the actual file with the expected hash; missing custody
  is not permission to retrain or substitute a different prior.
- **Prelaunch user amendment:** the user reports generation 5 complete and
  generation 6 nearly finished, and requests a newer prior. PR #535 confirms
  the gen5 training window, but no gen5/gen6 model bytes or artifact hashes
  were published in the inspected repository, releases or accessible local
  files. Use the newest completed, exported general MLP from **gen5 or gen6**
  available at freeze; pin its generation, source and SHA256. Do not use an
  in-progress checkpoint or fall back to gen3. The prior is selected by
  completion and custody before seeing any pilot outcome, not by pilot scores.
  The §460 result motivates the architecture/settings only; it does not
  qualify gen5/gen6 at A20.
- **Final artifact selection before any pilot outcome:** the user explicitly
  selected **generation 6 version E**. Its completed export is published in
  [PR #541](https://github.com/pherrman1/sts_ai/pull/541), commit
  `0f1b70f278fbc188d9ab96688d67004855d88db8`, at
  `docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt`.
  Downloaded bytes match published SHA256
  `ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228`.
  This is E (encounter and monster embeddings), not Eenc or the generic gen6
  version-D export. Per the user's instruction, PR #541's v2 support is
  integrated from `main` merge `531db3e33d5c38674b123932f0d701b066ef21a7`;
  there is no separate copy of its runtime change. Review and verify the
  integrated producer before freezing. The exact v2 file is loaded without conversion.
  K=8, weight 400 and root bonus stay fixed.

No qualifying preserved A20 matched transition panel was found. New collection
uses full in-memory fight entries, including path, agent state and RNG, rather
than reconstructing a fight from model input features.

## Fixed arms and state panel

| Condition | Simulations per combat decision | Prior | Redrawn futures |
| --- | ---: | --- | ---: |
| CTM | analytic expectation; 32 persistent-state samples | not applicable | model samples |
| plain2k | 2,000 | off | 4 |
| prior2k | 2,000 | frozen gen6 E MLP, root bonus and tree K=8, weight 400 | 4 |
| plain10k | 10,000 | off | 4 |
| prior10k | 10,000 | same frozen prior settings | 4 |
| control | 10,000 | off | original source future, one replay |

Exact means the requested flat Silver search budget; it does not mean a solved
combat or an optimal player. Disable adaptive and learned stopping. The source
and control force the prior off. Source runs use the existing frozen V4 OOC
policy with OOC MCTS off, A20 Ironclad, Act 3 objective and no Act 4 keys.
This samples ordinary trajectory fights, not hypothetical OOC sibling states.

One excluded canary: **97150701**. Four cohort sources:
**97150710, 97150711, 97150712, 97150713**. These are locally unobserved pilot
seeds, not a claim of a globally sealed holdout. No replacements or extensions.

At most six states per source, chosen solely by chronological slot:

1. First normal fight, first elite and first boss in Act 1.
2. First elite and first boss in Act 2.
3. First boss in Act 3.

Absent slots stay absent. The selected panel deliberately emphasizes elites
and bosses. Deaths shorten source runs; later-act coverage is reported rather
than repaired by adding runs. An unsupported CTM state consumes its slot and
is counted with its reason; it is excluded from the matched comparison.
At most 24 cohort states, 384 Silver forecast fights and 24 controls are
possible, plus the four ordinary source trajectories. Canary costs are extra
and bounded by the same per-source limits.

## Randomness, outcomes and interpretation

Use the harness's existing separate salts for future redraw and planner seed.
The A20-only redraw seeds `mt19937_64(redrawSeed)`, replaces the detached
`gc.seed` with its first draw, then uses six draws to reseed GameContext's
ai/cardRandom/misc/monsterHp/potion/shuffle streams while retaining counters.
Ordinary battle initialization derives its four correlated start streams from
the new `gc.seed + floorNum`; misc and potion use the redrawn inherited streams.
The Colosseum continuation uses the inherited combat streams as normal.
Replicate k has the same initialized combat future and planner seed across
all four Silver arms. Source/control are unchanged. Other hidden state stays
fixed. This is a conditional full-state experiment, not proof of public-input
sufficiency (#506). A synthetic test checks initialized streams, not merely
the GameContext before initialization.

The original source future is independent of the forecast redraw set and
provides a common plain-10k behavioral reference. The original-future control
must reproduce the source fight. Do not score a Silver forecast against a
reference using that forecast's own hidden future: that would give Silver an
outcome correlation unavailable to a marginal CTM prediction.

Use RAW post-combat persistent HP consistently, including combat-end healing;
death maps to HP zero. Do not use battle-end `terminalHp` as CTM truth. Escapes,
unsupported states, invalid source trajectories, missing samples and replay
mismatches receive explicit accounting. No silently pooled partial shard.

The report separates:

- **Forecast fidelity:** CTM death probability and expected HP, or each
  Silver arm's four-draw death fraction and mean RAW HP, scored against the
  independent original-future control (death Brier and HP squared error).
  Four-draw estimates retain sampling error; a single reference outcome is
  noisy. Also report non-HP persistent-state distribution scores where valid.
- **Controller outcomes:** paired prior-minus-plain at 2k and 10k, and
  10k-minus-2k within each prior setting, on the shared redraws. Report death,
  RAW HP and remaining potions separately. A controller can improve outcomes
  while becoming less faithful to the plain-10k behavioral reference.
- **Cost and repeat precision:** observed CPU per simulated fight, per
  four-draw forecast and per decision, CTM expectation/sample CPU, and
  descriptive within-state variance. Equal simulations are not equal CPU.

Each source has equal weight in the principal descriptive summaries; report
source counts, per-source results, selected states and pooled summaries too.
Four source clusters do not justify a population winner, an optimal simulation
budget, a reliable rare-death estimate or a confidence-interval promotion gate.
No bootstrap, significance declaration, training or default changes are made.

## Freeze, execution limits and decision rule

Before collection: focused tests and independent implementation/scientific
review; commit the reviewed source; build the Release executable from that
clean commit; record actual build command/log and executable hash; freeze
every loaded model, candidate manifest, teacher policy, runner, analyzer,
seed guard, protocol and full environment. All seed commands run through the
repository seed guard. Existing evidence and outputs are never overwritten.

Every source is a separate one-thread process. Hard limits: **180 CPU seconds
and 240 wall seconds per source**, at most two concurrent processes and five
attempted sources including the canary (maximum 900 allocated CPU seconds).
No retry, replacement seed, increased budget or outcome-driven early stop.
The canary must finish and pass all artifact/mechanism checks before cohort
launch. A failed canary blocks the cohort. A cohort execution/integrity failure
invalidates the planned panel; preserve partial output and do not infer a
winner from it. Ordinary valid deaths are not execution failures.

The only successful pilot verdict is **DESCRIPTIVE_COMPARISON_MEASURED** when
all four planned source jobs complete, custody/controls/counts pass and each
source contributes at least one matched supported state. Otherwise report
**INVALID_OR_INSUFFICIENT** with the exact reason. Successful collection is
not a SILVER_BETTER or CTM_BETTER verdict. A later OOC sibling-ranking or
student experiment requires a separate design informed by this evidence.

Knowledge impact: new evidence belongs in the experiment ledger and current
research page after execution. The opt-in harness extension belongs in the
maintained evaluation/tooling documentation; production behavior is unchanged.
