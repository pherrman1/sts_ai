# Active Lizard correction in the DeepSets/Brew CTM stack

This packet records the bounded integration of the frozen PR #330 active
Lizard correction into the PR #351 DeepSets plus standard-Attention Brew
fallback stack. It does not repeat either qualification cohort.

## Baseline and frozen inputs

- Task's named baseline: `812ce0235e67aa9832142f69c6c8fc89d6875372` (PR #330
  merge).
- Checkout baseline used here: `be84fd934131395e87858195d74c169146a36ccf`,
  a later `main` descendant that includes the merged DeepSets/Brew
  confirmation work.
- DeepSets tensor payload SHA-256:
  `429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`.
- Gate 1 integration-candidate artifact SHA-256:
  `40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25`.
  This is a metadata re-export of the exact qualified tensors; Gate 3 will
  package the same payload with production metadata only after Gate 2 passes.
- Standard Attention Brew fallback SHA-256:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- Frozen Lizard candidate manifest SHA-256:
  `15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617`.
- Frozen q/r artifact SHA-256:
  `9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9`;
  frozen r-model SHA-256:
  `fbf29bf742e3c40b18a358386509a74ced54e97a2a7e760ff988de5c14a335a8`.

The digest in the pasted request for the standard fallback has 62 hex
characters and is not a SHA-256. The tracked artifact at the specified path
was rehashed and its valid 64-character digest above is used for the canary.

The candidate keeps `q = 1 - pOrdinaryWin` and the frozen learned
`r(pReserveWin)`. For a consumed-win sample, T2 sets both the stripped
pre-state and predictor input `curHp` to `floor(pre.maxHp/2)` before running
the existing conditional heads. The usual maxHP, signed-HP, potion, and relic
heads then sample the post-state. Gate 1 directly compares each forced T2
child against a native child prepared from the stripped state and predictor
with that transformed HP; the full serialized post-state and RNG engine must
match. The returned Tail remains present with `data=0` and its relic bit
preserved. Active Lizard plus Entropic Brew remains unsupported; Fairy Potion
and Mark of the Bloom retain their existing exact-path boundaries.

## Gate 1 — deterministic native parity

**PASS after correction.** The verifier covered all 320 frozen Stage-C rows
and checked native support, ordinary/reserve survival probabilities, q, r,
all three class probabilities, the Python-reference T2 head-input HP, Tail
state, HP legality, potion count, and RNG/state invariants on all three forced
outcome branches per row. The T2 branch is supported after transforming both
conditional-head inputs; its sampled post-HP is not forced to half the newly
sampled maxHP. Consumed wins retain Tail with `data=0` and the original relic
bit. There were zero support and semantic mismatches. Maximum absolute
probability errors were:

| Value | Maximum absolute error |
| --- | ---: |
| `pOrdinaryWin` | 5.364418029785156e-07 |
| `pReserveWin` | 3.5762786865234375e-07 |
| `qTailConsumed` | 5.364418029785156e-07 |
| `rWinGivenConsumed` | 3.884912700424792e-07 |
| three class probabilities | 5.364418029785156e-07 |

All are below the predeclared `1e-4` tolerance. The eight-row dispatch fixture
passed for ordinary DeepSets, Brew-to-Attention, active Lizard, active Lizard
with a later relic, spent Tail on the ordinary native path, Lizard plus Brew
fail-closed, Fairy's existing fail-closed boundary, and Mark of the Bloom
existing support. Dispatch metrics were 1 fallback preparation, 6 fast
preparations, 3 Lizard preparations, 2 Lizard samples, 2 Lizard support
failures, and 9 boundary exclusions; repeated calls to support, forecast,
prepare, and the prediction probe contribute to the exclusion/failure counters.

The existing DeepSets/Brew mechanism fixture passed all 31 rows, retaining
13 ordinary DeepSets and 18 standard Attention fallback routes, 26 fast
samples, and 36 fallback samples. Complete RAW/RNG and scalar/prepared
identity held on every row. Its input is
`tests/fixtures/combat_transition_near_full.jsonl` (SHA-256
`d464bcc043bd3f9964a2300696f05356a602eb3fb98f01070800cb025e9226ee`).
Focused CTest selection passed 5/5: near-full sampler self-test, native
fixture, active-Lizard fixture, OOC MCTS adapter, and runtime loader. The
runtime probe SHA-256 is
`1ed808cfa04b9dbdddbae256d410f664b252690613e5d656253c526ee69ec692` and
`one_combat` SHA-256 is
`63975e203b240f987a1b87fac8778fb25f434cfa5e23834bfda1cd5a7e6fc7ee`.
Python syntax checks and `git diff --check` passed.

Files `native_parity.json`, `deepsets_brew_fixture.jsonl`, and
`deepsets_brew_fixture.metrics.json` contain machine-readable outcomes. The
320 paired states, selection, manifest, candidate, and q/r artifact are copied
with their original hashes into this packet. The frozen Python T2 reference
`tools/combat_transition_lizard_minimal.py` is pinned in the parity report at
SHA-256 `2465502731defca4ace9cfcd84eb222a8330b206297f50aaba55e1ad34e584eb`;
the q/r predictor `tools/combat_transition_lizard_mechanical_q.py` is pinned
at `fcee01d2319d40719cddcb6a6c81ff888ea2720b873d7223b7abe0683192bdbf`, and
the source assignment at
`752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a`.

## Gate 2 — forced-Lizard integration canary

**Pending review and source freeze.** The committed `gate2_canary_plan.md` fixes the eight paired seeds,
arms, environment, budgets, and decision rules before collection. The exact
reviewed source SHA, built executable hash, and final frozen per-run manifest
will be written before the first gameplay seed. Results will be appended here
without extending the cohort.

## Gate 3 — default plumbing

**Pending Gate 2.** If Gates 1 and 2 pass, the exact DeepSets payload will be
re-exported as the tracked production default for enabled OOC MCTS, with the
standard Attention Brew fallback. OOC MCTS remains globally off unless the
caller sets `STS_OOC_MCTS=1`. Two no-model-environment plumbing smokes will then
verify the default stack.

## Knowledge impact

Current research and baseline pages will be updated if Gate 3 qualifies the
default. Stable implementation behavior is documented at the sampler and OOC
adapter entry points. The existing PR #330 and PR #351 evidence remains the
scientific qualification; this packet records integration correctness and
plumbing only.
