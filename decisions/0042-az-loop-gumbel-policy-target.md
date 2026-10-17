# ADR-0042: The AlphaZero-style OOC loop trains its policy on Gumbel completed-Q targets

Date: 2026-10-17
Status: accepted

## Context

Philipp's planned stack for A20 Heart kills is an AlphaZero-like loop: a
distilled heart1 network as the out-of-combat (OOC) prior and rollout policy,
OOC MCTS as the teacher, and Silver inside combat. In such a loop the network
is trained on what the search decided at each real root.

At the loop's starting configuration (Arm C stack, 512 OOC simulations with the
visit-lock early stop) the search mostly follows its prior: in a 91-root smoke
the selected action was the prior's argmax in 76 roots, the median top prior was
0.985, and every root stopped on the visit lock at a median of 269 simulations
(`/mnt/project-files/audit-2026-10-17/ooc-mcts-adapter.md` §2). Visit shares
there mostly reproduce the prior. Root Q values measured for less-visited
actions are discarded by a visit-count target.

## Decision

- When the loop is built, its policy target is the Gumbel AlphaZero / MuZero
  improved policy `softmax(log prior + σ(completedQ))`, not raw visit shares.
  `completedQ` is the root action's search Q where visited and the root value
  otherwise; `σ` is a monotone scaling of per-root normalised Q.
- The scale of `σ` is fitted offline on held-out roots before training on it,
  because single rollout3 evaluations are noisy (§489).
- Captured decision rows keep raw visits, priors and Q as well, so the target can
  be recomputed later.

Philipp chose this on 2026-10-17 ("the gumbel alpha zero sounds perfect for us,
we should record that somewhere that we should do that").

## Consequences

The policy-target capture must record per-candidate prior, visits and Q at every
searched real root. Whether search improves on the prior at all is measured
separately (search vs prior alone at A20 Heart); this ADR fixes the target form,
not that the loop will improve play. No current default changes.

## Evidence

`/mnt/project-files/audit-2026-10-17/az-loop-plan.md` (F5-F7),
`/mnt/project-files/audit-2026-10-17/ooc-mcts-adapter.md` §2, ledger §489;
Danihelka et al., "Policy improvement by planning with Gumbel", ICLR 2022.
