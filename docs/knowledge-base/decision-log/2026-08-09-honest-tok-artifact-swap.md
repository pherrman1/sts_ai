# 2026-08-09 — Honest V4 token-net artifact swap: leaky → honest

Date: 2026-08-09
Session/task: User directed replacement of the stale, leaky V4 token-net
artifact with the honest NGLOB=42 model. Prompted by the investigate pipeline
finding that the git-tracked `ooc_strategic_tok_final.native` (NGLOB=50,
sha256 `05178ec8…`) contained 8 hidden-information leaks and was rejected by
the current C++ loader (dims-check failure: "truncated payload").

## Decision

Replaced `selfplay/models/ooc_strategic_tok_final.native` with the honest
NGLOB=42 model (previously `ooc_strategic_tok_honest_v2.native`, sha256
`f6bc6a96…`). The old leaky artifact is not separately preserved (its sha256
and properties are recorded in the prior audit decision log).

### Verification

Startup output now shows:
```
[ooc-strat-tok-net] loaded selfplay/models/ooc_strategic_tok_final.native
[OOC one-ply strategic TOK net ON: card rewards gated at margin 1]
```

Previously: `[ooc-strat-tok-net] truncated payload` with no TOK net ON message.

### Performance caveat

The honest model's gate benefit collapsed from ~+20pp (leaky, 41.4% vs 21.1%
baseline) to negligible or negative:
- NGLOB=41 honest (no bossId): 22.7% vs 21.1% (§142 gate)
- NGLOB=42 honest (bossId restored): 15.6% vs 21.1% (192-seed gate)

Both were measured on the older S2-fair @1k base, not the current S3+vnet
stack. The honest model's contribution on the recommended S3−belief−chain +
V_combat-honest-leaf stack is **unmeasured** as of this swap.

## Rationale

User directive: "i dont want to use any leaky model." The prior state violated
this — the tracked artifact was leaky and couldn't even load on HEAD. Honesty
is non-negotiable even when it costs winrate.

The leaky model exploited 8 hidden-information features (exact next elite/fight
identities, queue sizes/offsets) that are not player-observable in Slay the
Spire. bossId (the act boss) is player-visible and was retained.

## Alternatives considered

- Keeping the leaky artifact tracked but documenting that it's leaky — rejected:
  the user explicitly prohibited leaky models, and the artifact can't load on
  HEAD anyway.
- Keeping the old artifact at a separate path for reference — rejected: its
  sha256 is recorded in the audit decision log; historical EXPERIMENTS.md
  entries that cite it by name+sha remain valid historical records.

## Evidence

- 2026-08-09 feature-leak audit: `docs/knowledge-base/decision-log/2026-08-09-v4-feature-leak-audit.md`
- Honest model gate results: same log, lines 96–103 (NGLOB=42 192-seed gate: 15.6%)
- Startup load verification: this session, seed 126700 @1k S3 fair, `[ooc-strat-tok-net] loaded`
- Artifact hashes: old NGLOB=50 `05178ec8…`, new NGLOB=42 `f6bc6a96…`

## Status

- **Done.** Artifact swapped and verified loading.
- **Noted.** The V3 strategic net (`selfplay/models/ooc_strategic.native`,
  sha256 `b096498abf…`) is also leaky — it consumes `richRow()` features
  which include all 8 hidden-information leaks unfiltered. It is not in the
  recommended config but is a git-tracked artifact used by experimental
  ablation scripts. Fixing it would require changing `richRow()`, which is
  shared with the native floor/win GBMs.
- **Open.** The honest model's contribution on the S3+vnet stack is unmeasured.
  A paired gate (gates ON vs OFF, honest model, S3−belief−chain + vnet α=0.3)
  is needed before the recommended configuration row can honestly claim OOC
  gate benefit.
- **Open.** If the gate shows null/negative, the recommended config should drop
  the OOC gates and rely on native floor/win GBMs + heuristic path/shop/win-rest
  instead.
