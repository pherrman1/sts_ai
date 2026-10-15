## §28 Fair-play FULL-RUN validation — the value net TRANSLATES (2026-07-15)
Built fair prior (policygen STS_FAIR=1, 800 runs -> vpolicy_fair.csv 692k rows;
train_policy -> v_policy_fair.json top-1 0.474; truncated -> policy_fair_trees_c.txt 100t).
Then fair-play full-run A/B (128 seeds, 1000 sims, OOC held constant, v_server up):
  A fair rollout baseline           win 18.8  floor 37.3  hp 8.3   (5 cpu/run)
  B +fair prior only                win 16.4  floor 38.4  hp 8.9   (wash/neg)
  C +prior +vnet a0.3               win 24.2  floor 39.5  hp 11.4
  D +prior +vnet a0.5               win 25.0  floor 39.0  hp 12.2
  E +prior +vnet a0.7               win 21.1  floor 38.3  hp 9.3
  F vnet-only a0.3 (NO prior)       win 25.0  floor 40.8  hp 12.4  (BEST, 26 cpu/run)
  G vnet-only a0.5 (NO prior)       win 19.5  floor 38.3  hp 7.6
VERDICT: the isolated +9hp fair value net TRANSLATES to full runs: +6.2pp win /
+3.5 floor / +4 hp over fair baseline. **The PRIOR is dead weight in fair play**
(B wash; F==D at half cost). a0.3 is the sweet spot without the prior (a0.5 overshoots
-> leans too hard on net). Caveat: 128-seed SE ~3.8pp (18.8 vs 25.0 = 1.6sigma);
floor/hp gains consistent across all vnet arms corroborate. Cost: vnet leaf = 26 vs 5
cpu/run (1780-feat XGBoost walk every leaf) -> truncate trees next. Best fair config =
STS_FAIR=1 STS_POLICY=0 STS_VNET=build/v_combat_fair_trees.txt STS_VNET_ALPHA=0.3.
NEXT: 512-seed confirm (baseline vs F); truncate value trees for speed; low-sim arm.

## §28b Value-net truncation — 100 trees, 3.5x faster, gain intact (2026-07-15)
Full fair value net = 1500 trees @ 21.7 cpu/run (fair full-run). Truncated (truncate_trees.py):
  trees   full-run cpu/run    isolated GremlinNob 256s@50sims (fair, a0.3)
  1500    21.7                win 100.0  hp 40.9   (vs rollout-only 96.1 / 35.9)
   400     8.2                --
   200     6.7                win 98.4   hp 39.8
   100     6.2  (3.5x)        win 99.2   hp 40.0   <- PICK
100 trees keeps +3.1pp/+4.1hp of the full net's +3.9pp/+5.0hp at leaf cost 6.2 vs 5.0
rollout (~free). DEPLOY fair vnet = build/v_combat_fair_100.txt. 512-seed confirm now cheap
(~4.5min/arm). Accuracy plateau mirrors the crude-net/policy-net ~100-tree plateau.

## §29 Boss-aware drafting from EXISTING data (no datagen) (2026-07-15)
Autopsy: default-OOC agent 0.6% win vs server-V 25% (40x) => deckbuilding dominates.
Deaths cluster at ACT BOSSES (median death floor 16; 62/159 at A1 boss).
DIAGNOSIS: v_rich HAS bossId + nextFight* features but NEAR-IGNORES them -- boss-family
= 1.38% of gain (bossId 0.51%); it learned generic deck->finalFloor, not deck-vs-THIS-boss.
=> a TARGET problem, not a data problem. No new datagen needed (vrich.csv has bossId + finalFloor).
FIX: train_boss_survival.py -> P(pass next act boss | state), label = finalFloor > bossFloor[act]
(act1=17,act2=34,act3=50) on the SAME rows. val AUC 0.9106. boss-family importance ~2x (2.54%).
Card marginals are boss-appropriate: TOP Panache/DemonForm/Apotheosis/Mayhem/Reaper (scaling),
BOTTOM curses+dead cards. vs v_rich near-boss (Spearman 0.855 = agrees but re-ranks): drafts UP
DemonForm/LimitBreak/FeelNoPain/FireBreathing (sustained scaling), DOWN Immolate/Feed/Bludgeon
(burst-AoE, good vs hordes not a lone boss). = the right scaling-over-burst shift before a boss.
build/v_boss_xgb.json. Rollout-draft prototype (§ prior) HURT (-4.7pp, noisy 2-future/150-sim
estimator < trained V); boss-V marginal is the cheaper inference-free replacement.
NEXT: serve v_boss, use its marginal for near-boss card picks, 512-seed A/B (128 too noisy;
also truncated-100 vnet may cost vs full-1500 on full runs -- confirm on 512).

## §30 Boss-V blend draft A/B + progress tracker (2026-07-15)
Wired v_boss into near-boss drafting: v_server CB op computes v_rich & v_boss card
marginals, z-normalizes each across candidates (floors vs prob scale), blends
(1-w)*zr+w*zb, returns chosen card's v_rich marginal (skip logic unchanged). C++ sends
CB only within STS_BOSS_DRAFT_ROWS(=3) of a boss (STS_BOSS_V=1, STS_BOSS_V_W=w). ~free.
512-seed fair A/B (vnet100 a0.3):
  control (v_rich)   win 17.4  floor 36.8  hp 6.6
  boss-V w=0.3       win 18.4  floor 36.9  hp 7.2   <- best
  boss-V w=0.5       win 18.0  floor 37.0  hp 6.8
  boss-V w=0.7       win 18.0  floor 36.8  hp 7.4
READ: small CONSISTENT positive (all 3 weights > control, +0.6..1.0pp, hp +0.6..0.8) but
within 512-seed noise (SE_diff ~2.4pp; +1.0pp = 0.4sigma). Matches the 0.855 model overlap:
only a few near-boss picks change. w=0.3 best (light touch). Reasonable KEEP at ~free cost,
NOT the big lever. To amplify: widen gate rows, or sharpen boss model (per-boss / condition
on reaching boss). NOTE control 17.4% @512 vs old arm-F 25% @128 = mostly 128-seed NOISE
(truncation confound still unconfirmed; full-1500 @512 arm would isolate it).
Also: BenchProgress live \r status line (n/total, running win%/floor/hp, elapsed+eta, TTY-only
so logs stay clean) now default in bestBench.

## §31 CORRECTION: more combat-net trees = higher full-run win% (2026-07-16)
Direct test (128 seeds, fair, vnet-only a0.3), same seeds, only tree count varies:
  100 trees   win 16.4  floor 35.6  hp 6.6   (6.9 cpu/run)
  200 trees   win 14.8  floor 36.0  hp 6.8   (7.7)     [win% dip = noise]
  400 trees   win 19.5  floor 38.4  hp 9.4   (10.0)
  1500 trees  win 25.0  floor 40.8  hp 12.4  (27.1)
FLOOR + HP are MONOTONIC in tree count (low-variance corroboration): full net is
genuinely better, +8.6pp/+5.2floor/+5.8hp over 100. CORRECTS §28b + the earlier
claim that "25%@128 vs 17%@512 was mostly seed noise" -- it was MOSTLY TRUNCATION.
The isolated GremlinNob test (100~=1500) was MISLEADING: per-fight ~equal, but small
degradation COMPOUNDS over ~30 fights/run. DEPLOY = full 1500-tree v_combat_fair_trees.txt
(accept 4.5x combat cpu for the win%); 400 = fallback middle (+3pp @1.6x). Overnight
datagen should use >=400-tree net for better finalFloor labels (was 100).

## §32 Overnight fresh-data OOC models: NEGATIVE (volume-starved) (2026-07-16)
Ran datagen2 with the FULL 1500-tree fair combat net (best labels) ~10h -> vrich2.csv
393,635 rows / 26,403 runs (vs old vrich 2.9GB ~6x more). Retrained v_rich2 (finalFloor
R^2 0.352) + v_boss2 (AUC 0.827 on ITS OWN noisier val split -- not comparable to old 0.911).
Head-to-head 128-seed fair A/B (full net + boss-V w0.3), only OOC models swapped:
  OLD v_rich/v_boss   win 27.3  floor 40.6  hp 12.0
  NEW v_rich2/v_boss2 win 18.8  floor 38.7  hp 6.7
=> NEW is -8.5pp/-1.9floor/-5.3hp, consistent across metrics = REAL degradation, not noise.
CAUSE: data VOLUME. 394k rows too few vs old 2.9GB -> value model data-starved (rare
cards/decks). Better strong-agent labels did NOT compensate for ~6x less coverage. KEEP the
OLD models deployed. To make fresh-data retrain win: need multiple nights to reach comparable
volume (./datagen2_loop.sh 26000 300000 continues, disjoint seeds), THEN retrain. Uncertain
payoff. Side result: arm A 27.3% reconfirms FULL-net deploy (~25-27% @128). Assets kept:
v_rich2_xgb.json, v_boss2_xgb.json, vrich2.csv (append more nights before using).

## 33. V-informed pathing (deck-strength modulation)  ➖ (small, ~free, default off)
- **What:** the map heuristic (`roomValue`/`chooseMapAction`) is deck-BLIND. The next-fight
  features are a shared encounter QUEUE (route-independent at a decision) so V(state) is ~flat
  across immediate children -> per-child V scoring gives no signal. Instead use V(state) as a
  deck-STRENGTH scalar: server op `VS` returns raw V(state)=predFloor; C++ `vStateRaw` (1 query/
  floor) -> `aggr = clamp((predFloor - bossFloor[act]) / 8, -1, +1)`. aggr>0 (comfortably clearing
  the act) scales elites/fights UP + rest/shop/event DOWN; aggr<0 the reverse. Env STS_VPATH=1,
  gain STS_VPATH_K (default 0.4). Off = byte-identical to the old heuristic.
- **256-seed (1000 sims):** off 51.6% / f46.1 / 23.1hp -> k=0.4 **56.6%** / 26.8hp (+5.0pp) ; k=0.7 50.0% (overshoot).
- **512-seed confirm:** off 51.6 / f45.8 / 23.3 -> k=0.3 **53.7** / 24.5 ; k=0.4 **53.7** / f46.0 / 24.8 ; k=0.5 52.7.
- **Verdict:** ➖ the 256-seed +5pp was mostly NOISE (regressed to +2.1pp @512 = ~1sigma). SMALL
  consistent positive though: all V-arms > baseline, end-HP +1.2..1.5 (most stable), coherent
  dose-response (peak k=0.3-0.4, down by 0.5/0.7). Same class as boss-V blend: marginal ~free
  keeper behind STS_VPATH (DEFAULT OFF), k~0.35. NOT the big lever; needs 1024-seed confirm before
  default-on. Confirms the standing "pathing = small lever" finding (exp 6/6b) — NOT overturned.

## 34. Deck-set NN win-value model (DeepSets card embeddings)  ➖ (ties GBM; data-ceiling)
- **What:** test the thesis that GBM is synergy-blind and a SET NN over card embeddings should
  model card interactions better. train_deckset.py: deck vector = (d-u)@E_base + u@E_up (sum-pool
  == counts@E, no token expansion), + relic/potion/boss embeddings + z-normed scalars -> MLP ->
  sigmoid P(win). Target=won, GroupShuffleSplit(0.15,rs=0) by seed (SAME split as v_win GBM).
  torch 2.5.1+cu121, RTX 3060 Ti, ~2s/epoch, 126k params.
- **Result:** v1 (dropout 0.1, lr 2e-3) overfit hard (peak 0.737@ep4 then collapse). v2 (dropout
  0.3 everywhere incl pooled deck vec, lr 1e-3, wd 2e-4, best-ckpt) converged clean ->
  **val AUC 0.7497 @ep13 == GBM 0.7482 (TIE).** Two independent model classes hit the same ~0.75
  => **Inference:** the tested capacity increase did not beat the GBM on this
  data/label (~57k effective independent runs). This is consistent with a data/label
  bottleneck but does not prove a ceiling. Synergy did not improve absolute P(win) AUC.
- **Ensemble (eval_ensemble.py, streamed val-only, same rows):** GBM 0.7482 / NN 0.7476 / pred-corr
  0.912. Blend w=0.5 **AUC 0.7536 (+0.0054)**, logloss 0.5348->0.5308. Small but REAL orthogonal
  signal (different errors). Deployable via v_server blend (both models Python-side) if wanted.
- **Caveat / real open question:** absolute-P(win) AUC does NOT measure DRAFT MARGINAL quality.
  The NN's synergy payoff (if any) is in V(deck+card)-V(deck) depending on deck composition, which
  a tied absolute AUC can hide. The meaningful test is a full-run A/B serving NN (or blend) card
  MARGINALS vs GBM -- not yet run.
- **OPS NOTE:** loading vrich.csv float32 = ~5.8GB; running >1 loader concurrently thrashed swap and
  OOM-killed the user's IDE. eval_ensemble.py rewritten to stream val-only chunks (<1GB peak);
  train_deckset.py guarded under __main__ so importing DeckSet does NOT re-load the CSV. Keep to ONE
  CSV loader at a time.

### 34b. Deck-set NN card-MARGINAL full-run A/B  ➖ (does NOT beat v_rich drafting)
- **What:** the deciding test the absolute-AUC tie couldn't settle — does the NN's synergy-aware
  card marginal V(deck+card)-V(deck) improve DRAFTING? Served CN op in v_server (pure NN or
  w*NN+(1-w)*v_win), C++ STS_CARD_NN=1 / _W / _SKIP. A/B vs deployed v_rich floor drafting.
- **Skip-sensitive:** NN P(win) marginals are dilution-shifted (adding a card often lowers P(win)),
  so skip@0 skips too much (thin deck, floor 41). Swept skip on 32 seeds: -0.005 gave 62.5% (!!).
- **BUT 128-seed = the 32-seed spike was NOISE.** baseline 47.7%/f46.6/22.8hp ; NN skip=-0.005
  44.5/f39.1 ; NN skip=-0.02 **49.2**/f43.1 ; blend0.5 46.1/f40.3. Best NN arm TIES on win (49.2 vs
  47.7, within 4.4pp SE) but is -3..-7 FLOOR on every arm: same win%, decks lose EARLIER when they
  lose = worse mid-run decks. Also the skip=-0.005 "win" at 32 seeds was itself noise-overfit
  (-0.02 better at 128). +2hp on survivors doesn't compensate.
- **Verdict:** ➖ NN drafting does NOT beat v_rich. Together with the AUC tie (§34) and ensemble
  +0.005, this tested deck-set NN is negative for deckbuilding; the synergy hypothesis did not
  pay off here. **Inference:** data/labels are the more promising next lever, but these runs do not
  prove a fixed 0.75 ceiling. DEPLOY UNCHANGED (default path still
  v_rich; NN only via STS_CARD_NN env). To beat the ceiling: more runs or a better LABEL (bootstrapped
  /TD win value), not a fancier model. v_server now also loads v_deckset.pt (harmless; +~torch mem).

## 35. Dynamic potion-saving policy  ➖ (hurts both regimes; shelved)
- **Motivation:** data probe showed potions ARE used (~5.5/run, ~1% of runs never use one, mean
  potionCount 0.64 of ~3 cap, 46% at zero -> NO hoarding). The combat MCTS is per-fight MYOPIC
  (never sees future fights), so it spends potions on easy fights with no incentive to bank them
  for elites/bosses where we die. Hypothesis: saving potions for hard fights helps.
- **Design:** evaluateEndState already values a KEPT potion at 4 HP-equiv (drinking costs ~4 HP);
  made that DYNAMIC via search::g_potionKeepValue set per-fight by potionKeepValue(gc):
  ELITE/BOSS room -> keep=1 (spend); else if a hard fight (nearest elite/boss) within WINDOW rows ->
  keep = 4 + BONUS*proximity*scarcity where scarcity = 1 - (hardDist * pDrop)/DESIRED and
  pDrop = WhiteBeastStatue?1:potionChance/100 (refill-aware, per user's potion-chance point).
  Env STS_POTION_SAVE=1 (+WINDOW/BONUS/SPEND/DESIRED). Verified correct via trace (hoards keep 7->21
  as hardDist 5->1 in monster fights, keep=1.0 in elites/bosses).
- **Result (128 seeds known-RNG, 1000 sims):** baseline 47.7%/f46.6/22.8hp ; save-default 41.4
  /45.7/20.3 ; bonus25 42.2/44.8/22.9 ; window3 39.1/45.7/19.7 = **-5..-9pp, ALL configs worse.**
- **Result (64 seeds FAIR-PLAY):** baseline 21.9%/f36.8/8.4 ; save-default 18.8/36.9/6.0 ;
  bonus25 18.8/f36.5/**11.2hp** = -3.1pp (~0.6sigma). Strong arm = MORE end-HP, FEWER wins (the same
  healthier-survivors-fewer-wins signature as the NN draft §34b) = shifts HP<->win tradeoff the WRONG way.
- **Verdict:** ➖ hurts win% in BOTH regimes; gradient points toward baseline (no saving) => optimum
  is ~no saving. 4th combat-search bias to fail for the SAME reason (after depth-cap, TT, known-RNG
  learned-leaf): the per-fight search already makes locally-good potion decisions; forcing hoarding
  costs approach-fight HP/wins that banked potions don't repay. Deaths at bosses = a DECK problem,
  not potion-timing. SHELVED (STS_POTION_SAVE default off; g_potionKeepValue defaults 4 = unchanged).

## 36. Fairy in a Bottle bug (found via runtrace)  ✅ (real sim bug, fixed)
- **Tool:** new `runtrace <seed> <sims> <asc>` mode (STS_FAIR for fair-play) prints a per-map-node
  human trace (room, encounter/event, HP/gold, deck delta + full deck, relics, potions), draft
  OPTIONS + v_rich marginals, and can refight a floor N times (STS_REFIGHT_FLOOR/_N) to separate
  luck from a bad fight model. Built to audit decisions vs human game knowledge.
- **Bug:** BattleScumSearcher2::enumeratePotionActions emitted a "use" action for FAIRY_POTION
  (target -1). Fairy is NOT usable/discardable in StS -- it auto-procs on lethal in
  Player::wouldDie (heal 30% maxHp). drinkPotion's Fairy case is assert(false), but libsts.a is
  built NDEBUG so it silently discarded the Fairy and did nothing -> the search could THROW AWAY
  the auto-revive for zero benefit. (SimpleAgent.canDrink and isValidPotionAction already excluded
  Fairy; the MCTS enumerator was the outlier.) Confirmed via refight: Looter fight used the Fairy
  30/30 times.
- **Fix:** `continue` (enumerate no action) for FAIRY_POTION. Verified: same refight now uses it
  0/30. Strictly removes a dominated move (can only help/neutral); deployed (libsts rebuilt).
- **Audit findings (seed 0, fair-play, DEATH F16 Slime Boss):** (1) low-marginal DRAFT takes:
  Rupture taken at v_rich marginal +0.05 (skip bar -0.5) -- the floor-value model doesn't penalize
  deck BLOAT so near-zero filler gets slurped (human skips). (2) Lagavulin -44hp was NOT unlucky:
  refight 30x = 0 deaths, endHP med 32 (our 36 typical) -- deck just pays HP. (3) Slime Boss from
  52/74 = 29/30 DEATHS (~unwinnable): a DECK problem, not just the pre-boss smith-over-heal rest.
  Everything traces to a weak/bloated deck = the known deckbuilding+label ceiling.

## 37. Self-play training loop — Phase 0 (harness)  ✅ (validated end-to-end)
- **Goal (user-directed):** AlphaZero-style self-play to break the deckbuilding data/label ceiling
  WITHOUT hand knowledge (user explicitly refused expert tiers / bloat penalties — model must learn
  it from outcomes). ONE unified fair-play meta model V_win(state)->P(win) drives card/shop/rest
  (all = "which resulting state has higher V"; no separate shop/rest models). Fair-play throughout
  so the fight model is realistic.
- **Built:** `selfplay/loop.sh` (resumable loop) + `selfplay/status.sh` (console dashboard).
  Per iter: fair-play datagen N runs -> retrain V_win on last WINDOW iters -> GATE candidate vs
  current on held-out seeds -> promote iff cand win% >= current -> checkpoint. Resumable via
  selfplay/state.env (Ctrl-C anytime; re-run continues). Atomic promotion; win-count guard (skip
  retrain if <20 wins/one class); gate seeds 0..GATE held-out (self-play seeds >=1e6).
- **Validated (2 iters @1000 sims):** datagen 150 fair runs->2026 rows; train val AUC 0.76; GATE
  correctly REJECTED the under-trained candidate (0.0% vs current 16.7%) -> current kept, no
  regression. Full pipeline + resume + dashboard confirmed working.
- **Bugs fixed:** datagen2 writes no header on a fresh file (seed vrich header first); bestbench
  prints TWO 'BEST' lines (parse 'win%='); single-class train crash (loop-level win guard).
- **NEXT (Phase 1):** wire COMBAT model retraining (v_combat_fair value net + policy prior) into the
  loop; scale to thousands of runs/iter (overnight-scale, fair-play ~6x slower); tune replay WINDOW
  (volume-vs-freshness risk, cf §32). Note: unified-V_win OOC start is ~slightly weaker than deployed
  v_rich floor drafting, so iter-0 under-performs 51.6%; the loop must climb from there.

## 38. Self-play loop — Phase 1 (combat retraining wired)  ✅ (validated end-to-end)
- **What:** extended the Phase-0 loop to retrain the FULL agent, not just meta V_win. Now each iter
  retrains 3 heads and gates the whole stack all-or-nothing: meta V_win + combat VALUE NET
  (combatgen->train_value_combat->export_combat_model) + POLICY PRIOR (policygen->train_policy).
  Self-play datagen + gate use the current stack (STS_VNET=current value trees + STS_POLICY=current
  prior, cenv() helper). COMBAT=1 default (0 = meta-only Phase-0), POLICY_RETRAIN, VNET_TREES, POLICY_SIMS.
- **Fixes:** datagen2/combatgen/policygen wrote a header only `if(!append)` and self-play seeds>=1e6
  -> always "append" -> no header -> train KeyError. Now write header when file empty (f.tellp()==0),
  backward-compatible. train_winrate now saves the model BEFORE computing AUC so a single-class val
  split (common in early self-play) can't crash away the trained model.
- **Validated (1 iter @300 sims, 60 runs):** 3 datagen passes (meta 882 / combat 14868 / policy 59888
  rows, all headered); value net retrained R^2 0.827 -> exported & LOADS (200t, "[V_combat leaf value
  ON ...]"); policy retrained -> LOADS (576t, "[policy PUCT ON ...]"); gate measured full candidate
  stack (cand 0% vs curr 6.2% -> correctly NOT promoted at tiny scale). Atomic all-or-nothing promote.
- **Cost note:** datagen now = 3 full-run passes AND uses the value-net leaf (~5x combat cost) -> much
  slower/iter; overnight-scale with thousands of runs. Loop is resumable + trackable as before.
- **NEXT:** kick a real run at scale (RUNS_PER_ITER in the thousands); consider per-head gating if
  all-or-nothing stalls; tune replay WINDOW (volume-vs-freshness, cf §32).

## 39. Self-play loop — combined datagen + per-side gating  ✅
- **Combined datagen (fightgen):** new C++ mode `fightgen nSeeds sims asc eps valOut polOut seedOff`
  installs BOTH hooks (g_onCombatDecision value snapshots + g_onSearchComplete visit-π) in ONE play
  pass -> emits the value (endHp) AND policy CSVs perfectly aligned. Self-play datagen is now 2
  full-run passes (meta + fightgen) instead of 3 -> ~2x combat cost, not 3x.
- **Per-side gating (user's "bail-out"):** meta and combat sides A/B'd INDEPENDENTLY against the same
  baseline, each holding the OTHER side at current: promote meta iff (cand_vwin + cur_combat) >=
  current; promote combat iff (cur_vwin + cand_combat) >= current. A stuck side never blocks the
  other. History now: base / meta / combat win% + per-side promote flags.
- **Validated (1 iter @300 sims):** fightgen -> combat 14868 + policy 63723 rows; value net R^2 0.829,
  policy trained, both load; gate: base 6.2%, meta cand 0.0% (rejected), combat cand 6.2% (PROMOTED
  independently) — the meta side stuck while combat advanced, exactly the intended decoupling.

## 40. Boss-relic + Neow picks via V_win  ➖ (wired; not a standalone win at current model)
- **What:** the default heuristic used to own boss-relic + Neow picks (never model-driven -> a gap for
  self-play, since the model can't learn nodes the heuristic controls). Wired both through V_win:
  server "VW" op = raw V_win(state); bossRelicVPolicy/neowVPolicy COPY the gc, apply each option
  (real transition, RNG untouched on the real gc), evaluate V_win, argmax. Env STS_BOSS_RELIC / STS_NEOW_V.
- **A/B (128 fair seeds, 1000 sims, SE ~3.5pp):** baseline 18.8% ; +boss-relic 18.0 ; +Neow 17.2 ;
  +both 21.1/+1.6hp. ALL within noise -> NOT measurably important at current model quality: the default
  boss-relic priority table + default Neow are already competitive, and v_win isn't strong enough to beat
  them. KEEP wired (model must own these for self-play; they improve as v_win improves) but not a standalone win.
- **FEATURE GAP flagged for the datarun:** model sees PARTIAL path info only -- past = pv* room-type
  counts; future = bossId + nextEliteId + nextFight0/1/2 + remElites/remFights. MISSING the full remaining
  MAP TREE (layout ahead, branch options, rows-to-next-elite/rest/shop/boss, remaining reachable room
  counts). The map is deterministic/KNOWN = free info. Add forward-map features (distances + remaining
  reachable counts, maybe flattened 15x7 grid). The map is the ONE spatial/graph structure in StS -> the
  only place a conv/graph encoding fits.

## 41. Forward-map features + model-driven pathing/events  ✅ (features) / ➖ (path needs retrain)
- **Forward-map features (the datarun enabler):** appended 10 cols to richRow/richHeader + server RAW
  (fmDElite/Rest/Shop/Boss = rows-to-next; fmCElite/Rest/Shop/Event/Monster/Treasure = reachable-ahead
  counts). ONE map-reachability sweep (forwardMapFeatures). Appended LAST so existing models are
  unaffected: backward-compat VERIFIED (64-seed fair 23.4% == pre-fm baseline; server loads old models
  fine on the wider 1015-col vector). Map is deterministic/known -> free info the value model lacked
  (previously only pv* history + next-few-fights). Flows into datagen automatically; value model learns
  it on retrain.
- **Model-driven decisions wired (STS_PATH_V / STS_EVENT_V; boss-relic/Neow §40):** so the model owns
  every node (needed for self-play). A/B 64 fair seeds vs current fm-BLIND v_win:
  - model EVENTS = exact wash (23.4 vs 23.4) -> safe, upside once model improves.
  - model PATHING = CATASTROPHIC 6.2% (-17pp) -> pathVPolicy leans on fm features the current model
    ignores -> degenerates to leftmost-child. MUST stay OFF until v_win is retrained on fm data.
- **CONFIG for self-play:** fm features ON (automatic), pathing HEURISTIC + events default (clean iter-0
  data), flip on STS_PATH_V/STS_EVENT_V LATER once retrained v_win uses fm (gate to confirm). Never ship
  STS_PATH_V with an fm-blind model.

## 42. Full map graph capture (seed-determinism, zero bloat)  ✅
- **Insight:** the StS map is DETERMINISTIC from seed+act (both already stored per row), so the full
  node+edge graph need NOT be flattened into every decision-row (that'd repeat the same ~100-400 map
  cols ~30x/run = huge redundant bloat). Instead record POSITION and regenerate the graph on demand.
- **Added:** curMapX,curMapY to richRow/richHeader/server RAW (now 1017 state cols); `dumpmap <seed>
  <asc>` mode dumps the map graph (per node: y x room edges...). Future GNN pipeline: read
  (seed,act,curMapX,curMapY) from a row -> dumpmap -> build node+edge graph. Zero per-row bloat.
- **No trainer changes needed:** no bloaty grid added; the 10 fm aggregates + 2 position cols are all
  tree-friendly (position ~ progress). Full graph lives only in dumpmap, out of the training CSV.
- **Backward-compat VERIFIED again** on the wider 1017-col vector: 64-seed fair 23.4% (== baseline),
  old models load + serve, 0 server errors.

## 43. Native C++ V_win (kill the v_server socket for OOC)  ✅ (core done, validated)
- **What:** ported V_win to a native XGBoost tree-walk so OOC decisions skip the Python socket.
  export_win_model.py -> build/v_win_trees.txt (feats + logistic + base_score + trees). C++ WinNet
  (app-level, in one_combat.cpp): load maps model feats -> rich raw indices via richIdxMap() (from
  richHeader), predict = tree-walk + baseMargin=logit(base_score) + sigmoid. Feature vector =
  richFeatureVec(gc) (parse of vFeatCsv). Env STS_WIN_NET=1 (or path).
- **VALIDATED exact:** winnettest mode -> native vs server VW over 434 samples/5 seeds:
  max|native-server| = 1e-6. Full-run A/B (STS_CARD_WIN+BOSS_RELIC+NEOW): server 18.8%/f33.5/10.4 ==
  native (STS_WIN_NET) 18.8%/f33.5/10.4 -> BYTE-IDENTICAL decisions.
- **Native now:** card pick (nativeWinCardPick, mirrors decide_win: base + per-card d{cid}/deckSize
  delta), boss-relic, Neow, path (all via vStateWin). STILL socket: rest (HW/UW), shop (SW), v_rich
  card path, CB/CN blends -> full elimination needs porting those (mechanical, same predict+delta).
- **ROI (as flagged):** small datagen speedup (6.40 vs 6.56 cpu/run) -- combat DOMINATES (~6s/run),
  OOC socket is <1% -- so this is mainly an architecture cleanup + makes model-driven pathing cheap
  (100s of native per-candidate calls/run vs unbatched socket round-trips). Bigger datagen levers stay:
  modest self-play sims + truncated value net.

## 44. Adaptive paired self-play gate + live telemetry  ✅ (mechanics validated)
- **Why:** a fixed 500-seed gate is statistically defensible at ~5-8% win, but it always pays for
  baseline + meta + combat (up to 1,500 full runs), even when a candidate is clearly better/worse.
- **Gate:** evaluate common held-out seeds in 100-seed batches up to 500. For each candidate, compute
  the per-seed paired delta of `avg_floor + 0.1*win%`; promote only when the conservative lower
  confidence bound (default Z=2.58) exceeds the 0.5-floor margin, reject when the upper bound cannot
  clear it, and extend only inconclusive candidates. An inconclusive result at 500 is rejected.
- **Telemetry:** `bestbench` optionally appends flushed `seed,won,floor,hpEnd,sec` rows. The watcher
  now shows live step-3 arm/progress, win%, avg floor, paired delta/CI, datagen avg floor, and floor
  metrics in history. Mechanics validated by compiling, a nonzero-offset two-seed CSV smoke run,
  synthetic promote/reject cases, and a mocked live dashboard. Full selection behavior remains to be
  observed over subsequent real iterations.

## 45. CPU scaling: OpenMP run-per-thread vs. process-per-run  ✅
- **Setup:** Ryzen 5 7500F (6 physical cores / 12 SMT threads), 12 identical full `datagen2` seeds,
  600 simulations, current self-play stack and shared V_win server. The live iteration-4 datagen
  worker was SIGSTOP'd for the controlled test and resumed afterward without losing CSV progress.
- **Wall time / speedup:** 1 thread 91.89s / 1.00x; 2 threads 49.38s / 1.86x; 4 threads 27.20s /
  3.38x; 6 threads 21.28s / 4.32x; 8 threads 17.89s / 5.14x; 12 threads 17.06s / 5.39x.
  All variants completed all 12 distinct seeds without errors.
- **Multiple processes lose:** twelve concurrent one-thread processes took 19.31s / 4.76x, 13.2%
  slower than one 12-thread OpenMP process. The executable already assigns one independent STS run
  per OpenMP thread with dynamic scheduling, so process-per-run adds model/process overhead without
  exposing more parallelism.
- **Operational conclusion:** keep one `one_combat.elf` process and set `OMP_NUM_THREADS` to the
  available vCPUs. On this SMT desktop, 8 workers are the efficiency knee; 8 -> 12 adds only 4.9%
  throughput. Cloud scaling must be measured separately past one socket / NUMA domain, but sharding
  into multiple processes is not warranted by this benchmark.

## 46. Replay-window repair + deterministic baseline cache  ✅ (live gate validated)
- **Diagnosis:** after 2,000-run iterations were reduced to 500, the shared 5-iteration replay
  window eventually fell from 4,997/3,497 V_win trajectories (val AUC 0.722/0.765) to 2,002
  trajectories (AUC 0.631). Policy was not starved: each 500-run iteration still produced about
  0.5M edge rows / 100k decisions with stable 0.52-0.54 top-1 agreement. Combat candidates gained
  roughly 1-2 average floors but repeatedly exhausted the strict 500-seed gate inconclusively.
- **Changed:** separate `META_WINDOW=10`; retain combat `WINDOW=5` and memory-safe
  `POLICY_WINDOW=1`; adaptive `GATE_SEEDS=1000` (100-seed looks). Iteration 7 V_win then trained on
  6,497 trajectories and recovered to val AUC 0.7554.
- **Baseline cache:** deterministic held-out baseline rows are cached by SHA-256 over the executable,
  deployed V_win/value/policy models, policy mode, sims, ascension, value blend, and behavior-affecting
  `STS_*` environment. A promotion/model/binary/config change therefore invalidates automatically.
  Seeded from the verified iteration-6 0..499 baseline; iteration 7 live gate confirmed cache hits at
  100, 200, and 300 seeds instead of replaying them.
- **Failure safety:** gaming consumed GPU VRAM and all iteration-7 CUDA trainers failed. The old loop
  incorrectly checkpointed a no-model/no-gate `NA` row. That row/state advance was reverted; trainers
  now mark errors and retry without checkpointing. Local continuation uses `STS_XGB_DEVICE=cpu` while
  gaming. CPU rerun successfully trained V_win, combat value, and the 800-tree policy candidate.
- **Dashboard load:** three simultaneous watchers were each rescanning a completed ~400MB combat CSV
  every two seconds. `status.sh` now trusts the authoritative `.done` marker for completed combat
  progress, removing that repeated CPU/disk load.

## 47. One-run CPU profile: combat value inference dominates  ✅
- **Setup:** representative cached seed 2 (floor 40), fair-play current stack, 600 sims, one OpenMP
  worker pinned to CPU 0. The active datagen worker was paused and automatically resumed. A temporary
  optimized `-pg` binary used the same simulator library/models; `strace -f -c` and `/usr/bin/time -v`
  captured OS behavior. Profiled wall/user time was 14.26/13.95s, CPU utilization 97%, RSS 11.5MB.
- **Flat profile:** `CombatValueNet::predictVec` consumed **75.33% / 10.41 CPU-seconds**.
  Next largest self-time was simulator action execution 2.24%, card usability 1.30%, action
  enumeration 1.23%, action-queue insertion 1.09%, search step 0.87%, and combat feature extraction
  0.80%. Random rollout itself was only 0.51%. Total traced syscall time was 0.021s; 45 socket
  request/response pairs and file I/O were negligible, so this is compute-bound native inference.
- **Same-seed production timing split:** both value+policy 15.23s; value-only 13.44s; policy-only
  4.56s; neither 3.31s. Disabling models changes search decisions, so attribution is directional, but
  it consistently puts the 1,500-tree combat value ensemble at roughly 10-11s (~70% of wall), the
  100-tree policy at roughly 1.3-1.8s (~10%), and base simulator/MCTS at ~3.3s (~22%).
- **Why:** current value model = 1,500 trees / 311,006 nodes / 4.35MB; policy = 100 trees / 11,078
  nodes / 160KB. Each MCTS leaf walks all value trees through branch-heavy, dependent node loads.
- **Optimization priority:** first gate a 300-400-tree or shallower/distilled value model; a roughly
  linear inference reduction has far more upside than simulator micro-optimization. Then flatten the
  tree-of-vectors representation and resolve model feature indices to canonical indices at load time
  (removes one dependent lookup per split). Policy and feature extraction are secondary. Preserve
  held-out strength: this profile justifies what to optimize, not promoting a faster weaker model.

## 48. Combat-value tree-count latency sweep  ✅ (speed only; not promoted)
- **Setup:** truncated the deployed 1,500-tree value ensemble after its first 800, 400, and 200
  trees, preserving feature metadata and base score. Kept the deployed 100-tree policy fixed. Timed
  the same representative seed 2, fair-play stack, 600 sims, one worker pinned to CPU 0. The live
  iteration-9 gate worker was paused for isolation and automatically resumed afterward.
- **Results:** 1,500 trees / 311,006 nodes = **11.21s** (floor 40); 800 / 180,344 = **7.50s**
  (floor 40); 400 / 105,196 = **5.08s** (floor 40); 200 / 63,722 = **4.98s** (floor 44).
  Thus 400 trees was **2.21x faster** than the deployed model on this run and retained its observed
  floor, while 200 trees provided essentially no additional wall-time reduction because its changed
  decisions produced a longer run.
- **Conclusion:** 400 trees is the practical latency candidate: it removes 55% versus 800 trees and
  55% versus the 1,500-tree wall time without chasing the route-dependent 200-tree floor. This is a
  one-seed timing result, not sufficient quality evidence. Do not replace the deployed baseline
  mid-gate; evaluate a 400-tree value candidate with the same 100-tree policy on held-out paired
  seeds before promotion.
- **Actual iteration-9 candidate check:** its independently trained 400-tree value (117,888 nodes)
  took **6.05s** with the current 100-tree policy (floor 45), still **1.85x faster** than the 1,500-tree
  baseline. But the gate couples it to a new 800-tree policy (69,392 nodes), making that complete
  candidate take **12.47s** (floor 44), slightly slower than the deployed stack on this seed. Any
  speed-oriented promotion therefore needs to keep/cap the policy near 100 trees or gate value and
  policy changes separately.

## 49. Self-play meta-gate collapse was a serialization/fallback bug  ✅ fixed
- **Symptom:** iterations 7-9 produced identical held-out meta outcomes on every seed: 0% wins and
  average floor 12.9, despite different V_win models and improving validation AUC (up to 0.7908).
- **Root cause:** `loop.sh` trained to a filename ending in `.json.tmp`. XGBoost therefore selected
  binary UBJSON serialization, after which the file was renamed to `.json`. `v_server.py` failed to
  parse it as JSON but treated V_win as optional and continued. Unified card drafting then received
  its no-model fallback (`skip`, marginal -999) for every reward. The repeated meta results measure
  that deterministic fallback, not candidate quality or model variance.
- **Fix:** training temporaries now end in `.tmp.json`; self-play starts the server with
  `VWIN_REQUIRED=1`, making missing, malformed, or feature-incompatible requested models fatal. The
  existing iteration-9 candidate was losslessly loaded as UBJSON and re-saved as real JSON; its 197
  trees and 458 feature names were verified after conversion. Shell/Python syntax checks pass.
- **Evidence impact:** all prior unified-meta gates using these mislabeled candidates are invalid.
  Keep the deployed meta model unchanged and rerun the iteration-9 100-seed meta gate before making
  any claim about V_win variance or unified card/shop policy quality.
- **Corrected 100-seed gate:** with the converted model genuinely loaded, candidate performance rose
  from the invalid 0% / floor 12.9 to **5.0% / floor 29.13**. The paired deployed baseline was
  **29.0% / floor 38.78**; blended-score delta **-12.05**, SE 1.785, 99% CI
  **[-16.656, -7.444]**, therefore reject. The serialization bug explained most of the catastrophic
  result, but the unified V_win card+shop policy remains a clear systematic regression at this
  iteration. Do not restart full self-play with unified meta enabled; isolate card, shop, and rest
  arms before changing the objective/data or attributing the gap to estimator variance.

## 50. Corrected V_win decision-family ablation + independent self-play gates  ✅
- **Setup:** corrected iteration-9 V_win candidate, deployed combat stack, 600 sims, 100 common
  held-out seeds, eight workers. A no-win-decision control disabled win-based card/shop/rest. Each
  candidate arm enabled exactly one decision family; paired score was `floor + 10*won`, with the
  standard 99% interval and +0.5 promotion margin. All four arms ran serially.
- **Rest only:** 25% / floor 38.19. Versus deployed current-rest baseline (29% / 38.78), delta
  **-0.99**, CI **[-4.959, 2.979]**; versus no-rest control (20% / 38.77), delta **-0.08**, CI
  **[-4.264, 4.104]**. Inconclusive/wash: candidate rest is neither promotable nor clearly harmful.
- **Card only:** 17% / floor 31.26 versus control 20% / 38.77; delta **-7.81**, CI
  **[-12.629, -2.991]**: clear reject.
- **Shop only:** 10% / floor 35.19 versus control 20% / 38.77; delta **-4.58**, CI
  **[-7.569, -1.591]**: clear reject.
- **Conclusion:** unified V_win fails independently at both counterfactual card and shop scoring;
  this is not merely interaction between the two or estimator noise. Keep V_floor for card/shop and
  gate retrained V_win only on rest decisions. Learning card/shop later needs action-value/ranking
  targets or randomized counterfactual coverage, not more iterations of the same state classifier.
- **Loop refactor:** meta gates now retain the deployed hybrid and never auto-graduate to unified
  card/shop control. Combat value (candidate value + deployed policy) and combat policy (deployed
  value + candidate policy) have separate CSVs, confidence decisions, and atomic promotions; if both
  pass simultaneously, policy is deferred one iteration to avoid an untested combined stack. Policy
  training is capped by `POLICY_TREES=100` (default 100), while combat value remains capped at 400.
  Dashboard and history schema now report value and policy arms separately.

## 51. Larger training iterations, smaller held-out cap  ✅
- **Changed:** `RUNS_PER_ITER` from 500 to **1,000** and adaptive `GATE_SEEDS` from 1,000 to
  **500** (100-seed looks unchanged). This puts twice as many fresh self-play trajectories behind
  each retrain while bounding verification to half the previous worst case.
- **Resume safety:** `.done` markers now record the run target that created them. A marker is trusted
  only when it equals the current `RUNS_PER_ITER`; empty legacy markers or later target changes fall
  back to distinct-seed CSV counting. Iteration 9 therefore recognized its existing 500 meta and
  500 combat runs and launched exactly the missing 500 of each, beginning meta at seed 1,007,502.
- **Operation:** stopped the old in-memory 500/1,000 controller and resumed a single loop on eight
  logical CPUs with CPU-only XGBoost, 400 value trees, and 100 policy trees. This changes the
  training/evaluation allocation only; promotion still requires the same paired +0.5 margin and
  conservative 99% interval, with clear candidates allowed to stop before 500 seeds.

## 52. Speed-oriented self-play profile + value non-inferiority  ✅ deployed
- **Value promotion rule:** combat value is a latency optimization, so it now promotes when the 99%
  lower confidence bound beats `VALUE_MARGIN=-0.5`; meta and policy retain the stricter
  `PROMOTE_MARGIN=+0.5` superiority rule. Iteration 9's independently gated 400-tree value scored
  delta **+1.562**, CI **[-0.117, +3.241]**, and therefore passes non-inferiority. It was atomically
  deployed (122,080 nodes); the previous 1,500-tree / 311,006-node model is preserved as
  `selfplay/current/v_combat_trees.pre_iter9_1500.txt`. Earlier timing measured the actual candidate
  at 6.05s versus 11.21s for the deployed old stack with the same 100-tree policy (~1.85x faster).
- **Separate budgets:** combat/policy datagen uses **400 sims**, meta-label datagen **300 sims**, and
  held-out gates remain at **600 sims** through a new `GATE_SIMS` setting. Baseline-cache keys use
  the gate budget, so changing cheap datagen budgets cannot reuse or contaminate verification.
- **Cadence:** V_win and policy retrain/gate every **2** iterations (even iteration numbers by
  default); their data is still collected each iteration. Combat value continues every iteration.
  This removes repeated expensive gates for the historically wash/inconclusive rest and policy
  heads while preserving fresh replay data for their next scheduled update.
- **Validation:** shell syntax passes; cadence smoke gives due at iterations 10/12 and skipped at 11;
  the iteration-9 CSVs reproduce the non-inferiority promotion; deployed candidate/current hashes
  match; dashboard reports separate 400/300 datagen and 600 gate budgets and the value-specific bar.

## 53. Historical execution snapshot: iteration 10 on a Google VM
- **Machine:** `sts-test` in `europe-west3-c`, resized to Spot `c4d-highcpu-16`. The project exposes
  64 all-region CPUs, but the enforced C4D-family quota is 24 vCPUs; 16 is therefore the largest
  predefined C4D shape that can start without another quota approval. The loop uses all 16 OpenMP
  threads and CPU-only XGBoost.
- **Resume state:** the local loop was interrupted safely at iteration 10 and its **278/1,000**
  distinct completed meta trajectories were copied to `/mnt/sts-data/sts_lightspeed` together with
  the current models and required replay windows. The remote meta worker resumed exactly the
  remaining 722 runs at seed **1,008,280**; combat datagen remains 0/1,000.
- **Runtime safety:** the new 400 GB data disk holds the active workspace (2.8 GB at launch). A
  16 GB swap file on that already-provisioned disk supplements the VM's 29 GiB RAM to avoid an OOM
  kill during replay-window loading; it was unused at launch. The detached worker reported 16
  threads and roughly 1,400% CPU during its initial sample.
- **Resume audit/fix:** OpenMP completion order meant the interrupted 278-run meta file already held
  two seeds beyond its contiguous prefix. Resuming at `SEED_OFF + distinct_count` therefore reused
  two IDs and left seeds 1,008,023 and 1,008,275 absent. Both missing runs were appended with the
  same deployed stack, restoring exactly **1,000 unique meta seeds** while combat generation kept
  running. Future resumes now append beyond the maximum observed seed, persist that collision-free
  next seed in two-field `.done` markers, and advance `state.env` past the maximum used by either
  datagen pass; the dashboard accepts both legacy and new marker formats.

## 54. Strong-teacher redesign — historical iteration-12 plan/deployment snapshot
- **Teacher/student separation:** combat self-play targets now use `POLICY_SIMS=1000` while the
  deployed/gated agent remains at 400/600 simulations. The combined fight pass still emits value
  snapshots and policy visit targets once, but its policy target is now produced by a materially
  stronger search instead of redistilling the student's own 400-sim behavior.
- **Critical-state combat value:** `train_value_combat.py` weights low-HP, failed-fight,
  empirically high-failure-encounter, and high teacher-disagreement roots. Weights are clipped and
  mean-normalized; encounter difficulty is inferred from replay outcomes, not a hand-written tier
  list. Decision indices now advance even through forced roots and reset per fight, giving exact
  value/policy alignment. A four-run smoke matched all 274 sampled policy decisions and trained
  with disagreement on 274/362 value rows.
- **Paired campfire action values:** meta datagen optionally forks genuine rest-vs-smith states from
  the same pre-action context, uses a detached map and common future agent seed, and records both
  continuations. `train_rest_cf.py` predicts the direct paired gate-score difference; `v_server.py`
  serves it as `RC`, and deployment falls back to the existing V_win marginal comparison until a
  paired model passes the held-out gate. A 50-run smoke emitted 104 decisions from 37 runs, trained
  and served a compatible model, and replayed the previously crashing seed successfully.
- **Cadence and safety:** V_win, paired rest, combat value, and policy retrain/gate every two
  iterations by default; fresh data is still collected each iteration. Promotions retain the
  adaptive paired common-seed gate, 99% confidence bounds, +0.5 superiority for meta/policy, and
  -0.5 non-inferiority only for the latency-oriented combat value. At the 500-seed cap,
  inconclusive candidates remain rejected.
- **Operational telemetry:** the dashboard distinguishes deployed, teacher, meta, counterfactual,
  and gate budgets; reports paired-rest source runs/decisions; and avoids displaying a fake 0% win
  rate when a completed combat CSV is represented only by its authoritative marker.

## 55. Iteration-24 review — historical iteration-25 deployment snapshot
- **Progress audit:** iteration 20 produced the only promotion in iterations 12--24, raising the
  held-out deployed stack from **26.8% / 40.346 floors** to **31.4% / 41.218 floors**. Iterations
  22 and 24 regressed against that new baseline, while no meta or policy candidate promoted. The
  run is making real progress, but not yet consistently.
- **Capacity evidence:** iteration 24's validation RMSE was still improving at boosting round 1,499
  (10.154 at 400, 9.919 at 800, 9.785 at 1,499), but the exporter retained only 400 trees. A new
  held-out test of that exact model found the 1,500-tree export at **31.2% / 41.649 floors** versus
  **31.9% / 41.207 floors** for the deployed stack over 285 paired rows: blended delta **+0.372**,
  99% CI **[-1.935, +2.679]**. It is promising but not promotion-grade. The 800-tree export scored
  delta **-0.197**, CI **[-2.234, +1.841]**; on 281 exact common seeds, 1,500 beat 800 by **+0.605**
  blended score, also inconclusive.
- **Change:** future combat candidates now export all **1,500 trees**. Because this is a strength
  candidate rather than the old 400-tree latency optimization, its gate uses the standard
  **+0.5 superiority margin**, not the -0.5 non-inferiority allowance. The inconclusive iteration-24
  export was not promoted; iteration 26 will be the first newly trained full-capacity candidate.
- **Exporter fixes:** the validation output now has its own path instead of overwriting the replay
  training CSV, and validation reads only the 200 rows needed for the Python/C++ parity check rather
  than loading the multi-gigabyte replay window a second time.

## 56. Distilled native combat MLP  ❌ rejected at 500 paired seeds
- **Implementation:** `train_value_combat_nn.py` streams the replay CSV, samples by whole fight,
  predicts the full XGBoost teacher, trains a weighted MLP, and exports a standalone native format.
  `CombatValueNet` now loads either trees or `combat_mlp_sparse_v1`. Normalization is folded into
  the first-layer weights/bias so native inference skips zero card/relic features. Python/C++ parity
  for the final model had maximum error **0.000028 HP**.
- **Training:** the first dense 751->64->32->1 student used 458,638 sampled rows and generalized
  poorly across held-out fights (truth RMSE **11.521** versus teacher **7.159**). The final sparse
  751->128->64->1 student trained on all **1,830,668** iteration-24--28 replay rows (1,644,998 train,
  185,670 fight-group validation). It improved to truth RMSE **9.708**, teacher-imitation RMSE
  **5.749**, and critical-state truth RMSE **12.715**, but still trailed the teacher's **6.963**.
  Random row validation was misleadingly high (0.986 R2) because adjacent states from the same
  fights leak across a row split; the separate fight-group validation is the meaningful measure.
- **Speed:** on matched seed 2 at 600 sims and one core, sparse MLP took **5.043s** versus **11.775s**
  for 1,500 trees (**2.34x faster**). Across the first 100 seeds on 16 cores it took **50.45s**
  versus **66.55s** for the deployed 400-tree stack, about **24% faster** end-to-end.
- **Gameplay gate:** at 500 common seeds, deployed trees scored **31.4% / 41.218 floors** and the NN
  **24.6% / 39.644 floors**. Paired blended delta was **-2.254**, 99% CI
  **[-3.969, -0.539]**: a formal rejection even under the faster-model `-0.5` non-inferiority bar.
  The NN was not deployed. Its trainer, native evaluator support, model, parity data, and gate CSVs
  are preserved for a future categorical/embedding architecture; normal self-play remains on trees.

## 57. Entity-aware multi-head combat model  ❌ rejected at 500 paired seeds
- **Representation/output:** `train_value_combat_entity.py` replaces raw categorical integers with
  learned embeddings and pooling: four 371-card zone pools, relic and potion pools, encounter
  embedding, and a shared per-monster encoder with sum/max pooling. A 212->128->64 trunk predicts
  separate **P(fight win)** and **remaining-HP fraction conditional on winning** heads. Search backs
  up `P(win) * (win_bonus + E[HP|win])`; terminal rollout wins use the same `win_bonus + HP` scale.
- **Training:** CPU PyTorch 2.13 was installed on the VM. The model used 928,231 rows sampled by
  whole fight from the 1,851,423-row iteration-30--34 replay window, with 91,793 rows held out by
  complete fight. Best validation metrics were win Brier **0.0393**, win accuracy **94.9%**,
  conditional-HP-fraction MAE **0.0840**, and expected-end-HP RMSE **10.079** versus **8.049** for
  the iteration-32 tree teacher on the exact rows. Native/Python utility parity max error was
  **0.000022**.
- **Latency:** matched seed 2 at 600 sims took **6.465s** for the entity model versus **5.592s** for
  the deployed 400-tree model, so this candidate is ~16% slower and must prove superiority rather
  than use the faster-model non-inferiority allowance.
- **Tuning:** on seeds 0--99 at alpha 0.3, bonuses 0/25/50/100 produced blended deltas
  **-1.90/-1.51/-1.56/-3.97**. Bonus 25 was least bad. Its alpha sweep 0/0.1/0.2/0.3/0.5 gave
  **-7.04/-1.89/-2.18/-1.51/-2.45**; the catastrophic alpha-0 result shows that changing terminal
  reward to a survival bonus without the learned head does not help. Bonus 25, alpha 0.3 was selected
  and evaluated on untouched seeds 100--499.
- **Final gate:** over all 500 paired seeds, deployed trees scored **31.4% / 41.218 floors** and the
  entity model **27.6% / 40.004 floors**. Paired blended delta was **-1.594**, 99% CI
  **[-3.319, +0.131]**. The untouched 400-seed confirmation independently gave **-1.615**, CI
  **[-3.550, +0.320]**. Its upper bound is below the required **+0.5** superiority margin, so the
  model is formally rejected and was not deployed. Trainer, native format/evaluator, checkpoint,
  parity sample, and sweep/gate CSVs are preserved for research.

## 58. Shared-state entity policy prior  ➖ promising, not promoted at 500 paired seeds
- **Representation/training:** `train_policy_entity.py` encodes the combat state once per decision:
  learned embeddings pool cards separately across hand/draw/discard/exhaust, plus relics, potions,
  encounter identity, and shared monster/intent encoders with sum/max pooling. A 64-dimensional
  state vector and a card-aware action encoder produce a compatibility logit for each legal edge.
  Grouped cross-entropy directly fits the normalized MCTS visit distribution instead of regressing
  `log(visit+1)` independently per edge. The streaming loader retains one state per decision and
  splits by complete fight, permitting a large replay window without duplicating the 1,766-wide
  state for every action.
- **Data:** GPU training on the local RTX 3060 Ti used **every policy edge from iterations 26--35**:
  **16,861,363 edges / 3,127,654 decisions**, with no sampling. These iterations are post-redesign
  and share the post-iteration-20 deployed combat stack; earlier stale-teacher iterations were not
  mixed in. The fight-group split contained 2,815,541 training and 312,113 validation decisions.
  CPU preprocessing was capped at exactly eight threads.
- **Offline result:** the entity NN reached top-action agreement **57.01%**, captured visit share
  **37.87%**, softmax mass on the teacher-best action **34.76%**, and cross-entropy **1.4103**. The
  deployed 100-tree prior on the same held-out fights scored **46.93% / 34.88% / 30.51% / 1.4499**.
  The earlier single-iteration model reached only 53.0% top-action agreement, so the ten-iteration
  replay window materially improved generalization. Python/native maximum logit error was
  **0.0000030** across the 200-row parity sample.
- **Native inference:** `combat_policy_entity_v1` runs the state encoder once when an MCTS node is
  expanded, then only the small action encoder per legal edge. It is wired into the existing PUCT
  softmax without changing search semantics. The existing tree prior remains the default.
- **Current-stack gate:** on 500 common held-out seeds 51000--51499 at 600 sims, fair play, and
  eight threads, the deployed tree prior scored **33.2% wins / 42.280 floors / 12.644 end HP /
  7.225 CPU-s per run**. The entity prior scored **34.6% / 42.062 / 13.864 / 8.210**: +1.4pp wins,
  -0.218 floor, +1.220 end HP, and **13.6% more CPU**. The canonical floor + 10*win paired score
  delta was **-0.078**, SE **0.673**, 99% CI **[-1.815, +1.659]**. This does not clear the required
  +0.5 lower-bound margin, so it is preserved but **not promoted**.
- **Next policy-model test:** enrich future replay rows with target monster identity/status and
  potion identity (the current schema records only target HP and an is-potion flag), then retune
  policy temperature and `c_puct`. The large offline gain did not transfer decisively under the
  tree prior's existing PUCT calibration.

## 59. Entity-aware joint meta value model  ❌ floor head rejected; win head inconclusive
- **Representation/output:** `train_meta_entity.py` replaces the meta trees' thousands of sparse
  scalar columns with learned set encoders. Cards share an ID embedding augmented by count and
  upgraded fraction and use sum/max pooling; relics and potions have their own pooled embeddings;
  bosses, upcoming elites/fights, and bottled cards use categorical embeddings. Thirty-six
  normalized continuous features join a 192->96 trunk with separate **P(run win)** and
  **expected final floor** heads. The floor head predicts bounded remaining progress rather than an
  unconstrained absolute floor.
- **Data/training:** the CPU-only, eight-thread run used every one of the **182,958 state rows from
  10,000 runs in iterations 29--38**, split by complete seed. On the exact held-out rows, the NN
  improved win ranking (AUC **0.7215** vs tree **0.7144**) and floor accuracy (RMSE **9.769** vs
  **10.943**, R2 **0.247** vs **0.055**). Its win probabilities were slightly less calibrated
  (log loss **0.4337** vs **0.4301**, Brier **0.1346** vs **0.1340**).
- **Serving/parity:** `v_server.py` can opt into the joint TorchScript model with `VMETA_NN` and
  independently enable `VMETA_FLOOR` and `VMETA_WIN`; the existing XGBoost models remain the
  fallback/default. Fifty held-out rows matched offline inference within **5.4e-7** win probability
  and **7e-6 floors**. Serving now hides CUDA before importing PyTorch/XGBoost unless
  `VSERVER_ALLOW_CUDA=1`, preventing a CPU inference server from opening a GPU context.
- **Gameplay gate:** on seeds 53000--53099, the deployed tree stack scored **41.0% wins / 42.47
  floors**. Replacing only its floor decisions with the NN scored **27.0% / 35.90**; paired canonical
  score (`floor + 10*win`) delta **-7.970**, 99% CI **[-12.466, -3.474]**. It is decisively rejected:
  lower held-out regression error did not translate into useful action counterfactuals. The win
  head completed 81 paired seeds before interruption and scored **35.8% / 42.32**, delta **-0.506**,
  99% CI **[-4.406, +3.394]**; this is inconclusive and not promising enough to expose the user's
  machine to another large local gate while gaming. Neither head was deployed.
- **GPU incident:** during the partial win-head gate the NVIDIA driver exhausted VRAM, logged an
  MMU fault against a Python channel, then timed out the game context. No benchmark process survived
  the interruption. All inference tensors had been mapped to CPU, but explicit CUDA hiding is now
  enforced as an additional process-level safety boundary.

## 60. Paired card-reward action values with pretrained entity embeddings  ➕ offline-positive, not deployed
- **Target/data path:** `datagen3` can now fork every offered card plus skip from the identical
  pre-choice `GameContext`, detach the shared map, and finish branches with common agent/game RNG.
  Rows are grouped by `(seed, decisionIdx)`, contain the rich 1,017-feature state plus candidate
  identity/upgrade status, and store fractional mean outcomes over multiple matched futures. Output
  is flushed once per complete source run and is safe to interrupt/resume from collision-free seeds.
- **Label calibration:** three-fight bootstrapping through the old floor/win models was rejected: on
  24 exact decisions it chose the full-run-best action only **25%** of the time and had essentially
  zero rank correlation. Full-run 30-sim labels were also unstable versus 100 sims (best-action
  agreement **58.3%**, advantage correlation **0.234**). At 100 sims, averaging two futures gave
  one-vs-two-future advantage correlation **0.846** and sign agreement **91.7%**. Production data
  therefore uses **100 sims, two futures, full-run outcomes**, one sampled decision per source run.
- **Model:** `train_card_cf.py` trains a 180,349-parameter shared state/action model with separate
  base/upgraded card embeddings, pooled relic/potion/encounter state, candidate-to-deck attention,
  paired advantage regression, and a listwise best-action loss. Serving/deployment is intentionally
  deferred until offline ranking and a full gameplay gate pass.
- **Pilots:** with 500 decisions, scratch embeddings scored **36.205** versus **35.815** for the
  deployed floor-tree selector on 100 held-out paired decisions, but CI was wide. At 1,016 decisions,
  scratch training merely tied the tree. Initializing card/relic/potion and shifted candidate
  embeddings from the large-data `v_deckset.pt` checkpoint improved the same 204-decision validation
  to **36.875 / 46.6% best-or-tied**, versus tree **36.365 / 43.1%**. Paired delta was **+0.510**,
  SE **0.709**, 99% CI **[-1.317, +2.337]**: promising but not yet resolved.
- **Unattended scale-up:** the eight-thread, CUDA-hidden user service completed **20,000** additional
  decisions and automatic training. The final dataset has **21,863 decisions / 87,452 action rows**
  with zero partial groups or duplicate actions; 17,490 decisions train and 4,373 seed-held-out
  decisions validate the model. Artifacts are `selfplay/card_models/card_cf_full21k*`.
- **Full offline result:** the NN chose a best/tied action on **42.58%** of validation decisions and
  scored **37.161**, versus the deployed floor tree's **40.52% / 36.714**. Their paired score delta
  is **+0.446**, SE **0.119**, 99% CI **[+0.139, +0.754]**; NN/tree chose the same action 62.6% of
  the time (749 NN wins / 2,978 ties / 646 losses). The direct-action target has produced a
  statistically real offline improvement, but its 99% lower bound does not clear the normal +0.5
  promotion margin and offline labels are not a gameplay gate. Keep it undeployed until native/server
  parity, latency, and an adaptive paired full-run gate pass.

## 61. Full-map graph encoder for paired card values  ➖ implemented, no measured gain
- **Lossless reconstruction:** `one_combat_cardcf.elf mapbatch CARD_CF.csv MAPS.csv` now exports one
  deterministic map per `(seed, ascension, act)`. Each fixed 15x7 graph stores all 105 room ids,
  every outgoing edge as a seven-bit destination mask, and the burning-elite location. The 87,452-row
  full dataset reduces to **21,863 maps / 9.7 MB**. Recomputing the old forward-map distances and
  reachable-room counts from the exported graphs matched **all 21,863 decisions exactly**, so no new
  rollouts were needed.
- **Encoder:** optional fourth-argument map input in `train_card_cf.py` adds learned room, row, column,
  and burning-elite embeddings. A reverse sweep over the layered DAG recursively aggregates mean and
  max child messages, thereby carrying every downstream room and route into each ancestor. A
  state-specific readout pools only the roots/children reachable from the current map position. Its
  96-dimensional result enters the existing pretrained card network through a zero-initialized
  residual adapter. The graph model has **229,373 parameters** versus 180,349/180,950 reported for
  earlier variants and exports successfully to TorchScript.
- **Controlled offline result:** with the proven 21k card model frozen, six graph-only epochs selected
  a best/tied action on **42.9%** of the identical 4,373-decision validation split and scored
  **37.1626**, versus **42.6% / 37.1608** for the exact zero-map checkpoint. Paired delta is only
  **+0.0018**, SE **0.0683**, 99% CI **[-0.1740, +0.1777]**; choices agreed 86.1% of the time
  (267 graph wins / 3,858 ties / 248 losses). This is no evidence of useful map lift: the existing
  summary features likely capture most map information relevant to card selection, and the full-run
  labels remain noisy. Artifacts are `selfplay/card_buffer/card_cf_maps.csv` and
  `selfplay/card_models/card_cf_graph_full21k*`; keep this variant undeployed.
- **Runtime gate:** `VCARD_ACTION` in `v_server.py` and `STS_CARD_ACTION=1` in the C++ agent now
  provide an opt-in direct-action endpoint. It sends candidate upgrade flags, all 105 room ids and
  edge masks, the active burning-elite marker, and the rich state; the NN chooses cards and skip
  directly. A held-out serving row matched offline inference to **3.5e-8**, and TorchScript/runtime
  smoke tests passed. On **500 paired fair-play seeds 65000--65499 at 600 combat sims**, the floor
  tree scored **15.8% wins / 34.862 floors / 36.442 canonical score**; the graph NN scored **17.6% /
  35.770 / 37.530**. Paired score delta was **+1.088**, SE **0.726**, 99% CI **[-0.781, +2.957]**
  (195 NN wins / 159 ties / 146 losses by score). Runtime was only **1.5%** higher. The point estimate
  is encouraging but the 99% lower bound is below both zero and the +0.5 promotion margin, so keep
  the tree deployed. Per-seed results are `card_tree_gate_65000_500.csv` and
  `card_graph_gate_65000_500.csv`.

## 62. Full-map graph NN for path decisions  ➖ predictive gain, policy rejected
- **Data/model:** `mapbatch` now accepts any rich/meta CSV containing `seed`, `ascension`, and `act`.
  The 317,573-state / 21,863-run `pilot_meta.csv` reconstructs to **42,713 unique act maps / 19 MB**.
  `train_meta_entity.py` optionally adds the same reverse-DAG room/edge encoder through a
  zero-initialized residual on the frozen 96,727-parameter entity meta model. For training it pools
  all legal next children; at inference a third position coordinate selects one legal child so its
  complete downstream subtree is scored. The resulting model has **145,150 parameters** and is
  `selfplay/models/meta_graph_full21k*`.
- **Held-out prediction:** on 47,528 run-held-out states, the exact pretrained baseline had win AUC
  **0.7527**, log loss **0.2550**, and floor RMSE **10.328**. The graph residual improved these to
  **0.7752 / 0.2396 / 9.667** (floor R2 **0.330** vs **0.236**). Thus the historical maps are
  reconstructed correctly and contain useful predictive signal.
- **Serving/policy:** `VPATH_GRAPH` plus `STS_PATH_GRAPH=1` provides an opt-in `PG` endpoint. The C++
  agent leaves the actual run state at the parent and asks the NN to score each legal singleton child
  subtree; the heuristic remains the default and fallback. Runtime/TorchScript smoke tests passed,
  and a reconstructed source row matched direct TorchScript inference exactly (zero observed error).
- **Gameplay pilot:** on **128 paired fair-play seeds 66000--66127 at 600 sims**, heuristic pathing
  scored **15.6% wins / 35.953 floors / 37.516 canonical score**. Pure graph-NN pathing scored
  **10.2% / 35.633 / 36.648**. Paired delta was **-0.867**, SE **1.749**, 99% CI
  **[-5.373, +3.639]** (45 NN wins / 26 ties / 57 losses by score), with 7.8% runtime overhead.
  Do not extend or deploy this observational-value policy. Better absolute prediction does not identify
  the causal best route: training pooled the routes chosen by the heuristic, while inference asks for
  unseen singleton alternatives. The next justified version needs paired counterfactual outcomes for
  every legal child (or a conservative heuristic-residual trained on those direct advantages), not
  more epochs on terminal observational labels. Per-seed files are `path_heuristic_gate_66000_128.csv`
  and `path_graph_gate_66000_128.csv`.

## 63. Paired counterfactual path-action NN  ➖ offline-positive, gameplay inconclusive
- **Direct labels:** `pathcfgen` reservoir-samples one genuine branching map decision per source run,
  forks every legal child from an identical detached state, and completes each branch with common
  future agent seeds. Labels use the gate-aligned `floor + 10*win` score. Output is flushed after
  each complete source run. A two-salt 128-decision calibration found advantage correlation
  **0.836**, sign agreement **84.4%**, and best-action overlap **89.8%**, so production uses two
  futures and spends additional compute on more independent decisions rather than more futures.
- **Data/model:** 5,000 unique decisions (11,784 action branches) were collected with no duplicate
  actions or malformed groups; every source map was exported losslessly to
  `selfplay/path_buffer/path_maps_5k.csv`. `train_path_cf.py` initializes the entity/full-map
  encoders from `meta_graph_full21k.pt`, scores each candidate child subtree directly, and trains
  paired centered-regression plus listwise losses. Artifacts are `selfplay/models/path_cf_5k*`.
- **Held-out result:** on 1,000 seed-held-out decisions, the NN selected a best/tied route **64.9%**
  of the time and scored **32.220** versus **30.691** for the deployed heuristic (oracle 36.089).
  Paired delta was **+1.528**, SE **0.266**, 99% CI **[+0.843, +2.214]**. This establishes a real
  one-decision offline gain but is not sufficient for deployment.
- **Runtime integration:** `VPATH_ACTION`/`STS_PATH_ACTION=1` serves the direct `PA` endpoint;
  `STS_PATH_ACTION_MAX` limits non-heuristic interventions and `STS_PATH_ACTION_MARGIN` supplies a
  conservative predicted-advantage threshold. An opt-in `STS_PATH_ACTION_TRACE=1` prints the raw
  choice/margin/capacity response. Server and simulator must share the host network namespace;
  sandboxed simulator runs cannot reach port 5555 and silently exercise fallback policies.
- **Fresh gameplay look:** with at most one zero-margin intervention, 128 paired fair-play seeds
  71000--71127 at 600 sims gave heuristic **12.5% wins / 34.117 floors / 35.367 score** and NN
  **14.1% / 34.188 / 35.594**. Delta was **+0.227**, SE **1.786**, 99% CI
  **[-4.374, +4.827]**, with 7.4% runtime overhead (49 NN wins / 19 ties / 60 losses by dense
  score). This is inconclusive; do not deploy. The proper continuation is the existing adaptive
  gate's remaining 372 fresh paired seeds to the 500-seed cap, not additional training changes.

## 64. Future-fight auxiliary card supervision  ❌ initial model rejected (2026-07-22)
- **What:** paired card/skip continuations now record pass outcomes for the next combat, next routed
  elite, and current-act boss. These are produced by the normal copied `GameContext` continuation and
  combat search—so encounter queues, event pools, map routing, relics, potions, and ascension rules
  are simulated rather than represented by a hand-authored fight tier. The card-action NN receives
  three auxiliary survival logits (loss weight 0.3) while retaining its full-run value/ranking target.
- **Data:** 2,000 fresh full-run paired decisions / 7,853 action branches, adaptive two-to-eight
  futures, `selfplay/card_buffer/card_cf_future_fight_124k_2k.csv`. Near-term normal survival was
  nearly saturated (99.96% pass); elite pass was 97.1%; boss pass was 85.7% overall (89.9% conditional
  on reaching it). Thus boss survival is the meaningful extra supervision, not the next hallway fight.
- **Offline:** on 400 held-out decisions, future-fight NN selected score **37.676** versus **37.231**
  for the floor-tree selector. Its aggregate auxiliary survival accuracy was 95.4%, but is dominated
  by the trivial normal-combat target and is not policy evidence.
- **Fresh fair-play gate:** 128 common seeds 126000--126127 at 600 combat sims. Baseline floor-tree:
  **15.6% win / 39.352 floor / 7.031 HP**. Pure future-fight action NN: **6.2% / 31.578 / 2.633**.
  Paired canonical-score delta **-8.711**, SE 1.390; candidate/baseline/tie counts **20/78/30**.
  This is a decisive regression, not a noisy pilot: do not extend the gate or deploy either the action
  model or `VCARD_ACTION_SURVIVAL_W`. The immediate cause is likely data scale: the policy head was
  retrained on only 2k decisions, replacing the proven 21.9k full-run action-value dataset; the
  survival task did not compensate for that lost ranking coverage. Next version must initialize from
  or jointly train with the 21k card model, treating old rows as value-only and new rows as
  value-plus-survival, before another gameplay gate. Artifacts/results:
  `selfplay/card_models/card_cf_future_fight_124k_2k*` and
  `selfplay/gate/future_fight_124k_2k/`.
- **Additive retrain attempted:** `train_card_cf.py` now accepts value-only historic rows plus
  survival-labeled rows, masks the auxiliary loss on old rows, preserves the proven graph-card model's
  scalar normalization, and initializes all shared weights from `card_cf_graph_full21k.pt`. The joint
  23,863-decision / 95,305-action model froze the ranker for three epochs while calibrating only the
  new survival head, then fine-tuned. Its best held-out score was **37.285** versus **37.064** for the
  tree reference (the combined split is not directly comparable to the older 21k split).
- **Fresh fair-play gate:** 128 common seeds 126128--126255 at 600 combat sims: baseline **31.2% /
  40.984 floor / 9.977 HP**; initialized joint candidate **23.4% / 40.109 / 6.953**. Paired
  canonical-score delta **-1.656**, SE 1.259 (candidate/baseline/tie **35/49/44**). It is not a
  decisive 128-seed rejection, but its negative point estimate and failure to meet the required
  +0.5 lower-bound promotion condition mean **do not extend or deploy**. The extra labels alone have
  not yet produced a safe card policy improvement. Results:
  `selfplay/gate/future_fight_joint23k/summary_126128_128.json`.

## 65. Live all-act encounter-distribution card rollout  ➕ promising oracle; collect targets, do not deploy (2026-07-22)
- **Policy/evaluation:** `STS_ACT_FIGHT_PROBE_DRAFT=1` replaces only the *immediate* card/Skip
  selection with simulation. For each offer it samples four possible hidden remaining normal/elite
  encounter queues using the game's weighted pools and their no-repeat constraints, samples the
  current-act boss, then plays every reached combat on the chosen route through that boss. All
  candidate cards share each sampled queue (common random numbers). Map layout and non-combat RNG
  stay fixed; later simulated card choices use the ordinary server policy, so the current pick is
  selected **solely** by simulated combat outcomes, not a learned card scorer.
- **Objective:** each reached fight contributes a floor-distance-weighted, nonlinear post-fight HP
  safety value `sigmoid((HP/maxHP - 0.35)/0.10)`; a reached loss contributes -1. Averaging this over
  sampled queues naturally includes both an encounter's probability of occurring (the branch reaches
  it) and its conditional survival probability. This deliberately avoids hand-authored enemy/card
  tiers and avoids treating HP as linear. `STS_ACT_FIGHT_PROBE_FLOOR_DECAY` defaults to 0.985.
- **Fresh fair-play pilot + confirmation:** at 600 outer combat sims, 40 inner combat sims per
  fight, and four encounter-queue futures per offered action, the first 16 paired seeds
  126400--126415 gave baseline **18.75% win / 34.062 floor** versus rollout **25.00% / 40.812**,
  paired canonical (`floor + 10*win`) delta **+7.375**, SE 4.264. An independent 16 seeds
  126416--126431 gave **0.00% / 28.625** versus **18.75% / 38.625**, delta **+11.875**, SE 4.191.
  Combined 32-seed result: baseline **9.375% / 31.344 floor**, rollout **21.875% / 39.719**;
  paired delta **+9.625**, SE **2.969**, 99% CI **[+1.978, +17.272]**, with rollout/baseline/tie
  counts **19/8/5**. This is a real positive directional result, but not a promotion gate.
- **Cost/decision:** rollout consumed **80--126 CPU-seconds/run** versus **4.5--6.1** for baseline,
  so it is far too expensive to deploy as a default live policy. It is nevertheless the first
  future-fight formulation with a positive held-out signal. The justified next step is to collect
  its per-offer simulated all-act utilities as direct action labels, then train an NN to approximate
  this combat-strength-against-encounter-distribution target; retain the rollout as an offline
  oracle and require a normal large paired gameplay gate before any deployment. Results:
  `selfplay/gate/act_fight_probe_allact_16/` and
  `selfplay/gate/act_fight_probe_allact_confirm16/`.

## 66. Checkpointed combat-strength policy for every out-of-combat decision  ➕ strong pilot; confirm and distil (2026-07-23)
- **What changed:** `STS_ACT_FIGHT_PROBE_ALL_OOC=1` extends the encounter-distribution idea from
  card rewards to every strategic action. The original pilot exercised Act 1 map branches, card rewards, events, shops, rest
  sites, and selection targets. For a candidate action, the evaluator follows one ordinary
  out-of-combat trunk, but at each reached combat checkpoint scores every possible next
  normal/elite/boss encounter independently from the identical pre-combat state. It weights those
  scores by the game's encounter distribution and by distance, and uses the same nonlinear HP
  safety utility as the card-only probe. This is deliberately a *combat-strength profile*, not a
  recursive assertion that a floor-1 choice must already beat the Act boss.
- **Pilot:** 16 paired fair-play Ascension-0 seeds 126700--126715, 600 outer combat simulations,
  600 inner simulations per checkpoint fight, and four sampled remaining-encounter futures. Both
  arms used the deployed stack (card skip -0.5, heuristic pathing, shop-V, win-rate rest, PUCT);
  the candidate additionally enabled the all-OOC checkpoint probe and stopped after the Act-1
  boss. Thus `won` here means **cleared Act 1**, not a full-run win.
- **Result:** baseline cleared **9/16 (56.25%)**, reached mean floor **15.000**, and ended with
  mean HP **22.000**. The checkpoint candidate cleared **16/16 (100.0%)**, reached floor
  **16.000**, and ended with **61.875** HP. The paired Act-1 score `floor + 10*cleared` improved
  by **+5.375**, SE **1.690**, 99% normal CI **[+1.021, +9.729]**; 7 seeds improved, 0 regressed,
  and 9 tied on that intentionally coarse score. The result is driven by rescuing both floor-8
  deaths and five floor-16 deaths, while also producing much safer clears.
- **Cost and interpretation:** this is a strong directional result, not a promotion gate. The
  candidate consumed **6,951.89 CPU-seconds/run** versus **2.13** for baseline (roughly 3,265x),
  and only 16 paired Act-1 seeds were evaluated. It establishes that the proposed question—"how
  will this state perform against the possible upcoming fights?"—can select better live strategic
  actions under a very expensive teacher. It does not establish a full-run win-rate gain or justify
  deploying the literal rollout. Raw results are
  `selfplay/gate/act1_checkpoint_all_ooc_16/{baseline,candidate}.{csv,log}`.
- **Continuation plan:** (1) freeze this exact configuration and run one independent 16-seed
  paired Act-1 confirmation before changing any budget, utility, or policy; inspect per-decision
  traces to verify that every intervention is legal and that map/event/shop/rest actions are all
  actually exercised. (2) Add durable per-action teacher logging: state, legal actions, shared
  future samples, mean/uncertainty of the checkpoint utility, and its encounter/HP components.
  First calibrate a cheaper label setting against the 600-simulation teacher by action-ranking
  agreement, rather than assuming a reduced budget is adequate. (3) Collect action-conditioned
  counterfactual groups for all OOC decision types and train a distilled fight-strength/ranking
  model; action representations must cover cards/skip, map children, discrete event/rest choices,
  selection targets, and shop bundles. (4) Serve that model as an opt-in policy, verify
  Python/native parity and latency, then run the ordinary adaptive paired **full-run** fair-play
  gate. Only that final gate can decide promotion. Keep the direct checkpoint evaluator as the
  offline oracle and calibration target throughout.

### 66a. Known-boss correction and teacher traces (2026-07-23)
- The original pilot incorrectly treated the Act-1 boss as hidden: its counterfactual sampler
  replaced `gc.boss`, and its boss checkpoint averaged Guardian, Hexaghost, and Slime Boss. The
  boss is fixed at act generation and visible to the player, so the oracle now preserves the known
  boss and evaluates only that encounter with probability 1. The original 16-seed result remains a
  useful directional pilot, but is not a confirmation of the information-correct oracle.
- `STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv` now emits durable, append-only per-action rows:
  rich state features, all legal actions, known boss, the common future seeds, per-future utility,
  mean/sample-SD/SE, and each probability-weighted encounter/HP safety contribution. This should
  be enabled for the corrected calibration and confirmation runs.
- `STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS=N` supplies a local combat-strength horizon by scoring the
  next `N` reached combat checkpoints (rather than a variable number of map nodes); after the
  final scored checkpoint it does not pay for an unnecessary trunk fight. The 4-vs-2 future runtime
  calibration uses `N=3` before changing the combat-search budget.
- `STS_ACT_FIGHT_PROBE_PARALLEL=1` parallelizes the independent candidate-action × sampled-future
  branches within one OOC decision. With `bestbench ... 1 ...` it bypasses the otherwise empty outer
  OpenMP seed team, so `OMP_NUM_THREADS=8` genuinely supplies up to eight branch workers for one
  seed. It is intentionally disabled when dynamic potion saving or ordered tracing is enabled.
- `STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=400,200,100` optionally gives the first, second, and third
  reached checkpoint separate inner-combat base budgets. It applies to both each possible-encounter
  evaluation and the corresponding trunk fight; the live run remains at its ordinary outer budget.

### 66b. Three-checkpoint runtime calibration: four versus two futures (2026-07-23)
- **Setup:** corrected known-boss oracle; one fair-play A0 seed (126700); 600 live and inner combat
  simulations; three reached combat checkpoints; deployed skip/shop/rest/PUCT/V-combat stack; and
  `STS_ACT_FIGHT_PROBE_PARALLEL=1`, `OMP_NUM_THREADS=8`. The only changed setting was sampled
  encounter futures: 4 versus 2. Raw logs and durable teacher rows are in
  `selfplay/gate/act1_checkpoint_knownboss_runtime/`.
- **Runtime:** 4 futures took **418.77 wall-seconds**, **2,689.51 CPU-seconds** (mean active use
  ~6.4 cores); 2 futures took **274.10 wall-seconds**, **1,241.73 CPU-seconds** (mean ~4.5 cores).
  Thus 2 futures cut CPU by **53.8%** and wall time by **34.5%** (**1.53×** wall-time speedup). The
  weaker wall-time gain is expected: with only two futures, many two-action decisions expose fewer
  than eight independent branches and cannot fill all eight workers.
- **Scope:** both cleared Act 1, but ended at 65 HP (4 futures) and 90 HP (2 futures). One seed and
  different selected trajectories do **not** establish that two futures preserve teacher quality.
  Next use the teacher rows to measure chosen-action agreement and ranking regret against the
  4-future oracle before selecting the cheaper setting for a paired confirmation.

### 66c. Decreasing inner combat budgets across three checkpoints (2026-07-23)
- **Setup:** same corrected one-seed runtime setup as 66b, retaining **four** encounter futures,
  three checkpoints, 600-sim live combats, and eight-worker branch parallelism. Only the inner
  checkpoint schedule changed from uniform 600 to `STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=400,200,100`.
- **Runtime:** the decreasing schedule took **171.01 wall-seconds** and **1,083.21 CPU-seconds**,
  versus 418.77 wall-seconds / 2,689.51 CPU-seconds for uniform-600 four-future evaluation. That is
  a **59.2% wall-time reduction** (**2.45×** speedup) and **59.7% CPU reduction**. It cleared Act 1
  with 43 HP (uniform-600 cleared with 65 HP).
- **Scope:** retain four futures as chosen, but do not treat this single-seed trajectory as evidence
  that the decreasing schedule is an adequate teacher. Use the durable rows to compare action
  agreement/ranking regret to uniform 600 before adopting it for the paired confirmation.

### 66d. Direct learned combat transitions (2026-07-23)
- **Implementation:** `STS_ACT_FIGHT_PROBE_PREDICT=1` loads the existing entity combat model
  (`selfplay/models/v_combat_entity_iter34.txt`), which was trained from the combat buffer and has
  separate heads for `P(win)` and `E[end HP / max HP | win]`. At each checkpoint it now scores every
  possible enemy as `P(win) * HP-safety + (1-P(win)) * -1`, rather than playing a 400/200/100-sim
  MCTS fight. To reach checkpoints two and three, the sampled trunk applies the model's predicted
  win/loss (default threshold 0.5); on a predicted win it installs the predicted HP and calls the
  normal victory exit path, so Burning Blood and ordinary reward setup still occur. `sims=0` in the
  durable component trace explicitly denotes a model prediction, not a zero-budget combat search.
- **Runtime smoke:** on the same corrected fair-play A0 seed **126700**, four futures, three reached
  checkpoints, 600-sim live combat, eight-worker branch mode, and the 400/200/100 setting, the
  direct-transition run cleared Act 1 with 26 HP in **3.16 wall-seconds** (**2.81 CPU-seconds**).
  This is a **54.1x wall-time speedup** over 171.01 seconds for searched 400/200/100 checkpoints
  (and 132.5x over the 600/600/600 four-future runtime). Native inference was separately checked
  against 200 Python validation rows: max scalar difference 0.000023. Raw artifacts:
  `selfplay/gate/act1_checkpoint_knownboss_runtime/predict_entity_400_200_100.{log,time,teacher.csv}`.
- **Boundary:** this is a fast *approximate* transition, not yet a replacement teacher. It does not
  simulate card plays, potion use, combat RNG, transient relic/card counters, or exact rewards; the
  virtual victory preserves potions and uses the battle-start RNG state. The single successful
  trajectory proves integration and latency only. Before any policy-quality claim, compare action
  rankings/regret from these rows against the searched oracle on identical decision states, then run
  a held-out paired Act-1 gate if that agreement is acceptable.

### 66e. Full-run 16-seed smoke: **invalid pending reproducibility repair** (2026-07-23)
- The full-run smoke did execute real 600-simulation combats and did not accidentally stop after Act
  1: its candidate rows reach floors 20--50. Both arms nevertheless recorded **0/16** full clears.
  That outcome is plausible at this budget: the closest fair-play 600-simulation controls are
  12.5% (16 seeds 126500--126515), 15.6% (128 seeds 126000--126127), and 17.6% (500 seeds
  65000--65499) full-run win rate, for which an all-loss 16-seed block has roughly 12%, 6.6%, and
  4.5% probability respectively. It is not evidence of a hidden Act-1 stop.
- **Do not use the reported paired effect.** Repeating the candidate under the nominally same
  fair-play settings changes outcomes: parallel runs disagreed on seeds 126700 and 126704, and two
  serial one-seed replays of 126700 ended on floors 50 and 42. The serial 16-seed pass likewise gave
  baseline/candidate mean floors 17.0/29.4, not the parallel 16.75/31.0. Thus the prior apparent
  `+14.25`-floor result cannot yet be treated as a valid paired estimate.
- **Next requirement:** find and remove the remaining run-level nondeterminism (then require exact
  repeated per-seed CSV equality) before evaluating teacher agreement or running another gate. Raw
  forensic artifacts remain in `selfplay/gate/act1_predict_transition_fullrun16/`.

### 66f. All-act OOC scope and baseline boss-relic policy (implementation; pending reproducible gate) (2026-07-23)
- `STS_ACT_FIGHT_PROBE_ALL_OOC=1` now applies during **Acts 1--3**, rather than only Act 1. A
  boss-relic screen is an ordinary legal OOC action set: each relic is applied on a copied state,
  transition into the next act is performed normally, and that resulting state is scored at its
  next capped combat checkpoints. The current act's boss remains fixed/known throughout.
- The ordinary baseline already makes boss-relic decisions, but with the built-in
  `Expert::getBossRelicOrdering` table. It only switches those picks to V_win when
  `STS_BOSS_RELIC=1`; this was **not** enabled in the standard fair 600-simulation baseline. Thus
  the all-OOC candidate and baseline both choose a relic, but optimize it by different rules.
- Reproducibility audit: fully resetting `BattleContext`'s nested state at `init()` removed the
  baseline's repeated-seed divergence (seed 126700: three identical one-core replays all died on
  floor 8). The predictor/all-OOC path still has a separate first-run discrepancy, so no new
  all-act/full-run gate has been started; this entry records implementation scope, not a quality
  result.

### 66g. Serverless out-of-combat GBM evaluator (2026-07-23)
- **Implementation:** exported the deployed floor model `build/v_rich_xgb.json` to the native tree
  format `build/v_rich_trees.txt`. With `STS_NATIVE_OOC=1` (now the default), card rewards, shop
  bundles/removal, raw floor values, and win-rate rest/upgrade choices are evaluated in-process.
  The existing native `v_win_trees.txt` evaluator supplies the P(win) path. Set
  `STS_NATIVE_OOC=0` only for an explicit legacy `v_server.py` comparison.
- **Server scope:** the server was only an inference bridge. It served the floor GBM, win GBM, and
  optional neural/paired experimental endpoints; it was not needed for combat search or the entity
  checkpoint predictor. The native baseline replaces the GBM endpoints. Optional `STS_CARD_NN`,
  `STS_CARD_ACTION`, graph/path-action, and paired-rest experiments still require their respective
  server models.
- **Verification:** two independent no-server runs of seed 126700 under the four-future,
  three-checkpoint, direct-transition setup produced identical results: **1/1 win, floor 51,
  90 HP**, at about 15.3 CPU-seconds each. This also removes the previous cold-start race in which
  the first run began before the Python server had loaded its models and silently skipped cards or
  left shops empty.

### 66h. Native versus legacy server-backed evaluator, 64 paired seeds (2026-07-23)
- **Setup:** identical fair-play A0 configuration, 600 live combat simulations, four encounter
  futures, three checkpoint cap, direct entity combat transitions, PUCT/V-combat, seeds
  **126700--126763**, and eight outer workers. The only arm difference was OOC inference:
  `STS_NATIVE_OOC=0` with `v_server.py` versus the default native floor/win GBMs.
- **Results:** legacy server arm won **3/64 (4.7%)**, mean floor **32.03**, mean end HP **1.89**;
  native arm won **5/64 (7.8%)**, mean floor **32.55**, mean end HP **2.55**. Paired native-minus-
  server deltas were **+0.52 floors**, **+0.66 HP**, and **+2 wins**. The paired gate score
  (floor + 10×win) was **+0.83**, SE **1.13**, 95% CI **[-1.39,+3.04]**: no statistically reliable
  quality difference at 64 seeds.
- **Runtime (historical report):** server arm consumed **983.6 wall-seconds** (**380.6 reported process CPU-seconds**; the CSV's
  per-seed elapsed-time sum is 6471 seconds); native arm took **98.8 wall-seconds** (**722.6 process
  CPU-seconds**; CSV sum 738 seconds). Thus native was approximately **10.0× faster wall time**;
  the server arm's wall time includes Python socket/model overhead and did not scale efficiently
  across the eight workers. Per-seed elapsed times are not additive CPU measurements.
- **Conclusion:** native inference is the recommended baseline: it matches the legacy policy within
  this noisy 64-seed gate while eliminating the server dependency and cold-start failure mode. The
  comparison artifacts are in `selfplay/gate/native_vs_server_64/`.
- **Correction:** this 66h quality/runtime comparison is **invalid**. The first native implementation
  omitted the server's zero-signal upgrade-target fallback, so it was not policy-equivalent. A
  corrected one-seed check now matches the server exactly (seed 126700: floor 33). Do not use the
  earlier 64-seed deltas or 10x runtime claim as evidence.

### 66i. Primary recorded fair reference, 1,000 sims × 128 seeds (2026-07-23; historical)
- **Setup:** standard full-run stack with fair play, native in-process floor/win GBMs, PUCT/V-combat,
  no all-OOC checkpoint oracle, 1,000 live combat simulations, A0, seeds **126700--126827**, and
  eight outer workers.
- **Result (primary fair-play benchmark):** **39/128 wins (30.5%)**, mean floor **40.32**, mean end HP **11.91**. Runtime was
  **176.0 wall-seconds / 1,325.3 summed per-run elapsed-seconds**. Raw output is in
  `selfplay/gate/baseline_1000_128/`.
- This is the primary recorded fair-play score on the fixed 128-seed benchmark. Its cited raw
  directory is absent and the exact artifact/flag set is incomplete, so it is not exactly
  reproducible from the current checkout. It must not be
  compared directly with the historical 51.6%/1,000-sim known-RNG score: fair play re-randomizes
  hidden information during search, while known-RNG simulations can peek at future draws. The
  known-RNG number remains a diagnostic only; fair-play is the primary quality benchmark.

### 66j. Future-count / checkpoint-horizon sweep at 1,000 fair-play sims (2026-07-23)
- **Question:** does the all-OOC combat-strength evaluator improve full-run performance, and how
  many sampled futures and next combat checkpoints are useful? The candidate used the native floor/
  win GBMs, `STS_ACT_FIGHT_PROBE_ALL_OOC=1`, the entity combat predictor
  (`STS_ACT_FIGHT_PROBE_PREDICT=1`), and every legal Act 1--3 OOC action was scored. This is the
  fast predicted-transition evaluator, not the expensive searched checkpoint teacher.
- **Setup:** Ascension 0, fair-play, 1,000 live combat sims, common seed block 126700--126731,
  and futures × next-combats in `{1,2,4} × {1,2,3}`. A fresh baseline on the same block was
  **7/32 wins (21.9%)**, mean floor **37.31**, mean end HP **8.03**.

  | futures | next combats | wins | avg floor | avg end HP | paired score delta* |
  |---:|---:|---:|---:|---:|---:|
  | 1 | 1 | 1/32 (3.1%) | 29.41 | 1.34 | −9.78 |
  | 1 | 2 | 2/32 (6.2%) | 32.03 | 2.97 | −6.84 |
  | 1 | 3 | 2/32 (6.2%) | 31.25 | 2.75 | −7.62 |
  | 2 | 1 | 1/32 (3.1%) | 30.38 | 0.28 | −8.81 |
  | 2 | 2 | 2/32 (6.2%) | 30.91 | 1.81 | −7.97 |
  | 2 | 3 | 1/32 (3.1%) | **32.84** | 0.25 | **−6.34** |
  | 4 | 1 | 1/32 (3.1%) | 30.47 | 1.25 | −8.72 |
  | 4 | 2 | 2/32 (6.2%) | 30.41 | **3.25** | −8.47 |
  | 4 | 3 | 1/32 (3.1%) | 32.75 | 1.06 | −6.44 |

  *Paired score is `floor + 10×win`; deltas are candidate minus the fresh baseline per seed.
- **Verdict:** no performance gain appeared. The best depth point, 2 futures × 3 combats, was
  **−4.47 floors** and **−6.34 score units** paired against baseline, with 1 versus 7 wins.
  More futures did not improve the result, and longer horizons only partially recovered the damage.
  The current predicted-transition evaluator is therefore not deployable as an OOC policy. The
  likely issue is model/transition error compounding across counterfactual OOC trunks; the entity
  predictor does not model combat card/potion use or exact post-combat state transitions.
- **Reproducibility note:** the earlier stored 32-seed subset of the 128-seed baseline was 6/32,
  floor 39.59, while the fresh replay was 7/32, floor 37.31. This fair-play multi-thread run is
  not bit-identical across separate 8-thread invocations, so the table is directional; future
  gates should use repeated fixed-thread runs or single-thread paired evaluation.

### 66k. Direct next-combat OOC action labels and first NN (2026-07-24)
- **Collector:** added `oocnextgen`. It samples one genuine OOC decision from each baseline run,
  enumerates **all legal actions**, continues each branch only to its next battle, and records both
  the concrete baseline-combat result and the weighted result of searching every possible encounter
  at that checkpoint. This removes the multi-checkpoint predicted-transition approximation.
- **Dataset:** 2,000 seed-held-out decision groups and **10,564 action rows** across map, rewards,
  shop, rest, event, and selection screens. Mean group size was 5.31 actions. The concrete and
  all-encounter labels selected the same best action on **65.1%** of groups, giving an empirical
  upper-bound/noise reference for the target.
- **First model:** a raw rich-state/action MLP (`train_ooc_next_action.py`), 80/20 split by whole
  decision group. Held-out results on 400 groups: win Brier **0.0716**, win accuracy **90.9%**,
  HP-fraction MAE **0.211**, exact teacher-best action **29.5%**, and best-or-tied **42.8%**.
- **Verdict:** ✅ collector and labels are working; ❌ this first NN is not useful yet. Its action
  ranking is far below the 65.1% concrete-vs-encounter agreement ceiling. The next model should
  reuse/pretrain the large OOC state encoder and use structured action encodings (screen/action
  type, card identity, map child, shop bundle, event/selection target), rather than treating the
  raw 32-bit `GameAction` encoding as a universal action representation. Artifacts:
  `selfplay/ooc_buffer/next_combat_2000.csv` and `selfplay/models/ooc_next_action_2000*`.

### 66l. One-step NN evaluated against multi-checkpoint teacher (2026-07-24)
- **Question:** does a one-next-combat action model transfer to the desired multi-combat utility,
  or is a separate three-checkpoint target required? Reused the existing corrected **four-future,
  three-checkpoint** teacher trace (`futures4_teacher.csv`); no new rollout data was collected.
- **Result:** on 60 teacher decision groups / 201 legal-action rows, the NN score had Spearman
  correlation **0.636** and Pearson correlation **0.513** with the teacher's three-checkpoint
  utility. It selected the exact teacher-best action **56.7%** of the time and a best-or-tied action
  **70.0%** of the time; mean teacher regret was **0.093** utility units.
- **Interpretation:** one-step supervision does transfer to multi-checkpoint action ranking
  reasonably well. This supports directly wiring the NN into the three-checkpoint OOC benchmark;
  a new three-step training dataset is not required merely to test the idea. The result is an
  offline trace check only—the trace has one seed and is not a 64-seed gameplay gate.

### 66m. Repeated next-combat action NN benchmark (2026-07-24)
- **Setup:** paired fair-play A0 runs, 1,000 combat sims, 64 common seeds **126900--126963**.
  The action NN was queried in one batch for every legal OOC action and reapplied at every later
  OOC decision. The run was launched with the requested `futures=4` and `max-checkpoints=3`
  settings; those rollout knobs are metadata here because this deployed NN directly predicts the
  next combat rather than running the old checkpoint oracle.
- **Result:** baseline **14/64 wins (21.9%)**, mean floor **37.05**, mean end HP **7.53**;
  repeated-NN candidate **0/64 wins (0.0%)**, mean floor **19.53**, mean end HP **0.00**.
  Paired candidate-minus-baseline deltas were **−17.52 floors** and **−19.70** on `floor+10×win`;
  the candidate was better on 5 seeds, tied on 1, and worse on 58.
- **Verdict:** ❌ the first action NN does not transfer as a whole-run repeated OOC policy, despite
  its useful offline correlation with the three-checkpoint teacher. This is a deployment-level
  failure, not evidence that four futures or three checkpoints help: greedy next-combat action
  selection compounds errors across drafting, shop, rest, event, and map decisions. Keep the model
  as an offline ranker/diagnostic and do not promote it to the live OOC policy without structured
  action features, calibration, and a conservative gate against the existing policy.
- **Artifacts:** `selfplay/gate/ooc_action_nn_64_f4_c3/{baseline,candidate}.csv`.

### 66n. Server-path sanity check for 66m (2026-07-24)
- The OOC server was live and loaded `selfplay/models/ooc_next_action_2000`; a direct `OA` request
  returned one prediction per submitted action. With the server intentionally unavailable, the NN
  policy fell back to the ordinary baseline path: seed 126900 at 300 sims reached floor **50**.
  With the live OA endpoint, the same seed/budget reached floor **16**. Therefore the 0/64 result in
  66m is caused by the NN's selected actions, not a dead server or silent fallback.
- The earlier **32.75-floor** 4-future/3-checkpoint point in 66j is not the same policy: it used the
  native entity combat predictor inside the old checkpointed all-OOC rollout evaluator over the
  32-seed sweep. It did not use the new action NN or the OA server, and its score was already below
  the 37.31-floor baseline on that block.

