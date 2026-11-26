"""Read-only: draws WHOLE runs (all their samples, in sample order) from saved selfplay.py replay windows (mmap)
and writes them as gathered rows (Replay._gather, unpacked layout), one gather per run, many runs per .npz file.
usage: python3 slice_heads.py REPO WIN_DIR H1 OUT_DIR [TARGET_SAMPLES=65536] [SEED=20261126]
(2026-11-26 heads thread: one window; SEEN = whole runs ending before H1, UNSEEN = whole runs starting at or after H1)
"""
import importlib.util
import json
import os
import sys
import time

import numpy as np

repo, w1, H1, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
TARGET = int(sys.argv[5]) if len(sys.argv) > 5 else 65536
SEED = int(sys.argv[6]) if len(sys.argv) > 6 else 20261126
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
    if a1 <= a0:   # empty range (W2 == W1 in phase 1)
        return []
    ab = np.arange(a0, a1, dtype=np.int64)
    # window has no meta.run: hp_ref (sample -> absolute run index of the replay run ring) identifies the run
    run = np.asarray((R.meta["run"] if "run" in R.meta else R.hp_ref)[ab % R.cs]).astype(np.int64)
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
        print(f"{tag} file {fi // PER_FILE}: runs {fi}..{min(len(sel), fi + PER_FILE) - 1} ({time.time() - t0:.0f} s)", flush=True)
    return {"runs": len(sel), "samples": int(sum(e - a for _, a, e in sel)), **extra}



os.makedirs(out, exist_ok=True)
rng = np.random.default_rng(SEED)
R, st = open_window(w1)
t, h = st["scalars"]["s_tail"], st["scalars"]["s_head"]
allr = runs_of(R, t, h)[1:-1]   # drop the partial first run (tail) and the last (may continue past the head)
seen_pool = [r for r in allr if r[2] <= H1]
unseen_pool = [r for r in allr if r[1] >= H1]
def pick(pool):
    order = rng.permutation(len(pool)); sel = []; n = 0
    for i in order:
        sel.append(pool[i]); n += pool[i][2] - pool[i][1]
        if n >= TARGET: break
    return sorted(sel, key=lambda r: r[1])
seen, unseen = pick(seen_pool), pick(unseen_pool)
info = {"window": w1, "tail": t, "head": h, "H1": H1, "extra": st.get("extra"), "seed": SEED, "target_samples": TARGET}
info["seen"] = dump(R, seen, "seen", {"pool_runs": len(seen_pool)})
info["unseen"] = dump(R, unseen, "unseen", {"pool_runs": len(unseen_pool)})
with open(os.path.join(out, "info.json"), "w") as fh:
    json.dump(info, fh, indent=1)
print(json.dumps(info), flush=True)
