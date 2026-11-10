# Traced replay of the §775 whole-run Gumbel test, arms D and G16 (pre-registration)

Authorization: Philipp 2026-11-10 00:22 CET ("Jo klingt gut, go", trajectory-review thread) to the plan "Spur-Replay von
D und G16 mit etwa 218 Lane-Stunden" on 40 workers, which the coordinator assigns after the node-cap test.
Context: rank 1 of the trajectory review (https://claude.ai/artifact/48KD6wyhCLC8GZHzbEAVSR, addendum). §775's logs
hold one summary line per game, so HP per fight, HP and potions at boss entry and the fight that killed a run are
missing. The end-floor analysis attributes 42% of G16's Heart-kill gain to Act 1-3 path floors, which the HP-per-fight
proxy (§770, §772, §774: elite and boss fights only) never measured.

## Design

- Replays, not new games: seeds 111378256-111379279 (the §775 block, no new seeds), arms D (A20 default combat) and
  G16 (Gumbel root k 16 + max backup 4 at 16k in every fight), net-0420 as the whole out-of-combat policy, the same
  binary (0eabb014, code 5665d5ae, from the cache), the same environment as §775's run_unit.sh, plus
  STS_OOC_DECISION_TRACE (apps/one_combat/run_driver.cpp), which only reads state. Per seed D, then G16.
- Units: make_units.py packs consecutive seeds into 271 units of at most 3,600 s of §775 wall (D + G16) or 12 seeds;
  the longest unit is about 78 min, the mean about 48 min. Packing keeps the share's file count down: the share is near
  its 50,000-file limit while the node-cap test runs.
- Determinism check before freezing: 6 local replays (D and G16 on 111378256, 111378337, 111378451) with this binary
  and the games' own .env reproduced §775 exactly, including G16's Gumbel root and simulation counts, and this
  run_unit.sh on 111378484 and 111379153 (one unit) also reproduced them. The tuning thread re-checked 32/32 G16 games.
- Cost: §775's walls for D and G16 add up to 218 lane-hours (D 72, G16 146), about 2.7 h on 20 workers x 4 lanes
  plus the tail of the last units, or about 1.4 h on 40 workers.

## Analysis (analyze.py, frozen; descriptive, no gate, no default change)

1. Validity: a game counts only if it reproduces §775 (rc 0, BEST line, [heart1_ppo] game line, for G16 the Gumbel
   roots/sims line). Seeds with a non-reproducing game are listed and left out; more than 10 such games = REPRO_FAIL.
   Units that fail or time out are listed like non-reproducing games; nothing is imputed.
2. Per fight class (act x room, Act 4 Shield and Spear and Heart): deaths per fight, HP lost per won fight (pre minus
   post HP; post includes on-victory heals), potions used per fight, turns; G16 - D with a seed-cluster bootstrap.
3. State at entry of the Act 1-3 bosses (both Act 3 bosses), Shield and Spear and the Heart: HP, HP fraction, potions
   held, deck size.
4. The fight that ended each lost run, per arm and on the seeds where only one arm killed the Heart.
5. First divergence: each seed's first fight whose post state differs between the arms starts from the same state in
   both, so G16 - D in post HP and deaths there is a paired fight-level comparison on natural run states, by class.

Readings planned: whether G16's advantage per fight is larger in normal fights than in elite and boss fights, and
whether the Heart gain comes from search (first-divergence and per-fight numbers) or from a better entry state.
Result goes to RESULT.md and a ledger entry (descriptive).

## Outputs

Per game ARM-SEED.{done,log,err,env} and ARM-SEED.trace.jsonl.gz (a G16 Heart-kill trace is about 8 KB gzipped).
Share /mnt/project-files/gumbel-wholerun-trace: about 1,200 files in all (271 unit tars, about 900 claim files at 3 per
claim, up to 20 wWW.DONE.json, the brief) and about 15 MB. Snapshot claims/ into claims.txt before any cleanup of
claims/.
