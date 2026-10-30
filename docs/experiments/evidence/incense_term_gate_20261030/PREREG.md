# Incense Burner term at Shield & Spear: paired S&S → Heart gate (pre-registration)

Status: FROZEN 2026-10-30 before launch; prelaunch review PASS (ffbb092b). Philipp: "Yes do 16 workers" (19:08Z). Philipp: "Ja mach das" (2026-10-30 17:13Z) to the next step
of §723: a priced S&S end-state term for the Incense counter (default off, issue #914) with its own gate. Code, binary
and inputs are in `campaign.manifest`.

## Question
§723 measured that the Incense Burner counter at the Heart's start changes Heart kill by up to 18 pp. Silver's S&S
leaf does not see it. Does pricing it (`STS_SILVER_INCENSE_HEART_PHASE=1`) make Silver end S&S on a better counter,
and does that raise the Heart kill rate after paying for the stall (HP, potions, S&S death risk)?

## Term (code commit bfd45383)
A won S&S leaf with Incense Burner adds 1.33 × `kIncenseHeartPhaseKillPp[counter]` (HP), the §723 Heart kill minus
the state mean for the counter at the win (−1.75, +1.90, −8.25, +5.71, +10.16, −7.78 pp for 0..5), converted at 0.75 pp
of Heart kill per HP (V_H's slope at 40-70% HP, §721). Range −11.0 to +13.5 HP. Nothing else in the leaf changes.

## Design
- States: all 592 S&S entries holding Incense Burner (last act-4 MAP state on floor 54, before S&S) from Act-4-strong
  games of run 1 and the key-rules, expert-anchored, gumbel-qcap and card-rule campaigns (`tools/extract_ss.py`,
  `tools/to_ss.py`, shuffled with seed 20261031; `ss_states.tar`). Deck (one upgrade per "+"), relics with their
  recorded counters, potions, HP, max HP; card misc and bottled cards are not carried. §723's 630 Heart states include
  games that got Incense Burner from the S&S reward; those are not here. 79 of the 592 states are exact duplicates of
  another (513 distinct, 70 groups, every group within one source seed: run-1 base/fork copies and the same seed in
  run 1 and a later campaign). They stay in the primary (the bootstrap clusters by source seed).
- Each state is played with `one_combat act4replay` and `STS_ACT4REPLAY_CHAIN=heart`: S&S, then on a win the Heart from
  the S&S end state (HP, potions, relic counters; the S&S rewards are skipped, the same in both arms).
- Arms: off (no term) and on (`STS_SILVER_INCENSE_HEART_PHASE=1`), 4 replicates each. Replicate r uses battle seed
  BLOCK[r] + state, BLOCK = 111384000 (§696 expert-anchored), 111382000 (§691 key rules), 111395000 (#852 S&S block),
  111398100 (#852 Heart block): four used blocks, no new seeds. Both arms share every battle and planner seed.
- Silver as in §723: learned stop (gbt-0cac7cc64364, ≤ 10k per root, no boss extension), one-action roots unsearched,
  Act 4 strong off, node reuse cap 262,144, g7f_E root table and root/tree prior, boss prior playouts.

## Endpoints and analysis (fixed; `analyze.py`)
A state counts if its unit ended with rc=0 (`u<I>.done`; the run checks the stop model, reuse cap and the term's
on/off log line) and all 8 runs are valid (S&S valid, and the Heart valid when S&S was won). Unit rc counts are
reported. CIs: 95%, bootstrap over
source seeds (10,000, seed 20261031).
- **Primary:** mean over states of (Heart kill, on) − (Heart kill, off), where Heart kill = S&S won and Heart won,
  averaged over the 4 replicates.
- **Decision rule** on the primary CI [lo, hi]: lo > 0 → **PASS**: the term goes to Philipp as a default candidate
  (a production-budget check under Act 4 strong first is his call). hi < 0 → **HARMFUL**. Otherwise **INCONCLUSIVE**.
- **Co-reported:** Heart kill per arm; S&S death per arm and on − off; Heart kill given an S&S win; share of runs that
  reach the Heart on an aligned counter {0, 1, 3, 4}; counter at the Heart per arm; S&S HP left and turns; on − off
  by the counter at S&S entry; CPU per arm; every endpoint again on the first copy of each of the 513 distinct
  states (descriptive; the decision uses the primary).

## Power and cost
Expected effect a few pp: about a third of off-arm runs reach the Heart on a wasted counter (§723: −8 pp each), minus
the stall's cost. With 4 paired replicates the primary SE is ≈ 1.3-1.9 pp. Smokes (`SMOKE.md`): ≈ 50 CPU-s per
S&S + Heart run → 592 × 8 runs ≈ 66 CPU-h, ≈ 1-1.5 h on 16 workers × 4 lanes.

## Caveats
Not production's flat-40k Act-4-strong search; the price comes from §723, largely the same games
(not out of sample), and the scale 1.33 is not tuned.
