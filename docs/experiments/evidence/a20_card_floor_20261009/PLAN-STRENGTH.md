# A20 combat-strength card probe (plan, 2026-10-09)

Written and committed before any probe run. It follows §409 and §413, where
models trained on whole-run floor labels did not beat the teacher's card picks.
Philipp chose to test his "combat strength" idea next: value a state by how
well its deck fights the enemies still ahead, not by a whole-run outcome.

## Question

Does a training-free strength score rank the A20 card-reward options better
than the teacher's pick, measured on floor reached? The score is the CTM's
expected fight utility against the act's remaining enemies.

## Why

- Whole-run labels bury one card's effect under run noise of about 8 floors
  per future, against about 2 floors of option spread (§402, §409).
- One fight's expected outcome is far less noisy, and the CTM gives it in
  milliseconds.
- If strength separates cards in the right direction, a learned strength leaf
  is worth proposing. If it does not, the result is cheap to learn.

## Data

- **Source runs:** the §402 corpus seeds 59100000..59101199 at ASC 20, replayed
  with `one_combat cardstrengthprobe` to the same sampled decisions. The probe
  copies the corpus selection rule (`ooccfpilotgen` GEN=2, STATES=2,
  TYPES=CARD_REWARD,BOSS_RELIC) and teacher configuration (`run_corpus.sh`
  environment, teacher frozen with `make_teacher.py` at the probe commit). The
  game code is unchanged between the corpus commit 5ba068e0 and the probe
  commit (`git diff 5ba068e0 -- src apps` touches only the probe mode).
- **Seeds run:** only TRAIN and VALIDATION sources under `source_split`. TEST
  seeds are not replayed; they stay closed for a later learned leaf.
- **States scored:** corpus card rewards with:
  - acts 1 to 3;
  - exactly one chosen option and at least two options;
  - valid corpus labels (`apply_rules`).

  Boss card rewards whose map row lies in a later act are excluded (the §413
  leak rule).
- **Trajectory check:** a replayed state counts only if every option has the
  same key and chosen flag as in the corpus, and its rich row after the pick
  equals the corpus `options.csv` row (the four HIDDEN_FUTURE fields
  excluded). A mismatched state is dropped and counted. If more than 5% of
  eligible states mismatch, the run is `INVALID`.

## Strength score (fixed before the run)

For each option, the post-pick state is evaluated against the act's
encounters by the production default CTM stack. That stack is the lizard T2
DeepSets model with the near-full brew fallback, active Lizard, and the
OOC MCTS Smoke Bomb mask. Each fight is scored with the existing boss-leaf
utility:

`u = 0.75·P(survive) + 0.25·P(survive)·E[end HP fraction | win]`

The starting HP is the state's current HP.

**CTM input at ascension 0.** A one-seed mechanism smoke (seeds 59100000 and
59100001, before any scoring) showed the production CTM is degenerate at
ascension 20. With ASC 20 in the input it returned death 0 and one fixed HP
fraction for every encounter and every option: 1.0 at 75/75 HP against Donu
and Deca, and 0.62 for all 17 act-2 encounters. Its scalar normalisation puts
ASC 20 far outside the training range. The brew fallback was flat as well
(death 0.063 for every act-2 encounter). With ASC 0 in the input, the same
states give encounter-dependent values. The probe therefore prices each deck
at ascension 0: a strength proxy against the act's enemy types, not an A20
survival estimate.

**Pools** (acts 1 to 3):

| Pool | Encounters | Pool value |
|------|------------|------------|
| Weak | the act's weak list | weighted with the simulator's weights |
| Strong | the act's strong list | weighted with the simulator's weights |
| Elite | the act's three elites | uniform |
| Boss | the act's revealed boss | single encounter |

**Counts:**

- `cMonster` and `cElite` are the reachable monster and elite nodes ahead in
  the act, from the public forward-map features.
- Weak fights left: `nWeak = min(max(0, W − monOffset), cMonster)`, where W
  is 3 in act 1 and 2 otherwise, and `monOffset` is the number of hallway
  fights already drawn this act.
- Strong fights: `nStrong = cMonster − nWeak`.
- The boss counts once.

**Score:**

`S = (nWeak·U_weak + nStrong·U_strong + cElite·U_elite + U_boss) / (nWeak + nStrong + cElite + 1)`

**Unsupported encounters:** an encounter the CTM does not support for any
option of a state is dropped for every option of that state. A state that
loses a whole pool it needs is reported as unscored.

**Pick:** the highest S. Ties within 1e-12 go to the teacher's pick if it is
tied, otherwise to the lowest option index.

## Metric and decision rule

- **Metric:** selection gain in floors over the teacher's pick, as in §409.
  It is computed per state from the option's mean `horizonFloor` over the
  corpus futures, with a 95% bootstrap CI that resamples source seeds (2,000
  reps, seed 0).
- **Primary set:** TRAIN and VALIDATION together. Nothing is fitted.
- **Rule:**
  - `PASS` if the CI lower bound > 0. Then a learned strength leaf trained on
    Silver or CTM labels is worth a proposal.
  - `NOT_SHOWN` otherwise.
  - `INVALID` if the trajectory check fails.
- **Diagnostics, not part of the rule:**
  - each split and each act separately;
  - agreement with the teacher;
  - skip rate of the probe and of the teacher;
  - median score spread between the best and worst option;
  - oracle and uniform-random gains.

## Cost and provenance

- **Implementation:**
  - the default-off mode `one_combat cardstrengthprobe` in
    `apps/one_combat/combat_datasets.cpp`, registered in `tools/seed_guard.sh`;
  - analysis in `tools/a20_card_strength.py`;
  - the runner `run_strength.sh`, called as
    `run_strength.sh BINARY FROZEN_SHA OUT 59100000 1200 4`. It runs one seed
    per call through the seed guard and skips TEST seeds.
- **Mechanism smoke (done before freezing):** seeds 59100000 (TRAIN) and
  59100001 (VALIDATION). Both decisions matched the corpus exactly (option
  keys, chosen flags and 1,013 rich-row fields), with no unsupported
  encounters. A perturbed rich row was correctly rejected. These two states
  are part of the primary set; their outcomes were printed by the smoke and
  are not used to change anything here.
- **Run:**
  - about 1,030 source replays at about 12 CPU-s each (the corpus mean
    `sourceCpuSeconds`), plus about 4 options × 19 CTM probes per state;
  - about 3.5 CPU hours in total, about 1 hour on 4 cloud cores;
  - every command goes through `tools/seed_guard.sh`.
- **Seeds:** existing corpus seeds only, no fresh seeds. It runs only after
  Philipp's go.
- **Not in this version:** next-act bosses, event fights, and the Silver check
  of the CTM's per-card ranking from the draft. The Silver check is the
  natural follow-up if the CTM's option spread turns out too small to rank.

## Known caveats

- The CTM was trained on A0 fights, and is evaluated here at ASC 0 (see
  above). A20 enemies hit harder and have more HP, so the score understates
  danger. Whether the ASC 0 card ranking transfers to A20 is exactly what the
  floor-reached metric tests.
- The score ignores the order of fights, HP carried between fights, rests and
  upgrades. It is a strength proxy, not a run simulator.
