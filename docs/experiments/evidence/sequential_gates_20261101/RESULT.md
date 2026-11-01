# Sequential gates and control-arm reuse: result

Pre-registration: [PREREG.md](PREREG.md) (committed `68112c4` before any replay; Part B wording tightened after the
prelaunch review, `2a29768`, before any game ran).

## Part A: SPRT replay on seven recorded campaigns — ADOPT

`replay.py` re-extracted every campaign's per-seed paired outcomes from its `result.json` or unit tars and replayed
`tools/sprt_gate.py` (GSPRT, α = β = 0.05, looks every 64 pairs in ascending seed / state order, hard cap = the
campaign's size). Every extracted rate reproduces the recorded one. Raw: [partA/replay.json](partA/replay.json),
`partA/pairs_<§>.csv`.

| § | Contrast | Variant | N | A → B | Δ (pp) | Recorded | SPRT | Stopped at | Saving | 200 random orders: saving / flips / caps |
|---|---|---|---|---|---|---|---|---|---|---|
| 661 | M − A, Heart | gainer | 1,024 | 23.24 → 24.61 | +1.37 | IMPROVED | CAP | 1,024 | 0% | 0.3% / 0% / 99.5% |
| 676 | C − A, Heart | non-regression | 512 | 24.02 → 26.17 | +2.15 | not worse | CAP | 512 | 0% | 0% / 0% / 100% |
| 683 | MAP − OFF, Act 4 | gainer | 1,024 | 38.28 → 43.07 | +4.79 | PASS | **PASS** | 640 | 37.5% | 37.0% / 0% / 0% |
| 691 | F − R, Heart | gainer | 1,024 | 20.70 → 26.76 | +6.05 | PASS | **PASS** | 640 | 37.5% | 46.5% / 0% / 0% |
| 693 | B − A, Heart | gainer | 512 | 27.73 → 25.20 | −2.54 | NOT_SHOWN | CAP | 512 | 0% | 0% / 0% / 100% |
| 724 | on − off, Heart (per S&S state) | gainer | 592 | 57.26 → 63.13 | +5.87 | PASS | **PASS** | 192 | 67.6% | 71.3% / 0% / 0% |
| 727 | B − A, Heart | gainer | 1,536 | 25.07 → 10.09 | −14.97 | FAIL | **NOT_SHOWN (H0)** | 256 | 83.3% | 85.4% / 0% / 0% |

- **Flips: 0 of 7** (also 0% over 200 random orders for every campaign). **Pair-weighted saving: 39.3%**
  (3,776 of 6,224 pairs needed). Decision rule (flips ≤ 1 and saving ≥ 10%): **ADOPT**.
- Where the effect is large (|Δ| ≥ 4.8 pp) the SPRT stops at 13-63% of the pairs. Where the effect lies between the
  hypotheses or the campaign is small (§661 +1.4 pp, §676, §693 −2.5 pp at 512 pairs) it runs to the cap and costs the
  same as today, falling back to the fixed-sample reading. So the saving comes from clear results, and it does not
  make small effects cheaper; for those, gate size (X4 in the roadmap) still decides.
- A cap equal to today's fixed size is the conservative choice: the SPRT never costs more than the current design.
  Its error rates at the cap are those of a truncated SPRT (slightly below the nominal power), which is why a cap
  falls back to the fixed-sample CI rather than to an SPRT verdict.
- Unit of §724 is an S&S state (mean of 4 replicate differences); states from one source seed are correlated, which
  the per-state SPRT ignores (the campaign's own CI clustered by seed). It stopped at 192 states, far from the
  boundary's edge (LLR 4.87 vs 2.94).
- Simulated null false-pass rate of the gainer test (self-test, ρ 0.5 pairs, 300 runs): 6.0%.

## Part B: determinism smoke for control-arm reuse

Pending (B1 running locally since 07:44Z).
