# Combat net stage 3a: the net's policy as Silver's root prior (pre-registration)

Status: draft, frozen with the run commit (see `campaign.manifest`). Combat plan stage 3
([plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4)). Stage 2 ended with STAGE3_GO (§771). On 2026-11-08 at
13:26 CET Philipp asked to prepare the next step ("Und bereite hier den nächsten Schritt vor"). The run itself needs
his go and his worker count.

## Question

Production Silver takes its root prior from the g7f_E policy MLP. Does production play Baalorlord's A20 elite and
boss states with fewer HP lost when the combat net's policy supplies that prior instead, at about the same CPU?

## Net and integration (code: see `campaign.manifest`)

- **Net:** `polonly_d1`, stage 2's policy-only net (pretrained on D0, fine-tuned on D1).
  - On the D1 holdout its top-1 agreement with the Gumbel pick is +1.77 pp [+1.34, +2.20] over the g7f_E prior and
    +1.46 pp over the main net N (§771).
  - `model.pt` sha256 `3edda753…d264` (on the PC under `~/combatnet/polonly_d1/`).
  - Native export `polonly_d1.ctn` (`tools/combat_net/export_native.py`), sha256 `3bbf7cf8…1d90`.
- **Native inference** (`sts::search::CombatTokNet`). The encoder is a C++ port of `wire_encoder.encode` plus one
  row of `tensorize.py`; the forward pass is `CombatNet.forward` in eval mode. Three checks:
  - Forward pass: on the 32 D1 gate-holdout rows of the PC parity file (`in_*` tensors, PyTorch 2.5.1 CPU float32),
    the largest absolute difference is 1.9e-6 for N_d1's policy logits, 2.8e-5 for its value logits and 3.6e-6 for
    its aux outputs. polonly_d1's differences are 1.1e-6, 4.5e-7 and 1.4e-6.
  - Encoder: on 5,369 D1 roots (all usable roots of 3 D1 units, training split), every array equals the Python
    path (`wire_encoder` → `tensorize` → `collate`) exactly. This includes the float16 groups.
  - ctest `combat_tok_net_parity` covers 16 D1 rows with a small untrained net. It checks encoder and forward pass
    against PyTorch, and its rows include queues, card-select screens, status pairs and 3+ monsters.
- **Hook** (`STS_SILVER_COMBATNET_PRIOR`, thread override for arms, default off). At every searched root where
  production's root prior is on, the root prior becomes softmax(logits / T) over the root's edges.
  - Unchanged: the weight (400), the bonus and the Gumbel root's use of the prior.
  - Still g7f_E: the tree prior at decision nodes with ≥ 8 visits, the rollout card table and the boss-room prior
    playouts.
  - Cost: one forward pass per searched root, about 2.5 ms on one cloud core (d 128, 4 layers, 32 tokens on
    average). Production decisions take about 50 ms here (13 µs per simulation, about 3,800 simulations), so the
    forward pass alone adds about 5 % CPU.
- **Temperatures,** fixed before the run from D1 validation (h = 1: 4,235 multi-edge roots, 8 runs), not from these
  states:
  - `cnp100`: T = 1. This minimizes the cross-entropy to the teacher's visit shares: 1.550, against 1.562 at T =
    0.75 and 1.562 at T = 1.5.
  - `cnp55`: T = 0.55. This matches the mean entropy of the g7f_E prior, which production's weight 400 was tuned
    with: g7f_E 1.374 nats, the net 1.371 at T = 0.55 and 1.548 at T = 1. At T = 1 the net's prior is flatter (its
    top edge gets 0.34 on average, g7f_E's 0.42), so the same weight gives a weaker bonus.

## Design

- **States, environment and copy seeds** are §770's (teacher check), arm by arm:
  - States: §711's 329 vanilla-RNG Baalorlord runs (`units.txt` = §711's), every act-1-3 elite and boss fight inside
    the exact-replay prefix. These are external run seeds of §694; no new seeds and no 111xxxxxx block.
  - The states are exploratory: §711, §716, §718, §765, §770 and the running Gumbel budget check used them. No
    Baalorlord state entered D0 or D1, and stage 3 trains nothing on them.
- **Mode:** `one_combat expertfights` with `run_unit.sh`. That script is §770's, except for three lines: the arms,
  the model input and its load check (rc 92).
  - In every elite and boss fight, production and each arm play copies 0-3 on the same copy seeds. Copy 0 uses the
    game's battle seed.
  - Production plays the main line, as in §770.
- **Production:** today's A20 combat (learned stop, exact root budgets, g7f_E root table and prior, tree prior K = 8,
  boss-only prior playouts).
- **Arms:** `cnp100` and `cnp55`. Each is production with the net's root prior at the temperature above, and nothing
  else changes.

## Endpoints and analysis (fixed; `analyze.py`)

`analyze.py` is §770's with the two arms. HP lost per copy = entry HP − exit HP, with exit 0 on a loss; floor-51
exits are inverted for the Act-4 heal. Units with rc ≠ 0 are excluded, and the RESULT reports the unit tally by rc.
Each side's value is the mean over its 4 copies. Drops are as in §711. CIs come from a run-clustered bootstrap with
10,000 resamples and seed 20261108. Each arm is judged on its 97.5 % CI (two arms, Bonferroni).

- **Primary, per arm:** mean over all act-1-3 elite and boss fights of (arm − production) HP lost, CI [lo, hi].
- **Validity:** the campaign is INVALID if more than 1 % of the arms' copies show no net prior
  (`combatNetPriors` = 0; the arms then did not use the net). An arm whose CPU ratio to production is above 1.25 is
  not judged. In both cases nothing is concluded for that arm.
  - Why 1.25 and not 1.0: the net costs about 2.5 ms per decision, and production decisions take about 50 ms (smoke
    below). A different prior also changes where the search spends its simulations.
  - Extra CPU alone buys production little on these states: §770's rpl4 at 3.36× CPU gained −0.07 HP [−0.31,
    +0.17]. So a ratio up to 1.25 cannot explain a gain by itself.
- **Decision rule (applied by hand):**
  - An arm with hi < 0 → **PRIOR_BETTER.** The arm with the lower mean becomes the candidate for a whole-run SPRT
    A/B, which needs its own pre-registration and Philipp's go.
  - Otherwise, both arms with lo > −0.5 → **NO_GAIN.** Neither arm gains 0.5 HP per fight or more.
  - Otherwise → **INCONCLUSIVE.**
  - Separately, an arm with lo > 0 is reported as **WORSE.**
  - No default changes on this result.
- **Co-reported:**
  - Descriptive, 95 % CIs: cnp55 − cnp100, production − expert.
  - Per side: deaths and potions per fight, CPU ratio, simulations per decision and net priors per decision.
  - Breakdowns by act, by room, by act × room and by encounter (n ≥ 20).
  - Context only, not paired with this run: §770's Gumbel root at 16,000 simulations, −0.88 HP per fight at 3.15×
    CPU.

## Caveats fixed in advance

- The net learned from the Gumbel teacher's visit shares on self-play runs (student_sel's decks and paths). Its
  policy can be off on Baalorlord's decks, which differ from the bot's.
- Only the root prior changes. Below the root Silver still runs on g7f_E, so a stronger effect could need the tree
  prior too. At this net's cost, that would not be equal CPU.
- §770's caveats hold: the main line is production's, the arms are correlated with production on the same copy
  seeds, and most fights end the same on every side.
- Temperature 1 and 0.55 are the only values tried. Neither was tuned on these states.

## Cost and workers

§770 ran production plus four arms at 9.3× production CPU in 132 lane-hours, so production alone is about 14
lane-hours. Production plus two arms at about 1× each comes to about 45 lane-hours in 329 run units of 1-20 min.
With 10 workers × 4 lanes that is about 1.5 h. Philipp sets the worker count. The Gumbel budget check holds 40
workers until it finishes, and 40 is the project cap.

## Smoke (2026-11-08, cloud, this `run_unit.sh` and the branch's binary; not part of the analysis)

§770's two smoke units, 1675881103 and 1648247344:
- Both rc 0, at 56 s and 383 s wall. The log shows the model line, and 18 elite and boss fights were kept with 0
  dropped.
- **Production is unchanged:** all 72 production copies equal §770's on won, exit HP, exit max HP, turns, decisions
  and simulations. HP lost per fight is 4.89, as in §770's smoke.
- **The arms used the net:** none of the 144 arm copies lacks a net prior, and there are 0.95 net priors per
  decision. The other decisions have one action left after pruning, so they get no root prior.
- **CPU and budget:** CPU ratio to production 0.99 (cnp100) and 1.07 (cnp55). Simulations per decision: production
  3,954, cnp100 3,875, cnp55 3,990. In unit 1675881103 alone, cnp100's ratio was 1.20, which shows how noisy the
  ratio is on few fights.
- HP lost per fight (2 runs, no CIs): cnp100 4.15, cnp55 5.94.

## Amendment 1 (2026-11-08, before any campaign unit ran): a flat-budget pair

**Why.** At 18:03 CET Philipp asked whether the learned stop should be off for this test.
- The stop model (`gbt-0cac7cc64364`) sees only root visit statistics: top and second share, gap, entropy, Q gap,
  leader streak and the lock.
- It was trained on searches that used the g7f_E prior.
- A different or sharper prior concentrates visits differently. Under the learned stop, the primary contrast
  therefore mixes the prior's quality with a change in where the search stops.
- The primary question stays as it is, because it is what production would play. The pair below measures the prior
  at equal simulations.

**Added arms.** These use the same states, copy seeds and environment. Production and the two primary arms are
unchanged.
- `flat4000`: production with a flat 4,000 simulations at every root (one-action roots searched) and no learned stop.
  4,000 is about production's mean simulations per decision on these states (smoke: 3,954).
- `flat4000+cnp100` and `flat4000+cnp55`: `flat4000` with the net's root prior at T = 1 and T = 0.55.

**Secondary endpoint, per flat net arm.** The mean over the same fights of (arm − `flat4000`) HP lost, with CI [lo,
hi]. The CI is the run-clustered bootstrap above, at 97.5 % (two arms, Bonferroni, a family of its own).

**Secondary decision rule (by hand):**
- An arm with hi < 0 → **FLAT_PRIOR_BETTER.**
- Otherwise, both arms with lo > −0.5 → **FLAT_NO_GAIN.**
- Otherwise → **FLAT_INCONCLUSIVE.**
- Separately, an arm with lo > 0 is reported as **FLAT_WORSE.**

**Validity:**
- The 1 % no-net-prior rule covers all four net arms.
- A flat net arm whose CPU ratio to `flat4000` is above 1.25 is not judged.
- Leak check: production's and `flat4000`'s net-prior counts must sum to 0. Otherwise the campaign is INVALID.

**Reading, fixed now:**
- Primary PRIOR_BETTER: as above. The secondary result does not change the primary decision.
- Primary not PRIOR_BETTER, secondary FLAT_PRIOR_BETTER: the prior is better at equal simulations, and under the
  learned stop that gain does not show. The next step is a stop check with the net prior (a stop trace), not a
  whole-run A/B.
- Both NO_GAIN: the net's root prior does not help on these states, with or without the stop.

**Co-reported (95 %, descriptive):** `flat4000` − production, and `flat4000+cnp55` − `flat4000+cnp100`.

**Cost.** Five arms plus production at about 1× production CPU each come to about 85-90 lane-hours. With 10
workers × 4 lanes that is about 3 h, at 2-50 min per unit. Workers: 35. At 18:21 CET Philipp asked for 36 ("also
sollten wir das ganze auf 36 workern laufen lasssen können"), but 5 Gumbel workers still ran, and 35 is what the cap of
40 leaves.

**Smoke (2026-11-08, cloud, same two units and binary as above; not part of the analysis):**
- Both rc 0, at 112 s and 796 s wall (2.1× the first smoke's).
- Production's 72 copies again equal §770's. `cnp100` and `cnp55` repeat the first smoke exactly.
- The flat arms ran 4,000 simulations per decision. The flat net arms had 0.96 and 0.95 net priors per decision with
  0 copies lacking one. The leak check sums to 0.
- CPU ratio to `flat4000`: 1.03 (`flat4000+cnp100`) and 1.09 (`flat4000+cnp55`). `flat4000` to production: 1.00.
- HP lost per fight (2 runs, no CIs): `flat4000` 6.69, `flat4000+cnp100` 5.33, `flat4000+cnp55` 6.11, against
  production's 4.89.

## Not in this gate: the leaf (stage 3b)

N's value head predicts the fight's end-HP distribution and death under the teacher, not Silver's leaf formula. At
2.5 ms per forward pass, one net leaf costs about 50 rollout simulations, so a net leaf at every node is far from
equal CPU. Stage 3b needs its own design and pre-registration. The candidates:
- the value only at the root's children, as a Q initialization worth a few virtual visits;
- a much smaller distilled value net;
- calibrating the death probability first (§771 W1).
