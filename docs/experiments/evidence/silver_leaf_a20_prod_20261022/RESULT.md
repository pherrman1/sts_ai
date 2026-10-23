# Result: A20 self-play data with production Silver in combat (2026-10-23)

## Verdict

**Part B passes.** The head `a20prod`, trained on this campaign with the first campaign's scripts unchanged, meets
every pre-registered bar of Part B of `../leaf_head_turn_penalty_20261022/PREREG.md` in the selected mode
(hblend:a20prod:0.5/1) on the 300 fresh first fights. The campaign's combat plays at production strength (Heart
killed in 25.5% of the natural runs against 18.4% in the first campaign). On the four smoke fights in which the first
head failed at fight level, `a20prod` with the turn penalty does not fail; without the penalty it stalls again.

## Campaign

RUN_COMMIT f92343af, binary sha256 f4cc0752... (code 28e281f1). `verify_campaign.py --extract`: 192 of 192 units OK,
none missing or bad, no duplicates, every unit rc=0; all 8 workers verified. Wall 00:26-05:37Z on 8 workers; two
workers restarted with their containers and redid their running units (20 claims taken twice, none failed). All 192
unit manifests say `"combat": "production"`, `"oocPlay": "production_chain"`, prior playouts in boss rooms and teacher
`silver-az-10000-k8-rb1-prod-c45dcc0a`.

Outcomes (`outcomes.py` on the unit tars; `results/outcomes.txt`):

| runs | Heart killed | act 4 reached | act 3 | act 2 | Heart fights won |
|---|---|---|---|---|---|
| this campaign, 1,024 natural | **261 (25.5%, 95% CI 22.9-28.2)** | 39.6% | 59.6% | 84.7% | 68.1% |
| first campaign, 1,024 natural | 188 (18.4%, 16.1-20.8) | 30.6% | 56.0% | 84.2% | 62.9% |
| this campaign, 512 perturbed (real path) | 109 (21.3%) | 36.1% | 56.4% | 82.6% | 63.0% |

Production references on other seeds: student_sel 23.4% Heart and 41.5% act 4 (§569), gen-0 search 25.8%. The
first campaign's RESULT gives "60.1% of Heart fights won"; that is 188 of the 313 runs that reached act 4 (the same
ratio here: 261 of 405, 64.4%).

## Pack and head (README step 2)

`pack_a20.py` with this campaign's binary: 777,993 roots (36 dropped by the extractor for an edge mismatch, none for
a missing score), 30,912 refchg roots left out. `train_head_a20.py`: fit 454,345, stop 150,982, test (fold 4) 141,754
roots, 19 epochs, best stop-fold RMSE 23.46 points. Head `a20prod` (sha256 9b314c04...; `results/a20prod_head.txt`,
also on the share as `exact-combat-research/leaf-value/heads/a20prod.txt`). Fold 4, Silver points:

| group | roots | actual | head RMSE | head bias | root value RMSE | root value bias | constant RMSE |
|---|---|---|---|---|---|---|---|
| all | 141,754 | 123.0 | 23.7 | −0.1 | 22.3 | −12.0 | 36.6 |
| act 1 | 43,325 | 110.6 | 16.7 | +0.9 | 14.6 | −7.5 | 28.6 |
| act 2 | 40,853 | 117.0 | 21.9 | −0.1 | 20.2 | −11.3 | 33.0 |
| act 3 | 47,556 | 137.8 | 26.7 | −0.0 | 23.4 | −14.1 | 43.0 |
| act 4 | 10,020 | 131.2 | 37.6 | −4.7 | 43.1 | −24.3 | 47.0 |
| hallway | 58,050 | 125.9 | 15.9 | +0.4 | 12.5 | −7.7 | 29.2 |
| elite | 42,759 | 118.3 | 22.1 | +0.6 | 22.1 | −13.2 | 37.7 |
| boss | 37,458 | 123.0 | 33.6 | −1.5 | 32.5 | −17.5 | 44.4 |
| turn 0 | 34,871 | 123.2 | 23.8 | −1.2 | 29.5 | −19.6 | 35.9 |

As in the first campaign the head is unbiased outside act 4 and Silver's own root value (the most visited edge's Q
after 10,000 simulations) runs 8-24 points low. The first campaign's head had fold-4 RMSE 25.0 on its own data
(different fights, so not directly comparable). Full table: `results/a20prod_report.json`.

## First-fight test (README step 3: Part B)

Fresh replays 111333000-099 (Cultist, Two Louse, Jaw Worm; 300 fights), configs prod and prod@mb=4, 4,200 solves, no
failures. Exact regret per fight paired against the playout (none), mean ± SE:

| config | none | **hblend:a20prod:0.5/1** | hblend:a20prod:0.5 | head:a20prod | hblend:a20prod:0.5/1 +cap | hblend:a20:0.5/1 | hblend:a20:0.5/1 +cap |
|---|---|---|---|---|---|---|---|
| prod | 0.790 | **−0.264 ± 0.054** | −0.333 ± 0.055 | −0.068 ± 0.098 | −0.171 ± 0.054 | −0.251 ± 0.054 | −0.149 ± 0.054 |
| prod@mb=4 | 0.456 | **−0.214 ± 0.044** | −0.331 ± 0.050 | +0.181 ± 0.096 | −0.170 ± 0.045 | −0.283 ± 0.048 | −0.174 ± 0.050 |

- **Rule** (pooled change at most −0.10 in prod@mb=4, below 0 in prod, no encounter above +0.10 in either config):
  hblend:a20prod:0.5/1 meets all three; its worst encounter is Cultist in prod, +0.012 ± 0.054 (Jaw Worm −0.811 and
  −0.630, Two Louse +0.007 and +0.006). PASS.
- The other columns are descriptive (paired per fight, mean ± SE). With the same turn penalty `a20prod` is about as
  good as `a20`: −0.012 ± 0.025 against it in prod, +0.069 ± 0.031 with max backup; with the cap −0.021 ± 0.035 and
  +0.003 ± 0.038. Without the penalty its blend is the best mode so far (−0.333 and −0.331 against the playout,
  −0.069 ± 0.025 and −0.117 ± 0.031 against the penalized blend, worst encounter Cultist +0.047), where `a20`'s
  blend without the penalty stalled once with max backup (+0.118 ± 0.366, one 10-turn fight). The head alone no
  longer collapses (`a20` alone: +4.95 and +20.10) but is not better than the playout (Two Louse with max backup
  +0.247 ± 0.058). The cap costs `a20prod` +0.093 ± 0.039 and +0.044 ± 0.036.
- The `a20` columns come from the same solver binary and equal the rows of the earlier runs on these fights
  (`../leaf_head_turn_penalty_20261022/RESULT.md`, `../silver_leaf_head_shortfall_20261023/RESULT.md`).
- Played outcome (`outcome_tp.py`, end HP − 0.4 x turns, paired, no cap; `results/partb_outcome.txt`): every fight is
  won in every mode; hblend:a20prod:0.5/1 +0.06 ± 0.15 (prod) and +0.27 ± 0.13 (prod@mb=4), hblend:a20prod:0.5
  +0.13 ± 0.16 and +0.14 ± 0.14, head:a20prod −0.21 ± 0.20 and −0.31 ± 0.18 (longer fights: 3.2 and 3.4 turns against
  2.4 and 2.6).

## The four failing smoke fights (descriptive)

The fights in which the first head failed at fight level (`../silver_leaf_head_ab_20261022/PREREG.md`), replayed with
the leafhead diagnostics (`STS_CTMSILVER_FIGHTS`, binary `83de6c12...`, uncapped `a20prod`, blend 0.5). HP after the two
redraws, decisions in brackets; the other columns from `../silver_leaf_head_shortfall_20261023/RESULT.md`:

| fight | production (base10000) | a20 uncapped | a20 capped | **a20prod, 1 point per turn** | a20prod, no penalty |
|---|---|---|---|---|---|
| 111339997 f14 (Centurion + Mystic) | 67/67 (49) | 14/18 (136) | 68/67 (50) | **67/67 (67)** | 66/68 (70) |
| 111339997 f19 (Collector) | 75/50 (91) | 24/1 (108) | 75/59 (86) | **67/54 (97)** | 21/42 (97) |
| 111339999 f12 (Slavers) | 55/55 (36) | 55/41 (74) | 55/55 (55) | **55/55 (50)** | 55/55 (48) |
| 111339999 f18 (Darklings) | 46/35 (40) | 56/50 (495) | 40/52 (76) | **52/50 (90)** | 54, then a stall |

With the turn penalty the production head does not fail where the first head did: 467 HP over the eight redraws
against production's 450 and the capped first head's 471. Without it, it stalls again (the second Darklings redraw
passed 1,000 decisions and the engine's stall guard ended the run) and ends the Collector fight 62 HP worse than
production. Production labels shrink the overvaluation off the training states; they do not remove it, so the
penalty (or the cap) stays.

## Smoke of the uncapped production head (descriptive)

`a20prod` uncapped with the turn penalty (blend 0.5, 1 point per turn) in the A/B's harness on its smoke sources
111339997-999: `../silver_leaf_head_ab_20261022/run_unit.sh`'s environment with `STS_CTMSILVER_LEAF_HEAD_WIN_CAP=0` and
`STS_CTMSILVER_SWEEP_SIMS=10000` (production control at 10k only), binary `83de6c12...`. 50 valid fights, the same as
in the capped smoke, with identical base10000 rows. The A/B's `analyze.py` with only these two arms
(`results/smoke_prod_tp.json`):

| head10000 − base10000, 50 fights | score per fight | HP lost per fight | CPU per fight | stalls |
|---|---|---|---|---|
| `a20prod` uncapped, 1 point per turn | −4.3 | +0.19 | 1.11 | 1 |
| `a20` capped (the A/B's candidate, its smoke) | −0.8 | −0.39 | 1.11 | 0 |

Two boss redraws died that production survived at 10 and 1 HP (Hexaghost, Donu and Deca); the one stall by the
decision count is the Darklings fight above, which it ended with more HP than production. Three sources cannot rank
the two heads, and nothing here argues for swapping the A/B's candidate. Raw rows:
`/mnt/project-files/silver-leaf-head-ab/smoke/smoke_prod_tp_raw.tgz` (sha256 d7ff4342...).

## Provenance and commands

- Solver: `exact_combat_solver` built from 75afdee0's code (sha256 a214254f...). Head `a20` (049d08a2...) from the
  share.
- `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/silver_leaf_a20_prod_20261022 --extract DEST`
- `python3 ../silver_leaf_a20_data_20261022/pack_a20.py ONE_COMBAT_f4cc0752 REPO DEST PACK WORK 4` (pack sha256
  47efc292..., 421 MB, not kept; the command rebuilds it)
- `python3 ../silver_leaf_a20_data_20261022/train_head_a20.py PACK g7f_E/model.pt a20prod.txt a20prod_report.json`
- `../leaf_head_turn_penalty_20261022/run_tp.sh SOLVER OUT fresh 111333000 100 2 MODES HEADS` (wall 418 s) with
  HEADS = `a20prod=a20prod.txt,a20=a20.txt` and MODES =
  `none,hblend:a20prod:0.5/1,head:a20prod,hblend:a20prod:0.5,hblend:a20prod:0.5/1+cap,hblend:a20:0.5/1,`
  `hblend:a20:0.5/1+cap` (one string)
- `SEEDS=111333000:111333099 python3 ../silver_leaf_a20_data_20261022/analyze_oracle.py results/partb.json
  OUT/fresh_*.jsonl` (`results/partb_analysis.txt`), and the same with
  `../leaf_head_turn_penalty_20261022/outcome_tp.py`
- Raw rows: `/mnt/project-files/exact-combat-research/leaf-value/turn-penalty/raw_partb.tgz` (sha256 8ee14ae1...).
