# Privileged encounter lists in the offline critic (issue #1050 stage 0), pre-registration

Issue [#1050](https://github.com/pherrman1/sts_ai/issues/1050) proposes an asymmetric PPO critic: in training only,
the value head would also see the act's pre-generated encounter lists. Stage 0 asks, offline, whether that
information is worth anything before any PPO change. Philipp, 2026-11-15 17:08 CET: one thread per issue of today,
work each one off. Offline only: no seeds are played, no games, no workers.

## Question

§761 found that no public offline estimator beats LONG_C's online critic in act 1 (EV 0.072, AUC 0.67), so act 1 looks
near its public ceiling. How much of the remaining act-1 outcome variance do the encounters still ahead in the act
explain?

## What the privileged information is

`GameContext::generateMonsters` fills, at each act start, `monsterList` (normal encounters: 3 weak + 1 + 12 strong in
act 1, 2 + 1 + 12 in acts 2-3), `eliteMonsterList` (10 elites), `boss` and, in act 3 at A20, `secondBoss`.
`monsterRng` is used nowhere else (only `generateMonsters` and the regeneration when a list runs out), so the lists of
acts 1-3 are a function of (seed, ascension) unless a list runs out. Rooms consume them in order
(`getMonsterForRoomCreation` / `getEliteForRoomCreation`); which and how many depend on the path. The record's
`obs.v2.fought` is exactly the consumed prefix `monsterList[:offset] + eliteMonsterList[:eliteOffset]`
(`heart1_policy.cpp::encodeObservation`), so the offsets of every decision follow from the record and the table.

- The new binding `slaythespire.act_encounter_lists(seed, ascension)` returns the lists of acts 1-3 (GameContext at
  the seed, then `transitionToAct(2)`, `transitionToAct(3)`). The GameContext also exposes `monster_list`,
  `monster_list_offset`, `elite_monster_list`, `elite_monster_list_offset`, `second_boss`.
- Table: `critic_ceiling.py encounters --seed-range 111654400 111758399 --ascension 20` (LONG_C iterations 220-419,
  104,000 seeds), `critic_encounters_long_c_220_419.json.gz`, sha256
  `21e81001bcddaf5ed8d9cdcf15eaff40126d5ecd55447becb74fe26791c7ad63` (gzip header without name or mtime, sorted keys: reproducible).
  Transported to the PC as ref `ppo-xfer/critic-enc`.
- Mapping check before this PREREG (no outcome read): `check-encounters` on LONG_C iteration 419 (the 40 parts in
  refs `ppo-xfer/gn/LONG_C/traj-0419-p*`, part of the test set) and on cov8: every act 1-3 net decision
  (54,916 + 933) has `fought` equal to the table's consumed prefix and the recorded act boss equal to the table's boss.
  Most consumed in one act: 9 normals, 5 elites, so no list ran out.

## Data (as §761, same split)

- Test: LONG_C iterations 0400-0419 (800 parts, 10,400 games). Training: LONG_C 0220-0399 (7,200 parts), `--per-game
  8`, `--game-frac 1.0`, 5% seed-hashed early-stopping split, `--exclude-from` the test parts.
- Before any fit, `check-encounters` must pass on all 8,000 parts (it stops at the first mismatch, a seed missing from
  the table, a boss mismatch or a used-up list). If it fails, the run stops and the failure is reported.
- If a fit hits the RAM guard (MemAvailable < 4 GB, as in §761), all three GBM fits are redone at `--game-frac 0.5`
  so the comparison stays paired. The value used is reported.

## Estimators

- **online**, **online_cal**: as §761 (logged actor value; per-act Platt on the training parts' logged values).
- **gbm**: §761's GBM (every public record field, `flat_features`), refitted with this code and the §761 settings
  (depth 6, eta 0.05, up to 3,000 rounds, early stopping 100, min-count 20, 4 threads).
- **gbm_enc** (primary): the same GBM, same rows and settings, plus `encounter_features(scope="act")`: for the
  current act (1-3) the next 8 unconsumed normal encounters by position (`enc_n{i}_{id}`) and their counts
  (`enc_ncnt_{id}`), the next 4 unconsumed elites by position and counts (`enc_e{i}_{id}`, `enc_ecnt_{id}`), and in
  act 3 the second boss (`enc_boss2_{id}`). The act boss is public and already in the record. Act 4: no features.
- **gbm_run** (descriptive): `scope="run"`, additionally the later acts' lists from their start (8 normals, 4
  elites by position and count) and their bosses (incl. the act-3 second boss). This bounds the "several acts ahead"
  variant in the issue's "Later" section.

## Metrics

Per scope (first decision, acts 1-4, all): AUC, log loss, Brier, EV against the outcome, sd of GAE advantages
(λ 0.97 and 1), as §761. Paired game-cluster bootstrap (2,000 resamples, seed 20261106) of the differences
gbm_enc − gbm, gbm_enc − online_cal, gbm_run − gbm, gbm_run − gbm_enc on every scope, 95% CIs.

## Decision rule (fixed before any score is read)

`evaluate --rule encounters --enc-ev-margin 0.03` (`verdict_encounters`). **GO** for step 1 (a privileged critic in
PPO, a separate proposal that needs Philipp's typed go) if all three hold on act-1 decisions:

1. EV(gbm_enc) − EV(gbm) ≥ +0.03 (point estimate; the bar the issue suggests);
2. its 95% CI lies above 0;
3. EV(gbm_enc) − EV(online_cal) has its 95% CI above 0 (the privileged estimator beats the critic PPO has now).

Otherwise **NO_GO**: the asymmetric critic (step 1) is dropped, and step 2 of the issue via the privileged critic
with it. Log loss, acts 2-4, the first decision and gbm_run are descriptive. The three conditions are required jointly
(intersection-union), so no multiplicity correction is applied.

EV is offset-invariant (Var(y − v)), so the policy shift between training and test iterations (§761's known bias)
does not by itself cost EV; it can cost log loss, which is why log loss is not in the rule.

## Known limits

- A GBM with indicator features may not use the information as well as a net would; a NO_GO bounds this model
  class at this data size, as §761 did.
- Only the encounter identities enter, not their per-fight details (monster HP rolls, move choices), which come from
  other RNG streams and are not part of this question.
- The outcome is a Heart kill: an encounter can change the act-1 survival without moving the Heart kill much.
  Acts 2-4 are reported for that reason.

## Cost

PC CPU (4 threads, nice 10), about 2-3 h: the check over 8,000 parts, three GBM fits of about 10-20 min, one evaluate
of about 1-1.5 h. The PPO learner of PG16H24 keeps the GPU; this run uses no GPU. No cloud core-hours, no seeds.
