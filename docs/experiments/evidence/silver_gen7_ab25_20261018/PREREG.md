# Gen-7 Silver prior: held-out Act-4 A/B at 2.5k sims (pre-registered 2026-10-18 ~12:50Z, before any fight)

Follow-up to the 40k A/B (`../silver_gen7_ab_20261018`, NOT_SHOWN: dWin −0.3 pp [−1.6, +1.0], 189/2,188 discordant).
Philipp asked "what happens at lower sims though?" and typed "8 workers on 2.5k sims." (12:38Z). Ledger: part of §517.
Prior evidence: §476 found a prior helps at 2.5k and 625 but not at 10k.

## Design (identical to the 40k A/B except sims, copies and seeds)
- States: the same 1,094 held-out fold-4 Act-4 states (sha 549bd8f5; 586 S&S, 508 Heart, 586 source runs).
- `silverazact4gen`, code 0646798b, binary 09a611b1, flat exact root budgets, reuse cap 32k, tree prior K=8 weight
  400, root bonus off, learned stop off. **2,500 sims, 8 copies per state.** Arm A = g6_E (ca9bd7f2), arm B = g7_E
  (2bb2c98d).
- Seeds: state i uses seed 111177100 + i in both arms (paired); block 111177100-111178193 (author's block, unused
  so far; smoke used 111175701). 8,752 pairs, 17,504 fights, about 10 CPU-h.
- Campaign: `tools/cloud/worker.sh`, 8 workers, 88 units; `units.txt` is arm-major in blocks of 8 so every worker
  runs both arms.

## Outcome and decision rule (fixed now; same as the 40k A/B)
- Primary: paired dWin = mean(won_B − won_A) over all pairs, 95% CI by cluster bootstrap over source runs
  (10,000 resamples, numpy seed 0), `analyze.py` (unchanged copy). **SHOWN** if lower bound > 0; **HARM** if upper
  bound < 0; else **NOT_SHOWN**.
- Secondary (not decisive): dEndHp, per-encounter numbers, discordant counts; descriptive comparison with the 40k run.
- Validity: 88/88 units rc=0 and `verify_campaign.py` OK for all 8 workers; 0 unpaired and 0 invalid pairs expected,
  any nonzero count reported.

## What a result means
SHOWN means g7_E helps on Act-4 fights at a 2.5k budget under the self-play config. It changes no default by itself;
which budget and prior the live or AZ-loop search uses is Philipp's call.
