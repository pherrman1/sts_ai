# RESULT: STS_SILVER_MAX_BACKUP=4 gate (2026-11-07)

Design: [PREREG.md](PREREG.md). Run commit e58879bb, binary 73a32e99…, seeds 111760000–111762047, arms D (defaults)
and M (D + `STS_SILVER_MAX_BACKUP=4`), `bestbench 1000 1 20`, net-0220 (`408b2982…`).

**Run.** Started 2026-11-06 18:26 CET with 30 workers. Philipp stopped it at 18:33 CET ("postpone this for after the
long c run"). It was relaunched unchanged at 23:57 CET with 14 workers ("verteil die 40 worker fair auf die beiden
aufgaben") and finished 02:36 CET. The design, binary, seeds and queue were unchanged. Tars finished before the stop
were kept, nothing was analysed before the end, and every unit was played, so the stop selects nothing.
`verify_campaign.py`: 2,048 of 2,048 units OK, 3 duplicate tars (first kept), run ['e58879bbce30'].

**Drops.** 3 seeds (≤ 20, so not INCOMPLETE): D-111760602, M-111760272, M-111760572 ended rc 143 (SIGTERM at the
18:33 CET stop, worker w03 uploaded the unit anyway). Combat aborts: 1, D-111760928 (1,000-decision stall cap, floor
41), counted as a loss.
Sensitivity (review J): imputing the missing arm of the 3 dropped seeds as win or loss, in all 8 combinations, leaves
the verdict NOT_SHOWN (H0 at 640, 1,024 or 1,088 pairs).

**Primary (n = 2,045 pairs).** Heart D 21.96%, M 21.66%, d = −0.29 pp [−2.20, +1.61] (95% seed bootstrap).
SPRT gainer (d0 0, d1 +2 pp): accepts H0 at 640 pairs (LLR −2.99) → **NOT_SHOWN**.

**Secondary (not a gate).** Nonregression SPRT (d0 −1.5 pp): CAP (LLR +0.73 at 2,045); bootstrap lo −2.20 < −1.5 →
not NOT_WORSE. Act-3 clears d −0.05 pp [−2.25, +2.15]; final floor d −0.50 [−1.21, +0.21]. cpu_sec/run D 20.8,
M 21.1 (M/D 1.018). Games over 300 s wall: 0 / 0; max wall D 135 s, M 145 s.

**Decision (per PREREG).** NOT_SHOWN and not NOT_WORSE → `STS_SILVER_MAX_BACKUP` stays a research flag, default off.
Its stall effect on the 16 known stall fights (§759) stands, but on normal A20 runs it gives no measurable gain and a
loss of up to ~2 pp is not excluded.

Files: `result.json` (analyze.py output, incl. SPRT looks).
