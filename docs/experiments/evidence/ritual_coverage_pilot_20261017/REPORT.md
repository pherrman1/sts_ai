# Controlled A0 Ritual coverage pilot — result (2026-10-17)

**Classification: `PILOT_COVERAGE_INCONCLUSIVE`.** All 144 planned units ran
and passed capture integrity, but positive Ritual growth was too rare to meet
the preregistered coverage thresholds, especially in VALIDATION.

## Frozen packet

- Source `55837b02584dbb166ba44bc8613332701c69738d` (reviewed live ancestor `8879b531`).
- `one_combat` Release SHA-256 `d02d4a1da1081b1dd3190f1eddacb7cc1f6b350fa02cd39ca3e93662b423da0b`
  ([build-receipt.json](build-receipt.json)).
- Recipe SHA-256 `f4b715b3f7e0634b8cf305744fc3e8a0af6adb6acb882bb83e3cc8827e0d6b55`; 8 TRAIN + 4 VALIDATION
  sources × 12 cells per [PROTOCOL.md](PROTOCOL.md). Workers raised from two to eight on
  Philipp's approval ([resource-approval.json](resource-approval.json)); per-unit 60 s / packet 90 min unchanged.
- Independent read-only review: first pass FAIL (launcher could not import its
  analysis modules when run as a script, which would have invalidated every
  unit after the one-use latch); fixed in `55837b02`, second pass PASS
  ([review.json](review.json)).

## Result ([result-summary.json](result-summary.json))

- 144/144 units valid, no stop, 223 s wall. Mechanics checkpoint (first source,
  12 cells) valid with every cell exercised.
- 494 normalized Writhing target fights (FAST 332, STANDARD 162); outcomes
  482 victory, 12 escape. No ordinary-child exclusions.
- Only **25/494 targets (5%) show positive permanent Dagger growth**. Source
  52000003 and VALIDATION 52000019 reached no Act-3 hallway target.
- 43 coverage cells missing. Every `cellPositive` VALIDATION cell is short
  (only 52000007 ever grew in VALIDATION); 10/12 TRAIN `cellPositive` cells are
  short; `upgraded_single_*` produced almost no positives. Named Brew/Smoke use
  coverage is ample in TRAIN; Brew is thin in VALIDATION.
- Raw rows, per-unit results and the full ledger (89 MB) stay local under
  `build/ritual-coverage-pilot-20261017/` (`result.json` SHA-256
  `47eb18dbd65374719c5d87aa407cc02cf60c6de9db6c5234286d5c94a44f93a2`,
  `freeze.json` `118e3ca195fefeaa27570a6069a901442d824693c70504ee7cddf340b3997a0a`,
  `unit-ledger.json` `60ee981cbd9f7d0afff02a5a144542cb854bd78ce3e9dbbcf8871dea4e782212`).

## Interpretation

The corrected producer and controlled setup work at scale with no integrity
failures. The bottleneck is behavioral: Silver rarely finishes a Writhing
Mass kill with a Dagger even when one is forced into the deck, so forcing the
pre-state alone does not yield enough positive labels. No retry, extension,
fitting, TEST access or support change was made. A follow-up needs either many
more sources (positives are ~5% per fight) or a design that raises Dagger-kill
frequency, as a new preregistered packet.
