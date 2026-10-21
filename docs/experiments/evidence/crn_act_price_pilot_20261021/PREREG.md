# Pilot: CRN paired continuations to the end of the act, as difference labels for a Silver leaf (draft pre-registration, 2026-10-21)

Status: **authorized, not launched.** Philipp 2026-10-21 13:44Z: "Let's do 4 workers to speed it up after the smoke
finishes" (12:57Z/13:06Z/13:24Z: no OOC MCTS, production Silver with learned stop, act-end horizon is fine). Needs a
pre-launch review and a frozen RUN_COMMIT. Background: `/mnt/project-files/silver-leaf-eval/ooc-label-leaf/DESIGN.md`
(gen 1b failed the teacher check).

## Question
Can common-random-number (CRN) paired continuations to the **end of the current act** give difference labels
(price of −HP, −potion, −max HP, −gold in a given context) precise enough to train a per-context Silver leaf price
model, and what would a full data campaign cost? This is a **cost and noise pilot**. It does not test play strength.

## Baseline and existing evidence
- §510: 3-fight CRN continuations, flat potion price 9.9 HP-eq [7.9, 12.3], with per-type spread (Attack 21, Block ≈ 0,
  Fairy 44).
- §537: same design under student_sel. Non-Fairy potion 5.0 [1.8, 8.1], max HP 1.08, gold 0.011. In whole runs those
  prices lost (§542), so **Inference:** 3 fights is too short a horizon.
- §537 raw (w01, 166 states, 1,157 continuations): about **10.5 s CPU per 3-fight continuation** (≈3.5 s per fight,
  flat exact-10k Silver), plus about 90 s per source run.

## Intervention (one variable versus §537: the horizon)
`potionpriceprobe` as in §537, with these changes:
- **Horizon:** continue until the current act's boss fight ends (new `FIGHTS_AHEAD=act`, small default-off PR),
  then value with the bootstrap models at the next battle. This replaces "next 3 fights". Sampled Act-3 states stop
  at the Act-3 boss; Act 4 is excluded.
- **Copies per state** (all CRN): `base`, `hp:-12` (unit calibration), `gold:-50`, `maxhp:-5`, and one copy per
  held potion type removed. No leaf arms.
- **Policy:** student_sel OOC argmax, OOC MCTS off, keys off, Silver on current main defaults set explicitly
  (`STS_SILVER_LEARNED_STOP=1`, prior playouts on real boss/elite fights per ADR-0050; the smoke confirms whether
  continuation fights count as "real"). These are the conditions the leaf would be deployed under, and they are
  cheaper than §537's flat 10k. Silver = g7f_E root table + tree prior (ADR-0049), learned stop (ADR-0051), prior
  playouts on real boss/elite fights (ADR-0050, pinned with STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=1; frozen code predates #775). Fallback if the smoke shows > 30 s per continuation: flat 2.5k
  (§479: −0.68 fight score vs 10k). potionpriceprobe is not a whole-run mode, so learned stop is set explicitly and
  the smoke verifies it is active. (Philipp 12:57Z: no OOC MCTS.)
- **Sampling:** `SAMPLE=all`, 12 battle-start states per source (reservoir), acts 1–3.
- **Deviation from DESIGN.md, stated:** states are battle starts, i.e. after the previous fight's reward and path
  decisions, not raw post-fight states. Close enough for prices. Exact post-fight sampling would need more code.

## Seeds and size
- Sources 111146000–111146063 (64 seeds), smoke 111146900–111146903, reviewer 111146950–111146959.
- About 64 × 12 = 768 states (minus terminal ones) and about 5.2 copies per state, so about 4,000 continuations.

## Cost estimate
- Mean remaining fights to act end from a sampled battle start: about 5 (**Inference**, about 9–10 fights per act).
- Per continuation: about 5 × 3.5 s ≈ 17 s at flat 10k. Learned stop (about 0.5x) and prior playouts (more at
  bosses) roughly offset, so I assume 15–20 s.
- **Measured (smoke, seeds 111146900–903, 35 valid states, acts 1/2/3 = 18/11/6, all rc 0):** 7.7 s CPU per
  act-end continuation, 0.010 core-h per state with all copies (learned stop makes this ~2x cheaper than assumed).
- **Pilot:** ~700 valid states × 0.010 ≈ 7 core-h plus source runs, **about 8–10 core-h**; 4 workers × 4 cores:
  well under 1 h wall per worker (unit timeout 4 h).

## Metrics (primary first)
1. **Per-pair noise:** SD of the paired difference Δ(altFloor) for `hp:-12`, `potion`, `maxhp:-5` and `gold:-50`,
   plus the share of pairs with identical outcomes, all versus §537's 3-fight numbers on the same metric.
2. **HP slope** at the end-of-act horizon (floors per HP), with a seed-bootstrap CI.
3. Price estimates (HP-eq, ratio of means): non-Fairy potion, max HP, gold; per type, descriptive only.
4. Projected campaign size N\* (states) needed for a ±3 HP-eq 95% CI on the non-Fairy potion price within each act
   (N\* = n·(half-width/3)², summed over acts 1–3), and its core-hours at the pilot's measured cost per state.

## Decision rule (pre-registered)
- **GO to a full-campaign proposal** if the HP slope CI excludes 0 **and** N\* for the per-act potion price costs
  ≤ 800 core-h (about one night on 16 workers). The proposal then gets its own pre-registration (GBM over context ×
  Δx, a held-out offline gate against the formula, then a whole-run A/B).
- **STOP** if the HP slope CI includes 0 or N\* exceeds 800 core-h. Then record that end-of-act CRN labels are too
  noisy at affordable cost. The leaf line returns to waiting for a value head that passes the DESIGN.md teacher
  gate.
- In both cases this is descriptive. No leaf weights are taken from the pilot, and no default changes.

## Analysis
`python3 tools/analyze_crn_act_price_pilot.py OUT.json <extracted pilot tars> --compare <extracted §537 tars>`
(written and tested on the smoke before launch; values = A20 floor model `altFloor`; seed bootstrap 2,000, RNG
20261021; HP-eq prices are ratios of means against the `hp:-12` copy). A seed with rc ≠ 0 is dropped and reported;
states whose base copy is invalid or starts at 0 HP (terminal source states) are dropped. Decision field = the rule
above. Smoke output is not part of the pilot data.

## Omissions and risks
- **Divergence:** after the first different decision the copies no longer share randomness. That is the noise this
  pilot measures.
- The floor bootstrap model at act end is a learned value, so its bias enters the labels. It enters much less than
  a value at the post-fight state would, but it is not zero.
- Silver's actual sibling end states (from real search trees) are not used here. Resource copies come first.
