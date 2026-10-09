# #347 default-stack boss deaths: winnable or doomed on entry? (plan, 2026-10-09)

Status: frozen before any seed of this experiment ran. Ledger §417.

## Question and decision

Most default-stack losses happen at an act boss (157 of 202 losses in the §377
learned arm; 13 of 27 corrected-reference losses were final-boss losses in
§395). More boss search did not help (§377 boss 30k, §387 40k), but in §387
three of four flat-10k boss losses won 11 of 12 fresh planner seeds.

For current default-stack boss deaths: if the same boss entry is replayed with
fresh combat-planner seeds, how often does the same combat policy win?

- Mostly won on replay: the deaths are largely combat-planner variance on
  winnable states, so combat (consistency, not budget) is the lever.
- Mostly lost on every replay: the entries are doomed under this combat
  policy, so preparation (OOC decisions, V4) is the lever.

This is a descriptive diagnostic of the default stack, not a win-rate
qualification. No default changes.

## Baseline and stack

Current `main` gameplay at the frozen commit (the research change touches only
the `bossrescue347` diagnostic mode). Environment `env.sh`: the ADR-0026 live
profile (`silver_learned_stop/live_env.sh`: V4 token net and gate stack,
margin 1, keys off, fair Silver, reuse cap `allocated`) plus
`STS_SILVER_LEARNED_STOP=1 STS_SILVER_ADAPTIVE=0 STS_OOC_MCTS=0
STS_STOP_AFTER_ACT=3`. Card removal uses the current default (low weight
first). Ironclad A0, `bestbench` with 10,000 as the Silver cap.

## Why fresh sources (deviation from the brief)

The brief suggested reusing §395 Fprod or §377 learned-arm rows.
- §395 Fprod per-seed rows live only on Philipp's machine, not in the repo or
  the shared folder.
- §377 rows ran on `8c7da1d0`; later gameplay fixes (Gremlin Leader, Smoke Bomb,
  #420, #421) and the removal default flip mean current `main` cannot
  reconstruct them, and porting the mode to that commit would study an older
  stack.

So stage 1 generates new default-stack runs on the next free seed block,
66000000..66000255 (256 seeds). Stage 2 reconstructs each boss death with the
same binary.

## Replay arm (deviation from the brief)

The brief suggested flat exact 10k replays. The default stack's combat policy
is learned stopping (10k cap), and the source fight can only be reproduced
under that policy, so every replay uses it. Flat exact 10k at the boss would
need a boss-multiplier override in the mode; §377 found learned stopping and
flat budgets similar, and §387 already measured flat 10k.

## Stage 1: sources

`source_run.sh`: four shards of 64 seeds, one CPU each, through
`tools/seed_guard.sh`, `bestbench 10000 64 0 <start>`.

## Selection (frozen rule, `select_deaths.py`)

Eligible: `won == 0` and the recorded `deathEncounter` is an act boss (enum
parsed from `MonsterEncounters.h`). All eligible deaths are selected, up to 48
by ascending `sha256("boss-deaths-347-v1:{seed}:{act}")`. Expected about 39
(157/1024 × 256). No replacement and no extension: if fewer than 24 qualify,
the result is reported as is with the smaller sample.

## Stage 2: replays (`run.sh`, `bossrescue347` schema `boss_deaths_default_347_selection_v1`)

Per entry, one process under `env.sh`:
1. Reconstruct the run with `runFullRunOOC` and capture the boss entry
   (`t_bossEntryHook`: detached `GameContext` copy with all RNG streams, path,
   agent, OOC policy state). The reconstructed run must equal the stage-1 row
   on all eight fields, the hook must see the recorded boss and the fight
   must be lost.
2. `control`: original planner seed. Must reproduce the source fight exactly
   (outcome, terminal HP, full action trace, post-exit state digest,
   simulations).
3. Eight `fresh` replays, planner seed
   `int(sha256("boss-deaths-347-planner-v1:{seed}:{act}:{rep}")[:16], 16)`,
   rep 0..7. Only the search's seed changes; the live battle's RNG streams
   are untouched.
4. `control_repeat` and `fresh_repeat` (rep 0) must equal the first runs.
5. Every row starts from the entry digest; every searched root uses at most
   10,000 steps and `simulations == searchSteps`.

An entry failing any check is `INVALID`: kept, reported, not replaced and not
classified.

## Decision rule (`analyze.py`)

Per valid entry, w = fresh wins out of 8:
- `DOOMED`: w = 0
- `MARGINAL`: 1 ≤ w ≤ 3
- `WINNABLE`: w ≥ 4

Verdict over valid entries:
- `COMBAT_VARIANCE_DOMINANT` if at least half are `WINNABLE`;
- else `PREPARATION_DOMINANT` if at least half are `DOOMED`;
- else `MIXED`.

Also reported: mean fresh win rate over entries with an entry-level bootstrap
95% interval (10,000 replicates, seed 20261009), the distribution of w, and
breakdowns by act and boss with entry HP, deck, upgrades, relics and potions.

## Caveats stated in advance

- Planner repeats share one environment; they are not independent game
  futures. Card draws and enemy rolls follow the fixed RNG streams, though
  different play consumes them differently.
- Entries are selected on a lost fight, so replays regress toward the entry's
  true win rate; that regression is what is measured.
- `DOOMED` means doomed for this combat policy at 10k, not unwinnable in
  principle. `WINNABLE` does not say which combat change would fix it.

## Cost

Stage 1: 256 runs at about 24 CPU-s ≈ 1.7 core-hours. Stage 2: about 39 entries
× (one run to the boss + 11 boss fights) ≈ 1 core-hour. About 3 core-hours on
one 4-CPU cloud container, within Philipp's authorization for this thread.
