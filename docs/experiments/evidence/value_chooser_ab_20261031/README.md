# Value chooser A/B: stage-5b act values pick at card rewards, card select and boss relics (pre-registration, 2026-10-31)

Philipp (10-31 10:47Z "Joa mach go, aber nimm auch Karten Belohnungen mit", 10:48Z "Und dann nimm so viele seeds auf
32 workern"), after §725 and the exploratory non-map check (V_A1 beats the policy prior's pairwise concordance with
the rollout labels by +0.11 in act 1, V_A2 by +0.05 in act 2; V trained on those labels, so only a game-level A/B
can show a win).

**Question.** Does letting §725's V_A1/V_A2 choose at non-map decisions in acts 1-2 raise the A20 Heart kill rate?

**Arms** (one unit = one fresh seed, both arms on it; `run_unit.sh`):
- A: today's A20 default, the capture-2 environment verbatim (`../value_clean_labels_capture2_20261030/run_unit.sh`)
  without capture.
- B: A + `STS_OOC_VALUE_CHOOSER=python3 value_chooser_server.py .` (code 8f5b17d6, research, default off): at real
  decisions on REWARDS (card picks only: take a card or skip, when the prior's top is one; keys, relics, potions and
  leaving stay production), BOSS_RELIC_REWARDS and CARD_SELECT
  (upgrade, remove, transform, ...) in acts 1-2, after the fixed rule chain (keys, chest, reward relics, gold,
  potions) and instead of student_sel, the top 3 root candidates by prior each get one sampled successor's public
  record; V_A{act} (stage 5b, §725; V_A1 d7e69feed627, V_A2 e557c80cbfa6, scored on CSR) prices them, the highest is
  played (ties: higher prior). Map (OOC MCTS), events, shops, campfires and act 3 stay production.

**Seeds.** 1,536 fresh seeds 111312000-111313535 (free per the seed ledger; no hit in main's units/ledger/READMEs).
Smoke: 111387991 (free card-rule smoke seed), author only. Power: paired SD ≈ 0.42 per pair → CI ±2.1 pp at 1,536
pairs; a true +3 pp has ≈ 80% power.

**Primary metric.** Heart kill rate B − A over all 1,536 paired seeds, 95% seed-bootstrap CI (10,000 resamples).
- PASS: CI lower bound > 0.  FAIL: CI upper bound < 0.  Otherwise NOT_SHOWN.
- A unit counts only if both arms finished as frozen (rc 0); missing units are reported, not imputed.

**Secondary (descriptive).** Act-4 arrival, Heart reach, act-1/2/3 death rates, mean final floor, decisions changed
by the chooser (B chooses a candidate other than the prior's top; per screen and act), first-divergence screen,
CPU and wall ratio B/A (the matched-CPU rule, B ≤ 1.10 × A, applies before any default change).

**Decision.** PASS → default candidate (Philipp's call; needs a native scorer before production use). FAIL/NOT_SHOWN
→ ledger, no default change.

**Prior evidence against.** §712: a value-head argmax at card rewards lost −17.6 pp Heart kills to student_sel (256
seeds). That head was the old X2-B-style value; V_A1/V_A2 are new act values on clean labels, but the risk is real.

**Smoke** (author, 111387991, local non-v3 build of 8f5b17d6): both arms rc 0; A died act 2 floor 18 (239 s), B died
act 2 floor 33 (460 s); B logged 21 choices (14 card rewards, 4 card select, 1 boss relic in act 1, rest act 2), 9 not
the prior's top. An earlier build (d11fd502) let V decide key/relic/leave rows and once left a relic; fixed in
8f5b17d6 (card picks only on REWARDS).

**Cost.** ≈ 14 s per floor per game → ≈ 25 min per unit (2 games) → ≈ 650 lane-h, ≈ 5-6 h on 32 workers × 4 lanes.
Share ≈ 1-2 GB.

**Analysis.** `analyze.py` (to be committed before any campaign tar is read).
