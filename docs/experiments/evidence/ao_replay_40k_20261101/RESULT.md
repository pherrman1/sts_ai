# Awakened One replay: result (2026-11-01, §TBD)

Campaign `ao-replay-40k` (README.md prereg, review K PASS), RUN_COMMIT 15737bbe, code 53d591b6, binary dda31542,
16 cloud workers, 17:08-21:43 UTC. `verify_campaign.py`: 304/304 units OK, 0 missing, 0 bad. Output tars on
/mnt/project-files/ao-replay-40k/units. `python3 analyze.py <extracted units>` → `result.json`.

**Primary: NOT_PLANNING_LIMITED.** Per-fight death rate on 304 recorded §727 arm-A Awakened One entries (3 paired
copies per arm): production P 25.0%, flat 40k F 23.8%, **dDeath −1.2 pp [−2.9, +0.3]** (entry bootstrap 4,000).
The CI excludes the −4 pp threshold; it does not exclude a small real gain of up to ~3 pp per fight. Translated to
runs (× 5,543/15,363 AO entries per run × 0.59): ≈ +0.26 pp Heart kills, at most ≈ +0.6 pp at the CI end.

- Identity: 304/304 production replays of the recorded seed reproduce the recorded fight exactly.
- HP lost F − P: −0.7 [−1.9, +0.5] (P 26.6 HP).
- CPU per copy: P 60 s, F 447 s (7.5×).
- Entry-level SD of the paired difference: 0.142.
- Recorded death share of the 304 entries: 24.3% (P replays 25.0%).
- Descriptive (not pre-registered): entries where P died in all 3 copies (50): F still died in 96% of copies (selection
  on P's outcome favours F here, so 4% is an upper bound on rescue). P never died (200): F died in 2%. By entry HP
  fraction the difference is flat (< 40%: −1.4 pp, n 23; 40-70%: −1.3, n 53; ≥ 70%: −1.2, n 228). F lost some fights P
  won (20 entries worse, 29 better).

**Decision (pre-registered):** Awakened One deaths are deck/state problems, not planning; no AO budget follow-up. The
X5 lever moves to deck building (phase 3/5 metric). Consistent with §718 (40k gave no gain on expert boss states).
