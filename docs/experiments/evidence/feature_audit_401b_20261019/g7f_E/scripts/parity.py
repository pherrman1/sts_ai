"""Step 1 parity: deployed artifact on the g7f_E validation fold vs runs/g7f_E/train.json val_best.
usage: parity.py ARTIFACT.txt MODEL.pt VAL.npz TRAIN.json OUT.json"""
import sys, json, time, hashlib, numpy as np, torch
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g7f_model as G
torch.set_num_threads(1)
art, ckpt, valp, trainj, out = sys.argv[1:6]
t0 = time.time()
z = np.load(valp)
m = G.Model(art, ckpt)
nedge = z["r_nedge"]; e_ptr = np.concatenate([[0], np.cumsum(nedge, dtype=np.int64)])
eroot = np.repeat(np.arange(len(nedge)), nedge)
vsum = np.add.reduceat(z["e_vis"], e_ptr[:-1])
share = (z["e_vis"] / np.maximum(vsum[eroot], 1)).astype(np.float32).astype(np.float64)
lg, val = m.forward(z["st_idx"], z["st_val"], z["st_ptr"], nedge, z["e_act"], z["e_tgt"])
ce, top = G.root_stats(lg, share, nedge)
rv = z["r_val"]; hv = ~np.isnan(rv)
rep = json.load(open(trainj))
res = {"artifact_sha256": hashlib.sha256(open(art, "rb").read()).hexdigest(),
       "roots": int(len(nedge)), "edges": int(len(lg)), "ce": float(ce.mean()), "top1": float(top.mean()),
       "value_mse": float(np.mean((val[hv] - rv[hv]) ** 2)), "value_var": float(np.var(rv[hv])), "value_rows": int(hv.sum()),
       "train_json_val_best": rep["val_best"], "best_epoch": rep["best_epoch"]}
res["ce_rel_diff"] = abs(res["ce"] - rep["val_best"]["ce"]) / rep["val_best"]["ce"]
res["top1_abs_diff"] = abs(res["top1"] - rep["val_best"]["top1"])
# Cross-check vs the torch checkpoint through arch_dev.Net on a 20k-root sample (logit max abs diff).
try:
    import argparse
    sys.path.insert(0, sys.argv[6]) if len(sys.argv) > 6 else None
    import arch_dev as AD
    a = argparse.Namespace(**m.ck["args"]); net = AD.Net(a); net.load_state_dict(m.ck["state"]); net.eval()
    k = 20000
    sl = slice(0, z["st_ptr"][k]); el = slice(0, e_ptr[k])
    st_idx = z["st_idx"][sl].astype(np.int64); st_val = z["st_val"][sl]
    ss, as_, ts = (np.array(x, np.float32) for x in m.ck["scales"])
    enc, mon, blk = G.derived(st_idx, st_val, z["st_ptr"][:k + 1], k)
    er = eroot[el]; tgt = z["e_tgt"][el].astype(np.int64); tv = np.zeros((len(er), G.NT), np.float32)
    has = np.flatnonzero(tgt >= 0); tv[has] = blk[er[has][:, None], tgt[has][:, None] * G.NT + np.arange(G.NT)]
    card = z["e_act"][el][:, 4].astype(np.int64) + 1; card[(card < 0) | (card >= G.NCARD)] = 0
    T = torch.from_numpy
    b = dict(idx=T(st_idx), off=T(z["st_ptr"][:k].astype(np.int64)), w=T(st_val * ss[st_idx]),
             act=T(z["e_act"][el] * as_), card=T(card), tv=T(tv * ts), eroot=T(er.astype(np.int64)), nroot=k,
             enc=T(enc[:k]), mon=T(mon[:k]))
    with torch.no_grad():
        tl, tvv = net(b)
    res["torch_ckpt_max_abs_logit_diff_20k"] = float(np.abs(tl.numpy() - lg[el]).max())
    res["torch_ckpt_max_abs_value_diff_20k"] = float(np.abs(tvv.numpy() - val[:k]).max())
except Exception as ex:  # report, do not hide
    res["torch_ckpt_check_error"] = repr(ex)
res["seconds"] = time.time() - t0
json.dump(res, open(out, "w"), indent=1); print(json.dumps(res, indent=1))
