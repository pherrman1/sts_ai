import sys, struct, zipfile, numpy as np, torch
sys.path.insert(0, "/home/philippherrmann/Documents/sts/gen7-gpu/data"); import silver_az_mlp as M
z = np.load("/home/philippherrmann/Documents/sts/gen7-gpu/data/pack-g7f.npz")
r_seed = z["r_seed"]; r_nedge = z["r_nedge"]; st_ptr = z["st_ptr"]; r_src = z["r_src"]
e_ptr = np.concatenate([[0], np.cumsum(r_nedge, dtype=np.int64)])
rng = np.random.default_rng(123)
test = np.flatnonzero(r_seed % 5 == M.TEST)
pick = np.sort(rng.choice(test, 4000, replace=False))
st_idx = z["st_idx"]; st_val = z["st_val"]; e_tgt = z["e_tgt"]
e_act = z["e_act"]
with open("roots.bin", "wb") as f:
    f.write(struct.pack("i", len(pick)))
    for r in pick:
        s = np.zeros(M.S, np.float32); sl = slice(st_ptr[r], st_ptr[r+1]); s[st_idx[sl].astype(np.int64)] = st_val[sl]
        e = slice(e_ptr[r], e_ptr[r+1])
        f.write(struct.pack("i", r_nedge[r])); f.write(s.tobytes()); f.write(e_act[e].astype(np.float32).tobytes())
        f.write(e_tgt[e].astype(np.int32).tobytes())
np.save("pick.npy", pick)
print("roots", len(pick), "edges", int(r_nedge[pick].sum()), "orig-share", float(np.mean(r_src[pick]==0)))
