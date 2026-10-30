# Incense Burner phase before the Heart: paired Heart-fight probe (pre-registration)

Status: FROZEN 2026-10-30 before launch. Philipp: "Ja, mach das" (13:02Z, causal test + issue #914), Heart search
settings (14:27Z: "reuse cap höher, learned stop an, bei nur einer Aktion nicht suchen"), "Mach doch einfach 16 workers
auf" (14:45Z). Code, binary and inputs are in `campaign.manifest`.

## Question
Incense Burner gives Intangible every 6 turns and its counter carries across fights. The Heart opens with Debilitate,
then repeats two attacks (Blood Shots 2×15, Echo 45, random order) and a Buff, so Intangible always lands on the same
slot of that cycle. With the counter at 5 or 2 at the Heart's start it only ever covers Debilitate or Buff turns
("wasted"); at 0, 1, 3, 4 it covers an attack ("aligned"). Silver's leaf at the end of Shield & Spear does not see the
counter (§721; issue #914). Observed Heart kill rates by counter at entry: 71/80/71/76/78/52% (n 71-140, not causal).
Does the counter phase change the Heart kill rate causally, and by how much?

## Design
- States: all 630 Heart entries holding Incense Burner (last act-4 MAP state on floor 55 after Shield & Spear) from
  §721's `heart.pkl` (run 1 and the key-rules, expert-anchored, gumbel-qcap and card-rule campaigns; shuffled with seed
  20261030, `tools/to_act4replay.py`; `heart_states.tar`). Deck (one upgrade per "+"), relics with their recorded
  counters (`relicData`), potions, HP, max HP. Card misc and bottled cards are not carried (act4replay; shared by all
  counters).
- Arms: the Incense Burner counter forced to c = 0..5. Unit I plays state I once per c with `one_combat act4replay`,
  battle seed 111384000 + I (inside the used run-1 block 111384000-385023; no new seeds) and the same planner seed for
  every c, so the six fights differ only in the counter.
- Silver: learned stop (gbt-0cac7cc64364, ≤ 10k per root, no boss extension), one-action roots committed without search
  (`STS_ACT4REPLAY_BUDGET=learned`, Philipp 14:27Z), Act 4 strong off, node reuse cap 262,144 (production Heart cap),
  g7f_E root table and root/tree prior, boss prior playouts. Production's Heart (flat 40k) is stronger; the phase
  effect is mechanical and is not expected to depend much on budget (caveat).

## Endpoints and analysis (fixed; `analyze.py`)
A state counts if all six fights are valid. CIs: 95%, bootstrap over source seeds (10,000, seed 20261030).
- **Primary:** mean over states of (mean Heart kill over c ∈ {0, 1, 3, 4}) − (mean over c ∈ {2, 5}).
- **Decision rule** on the primary CI [lo, hi]: lo > 0 → **PHASE_MATTERS**: next is a priced S&S end-state term
  (default off, issue #914) and its whole-run gate (Philipp's call). hi < 0.03 → **NO_USEFUL_EFFECT** (below 3 pp).
  Otherwise **INCONCLUSIVE**.
- **Co-reported:** kill rate by counter and relative to the state mean; "one more S&S turn" table, kill(c + 1 mod 6) −
  kill(c); HP left at a win by counter; turns; CPU.

## Cost
Smokes (`SMOKE.md`): 3-110 CPU-s per Heart fight, mean ≈ 45 s → 3,780 fights ≈ 47 CPU-h, ≈ 45 min on 16 workers × 4
lanes plus the tail (longest unit ≈ 6 × 2 min).
