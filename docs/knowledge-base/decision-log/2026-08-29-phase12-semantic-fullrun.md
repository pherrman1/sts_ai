# Phase-12 semantic survival-tradeoff full-run adjudication

Date: 2026-08-29

## Decision

Keep the explicit survival-versus-strength decomposition classified as
**INCONCLUSIVE**. Do not promote a combined-product OOC rule or begin model
training from this experiment.

## Evidence

The prospective manifest united the 18 and 19 independently fresh-confirmed
Phase-12 contexts without terminal-outcome reselection. It contained 37
decisions from 36 source seeds; seed `810008` contributed two decisions. Each
frozen semantic safe/strength pair received 16 fresh matched terminal
continuations at 1,000 reference combat simulations. All 1,184 branches were
valid, and every sibling future shared its hidden-encounter and
continuation/search seed.

Safe actions won 17 contexts, strength actions won 12, and 8 tied. Combined
product was correct on 19/29 non-tied contexts, versus 17/29 for survival,
12/29 for strength, and 16/29 for dense K3. Its mean selected terminal-win rate
was 0.3851 and mean regret 0.0473, the best point estimates among the four
frozen rules.

The source-seed-clustered paired 95% intervals nevertheless included zero:

- combined minus survival: `+0.02027 [-0.02404,+0.06771]`;
- combined minus strength: `+0.03209 [-0.03125,+0.09539]`;
- combined minus dense K3: `+0.02027 [-0.02431,+0.06908]`.

The existing promotion rule requires intervals above zero against both primary
baselines in addition to better point accuracy and regret. That condition did
not pass. The evidence is favorable in direction but not decisive.

## Provenance

- Baseline semantic K3 evaluator:
  `bb41af08c4e2b4ff1757dfaeb064113eb184684f`.
- Reviewed full-run evaluator and scientific SHA:
  `4794647faf989cc0710c4239302d4cb27b27b053` (PR #83, Linux GCC passed).
- Frozen manifest SHA-256:
  `6E7B8EDB608B61C45FB9CBC6A1375FD1770759BCA0287F4F6C77EF3C040C5988`.
- Raw adjudication SHA-256:
  `F1F842FE773C17E9EF7A1999A3189C03540DD80E6E383E4ED68422D467828F9A`.
- Exact Release executable SHA-256:
  `B9E592991AAFC77454485E5B8182CB682E8AE92AA1425987D95AC12F1059026F`.
- Future identities: `1000000--1000015`; 1,184 branches; elapsed 16,647 s.

## Boundaries

Act and screen breakdowns are descriptive because their cells are small. The
result does not test alternative K horizons or combat-search budgets, and it
does not justify tuning those quantities against these terminal outcomes. No
production behavior, model, training data, or OOC trajectory collection was
changed.
