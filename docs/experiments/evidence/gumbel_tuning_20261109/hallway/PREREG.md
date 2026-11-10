# Gumbel tuning, hallway test: c2 against the control on hallway fights (pre-registration DRAFT)

**Status: DRAFT, not frozen, not launched.** It waits for Philipp's typed go with a worker count and for a prelaunch
review; the cost section is filled from the smoke before freezing.

Follows the whole-run test ([../wholerun/RESULT.md](../wholerun/RESULT.md), §777): stage 2's pick c2 lost 4.69 pp of
Heart kills against §775's G16 + mb4 in whole runs. Its excess deaths are resolved only in act 2 outside the boss,
where hallway fights dominate, while the tuning (stages 1 and 2) played only elite and boss fights. This test measures
c2 on the fights the tuning never saw.

**Authorization.** Philipp, 2026-11-09 23:30 CET (decision card "Welcher Test soll als Nächstes laufen?", option "Nur
Hallway-Test"); the launch waits for his typed go with the worker count. The node-cap test (wholerun PREREG, Test 2)
is not part of this and waits.

## Question

Does c2 lose more HP per hallway fight than the control (`gsh16+flat16000+mb4`, the stage-2 control and §775's G16 +
mb4 setting) on production A20 states?

## Design

- `one_combat selffights` as stages 1 and 2 (`../run_unit.sh`'s production environment: A20, student_sel out of combat
  with OOC MCTS, production Silver with the learned stop): the main line is the production run; at every arm fight
  both arms play copies 0-3 on the same copy seeds; the main line continues from production's copy 0.
- Arm rooms `1M,2M,3M,1?,2?,3?`: every hallway fight and every fight in a '?' room of acts 1-3. Elites, bosses and
  Act 4 are not arm fights.
- Arms: ctl = `gsh16+flat16000+mb4`, c2 = `gsh16+flat16000+mb4+ucb12.5+pw100+tp32+wet14.8+wch1.85` (stage 2's tokens,
  unchanged). 4 copies each.
- Seeds: stage 2's 56 D0 seeds (`../packages.tsv` package `combine`), one unit per seed (`units.txt`, `run_unit.sh`
  refuses any other seed). No new seeds. The scout (`gumbel-tuning-scout`) holds these runs' main lines: on them, 881
  hallway fights in acts 1-3.
- Binary b5090b16 (code 13bb97ec, the whole-run test's; the arm tokens and the selffights main line are unchanged
  since stage 2's e5ba1aad, checked by the reproduction gate below and by the smoke).

## Primary (analyze.py, frozen with this file)

Per hallway fight (room M, acts 1-3) and arm: HP lost = entry HP − exit HP, the entry HP on a loss, mean over the 4
copies. d = c2 − ctl, mean over fights; 95% seed-clustered bootstrap (10,000 resamples, seed 20261109).
**C2_HALLWAY_WORSE** if lo > 0, **C2_HALLWAY_BETTER** if hi < 0, else **NO_DIFFERENCE_SHOWN**. A fight without 4
valid copies of both arms is dropped and counted; units with rc ≠ 0 are excluded and listed. Before the analysis
`verify_campaign.py` must show 56 of 56 units delivered; a unit missing from the share (no tar, so no .done) is listed
by that check, since analyze.py sees only delivered units.

**Reproduction gate (pairing).** Every unit's fights through act 3 equal the scout's (floor and encounter, in order),
and the main-line copy 0 of every fight equals the scout's copy 0 (fights matched by floor and order on the floor, so a
'?' floor with two fights is compared correctly). Both shares ≥ 99% = PAIRED; otherwise every verdict is NOT_PAIRED.

## Secondary (not gates)

By act; '?' room fights; potions used per fight and d; d in HP + 3.7 HP per potion (§766's price); losses per copy;
CPU ratio; per encounter with ≥ 10 fights.

## Power and cost (smoke, below)

Smoke (local, 2026-11-09 23:33 CET): seeds 111860117 and 111860140, both rc 0, 632 s and 929 s of wall time per unit,
one unit per lane. At about 780 s per unit the 56 units cost about 12 lane-hours (10-15 with the spread); on 14 workers
× 4 lanes one round, so about 20-30 minutes including the longest unit. The power figure follows from stage 2's paired
SD per fight once the reproduction check of the smoke units is written here before freezing.

## Decision

No default change. C2_HALLWAY_WORSE supports the reading that c2's whole-run loss comes at least partly from hallway
fights; the next proposal would then be a whole-run test with c2's constants in elite and boss fights only (needs code
for room-dependent constants in whole runs, and Philipp's go). NO_DIFFERENCE_SHOWN or C2_HALLWAY_BETTER: hallway HP is
not the explanation; the remaining candidates are the potion cost, Act 4 and the different runs (net-0420's), which
this test does not separate.
