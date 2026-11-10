# Act-4-strong budget curve in whole runs: G1, G2, G4 and G8 with Act 4 strong (pre-registration)

**Authorization.** Philipp, 2026-11-10 00:41 CET: "Ja würde gerne 1-8k mit dem stärkeren act4 laufen lassen danach",
after the budget curve ([../gumbel_2k8k_wholerun_20261109/RESULT.md](../gumbel_2k8k_wholerun_20261109/RESULT.md)) showed
that its G1-G8 played Act 4 at their own budget while §775's G16 + mb4 played it with Act 4 strong. "Danach" = after
node-cap Test 2. 40 workers as in the budget curve (stated to him at 00:42 CET, open to a lower count). J's prelaunch
review runs before the launch.

## Question

How much of the step from G8 (31.6% Heart) to §775's G16 + mb4 (40.4% on the same seeds) is Act 4 strong, and what is
the budget curve from 1,000 to 64,000 simulations when every arm plays Act 4 the same way?

## Design

- Seeds: the budget curve's 512 (§775's 111378256-111378767), no new seeds. One unit per seed holds the four arms, in
  an order rotated by seed (`run_unit.sh`, `units.txt`).
- Arms G1S, G2S, G4S, G8S = the budget curve's G1, G2, G4, G8 with `STS_SILVER_LEARNED_STOP=1` and
  `STS_SILVER_ACT4_STRONG` unset instead of `STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0`. That is §775's
  environment for G16 + mb4 with only the simulation count changed.
- What changes (`NativeSilverBackend.cpp`, `act4Strong`, `wholeRunGumbel`, `flatBudget`): the whole-run Gumbel root
  replaces the learned stop in every fight, so acts 1-3 search exactly as in G1-G8. In Act 4 the Shield and Spear get
  max(10,000, arm budget) simulations with prior playouts, and the Heart gets max(40,000, arm budget) with a
  262,144-node reuse cap; G1-G8 played both at their own budget, the Shield and Spear without prior playouts.
- Comparison arms reused, no reruns: G1 and B1 from the 1k test, G2/G4/G8 from the budget curve (same binary
  b5090b16, same seeds), D, G16, G32, G64 (+ mb4) from §775 (binary 0eabb014; §777's 32/32 sentinel showed b5090b16
  replays §775's G16 games).
- Binary b5090b16 (code 13bb97ec) from the share's binary cache. Timeout 2 h per game.
- Smoke (local, 2026-11-10 00:46-00:54 CET, binary b5090b16, not part of the data), G1S on two of the campaign's seeds:
  - 111378284 (G1 died on floor 50): rc 0 in 12 s; the log equals G1's apart from the combat backend banner and the
    net path (same BEST line, `[heart1_ppo]` line, Gumbel roots and tree reuse lines).
  - 111378275 (G1 lost to the Heart on floor 56): rc 0 in 485 s (G1: 59 s), Heart killed, banner with "Act 4 strong
    (S&S 10k prior playouts, Heart 40k)", Gumbel simulations 4.00 M (G1: 0.89 M).
  - `analyze.py` on these two games with the real comparison units: replay check passes on both, no errors.
- `REF_UNITS_DIR` holds §775's extracted `SEED_low` (D, G16, G32) and `SEED_G64` units of the 512 seeds.

## Primary (analyze.py, frozen with this file)

Five contrasts of the Heart kill rate, paired by seed, seed bootstrap (10,000 resamples, seed 20261109) at 99%
(Bonferroni over five):

- **GkS − Gk** for k = 1, 2, 4, 8: **GkS_BETTER** if the lower end > 0, **GkS_WORSE** if the upper end < 0, else
  **NO_DIFFERENCE_SHOWN**.
- **G16 − G8S** (the 8k → 16k step with Act 4 the same way in both): **G16_BETTER** / **G16_WORSE** /
  **NO_DIFFERENCE_SHOWN**.

No SPRT, every seed runs. A game with rc ≠ 0, a wrong environment or a missing BEST line is a drop; each contrast uses
the seeds where both its games count. More than 10 of this campaign's seeds with a drop: every verdict
**NOT_EVALUABLE**.

## Replay check (pre-registered, part of the reading)

Acts 1-3 should replay G1-G8 exactly. For every seed where both games count: if the Gk game ended before Act 4
(final floor < 52), the GkS game must have the same Heart result, final floor, `[heart1_ppo]` game line, Gumbel roots
line and tree reuse line; if the Gk game reached Act 4, the GkS game must reach it too. **REPLAY_OK** if no seed fails,
else **REPLAY_BROKEN** with the failing tags. With REPLAY_BROKEN the verdicts stand as whole-run contrasts, but the
reading "GkS − Gk is the effect of Act 4 strong alone" is withdrawn.

## Secondary (95%, not gates)

- Curve with Act 4 strong: G2S − G1S, G4S − G2S, G8S − G4S, G16 − G8S, G32 − G16, G64 − G32 (the last two §775's
  games on these 512 seeds).
- GkS − D and GkS − B1.
- Heart per Act-4 arrival of Gk and GkS on the seeds where Gk reached Act 4 (difference with a 95% bootstrap).
- Per arm Heart, Act-4 reach, final floor, CPU per run and per floor, aborts; Gumbel roots and simulations per run.

## Cost

Acts 1-3 cost what G1-G8 cost (18 + 40 + 87 + 166 s per seed); Act 4 adds the Shield and Spear at 10,000 and the Heart
at 40,000 for the 30-43% of runs that reach it. The smoke's Act-4 run added about 430 s at 1,000 simulations (less at
8,000, whose own Act 4 already costs more). Estimate about 100-130 lane-hours, about 1-1.5 h on 40 workers × 4 lanes. Share: one campaign at a time after Test 2's claims cleanup, about 512 × 3 claim files plus 512 tars.

## Decision

No default change. The result splits the budget curve's jump at 16,000 into Act 4 strong and budget, and gives the
curve 1k-64k with Act 4 played the same way. A GkS that matched G16 + mb4 at lower CPU would be a teacher or actor
candidate for a separate test with Philipp's go.
