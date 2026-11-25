"""Read-only: draws N random samples from a saved selfplay.py replay window (mmap, no copy of the window) and writes
them as gathered training batches (Replay._gather, unpacked layout) of MB rows, G batches per .npz file.

Run niced on the PC while the live run continues; it only reads the saved window directory.
usage: python3 slice_replay.py REPO REPLAY_DIR OUT_DIR [N=65536] [MB=64] [G=128] [SEED=20261124]
"""
import importlib.util
import json
import os
import sys
import time

import numpy as np

repo, rdir, out = sys.argv[1:4]
N = int(sys.argv[4]) if len(sys.argv) > 4 else 65536
MB = int(sys.argv[5]) if len(sys.argv) > 5 else 64
G = int(sys.argv[6]) if len(sys.argv) > 6 else 128
SEED = int(sys.argv[7]) if len(sys.argv) > 7 else 20261124

spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

with open(os.path.join(rdir, "state.json")) as fh:
    st = json.load(fh)
lay = st["layout"]
R = sp.Replay.__new__(sp.Replay)
ld = lambda k: np.load(os.path.join(rdir, k + ".npy"), mmap_mode="r")
R.compact, R.compress, R.hp_runs, R.soft_q = lay["compact"], lay["compress"], lay["hp_runs"], lay["soft_q"]
R.meta, R.hq_lo, R.hq_len, R.soft_outcome = {}, None, None, None
for k in lay["arrays"]:
    if k.startswith("meta."):
        R.meta[k[5:]] = ld(k)
    else:
        setattr(R, k, ld(k))
if R.compact:
    R.tok_type, R.ids, R.f = ld("store.tok_type"), ld("store.ids"), ld("store.f").view(np.float16)
R.cs, R.ci, R.ca = len(R.ntok), len(R.tok_idx), len(R.a_type)
R.cq, R.cr = len(R.sq), len(R.hpr)
R.ct = len(R.tok_type)
s_tail, s_head = st["scalars"]["s_tail"], st["scalars"]["s_head"]
n = s_head - s_tail
rng = np.random.default_rng(SEED)
pick = rng.choice(n, N, replace=False)
j_all = (s_tail + pick) % R.cs
os.makedirs(out, exist_ok=True)
SMALL = {"tok_type": np.int8, "ids": np.int16, "a_type": np.int16, "a_src": np.int16, "a_tgt": np.int16}
t0 = time.time()
nb = N // MB
for fi in range(0, nb, G):
    arrs = {}
    for bi in range(fi, min(nb, fi + G)):
        jj = np.sort(j_all[bi * MB:(bi + 1) * MB])
        b = R._gather(jj)
        for k, v in b.items():
            arrs[f"b{bi}.{k}"] = v.astype(SMALL[k]) if k in SMALL else v
        arrs[f"b{bi}.abs"] = (s_tail + pick[bi * MB:(bi + 1) * MB]).astype(np.int64)
    np.savez_compressed(os.path.join(out, f"part{fi // G:03d}.npz"), **arrs)
    print(f"part {fi // G}: batches {fi}..{min(nb, fi + G) - 1} ({time.time() - t0:.0f} s)", flush=True)
info = {"replay_dir": rdir, "extra": st.get("extra"), "s_tail": s_tail, "s_head": s_head, "N": N, "MB": MB,
        "G": G, "seed": SEED, "secs": round(time.time() - t0, 1)}
with open(os.path.join(out, "info.json"), "w") as fh:
    json.dump(info, fh)
print(json.dumps(info), flush=True)
