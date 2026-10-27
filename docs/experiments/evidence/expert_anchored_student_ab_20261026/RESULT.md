# Expert-anchored student_sel vs student_sel, paired A20 A/B: result (2026-10-27)

**Verdict: NOT_SHOWN.** Heart kills B (expert-anchored) 260/1,024 = 25.4% vs A (student_sel) 267/1,024 = 26.1%,
B − A −0.7 pp [−3.4, +2.0], 97 vs 104 discordant pairs, exact McNemar p = 0.67. student_sel stays.

## Run
- PREREG.md, run commit `d9aa44fa`, code `f526cef9`, binary `5d9ac015…` (x86-64-v3), expert.bin `14506144…`,
  student_sel.bin `cf6bf7fb…`. Authorization: Philipp 2026-10-26 22:03Z / 22:56Z (16 workers). Pre-launch review and
  delta check PASS (reviewer J, `/mnt/project-files/reviews/pr875-prelaunch-review.md`).
- 16 cloud workers, 2026-10-27 04:58Z–18:0xZ. The project share hit its file-count limit from ~05:40Z to 07:41Z (no new
  claims, uploads invisible across containers); work resumed without loss. W14 died holding 111384253; it was run
  locally for the futility look and W14's later tar is byte-identical to the local run.
- `verify.txt`: 1,024/1,024 units OK, 0 missing, 0 bad, one duplicate (111384717, both tars identical game records);
  `tars.sha256`. 2,048 games, all rc 0, all banner checks pass; 1,024/1,024 seeds valid. About 543 core-h.

## Endpoints (`result.json`)
| | A student_sel | B expert-anchored | B − A |
|---|---|---|---|
| Heart kills | 267 (26.1%) | 260 (25.4%) | −0.7 pp [−3.4, +2.0], p 0.67 |
| Act-4 arrival | 432 (42.2%) | 429 (41.9%) | −0.3 pp [−3.4, +2.8], p 0.90 |
| kills per Act-4 arrival | 0.618 | 0.606 | |
| mean final floor | 42.11 | 42.14 | +0.03 [−0.82, +0.88] |
| deaths act 1 / 2 / 3 / 4 | 141 / 233 / 218 / 165 | 139 / 232 / 224 / 169 | |
| mean wall per game | 954 s | 957 s | ratio 1.003 |

Futility look at 256 seeds (`FUTILITY.md`): Act 4 +2.3 pp → CONTINUE; the first 256 seeds' +1.6 pp Heart edge did not
hold.

## Mechanism (first divergence, B − A)
929 of 1,024 pairs diverge; 95 play identically. First divergences: act-1 card rewards 263 seeds (Heart −5), act-1
card selects 259 (−5), act-1 maps 105 (+2; the tree prior shifted), act-1 shops 51 (−2), act-2 rewards 48 (+2). No
screen's divergences carry a visible effect. Searched roots are map-only in both arms (37,258 vs 37,177).

## Reading
The fine-tune moved student_sel toward Baalorlord's picks offline (card rewards +8.0 pp, smith targets +12.5 pp on
held-out expert runs) and changed most games, but did not change how often they win. **Inference:** at the size of
change it makes, expert agreement on these screens is not what limits the A20 Heart rate; either the bot's other
decisions (combat HP loss, §688) dominate, or matching an expert's pick without his whole plan buys nothing. A larger
α or rest-site imitation was not tested.
