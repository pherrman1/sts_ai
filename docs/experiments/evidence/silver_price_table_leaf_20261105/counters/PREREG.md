# Counters-only price table at Shield & Spear (follow-up to stage C, §757) — pre-registration

Status: frozen with this campaign (RUN_COMMIT / binary in `campaign.manifest`). Philipp's go: 2026-11-05 23:25 CET
"ja mach noch den kleinen zwischentest", 23:28 CET "ja 40 worker".

## Question
§757: the full price table (T) recovers most of §724's Incense gain but loses −2.4 pp on S&S states without Incense
Burner, where it prices HP and potions (model A is miscalibrated there, §746). Does a table that prices only the
relic counters, on top of Silver's default victory leaf, keep the Incense gain without the loss, i.e. raise Heart kill
against the default leaf?

## Candidate
`STS_SILVER_PRICE_TABLE_LEAF=a746:counters` (this PR; research, default off): at S&S start the a746 table is built as
in §757; the win leaf is Silver's default victory leaf (winBonus 53, HP, 11 per potion, death saves, gold / max HP,
turn penalty, Smoke Bomb / Parasite) plus Σ the table's counter prices at the end values. Lizard Tail's counter is
left out (the default leaf prices it as a death save). Loss branch, other fights and the Heart unchanged.

## Design
- States, seeds, Silver and play: stage C's, unchanged (1,024 states, `ss_states.tar` `3422ca46…`; 4 replicates,
  battle seed BLOCK[r] + state; §724's research Silver). Only arm C is played.
- Control reuse: stage C's D, T and I runs (RUN_COMMIT 47a5289c, binary `4ace2751…`) are the control. Sentinel: the
  first 32 states of stage C's order replay arm D with this binary (units `<I> S`); every row must equal stage C's
  except the CPU columns, otherwise the control is not reusable and the campaign gives no verdict (rerun D needs a
  new go). The flag-off path is unchanged by this PR (ctest off identity).
- Units: 32 sentinel units, then all 1,024 C units in stage C's seeded order (`units.txt`).

## Analysis (`analyze.py`, frozen before launch)
- **Primary:** C − D Heart kill over all states. Sequential gate (ADR-0064, `tools/sprt_gate.py`): gainer, H1 δ = +2
  pp, α = β = 0.05, look every 64, key = rank among non-dropped states in stage C's order (start 0), cap = all
  non-dropped states; without a crossing the 95% bootstrap CI over source seeds decides (lo > 0 PASS, hi < 0 HARMFUL,
  else INCONCLUSIVE).
- **Drops:** a state counts only if its stage C unit passed stage C's rule and its C unit has rc 0 and 4 valid runs;
  otherwise it is dropped from every comparison and listed.
- **Secondary (descriptive):** C − D and C − T on Incense and other states; C − I on Incense states; aligned counter at
  the Heart; S&S death, HP left, potions used.

## Decision
PASS → report; a counters-only table is the candidate for a whole-run test at S&S (proposed to Philipp); no default
change from this campaign. INCONCLUSIVE / HARMFUL → report; the flag stays research-only.

## Cost
1,024 × 4 + 32 × 4 runs ≈ 4,224 × 43 CPU-s ≈ 50 CPU-h (≈ 20-30 min on 40 workers × 4 lanes). Seeds: none new.
