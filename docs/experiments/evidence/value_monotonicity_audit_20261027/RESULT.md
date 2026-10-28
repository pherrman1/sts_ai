# OOC value counterfactual monotonicity audit: result (issue #886, 2026-10-28)

Plan: [README.md](README.md), written before the run. Run commit `e00b86c` (main `ed2dcb2` + the instrument),
`one_combat` sha256 `0302d4d8…`, student_sel `cf6bf7fb…` (hashes in `results/raw.sha256`).

## Verdict

- **HP: no model inconsistency.** X2-B and the calibrated leaf anchor never moved against HP in 25,315 HP pairs
  (0 violations; 20 % exact ties from the piecewise-constant trees). The rollout3 leaf, the value the search actually
  backs up, moved the wrong way in 21 % of pairs, but beyond 2 paired SE in only 0.5 % (62 of 12,562 mechanically
  dominating pairs). That rate is below what noise alone gives. The leaf's mean HP slope is the right sign at every
  step (−24 HP: −7.1 pp anchor, −3.5 pp rollout; +12 HP: +3.0 / +1.7 pp).
- **Upgrades: a confirmed, material model inconsistency in X2-B.** On plain-number upgrades (class P), X2-B lowered the
  value in 29.7 % of 32,186 pairs, by ≥ 0.5 pp in 3,002 of them. The rollout3 leaf inherits this: wrong-way beyond 2 SE
  in 10.3 % (3,326). The violations are card-specific and repeat across seeds (decks):

  | upgrade | pairs | seeds | X2-B leaf wrong-way | mean leaf Δ | rollout Δ |
  |---|---|---|---|---|---|
  | Dropkick+ | 245 | 1 | 100 % | −3.42 pp | −2.28 pp |
  | Apotheosis+ (cost 2→1) | 327 | 1 | 99 % | −0.79 pp | +0.12 pp |
  | Anger+ | 1,617 | 5 | 51 % | −0.71 pp | −0.56 pp |
  | Defend+ | 2,610 | 8 | 75 % (4 seeds 99–100 %) | −0.61 pp | −0.14 pp |
  | Bash+ | 3,163 | 8 | 66 % | −0.42 pp | −0.17 pp |
  | Flame Barrier+ | 364 | 1 | 99 % | −0.36 pp | −0.32 pp |

  Strong cards are priced the right way, e.g. Demon Form+ +8.8 pp, Inflame+ +5.5 pp, Shockwave+ +2.8 pp
  (`results/upgrades_by_card.txt`). X2-B is blind (exact tie everywhere) to Clothesline+, Dark Embrace+ and Discovery+.
  It has no `u113` input for Discovery; the other two have inputs the trees never split on usefully. Class H
  (heuristic dominance) upgrades: X2-B wrong-way in 19.5 %, rollout beyond 2 SE in 4.2 % (table below).
- **Mechanical exceptions** (act 1 vs Hexaghost, Red Skull, Meat on the Bone) are kept separate. They behave like the
  dominating HP pairs: X2-B 0 violations, rollout 0.8 % beyond 2 SE. In these runs the exceptions did not show up as
  wrong-way values.
- **Decision impact: indirect, not measured.** At A20 the search runs only at map roots. Sibling map actions never
  differ by exactly one upgrade, so these pairs cannot flip a root by themselves. The inconsistency enters through the
  leaf: rollouts that smith or otherwise upgrade Defend/Bash/Anger/Dropkick end in a lower X2-B value than the same
  rollout without the upgrade. As an upper bound, in 1,416 of 32,186 P pairs the leaf-anchor error exceeds the gap
  from the leaf's root action to its adjacent sibling action, i.e. it would reorder that root if every successor of
  the action carried the same error. That is a bound, not a measured flip rate.

## Counts (`results/summary.json`)

Data: 8 used §683 MAP seeds 111374100–107, 155 map roots, 3,166 depth-1 leaves (acts 1/2/3: 1,001 / 1,166 / 999;
no act-4 map roots reached the capture), 62,346 pairs. Leaves of one root and of one seed are correlated, so the
effective sample for the per-card table is the number of seeds.

| group | estimator | n | wrong-way | tie | ≥ 0.5 pp wrong | > 2 SE wrong |
|---|---|---|---|---|---|---|
| HP, dominating | X2-B / leaf anchor | 12,562 | 0.0 % | 19.6 % | 0 | n/a |
| HP, dominating | rollout3 (16 CRN) | 12,562 | 22.1 % | 7.1 % | 1,461 | 62 (0.5 %) |
| HP, flagged | X2-B / leaf anchor | 12,753 | 0.0 % | 21.2 % | 0 | n/a |
| HP, flagged | rollout3 | 12,753 | 20.7 % | 7.2 % | 1,386 | 107 (0.8 %) |
| upgrade P | X2-B | 32,186 | 29.7 % | 32.7 % | 3,002 | n/a |
| upgrade P | leaf anchor | 32,186 | 29.7 % | 32.7 % | 4,403 | n/a |
| upgrade P | rollout3 | 32,186 | 32.4 % | 3.1 % | 4,709 | 3,326 (10.3 %) |
| upgrade H | X2-B | 4,845 | 19.5 % | 30.4 % | 188 | n/a |
| upgrade H | rollout3 | 4,845 | 20.2 % | 4.9 % | 230 | 205 (4.2 %) |

"Tie" for rollouts means an identical mean over the 16 streams. The leaf anchor's ≥ 0.5 pp count is larger than
X2-B's because M0 multiplies differences at mid-range values.

## Secondary: value heads the search does not read (`results/value_heads.json`)

The same 65,512 variants as heart1 public records, rebuilt from each leaf's record. The rebuild reproduced the
capture's student_sel values exactly (max deviation 0.0).

| head | HP wrong-way | upgrade wrong-way |
|---|---|---|
| student_sel (cf6bf7fb) | 29.6 % | 88.1 % |
| SR LC25 s1 / s2 | 19.3 % / 19.4 % | 28.3 % / 35.1 % |
| SR LC50 s1 / s2 | 17.2 % / 15.3 % | 30.6 % / 30.5 % |
| SR 100 % (SR_crn_r2) s1 ep13 / s2 ep20 | 17.5 % / 17.3 % | 28.7 % / 26.9 % |

student_sel's value head prices almost every upgrade negative. It is not used by search. The SR heads are far
better than student_sel on upgrades, but against HP they are worse than X2-B (which has 0 %). Across 25/50/100 % the
rates move by about as much as the seed-to-seed spread. Learning curve: **inconclusive/flat**, in line with §700.
Heads are deterministic, so these rates are model error, not sampling noise.

## Checks

- Every captured game equals its uncaptured game at this commit. 5 of 8 reproduce the §683 MAP trace exactly
  (100, 101, 103, 106, 107). 102, 104 and 105 diverge from §683 at one map decision after identical states (rows 242,
  109, 65). The uncaptured replay at this commit diverges identically (421/421, 349/349, 441/441 rows equal to the
  captured game; `plain-uncaptured-102-104-105.tgz` on the share, sha256 in `results/raw.sha256`), so the capture
  is not the cause.
- **Cause of the divergence:** `mono_unit.sh` copies the §695 env, which predates #868. It does not set
  `STS_CALLING_BELL_CARD_RNG_FIX=0`, and that fix has been on by default since §683. Uncaptured replays of 102/104/105
  with `=0` (otherwise the same env, stopped early) match §683 on their first 249 / 216 / 156 rows, past the
  divergence rows 242 / 109 / 65 (`trace_check.py --prefix`; replays stopped there,
  `bell-fix0-102-104-105.tgz` on the share, sha256 in `results/raw.sha256`).

## Deviation from the plan

The plan (README §Data) said a diverging replay is excluded. 102/104/105 diverged and were included in the headline
8-seed numbers above, so this is a deviation. Those three seeds carry 9,899 of the 12,562 dominating HP pairs. The
pre-registered 5-seed analysis (100, 101, 103, 106, 107; `results/summary_5seed.json`: 91 roots, 1,873 leaves, 38,553
pairs) gives the same conclusions:

| group | estimator | 8 seeds | 5 seeds (pre-registered) |
|---|---|---|---|
| HP, dominating | X2-B wrong-way | 0 / 12,562 | 0 / 2,663 |
| HP, dominating | rollout3 > 2 SE wrong | 62 (0.5 %) | 2 (0.1 %) |
| upgrade P | X2-B wrong-way | 29.7 % | 31.2 % (6,326 / 20,277) |
| upgrade P | rollout3 > 2 SE wrong | 10.3 % | 11.2 % (2,264) |
| Defend+ | X2-B leaf wrong-way | 75 % | 86 % (1,131 / 1,317), −0.81 pp |
| Bash+ | X2-B leaf wrong-way | 66 % | 68 % (1,279 / 1,872), −0.28 pp |
| Anger+ | X2-B leaf wrong-way | 51 % | 62 % (793 / 1,277), −0.89 pp |

Dropkick+, Apotheosis+ and Flame Barrier+ come from seeds in both sets and are unchanged. The 102/104/105 games are
valid games of the same bot with the Calling Bell fix on; their pairs are within-game counterfactuals, so the fix
changes which states are sampled, not the pair check.
- All 65,512 variants passed the feature check: exactly `curHp`, or exactly the card's `uNN` +1. No restore error.
  All 3,166 base-variant rollouts reproduced the leaf's own repeats bit for bit.
- Two container restarts killed runs. Seeds 105–107 were rerun from scratch, and only complete runs are analysed.

## Interpretation and limits

- **Inference:** the upgrade violations look like confounding in X2-B's training data. A small, card-specific
  `uNN` feature, e.g. Defend+ and Bash+, upgraded when the run is already weak, is learned as a negative signal.
  Unverified.
- The bot-policy value need not be monotone even where the game value is, since the rollout policy reacts to HP. The
  HP result needs no such excuse; the upgrade result is too consistent per card to be policy reaction.
- No training constraint, augmentation or model change in this issue. Natural follow-ups: an upgrade-sign check
  added to X2-B's training gate, or upgrade-paired augmentation. A smith-target or rest-site study would show whether
  the bias changes real choices. student_sel, not the search, decides rest sites at A20.

Raw data: `/mnt/project-files/value-monotonicity-886/` (per-seed tars, `pairs.jsonl.gz`; sha256 in
`results/raw.sha256`). `results/leaves.jsonl.gz` lists every leaf.
