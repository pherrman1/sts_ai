# §431 evidence: generator OOC policy drift (2026-10-11)

Raw data: `/mnt/project-files/generator-policy-drift-431/generator-policy-drift-431.tgz`
(sha256 `2fc7feb020ec4f5611c57b1fecded4d10cc9cd737bcf87a3f2bed59e9d422347`), containing every CSV/log
below, the analysis scripts (`analyze.py`, `analyze3.py`, `paired.py`, `labels.py`), the launch
scripts and `binaries.sha256`.

## Producers

All Release (`linux-gcc-release`), cloud container, default env unless stated, 1000 sims, OMP 4 threads.

| Binary | Source | Used for |
|---|---|---|
| `one_combat.probe` | `474237b8` (probe v2: full successor + first action) | `runs/`: chain-as-main trajectories, bestbench, V4-flag first-action arm |
| `one_combat.probe3` | `cd1d99a5` (probe v3: + whole-screen resolution) | `runs3/drift-*` (superseded by v4) |
| `one_combat.probe4` | `8790fa27` (probe v4: stale reward counters ignored once the screen is left) | `runs4/`: headline per-decision drift |
| `one_combat.base478` | `cd1d99a5` + #478's one-line `t_curPath` restore | `runs3/sg2-base478-*` |
| `one_combat.ref478` | `fedadeb2` tree + the same restore | `runs3/sg2-ref478-*` |

`oocpolicydrift N SIMS ASC OUT SEEDOFF MAIN` plays a run with chain `MAIN` (`canon` =
`runFullRunOocPolicyStep(gc, agent, false, true)`; `sg` = verbatim strategicgen chain; `cf` = verbatim
`finishOocCounterfactual` chain; `v4` = `stepFrozenV4Ooc`) and at every OOC decision applies all four
chains to copies of the same state and agent. The probe was removed with the refactor.

## Checks

- Probe `canon` trajectory equals `bestbench` end state (won, floor, hp) on 64/64 A0 seeds
  (74008000-063) and 64/64 A20 seeds (74008100-163).

## Per-decision drift on the deployed trajectory (probe v4, `runs4/`)

A decision differs when a chain, resolving the whole screen on its copy, ends in a different state
than `canon`.

| Config | Decisions | sg | cf | v4 |
|---|---|---|---|---|
| A0, default flags, 64 seeds | 10,424 | 584 (5.6%; 9.1/run; shop 455, card select 106, event 23) | 70 (0.7%; card select 36, event 23, rest 11) | 59 (0.6%; card select 36, event 23) |
| A20, default flags, 64 seeds | 7,252 | 460 (6.3%; shop 335, card select 64, event 61) | 103 (1.4%; event 61, card select 27, rest 15) | 88 (1.2%; event 61, card select 27) |
| A0, V4 gates on (`live_env.sh` gate flags, `ooc_strategic_tok_final.native`), 32 seeds 74008200-231 | 5,492 | 896 (16.3%; rewards 425, shop 234, event 89, card select 68, rest 63, boss relic 17) | 716 (13.0%; rewards 425, shop 92, event 89, rest 54, card select 39, boss relic 17) | 17 (0.3%) |

First-action comparison (probe v2/v3) additionally counts pick-up order (relic before gold, potion
taken with full slots) at about 600 reward screens per 64 runs; those leave the same state once the
screen is left.

## Chain as the main trajectory vs `canon` (probe v2, `runs/`), paired, bootstrap 10,000

| | identical end state | floor Δ (chain − canon) | win Δ |
|---|---|---|---|
| A0 sg | 5/64 | −0.33 [−2.80, +2.00] | +1.6 pp [−12.5, +15.6] |
| A0 cf | 30/64 | +0.09 [−0.88, +1.12] | −1.6 pp [−10.9, +7.8] |
| A0 v4 | 36/64 | −0.16 [−1.03, +0.67] | +0.0 pp [−7.8, +9.4] |
| A20 sg | 21/64 | −4.48 [−8.38, −0.72] | −9.4 pp [−17.2, −3.1] (1 vs 7 wins) |
| A20 cf | 40/64 | −0.80 [−2.91, +1.25] | −6.2 pp [−14.1, +0.0] |
| A20 v4 | 43/64 | −0.56 [−2.64, +1.53] | −1.6 pp [−7.8, +3.1] |

## strategicgen2 labels before vs after (`runs3/sg2-*`)

`strategicgen2 32 1000 ASC`, `STRATEGIC_SAMPLES_PER_RUN=8`, default branch settings (K=3 fights,
bootstrap). Compared only on labeled decisions whose pre-state rows are identical in both runs (before
the main trajectories diverge), with at least two options.

| | shared decisions | argmax(labelFloor) same | any option label changed | mean labelFloor Δ |
|---|---|---|---|---|
| A0 (74008300-331) | 32 | 31/32 | 4/32 | +0.03 |
| A20 (74008400-431) | 77 | 75/77 | 13/77 | −0.39 |

Seeds: 74008000-063, 74008100-163, 74008200-231, 74008300-331, 74008400-431; smoke/tests 74008990-999.
