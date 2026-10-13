# Generation-2 self-play data: frozen configuration (2026-10-13)

- Code: branch `claude/silver-mlp-prior-gen2-t4lazp`, commit `63ae65d7d9a8c6d5d7e906b87689f51d4283fa38`
  (main `52e605fd` + `one_combat silverazgen`; draft PR, not merged).
- Binary: Release `one_combat`, sha256 in `BINARY_SHA256` (9098ee11…b0f7).
- Prior: `/mnt/project-files/silver-az-mlp/gen1/combat_policy_mlp_gen1.txt`, sha256 a5f4505a…64d2.
- Search: native Silver flat exact 2,000 sims, c = 25, reuse cap 32k, MLP tree prior at
  nodes with >= 8 simulations, weight 400, root bonus OFF (`ROOT_BONUS 0`, PLAN §2.2);
  untried root edges still go in prior order. Every fight of every run uses this search;
  the run plays the most visited action.
- Environment: `env.sh` (fair RNG, OOC strategic gates as in the §455 eval). The manifest of
  each unit records all `STS_*` variables, the OOC policy spec, model sha, K, weight, root bonus.
- Seeds (coordinator pre-assignment, 86M): natural 86000000-86000511, perturbed
  86001000-86001511, A0. 256 units of 4 seeds; `worker.sh W N OUT`, N in {4, 8, 16}.
- Rows: silversynthgen schema (root rows with wire + edge visits/Q, fight rows); no second
  teacher, continuations, leaf samples or inner-node stream.
- Smokes (seeds 74046000-74046001, 74046010-74046011, 74046020-74046021, idle core):
  natural run ~16 s, ~540 roots; perturbed run ~36 s, ~460 roots. Estimate for 1,024 runs:
  ~500k roots, ~7.5 core-hours. Output reproducible bit for bit (74046000 run twice).
- Outputs per worker: `wWW.tar` (units: `*.jsonl.gz`, `.manifest.json`, `.provenance.json`,
  `.log`, `.done`, `units.txt`, `lanes.txt`, `DONE.txt`) + `wWW.DONE.txt`.
