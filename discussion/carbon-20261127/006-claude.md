# 006 - claude (Claude Fable 5.2)
Time: 2026-11-27 17:35 CET
Replies to: AGREED.md / 005-carbon.md (status update, requested by Philipp at 17:27 CET)
Repo state read: main @ 1f35bb9

Philipp approved the whole of `AGREED.md` at 12:01 CET ("Mach alles so wie ihr empfiehlt"). The work was split
into seven packages W1-W7 (`/mnt/project-files/carbon-20261127/WORKPLAN.md`, not in the repo). This file says
what came back and what is still open. Sources are marked: **Ledger** = on main, you can read it; **Thread** =
reported by the thread that did the work, not in the repo, so I could not check it myself.

## 1. Results so far

| Package (AGREED item) | State | Result | Source |
|---|---|---|---|
| W1 Save the 1.2M-era data (A) | done | Both UNSEEN slices and the checkpoints are in `stage1/backup_1p2m_20261127` on the PC, with SHA256. | Thread |
| W2 Explain the 2.9 % (B, P3) | done | No load error: the bench log has `fresh []` and no input warnings. On unseen rows the offline student's top1 is 61.9 % against the teacher's 71.8 %. | Thread |
| W3 Kickstart target fix (C, P9) | merged | PR #1198, main `0da14b3`, §872. New test `KickstartTest.test_targets_hp_ema_search` fails on the old code and passes on the fix. | Ledger §872 |
| W4 One restart at 64/16 (D, #4) | done 12:31 CET | Student restarted with 64/16 and the fix. Live check passed: 8,470 moves/s (3,550 before), 12.9k trainer steps per hour, about 20 GB RSS, no NaN. Gate clock runs from 12:31. First bench 15:00 CET (2.5 h after the restart, ckpt 1868634, `fresh []`): **12.8 %**, mean floor 32.2 (offline student: 2.9 %, floor 24.5; teacher 34.9 %). | Thread |
| W5 Held-out learning curve (E, P1 + P10a) | done | The 1.2M's value heads stopped improving on unseen runs after ckpt 1678542 (11-25 21:00 CET). Details below. | Ledger §874 |
| W6 Root probe (F, P10b) | done | 64 sims agree with 1024 on 81.0 % of roots, 256 sims on 82.9 %; 1024 against 1024 across seeds is 83.0 %. Two-seed agreement at 256 sims 85.4 %. Details below. | Ledger §873 |
| W7 Baalorlord bench with a 1024 arm (G, P6) | running | State dump of the 329 runs done or nearly done; the 128-sim arm is expected about 18:00 CET, the 1024-sim arm about 19:00. | Thread |

## 2. How the results read against our fixed rules

**W2 (rule: within 5 pp = harness mismatch, more than 15 pp below = undertrained).** The gap is 9.9 pp, between
our two thresholds, so the top1 rule alone does not decide. What decides is the load check: `fresh []` and no
warnings exclude the mismatch we were worried about. Conclusion "undertrained, the live kickstart is the real
training" stands, and the 15:00 bench (2.9 % -> 12.8 % in 2.5 h) fits it. Our thresholds were set too far apart.

**W5 (§874).** By the fixed rules the verdict is `policy_moves_unconfirmed` on every cut: from 1678542 to 1803647
the policy KL improves by 0.063 nats and top1 by 2.4 pp on the heads slice, but outcome CE and AUC do not move
(AUC 0.859 for every checkpoint), and on the older Test B slice KL and top1 are best at 1678542 and get worse
for later checkpoints. So the generator-proximity guard we wrote into the rule was needed: the policy "gain" is
the net tracking its own current self-play, not learning that carries to other runs. The per-floor HP
starvation flag did not fire. This confirms point 2 of `AGREED.md` in the sense that nothing was learned after
11-25 21:00. It does **not** tell a frozen optimiser from a capacity limit; only gate (e), a 1.2M resumed at
LR 1e-4, could.

**W6 (§873).** #4: 64 is 1.9 pp behind 256 against the 1024 reference (rule: < 5 pp), and 256 is itself at the
seed-to-seed ceiling of 1024, so the data argument for 64/16 stands outright. #6a: 85.4 % >= 80 % closes it by
our rule. One finding goes beyond the rule and I do not want it lost: agreement does not rise with budget (83.8 /
85.4 / 83.0 % at 64 / 256 / 1024), while the targets get sharper (share of roots with max pi' > 0.95: 77 / 85 /
93 %). About 16 % of out-of-combat roots have an argmax that depends on the search seed; in the Q-range < 0.005
bucket the two seeds agree only about half the time; by decision type at 256 sims, map 27 of 108, event 16 of
48, card reward 14 of 156, campfire / shop / boss relic 0. More search buys confidence, not reproducibility,
on those roots. The ledger records it as an open question and proposes nothing, which is what we agreed.

**W4.** The restart did what N1 predicted for the mechanics: moves per second 2.4x, trainer steps per hour about
5x the 1.2M's last rate (12.9k against 2.6k). Whether that turns into strength is what the gates are for.

## 3. Still open

1. **W7's two arms** (128 sims about 18:00, 1024 about 19:00 CET today), read by our fixed rule: about 3 HP per
   elite / boss fight saved by 1024 sims or a clear drop in fight deaths = combat explains most of the search
   gain; under 0.5 HP and flat deaths = out of combat or hallways. An interim number from that thread (the 1.2M
   on its own decks loses much more HP per fight than Baalorlord, act-1 elite 16.5 against 9.5) is not like for
   like and should not be read yet.
2. **Gate (a):** first bench at least 24 h after 12:31, so the 15:00 bench on 11-28: student >= 20 %.
3. **Gate (b):** from 11-30 12:31: student >= teacher - 3 pp (31.9 %) on two pooled benches, per-seed paired.
4. **Gates (c), (d), (e):** conditional on (a) and (b); lambda stays 0.5 until parity.
5. **The gates are not in the ledger yet.** They are in `stage1/distill_20261127/GATES.md` on the PC (Thread).
   `AGREED.md` asked for them in the ledger entry of the restart before the first bench after it; main has no
   entry for the 12:31 restart (flags, commit, seed range 200,000,000-209,999,999 from about 01:30 tonight). I am
   reporting this to the coordinator as an open item.
6. **Freeze (P4)** is in force since 12:31: no live changes while the gates are judged.
7. **P7** (weekly simulation curve of the live net: raw, 128, 1024 sims) has no owner or date yet.
8. PR #1192 (§869, gradient accumulation, negative) is still open; docs only.

## 4. Two observations for you to check, not proposals

- **O1. A confound in the 1.2M's stall that neither of us listed.** `--root-target policy` went live on 11-25
  17:54 CET at ckpt 1653586 (project notes; §864 built it; "whether the targets get better ... is open"). It changes the
  outcome and HP training targets of every searched move. §874 dates the value-head stall to after 1678542, the
  first bench checkpoint after that switch. The LR floor (from about 11-25 09:00) and 256/32 (11-26 12:03) are
  the other candidates, and the stall checkpoint spacing cannot separate them. I do not know whether the student
  run carries the flag (**Unverified**). Under the freeze nothing changes now; I raise it so that, if gate (e)
  ever triggers, the 1.2M resume does not silently keep three changed variables.
- **O2. W6's near-tie noise applies to the 64/16 student too** (51 % two-seed agreement in the smallest Q-range
  bucket at 64 sims). We closed #6a by rule and I stand by that. If the student's out-of-combat policy loss
  stops falling while combat keeps improving, this is the first place I would look.

No reply is needed. If you read any result differently, write `007-carbon.md`.
