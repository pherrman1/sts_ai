# Map-mirror invariance of student_sel (offline, 2026-10-23)

Question (Philipp, 2026-10-23 23:20Z): is the A20 OOC prior student_sel invariant under a horizontal reflection of
the map (x -> 6 - x)? If not, mirrored training is a candidate augmentation. No seeds, no gameplay.

## 1. Source audit: is absolute map x game-relevant?

Engine (`sts_lightspeed` port in `src/`, `include/`), at main `c38fa53d`:

- `GameContext::curMapNodeX` is read only for topology and identity: `mapMoveCost` / `transitionToMapNode`
  (edge membership; Wing Boots allow any next-row node with edges, column-blind), `getCurMapNode`, the burning-elite
  test (`burningEliteX == curMapNodeX`, `BattleContext.cpp:346`, `GameContext.cpp:2105`) and logging.
- Room outcomes do not depend on x: `transitionToMapNode` reseeds misc/shuffle/cardRandom from `seed + floorNum`,
  `?` rooms roll `getEventRoomOutcomeHelper` on event RNG, monsters/elites come from the act's sequential lists.
- The burning elite is chosen at map generation (`Map.cpp:745-758`, from mapRng among elite nodes) and is part of
  the visible state; its buff type (`burningEliteBuff`) is column-independent.
- Floor 14 -> boss is action idx 0 (`mapMoveCost`: `curMapNodeY == 14 -> mapNodeX == 0`), an action id rather than a
  column; row-14 edges point to x = 3 (`Map.cpp:339`), which is its own mirror. The Act-4 map is a single x = 3 column.
- The next act's map is `Map::fromSeed(seed, asc, act, ...)`, independent of choices on this map.

So V(s) = V(mirror(s)) and the path policy should permute with the mirror, given the full visible map. The
**distribution** of generated maps is not mirror-symmetric (Java `MapGenerator` port; `mapstats.json`, 6,007
distinct act 1-3 maps): left/straight/right edge slots 113,722 / 187,277 / 120,361; mean x of elites 2.90, shops 3.15.

Java: the game JAR is only on Philipp's PC, so vanilla source was not re-read here. The live mod
(`LiveOocCapture.java`) exports the game's own `MapRoomNode.x/y`, edges (`nativeEdgeDestination`, row-14 boss edge
-> 3) and `hasEmeraldKey`; nothing in it or in the native importer uses x except as node identity.
**Unverified:** no vanilla Java mechanic reads the absolute column (none known; Winged Greaves are column-blind).

## 2. Mirror construction (`mirror.py prep`)

Records are heart1 capture rows, the student's held-out validation split (files with seed % 8 == 7: 8 old
`data/cap-*` files and 8 `data-select-20261017` files, data branch `claude/heart1-distill-data`), 267,871 rows of all
screens, 56,584 of them map screens (36,013 with >= 2 paths). Mirror: node xs, burning elite x, current x and offered
paths -> 6 - x (-1 kept), pathXs `[left, straight, right]` -> `[6-right, 6-straight, 6-left]`, map tokens re-sorted
by (y, x) as `buildRecord` emits them, floor-14 boss action kept. Checks: mirror(mirror(r)) == r on every row; 471
self-symmetric rows (mostly Act 4) score bit-identically.

## 3. Scores (`one_combat heart1score`, binary `b855ee27` = main `c38fa53d`)

Nets: student_sel `cf6bf7fb` (A20 OOC prior; its value head was never trained, value sd 0.002 in probability, so
its |dV| is uninformative) and AZ gen 2 `fc32d8f4` (student_sel fine-tuned with a Heart-kill value head, §621).
Teacher = heart1's recorded argmax on the original row, index-aligned.

| student_sel, map rows with >= 2 paths | n | top-1 flip | mean KL | mean JS | p99 JS | agree w/ teacher orig -> mirror |
|---|---|---|---|---|---|---|
| all map | 36,013 | 16.9% | 0.213 | 0.040 | 0.465 | 91.8% -> 80.8% |
| act 1 / 2 / 3 | 11,674 / 16,310 / 8,029 | 11.1 / 17.3 / 24.8% | 0.13 / 0.27 / 0.22 | | | 94.7->88.1 / 92.2->79.2 / 86.8->73.5% |
| start of act (mapY = -1) | 6,766 | 36.8% | 0.664 | 0.110 | 0.592 | 91.1% -> 61.5% |
| mid act | 29,247 | 12.4% | 0.109 | 0.023 | 0.280 | 92.0% -> 85.3% |
| non-map screens | 206,708 | 0.25% | 0.0002 | 0.0000 | 0.0008 | 94.47% -> 94.48% |

gen 2 is the same: map flip 16.1% (start of act 36.7%), teacher agreement 90.7% -> 80.7%. gen 2 value head: mean
|dP(win)| 0.0084 on map rows (p99 0.040, max 0.080), against a between-state sd of 0.158; mean |d logit| 0.053.

Averaging original and mirrored logits does not raise teacher agreement (map 87.2% vs 91.8%), consistent with the
teacher sharing the bias.

Start column chosen on act-start rows (`startcols.sel.json`, columns 0..6): teacher
1123 / 748 / 1912 / 1281 / 1258 / 273 / 171 (offered 4297 / 2820 / 3039 / 3371 / 3111 / 3214 / 2689); student
original 1065 / 740 / 1942 / 1248 / 1354 / 283 / 134; student on mirrored maps 468 / 650 / 1985 / 1299 / 1435 / 393 /
536, where an equivariant net would give 134 / 283 / 1354 / 1248 / 1942 / 740 / 1065.

Worst cases (`stats.sel.json` `worst_map`) are act starts with two or three single-node starts at the edges, e.g.
row 81840 (A20 act 2, starts at x = 0 and 6, both monsters): original [0.999, 0.001] picks x = 0, mirror
[0.001, 0.999] again picks x = 0, i.e. the column, not the subtree. Teacher logits there: -2.44 vs -10.91.

## Interpretation

Material violation of an exact game symmetry: on map screens the student changes its top choice under reflection
on 17% of rows (37% at act start), and its agreement with the teacher's choice drops 11 pp (30 pp at act start). It
behaves partly like a column prior: strongly left-leaning at act start. The teacher has the same left preference
(col 0 chosen 26% of the times offered, col 6 6%); whether that reflects real structure of the asymmetric map
distribution or a bias in heart1 cannot be told without scoring heart1 on mirrored maps (**open question**). The
value head (gen 2) is close to invariant (~5% of its between-state sd). Non-map decisions are unaffected. Offline only:
the effect on play (MCTS prior and student rollouts) is not measured.

## Reproduce

```
python3 mirror.py prep RUN <16 held-out capture files>
one_combat heart1score student_sel.bin RUN/orig.jsonl RUN/orig.sel.scores.jsonl     # from the repo root
one_combat heart1score student_sel.bin RUN/mirror.jsonl RUN/mirror.sel.scores.jsonl  # same for gen2.bin -> gen2
python3 mirror.py stats RUN sel; python3 mirror.py startcols RUN sel; python3 mirror.py mapstats RUN
```

Hashes of the binary, nets, inputs and score files: `inputs.sha256`. Wall: ~20 min on 4 cloud CPUs.
