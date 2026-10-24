# The HP-head fine-tune becomes the A20 CTM default: closer HP on fresh fights, the same deaths (2026-10-24)

**Question.** Philipp, 2026-10-24 07:52Z: "Don't qualify ctm by winrate but by precision, so the new one goes in as
default." [ADR-0059](../../../../decisions/0059-ctm-a20-hp-finetune-default.md) makes §672's HP-head fine-tune
([`../ctm_finetune_20261023/`](../ctm_finetune_20261023/README.md)) with its own refitted table the built-in A20 CTM
stack. `STS_CTM_A20_HP_FINETUNE=0` restores the §470 stack with the ADR-0058 table. Two questions:
1. Is the new default more precise than the old one (old net + ADR-0058 table) on fights neither has seen?
2. Does the change do exactly that? The default must predict what the reviewed research flags predicted on main, and
   `=0` must predict and play exactly as main.

## Precision (question 1)
Rows:
- **Fresh:** the 24,186 real fights of the §676 guard's 1,024 games (both arms;
  [`../ctm_calibration_20261023/RESULT.md`](../ctm_calibration_20261023/RESULT.md) rebuilds them). The games were
  played between 23:25Z on 2026-10-23 and 02:21Z on 2026-10-24, after the fine-tune and its table were frozen, on
  today's engine.
- **Held out:** §670's 6,022 stage 1–2 fights (set LC), which neither the fine-tune nor its table was fitted on.

Both are scored with this change's binary, the default against `STS_CTM_A20_HP_FINETUNE=0`.
`tools/ctm_calibration.py compare` gives the tables, with a 95% bootstrap over source seeds:
[`precision/guard_v1_vs_ft.json`](precision/guard_v1_vs_ft.json), [`precision/lc_v1_vs_ft.json`](precision/lc_v1_vs_ft.json),
and against the raw CTM [`precision/guard_raw_vs_ft.json`](precision/guard_raw_vs_ft.json).

| fights | n | death log loss, old default → new | won-fight HP MAE, old default → new | change [95% CI] | mean HP bias |
|---|---|---|---|---|---|
| fresh (guard) | 24,186 | 0.0660 → 0.0660 | 7.75 → 7.59 | −0.16 [−0.20, −0.12] | −0.11 → +0.04 |
| held out (LC) | 6,022 | 0.0698 → 0.0698 | 7.60 → 7.45 | −0.16 [−0.23, −0.09] | +0.15 → +0.31 |

- Deaths are the same fight for fight: the fine-tune's `p_death` equals the old net's, and both tables shift deaths
  alike.
- Against the raw CTM (no table) on the fresh fights: death log loss 0.0711 → 0.0660 ([−0.0064, −0.0038]), won-fight
  HP MAE 8.65 → 7.59 ([−1.16, −0.94]).
- By group, fresh fights (won-fight HP MAE, old default → new):

  | group | won fights | HP MAE |
  |---|---|---|
  | Act-1 bosses | 896 | 10.80 → 10.63 |
  | Act-2 bosses | 669 | 17.07 → 16.57 (Automaton 17.80 → 16.90) |
  | Act-3 bosses | 964 | 16.50 → 15.40 (Awakened One 19.19 → 17.24, Donu and Deca 15.05 → 14.14) |
  | Act-3 elites | 1,569 | 11.46 → 11.16 |
  | Act-3 events and other rooms | 372 | 8.79 → 8.28 |
  | Shield and Spear | 413 | 18.21 → 17.29 |
  | the Heart | 257 | 18.45 → 18.58 (bias +0.16 → +3.56) |
  | hallway fights, Acts 1–3 | 13,802 | within 0.15 of the old, all lower |

  Worse: the Heart, which has no use for the search (a won Heart ends the run); Act-2 other rooms (7.39 → 7.44) and
  the Gremlin Leader (12.27 → 12.31) by less than 0.05.

## Equivalence (question 2)
Offline, `one_combat ctmscorerows` of four row sets: A (§670's stage-3 A/B arm A, 25,018 rows, `24e9d96d…`), LC
(6,022, `4993471c…`), and the guard's arms gA (11,950, `1c898d9a…`) and gC (12,236, `2752c57a…`) ([`rows.sha256`](rows.sha256)).
- Binaries (x86-64-v3 release `one_combat`): `main` `b855ee27…`, the guard's binary (code `c38fa53d`; main's later
  changes up to `e98d5282` do not reach `one_combat`); `new` `84d5c853…`, this change.
- [`score.sh`](score.sh) clears every CTM setting and sets only the listed ones. Hashes: [`scores.sha256`](scores.sha256).

| check | sets | result |
|---|---|---|
| `new`, all unset = `main` with the fine-tune's research manifest and its table by path (the §672 flags) | A LC gA gC | identical |
| `new` with `STS_CTM_CALIBRATION=0` = `main` with the research manifest and `=0` (raw fine-tune; = §672's `final-off`) | A LC gA gC | identical |
| `new` with `STS_CTM_A20_HP_FINETUNE=0` and the §470 artifact = `main`'s default (§670 `cal/`, the guard's default scores) | A LC gA gC | identical |
| the same with `STS_CTM_CALIBRATION=0` = `main` raw (§670 `off/`, the guard's `=0` scores) | A LC gA gC | identical |
| `STS_CTM_A20_HP_FINETUNE=1` = unset | LC | identical |
| the fine-tune's research manifest, table unset, under the default and under `=0` = the default | LC | identical (fine-tune table) |
| the §470 research manifest (`00bb4da6…`) with the §470 artifact, table unset, under the default = §670 `cal/` | LC | identical (ADR-0058 table) |
| `STS_CTM_ACT4_SURVIVAL_MODEL` set = raw fine-tune | LC | identical (no table) |

The wrong pairings fail before scoring (exit by the runtime's exception):
- default with the §470 artifact: `combat runtime: selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
  (sha256 ae785ec2…) is not an artifact of the built-in A20 CTM stack: the ADR-0059 HP-head fine-tune, fast artifact
  models/candidates/ctm_finetune_hp_pathb_a20_v1.native (STS_CTM_A20_HP_FINETUNE=0 restores the §470 stack)`;
- `=0` with the fine-tune: `… is not an artifact of the built-in A20 CTM stack: the §470 stack under
  STS_CTM_A20_HP_FINETUNE=0, fast artifact selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native`;
- `STS_CTM_A20_HP_FINETUNE=yes`: `STS_CTM_A20_HP_FINETUNE must be 0 or 1 when set`.

**Games.** Two guard seeds, each one `heartoutcomegen` game under `tools/seed_guard.sh` with the guard's arm-C
environment (its `C-SEED.env`) via [`../ctm_calibration_default_20261023/run_exp.sh`](../ctm_calibration_default_20261023/run_exp.sh)
on the `new` binary: `zero` with `STS_CTM_A20_HP_FINETUNE=0`, `ft` with it unset. [`compare.py`](compare.py)
requires a complete, integrity-passed footer in every game and `zero` equal to the guard's arm C in every record after
the header and every CTM row. **PASS** ([`compare.txt`](compare.txt)):
- `zero` replays the guard's arm C exactly on both seeds: 111392255 (372 records, 26 CTM rows, died in Act 3 on floor
  46) and 111392359 (165 records, 13 CTM rows, died in Act 2 on floor 24).
- Banners and headers name each game's stack: `hp_finetune=0` with the ADR-0058 table (`359619f7…`) and
  `hp_finetune=1` with the fine-tune's table (`8c226f23…`); the header's `ctm_a20` artifact is the fine-tune
  (`bdbfafa6…`) in `ft`, the §470 artifact in `zero`.
- The default's search statistics differ from the first decision on. Its moves: on 111392359 the same at all 75
  decisions; on 111392255 the first different move is at decision 86 of 172 (Act 2, floor 23, a different card
  picked). Both seeds end the same way.
- Outputs (the four games and every score CSV above):
  `/mnt/project-files/ctm-calibration/ctm_finetune_default_20261024.tar.gz` (sha256 `be1f25ff…`).

**Tests.** `ctm_calibration_ft_hp_{parity,default,default_research_manifest,default_act4_set,off}` check the C++
calibration of the fine-tune stack against `tools/ctm_calibration.py` on 27 rows (one per group, one with Entropic
Brew; `tests/fixtures/ctm_calibration_ft_hp_parity.jsonl`, written by `ctm_calibration.py fixture` from A's raw and
zero-table scores), and the five `ctm_calibration_*` ones check the §470 stack under `=0`. `ooc_mcts_live_startup` checks the
banner both ways and the bad value; `live_advisor_protocol` the live A20 stack both ways and the mixed pairing;
`test_live_game_runtime` the release pairing.

## Commands
From the repository root (`D` = this directory, `R` = the four row sets, `B` = a binary):
```
FT=models/candidates/ctm_finetune_hp_pathb_a20_v1.native
OLD=selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
M=STS_CTM_RESEARCH_CANDIDATE_MANIFEST=models/candidates/ctm_finetune_hp_pathb_a20_v1.manifest.json
MS=STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=31bb21f7ace7e3cd440136cf0799dbae1e0fbc2964d00bfa7bac8e21124e0a5c
T=models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json
bash $D/score.sh main R out/main_research_ftcal $FT $M $MS STS_CTM_CALIBRATION=$T
bash $D/score.sh main R out/main_research_off $FT $M $MS STS_CTM_CALIBRATION=0
bash $D/score.sh new R out/new_default $FT
bash $D/score.sh new R out/new_off $FT STS_CTM_CALIBRATION=0
bash $D/score.sh new R out/new_restore $OLD STS_CTM_A20_HP_FINETUNE=0
bash $D/score.sh new R out/new_restore_off $OLD STS_CTM_A20_HP_FINETUNE=0 STS_CTM_CALIBRATION=0
python3 -I tools/ctm_calibration.py compare out/new_restore/gA.csv out/new_default/gA.csv \
    out/new_restore/gC.csv out/new_default/gC.csv --json $D/precision/guard_v1_vs_ft.json
python3 -I tools/ctm_calibration.py compare out/new_restore/LC.csv out/new_default/LC.csv --json $D/precision/lc_v1_vs_ft.json
python3 -I tools/ctm_calibration.py compare out/new_restore_off/gA.csv out/new_default/gA.csv \
    out/new_restore_off/gC.csv out/new_default/gC.csv --json $D/precision/guard_raw_vs_ft.json
python3 -I tools/ctm_calibration.py fixture $T R/A.jsonl out/main_research_off/A.csv,ZERO_A.csv \
    tests/fixtures/ctm_calibration_ft_hp_parity.jsonl    # ZERO_A: A scored with the research manifest and the zero table
# games: RUN holds the new one_combat and student_sel.bin (cf6bf7fb…); G = the guard's extracted out/units
X=docs/experiments/evidence/ctm_calibration_default_20261023/run_exp.sh
bash $X $PWD RUN G/SEED/C-SEED.env games/zero-SEED/C-SEED SEED STS_CTM_A20_HP_FINETUNE=0   # one directory per game
bash $X $PWD RUN G/SEED/C-SEED.env games/ft-SEED/C-SEED SEED
python3 -I $D/compare.py G games 111392255 111392359 > $D/compare.txt
```
