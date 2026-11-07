# Stage-2 leaf pilot: paired fight-end continuations under net-0420 (pre-registration, 2026-11-07)

Status: **FROZEN for launch** once `campaign.manifest` carries `code_commit` and `binary_sha256` (prelaunch review K).

**Question.** Leaf plan, stage 2. Philipp asked on 2026-11-07 at 08:57 CET: "wir könnten noch die vielen core hours für silver combat leafs machen?". His go came at 09:09 CET: "wir können den pilot einfach ausweiten, sodass 40 worker etwa 5-6h brauchen". He confirmed it at 09:24 CET ("du hast mein go für später"). At 09:26 CET he changed the stop: "kannst du ansttaddessen einfach die worker weiterlaufen lassen undich stoppe iwann den lauf? bzw mit max cap von 12h anstatt 5.5h?". The pilot asks two things:

1. Do paired fight-end continuations to the run end resolve Silver leaf prices per act?
2. What would a label factory that resolves them cost?

Prices here are the Heart-kill change from losing HP, a potion, max HP or gold right after a won fight. Fork, copy and continuation follow `fightendpairgen` (#987, KB `research/fight-end-pairs.md`).

## Setup

**Policy (frozen baseline).** The policy is LONG_C's final net-0420 (§760; sha256 `8c0bd16c…`, share `ppo-long-c/nets/net-0420.bin`). Philipp chose it as the new PPO baseline on 2026-11-07. It plays the whole out-of-combat part:

- `STS_OOC_HEART1_PPO=1`, temperature 0, salt 0, `STS_OOC_MCTS=0`.
- New option `ooc=ppo` (this PR). `finishOocCounterfactual` calls `heart1::ppoStep` before any rule, as the PPO runner's chain does with full coverage and without the key rule. Fallbacks go to the deployed chain. The net's counters restart with each continuation.
- Without `ooc=ppo`, nothing changes: the default path and `ooc=heart1` play as before.

Combat is combat B of LONG_B and LONG_C: flat Silver 1,000 sims per root, learned stop off, Act-4 strong off, the g7f_E root and tree prior, and the default Silver leaf (no price table, no Incense term). The environment is exactly the one in `../ppo_long_b_20261104/eval/run_unit.sh`, which is also the environment of §760's evaluation. Every other default is as on main (engine turn cap 500).

**Engine.** RUN_COMMIT = main 7074a3e5 + this PR (code + campaign); the binary sha256 is in `campaign.manifest`.

**Seeds.** 20,480 new source seeds in 2,560 units of 8 seeds (`units.txt`, one first seed per line):

- 111780000-111788191 (units 1-1,024);
- 111790000-111802287 (units 1,025-2,560).

Smoke seeds are 111789990-111789999. Before freezing, the ledger and the seed notes showed nothing in use above 111769991. The author's smoke played 111789990 (one source seed, `run_unit.sh`) with this code and binary; that seed is not in `units.txt`.

**Generator call.** Each unit runs `one_combat fightendpairgen 8 FIRST 1000 20 OUT n=4,ooc=ppo default`:

- up to 4 fight ends per source run, reservoir-sampled from won NORMAL, ELITE and BOSS fights in acts 1-4;
- copies: base, `hp:-3`, `hp:-8`, `hp:-15`, `pot:*` (one copy per distinct held potion type), `maxhp:-5` and `gold:-50`;
- every copy is played to the run end on the fork's continuation seed (common random numbers).

**Workers.** 40 workers with 4 lanes each, queue schedule (`campaign.manifest`).

**Stop rule.** The run ends at the first of three events:

- all units are done;
- Philipp stops it;
- 12 h have passed since the first worker started (hard cap).

At the stop, every worker gets `worker.sh stop`: no new units start, and running units finish and upload.

- Any started unit that is not uploaded at the stop is re-run before the analysis, if the units missing that way are more than 2% of the started units.
- The analysis then uses every uploaded unit. Units start in queue order, independent of their outcome, so the uploaded units are a seed-exchangeable sample.

**Expected cost.** About 3.7 forks per run and about 6.5 copies per fork. Continuations cost 5-35 s each in the smokes (a continuation that reaches the Heart takes 30-45 s), and a source run costs 20.6 s (§760). That puts one unit at about 50-60 lane-minutes. All 2,560 units would take about 14 h on 160 lanes, so the 12 h cap or Philipp's stop ends the run first, at no more than about 1,900 core-h.

## Analysis (`analyze.py`, pre-registered)

**Rows**

- A unit counts only if `result.txt` shows rc 0 and all 8 source rows are present. A failed unit is dropped whole.
- A fork enters only with a valid base row. A pair (fork, variant) enters only with a valid variant row.

**Pairs.** D = y_variant − y_base, with:

- y = `heartKill`: primary;
- y = `finalFloor`: secondary.

**Per act a (1-4) and variant family v.** The families are `hp:-3`, `hp:-8`, `hp:-15`, `pot` (all `pot:NAME` copies pooled), `maxhp:-5` and `gold:-50`. For each cell the analysis reports:

- the mean effect Δ;
- its 95% CI, from a percentile bootstrap over source seeds (2,000 resamples, seed 20261107);
- the discordance f = P(y_variant ≠ y_base);
- Var(D);
- the pairing efficiency ρ = 1 − Var(D) / (Var(y_variant) + Var(y_base)).

**HP slope β (acts 1-3 pooled).** β is in pp of Heart kill per HP lost: the least-squares line through the origin of −D on h over the three HP families (h = 3, 8, 15), so β = Σ h·(−D) / Σ h². Its CI uses the same bootstrap.

**Projection.** For each act a = 1, 2, 3, take σ²_a = Var(D) of the `hp:-8` pairs in act a. Then:

- n_a = σ²_a · (3 / (8β))² forks;
- N* = Σ_a n_a · c, where c is the pilot's mean number of copies per fork (base included);
- cost* = N* · t, where t is the pilot's mean CPU seconds per continuation, in core-h.

cost* is reported with a bootstrap 95% interval.

## Decision (pre-registered)

**Sign check S.** S passes when none of `hp:-15`, `pot` and `maxhp:-5`, pooled over acts 1-4, has a 95% CI for Δ (Heart kill) entirely above 0.

**Price check P.** P passes when β > 0 and cost* ≤ 20,000 core-h.

**Outcomes**

- **GO** (stage 3 proposed to Philipp, own go) if S and P pass. If the pilot alone already resolves the 8-HP price per act at z ≥ 3, stage 3 is not needed for HP prices, and stage 4 (model fit) is proposed directly on these labels.
- **NO-GO** if S fails. Find the sign error before anything else.
- **NO-GO** if P fails. The fallback is pooled per-act prices tested through the existing leaf weights (`STS_SILVER_POTION_WEIGHTS`, `_GOLD_WEIGHT`, `_MAXHP_WEIGHT`), as a separate proposal.

No default change in any case.

## Descriptive

- Δ by act × room × family, and per potion type.
- Prices in HP units, Δ / β: per potion type, per max-HP point and per gold.
- Heart kill of the source runs (new `heartKill` field of the source row) and of the base copies, compared with §760's 25.49%. A source rate outside 20-31% is flagged as a policy-path deviation.
- The net's fallback share among its decisions; above 1% is flagged.
- CPU per continuation by act; skips by reason.

## Deviations

Deviations are reported in the RESULT.
