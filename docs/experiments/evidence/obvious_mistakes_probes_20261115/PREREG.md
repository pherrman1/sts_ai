# Paired probes for the four patterns of the obvious-mistakes pilot (issue #1056, pre-registration)

Authorization: Philipp 2026-11-15 21:31 CET ("oke für jedes muster jetzt eine gepaarte probe", #1056 thread) and his
choice of "40 Worker, 128 Zustände je Muster" (512 pairs, about 150 core-hours) on the same evening; he then split the workers with #1053 Stage 3, which leaves
8 workers for this campaign. Context: the pilot
(`../obvious_mistakes_pilot_20261115/RESULT.md`, draft PR #1069) found four out-of-combat patterns where the PPO actor
(net-0420) and its own critic disagree or the play looks risky. Which side is right is not decidable from traces; these
probes ask it directly.

## Question

For each pattern, does the alternative decision give more Heart kills than the production decision, from the same
§782 game states and with the same hidden future?

| pattern | state (from §782's 1,024 G16 games) | production (B) | alternative (A) | key |
|---|---|---|---|---|
| smith | Act-1 campfire on floor 15 (before the boss), HP <= 85 % of max, the net smithed | SMITH | REST | `ppo:fa=4` |
| elite | map decision with more than one option whose chosen next room is an elite, HP <= 50 % | the elite path | the net's best path whose next room is not an elite | `ppo:path_not=3` |
| corruption | card reward where the net took Corruption | Corruption | the net's best other offered card | `ppo:card_not=83` |
| runic | boss-relic screen where the net took Runic Dome, Pyramid or Cube | the runic relic | the net's best non-runic relic offered | `ppo:relic_not=56,57,58` |

"The net's best other" means the token with the highest PPO logit among the allowed tokens (first one on ties), so A is
the actor's own second choice inside the allowed set. Skipping the card reward or the boss relic is not an allowed
alternative here (the key forbids only the named ids among card or relic tokens).

## Design

- States: `make_units.py` scans all 1,024 §782 G16 traces (seeds 111378256-111379279, the §775 block; no new seeds) with
  the rules above. Candidates: smith 526, elite 277, corruption 502, runic 365. Per pattern they are ordered by
  sha256("issue1056-probe-" + pattern + "-" + seed + "-" + idx) and the first 128 are taken (512 units in
  `units.txt`). A seed can appear in more than one pattern and more than once in one pattern (different decisions); the
  analysis treats each pair as one observation (see Limits).
- Pair: each unit replays the §782 game to the decision (`STS_OOC_FORCE_DECISION=INDEX:SALT:KEY`,
  apps/one_combat/run_driver.cpp) and plays two games to the end: A with the forced token, B with the production
  choice (key `-`). Both redraw the hidden future after the decision with salt 1 (`resampleCounterfactualFuture`), so
  A and B share the same future draw and differ only by the decision and what follows from it. One future per state.
  Known-RNG replay is used only to reach the state; the outcome comes from the redrawn future (ADR-0002).
- Arm: §775's G16 arm exactly as in §782 (`../gumbel_wholerun_trace_20261109/run_unit.sh`): Gumbel root k 16 + max
  backup 4 at 16k simulations in every fight, net-0420 (sha 8c0bd16c) at temperature 0 out of combat, A20 Ironclad.
- Binary: code `ebd446b3` (reproduces §782, see the pilot) plus one research commit, `6de313e`, that adds the
  `ppo:` keys to `STS_OOC_FORCE_DECISION` (heart1_policy.cpp `ppoForcedChoice`; the key forces the best PPO token among
  the allowed ones; without the flag nothing changes). Built with preset linux-gcc-release-x86-64-v3, sha256
  32c21093..., from the worker cache.
- Eligibility: if the key matches no token at the decision (for example every path leads to an elite), A stops at the
  decision with `no_token_matches_`, the unit is ineligible and B is not played. Eligibility depends only on the
  state, not on an outcome. Ineligible units are counted and not replaced.
- Prelaunch checks (local, before the campaign): the selftest of the key (`one_combat heart1pposelftest`); one pair per
  pattern, where both games must replay §782's trace exactly up to the decision, B's decision must equal §782's and A's
  forced token must differ; one unforced game of this binary must equal §782's trace.
  Done 2026-11-15 21:45-22:25 CET in the author's container: selftest passed; u072 (smith), u202 (elite, A only),
  u269 (corruption) and u510 (runic) pass every check of analyze.py (the smith pair failed run_unit's PPO-line check
  only because a fork prints the redrawn seed; the check now accepts any seed); the unforced game of 111378715 equals
  §782's trace (70 of 70 records). Prelaunch review (J): PASS, /mnt/project-files/reviews/pr1069-prelaunch-review.md.

## Analysis (analyze.py, frozen before the first campaign result)

1. Validity per unit: both games rc 0 with the §782 checks of run_unit.sh (net loaded, BEST line, learned stop, Gumbel
   banner, PPO game line; A's trajectory carries the forced key), no combat abort; both traces equal §782's up to the
   decision; B's decision equals §782's; A's chosen token differs from B's. A unit that fails a game (rc, timeout 4 h,
   abort) is a drop; a unit that fails a check is invalid. Neither is imputed or replaced. A pattern with more than 5 %
   invalid among its eligible units is INVALID.
2. Primary, per pattern: Heart kill A minus B over the valid pairs, mean with a 95 % normal interval and a bootstrap
   interval, and the exact two-sided sign test on the discordant pairs. Four tests: the readings use Holm-adjusted
   p < 0.05. ALTERNATIVE_BETTER (mean > 0), PRODUCTION_BETTER (mean < 0), else NOT_SHOWN.
3. Secondary (descriptive, no test): survival past the act of the decision, final floor (A minus B, with intervals);
   the critic's own gap at the next PPO decision after the fork (value in A minus value in B), set against the
   realised Heart gap, to see whether the critic or the actor was right on average; the actor's probability of the
   production choice.
4. Output: `results/summary.json` and RESULT.md; a ledger entry, descriptive, in PR #1069. No default change follows
   from this run: a pattern that reads ALTERNATIVE_BETTER is a candidate for a training signal or a gated rule, with its
   own pre-registration.

Power (stated before the run): with about 30 % discordant pairs, the standard error of a mean difference over 128 pairs
is about 0.05, so only differences of about 10 percentage points or more in Heart kills from these states would read
as shown. Smaller effects will read NOT_SHOWN; that is not evidence of no effect.

## Limits

- One hidden future per state: the pair difference mixes the decision's effect with how sensitive the run is to it in
  that one future; it is unbiased for the mean effect over states but noisy per state.
- States are drawn from the net's own play (production policy), so the result is about these decisions where the net
  made them, not about the decision in general.
- Repeated seeds in a pattern (different decisions of one game) are counted as separate pairs; intervals do not
  cluster on seed. The number of such seeds is reported.
- The alternative is the actor's second choice, not the best alternative.

## Cost and outputs

Each unit plays two games, each about one §782 G16 game (prefix replay plus the rest): about 1,060 s per unit, about
150 core-hours for 512 units, about 5 h on 8 workers x 4 lanes plus the tail. Share
`/mnt/project-files/obvious-mistakes-probes`: 512 unit tars (about 100 MB), about 1,600 claim files, up to 8
wWW.DONE.json, the brief: about 2,200 files (share at about 38,400 of 50,000 files and 6.9 of 10 GB before the run).
Per game TAG-SEED-IDX.{done,env,log,err,trace.jsonl.gz,ppo.jsonl.gz}.
