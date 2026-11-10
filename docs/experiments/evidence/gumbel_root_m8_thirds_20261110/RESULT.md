# Gumbel root with m = 8 candidates or thirds instead of halving: offline check (no games)

**Question (Philipp, 2026-11-10 15:24 CET):** how much does the root prior drive G16 + mb4's Gumbel root, and would
starting sequential halving at m = 8 instead of 16, or cutting to a third instead of a half, be worth a gate?
**Decision (Philipp, 2026-11-10 15:43 CET, decision card):** drop the topic; no gate, no default change.

## Data and method

- 574,741 roots of the 1,024 traced G16 + mb4 whole runs of the Gumbel stop-trace data campaign (#1025, seeds
  111430000-111431023, code c718ee47; share `/mnt/project-files/gumbel-stop/data/units`). One trace row per
  sequential-halving boundary: leader, runner-up, their Q and prior, the final pick.
- `analyze.py UNITS_DIR results/result.json` (about 1 min on 8 processes). Descriptive only; no game was played with
  m = 8 or thirds.
- Code fact (`SilverSearcher::searchGumbelRoot`): the candidates are the `min(legal, k)` best edges by g + log prior,
  phases = ceil(log2 candidates), equal budget per phase. With a flat budget, m changes how the 16,000 simulations are
  split, not the CPU.

## Results

**Legal root actions:** median 6, p90 10, p99 17. 80.7% of roots (77% of root CPU) have at most 8, where m = 8 plays
exactly as m = 16; 18.1% have 9-16, 1.1% more than 16.

| legal | roots | CPU | final = first Gumbel sample | est. final in prior top 8 | last boundary: exact Q tie / real Q flip |
|---|---|---|---|---|---|
| 2 | 9.1% | 7.1% | 78.2% | 100% | 0 / 0 |
| 3-4 | 25.7% | 20.8% | 55.0% | 100% | 11.6% / 0.31% |
| 5-8 | 45.9% | 48.6% | 34.0% | 100% | 15.2% / 0.74% |
| 9-12 | 14.9% | 18.5% | 21.4% | 85% | 10.3% / 1.00% |
| 13-16 | 3.2% | 3.6% | 15.7% | 67% | 7.0% / 1.19% |
| 17-24 | 0.9% | 0.8% | 13.9% | 56% | 7.7% / 0.73% |
| 25+ | 0.3% | 0.6% | 8.8% | 22% | 2.4% / 0.06% |

"est. final in prior top 8": Monte Carlo Gumbel-top-8 inclusion of the final pick's prior with the remaining mass
spread equally over the other edges (pessimistic). About 3-4% of all roots would lose G16's pick under m = 8.

**After phase 1 (halving budgets), the final pick is the leader / in the top 2:** n = 5: 74% / 93%, 6: 68% / 89%,
7: 60% / 82%, 8: 56% / 79%, 9: 50% / 73%, 12: 44% / 65%, 16: 37% / 56% (`boundary1_by_n`). Thirds keep
ceil(c/3) (2 of 5-6, 3 of 7-9), so they would drop G16's eventual pick after phase 1 in roughly 10-20% of the roots
with 5 or more actions (top 2 is a lower bound for top 3; thirds' phase 1 would have 1.5× the simulations). The
winner also gets fewer simulations (n = 8: 1,000 + 2,667 = 3,667 vs halving's 667 + 1,333 + 2,667 = 4,667).

**Prior at the root:** sigma = (50 + max visits) × normalised Q is in the thousands after phase 1 and outweighs
g + log prior. At the last boundary the two finalists have exactly equal Q in 13.0% of roots (equivalent actions),
where the prior and the noise decide harmlessly; a lower-Q finalist wins in only 0.68% of roots with 3 or more actions.

## Interpretation (Inference)

- m = 8 changes nothing on 81% of roots and saves no CPU; elsewhere it trades G16's pick in a few % of roots for more
  simulations per candidate. §776's screening already measured k 8 → 32 at −0.11 HP per fight [−0.27, +0.07]
  (INACTIVE, slight lean to larger k) and the halving budget as INACTIVE.
- Thirds change most roots with 5+ actions, cut early on rankings that are still noisy, and give the winner fewer
  simulations. No CPU saving either.
- The root prior is close to a tiebreaker at the root. Its influence sits below the root (tree prior, §776 G/H:
  about ±0.2 HP per fight), and a better net as root prior gained nothing (§773).
- A whole-run gate (G8 + mb4 vs §775's reused G16, about 175 lane-hours) would expect well under 1 pp, below what
  1,024 paired seeds resolve (95% half-width about 2.8 pp).
