# V_A4 Act-4 entry perturbation pilot: result (2026-10-31)

Campaign: [README.md](README.md). RUN_COMMIT 1cba6023, code 93cef2bd, binary a4da3156…. 16 workers (Philipp's go,
2026-10-30 17:41Z), started 21:10Z, last unit in 12:1xZ on 10-31. One unit (111384980, about 6 h because its Act 4 is
slow) needed 4 attempts after container resets.

## Verify
| check | result |
|---|---|
| `tools/cloud/verify_campaign.py` | 64/64 OK, 0 BAD, no duplicates, one run commit |
| units | all rc 0, 16 children each (960 perturbed children + 64 controls) |
| `control_check.py`: child 0 vs run 1's base game | **64/64 identical** after the header |
| `entry_diff_check.py`: entry record changes only in the operator's fields | 960/960 (Searing Blow keeps its upgrade count in `obs.deck.misc`, allowed for (un)upgrade); 2 hp children change no record field (203→204 HP, both on seed 111384265) |

## Gate (pre-registered, `gate.py`, [results/gate_result.json](results/gate_result.json))
`gate.py` checks that the wrapper with no perturbation rows reproduces exp8 exactly (`GATE_CHECK=1`: GBM rep 0, max |Δ| =
0). That the controls' feature rows equal the run-1 rows exactly was checked separately, here and in the results review.

| | BCE (dev core, per game) | R² | run-1 BCE | run-1 R² |
|---|---|---|---|---|
| A = ENS_rc (exp8) | 0.4910 | 0.284 | 0.4936 | 0.259 |
| B = A + 960 perturbation rows | 0.4905 | 0.284 | 0.4934 | 0.259 |

**B − A = −0.0005 [−0.0026, +0.0017] → NOT_SHOWN at pilot size.** On the 64 pilot seeds' own real rows the difference
is −0.0037 [−0.0103, +0.0030]; on all other dev rows it is −0.0001 [−0.0022, +0.0022]. The size matches the
pre-registered expectation (about −0.002). The pilot cannot tell a useful effect from none.

## Secondary: CRN effects per operator ([results/crn_result.json](results/crn_result.json))
Paired Heart kill (child − control of the same entry), seed-cluster bootstrap. The control kills the Heart in 70.3%
of these entries. Run 1's four redrawn-future forks of the same 64 entries kill in 70.7%, so the control is not lucky.

| operator | n | mean Δ kill | 95% CI |
|---|---|---|---|
| relic_add | 85 | +0.08 | [−0.01, +0.17] |
| potion_add | 86 | +0.05 | [−0.04, +0.14] |
| relic_swap | 67 | −0.05 | [−0.23, +0.13] |
| hp (slope +0.17 pp per HP [0.0, +0.5]) | 87 | −0.05 | [−0.13, 0.00] |
| upgrade | 88 | −0.07 | [−0.18, +0.05] |
| card_remove (non-basic) | 83 | −0.07 | [−0.24, +0.09] |
| card_add | 67 | −0.08 | [−0.29, +0.14] |
| gold (slope +0.04 pp per gold, CI ∋ 0) | 87 | −0.10 | [−0.23, +0.02] |
| unupgrade | 87 | −0.12 | [−0.21, −0.02] |
| potion_remove | 36 | −0.14 | [−0.30, 0.00] |
| relic_remove | 74 | −0.18 | [−0.31, −0.04] |
| relic_counter (redraw) | 45 | −0.20 | [−0.36, −0.06] |
| max_hp | 68 | −0.21 | [−0.35, −0.07] |

**Sign check: not clean, borderline.** Across all 960 children the kill rate is 62.7% vs 70.3% for the controls:
−7.6 pp, seed-clustered CI [−15.1, +0.1], which includes 0. Against all five run-1 games of the same entries the gap
is about −8 pp [−14, −2] (results review). Changes that should not hurt are also negative on average:
- upgrade −7 pp [−18, +4];
- HP gain −3 pp (n 36);
- max-HP gain (with the matching heal, as the game does) −15 pp (n 26), max-HP loss −24 pp (n 42);
- gold gain −4 pp (n 47).

Losses are larger than gains, as they should be, but the level is shifted down.

Exploratory ([`path_divergence.py`](path_divergence.py), [results/path_divergence.json](results/path_divergence.json)):
- **Same OOC path, gold:** when a gold change leaves the Act-4 decision path unchanged (15 children), the outcome
  equals the control in every case. So the fork, the CRN and the perturbation mechanism reproduce the game exactly when
  combat is untouched.
- **Same OOC path, combat changes:** when combat-relevant fields change and the OOC path stays the same, the mean Δ
  is still negative: max_hp −0.20 (n 61), relic_counter −0.20 (41), card_add −0.14 (58), unupgrade −0.12 (86),
  upgrade −0.09 (81), hp −0.02 (83).

Results review (`/mnt/project-files/reviews/pr919-results-review.md`), from the raw records:
- The perturbations reach the first Act-4 fight exactly as intended (flags, upgradeable count, max HP, relic bits,
  potions).
- The combat RNG equals the control's in 941/960 children.
- The 69 children whose Act-4 fight inputs all equal the control's reproduce it exactly.
- HP lost in the first Act-4 elite fight moves the right way per operator (relic_add −6.7, upgrade −1.4,
  relic_remove +6.5), and the mean over all children is +0.08, so there is no level shift there.
- The deficit sits in the **Heart fight**. Heart-entry HP is about 75 in all groups, but conversion is 66% for
  children vs 75% for controls and 73% for run-1 forks.
- No combat-input bug was found. A Silver- or Heart-internal cache is the one thing the records cannot rule out.

Possible reasons, not separated by this pilot:
1. **Real effect.** The bot's own Act-4 entry state is locally better than a random nearby one, even for upgrades.
2. **Engine or search inconsistency.** After an in-place edit of HP, max HP, deck or relic counters, a derived
   combat cache could be stale. The #917 self-test checks the GameContext and the public record, not combat-time
   derived state.
3. **Something else lowers combat quality in perturbed children.**

The max-HP gain at −15 pp and the counter redraw at −20 pp are the clearest red flags for reason 2.

## Decision
Gate: **NOT_SHOWN** (pre-registered). Do not scale up as is. First clear the sign anomaly with a cheap engine-level
check:
- replay a few children's **Heart fight** with `act4replay`, both from the perturbed child's state and from a
  freshly constructed state with the same fields (the review places the deficit there);
- or add an operator that changes only a combat-irrelevant field (for example gold with the shop excluded) next to
  a `max_hp +0` control.

If the shift is real, perturbation rows are still valid training data. If it is a bug, the pilot's 960 rows are
biased, and the scale-up waits for a fix.
