# Optimizer's-curse shrinkage on the §727 value chooser (offline, no seeds)

Idea 8 of [search-and-value-literature.md](../../../knowledge-base/research/search-and-value-literature.md):
any value-led override should use α·ΔV with α the out-of-sample slope (§715: 0.16-0.18). Question (Philipp,
2026-11-01): on §727's choice logs, do the overrides that survive shrinkage (α·ΔV > 1 pp) still lose? If they lose
as much per choice as the rest, the head's sign (direction at large gaps) is wrong, not only its scale.

**Post hoc on read data.** §727's outcomes were read for its verdict; this re-slices the same 1,536 units. The rule
below was written before this script was first run, but the data are not fresh.

## Data
`/mnt/project-files/value-chooser-ab/units/*.tar` (§727, RUN_COMMIT 3d62ff5e, 1,536/1,536 units). Per unit: arm A
and B outcomes (`heartKilled`) and B's `B-<seed>.chooser.jsonl.gz` (29,330 choices: top-3 candidates by prior, each
with prior and V_A1/V_A2 value, and the chosen index; index 0 = the prior's top = A's pick at that state).
`extract.py` → pickle, `analyze.py` → [result.json](result.json).

## Definitions
- Override: B picked a candidate other than the prior's top. ΔV = V(chosen) − V(prior top) (Heart-kill units).
- Surviving override: α·ΔV > τ. Main cell α = 0.17, τ = 1 pp (ΔV > 0.059); grid α ∈ {0.16, 0.17, 0.18},
  τ ∈ {0.5, 1, 2} pp.
- Primary (clean): B's trajectory equals A's until B's **first** override, so the first override's ΔV is assigned
  before any divergence. Units split by whether their first override survives (L) or not (S); outcome = Heart kill
  B − A per unit. Bootstrap 95% CIs over units.
- Rule: if L's CI lies below 0 and L − S does not exceed 0, surviving overrides still lose → not a scale-only
  problem (sign/direction wrong at large gaps too). If L's CI includes 0 and L − S > 0, shrinkage would help (scale).
  Else inconclusive.
- Secondary (endogenous, disclosed): per-unit regression of B − A on the counts of surviving and non-surviving
  overrides (counts depend on how long B survives, which biases both slopes upward).

## Result
- Shrinkage removes almost everything: of 13,939 overrides, 7.8% survive at α 0.17, τ 1 pp (2.5% at 2 pp, 21.7% at
  0.5 pp). ΔV quantiles: median 0.011, 90% 0.051, 99% 0.171.
- **Primary (α 0.17, τ 1 pp):** L (41 units) −19.5 pp [−34.1, −4.9]; S (1,488) −14.9 [−17.3, −12.7];
  L − S −4.6 [−20.2, +11.1]. The README's rule as first written read L's CI below 0 as "not scale only"; the
  review (reviewer K, 2026-11-01) showed that L alone is confounded: L units go on to make 8.3 more overrides each
  (0.8 surviving), S units 8.1 (0.68), and S loses −14.9 pp from that same later stream. The contrast that isolates the
  first surviving override is **L − S, which includes 0 in every grid cell → INCONCLUSIVE on the sign question.**
- Grid: L − S −2.2 to −4.6 pp at τ 0.5 and 1 pp for all α, every CI including 0 (L alone −16.9 to −19.5).
  At τ 2 pp (16-17 units, ΔV > 0.11) L is 0.0 / −5.9 pp with CIs about ±19 pp: uninformative.
- First-override ΔV bins (Heart kill B − A): ≤0.005 −14.0, 0.005-0.01 −14.3, 0.01-0.02 −18.2, 0.02-0.04 −13.5,
  0.04-0.059 −22.0, 0.059-0.1 −34.8 [−56.5, −17.4] (23), > 0.1 0.0 [−22, +22] (18). No dose-response toward gain;
  linear slope −1.4 pp per 0.1 ΔV [−13.5, +10.2].
- Count regression (α 0.17, τ 1 pp): constant −15.7 pp, per surviving override −2.7 pp [−5.6, +0.2], per
  non-surviving +0.3 [−0.4, +1.0] (survival bias pushes both up).
- No unit had all its overrides survive, so a shrunk chooser cannot be replayed exactly from these logs.
- 1,086 overrides (7.8%) tie the prior's top in prior; counted as overrides as in §727.

## Reading
**INCONCLUSIVE on the sign question.** Shrinkage would have stopped ~92% of the overrides. Whether the ones it keeps
are worse, equal or better than the rest is not measurable here: every unit keeps overriding afterwards (about 8 more
overrides, mostly small), so a unit's outcome is dominated by that later stream, and the contrast for the first
surviving override (L − S, −4.6 pp [−20.2, +11.1]) includes 0. The count regression ([−5.6, +0.2]) and the bins
(−34.8 pp for 23 units, 0.0 for 18) do not settle it either. What the logs do show: under α ≈ 0.17 and a 1-pp
margin, a shrunk chooser would override about 0.7 times per game instead of about nine times. Shrinkage stays a required
guard for any future value-led decider; no shrunk-chooser A/B is proposed for V_A1/V_A2 (§727's failure and this
evidence give no reason to expect a gain). A clean test of the large-gap sign would need a chooser that overrides only
above the margin, i.e. a new A/B.
