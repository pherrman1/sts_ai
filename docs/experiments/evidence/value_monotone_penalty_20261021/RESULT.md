# OOC value head: monotonicity penalty — result (2026-10-21)

Plan: `PLAN.md` here (written before training). Runs on Philipp's GPU 14:1x–15:0xZ; weights, `train.log` and
`summary.json` per run on the data branch `claude/az-gen2-data` under `gen2/mono/` (`8718d6ab` seed 0, `6b23ed47` B_s1).
distill.py = sweep file `0f25037c…` + `apply_mono.py` → `b15843bb…`; monotone.py `09efffaf…` (= PR head `eb52ab45`).
Encoded-tensor cache `eb5e79069123c0c1` reused (no re-encode). No game seeds.

## Verdict: FAIL (offline gate), stopped before seeds 1–2 of M*

The penalty does what it is trained to do (fewer wrong-signed pairs on held-out folds, no policy cost) but only by
weakening the value head: every weight that moves max HP much fails the value-BCE allowance, and the qualifying weight
(M = 0.3) leaves max HP wrong in 53 % of states and misses both `prices.py` teacher-gate items it targets. The
remaining seed runs (B_s2, M0.3_s1, M0.3_s2) were stopped at Philipp's request (15:02Z) to free the GPU; they could
not turn the `prices.py` items (30 % vs ≥ 90 %; 90.8 % vs ≥ 95 %) into a pass.

## Training runs (gen-2 pick recipe, seed 0 unless noted)

Selection fold (seed % 8 == 6) except the val columns; violation = better state gets the strictly lower value logit,
fixed deltas −3 HP, +5 max HP, +50 gold, first filled potion emptied, Clumsy added (fp32, chosen epoch).

| run | epoch (run) | sel KL | sel value BCE (const 0.642) | sel AUC | val KL | val BCE (const 0.622) | val AUC | viol hp | viol max HP | viol gold | viol potion | viol curse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_s0 | 17 (20) | 0.05541 | 0.5588 | 0.740 | 0.05414 | 0.5255 | 0.758 | 15.7 % | 83.6 % | 47.1 % | 0.19 % | 0 |
| B_s1 | 17 (20) | 0.05535 | 0.5582 | 0.740 | 0.05429 | 0.5252 | 0.758 | 15.9 % | 83.7 % | 47.3 % | 0.20 % | 0 |
| M0.3_s0 | 17 (20) | 0.05527 | 0.5607 | 0.739 | 0.05394 | 0.5285 | 0.754 | 14.7 % | 52.6 % | 26.9 % | 0.02 % | 0 |
| M1_s0 | 17 (20) | 0.05509 | 0.5691 | 0.729 | 0.05346 | 0.5368 | 0.742 | 14.4 % | 33.8 % | 17.8 % | 0 | 0 |
| M3_s0 | 20 (20) | 0.05490 | 0.5824 | 0.708 | 0.05314 | 0.5502 | 0.720 | 13.9 % | 27.7 % | 13.2 % | 0 | 0 |

- B_s0 reproduces the sweep's pick (sel KL 0.0554, BCE 0.5590 / AUC 0.740 there); B_s1 its seed 1 (0.0553 / 0.5583).
- Validation-fold violation rates match the selection fold within 1.5 points (`summary.json["monotone"]`).
- Decision rule: KL cap 0.0560 met by all; BCE cap B + 0.003 = 0.5618 met only by M0.3 → **M\* = 0.3**.
- With a probability tolerance of 0.001 the max-HP rate is 82 / 44 / 19 / 9 % (B / 0.3 / 1 / 3): at high weight
  most remaining violations are near-ties.
- Epoch time 35 s with the penalty vs 22 s without (one extra forward/backward per batch).

## `prices.py` on the exported heads (2,916 post-combat round-2 states, one_combat heart1score, main `95df6614`)

Probe reproduces the gen-2 thread's `gen2-prices.json` exactly on `fc32d8f4`. `prices_gate.py` here adds the
sign shares; `prices/*.json` = `prices.py analyze` output.

| head (export sha256) | −1 / −3 / −6 HP sign right | max HP +5 > 0 (pos-slope states) | gold +50 > 0 | 12-HP slope p50 | potion HP-eq p50 | Fairy p50 | max HP HP/pt p50 |
|---|---|---|---|---|---|---|---|
| B_s0 (`e87b8c56`) | 71.1 / 88.6 / 94.1 % | 11.1 % | 65.2 % | 0.00128 | 9.6 | 16.1 | −1.55 |
| M0.3_s0 (`78ebd133`) | 78.6 / 90.8 / 94.9 % | 30.5 % | 81.7 % | 0.00087 | 13.6 | 21.7 | −0.43 |
| M1_s0 (`2119415c`) | 77.4 / 91.2 / 94.6 % | 46.3 % | 87.5 % | 0.00059 | 19.3 | 29.9 | −0.04 |
| M3_s0 (`a7d70b08`) | 68.0 / 91.2 / 94.9 % | 59.2 % | 90.1 % | 0.00031 | 34.1 | 49.6 | +0.12 |

Gate items (DESIGN.md): max-HP price > 0 in ≥ 90 % — FAIL at every weight; −3 HP sign right ≥ 95 % — FAIL at every
weight. Potion and Fairy items were not targeted.

## Reading

- The hinge is satisfied mostly by **flattening** the head along the perturbed inputs: the per-HP slope falls 1.5×
  (M0.3) to 4× (M3), so every HP-equivalent price inflates (potion 9.6 → 34 HP at M3) and AUC drops. The penalty has
  no term that keeps the magnitude of a correct difference, so "flat" is the cheapest way to stop being wrong.
- HP sign errors barely move (15.7 → 13.9 %) even at M = 3. **Inference:** consistent with the gen-2 thread's finding
  that hp / max HP / gold enter only through silverbot's FixedVec sinusoids (frequencies up to 10 rad per unit, no
  linear copy), so ±1–6 HP lands on nearly unrelated features; a hinge on the output cannot make that encoding smooth.
- The one-bit run outcome z injects the wrong max-HP trend in the first place (raw heart1 is ~10 % wrong on max HP and
  gold on the gen-2 validation probe, heart1 fine-tuned on z 64 %; gen-2 thread, 14:46Z).

## Not done
- Seeds B_s2, M0.3_s1, M0.3_s2 (stopped by request; B_s2 was killed at epoch 6, nothing pushed).
- Untested alternatives (not pre-registered): a penalty against raw heart1's value-difference signs instead of fixed
  rules; smooth linear extra inputs for HP, max HP and gold (needs a native port and parity).
