# Pilot: prior-argmax playouts vs greedy playouts in Silver (A20, fight level, leaf headroom)

Status: small in-thread pilot requested by Philipp (2026-10-18 14:06Z, thread "Better fast leaf evaluation":
"good idea, lets do that", answering the proposal to measure leaf headroom first). Written before any pilot
result. Ledger §TBD. Seeds assigned by the coordinator: 111197692–111197791 (pilot sources 111197692–111197707, smoke 111197780–111197783).

## Question

§479 and §523 indicate that a Silver leaf's value comes from its playout policy, not from playout variance, and
2.5k vs 10k simulations differ by only −0.68 [−3.13, +1.87] fight score (§479). A faster leaf alone therefore
buys little. Is there headroom for a *better* leaf? Upper-bound probe: replace the greedy playout policy by the
gen-6 E prior's argmax at every playout card play, at equal simulations. Not deployable (a prior forward per
playout step); it only measures whether a better-playing leaf is worth distilling into a fast one.

## Design

`one_combat ctmsilvergen` at Ascension 20, new armset `priorpl`, otherwise the §523 harness (`env.sh`, `run.sh`
here; student C source runs, gen-6 E root prior weight 400, keys flag off, hallway every 3rd, R = 2), except that
the ADR-0046 root table stays on (current default). Arms at 2,500 simulations, both with the root prior and the
tree prior (K = 8):

- `greedy2500`: production playouts (greedy `SilverRolloutAgent`, per-root card table).
- `priorpl2500`: `STS_SILVER_ROLLOUT_PRIOR` playouts: every `PLAYER_NORMAL` step plays the gen-6 E argmax over
  card plays and END_TURN (no potions, like the greedy playout); card selects stay greedy.

Sources: 16 (4 shards of 4) in this thread on 4 cores, plus a 4-seed smoke first. Code commit and binary:
`CODE` in `run.sh`, `BINARY_SHA256`.

## Analysis and decision rule

`analyze.py` (the §523 analyzer with these arms): per arm fight score, win, HP lost, CPU per fight and per
simulation, rollout length; `priorpl2500 − greedy2500` paired contrasts with 95% seed bootstrap, all fights and
boss / elite / normal / Act 4 subsets.

Label on the all-fight score contrast:
- `HEADROOM`: mean ≥ +5 and CI lower bound > 0 → design a fast distilled leaf (options note
  `/mnt/project-files/silver-leaf-eval/FAST-LEAF.md`, option 2).
- `NO_HEADROOM`: CI upper bound < +5 → close the learned-leaf line for Silver.
- `INCONCLUSIVE` otherwise → report; any larger run needs Philipp's authorization.

No default changes. `STS_SILVER_ROLLOUT_PRIOR` stays research-only and off.
