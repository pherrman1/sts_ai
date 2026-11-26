"""Draws N_MB batches of 1024 rows uniformly (without replacement) from all seen rows and writes each as a small
compressed npz (rows padded to the batch's own max tokens / actions). Low RAM: PASS batches per pass over the runs.
usage: python3 build_batches.py SLICE_DIR OUT_DIR N_MB [PASS=16] [SEED=20261126]"""
import glob, os, sys, time
import numpy as np
sdir, out, N_MB = sys.argv[1], sys.argv[2], int(sys.argv[3])
PASS = int(sys.argv[4]) if len(sys.argv) > 4 else 16
SEED = int(sys.argv[5]) if len(sys.argv) > 5 else 20261126
MB = 1024
TOK = ("mask", "tok_type", "ids", "f"); ACT = ("a_type", "a_src", "a_tgt", "a_f", "a_mask", "policy")
files = sorted(glob.glob(os.path.join(sdir, "seen_*.npz")))
zs = [np.load(fn) for fn in files]
runs = []   # (file index, run name, n rows)
for fi, z in enumerate(zs):
    names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
    for nm in names:
        runs.append((fi, nm, len(z[nm + ".outcome"])))
n = np.array([r[2] for r in runs]); off = np.concatenate([[0], np.cumsum(n)])
N = int(off[-1]); print(f"{len(runs)} runs, {N} rows", flush=True)
rows = np.random.default_rng(SEED).permutation(N)[:N_MB * MB].reshape(N_MB, MB)
os.makedirs(out, exist_ok=True)
t0 = time.time()
for p0 in range(0, N_MB, PASS):
    blk = rows[p0:p0 + PASS]
    ri = np.searchsorted(off, blk, side="right") - 1          # run of each row
    need = np.unique(ri)
    parts = {b: [] for b in range(len(blk))}
    for r in need:
        fi, nm, _ = runs[r]; z = zs[fi]
        run = {k.split(".", 1)[1]: z[k] for k in z.files if k.startswith(nm + ".") and not k.endswith((".abs", ".run_id"))}
        for b in range(len(blk)):
            m = ri[b] == r
            if m.any():
                parts[b].append({k: v[blk[b][m] - off[r]] for k, v in run.items()})
        del run
    for b in range(len(blk)):
        P = parts[b]
        T = max(p["mask"].shape[1] for p in P); K = max(p["a_mask"].shape[1] for p in P)
        o = {}
        for k in P[0]:
            vs = []
            for p in P:
                v = p[k]
                if k in TOK: v = np.pad(v, [(0, 0), (0, T - v.shape[1])] + [(0, 0)] * (v.ndim - 2))
                if k in ACT: v = np.pad(v, [(0, 0), (0, K - v.shape[1])] + [(0, 0)] * (v.ndim - 2))
                vs.append(v)
            o[k] = np.concatenate(vs)
        np.savez_compressed(os.path.join(out, f"b{p0 + b:04d}.npz"), **o)
        del o
    del parts
    os.sync()
    print(f"batches {p0}..{p0 + len(blk) - 1} ({time.time() - t0:.0f} s)", flush=True)
print("done", flush=True)
