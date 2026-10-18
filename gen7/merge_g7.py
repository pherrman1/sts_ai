"""Gen-7 window: gen-6 pack + Act-4 pack (source g7a4).
Act-4 roots get r_seed := the fight's perturbation.sourceSeed so Data.fold = r_seed % 5 keeps
Shield + Spear and Heart of one source run (and both copies) in one fold; the generator seed is kept
in r_state_seed (-1 for gen-6 roots). Usage: merge_g7.py PACK_G6 PACK_A4 A4_CORPUS_DIR OUT"""
import glob, gzip, json, os, sys, numpy as np
g6p, a4p, corpus, out = sys.argv[1:5]
src = {}
for p in sorted(glob.glob(os.path.join(corpus, "**", "*.jsonl.gz"), recursive=True)):
    if not os.path.exists(p[:-len(".jsonl.gz")] + ".done"):
        continue
    with gzip.open(p, "rt") as f:
        for line in f:
            if '"kind":"fight"' in line:
                r = json.loads(line)
                k = (r["seed"], r["fight"]); s = r["perturbation"]["sourceSeed"]
                assert src.setdefault(k, s) == s
a = {k: v for k, v in np.load(g6p).items()}
b = {k: v for k, v in np.load(a4p).items()}
assert list(b["tags"]) == ["g7a4"] and "g7a4" not in list(a["tags"])
state_seed = b["r_seed"].copy()
b_src_seed = np.array([src[(int(s), int(f))] for s, f in zip(b["r_seed"], b["r_fight"])], np.int64)
assert ((111160000 <= b_src_seed) & (b_src_seed <= 111169999)).all()
m = {}
m["st_idx"] = np.concatenate([a["st_idx"], b["st_idx"]]); m["st_val"] = np.concatenate([a["st_val"], b["st_val"]])
m["st_ptr"] = np.concatenate([a["st_ptr"], b["st_ptr"][1:] + a["st_ptr"][-1]])
m["r_src"] = np.concatenate([a["r_src"], np.full(len(b["r_src"]), len(a["tags"]), np.int8)])
m["r_seed"] = np.concatenate([a["r_seed"], b_src_seed])
m["r_state_seed"] = np.concatenate([np.full(len(a["r_seed"]), -1, np.int64), state_seed])
for k in ("r_fight", "r_var", "r_val", "r_nedge", "e_act", "e_tgt", "e_vis"):
    m[k] = np.concatenate([a[k], b[k]])
m["tags"] = np.array(list(a["tags"]) + ["g7a4"])
np.savez(out, **m)
fold = b_src_seed % 5
print(json.dumps({"roots": int(len(m["r_seed"])), "edges": int(len(m["e_tgt"])),
                  "roots_by_source": {str(t): int((m["r_src"] == i).sum()) for i, t in enumerate(m["tags"])},
                  "g7a4_fold_roots": {int(f): int((fold == f).sum()) for f in range(5)},
                  "g7a4_source_runs": len(set(b_src_seed.tolist()))}))
