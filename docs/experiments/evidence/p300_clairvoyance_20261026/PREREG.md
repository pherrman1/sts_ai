# P300 clairvoyance 2x2 (Heart stage values): pre-registration

Frozen 2026-10-26 before any 2x2 fight ran. Philipp authorized the run on 2026-10-26 (23:31 CET, "merge 870. lets do
it on this on 2 workers"), after the cost estimate of about 31 core-h. Design and background:
`/mnt/project-files/p300-clairvoyance/DESIGN.md` (thread "P300 clairvoyance test"), ADR-0062.

## Question

P300 (destire-mio/sts-ironclad-agent, D4 Heart table) values Feel No Pain, Demon Form, Impervious, Corruption and
Barricade at +10 to +14 pp, measured with a known-RNG search at full HP. Our fair Silver measurement at natural HP
(§684) found about 0 for the same cards. Which factor explains the gap: clairvoyance (C), entry HP (H), or neither
(P300's effect does not reproduce on our engine and decks)?

## Design

- **Decks:** deckIndex 0-95 of the stage-value table (`../stage_value_table_20261024/variants.jsonl.gz`, the §684
  Stage A decks), base state = variantIndex 0.
- **Variants (12, fixed, `make_states.py`, `states.jsonl.gz`):** base; add Feel No Pain, Demon Form, Impervious,
  Corruption, Barricade (P300 top 5); add Whirlwind, Rampage, Anger, Immolate, Wild Strike (P300 bottom 5);
  rm:Strike. An add is upgraded when the deck has the matching egg. 20 decks have no Strike, so rm:Strike exists on
  76 decks (1,132 states).
- **Cells:** combat regime x entry HP.
  - `Fnat`, `Ffull`: fair Silver at flat 10,000 sims, arm P of act4_combat_strength_20261024 (identical environment
    to §684 Stage A, `run_unit.sh`).
  - `Knat`, `Kfull`: `STS_ACT4REPLAY_COMBAT=known` (ADR-0062: P300's known-RNG search), 8,000 sims x Boss multiplier 3.
  - `nat` keeps the natural Heart entry HP; `full` sets hp = maxHp.
- **CRN:** 4 copies. Copy r of every variant and every cell of deck d uses battle seed 111304600 + 4d + r
  (seeds 111304600-111304983; the K-full base calibration used the same seeds on a different build, and is not
  part of this analysis). 4,528 fights per cell, 18,112 in all.
- **Frozen code:** `code_commit` 4e3783bf (main with #870 merged), preset linux-gcc-release-x86-64-v3, binary sha256
  in `campaign.manifest`. 2 cloud workers x 4 lanes (Philipp's count), queue schedule.

## Statistics (`analyze.py`)

- Fight score: won = valid and won (an invalid fight counts as a loss and is reported).
- Effect of variant v on deck d in cell c: mean win of v minus mean win of base, over the 4 copies.
- **Primary, per cell: D = mean effect of the top-5 adds minus mean effect of the bottom-5 adds** (decks weighted
  equally). P300 predicts D of about 8-12 pp in its regime.
- Main effects on D: C = mean over HP of D(K) - D(F); H = mean over regimes of D(full) - D(nat); interaction C x H.
- Secondary: base win, mean add effect, every single add (Impervious and Feel No Pain named in advance), rm:Strike.
- 95% CIs: deck bootstrap, 2,000 resamples, seed 20261026.

## Pre-registered readings (point estimates, in pp)

| Rule | Condition | Reading |
|---|---|---|
| R1 | D(Kfull) < 3 and D(Knat) < 3 | P300's effect does not reproduce on our engine and decks (factor S or D). Stop; ledger as a non-replication. |
| R1c | D(Kfull) < 3 and D(Knat) >= 3 | The known-RNG effect exists but the ~86% Kfull base compresses it: read C from the natural-HP cells (D(Knat) - D(Fnat)), not as a non-replication. |
| R2 | D(Kfull) >= 5 and D(Fnat) <= 2 and C >= 4 | Clairvoyance inflates the power/defence card values: P300's Heart table does not transfer to fair play. |
| R3 | H >= 4 and abs(C) < 2 | Entry HP drives it: the values are HP-conditional; a fixed-key table at natural HP stays near 0. |
| R4 | D(Fnat) >= 4 | Stage A was underpowered by its random key sampling: a fixed-key fair table is worth building. |

Any combination that matches none of these is reported as numbers only, without a new conclusion.

**Known caveat, stated before the data:** the K-full base calibration won 85.7% (P300: 68% on its decks; our decks
reach the Heart with more max HP, relics and potions). A base near 86% compresses the room for card gains in
`Kfull`, which biases D(Kfull) toward 0. R1 therefore also needs D(Knat) < 3 (pre-launch review suggestion). `Knat` is the less compressed known-RNG cell; the per-cell
base win is reported next to every D.

## Validity checks

- Every unit ends with rc=0 (`run_unit.sh` checks 4 rows, no ERROR rows, the Silver prior/table load lines for F,
  the `regime` column for every cell). `verify_campaign.py` checks the tars against the frozen identity.
- `analyze.py` asserts every expected csv, the battle seeds, the regime and the variant id of every row.
- `[known-rng]` messages (plan mismatch, replanning limit, turn limit) and invalid-action dumps are counted by the
  verifier from the unit .err files and reported.
