# §423 raw worker folders w01..w04 (backup)

Backup of /mnt/project-files/ooc-rollout3-lizard/w01..w04 (ledger §423, PR #475), made 2026-10-11 while the shared folder
was at its file limit and dropped new files. The loose w01..w03 files had already been removed from the share. Data branch only; not for merging.

Restore: `tar -C /mnt/project-files/ooc-rollout3-lizard -xf wNN.tar` (creates wNN/). Check with
`cd /mnt/project-files/ooc-rollout3-lizard && grep -E ' w0[1-4]/' <repo>/docs/experiments/evidence/ooc_rollout3_lizard_20261010/data-sha256.txt | sha256sum -c`.

```
88e6bb39b51c3cf618bdfffc854f4c8bf63f3bfb594eedaabbbd7a0622179820  w01.tar
43272e55a6875e9af7a825faff4762ca598dfe7640a8d4ad6d37a42a62827a65  w02.tar
bc8713d43d2180e2b4a95bbb6e653b3d600a367e810fc836621f06e42cc367c6  w03.tar
3128578b47d527fb06b0326364173b3b5485efd658a2ac9e963064a2486ac913  w04.tar
```
