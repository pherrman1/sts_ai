# Stage C: §746 model A as Silver's Shield & Spear leaf, through the price table (pre-registration DRAFT)

Status: **DRAFT, not frozen, not run.** Written with the price-table flag (leaf plan stage 0, thread B). Running it
needs Philipp's typed go, a prelaunch review and a frozen RUN_COMMIT / binary / model sha in `campaign.manifest`.
§746's pre-registered decision ("PASS → pre-register stage C: A as Silver's S&S win leaf in §724's S&S → Heart
chain") is what this document carries out.

## Question
§746: model A (all-feature Heart-entry GBM) prices single changes of the Heart-entry state better than Silver's leaf
(paired squared error −0.00180 [−0.00240, −0.00121]). Does Silver play Shield & Spear better for the Heart when its
win leaf uses model A's prices (`STS_SILVER_PRICE_TABLE_LEAF=a746`), i.e. does Heart kill rise?

## Candidate (frozen at freeze time)
- Flag `STS_SILVER_PRICE_TABLE_LEAF=a746` (research, default off): at S&S start the table is built once from model A
  (`models/candidates/silver_price_a746.trees`, vocabulary `.vocab.json`, provenance in
  `silver_price_table_leaf_20261105/README.md`). A won S&S leaf scores winBonus + U(HP) + potion prices + counter
  prices + max-HP / gold prices − turn penalty − Smoke Bomb / Parasite penalties; the loss branch and every other
  fight (the Heart included) keep the default leaf.
- Prices are in units of model A's own 1-HP slope at the S&S start HP (see the README for the scale rule and its
  floor).

## Design (§724's, changed only where stated)
- States: §724's 592 S&S entries holding Incense Burner (`ss_states.tar`, share `incense-term-gate/`), plus S&S
  entries without Incense Burner from the same source campaigns (`extract_ss.py` with the Incense filter removed;
  deduplicated as §724; at most 1,024, drawn with seed 20261105). The second set has to be extracted and counted
  before freezing; its size changes only the cost.
- Play: `one_combat act4replay` with `STS_ACT4REPLAY_CHAIN=heart`, learned budget, Silver as §724 (learned stop
  gbt-0cac7cc64364, ≤ 10k per root, one-action roots unsearched, Act 4 strong off, node reuse cap 262,144, g7f_E root
  table and root/tree prior, boss prior playouts); `run_unit.sh` = §724's with the arm list below.
- Arms (all states): **D** default S&S leaf; **T** `STS_SILVER_PRICE_TABLE_LEAF=a746`.
  Arms (Incense states only): **I** `STS_SILVER_INCENSE_HEART_PHASE=1` (§724's PASS arm); **TI** T and I together
  (the table's own Incense counter prices plus §724's term on top).
- 4 paired replicates; replicate r uses battle seed BLOCK[r] + state, BLOCK = §724's four used blocks (111384000,
  111382000, 111395000, 111398100). States beyond index 591 need the block extents checked against the ledger and
  the seed guard before freezing (only used seeds; otherwise the extra states are dropped). All arms share every
  battle and planner seed.
- Unit = one state (all its arms and replicates); rc and validity as §724 (+ the price-table log line in T/TI, its
  absence in D/I).

## Endpoints and analysis (`analyze.py`, frozen before launch)
Heart kill = S&S won and Heart won, averaged over the 4 replicates per state and arm. CIs: 95% bootstrap over source
seeds (10,000, seed 20261105).
- **Primary:** T − D Heart kill over all states. Sequential gate (ADR-0064, `tools/sprt_gate.py`): gainer variant
  H0 δ = 0 vs H1 δ = +2 pp, α = β = 0.05, per-state differences in ascending unit order, a look every 64 contiguous
  units, hard cap = all states; without a crossing by the cap, the fixed-sample CI decides: lo > 0 PASS,
  hi < 0 HARMFUL, else INCONCLUSIVE.
- **Secondary (Incense states, descriptive unless stated):** T − I and TI − I Heart kill; TI − I is the question
  whether the table adds to §724's term.
- **Co-reported:** Heart kill per arm; S&S death per arm (the table keeps winBonus = 53 while its HP range is up to
  4× the default's, so its price of dying differs from the model's own; README); Heart kill given an S&S win; S&S HP left, potions used and
  turns; counter at the Heart and the aligned-counter share (Incense states); CPU per run and table build time; the
  share of S&S fights whose table fell back to the default leaf (flat HP curve); all endpoints on the first copy of
  each distinct state.
- **Model A vs §723 (descriptive, as §746 asks):** for every Incense state, the table's Incense counter prices
  (HP per counter 0..5 relative to the S&S start counter) next to §723's kill-pp table converted at 1.33 HP/pp; mean
  price per counter, correlation with §723. §732 reported that model A (§731 labels only) missed the Incense
  phase; the refit on §731 + §745 prices it at about 0.6× §723 with counter 1 wrong (README), so T may keep part of
  I's aligned-counter gain.
- **Calibration checks from §746** (co-reported): S&S HP and potion use under T vs D (model A overstates HP and
  potion changes by 1.1-1.7×) and how often T ends S&S with fewer potions at higher HP.

## Decision
- PASS → stage 4's model comparison uses T as the price-table baseline; a whole-run SPRT (Silver 1000) of the table
  at S&S is proposed to Philipp. No default change from stage C.
- INCONCLUSIVE or HARMFUL → report; the table flag stays research-only; stage 2's labels decide the next model.
- In every case TI − I is reported to say whether §724's term should stay on top of a table.

## Optional reference arm (not in the cost below)
A direct-evaluation mode (model A at every won S&S leaf instead of the table) would measure what the table
approximation loses. It is not built: one direct call costs as much as one table row, but it would run at every
won S&S leaf (thousands per decision) instead of 25-40 times per fight. Add it only if T and D differ
and Philipp wants the approximation error measured.

## Cost (estimate; to be replaced by the smoke)
§724: ≈ 53 CPU-s per S&S + Heart run, the term +3%. Table build ≈ 0.6 ms per S&S fight (README), negligible.
- Incense states: 592 × 4 arms × 4 replicates = 9,472 runs ≈ 140 CPU-h.
- Other states (≤ 1,024): ≤ 1,024 × 2 × 4 = 8,192 runs ≈ 120 CPU-h.
- Total ≈ 260 CPU-h (≈ 4 h on 16 workers × 4 lanes), less if the SPRT stops early.

## Caveats
Research Heart search, not production's flat 40k Act-4-strong search (as §724). Model A was fitted on Heart-entry
states of the same source campaigns (§731/§745 bases come from §721's records), so its prices are not out of
sample for these S&S entries. The scale rule (1-HP slope at the start HP with a floor) is a design choice, not tuned.
