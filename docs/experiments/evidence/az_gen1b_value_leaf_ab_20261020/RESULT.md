# Gen-1b value head as the rollout3 end value: result (ledger §TBD)

**NOT_SHOWN.** Over 512 paired A20 seeds, the gen-1b value leaf killed the Heart on 123 seeds (24.0%) and X2-B on 107
(20.9%): +3.1 pp [−1.0, +7.2], exact McNemar p 0.16, at 1.07× wall per run. X2-B stays the rollout3 end value.

Pre-registration: [PREREG.md](PREREG.md) (freeze record at the end). Offline numbers: [OFFLINE.md](OFFLINE.md).

## Run
- Authorization: Philipp 2026-10-21 06:49Z "Just update to main, then go 32 workers"; learned OOC stop off (05:22Z);
  the #765 queue worker (09:59Z).
- RUN_COMMIT `7cd3ae69` (main `0ba0e9a9` plus campaign files), binary sha256 `a822b950…`, student_sel `cf6bf7fb…`,
  gen1b `e6aa044c…`. Pre-launch review PASS (twice; the reviewer's build matched the binary). Smoke seed 111144994:
  both arms rc 0.
- 32 workers × 4 lanes, `schedule queue`, 11:37Z–18:31Z. Seeds 111144000–111144511.
- `verify_campaign.py` ([verify.txt](verify.txt)): units OK 512 of 512, BAD 0, worker DONE.json 32/32. 67 units ran
  twice because claims raced on the project share (fixed for later campaigns by #773); duplicates gave identical
  outcomes and the verifier uses the first tar. Tar hashes: [tars.sha256](tars.sha256).
- `python3 analyze.py <verify_campaign --extract dir>` → [result.json](result.json). 1,024 of 1,024 arm runs rc 0, 512
  of 512 seeds valid.

## Result

| | A: X2-B | B: gen 1b value | B − A [95% CI] | discordant B / A | McNemar p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Heart kills | 107 (20.9%) | 123 (24.0%) | +3.1 pp [−1.0, +7.2] | 66 / 50 | 0.16 |
| Reached Act 4 | 209 (40.8%) | 222 (43.4%) | +2.5 pp [−2.3, +7.3] | 85 / 72 | 0.34 |
| Act-1 deaths | 48 (9.4%) | 50 (9.8%) | +0.4 pp [−2.4, +3.2] | 27 / 25 | 0.89 |
| Mean final floor | 43.9 | 44.1 | | | |
| Wall s/run (mean, max) | 1,976, 5,649 | 2,105, 4,669 | B/A 1.07 | | |

The CI is a normal approximation; the verdict uses the exact McNemar p.

Descriptive:
- Searched roots A 33,691 / B 34,072 (full-budget 8,328 / 8,470, none aborted). Search effort on roots a stop can act on:
  2,389 vs 2,382 simulations per root (exact visit lock; learned stop off in both arms).
- The search's pick differed from the prior's argmax at 3,043 of A's searched roots (9.0%) vs 2,302 of B's (6.8%).
- On seeds where both arms ended on the same floor (interim count, 206 of 504), B's wall was 1.06× A's, so most of
  the 1.07× is the value-head evaluation itself, not longer runs.

## Reading (Inference)
- The point estimate favours the value head (+3.1 pp), but the test resolves about ±4 pp and the result is NOT_SHOWN.
- No act-1 penalty: 50 vs 48 act-1 deaths, unlike the §522 P(Heart) leaf (114 vs 69). The offline Act-1 weakness
  (§577) did not show up as deaths.
- B overrode the prior less often. Its Q values are compressed (value mean ≈0.30 vs X2-B ≈0.79), so at the same
  cpuct the prior weighs more; this is part of the intervention, not corrected.
- Absolute rates are not comparable with gen 0 (§569) or the gen-1b prior A/B (§589): engine fixes and the learned
  stop setting differ. Arm A here: 20.9% at 1,976 s/run.
