"""Extract the g7f_E validation fold (r_seed % 5 == 3, as silver_az_mlp.Data / arch_dev.py) from pack-g7f.npz.
usage: cache_val.py PACK.npz OUT.npz"""
import sys, numpy as np
pack, out = sys.argv[1:3]
z = np.load(pack)
r_seed = z["r_seed"]; r_nedge = z["r_nedge"]; st_ptr = z["st_ptr"]
VAL = 3
roots = np.flatnonzero(r_seed % 5 == VAL)
e_ptr = np.concatenate([[0], np.cumsum(r_nedge, dtype=np.int64)])
def gather(ptr, roots):
    lens = ptr[roots + 1] - ptr[roots]
    pos = np.repeat(ptr[roots] - np.concatenate([[0], np.cumsum(lens)[:-1]]), lens) + np.arange(lens.sum())
    return pos, lens
spos, slen = gather(st_ptr, roots)
epos, elen = gather(e_ptr, roots)
d = dict(roots=roots, r_seed=r_seed[roots], r_src=z["r_src"][roots], r_val=z["r_val"][roots],
         r_nedge=r_nedge[roots], r_fight=z["r_fight"][roots], tags=z["tags"],
         st_idx=z["st_idx"][spos], st_val=z["st_val"][spos],
         st_ptr=np.concatenate([[0], np.cumsum(slen)]).astype(np.int64))
del spos
d.update(e_act=z["e_act"][epos], e_tgt=z["e_tgt"][epos], e_vis=z["e_vis"][epos])
np.savez(out, **d)
print("val roots", len(roots), "edges", int(elen.sum()), "nnz", int(slen.sum()))
