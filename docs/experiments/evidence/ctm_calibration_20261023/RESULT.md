# CTM-calibration guard at A20: NOT_SHOWN (+2.15 pp), the default stays (2026-10-24)

**Question** ([PREREG](PREREG.md)). With the per-fight CTM calibration now the A20 default (ADR-0058), does the search
kill the Heart clearly less often than with the raw CTM (`STS_CTM_CALIBRATION=0`)? Only WORSE (the CI's upper bound
below 0) turns the default off.

**Run.** Frozen at run commit `4056cef9` (code `c38fa53d`, #845 merged), binary `b855ee27…`. 16 cloud workers × 4
lanes, queue schedule, from 2026-10-23 23:25Z to 2026-10-24 02:21Z. 512 seeds (111392000–111392511), both arms per
seed on one lane. `tools/cloud/verify_campaign.py`: 512 of 512 units OK, no duplicates, all on the run commit, 16 of
16 workers done ([`guard/verify_summary.txt`](guard/verify_summary.txt)). All 1,024 games are valid.

| arm | Heart kills | reached Act 4 | kills per Act-4 arrival | deaths in act 1 / 2 / 3 / 4 | mean floor | wall vs A |
|---|---|---|---|---|---|---|
| A (`=0`, raw CTM) | 24.0% (123) | 40.6% (208) | 59.1% | 68 / 117 / 119 / 85 | 42.0 | 1.00 |
| C (the default) | 26.2% (134) | 44.3% (227) | 59.0% | 60 / 110 / 115 / 93 | 43.1 | 1.05 |

**Result** ([`analyze.py`](analyze.py) output: [`guard/analysis.json`](guard/analysis.json)).
- **Primary: C − A +2.15 pp [−1.17, +5.66], NOT_SHOWN.** 45 seeds were kills in C only and 34 in A only (exact
  McNemar p 0.26). It is not WORSE, so the default stays.
- Reached Act 4: +3.71 pp [+0.20, +7.23] (secondary, descriptive; McNemar 52 vs 33, p 0.050). Kills per Act-4 arrival
  are the same (59.0% against 59.1%): C's extra kills come from reaching the Heart more often.
- The frozen prediction was 0 pp. The point estimate came out +2.15 pp; the 10-seed smoke had leaned the other way.
- Play, by act:
  - C fights more Act-3 elites (1.64 against 1.51 per run); Acts 1–2 are about the same (2.47 / 1.73 against
    2.46 / 1.71).
  - It enters fights with the same HP: within 0.3 HP in every act. The predicted lower HP in Act 2 did not show.
  - Fights entered below 20 HP in Act 3: 45 in C and 39 in A, with 18 and 14 deaths.
- Search: searched roots (33,404 against 32,489) and picks off the prior's argmax (4.8% against 4.9%) are about the
  same, no root was aborted, and the learned OOC stop fires at about the same share of fast roots in every act.
- Wall: C / A 1.05, below the 1.10 flag.

**The CTM's precision on the guard's own fights** (descriptive, not pre-registered). These are the 24,186 real fights
of both arms: new seeds, played on today's engine with the fixes the §670 rows predate (#831, #833, #835, #836). The
frozen binary scored them with `=0` and with the default ([`guard/precision_guard.json`](guard/precision_guard.json),
`tools/ctm_calibration.py compare`):

| fights | rows | deaths: observed | raw CTM | calibrated | death log loss: raw → calibrated | won fights: HP MAE |
|---|---|---|---|---|---|---|
| all | 24,186 | 0.032 | 0.040 | 0.034 | 0.0711 → 0.0660 | 8.65 → 7.75 |
| Act-1 bosses | 975 | 0.081 | 0.107 | 0.070 | 0.2008 → 0.1910 | 11.11 → 10.80 |
| Act-3 bosses | 1,122 | 0.141 | 0.174 | 0.143 | 0.2728 → 0.2239 | 25.98 → 16.50 |
| the Heart | 413 | 0.378 | 0.512 | 0.403 | 0.4405 → 0.3815 | (the run ends) |

- Over all fights the log-loss change is [−0.0064, −0.0038] and the HP-error change [−0.99, −0.79] (seed bootstrap,
  95%). The mean HP bias of won fights goes from −2.24 to −0.11.
- Act-1 bosses improved this time; on §670's held-out games they had got worse.
- A few groups got a little worse: Act-2 elites are predicted at 0.049 against 0.039 observed (log loss still
  0.1035 → 0.1026), Slime Boss 0.2191 → 0.2248, Gremlin Nob 0.0579 → 0.0602, Slavers 0.0999 → 0.1018.

**Conclusion.** The guard found no loss, and its point estimate favours the calibration (+2.15 pp, CI −1.17 to +5.66).
The default stays (ADR-0058). On 24,186 fresh real fights the calibration predicts deaths and HP better, about as
much as on §670's data.

## Files and commands
- Raw: the 512 unit tars in `/mnt/project-files/ctm-calibration-ab/units/`.
- Rows (concatenated `*.ctm.jsonl.gz` per arm, in path order): A 11,950 rows `1c898d9a…`, C 12,236 rows
  `2752c57a…`. Scores (sha256): `=0` A `03900619…`, C `c7dffd91…`; default A `c9248483…`, C `36229092…`.

From the repository root at the run commit:
```
python3 -I tools/cloud/verify_campaign.py docs/experiments/evidence/ctm_calibration_20261023 --extract X
python3 -I docs/experiments/evidence/ctm_calibration_20261023/analyze.py X analysis.json
for arm in A C; do (for f in X/out/units/*/$arm-*.ctm.jsonl.gz; do zcat "$f"; done) > R/$arm.jsonl; done
FAST=selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
STD=selfplay/models/combat_transition_near_full_escape_pathb_a20.native
STS_CTM_CALIBRATION=0 one_combat ctmscorerows R/A.jsonl zero0/A.csv $FAST $STD 1        # and R/C.jsonl
env -u STS_CTM_CALIBRATION one_combat ctmscorerows R/A.jsonl default/A.csv $FAST $STD 1  # the default
python3 -I tools/ctm_calibration.py compare zero0/A.csv default/A.csv zero0/C.csv default/C.csv \
  --json precision_guard.json
```
