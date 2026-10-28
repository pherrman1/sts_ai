# Smoke: exact replay of §644 sources (2026-10-28)

The original units are from `/mnt/project-files/ooc-sibling-crn/units/`. The comparison drops only timing, sha and
environment fields. The one differing policy row in each check is the outcome row's `producerSha`.

## Today's main (`015618c`) with every comparability flag
Flags: `STS_OOC_MCTS_LEAF_CALIBRATION=0 STS_CTM_CALIBRATION=0 STS_CTM_A20_HP_FINETUNE=0 STS_SILVER_ACT4_STRONG=0
STS_OOC_MCTS_SCREENS=all STS_CALLING_BELL_CARD_RNG_FIX=0`.
- **Source 111144546** (died on floor 6): 43 policy rows, 150 capture rows and 5 CTM rows. All match, including all
  32 repeat values of every row.
- **Source 111144735** (Heart kill): drifts at CTM row 13, an act-2 elite on floor 27.
  - Real-combat HP after the fight is 69 in the original and 63 in the replay. Capture rows match up to row 1,252.
  - Engine fixes since `90eb9f07` change real combats, and some have no restore flag (live problems 99–101, the
    Corruption fixes).
  - **So main cannot reproduce the §644 data.**

## Backport: `90eb9f07` plus the swkeyed code (`d4a4ec3c`)
Binary sha256 `382997c2…`, `linux-gcc-release-x86-64-v3`. [run_unit.sh](run_unit.sh) with `EST=base`:
- **111144546:** all rows and repeats match.
- **111144735** (Heart kill, 1,743 s): 385 policy rows, 31 CTM rows and 2,033 capture rows. All match the original,
  including all 32 repeat values per row.

With `EST=swkeyed` on 111144546:
- The policy and CTM rows match the base run, so play is unchanged.
- All 150 capture rows carry `rolloutEstimator: swkeyed`, and their repeats differ.
- The repeat values equal main's `015618c` swkeyed values under the restore flags on the same source.

## swkeyed vs base on source 111144546 (main with flags, VR arms base and swkeyed, R = 128)
- The pooled mean difference over 8 roots is −0.011 (SE 0.007), and 2.7 % of 150 rows have |z| > 2.
- The R = 32 label run gave −0.031 (SE 0.014) over the same 8 roots. With R = 128 that shrank, so it reads as noise
  on few roots.
- In the campaign, the paired bias check over all 320 sources (the §644 labels are the base arm, row by row) is the
  real test.
- In that run, base had 127 deaths in 4,800 label rollouts (2.6 %) and swkeyed had 0.

## CPU
Label rollout CPU, swkeyed / base, on the same 150 rows:
- 1.30 on main;
- 1.23 on the backport, with another job on the container.

The capture rollouts are 30–31 % of source wall time (111144546 and 111144735 originals), so a source costs about
1.07–1.09× its §644 time.

## Groups
`crn_groups.py` (data branch `claude/az-gen2-data`) on the 240 original TRAIN units reproduces the content of
`crn_train_groups.jsonl.gz` exactly: 15,129 groups and 155,368 rows. Only the gzip header differs; the original's
sha256 is `dc5b67e0…`.
