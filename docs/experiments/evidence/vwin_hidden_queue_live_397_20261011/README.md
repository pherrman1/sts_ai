# §434 — hidden encounter queue in the native OOC fallback: live ablation (#397)

**Result: `LEAK_NOT_SHOWN`.** On 128 paired seeds, the legacy native fallback (reads the realized
`nextEliteId`/`nextFight0..2`) won 103/128 and the public-futures fallback (`STS_OOC_PUBLIC_FUTURES=8`)
won 104/128: Δwin +0.8 pp, 95% CI [−4.7, +6.3]; 6 public8-only vs 5 legacy-only wins (McNemar p = 1.0);
Δfloor −0.18 [−1.13, +0.83]; 54.1 vs 53.2 s per run. 73/128 trajectories diverged; 112/128 seeds ended
with the same outcome and floor.

- [PREREG.md](PREREG.md): frozen before the pilot ran (copy on the share at the same time).
- [arm.sh](arm.sh), [run_pilot.sh](run_pilot.sh): exact environment and units; the only arm difference is
  `STS_OOC_PUBLIC_FUTURES` 0 vs 8.
- [analyze.py](analyze.py) → [report.json](report.json): `python3 analyze.py <pilot dir>`.
- [data-sha256.txt](data-sha256.txt): per-unit CSV hashes.

Code main `491bc21b`, Release `one_combat` sha256 `bab14cd5…ee6c`, 4-CPU cloud container, 4 units in
parallel, 1 OMP thread each. Seeds 74015000–127, smoke 74015900. Validity: 8/8 units rc=0, every seed once
per arm, public scorer receipt `futures=8` with scorers > 0 on all 128 public8 seeds (mean 23 per run),
none in legacy.

Raw: `/mnt/project-files/vwin-hidden-397/s434-raw.tar.gz`
(sha256 `df4983d4df36f3ff981d7a4f4e4f2ec45205110804f596ff993201f979533741`; CSVs, logs, decision traces,
smoke).

**Limits.** 128 pairs resolve only effects of roughly ±5 pp or larger. Only the §422 off base (V4 gates on,
OOC MCTS off, `STS_REST_WIN=0`) was tested; with `STS_REST_WIN=1`, or with V4 gates off, more decisions go
through the fallback.
