# §458 §457 `combo` rerun with the Lizard-capable A20 CTM, 128 paired seeds at ascension 20 (pre-registration, 2026-10-13)

Philipp, 2026-10-13 19:31Z: "Okay add the lizard support then? I want no fallbacks to v4"; 19:58Z he chose "Rerun anyway"
on the card "Use the Lizard A20 CTM for the 128-seed rerun even though its keep rule failed?". Frozen with the run commit
before launch; independent pre-launch review by the coordinator. 16 cloud workers × 8 seeds × 1 arm (Philipp's pick
on the coordinator's worker-count card, 20:08Z).

## Baseline (§457, merged 64aae668)
- Same seeds 87000000–87000127, same binary (code `52e605fd`, Release `one_combat` `fdc44395…`).
- Floors vs `off`: `combo` (A20 escape candidate, no Lizard support) −0.50 [−2.69, +1.65] NOT_SHOWN, with 64.6% of OOC
  decisions decided by the V4 fallback (6,556 `active_unqualified_lizard` and 9 `writhing_ritual_intersection` aborts);
  `combo_def` (default CTM, raw ascension 20) −6.20 [−9.40, −2.90] WORSE (1.9% fallback). Wins 9 / 12 / 7 of 128.

## The change: one arm, `combo_liz`
§457 `combo` unchanged (§433 combo, `STS_OOC_PUBLIC_FUTURES=8`, ascension 20) except the CTM files and
`STS_OOC_MCTS_ACTIVE_LIZARD=1` (`arm_env.sh`). CTM = §443 Step 1b candidate `pathb-a20` with Lizard support
(`/mnt/project-files/ctm-a20/lizard/PREREG-LIZARD.md`, amended sha256 `d2ea9904…`), pinned in `ctm_artifacts.txt`
from `claude/ctm-a20-data` `c507cebb`: fast `FAST4L.native` `ae785ec2…` (Lizard header, A20 r refit, Fairy and Brew,
escape weights byte-identical to §457's, Writhing+Ritual), standard `STD2.native` `e338506d…` (escape + Writhing+Ritual),
manifest `704f2a58…`.
- **Keep rule result (recorded before this run):** criterion 1 PASS (VALIDATION r NLL vs TRAIN base rate: fast 0.300 vs
  0.384, standard 0.244 vs 0.327); criterion 2 FAIL as written (composed survival on Tail-fired VALIDATION rows: fairy
  +0.070 on 44 rows, brew −0.014 on 21 rows, bar 0.01; on all VALIDATION rows of each cohort −0.0003 and −0.0013).
  So the Lizard support is NOT_QUALIFIED; this is a research arm by Philipp's decision, and the §443 re-gate stays blocked.
- **Inference:** the Writhing+Ritual capability has no cohort gate at A20 (too few rows).
- `off` and `combo_def` are not rerun: their §457 rows are reused (same binary and seeds; `combo` too, descriptively).
  `worker.sh setup` builds at `52e605fd` and stops unless the binary hash is `fdc44395…`.

## Smoke (done in the planning thread, `/root/a458-smoke`, same env as `arm_env.sh`)
74047010: won, V4 fallback 4/138 (1 `hp_envelope` support abort; the rest root-boundary decisions, as in other arms).
74047011 (`STS_FORCE_RELIC=LIZARD_TAIL`): floor 33, fallback 2/85, 0 support aborts, 182,336 Lizard samples, 0 Lizard
support failures. Both logs show the candidate banner and `"activeLizardEnabled":true`.

## Analysis (`tools/analyze_ooc_a20_458.py`, RNG seed 458)
- Primary: `combo_liz − off`, mean paired floor difference, paired seed bootstrap 95% CI (10,000 reps). IMPROVED if
  the lower CI > 0, WORSE if the upper CI < 0, NOT_SHOWN otherwise.
- Same statistic, descriptive: `combo_liz − combo_def`, `combo_liz − combo`.
- Key secondary: wins (CI of the difference, discordant pairs, exact McNemar p).
- Descriptive: V4 fallback share and support aborts by arm (expected well under §457's 64.6%), deaths by act, boss
  deaths, CPU per run.
- Validity as §457 (stalls `[bestbench-seed-failure]` dropped from all arms and listed; anything else INVALID); every
  `combo_liz` log must show the candidate banner and `"activeLizardEnabled":true`.
- Decision: no default change either way (ADR-0027; the CTM is NOT_QUALIFIED).

## Seeds
87000000–87000127 (reused paired with §457); smokes 74047010–011 (this thread).
