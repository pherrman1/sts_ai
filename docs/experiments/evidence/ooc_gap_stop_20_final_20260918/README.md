# OOC 20% gap-stop final quality confirmation

This packet records the predeclared independent paired confirmation of the
frozen OOC-MCTS candidate. The gameplay executable was not rebuilt.

## Frozen provenance and protocol

- Execution source SHA: `495fa147517fdc42e631c513bde5a87b3bb25144`
- Frozen `one_combat` SHA256:
  `9a3b8c2bd1e563c691926d823c43767430d03c11b97a9c5f0d924e616beb1250`
- Cohort: `12005000..12005127`, exactly 128 paired seeds
- Ironclad A0, project-fair, Act-3 stop, keys off
- One OMP1 process per seed, up to 12 concurrent workers, 600-second ceiling
- Control first; treatment launched only after all controls validated
- Control: `STS_OOC_MCTS_GAP_STOP_20=0`
- Treatment: `STS_OOC_MCTS_GAP_STOP_20=1`
- OOC MCTS: 2,048 simulations, policy prior, temperature 1, cPuct 1.5,
  widening 2/0.5, max depth 32, visit-root selection, exact visit-lock ON,
  native leaf, zero leaf combats, V4 continuation policy
- Silver: exact 10,000 simulations, allocated reuse cap 32,768, adaptive OFF,
  exact-root budgets ON, exact-visit-lock/rho racing OFF
- Diagnostic checkpoint, root-lock, and CPU-profile modes were OFF

The control arm was initially interrupted after seeds through `12005059`.
The remaining 68 controls were rerun into fresh paths; no partial artifact was
appended, no seed was replaced, and all 128 controls were validated before
treatment began.

## Result

| Metric | Control | Treatment | Paired treatment minus control |
|---|---:|---:|---:|
| Wins | 95/128 (74.22%) | 88/128 (68.75%) | -5.47 pp, 95% CI [-12.50, +1.56] pp |
| Mean floor | 48.34 | 48.40 | +0.06, 95% CI [-1.26, +1.33] |
| Mean ending HP | 37.95 | 36.48 | -1.47, 95% CI [-7.01, +3.97] |

Paired outcomes were 81 both-win, 26 both-lose, 14 control-only, and 7
treatment-only. The exact two-sided discordant-pair/binomial p-value was
`0.1892471313`.

Treatment produced 11,777 20%-gap stops across all 128 seeds; control produced
zero. Control and treatment had respectively 93 and 75 unsupported-combat
support aborts, with zero continuation-limit aborts. Full simulation,
ownership, fallback, root-stop, and support accounting reconciled for every
run. The machine-readable totals and all paired bootstrap intervals are in
[`analysis.json`](analysis.json).

## Decision

**`OOC_GAP_STOP_20_FINAL_PASS`**

All 256 processes completed with clean exit status and valid frozen
provenance. The win-rate interval does not establish a regression, and the
floor/ending-HP evidence does not show a convincing meaningful downside. The
bounded conclusion is:

> No meaningful quality regression detected at this bounded confirmation,
> combined with the previously established speed benefit.

This is not equivalence proof and does not promote the flag to the default.
Independent review remains required before any default or deployment change.

## Unresolved verification note

A seed-free `oocmctsselftest` run with the full Silver environment emitted:
`FAIL oocmctsselftest: same sole wheel primitive hides a fallback agent RNG
draw`. This is a self-test-only assertion; it did not consume a cohort seed or
alter the frozen executable. The general 21-case OOC startup matrix passed,
and all 256 actual gameplay processes completed with clean exits and validated
Silver/provenance metadata. The assertion remains unresolved and is explicitly
not treated as cleared by the gameplay run; it requires independent review
before any default or deployment decision.

## Model hashes

| Artifact | SHA256 |
|---|---|
| CTM `combat_transition_near_full_except_smoke_v2.native` | `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd` |
| V4 OOC token net `ooc_strategic_tok_final.native` | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` |
| Native V_win `models/v_win_trees.txt` | `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70` |
| Native V_rich `models/v_rich_trees.txt` | `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3` |
| Policy trees `models/policy_trees_c.txt` | `24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321` |

The [`raw/`](raw/) directory preserves the result CSV, metadata JSON, MCTS
trace, support JSONL, exit record, and log for every arm/seed. The complete
SHA256 manifest is [`SHA256SUMS`](SHA256SUMS).
