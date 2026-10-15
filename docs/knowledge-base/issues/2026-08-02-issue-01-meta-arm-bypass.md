# Issue 01: Self-play meta arm bypasses its candidate models

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`operations/selfplay-loop.md`](../operations/selfplay-loop.md), "Blocking discrepancies"

## Symptom

The self-play meta arm starts a server with candidate V_win/rest models, but
`one_combat` keeps native OOC enabled and uses the fixed tracked floor/win
trees, so the candidate models never own any decision. No meta gate or
promotion is valid until arm-specific loading and use are demonstrated.

## Evidence

- `selfplay/loop.sh::start_server` launches candidate `v_win.json`/`rest_cf.json`
  models, but `FLOOR_POLICY_ENV`/`WIN_POLICY_ENV` do not set `STS_NATIVE_OOC=0`.
- `apps/one_combat.cpp::main` defaults native OOC on; `vQueryRestCounterfactual`
  and win-rest helpers return without using the server.
- Same finding in [`behavior/invariants.md`](../behavior/invariants.md), "Known
  limitations".

## Why it matters

Self-play is the promotion path for learned OOC models. A gate that cannot
exercise the candidate produces misleading qualification evidence and can
promote artifacts that were never measured.

## Candidate fix direction

Disable native OOC for meta gates (verify server artifacts own every intended
decision via startup/trace evidence) or export/load arm-specific native trees.
**Inference:** the design intent was server-backed meta gating, based on
`start_server` existing.

## Relevant code

- `selfplay/loop.sh::start_server`, `run_gate_batch`
- `apps/one_combat.cpp::main`, `vQueryRestCounterfactual`

## Resolution (2026-08-02)

Fixed in `selfplay/loop.sh` (2026-08-02): `META_POLICY_ENV` adds `STS_NATIVE_OOC=0` for meta datagen and meta gates, so candidate V_win/rest models own meta decisions; `start_server` port-liveness failure fails the batch. Residual gap: candidate use is evidenced by env plus port liveness, not a per-decision query log (open question in `selfplay-loop.md`).

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
