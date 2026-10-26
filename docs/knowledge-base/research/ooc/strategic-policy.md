# Strategic out-of-combat policy

Last verified: 2026-08-11.

## Purpose / research question

Can a learned one-ply Q-gate policy improve out-of-combat decisions (card
rewards, rest, events, shops, treasure, boss relics) over heuristic rules?

## Current conclusion

**The V4 token-net one-ply Q gate stack is the recommended OOC configuration**
when opt-in, providing significant win-rate gains at the cost of a deployed
model artifact. However, the gates are opt-in — the binary default plays
without them.

Key facts:

- Full gate stack (V4 token net, all screens ON, margin 1.0): +8–14pp over
  flags-off baseline at matched sim budgets.
- V4 token net ≈ V3 strategic net at matched budgets (§92/§99); V4 is the
  deployed format since 2026-08-03.
- **V4 gates help Act-4 survival but hurt Act-3-only performance** (§153):
  gates ON 21.9% with Act 4 (31.2% Act-3-only); gates OFF 6.3% with Act 4
  (37.5% Act-3-only). Net: gates are −6.3pp Act-3-only but +15.7pp with Act 4.
- The deployed V4 artifact is `selfplay/models/ooc_strategic_tok_final.native`
  (sha256 `e62abd83…`, §149 skewfix model, 42-glob, honest).
- The margin-gated design means actions are overridden only when the Q(s,a)
  advantage exceeds a threshold (margin 1.0), preserving a heuristic fallback.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-08-02 | [§70-§71 Phase 5 rounds 1-2](../../../../docs/experiments/ledger-03.md) | All-actions datagen + Tier-A net; card gate negative/neutral |
| 2026-08-02 | [§73 Round 3: Tier-B Q labels](../../../../docs/experiments/ledger-03.md) | Q-head card gate fires at margin 1.0 |
| 2026-08-02 | [§74 Round 4: campfires + events](../../../../docs/experiments/ledger-03.md) | Cards+rest+event +7.0pp |
| 2026-08-02 | [§75 Round 5: V4 token net](../../../../docs/experiments/ledger-03.md) | V4 ladder + paired gate; +3.1pp at m5; V3 stays default |
| 2026-08-02 | [§76 Round 6: full gate stack](../../../../docs/experiments/ledger-03.md) | +18.8pp statistically established |
| 2026-08-03 | [§81 V4 full gates + §82 margin + 256 block](../../../../docs/experiments/ledger-03.md) | V4 top arm 41.4% |
| 2026-08-04 | [§99 V4 @3k sims top arm](../../../../docs/experiments/ledger-04.md) | 45.3% at 3k sims |
| 2026-08-09 | [§149 V4 glob-skew fix + retrain](../../../../docs/experiments/ledger-06.md) | Deployed model stays skewfix |
| 2026-08-09 | [§153 Ascension sweep](../../../../docs/experiments/ledger-06.md) | Gates essential for Heart; hurt Act-3 only |

## Rejected / falsified approaches

- **Pooled-head regression (V2)** — −10.9pp at margin 1.0 (§70)
- **PPO/GAE action-value heads** — negative (§78)
- **Policy-score gate (Phase F)** — every arm loses to Q-gate; falsified (§104)
- **Q_win probability-point margins** — negative (§96)
- **Label-noise reduction (futures, denoising, quantization)** — all null (§105)
- **Map-route Q gate (M1)** — negative at every margin (§91)
- **C_psi route search (M2)** — negative (§93)
- **Shop beam search (B1)** — negative (§85)
- **Map-DAG encoder (V6)** — offline gain, gameplay neutral-to-negative (§100)
- **Fixed-stats V4 retrain** — S2 negative, S3 significantly negative (§108)
- **Corrected honest V4 on Act-3 stack** — inconclusive due to reproducibility failure (§155), later confirmed at 128 pairs (§163)

## Relationships

- [encounter-marginalization.md](encounter-marginalization.md) — M0/M1 are alternative strategic label sources
- [external-evidence-and-ideas.md](external-evidence-and-ideas.md) — external benchmarks, expert play and ranked candidates for the A20 plateau
- [leaf-evaluation.md](../combat-search/leaf-evaluation.md) — combat VNet interacts with gate decisions
- [searcher3.md](../combat-search/searcher3.md) — gate stack tested under both S2 and S3

## Current implementation

All gates are **opt-in** via `STS_OOC_STRATEGIC_TOK_NN=<path>` and per-screen
`STS_OOC_STRATEGIC_{CARD,REST,EVENT,SHOP,TREASURE,BOSS_RELIC}=1` flags.
Global margin: `STS_OOC_STRATEGIC_MARGIN` (default 1.0).

The V4 token net uses a 42-glob + counted-deck-token + relic-token + potion-token
state representation. The Q head is trained on Tier-B one-ply counterfactual
labels from `strategicgen2`.

See [`docs/knowledge-base/architecture/out-of-combat.md`](../../architecture/out-of-combat.md).

## Open questions

- Should the honest V4 model be promoted to the recommended configuration? (§163 confirmed at 128 pairs)
- Can the Act-3 regression be addressed without losing Act-4 benefit?
- Is a full-stack recommended measurement (V4 gates + S3 + 7k-vnet) needed?
