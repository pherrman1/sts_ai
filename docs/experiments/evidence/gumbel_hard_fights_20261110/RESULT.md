# Gumbel only in hard fights, whole-run gate: result (2026-11-10)

Pre-registration: [PREREG.md](PREREG.md) (frozen in run commit 69cdcd53 before any campaign game). Analysis:
`analyze.py` as frozen, `results/result.json`, claims snapshot `results/claims.txt`.

**Verdict: WORSE.** GHARD (G16 + mb4 in elite and boss rooms, D elsewhere) loses Heart kills against §775's G16 + mb4,
**−3.23 pp [−5.87, −0.59]**, and saves only about 15% of the CPU.

## Data

- Code b1149acd, binary b9b7fc48 (bin cache, preset v3), run commit 69cdcd53. 40 workers, 2026-11-10 18:57-~20:15 CET.
- `verify_campaign.py`: 1,056 of 1,056 units OK, 0 missing, 0 bad, 0 duplicates, one run commit, DONE.json 40/40.
- **Sentinel: 32 of 32 G16 games identical to §775 → REUSE_VALID.** §775's G16 and D games are the controls.
- 1,023 of 1,024 seeds analysed. Dropped: 111378484. Its GHARD game ended before any elite or boss fight, so it had no
  Gumbel root and failed the `whole-run Gumbel roots=[1-9]` log check (rc 85, the path the prelaunch review predicted).
  0 combat aborts, 0 env mismatches.

## Primary: GHARD − G16 (paired, 1,023 seeds)

| | G16 + mb4 (§775) | GHARD | d (95% seed bootstrap) |
|---|---|---|---|
| Heart kills | 41.25% | 38.03% | **−3.23 pp [−5.87, −0.59]** |
| Act 3 cleared (final floor ≥ 52, also counts keyless act-3 clears) | 49.2% | 46.0% | −3.23 pp [−5.87, −0.59] |
| Mean final floor | | | −1.02 [−1.88, −0.13] |

- Discordant seeds: 82 kill only with GHARD, 115 only with G16.
- SPRT nonregression (H0 −1.5 pp, H1 0) reaches CAP (LLR −1.98). The fixed-sample rule then decides: the one-sided 95%
  upper bound is −0.98 pp < 0 → **WORSE**. The gainer SPRT accepts H0 at 640 seeds.

**Cost (co-primary):** CPU per run GHARD / G16 **0.915 [0.870, 0.963]** raw; **0.848** corrected for machine speed by
the sentinel (this campaign's 32 G16 games ran 1.08× slower than §775's on the same seeds). Gumbel simulations per run
0.563 [0.545, 0.583]. That ratio counts only the Gumbel fights; GHARD's D fights are not in it. Gumbel roots 0.539×.
Mean CPU per run: GHARD 469 s, G16 512 s, D 253 s.

## Secondary

- GHARD − D (§775): **+6.35 pp [+3.42, +9.29]** Heart kills at 1.85× D's CPU. Act 3 cleared +4.89 pp.
- So GHARD keeps about two thirds of G16's +9.57 pp (§775) for about 85% of its extra CPU over D.

## Reading

- **Normal fights matter.** §782 showed no resolved change in death rates in normal fights. But G16 also carried
  5.2 HP per run more out of them into the hard fights. Priced at D's −0.24 to −0.51 pp per entry HP at bosses, that is
  1.2-2.7 pp (the prelaunch review's correction of the PREREG's "roughly 1 pp"). The measured −3.2 pp sits at the upper
  end of that range or a little above it. The PREREG's other expectation, a CPU ratio of 0.75-0.8, was also optimistic.
  Hard-fight turns cost more than normal ones, and the review predicted 0.80-0.85 (corrected: 0.85).
- **Cost per point.** G16 buys +9.57 pp for +259 CPU s per run over D (about 0.037 pp per CPU s). GHARD buys +6.35 pp
  for +216 s (about 0.029 pp per CPU s). Taking Gumbel out of normal fights is a worse trade than keeping it everywhere.
- Combined with §783 (learned stop −2.34 pp at about 0.76× CPU) and §781 (8k → 16k), every cut to the G16 budget tried
  so far gives up Heart kills roughly in proportion to the CPU saved, or worse.

## Decision (as pre-registered)

WORSE: GHARD is dropped, and no default changes. G16 + mb4 in every fight stays the teacher configuration. The flags
`STS_SILVER_GUMBEL_ROOT_ROOMS` / `_SIMS` stay as research options (default off).

## Cost

About 137 lane-hours (1,056 units; mean GHARD 469 CPU s, sentinel 448 s). Seeds: §775's 111378256-111379279 reused, no
new seeds; smoke 111379280 (§775 smoke block, used).
