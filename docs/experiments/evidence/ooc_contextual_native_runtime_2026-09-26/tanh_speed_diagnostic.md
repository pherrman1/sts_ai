# Tanh GELU speed-only diagnostic

This is the bounded review follow-up to §361. The treatment changed only C1’s activation from exact `std::erf` GELU to the existing V4 tanh-GELU formula. The already-known native/Python fidelity failure means this run is speed-only; no parity claim is made for the treatment.

- Frozen source baseline: `71e9ace30a876a3c0ed12254615eb58814d87d14`.
- Inputs: the pinned 6,317-state canonical trace, the tracked attention artifact, and the previously exported contextual weights. Trace SHA-256: `192b623ca28887e7da646aca16efaecd041583261265e1af23b83a1eab958370`.
- Temporary treatment-header SHA-256: `0d2d01c53d5139075dce6d4f7b591e409a41d542edbee21a14dbb3386da2b8d0`; exact diff is in `tanh_speed_diagnostic.patch`.
- Release flags matched the project probe build (`-O3 -DNDEBUG -std=gnu++20 -fopenmp -flto`); the temporary include trace confirms the treatment header was selected.
- One thread, one warm-up pass per arm, five measured alternating A/B passes, `CLOCK_THREAD_CPUTIME_ID`; 31,585 state calls per arm and operation. Trace decoding and JSON parsing were outside timed regions.

## Results

| Operation | Attention CPU s | Tanh C1 CPU s | B/A | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Deck encoder | 1.302093 | 1.531404 | 1.176110 | -17.611% |
| `prepareState` | 2.677835 | 2.884597 | 1.077212 | -7.721% |
| Complete prior | 4.526272 | 4.760331 | 1.051711 | -5.171% |

The decision-bearing full-prior result is **5.171% slower** (B/A 1.051711), so the predeclared ≥5% improvement gate fails. Deck encoding is 17.611% slower and `prepareState` is 7.721% slower. The deck-count results are in the raw JSON; the 33–64 token bucket has only 25 measured calls.

Decision: stop here. No high-accuracy GELU approximation was implemented or benchmarked, and no 8-seed smoke was run. The permanent C1 runtime, artifact, and tests are removed from the final PR tree; the initial §361 parity and exact-GELU timing evidence remain as historical results. See `tanh_speed_diagnostic.json` and `tanh_speed_diagnostic_compile.log` for raw timing and build provenance.
