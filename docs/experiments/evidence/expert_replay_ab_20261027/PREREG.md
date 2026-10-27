# Expert decisions vs the A20 bot on expert seeds: paired A/B (pre-registration)

Status: frozen before launch. Philipp authorized the run on 2026-10-26 (23:31Z, "Also 16 workers, but work with the
coordinator when to actually run them"); launch timing is agreed with the coordinator.

## Question

How much A20 Heart win rate does today's bot lose to an expert's out-of-combat decisions, with combat held fixed
(Silver, today's A20 default)? Deep-research experiment 3. Fidelity of the replay:
[expert_replay_fidelity_20261026](../expert_replay_fidelity_20261026/RESULT.md) (card offers 93.4%; 258 of 348 runs
exact through act 3) and its [smoke](../expert_replay_fidelity_20261026/SMOKE.md).

## Design

- Seeds: the 329 vanilla-RNG Baalorlord Ironclad A20 runs (`units.txt`, run ids) out of 348: the 19 runs that started
  with the unmodeled two-option Neow blessing are excluded (their expert arm would be the bot from floor 0). External
  seeds, outside the project's 111xxxxxx blocks; the run files are the frozen input `expert_runs.tar` (third-party
  data, project share only; sha256 in `campaign.manifest`).
- Arms, both per seed, order rotated by run id (`run_unit.sh`):
  - **X**: `one_combat expertreplay` with `STS_EXPERT_REPLAY_TYPES=all`. The expert's logged path, rewards, chests,
    campfires, shops, boss relics, events and Neow are replayed while the engine's offer equals the log and the action
    is legal; at the first decision that is not, or at the end of the log, or at Act 4, the A20 default chain plays the
    rest of the run. Unlogged picks (Bottled cards, Astrolabe, Match and Keep, old Neow sub-choices) are the bot's.
  - **B**: the same binary and mode with `STS_EXPERT_REPLAY_TYPES=none`: the A20 default alone.
- Everything else is today's A20 default stack (ADR-0060 Act 4 strong, ADR-0061 map-only OOC search, M0 leaf, default
  CTM, learned Silver stop, flexible keys, `STS_CALLING_BELL_CARD_RNG_FIX` default on). Combat randomness is not
  shared between arms; a game is deterministic given seed and arm.
- Binary and inputs: `campaign.manifest` (code_commit, binary sha256, student_sel `cf6bf7fb…`). 16 workers × 4 lanes,
  queue schedule; 7 h timeout per game (rc 124 counts as a loss and is reported).

## Endpoints and analysis (fixed)

- **Primary:** Heart-kill rate X − B, paired over the 329 seeds, with a 95% paired bootstrap CI (10,000 resamples
  over seeds) and the exact McNemar test on discordant pairs.
- **Secondary (descriptive):** Act-4 reach rate X − B; mean final floor; the primary difference split by how far the
  replay ran (stopped in act 1 / act 2 / act 3 / replayed through act 3 or the expert's death); replay stop reasons;
  expert's own result vs both arms; mean wall per arm.
- Intention to treat: every seed counts in its arm whatever the replay stop floor. A game that fails (nonzero rc after
  the queue's retries) is reported and excluded pairwise.
- Expectation (a guess, not a gate): X ≥ B. Baalorlord wins 425/676 (63%) of his A20 runs; the bot's Heart rate is
  ~25%. This is a measurement, not a default change; no default changes on its result.

## Cost

Smoke: mean 925 s (X) and 405 s (B) per game, longer for games that reach the Heart. 658 games ≈ 120-170 core-h; on
16 workers × 4 lanes about 2-3 h wall plus a straggler tail.
