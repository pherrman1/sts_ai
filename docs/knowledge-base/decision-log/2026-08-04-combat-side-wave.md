# 2026-08-04 — Combat-side wave: vnet rejected under gates; 4,000-sim budget established for the gate stack

Date: 2026-08-04
Session/task: Execute the combat-side wave (plan A+B): A/B the fair 1,500-tree
combat value net under the one-ply gate stack, then sweep the fair-play sim
budget of the gate stack on the recorded blocks.

## Decisions

1. **The fair combat value net is rejected under the gate stack.** Wave A
   (fair, A0, 1,000 sims, 128 seeds 126700–126827, V3 full gates @m1.0 vs the
   same + `STS_VNET=build/v_combat_fair_trees.txt`): α0.3 = 36.7% (−3.1pp vs
   the 39.8% reference), α0.5 = 39.8% (+0.0pp), α0.3+`STS_POLICY=0` = 36.7%
   (−3.1pp), at ~3.1–3.2× cpu. `STS_VNET` stays off for the gate stack; no
   V4+vnet arm (no positive point to extend). EXPERIMENTS.md §97.
2. **4,000 sims is the new recommended combat budget for the gate stack.**
   Wave B (fair, gates-only, GCP 24 threads): on the 256-seed block
   126700–126955, 4k sims = **44.5% vs 37.1% at 1k (+7.4pp win CI
   [+1.2,+13.7], +2.7 floor CI [+1.2,+4.1], +4.2 HP)** — win and floor CIs
   exclude zero; the curve is monotone (2k +2.0pp wash, 3k +5.9pp, 4k +7.4pp)
   and matches the §26 known-RNG direction. EXPERIMENTS.md §98.
3. **Process:** Wave A ran locally on 12 threads (each arm ~3–5 min;
   fair replay is bit-identical across thread counts, §69, and the reference
   was re-verified bit-identical first). Wave B ran on the GCP server
   `sts-test` per the established protocol; server sources + model artifacts
   verified hash-identical to local HEAD before use. An initial server
   artifact check was confused by comparing an md5 to the tracked sha256 —
   the artifacts actually match.

## Rationale

- §28's old +6.2pp vnet gain was measured against the pre-gate fair baseline;
  the PUCT prior + gate stack already capture what the net's leaf offered,
  and its older-era guidance hurts at low α. **Inference.**
- The fair sim frontier being flatter than known-RNG (2k wash vs §26's +8pp)
  fits the standing finding that fair-play combat is HP-starved and needs
  more search; no cheaper per-sim shortcut has ever matched it (§21–§23).

## Alternatives considered

- V4 token net + vnet — skipped: no positive α point at V3 to extend.
- 5,000-sim arm — deferred: §26 shows the known-RNG curve flattens past
  4–6k; run only if 4k's +7.4pp needs a plateau check.
- vnet α tuning (0.7) — pointless: α0.5 already ties the free reference at
  3.2× cost; a dominated lever needs no fine-tuning.

## Evidence

- EXPERIMENTS.md §97/§98; per-seed CSVs `build/vnet_{a03,a05,a03_nopol}_128.csv`,
  `build/simsweep_{2k,3k,4k}_256.csv`, `build/simsweep_{2k,3k}_128.csv`;
  reference re-measurement /tmp/opencode/repro_gates.csv (0 non-`sec` diffs vs
  `build/gates_ref_m1.csv`); paired_analysis.py outputs; server logs
  `/tmp/wb_*.log` on `sts-test`.

## Status and follow-up

- Wave A closed (negative, recorded); Wave B closed with a new top arm.
- **New top arm (EXPERIMENTS.md §99):** V4 token net full gate stack @3,000
  sims = 45.3% win / 42.9 floor / 25.3 HP on the 256-seed block, +8.2pp win
  (CI [+0.8,+15.6]) and +2.0 floor (CI [+0.3,+3.7]) vs the previous
  recommended config (V3@1k, 37.1%), at 3.4× cpu. V4@4k adds +1.2pp
  (noise, floor/HP flat) — 3k is the operating point.
- Open: whether to adopt V4@3k as the recommended configuration for future
  gate rounds (baselines table updated; a default flip remains a separate
  deployment decision given the 3.4× cost); 5k plateau check optional
  (curve is flat between 3k and 4k for V4).
