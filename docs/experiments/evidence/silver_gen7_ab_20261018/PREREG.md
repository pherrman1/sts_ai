# Gen-7 Silver prior: held-out Act-4 A/B (pre-registered 2026-10-18 ~10:40Z, before any A/B fight)

Philipp chose the Act-4 replay A/B (card, 10:02Z) and typed "go 8 workers" (10:13Z) in the performance thread.
Ledger: part of §517 (gen-7 prior).

## Question
Does the gen-7 tree prior g7_E (`combat_policy_mlp_g7_E.txt`, sha 2bb2c98d, data branch
`claude/silver-gen7-act4-data` 1d69e625) win more A20 Act-4 fights than g6_E (ca9bd7f2) under the same search?

## Design
- States: the 1,094 lines of the gen-7 states file (c095368c) whose source run has `sourceSeed % 5 == 4`, the
  test fold that gen-7 training never used (586 Shield & Spear, 508 Heart, 438 source runs). `make_fold4.py`
  writes them in file order; sha 549bd8f5.
- Both arms: the gen-7 self-play generator and config unchanged (`silverazact4gen`, code 0646798b, binary
  09a611b1): 40k sims, flat exact root budgets, reuse cap 32k, tree prior K=8 weight 400, root bonus off,
  learned stop off, 2 copies per state. Arm A = g6_E, arm B = g7_E. Nothing else differs.
- Seeds: state i of the file (0-based) uses seed 111176000 + i in both arms, so copy r of a state is the same game
  seed and combat future in A and B (paired). Block 111176000-111177093 (the author's block; smoke used
  111175700). 2,188 pairs, 4,376 fights.
- Campaign: `tools/cloud/worker.sh`, 8 workers, 88 units (arm x 25 states), `units.txt` interleaves arms.

## Outcome and decision rule (fixed now)
- Primary: paired win difference dWin = mean(won_B - won_A) over all valid pairs; 95% CI by cluster bootstrap
  over source runs (10,000 resamples, numpy seed 0), `analyze.py`.
  **SHOWN** if the CI lower bound > 0; **HARM** if the upper bound < 0; else **NOT_SHOWN**.
- Secondary (reported, not decisive): dEndHp (end HP, 0 on a loss) with the same bootstrap; the same numbers per
  encounter; discordant pair counts.
- Validity: every one of the 88 units rc=0 and verified by `verify_campaign.py`; 2,188 pairs with matching
  sourceSeed, encounter and preHp; any unpaired fight or invalid pair is reported. A missing unit means no verdict
  until it is rerun from scratch with the same frozen config.
- Sanity (not decisive): arm A's win rate should be near the gen-7 self-play's win rate on the same 1,094 states
  (same config, other seeds).
- Power (rough): with ~30% discordant pairs the CI half-width is about 2.4 points.

## What a result means
SHOWN supports g7_E as the Silver prior under the self-play search config on Act-4 fights. It does not by itself
change any default: the live config and full-run effects are separate checks, and any default change is
Philipp's call.
