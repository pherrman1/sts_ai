# ADR-0063: Sapphire and Ruby follow the policy, Emerald masks the Act-3 route, by default

Date: 2026-10-27
Status: accepted

Amends [ADR-0041](0041-a20-heart-objective.md)'s key-choice rules; the Heart objective itself is unchanged.

## Context

ADR-0041 forced every key choice: Sapphire at the first chest that offers it, Ruby Recall at the first Act-3
campfire, and on the Act-3 map the first legal edge still reaching the burning elite. PR #611 added opt-in variants
(`STS_KEY_SAPPHIRE`, `STS_KEY_RUBY`, `STS_KEY_EMERALD`), and every campaign since §569 set the flexible ones
(`policy`, `policy`, `mask`), but they were never tested against the default.

§691 tested them: 1,024 paired A20 seeds with student_sel alone on main `db216ff0` (Act 4 strong). Flexible keys killed
the Heart in 26.8% of runs and the ADR-0041 rules in 20.7%: +6.05 pp [+3.42, +8.59], exact McNemar p 8e−6; Act 4
+7.6 pp. 901 of 1,024 pairs first diverge at the Act-1 Sapphire offer, where student_sel usually keeps the chest relic.
Philipp chose on 2026-10-27 (decision card, 07:20Z): "Yes, separate PR".

## Decision

- With `STS_KEY_*` unset: `STS_KEY_SAPPHIRE=policy` (the policy decides; the Act-3 treasure row is the backstop),
  `STS_KEY_RUBY=policy` (the pre-boss campfire is the backstop), `STS_KEY_EMERALD=mask` (Act-3 candidate edges are
  limited to those still reaching the burning elite; an edge is forced only when one remains). Acts 1–2 stay the
  policy's choice for the burning elite, as before. Emerald is still always taken when offered.
- `first` restores the ADR-0041 rule for that key; all three `=first` reproduce the old default. `act3`, `hp` and
  `STS_KEY_RUBY_MIN_HP` keep their meaning.
- The rules apply wherever keys are collected (`STS_COLLECT_KEYS`, default on): whole runs, the data generators, OOC
  MCTS's tree rules and the live advisor. The evidence is at ascension 20, where all current research runs.
- `HeartKeyRules{}` still holds the ADR-0041 rules; `isAdr0041()` (was `isDefault()`) reports them. The startup line
  `heart_key_rules sapphire=… ruby=… ruby_min_hp=… emerald=…` now prints under the default and stays silent under all
  three `=first`.

## Consequences

- Play changes on every run that reaches a Sapphire offer, an Act-3 campfire without Ruby, or an Act-3 map without
  Emerald. Campaign configs that already set the flexible flags play byte-identically (checked on 4 §691 seeds, both
  directions).
- Comparability: runs from before this ADR that left the flags unset are reproduced with
  `STS_KEY_SAPPHIRE=first STS_KEY_RUBY=first STS_KEY_EMERALD=first`; freeze files must record the flags.
- The live advisor plays flexible keys after its next reinstall (which needs Philipp's typed OK).
- With OOC MCTS on, the search chooses key timing too; that combination is untested beyond §569's descriptive run.
