# Silver grouped visit-policy online screen: invalid

## Outcome

The reviewed 32-seed A/B screen is **invalid**. Ordinary Silver (`off`) completed all 32 seeds and passed strict provenance and correctness validation. The grouped visit-prior arm completed only seeds `976000..976003`, then aborted during seed `976004` because the selected exact vendor action bits were not live-legal.

The abort is not counted as a loss. No paired estimate, bootstrap interval, CPU ratio, or advance/negative/inconclusive decision was computed.

## Frozen implementation and protocol

- Implementation: `eb4fcc157f542c6d31c81ddd5339aec39fa44600`; base `034830df6510f1ab37ad4f053c07333fca0970c7`.
- Release executable SHA-256: `b306623381227b376aaaa2015aee0ea68d657b5556b2dc95ad22d0601ad438ba`.
- Runtime model SHA-256: `bf16ecf38cd90c1deed494df1c8d16647e61cad7e57a13e7ef44d4bfe205c984`.
- Source NPZ SHA-256: `a9f4ba81b200ec7ac7510970e7279ba7b46b1a0f53af521e5bebb98eba3986cf`.
- Final manifest SHA-256: `b1ee50b9f1b0567c123076e374aeb87f88b762556b86a9877aa3ddf20a6c0f8f`; manifest and exact-SHA preflight passed.
- Seeds `976000..976031`, Ascension 0, project-fair RNG, explicit Act-3 horizon, exact 1,000 root simulations, allocated reuse cap 32768, one thread, arms run separately.
- Linux OOC model hashes: floor `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3`; win `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`.

## Validity sequence

Two A setup attempts were rejected before interpretation. Attempt 1 ran no seed because Windows SCP removed the executable bit. Attempt 2 completed but its sidecar resolved the designated root Git SHA instead of the reviewed worktree SHA. The execute bit and Git context were corrected without changing executable bytes or gameplay settings; attempt 3 used a fresh output namespace and passed strict validation.

Valid A attempt 3 produced 20/32 wins, mean floor 49.4375, median floor 51, mean ending HP 26.34375, mean CPU 2.970066 seconds/run, and 95.0 seconds wall time. These are baseline diagnostics only because B is invalid.

B loaded the grouped model from the explicit runtime path with the expected source NPZ SHA. Its 114 emitted combat telemetry records covered 2,193 scored roots, 13,309 scored actions, 840 fresh-root prior applications, 1,353 reused-root applications, and 41,462 inference microseconds. Every emitted counter was zero before the abort. The terminal exception was:

```text
Silver live backend exact Silver action-bit legality: selected root action bits are not live-legal
```

## Scientific interpretation

There is no gameplay estimate for the grouped prior. This failure does not support or reject the policy hypothesis; it exposes a runtime exact-action legality defect reached during full gameplay. The predeclared screen decision rule requires a valid 32-pair block and therefore was not applied.

Do not rerun seed `976004`, tune the policy, or begin a 128-seed confirmation. A repair would change the frozen executable and must receive independent implementation review before a new scientific run is authorized.

## Post-screen implementation correction

The failure was reproduced as a `SECRET_TECHNIQUE` selection: Silver returned
state-local action bits for canonical draw-pile index 1, while the live pile at
that index was not a legal skill. Commit
`fb6af48b1c8d783abf7a4021a35ab29993b0d963` adds an explicit boundary rule for
draw/discard/exhaust selections: translate the selected card identity from the
canonical isolated pile to the live pile index, then retain strict live legality
validation. All other treatment actions continue to use the exact selected
vendor bits, including duplicate-identity private multi-select confirmations.

The repaired Release executable SHA-256 is
`45305dfc93cf3261ff3d0ccc60ef2c87521a7b02253db93ee923d1938e4439ba`;
the runtime model remains byte-identical at
`bf16ecf38cd90c1deed494df1c8d16647e61cad7e57a13e7ef44d4bfe205c984`.
The focused boundary fixture, 63-root grouped/rank-4 probability parity, both
252-selection replay checks, exact-root-budget canaries for off/grouped/rank4
at seeds 975000 and 975024, default-off selector parity, and the formerly
failing 976004/grouped diagnostic all passed with zero treatment failure
counters. These are implementation checks, not new gameplay evidence.

The invalid screen remains invalid. The repaired executable must receive
independent review before a new, fresh 32-seed block is frozen or launched.
Machine-readable correction evidence is in
`silver_grouped_visit_policy_pile_selection_repair_2026-08-30.json`.

Machine-readable evidence and raw artifact hashes are in `silver_grouped_visit_policy_online_screen_2026-08-30.json`.
