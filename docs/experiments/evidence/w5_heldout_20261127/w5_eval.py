"""W5 (2026-11-27): did the 1.2M net still learn on unseen data between 11-25 and 11-27?
Evaluates frozen checkpoints on held-out run slices (no seeds, no GPU, no gameplay).
usage: nice -n 19 ionice -c3 OMP_NUM_THREADS=2 python3 -E w5_eval.py REPO OUT_DIR [THREADS=2]
Stage 1 (this file, default): per-sample metrics of every ckpt on every slice -> OUT_DIR/persample_<slice>.npz.
The per-sample arrays are aggregated with run-level bootstrap CIs by w5_summ.py.
Memory guard: aborts if MemAvailable < 1.5 GB or swap grows by more than 1.5 GB over the value at start.
"""
import glob
import importlib.util
import json
import os
import sys
import time

import numpy as np
import torch

repo, out_dir = sys.argv[1:3]
THREADS = int(sys.argv[3]) if len(sys.argv) > 3 else 2
torch.set_num_threads(THREADS)
torch.set_num_interop_threads(1)
S1 = "/home/philippherrmann/Documents/sts/stage1"
BK = S1 + "/backup_1p2m_20261127"
CK = {1594969: BK + "/ckpts/ckpt_1594969.pt", 1635474: BK + "/ckpts/ckpt_1635474.pt",
      1678542: BK + "/ckpts/ckpt_1678542.pt", 1679639: BK + "/ckpts/ckpt_1679639.pt", 1717027: BK + "/ckpts/ckpt_1717027.pt",
      1755240: BK + "/ckpts/ckpt_1755240.pt", 1782264: S1 + "/amber_scratch/ckpt_1782264.pt",
      1803647: S1 + "/amber_scratch/ckpt_1803647.pt", 1805354: BK + "/ckpts/ckpt_1805354.pt", 1816571: BK + "/ckpts/ckpt_1816571.pt",
      1828683: BK + "/ckpts/ckpt_1828683.pt"}
SLICES = {"heads_unseen": BK + "/heads_unseen/unseen_*.npz", "testB_unseen": BK + "/testB_unseen/unseen_*.npz"}
INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}
NEED = ("tok_type", "ids", "f", "mask", "a_type", "a_src", "a_tgt", "a_f", "a_mask")

spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
am = sp.amber_net


def meminfo():
    m = {}
    for l in open("/proc/meminfo"):
        k, v = l.split(":")
        m[k] = int(v.split()[0]) // 1024
    return m["MemAvailable"], m["SwapTotal"] - m["SwapFree"]


AV0, SW0 = meminfo()


def guard():
    av, sw = meminfo()
    if av < 1500 or sw > SW0 + 1500:
        print(f"MEMGUARD abort: avail {av} MB, swap {sw} MB (start {SW0} MB)", flush=True)
        sys.exit(3)


nets, load_info = {}, {}
for step, path in CK.items():
    ck = torch.load(path, map_location="cpu", weights_only=False)
    a = ck["args"] if isinstance(ck["args"], dict) else vars(ck["args"])
    d, layers = am.SIZES.get(a["net"]) or tuple(int(x) for x in a["net"].split("x")[:2])
    net = sp.net_like_ckpt(d, layers, 56, a.get("w_soft_policy", 0) > 0, a)
    r = net.load_state_dict(ck["net"], strict=False)
    am.input_options_from_ckpt(net, ck)
    net.sdpa = True
    net.eval()
    load_info[step] = {"path": path, "net": a["net"], "params": sum(p.numel() for p in net.parameters()),
                       "missing": list(r.missing_keys), "unexpected": list(r.unexpected_keys),
                       "counter_step": int((ck.get("counters") or {}).get("step", -1))}
    print("load", step, json.dumps(load_info[step]), flush=True)
    if r.missing_keys or r.unexpected_keys:
        sys.exit(f"ckpt {step}: missing/unexpected keys")
    nets[step] = net
    del ck
json.dump(load_info, open(os.path.join(out_dir, "load_info.json"), "w"), indent=1)
STEPS = list(CK)


def tens(run):
    return {k: (torch.from_numpy(np.ascontiguousarray(run[k].astype(np.int64))) if k in INT
                else torch.from_numpy(np.ascontiguousarray(run[k])).float() if run[k].dtype == np.float16
                else torch.from_numpy(np.ascontiguousarray(run[k]))) for k in NEED}


for sname, pat in SLICES.items():
    t0 = time.time()
    st = {k: [] for k in ("run", "combat", "has_policy", "win", "floor", "n_legal")}
    per = {s: {k: [] for k in ("kl", "top1", "ce_out", "pwin", "ce_hp", "hpf_se", "hpf_n")} for s in STEPS}
    ri = 0
    for fn in sorted(glob.glob(pat)):
        guard()
        z = np.load(fn)
        names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
        for nm in names:
            run = {k.split(".", 1)[1]: z[k] for k in z.files if k.startswith(nm + ".")}
            n = len(run["outcome"])
            b = tens(run)
            amask = b["a_mask"]
            pol = torch.from_numpy(run["policy"].astype(np.float32))
            has = run["has_policy"].astype(bool)
            y = torch.from_numpy(run["outcome"].astype(np.int64))
            hp_end = torch.from_numpy(run["hp_end"].astype(np.int64))
            lab = torch.from_numpy(run["hp_floor"].astype(np.int64))
            m = (lab >= 0).float()
            t = lab.float().clamp(0, 255) / 255.0
            plogp = torch.where(pol > 0, pol * torch.log(pol.clamp(min=1e-30)), torch.zeros_like(pol)).sum(-1)
            targ = pol.masked_fill(~amask, -1).argmax(-1)
            st["run"].append(np.full(n, ri, np.int32)); st["combat"].append(run["combat"].astype(bool))
            st["has_policy"].append(has); st["win"].append(run["outcome"] == 0)
            st["floor"].append(run["floor"].astype(np.int16)); st["n_legal"].append(run["a_mask"].sum(1))
            for s in STEPS:
                with torch.no_grad():
                    logits, outcome, hp, hpf, *_ = nets[s](b)
                lp = torch.log_softmax(logits.float().masked_fill(~amask, -1e4), -1)
                kl = plogp - (pol * lp).sum(-1)
                top1 = (lp.argmax(-1) == targ)
                lo = torch.log_softmax(outcome.float(), -1)
                C = lo.shape[-1]
                lh = torch.log_softmax(hp.float(), -1)
                P = per[s]
                P["kl"].append(kl.numpy().astype(np.float32)); P["top1"].append(top1.numpy())
                P["ce_out"].append((-lo.gather(1, y.clamp(0, C - 1)[:, None])[:, 0]).numpy().astype(np.float32))
                P["pwin"].append(lo[:, 0].exp().numpy().astype(np.float32))
                P["ce_hp"].append((-lh.gather(1, hp_end.clamp(0, lh.shape[-1] - 1)[:, None])[:, 0]).numpy()
                                  .astype(np.float32))
                P["hpf_se"].append(((((hpf.float() - t) ** 2) * m).sum(-1)).numpy().astype(np.float32))
                P["hpf_n"].append(m.sum(-1).numpy().astype(np.int16))
            ri += 1
            del run, b
        print(f"{sname} {os.path.basename(fn)}: {ri} runs ({time.time() - t0:.0f} s)", flush=True)
    out = {k: np.concatenate(v) for k, v in st.items()}
    for s in STEPS:
        for k, v in per[s].items():
            out[f"{s}.{k}"] = np.concatenate(v)
    np.savez(os.path.join(out_dir, f"persample_{sname}.npz"), **out)
    print("saved", sname, ri, "runs", len(out["run"]), "samples", flush=True)
print("done", flush=True)
