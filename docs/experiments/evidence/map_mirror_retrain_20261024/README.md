# student_sel retrained with 50% map mirroring (offline, 2026-10-24)

Follow-up to §674 (`../map_mirror_20261023/`). Philipp chose "Retrain starten" on 2026-10-23 23:55Z. Offline only.

## Pre-registered gate (written in the decision card before training)

Compared with student_sel (E_d64_sel_xin) on the unchanged validation set:
- top-1 vs heart1 on the original validation rows at most 0.5 pp below student_sel, and
- map top-1 flip rate under the mirror below 5%.

Passing makes F an offline candidate only; an A20 A/B needs Philipp's separate authorization.

## Run

- Code: `tools/heart1/distill.py --mirror 0.5` (+ `tools/heart1/map_mirror.py`), commit `4acd3425`, on Philipp's
  PC (3060 Ti) via Remote Control, 2026-10-24 00:00-01:31Z.
- Recipe identical to E (`results/E_d64_sel_xin/summary.json` on data branch `claude/heart1-distill-data`): same 128
  files in the same order (checked), init student C, d64/L2/mult 4/heads 4, trim map, 6 epochs, bs 256, lr 3e-4,
  wd 0.01, seed 0, AMP, extra inputs; best-validation epoch (6). Train 1,723,730 rows / 112 files, val 243,103 rows
  / 16 files; initial validation KL/top-1 identical to E (1.4203 / 0.7576).
- Output: data branch `9601d463`, `results/F_d64_sel_xin_mirror50/` (student.pt `9a6bec57…`, export
  `student_mirror50.bin` `acc9051e…`, summary, log).
- Mirror audit: §674's `mirror.py stats` / `startcols` on the same 267,871 held-out rows, native `heart1score`
  (binary `b855ee27`). Hashes: `inputs.sha256`.

## Result

| | E = student_sel | F = mirror 50% |
|---|---|---|
| val top-1 vs heart1, all rows (distill.py) | 94.11% | 93.38% (−0.73 pp) |
| val KL | 0.0522 | 0.0590 |
| map top-1 / KL | 91.88% / 0.0586 | 86.97% / 0.1048 |
| other screens | — | within ±0.01 top-1 of E (`summary.json` per_screen) |
| map top-1 flip under mirror | 16.9% | 2.5% |
| — act start / mid act | 36.8% / 12.4% | 8.8% / 1.05% |
| — act 1 / 2 / 3 | 11.1 / 17.3 / 24.8% | 0.8 / 3.1 / 3.9% |
| map mean JS (p99) | 0.040 (0.465) | 0.0001 (0.0018) |
| map agreement with heart1, original / mirrored | 91.8% / 80.8% (mean 86.3%) | 86.9% / 86.8% (mean 86.9%) |
| map agreement act 1 / 2 / 3 (original) | 94.7 / 92.2 / 86.8% | 93.0 / 87.2 / 77.6% |
| map agreement act start (original), the largest drop | 91.1% | 79.4% |
| non-map flips | 0.25% | 0.10% |

Start column chosen at act start (`startcols.m50.json`): F original 822 / 487 / 1887 / 1259 / 1701 / 389 / 221,
mirrored 214 / 428 / 1877 / 1252 / 1729 / 446 / 820 (equivariant: 221 / 389 / 1701 / 1259 / 1887 / 487 / 822);
teacher 1123 / 748 / 1912 / 1281 / 1258 / 273 / 171.

Gate: flip criterion PASS (2.5% < 5%); top-1 criterion FAIL (−0.73 pp > 0.5 pp). **GATE: FAIL**.

## Interpretation

Augmentation makes the net nearly mirror-equivariant (flips 16.9% -> 2.5%, JS ~400x smaller) and leaves non-map
screens unchanged. What it loses is agreement with heart1 on original map rows (−4.9 pp, act 3 −9.2 pp). Because the
game symmetry is exact (§674), heart1's original-map labels cannot be matched by an equivariant net wherever heart1
itself is asymmetric (on such a row an equivariant net can agree with at most one of the two orientations). The drop is
therefore consistent with a column-biased teacher; it does not by itself show that F chooses worse.
Averaged over both orientations F agrees with heart1 slightly more than E (86.9% vs 86.3%). The pre-registered gate
measures imitation of a teacher that is (at least partly) column-biased, so it cannot separate "less biased" from
"worse"; only play can. F is not a candidate under the gate as written.

**Open question:** how asymmetric heart1 is (score heart1 on mirrored records; needs silverbot + heart1.pt on the PC).
