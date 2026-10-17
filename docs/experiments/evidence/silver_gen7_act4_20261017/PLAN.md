# Silver MLP prior gen 7: A20 Act-4 self-play (plan, 2026-10-17)

Philipp 2026-10-17 18:57Z: the gen-6 prior never saw Act-4 combats; 19:01Z "lets do the next prior generation."
Ledger entry: §517 (assigned by the coordinator). Seeds: block 111170100-111179999 (smokes 111170100-113 used;
run 111170200 + state index).

## Why a new generator
All earlier generations came from `silverazgen` full runs at A0 with that mode's own out-of-combat loop, so no
prior saw an A20 fight or an Act-4 fight. Running `silverazgen` at A20 would break Philipp's rule that A20 data
uses student C out of combat. `silverazact4gen` (PR #621) instead replays the Act-4 fight starts of the Act-4 CTM
label collection (RUN_COMMIT bcf14d34, student C out of combat, seeds 111160000-111169999).

## Data
- States: every usable row of the verified label tars (`make_states.py`: runValid, one capture, no quarantine,
  act 4, A20, Shield + Spear or Heart), sorted by (sourceSeed, fightIdx); file `act4-states.jsonl`, its sha256
  frozen in `worker.sh`. Expected ~4,500 states.
- Teacher: 40,000 simulations per root, flat exact budgets, 32k reuse cap, gen-6 MLP g6_E (ca9bd7f2…3228) as tree
  prior at K = 8, weight 400, root bonus off (the gen-6 teacher settings with the current prior). 2 copies per
  state (own game seed and combat streams each).
- Cost (smoke, 40k): ~42 CPU-s and ~45 roots per fight -> ~9,000 fights, ~400k roots, ~105 CPU-h.
- Workers: N from Philipp; units of 25 states, 4 lanes per worker (`worker.sh`).

## Training (after the data is verified)
Window = gen-6 pack (orig + x5 + g3..g6) + the Act-4 roots, folds by `sourceSeed % 5` for Act-4 rows. Recipe = gen-6 E
(distilled 128/64 + encounter/monster embeddings, cosine lr) on Philipp's GPU via a data-only branch.
Offline gate (fixed before any data): gen 7 must not be worse than g6_E on fold-4 orig CE by more than 0.005, and must
improve fold-4 Act-4 CE over g6_E. Online check and default change are Philipp's call.
