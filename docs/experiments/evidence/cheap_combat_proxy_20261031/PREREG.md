# Cheap-combat proxy check (roadmap experiment X1, pre-registration, 2026-10-31)

Philipp, 2026-10-31 22:27Z: "Okay try den billigen Kampf" (X1 of [the one-year roadmap](../../../knowledge-base/research/one-year-roadmap.md)).

**Question.** Does an out-of-combat policy effect measured with production combat survive when real combats are played
by flat cheap Silver (1,000 or 200 sims per decision)? If yes, PPO self-play and OOC screens can use cheap combat
(17-40× cheaper per game).

**Known effect.** §691: flexible keys (F: `STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask`) vs the
rigid ADR-0041 rules (R) with student_sel alone, +6.05 pp Heart kills [+3.42, +8.59] on 1,024 paired seeds.

**Arms** (`run_unit.sh`, one unit = one seed): R/F × combat C:
- C = 1000, 200: flat Silver C sims per decision (`STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0`, bestbench C).
- C = P (same-runner production control): learned Silver stop, Act 4 strong (bestbench 10000).
Out of combat every arm runs `STS_OOC_MCTS=0` with student_sel (`cf6bf7fb`): key rules, then student_sel's argmax.
This differs from §691's runner (heartoutcomegen with OOC MCTS on and no searched screens, which runs the
chest/relic/gold/potion rule chain before student_sel); heartoutcomegen refuses a non-10k real-combat budget, so it
cannot play cheap combat. The P arms measure the key effect on this runner.
Key flags are explicit in both arms (R `=first`), so the effect does not depend on the binary's default.

**Provenance.** Binary `d74cfded889b9440…` = §691's binary (code `db216ff0`, from the bin cache); `models/` and
`selfplay/models/` at the run commit are byte-identical to `db216ff0`. One 4-CPU cloud container, 4 lanes.

**Seeds.** §691's 1,024 seeds 111382000-111383023 (USED; replays, nothing new consumed), so every seed is also paired
with its production result in §691. Smokes: 111383024 (cheap arms) and 111383025 (P arms), both §691 smokes (USED).

**Primary metric.** For C = 1000 and C = 200 separately: D_C = Heart kill F − R over the paired seeds, 95% seed
bootstrap (10,000 resamples, `analyze.py`). P = §691's +6.05 pp.
- VALID: CI lower bound > 0 and D_C within [0.5 P, 1.5 P] = [+3.03, +9.08].
- INVALID: CI upper bound < 0.5 P.
- INCONCLUSIVE otherwise.
A seed counts for C only if both of its C games finished as frozen (rc 0); missing games are reported, not imputed.

**Secondary (descriptive).** Heart and Act-4 levels per arm; D_P on this runner; per seed difference-in-difference
(F_C − R_C) − (F_P − R_P) with bootstrap CI where the control ran; mean wall per game per arm.

**Decision.** VALID at C = 1000 → PPO self-play and cheap OOC screens may use flat Silver 1,000; at C = 200 also →
Silver 200. INVALID at both → phase 3 of the roadmap needs production-strength combat and is re-costed.
A pass is necessary, not sufficient: the key effect sits mostly at the act-1 Sapphire chest (§691), an OOC choice whose
value may not depend much on combat skill.

**Cost.** Cheap arms ≈ 1,024 × (2 × ~14 s + 2 × ~6 s) ≈ 11 core-h (local). The P control is ~237 s per game; its size
is Philipp's call (decision card).
