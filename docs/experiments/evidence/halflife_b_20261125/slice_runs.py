"""Read-only: draws WHOLE runs (all their samples, in sample order) from saved selfplay.py replay windows (mmap)
and writes them as gathered rows (Replay._gather, unpacked layout), one gather per run, many runs per .npz file.

Test B of thread "Check Carbon's training proposals" (2026-11-25): EMA halflife 10 vs 20, offline.
SEEN  = runs of window W1 (the checkpoint was trained on them), the oldest run of the window dropped (may be cut).
UNSEEN = the first runs of window W2 whose samples all lie after W1's s_head (added after W1 was saved).

usage: python3 slice_runs.py REPO W1_DIR W2_DIR OUT_DIR [N_SEEN=3000] [N_UNSEEN=1500] [SEED=20261125]
Run niced (nice -n 19 ionice -c3) on the PC while the live run continues; it only reads the two window dirs.
"""
import importlib.util
import json
import os
import sys
import time

import numpy as np

repo, w1, w2, out = sys.argv[1:5]
N_SEEN = int(sys.argv[5]) if len(sys.argv) > 5 else 3000
N_UNSEEN = int(sys.argv[6]) if len(sys.argv) > 6 else 1500
SEED = int(sys.argv[7]) if len(sys.argv) > 7 else 20261125
PER_FILE = 250

spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
SMALL = {"tok_type": np.int8, "ids": np.int16, "a_type": np.int16, "a_src": np.int16, "a_tgt": np.int16}


def open_window(rdir):
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
    return R, st


def runs_of(R, a0, a1):
    """[(run_id, abs_first, abs_end)] of the samples a0..a1-1 (runs are contiguous: take_samples never splits one)."""
    ab = np.arange(a0, a1, dtype=np.int64)
    run = np.asarray(R.meta["run"][ab % R.cs]).astype(np.int64)
    cut = np.flatnonzero(run[1:] != run[:-1]) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(run)]])
    return [(int(run[s]), a0 + int(s), a0 + int(e)) for s, e in zip(starts, ends)]


def dump(R, sel, tag, extra):
    t0 = time.time()
    for fi in range(0, len(sel), PER_FILE):
        arrs = {}
        for ri, (rid, a, e) in enumerate(sel[fi:fi + PER_FILE], start=fi):
            ab = np.arange(a, e, dtype=np.int64)
            b = R._gather(ab % R.cs)
            for k, v in b.items():
                arrs[f"r{ri}.{k}"] = v.astype(SMALL[k]) if k in SMALL else v
            arrs[f"r{ri}.abs"] = ab
            arrs[f"r{ri}.run_id"] = np.int64(rid)
        np.savez_compressed(os.path.join(out, f"{tag}_{fi // PER_FILE:03d}.npz"), **arrs)
        print(f"{tag} file {fi // PER_FILE}: runs {fi}..{min(len(sel), fi + PER_FILE) - 1} ({time.time() - t0:.0f} s)",
              flush=True)
    return {"runs": len(sel), "samples": int(sum(e - a for _, a, e in sel)), **extra}


os.makedirs(out, exist_ok=True)
rng = np.random.default_rng(SEED)
R1, st1 = open_window(w1)
t1, h1 = st1["scalars"]["s_tail"], st1["scalars"]["s_head"]
seen_all = runs_of(R1, t1, h1)[1:]          # oldest run may have lost samples to eviction
seen = [seen_all[i] for i in sorted(rng.choice(len(seen_all), min(N_SEEN, len(seen_all)), replace=False))]
info = {"w1": w1, "w1_tail": t1, "w1_head": h1, "w1_extra": st1.get("extra"), "seed": SEED}
info["seen"] = dump(R1, seen, "seen", {"pool": len(seen_all)})
del R1
R2, st2 = open_window(w2)
t2, h2 = st2["scalars"]["s_tail"], st2["scalars"]["s_head"]
a0 = max(h1, t2)
cand = runs_of(R2, a0, h2)
if a0 == h1 and cand and cand[0][1] == h1:
    pass
cand = [r for r in cand if r[1] >= h1][1:]  # first run after h1 may be a run that straddled the save; drop it
unseen = cand[:N_UNSEEN]
info.update({"w2": w2, "w2_tail": t2, "w2_head": h2, "w2_extra": st2.get("extra")})
info["unseen"] = dump(R2, unseen, "unseen", {"pool": len(cand)})
with open(os.path.join(out, "info.json"), "w") as fh:
    json.dump(info, fh, default=str)
print(json.dumps(info, default=str), flush=True)
