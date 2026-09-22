# Frozen SilverPriorNetV1 online gameplay screen

This packet records the pre-review implementation evidence and two paired
end-to-end smoke seeds. The smoke runs validate runtime integration only; their
win/loss outcomes are excluded from the scientific screen.

The frozen offline root-mechanism result remains
`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`. This online question was explicitly
requested as a separate bounded gameplay check. The user waived the proposed
5 ms per-root inference stop threshold, so measured inference latency is
reported without blocking the smoke runs.

The 32-seed gameplay screen is not included here and must not run until
independent implementation review. After review, use exactly seeds
24100000..24100031, after first checking that this block has never been used.

## Frozen identities

- Branch: `codex/silver-prior-root-screen-20260923`
- Main merged into the experiment branch: `3d28adfcf3c989e338eff9ef85e4a5c6d8794497`
- Pre-merge experiment head: `9fe3cb05b4dfd367f9db1370d245cb8d1a4f978e`
- Frozen checkpoint: `b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`
- Native artifact: `/home/philippherrmann/Documents/sts/silver-prior-model-v1/native/T2.native`
- Native artifact SHA-256: `b3a4c5e4bbe91b7f17dadf588408a95199ec5b8b25f732d99ef0966c0ff05fdb`
- Native parity: [`native-parity.json`](native-parity.json)
- Native latency: [`native-latency.json`](native-latency.json)
- Smoke outcomes and per-combat telemetry: [`smoke.json`](smoke.json), raw CSV/log files in this directory

The smoke comparison is paired by seed, Ascension 0, 1,000 simulations per
combat decision, project-fair play, native OOC, Silver combat, Act 3 stop,
keys off, one thread, fixed root budgets, adaptive off, 32,768 allocated reuse
cap, exact visit lock off, and rho racing off. The treatment differs only by
loading the frozen native prior; the existing policy prior remains unchanged.

## Interpretation boundary

The two smoke outcomes are not evidence that the model improves gameplay.
They establish whether the runtime contract works: completed arms, correct
simulation counts, prior calls only in eligible ordinary decisions, zero
surface failures, matching PUCT/evaluation counts, and retained-root reuse.
The offline negative result remains visible and unchanged.

Knowledge impact: current model and integration contract are documented by the
implementation and this experiment evidence packet; no offline evidence was
changed.
