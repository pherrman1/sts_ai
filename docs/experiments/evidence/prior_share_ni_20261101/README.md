# Prior-share stop at A20 map roots: non-inferiority vs the 1,024 default (pre-registration, 2026-11-03)

Philipp 2026-11-01 23:02 CET "16 worker für prior share lauf" (go), put on hold 23:09 CET, resumed 2026-11-03
20:19 CET "Mach auf 4 workern weiter" (4 workers). Implementation #942 (`STS_OOC_MCTS_PRIOR_SHARE_STOP=H`, merged
85bf1ba0, review J PASS); offline basis `map_root_maxq_count_20261101/budget_stop.py` (`S_prior`).

**Question.** Does stopping an A20 map root early (after 128/256/512 simulations, once the most-visited action is
the prior argmax with at least 90% of the visits) cost less than 1.5 pp of Heart kills compared to the current
default of 1,024 map simulations (ADR-0065)?

**Arms.** R = control, the 1,024 default: §741 arm B (`STS_OOC_MCTS_FULL_ROOT_SIMS=1024`, which is exactly the
ADR-0065 default). C = §741 B's environment verbatim (`run_unit.sh`, env list checked by `diff`) without the explicit
`FULL_ROOT_SIMS` (unset = 1,024 at these roots) plus `STS_OOC_MCTS_PRIOR_SHARE_STOP=0.9`. **H = 0.9** (offline the
larger saving, 0.38x vs 0.44x map sims at 0.21% vs 0.14% changed roots; the author's choice for a speed gate).
C runs on `85bf1ba0` = main right after #942's merge (v3 binary in the manifest). Not current main: the smoke on
main `520d4e4b` (2 sentinels, 2 diverging units) did not reproduce the control (sentinel 111312009 departs at
decision 129, a Heart-key screen, and loses a Heart kill), because later merges change play by default (#970 OOC
relic/event fidelity, #976 Reaper/Bite heal, empty-pile loss, Thorns; #957 removeCardReward OOB read). 85bf1ba0 is
53d591b + #942, and 53d591b replayed §741 B's 111312000 decision for decision (#942 smoke). The stop itself does not
interact with those fixes; a default PR would land on current main.

**Control reuse (why only 81 games are played).** R is not re-played. R(s) = the §741 B record where B was played
(716 seeds), else the §727 A record (820 seeds; §741 showed B plays A's game there: 64/64 sentinels, 652/652 diverging
prefixes). Hashes frozen in `divergence_ps90.json` (`divlist.py`). **Inference (code read):** with the stop off a map
root's first k simulations are the k-simulation search (§741), and the prior-share stop only ends the search at a
checkpoint, so C plays R's game until the first map root where `S_prior`'s pick differs from R's 1,024 pick
(`divlist.py`; checked natively in #942's smokes, 0 mismatches on 3 seeds). That happens on **49 of 1,536 seeds**
(all at the 128 check); on the others d = 0. Two checks guard the reuse:
- **sentinels:** 32 non-diverging seeds (the first 16 by sha256 of the seed string from each control source, B741
  and A727) are played in C; each must reproduce R's record exactly (every state record, every decision's
  rule/selected key, the outcome).
- **diverging units:** each of the 49 must match R row for row before the predicted root and pick the predicted
  key there.
If any unit fails either check, or any unit is missing, the reuse is invalid: verdict INVALID, no reading of the
outcome; the fallback (C on all other seeds) goes to Philipp.

**Seeds.** None new: the 1,536 USED §727 seeds 111312000-111313535 are replayed (81 of them in C). Smoke on
111312009, 111312081 (sent), 111312023, 111312024 (div), author container (see Smoke).

**Primary.** d_i = kill_C − kill_R per seed (A20 Heart kill), all 1,536 seeds in ascending order. SPRT per
ADR-0064 (`sprt_gate.py` = `tools/sprt_gate.py` of main 520d4e4b, vendored, variant `nonregression`, d0 = −0.015, d1 = 0, α = β = 0.05, look every 64 pairs,
cap 1,536). H1 crossing → **NOT_WORSE**; H0 crossing → **WORSE**; CAP → fixed-sample reading (mean d, 95% seed
bootstrap, 10,000 resamples): NOT_WORSE if the lower bound > −1.5 pp, WORSE if the upper bound < 0, else
INCONCLUSIVE. The mean d and its CI are reported in every case. What the gate can show (reviewer J): R kills the Heart on 20 of the 49 diverging seeds, so mean d ≥ −20/1,536 =
−1.30 pp by construction and the −1.5 pp margin cannot be crossed: **NOT_WORSE is nearly guaranteed** (the SPRT's H0
needs ≈ 12 net kill losses, mean < −0.75 pp, to cross WORSE). The informative number is the **kill difference on the
49 diverging seeds** (secondary, with its CI); the gate itself mainly confirms that the speedup costs nothing
visible on the other 1,487 seeds, where C plays R's game.

**Failed units.** A diverging unit whose 4th attempt fails with a game error (`claims/<id>.a4/failed`, rc not one of
run_unit's configuration checks 88/89/92/93/95) counts as a C loss (d = −kill_R; secondaries keep R's values) and is
reported. A failed sentinel, or a configuration-check rc, stays missing: INVALID. Duplicate unit tars (the queue can
run a unit twice): the first tar in sorted order is used and the duplicate reported, as in `verify_campaign.py`.

**Secondaries (descriptive).** Kill difference on the 49 diverging seeds alone; Act 4 reached, Heart reached,
final floor, death by act (C − R with CIs); map simulations and wall per played game, R vs C (different
containers, wall indicative only). Offline, all 1,536 games: C uses 0.38x R's map simulations up to divergence.

**Decision.** NOT_WORSE → `STS_OOC_MCTS_PRIOR_SHARE_STOP=0.9` becomes a default candidate (Philipp decides, own
PR + ADR). WORSE or INCONCLUSIVE → stays off. Ledger entry either way.

**Cost.** 81 games at ≈ 600-900 s ≈ 17 core-h (4 workers × 4 lanes, about 1.5 h).

**Smoke (author container, before launch, binary d3289b52 of 85bf1ba0).** 111312009 sent (B741), 111312081 sent
(A727), 111312023 div, 111312024 div: all rc 0, banner `prior_share_stop=0.900000 … map_root_sims_a20_default=1024`;
`analyze.py` on a test share of the four tars: both sentinels identical to R, both diverging units identical before
the predicted root and pick the predicted key there. Wall 117-874 s. (The same four on main 520d4e4b's binary
ca8db597 failed every check, see Arms.)
