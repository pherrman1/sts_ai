# Gen-6 GPU training data (never merge)

Transfer of the gen-6 Silver MLP prior pack for the 512/256 teacher, distilled arm D and embedding arm E
on Philipp's GPU. Gen-6 plan: /mnt/project-files/silver-az-mlp/gen6/train/PLAN-train.md (project share).

Reassemble: `cat pack-g6.npz.gz.part* | gunzip > pack-g6.npz` and check `sha256sum -c SHA256SUMS`.
`arch_dev.py` = net-arch thread's arch.py (share sha 3e736bba) + `--device`, env `STS_TOOLS`, `ARCH_RUNS`;
CPU smoke gives byte-identical results to the original. `silver_az_mlp.py` = tools/ after #535 (3e28818).
