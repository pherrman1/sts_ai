# ADR-0028: The native OOC fallback scores 8 public encounter futures by default

Date: 2026-10-12
Status: accepted

## Context

The native OOC fallback (card, shop, remove, rest and upgrade picks with the
tracked floor/win trees) builds its rich vector from the live `GameContext`,
including the realized `nextEliteId` and `nextFight0..2`. These four fields are
the only hidden-future inputs of the rich row (§371), and both tracked tree
ensembles split on them (§438). `STS_FAIR=1` does not remove them, so default
play read information a player cannot see. OOC MCTS is not affected: it
resamples the queues at its root.

`STS_OOC_PUBLIC_FUTURES=8` (research control since 2026-10-08) replaces the
four fields with 8 sampled, public-history-conditioned futures and averages
the predictions. On 128 paired seeds (§434, PR #490) it won 104/128 vs 103/128
for the legacy inputs, +0.8 pp [−4.7, +6.3], at about the same run cost.

Philipp chose to make it the default on 2026-10-12, until the floor/win trees
are retrained without the hidden fields.

## Decision

- `STS_OOC_PUBLIC_FUTURES` unset means 8. Explicit `0` restores the legacy
  hidden-information inputs exactly; other values 1..256 are unchanged.
- In Act 4 (fixed elite and boss, no hallway queue) the fallback scores the
  state as it is, without a mixture; before this change Act 4 threw when the
  control was enabled.
- Everything that calls the shared scorer follows the default: `bestbench`
  and the other run modes, generator main trajectories and their
  `vStateRaw`/`vStateWin` branch bootstraps (including `STS_CF_ALT_BOOT_*`),
  and the live advisor's native fallback.

## Consequences

- Default play changes (73 of 128 §434 runs diverged), so earlier default-stack
  numbers are not directly comparable with new runs. Reproducing them needs
  `STS_OOC_PUBLIC_FUTURES=0`.
- Teacher policy specifications now record `native_ooc_public_futures: 8`, so
  frozen teachers without that field fail identity checks unless run with
  `STS_OOC_PUBLIC_FUTURES=0`.
- Each fallback evaluation costs 8 tree predictions instead of 1.
- A floor/win model trained without the four hidden fields makes the mixture
  a no-op; the default can then return to 0 for speed.
