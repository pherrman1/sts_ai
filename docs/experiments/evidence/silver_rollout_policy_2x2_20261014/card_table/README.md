# Learned rollout card table (offline fit, 2026-10-14)

Research input for `STS_SILVER_ROLLOUT_CARD_TABLE` (off by default). Not evidence for any default.

- Data: gen-6 Silver self-play roots (`/mnt/project-files/silver-az-mlp/gen6/w01.tar`–`w08.tar`, A0, 40k-simulation
  roots). Rows: PLAYER_NORMAL roots with at least two distinct playable (card id, upgraded) card-play edges;
  label = the (card id, upgraded) whose card-play edges have the most visits (summed over targets).
- `extract_card_choices.py` builds the rows (302,528); `fit_card_table.py` fits a conditional-logit score per
  (card id, upgraded) on workers w01–w06 and tests on w07–w08 (split by seed block).
- `card_table_fit.json` is `fit_card_table.py`'s full output (held-out result and every nonzero weight, keyed
  card id * 2 + upgraded). `make_table.py card_table_fit.json card_table_g6.txt` writes the table from it, and the
  regenerated file is byte-identical to the committed one (sha256 `fa93269f…`).
- `card_table_g6.txt`: `<card id> <upgraded> <score>`, higher plays first; unlisted cards score 0. The rollout
  agent ranks by `-score * 1000` truncated to an integer (`SilverRolloutAgent::loadPlayTable`).
- Held-out top-1 agreement with Silver's choice (`fit_result.json`): learned table 45.7%, greedy
  `cardPlayPriorities` order alone 32.3%, uniform over options 31.0% (mean 3.7 options).

Caveats: this compares only the priority-order component. The real greedy policy also plays zero-cost cards
first, skips defensive cards when block suffices, and swaps to AoE; those rules stay in place with the table.
First-card agreement also undervalues orders that reach the same end of turn. The data are A0; the smoke
below is A20.

Smoke (not evidence, 32 full A20 runs, seeds 74071458–74071489, 2,500 simulations, paired with the greedy run
on the same seeds): mean floor 32.3 vs 30.5 (paired +1.8, s.e. 2.5), wins 2 vs 1, CPU per run 8.29 vs 8.25 s.
