"""Test B head probe (2026-11-25): does an outcome head trained on h10 EMA targets generalize better to unseen runs
than one trained on the live h20 targets? Frozen checkpoint trunk; features c (the input of net.outcome) computed
once per sample (streamed, per run); then fresh outcome heads (same init) trained on SEEN train runs with h20 vs
h10 targets (h10 = exact per-run remix of the stored h20 targets, see remix()). Eval per epoch on held-out SEEN
runs and on UNSEEN runs: CE vs the final outcome, CE vs h20 / h10 targets, AUC and Brier of P(win) (class 0).
Also arm *_warm: start from the checkpoint's own outcome head. Low RAM: features are float16, ~0.3 GB.
usage: nice -n 19 ionice -c3 python3 -E -P head_probe.py REPO CKPT SLICE_DIR OUT_JSON [THREADS=2] [EPOCHS=12]
"""
import glob
import importlib.util
import json
import os
import sys
import time

import numpy as np
import torch

repo, ckpt_path, sdir, out_json = sys.argv[1:5]
THREADS = int(sys.argv[5]) if len(sys.argv) > 5 else 2
EPOCHS = int(sys.argv[6]) if len(sys.argv) > 6 else 12
torch.set_num_threads(THREADS)
L20, L10 = 0.5 ** (1 / 20), 0.5 ** (1 / 10)
INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}
spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netload  # noqa: E402


def remix(T, final, l_old, l_new):
    M, C = T.shape
    T = T.astype(np.float64)
    nxt = np.zeros(C); nxt[int(final)] = 1.0
    nxt_new = nxt.copy()
    out = np.zeros_like(T); neg = np.zeros(M)
    for m in range(M - 1, -1, -1):
        D = (T[m] - l_old * nxt) / (1 - l_old)
        neg[m] = -D[D < 0].sum()
        out[m] = (1 - l_new) * D + l_new * nxt_new
        nxt, nxt_new = T[m], out[m]
    out = np.clip(out, 0, None)
    out /= out.sum(1, keepdims=True)
    return out.astype(np.float32), neg


ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
net, _, _, W, A = netload.build(sp, ck)
net.eval()
feat = {}
net.outcome.register_forward_hook(lambda m, i, o: feat.__setitem__("c", i[0].detach().float()))


def tens(run):
    b = {}
    for k, v in run.items():
        if k in ("abs", "run_id"):
            continue
        t = torch.from_numpy(np.ascontiguousarray(v.astype(np.int64) if k in INT else v))
        b[k] = t.float() if t.dtype == torch.float16 else t
    return b


def process(pattern):
    """-> dict of arrays over all samples of the files: c (f16), y (final class), t20, t10, run index, own-head logp."""
    C_, Y, T20, T10, RUN, OWN, NEG = [], [], [], [], [], [], []
    ri = 0
    t0 = time.time()
    for fn in sorted(glob.glob(os.path.join(sdir, pattern))):
        z = np.load(fn)
        names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
        for nm in names:
            run = {k.split(".", 1)[1]: z[k] for k in z.files if k.startswith(nm + ".")}
            with torch.no_grad():
                o = net(tens(run))[1].float()
            C_.append(feat["c"].numpy().astype(np.float16))
            OWN.append(torch.log_softmax(o, -1).numpy().astype(np.float32))
            y = run["outcome"].astype(np.int64)
            t20 = run["soft_outcome"].astype(np.float32)
            t10, neg = remix(t20, y[-1], L20, L10)
            Y.append(y); T20.append(t20); T10.append(t10); NEG.append(neg)
            RUN.append(np.full(len(y), ri)); ri += 1
            del run
        print(f"{fn}: {ri} runs ({time.time() - t0:.0f} s)", flush=True)
    cat = lambda L: np.concatenate(L)
    return {"c": cat(C_), "y": cat(Y), "t20": cat(T20), "t10": cat(T10), "run": cat(RUN), "own": cat(OWN),
            "neg": cat(NEG), "runs": ri}


seen, unseen = process("seen_*.npz"), process("unseen_*.npz")
rng = np.random.default_rng(20261125)
ev_runs = set(rng.permutation(seen["runs"])[:300].tolist())
is_ev = np.isin(seen["run"], list(ev_runs))
tr = np.flatnonzero(~is_ev); ev = np.flatnonzero(is_ev)
diag = {"seen_runs": seen["runs"], "unseen_runs": unseen["runs"], "train_samples": int(len(tr)),
        "eval_seen_samples": int(len(ev)), "unseen_samples": int(len(unseen["y"])),
        "neg_D_mass": {"mean": float(seen["neg"].mean()), "p99": float(np.quantile(seen["neg"], .99)),
                       "max": float(seen["neg"].max())},
        "y_class_range": [int(seen["y"].min()), int(seen["y"].max())]}
print(json.dumps(diag), flush=True)


def metrics(logp, y, t20, t10):
    lp = torch.as_tensor(logp)
    y_ = torch.as_tensor(y).clamp(0, lp.shape[-1] - 1)
    pw = lp[:, 0].exp().numpy(); win = (y == 0)
    r = np.empty(len(pw)); r[np.argsort(pw)] = np.arange(1, len(pw) + 1)
    npos = win.sum()
    return {"ce_final": float(-lp.gather(1, y_[:, None]).mean()),
            "ce_h20": float(-(torch.as_tensor(t20) * lp).sum(-1).mean()),
            "ce_h10": float(-(torch.as_tensor(t10) * lp).sum(-1).mean()),
            "auc_win": float((r[win].sum() - npos * (npos + 1) / 2) / max(1, npos * (len(pw) - npos))),
            "brier_win": float(np.mean((pw - win) ** 2)), "pwin_mean": float(pw.mean()), "win_rate": float(win.mean())}


def sets(fn):
    out = {}
    for name, D, idx in (("seen", seen, ev), ("unseen", unseen, np.arange(len(unseen["y"])))):
        out[name] = metrics(fn(D, idx), D["y"][idx], D["t20"][idx], D["t10"][idx])
    out["gap_ce_final"] = out["unseen"]["ce_final"] - out["seen"]["ce_final"]
    return out


res = {"diag": diag, "ckpt_head": sets(lambda D, idx: D["own"][idx]), "arms": {}}
print("ckpt_head", json.dumps(res["ckpt_head"]), flush=True)
d = seen["c"].shape[1]
for warm in (False, True):
    for tgt in ("t20", "t10"):
        arm = tgt.replace("t", "h") + ("_warm" if warm else "")
        torch.manual_seed(0)
        head = sp.amber_net.mlp(d, d, net.outcome[-1].out_features)
        if warm:
            head.load_state_dict(net.outcome.state_dict())
        opt = torch.optim.AdamW(head.parameters(), lr=3e-4 if warm else 1e-3, weight_decay=1e-4)

        def predict(D, idx):
            with torch.no_grad():
                return torch.log_softmax(head(torch.as_tensor(D["c"][idx]).float()), -1).numpy()
        curve = [{"epoch": 0, **sets(predict)}]
        g = np.random.default_rng(1)
        for ep in range(1, EPOCHS + 1):
            perm = tr[g.permutation(len(tr))]
            for i in range(0, len(perm) - 1023, 1024):
                j = perm[i:i + 1024]
                lp = torch.log_softmax(head(torch.as_tensor(seen["c"][j]).float()), -1)
                loss = -(torch.as_tensor(seen[tgt][j]) * lp).sum(-1).mean()
                opt.zero_grad(); loss.backward(); opt.step()
            curve.append({"epoch": ep, **sets(predict)})
            u = curve[-1]
            print(arm, ep, f"unseen ce_final {u['unseen']['ce_final']:.4f} auc {u['unseen']['auc_win']:.4f} "
                  f"gap {u['gap_ce_final']:.4f}", flush=True)
        res["arms"][arm] = curve
        json.dump(res, open(out_json, "w"), indent=1)
print("done", flush=True)
