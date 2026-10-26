# Gumbel root Q cap (Muesli-style): offline root replay (2026-10-26)

**Question.** Deep-research report (2026-10-26), point 3: the Gumbel root's σ(Q) term is
`(50 + max N) · 1.0 · minmax(Q)` (`OocMctsPlanner.cpp` `gumbelSigma`; mctx's default scale is 0.1). With two
survivors min-max maps any gap to {0, 1}, i.e. 50 + N logits against ~4.6 for a 0.99 prior, so §635's B arm played
close to argmax of noisy leaf Q. Does `STS_OOC_MCTS_GUMBEL_QCAP=1` (σ = clip((Q − V)/SE, −1, 1)) keep the prior
dominant on real roots while still letting Q move weak-prior roots?

**Setup.** `run.sh`: the §635 arm-A config (student_sel `cf6bf7fb…`, PUCT plays, full roots 4096, 25% full roots,
learned OOC stop, real-combat learned Silver stop) on current main defaults (`8cce22b4` + this PR, binary sha256
`a8e38c53…` built from `03a613c7`) with `STS_OOC_MCTS_SCREENS=all` (§635 searched every screen), plus
`STS_OOC_MCTS_ROOT_COMPARE` and the cap. At each full root the same model runs the 8192-simulation uniform reference,
Gumbel SH M16@2048 uncapped and capped (same seed, so they differ only in the Q term). Play is unchanged. 4 full
games, seeds 111305000–003 (1 Heart kill), 48 full roots. `analyze.py`.

| method | leaves prior argmax | agrees with ref best | regret ×1e-3 |
|---|---|---|---|
| prior argmax | – | 0.438 | 11.34 |
| PUCT 4096 (played) | 2.1% | 0.438 | 11.85 |
| SH M16@2048 uncapped (§635 B) | 66.7% | 0.708 | 4.03 |
| SH M16@2048 capped, c = 1 | 10.4% | 0.417 | 12.29 |

Paired regret: capped − uncapped +8.26e-3 [+4.45, +12.52]; capped − PUCT +0.44e-3 [−1.14, +2.08]. On the 29 roots
with top prior ≥ 0.9, uncapped leaves the prior argmax 20 times, capped 0, PUCT 0. The capped root's 5 overrides
are all at top prior ≤ 0.76 (two act-1/2 map choices, two act-4 shop buys, one potion-discard tie); reference Q
differences there are 0.001–0.024. CPU per root: capped 22.0 s, uncapped 21.6 s, reference 82 s (PUCT 4096 ≈ 2×).

**Interpretation.** The mechanism claim holds on real roots: the uncapped term overrules strong priors on two
thirds of full roots (in play §635 saw 17.3% of all searched roots), and the cap removes that completely at
priors ≥ 0.9. Capped Gumbel at 2048 behaves like PUCT at 4096 on the leaf-Q reference, at about half the full-root
CPU. The reference shares the leaf (rollout3 + X2-B), so the uncapped root's lower regret is agreement with the
leaf that lost in play (§635), not evidence of strength; the capped root's equality with PUCT is not evidence of a
gain either. Expected play effect 0 to +1 pp. Only a paired play A/B can decide, and that needs Philipp's go.
Small sample (4 games, 48 roots); c = 1 not tuned.

Raw: `cmp.jsonl.gz` (rows, sha256 per seed in `cmp.sha256`); full run outputs
`/mnt/project-files/gumbel-qcap-20261026/replay-out.tar.gz`.
