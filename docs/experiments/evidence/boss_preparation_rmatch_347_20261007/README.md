# #347 boss-preparation R-match on #417 sources (2026-10-07)

Frozen plan: [PLAN.md](PLAN.md). Sources: [selection.json](selection.json)
(`select.py` over the #417 rows at evidence ref `10e56bd8` and the frozen #425
manifest), frozen before any comparison run. Ledger §388; PR #428.

- Baseline `main` `866e8c32` (merge of #425). Diagnostic build source
  `5549a16a` (parent `e6b6122a`, the #425 research patch on the #417 baseline
  `5e9583cc`). Binary SHA-256
  `b9dc45ad12fd6cc75faf4f0c21d488868cfc5451456ca513c9e675a74531de0b`
  (`linux-gcc-release`, `one_combat`, GCC 13.3). Models and arm env as in PLAN.md.
- Independent pre-run review: clear, no blocking findings. Run frozen at plan
  commit `c797c311`.
- Run ([run/](run/)): `run.sh` on one 4-CPU cloud container, four workers,
  08:47–08:53 UTC. All eight processes exit 0, all eight sources `VALID`.
  `analyze.py selection.json run --out report.json` reproduces
  [report.json](report.json).
- Pre-review checks ([fixtures/](fixtures/), [smoke/](smoke/), never pooled): see
  PLAN.md.

## Validity (implementation)

Every reconstructed run matched its historical #417 row on all eight fields;
the hook saw the expected boss in the target act at budget 10,000; each M source
fight was a loss and each F source fight a win, as recorded. Each original-seed
10k control reproduced its source fight exactly (outcome, raw terminal HP, full
action trace, post-exit state digest, simulations). Control and fresh rep-0
repeats were identical. All rows started from their entry digest and every
searched root ran exactly 10,000 steps. M and F fresh rows of each seed used the
same planner seeds.

## Result (descriptive, four failure-enriched seeds)

Verdict **`PREPARATION_HEADROOM_SIGNAL`, shape consistent_positive**: F won
29/32, M 1/32; 28 F-only, 0 M-only, net +28 (rule needs >= 8); all four seeds
positive (rule needs >= 3). Seed-cluster bootstrap of mean net per seed
(descriptive): [5.75, 8.0] of 8.

| seed | boss | M entry HP | F entry HP | important entry differences (F vs M) | M wins/8 | F wins/8 | F-only | M-only | net |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| 48000024 | Champ (a2) | 80/85 | 80/80 | upgrades 16 vs 4; relics 11 vs 7; M 449 gold unspent, no shop visit; F Strength potion | 0 | 8 | 8 | 0 | +8 |
| 48000014 | Donu & Deca (a3) | 80/80 | 80/80 | upgrades 19 vs 6; relics 17 vs 8; elites 6 vs 3; 3 potions vs 1 | 1 | 8 | 7 | 0 | +7 |
| 48000116 | Champ (a2) | 54/85 | 92/100 | HP +38; Potion Belt, 3 potions vs 0; 2× Demon Form+; elites 5 vs 3 | 0 | 8 | 8 | 0 | +8 |
| 48000095 | Time Eater (a3) | 80/80 | 117/117 | max HP +37; relics 14 vs 9; elites 6 vs 4; 1 potion vs 3 | 0 | 5 | 5 | 0 | +5 |

Raw terminal HP when won (before act-transition healing): F 24: 57, 63, 32, 22,
69, 67, 78, 41; F 14: 45, 55, 50, 38, 56, 44, 51, 64 (M's one win: 1 HP); F 116:
12, 25, 2, 16, 14, 8, 7, 1; F 95: 19, 4, 23, 4, 8. Per-pair rows and
`postExitSummary` are in `run/<stateId>.rows.csv` (kind=fresh, same rep).

### Compact deck / relic / potion differences

Multiset differences of the entry state (upgraded copies count as distinct
cards). Room visits are `PathHistory.roomVisits` (shop, rest, event, elite,
monster, treasure) at boss entry. Full lists: `report.json` `entryDifference`.

- **48000024 Champ.** Cards only M: Barricade, Battle Trance, Blind, Carnage,
  Clash, Defend×4, Ghostly Armor+, Immolate, Perfected Strike+, Power Through,
  Sentinel, Shrug It Off, Strike×5, Thunderclap, Warcry+, Writhe (curse). Only F:
  Anger, Battle Trance+, Carnage+, Clash+, Defend+×4, Discovery, Enlightenment,
  Ghostly Armor, Heavy Blade, Immolate+, Inflame, Metallicize, Metallicize+,
  Panacea+, Pommel Strike, Sentinel+, Shockwave, Strike+×4, Sword Boomerang.
  Relics only M: Mutagenic Strength; only F: Bag of Marbles, Bird-Faced Urn,
  Centennial Puzzle, Frozen Egg, Regal Pillow. Potions: M none, F Strength.
  Rooms M 0/7/5/4/12/2, F 2/6/4/4/12/2.
- **48000014 Donu & Deca.** Cards only M (23) include Shrug It Off×4, Impervious,
  Metallicize, Dark Embrace+, Parasite (curse), unupgraded Bludgeon/Clash/
  Havoc/Uppercut; only F (21) include Fiend Fire+, Reaper+, Inflame, Inflame+,
  Whirlwind+, Anger, Anger+ and upgraded Bludgeon/Clash/Havoc/Uppercut/Shrug×2.
  Relics only M: Centennial Puzzle, Runic Dome, The Abacus; only F: Bag of
  Preparation, Brimstone, Ectoplasm, Gremlin Horn, Lantern, Maw Bank, Prayer
  Wheel, Shovel, Singing Bowl, Smiling Mask, Sundial, War Paint. Potions M
  Gambler's Brew; F Blood, Speed, Entropic Brew. Rooms M 5/9/7/3/18/3,
  F 3/10/10/6/13/3.
- **48000116 Champ.** Cards only M: Armaments, Carnage+, Clash, Infernal Blade,
  Iron Wave+, Perfected Strike, Power Through, Pummel×2, Reaper, Strike+, Twin
  Strike, Warcry+, Wild Strike. Only F: Chrysalis, Clash+, Cleave, Demon Form+×2,
  Discovery, Feed+, Havoc×2, Immolate+, Impervious+, Pommel Strike, Sever Soul×2,
  Thunderclap, Whirlwind+. Relics only M: Burning Blood, Hand Drill, The Abacus,
  Tiny House; only F: Bag of Marbles, Black Blood (Burning Blood upgrade),
  Omamori (2), Potion Belt. Potions M none; F Weak, Elixir, Dexterity.
  Rooms M 4/4/3/3/14/2, F 2/6/5/5/10/2.
- **48000095 Time Eater.** Cards only M (20) include Offering×2, Combust, Mayhem,
  Finesse, Panic Button, Carnage, Carnage+, Havoc, Havoc+, Parasite (curse); only
  F (18) include Fiend Fire+, Bludgeon+×2, Body Slam+, Feed, Headbutt,
  Headbutt+, Battle Trance+, Shockwave, Pummel. Relics only M: Pantograph, Toy
  Ornithopter; only F: Bag of Preparation, Incense Burner, Meat on the Bone,
  Pear, Potion Belt, Red Mask, Self-Forming Clay. Potions M Ancient, Swift×2;
  F Block. Rooms M 3/7/7/4/21/3, F 2/6/8/6/20/3.

RNG stream counters differ between M and F on every seed (cardRng, potionRng,
merchantRng, aiRng and others), as expected: the entries do not share a combat
future.

Cost (eight reps per source): M 15.12M simulations, 274 CPU-s; F 11.67M,
219 CPU-s. M fights ran longer (more decisions per fight) on three seeds.

## Interpretation (separate from validity)

- The historical contrast persists under fresh planner seeds almost completely:
  the M entries won 1 of 32 continuations, the F entries 29 of 32. The selected
  #417 MCTS boss deaths were therefore not combat-planner bad luck, unlike the
  #425 C sources.
- **Inference:** on these seeds OOC MCTS reached much weaker boss entries than
  flat10k OOC play. The descriptive differences point at elites/relics,
  upgrades, shops and HP/max HP, but entries also differ in RNG state and the
  combat future, so no single decision or feature is shown causal.
- Four selected, failure-enriched seeds; not a full-run or win-rate estimate
  and not an estimate of how much of the #417 MCTS regression comes from boss
  preparation in general.

## Recommended next experiment

Localize the OOC decisions behind the stronger F entries. Per seed, align the
M and F trajectories (both reproducible on build `5549a16a`) and find the
earliest consequential divergence among route/elite choice, rest vs upgrade,
shops (M left 449 gold unspent on 48000024), card and relic picks. Then run the
cheapest counterfactual on one recurring decision family, for example forcing
the flat10k choice at that decision inside the MCTS trajectory. No new model or
boss heuristic first.
