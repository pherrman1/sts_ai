# Sequential gates and control-arm reuse: validation before adoption (pre-registration)

Date: 2026-11-01. Requested by Philipp (2026-11-01 07:25Z: "führe 1 und 2 als Standard ein. Ersparnis für Rechenzeit
darf auch bei 10% liegen"), ranks 1 and 2 of
[search-and-value-literature.md](../../../knowledge-base/research/search-and-value-literature.md#ranked-ideas).
Written before any replay was computed. Baseline main `e55f482`.

This page fixes two checks. Part A uses only recorded campaigns (no seeds). Part B is a determinism smoke that replays
used seeds and runs only after a prelaunch review.

## Part A: SPRT replay on recorded paired campaigns (zero seeds)

### Rule under test

Paired campaign, per-pair difference `d_i = y_B − y_A` of the campaign's primary binary metric (for §724 the unit is an
S&S state and `d_i` is the mean of its replicate differences). Looks after every 64 pairs (states for §724) in the
pre-registered order: ascending seed (or state index) order, i.e. the order of the campaign's `units.txt`.

Generalised SPRT with the normal approximation used by Fishtest:

- `LLR_n = (δ1 − δ0) / s_n² · (Σ d_i − n (δ0 + δ1) / 2)`, `s_n²` = sample variance of `d_1..d_n` (floor `1e-4`).
- α = β = 0.05: stop and **accept H1** when `LLR_n ≥ log((1−β)/α) = +2.944`, stop and **accept H0** when
  `LLR_n ≤ log(β/(1−α)) = −2.944`.
- No stop before the first look (64). Hard cap = the campaign's recorded size; no crossing by the cap = **cap**.
- Two standard variants:
  - **gainer** (does the change help?): δ0 = 0, δ1 = +2 pp. accept H1 = PASS, accept H0 = NOT_SHOWN.
  - **non-regression** (a guard or a CPU saving): δ0 = −1.5 pp, δ1 = 0. accept H1 = not worse, accept H0 = WORSE.

### Campaigns, contrasts and recorded verdicts (fixed now)

| § | Campaign (evidence dir) | Contrast, metric | Variant | N | Recorded verdict | Class |
|---|---|---|---|---|---|---|
| 661 | `value_level_ab_20261023` | M − A, Heart kill | gainer | 1,024 | IMPROVED +2.15 [+0.10, +4.25] | positive |
| 676 | `ctm_calibration_20261023` | C − A, Heart kill | non-regression | 512 | guard passed (+2.15 [−1.17, +5.66], not WORSE) | not worse |
| 683 | `ooc_map_only_search_20261024` | MAP − OFF, reached Act 4 | gainer | 1,024 | PASS +4.8 [+2.3, +7.3] | positive |
| 691 | `key_rules_ab_20261026` | F − R, Heart kill | gainer | 1,024 | +6.1 [+3.4, +8.6] | positive |
| 693 | `gumbel_qcap_ab_20261026` | B − A, Heart kill | gainer | 512 | NOT_SHOWN −2.5 | null/negative |
| 724 | `incense_term_gate_20261030` | term − base, Heart kill, per S&S state (4 replicates) | gainer | 592 states | PASS +5.9 [+4.1, +7.8] | positive |
| 727 | `value_chooser_ab_20261031` | B − A, Heart kill | gainer | 1,536 | FAIL −15.0 [−17.3, −12.7] | negative |

Extraction: per-seed outcomes come from each campaign's `result.json` `perSeed` where present, else from the unit
tars on the share, using the campaign's own validity rules (complete outcome record, rc 0). The extracted per-arm rates
must reproduce the recorded rates exactly; any mismatch is reported and that campaign is excluded rather than patched.

### Agreement and decision rule

- **Flip:** the SPRT accepts H1 where the recorded class is not positive / not worse, or accepts H0 where it is
  positive / not worse. Stopping at the cap is not a flip (it would have fallen back to the fixed design).
- **Saving:** `1 − n_stop / N` per campaign; the headline is the pair-weighted saving `1 − Σ n_stop / Σ N`
  (pairs have equal cost within a campaign; the weighting by N is a stated simplification).
- **ADOPT** the SPRT as the standard gate if flips ≤ 1 of 7 **and** the saving ≥ 10% (Philipp's threshold; the
  research page's original rule was 25%). Otherwise **DO NOT ADOPT** and report why.
- Secondary (descriptive, not decision-bearing): the same replay over 200 random permutations of each campaign's
  order (numpy seed 20261101), giving the flip rate and the mean saving per campaign; the hard-cap rate.

## Part B: determinism smoke for control-arm reuse (replays of used seeds; runs only after a prelaunch review)

Control-arm reuse means: play the default arm once on a frozen seed bank and compare later candidates against those
stored records. It is valid only if a stored control record is what the same configuration would play today.

- **B1 (same binary):** replay arm A of §727 (`value_chooser_ab_20261031`, RUN_COMMIT/code `8f5b17d6`, binary
  `d39c2b98…` from the share's bin-cache, `run_unit.sh` arm A environment verbatim, no chooser) on its first 32 seeds
  111312000-111312031 (used, replays). Compare with the stored `A-<seed>.jsonl.gz` (`compare.py`): every state,
  decision and outcome row exactly and in order; only the header row (producer SHA, artifact paths and hashes) is
  excluded and reported. (Amended before any run: the stored records were found to carry no wall-clock fields, so
  nothing else is removed.)
- **B2 (current main):** the same 32 seeds and environment with a fresh `e55f482` build (x86-64-v3 preset). Report
  whether main's changes since `8f5b17d6` alter default play (expected only where a play-changing default changed).
- Cost: 64 games ≈ 64 × ~830 s ≈ 15 core-h, run locally in this thread's container (4 lanes), via `tools/seed_guard.sh`.
- **Decision:** B1 byte-identical on 32/32 (outcome + decision rows, timing excluded) → control reuse is adopted with a
  per-campaign sentinel (below). Any B1 mismatch → no reuse until the cause is found and fixed. B2 is descriptive: it
  says whether today's control bank must be re-recorded at main before the first reuse.
- Sentinel for every reusing campaign (the standard): the candidate binary with its flag off replays 32 bank seeds
  first; any non-identical control record stops the campaign before arm B starts and forces a fresh control arm.

## What adoption changes

Docs and a gate tool only (`tools/sprt_gate.py`, the benchmark protocol's gate section, an ADR); no engine code, no
default play changes. Campaign briefs then order units by seed, let the analysis look every 64 completed contiguous
pairs, and stop at a boundary or the cap.
