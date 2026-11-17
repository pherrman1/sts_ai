# Stage 1: from-scratch self-play training of the 0.44M AmberNet (PREREG, 2026-11-17)

**Question (Philipp 2026-11-17 08:46 CET "Lokal, go auf dem 0.44m netz"; 09:27 CET "Starte sobald wir fertig
sind"):** does the Amber-Eye-style loop (https://8e9f.github.io/amber_eye/) learn A20 Ironclad on our engine from
scratch, with no teacher, on the PC (Ryzen 5 7500F, RTX 3060 Ti)?

**Setup.** Code: this PR (apps/az_bench/az_run_driver.*, tools/az_bench/selfplay.py), the native encoders
(AmberEncoder.h, #1077 / #1080), and the stage 0 kernels (§817). Research only: no main-agent defaults change.
Defaults of selfplay.py: 0.44M net (64 x 6), 11 workers x 700 runs in flight, Gumbel 64 / 16 sims per full / fast
move, playout cap randomization 0.25, utility U = F + H (both weights 1), every full move kept as a sample (pending
cap 300k), window 500k samples, replay ratio 2, AdamW lr 1e-3 (500 warm-up steps), batch 1024, weight sync every 50
steps, inference fp16 compiled with --fused-layer. Command: `selfplay.py --compile --fused-layer --seed-base
130200000 --hours 168` (seeds 130200000 onward, one per run; smokes used 130000000-130199999).

**Measured.** Self-play results of the training runs themselves (training search budget): win rate and mean final
floor per 30 s window and per 10k runs, death-floor histogram, losses, positions/s.

**Decision rule (from the 2026-11-16 assessment, set before the run):**
- GO (continue; next: larger net kickstarted from this one) if the self-play win rate is >= 10 % by 1M runs, or if
  the first wins appear by 500k runs and the mean floor is still rising.
- STOP if there is no win by 1M runs and the mean floor gained < 2 floors over the last 500k runs.
- Otherwise INCONCLUSIVE: report and ask Philipp.
Not a gate against the main agent; a whole-run comparison with the G16 agent is a later, separate PREREG.

**Cost.** The PC's GPU, exclusively, until a decision (estimate: 1M runs in ~2-5 days at the smoke's rates).

**Fair play (review of PR #1082, 2026-11-17).** The combat search root and the net input are the player's public view
(`nativeSilverSearchRoot` with a per-run `CombatKnowledgeState`: draw pile as information set, Runic Dome intents
hidden), checked by ctest `az_fair_view`. Any run started before this fix is void and is not resumed. Later
evaluations of stage 1 nets use seeds outside 130000000 + (runs used).

## Continuation 1M-2M with pick-rate exploration (Philipp, 2026-11-17 15:16 CET)

Philipp: "Mach mal nur erzielte Erkundung an, kein save scum. Der Lauf soll quasi weitergehen, also nochmal 1 Mio
spiele aber auf dem endnetz der ersten 1 Mio spiele." The main run is stopped at ~1M runs (final checkpoint) and resumed
from that checkpoint (net, optimizer, counters; seeds continue after the ones used, same --seed-base 130200000) with
`--explore-c 0.05 --pick-target 0.01 --max-runs 2000000`, same out-dir (one metrics curve).

**Pick-rate exploration** (simplified from Amber Eye, whose exact boost rule is not published): an out-of-combat item
(the source token of a CHOOSE_CARD / CHOOSE_OPTION action: card reward, event / Neow option, relic, shop item; hashed
by type and token ids) picked in fewer than 1 % of the continuation's runs is under target. A root offering one gets a
full search (policy target recorded), and with probability min(1, 0.05 * (1 - rate / 0.01)) the most under-target
item is played instead of the search's choice; the training sample keeps the search's improved policy. Pick counts
start at 0 at the resume. Combat, skips and map moves are never forced. Metrics: ooc_roots, explore_roots,
forced_picks.

**Decision rule (continuation):** GO if the self-play win rate reaches 10 % by 2M runs or the first wins appear while
the mean floor still rises; STOP if there is no win by 2M runs and the mean floor gained < 2 floors over runs 1M-2M;
otherwise INCONCLUSIVE. Forced picks cost some self-play strength (Amber Eye: ~3 pp at 0.2 % forced moves), so the
self-play win rate of the continuation is slightly pessimistic.
