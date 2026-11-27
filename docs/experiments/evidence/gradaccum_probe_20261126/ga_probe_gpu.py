"""Proposal #3 offline probe (2026-11-26): gradient accumulation x LR at equal training samples.
Frozen ckpt 1635474 (net + AdamW state), fine-tune on seen runs (Test B slices), evaluate the live loss on later
unseen runs. Every arm sees the identical micro-batch sequence; arms differ only in micro-batches per optimizer step
(accum) and lr. Read-only on the repo; CPU only.
usage: CUDA_VISIBLE_DEVICES= nice -n 19 python3 -E -P ga_probe.py REPO CKPT SLICE_DIR OUT_JSON SAMPLES THREADS ARMS
  ARMS e.g. "A:1:3e-5,B:4:6e-5,C:4:1.2e-4,D:1:6e-5" (name:accum:lr)
"""
import copy, glob, importlib.util, json, os, sys, time
import numpy as np
import torch

repo, ckpt_path, sdir, out_json = sys.argv[1:5]
SAMPLES, THREADS = int(sys.argv[5]), int(sys.argv[6])
ARMS = [(a.split(":")[0], int(a.split(":")[1]), float(a.split(":")[2])) for a in sys.argv[7].split(",")]
ECHUNK = int(os.environ.get("ECHUNK", "128"))
MB, EVAL_RUNS = 1024, int(os.environ.get("EVAL_RUNS", "300"))
torch.set_num_threads(THREADS)
DEV = torch.device(os.environ.get("DEV", "cuda"))
torch.manual_seed(0)
spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netload  # noqa: E402

INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}
TOKAX = ("mask", "tok_type", "ids", "f")
ACTAX = ("a_type", "a_src", "a_tgt", "a_f", "a_mask", "policy")
ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
net0, _, _, W, A = netload.build(sp, ck)
net0 = net0.to(DEV)
am = sp.amber_net


def make_opt(net):
    named = list(net.named_parameters())
    main = [p for n, p in named if not sp.extra_param(n)]
    aux = [p for n, p in named if n.startswith("aux_fight.")]
    en = [p for n, p in named if n in ("enemy_bias", "enemy_gate")]
    fix = [{"params": [p]} for n, p in named if n in getattr(am, "INPUT_FIX_PARAMS", ())]
    opt = torch.optim.AdamW([{"params": main}] + ([{"params": aux}] if aux else [])
                            + ([{"params": en, "lr_scale": A("enemy_lr_scale", 0.01), "weight_decay": 0.0}] if en else [])
                            + fix, lr=1e-4, weight_decay=A("weight_decay", 1e-4))
    sp.load_opt_state(opt, ck["opt"])
    for st in opt.state.values():
        for k, v in list(st.items()):
            if torch.is_tensor(v) and v.dim() > 0:
                st[k] = v.to(DEV)
    return opt


def load_runs(fn, keep=None):
    z = np.load(fn)
    names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
    runs = []
    for nm in names:
        if keep is not None and nm not in keep:
            continue
        runs.append({k.split(".", 1)[1]: z[k] for k in z.files if k.startswith(nm + ".") and not k.endswith((".abs", ".run_id"))})
    return runs


def collate(rows_list):
    """rows_list: list of (run dict, row indices); pads token / action axes to the max."""
    T = max(r["mask"].shape[1] for r, _ in rows_list); K = max(r["a_mask"].shape[1] for r, _ in rows_list)
    out = {}
    for k in rows_list[0][0]:
        parts = []
        for r, ix in rows_list:
            v = r[k][ix]
            if k in TOKAX and v.shape[1] < T:
                v = np.pad(v, [(0, 0), (0, T - v.shape[1])] + [(0, 0)] * (v.ndim - 2))
            if k in ACTAX and v.shape[1] < K:
                v = np.pad(v, [(0, 0), (0, K - v.shape[1])] + [(0, 0)] * (v.ndim - 2))
            parts.append(v)
        v = np.concatenate(parts)
        t = torch.from_numpy(np.ascontiguousarray(v.astype(np.int64) if k in INT else v))
        out[k] = (t.float() if t.dtype == torch.float16 else t).to(DEV, non_blocking=True)
    return out


F = torch.nn.functional


def denoms(d, ix):
    """Data-only denominators of selfplay.losses' terms over the rows ix of batch dict d (numpy)."""
    aux = np.asarray(d["aux_mask"][ix]).astype(np.int64)
    bits = sum(((aux >> j) & 1).sum() for j in range(sp.AUX_SLOTS))
    return {"pol": max(1, int(d["has_policy"][ix].astype(bool).sum())), "rows": len(ix),
            "hpf": max(1, int((d["hp_floor_target"][ix] >= 0).sum())), "aux": max(1, int(bits))}


def loss_num(net, b, D):
    """selfplay.losses (as configured: EMA outcome / HP / per-floor targets, soft policy, aux; no kickstart) with each
    term's numerator divided by the given batch-level denominators D: chunk results add up to the whole batch's loss."""
    logits, outcome, hp, hpf, *soft = net(b)
    logp = torch.log_softmax(logits.float().masked_fill(~b["a_mask"], -1e4), -1)
    has = b["has_policy"].bool()
    p = {"policy": ((-(b["policy"] * logp).sum(-1)) * has).sum() / D["pol"]}
    slogp = torch.log_softmax(soft[0].float().masked_fill(~b["a_mask"], -1e4), -1)
    p["soft_policy"] = ((-(sp.soft_policy_target(b["policy"], b["a_mask"]) * slogp).sum(-1)) * has).sum() / D["pol"]
    p["outcome_ema"] = -(b["soft_outcome"] * torch.log_softmax(outcome.float(), -1)).sum() / D["rows"]
    p["outcome"] = F.cross_entropy(outcome.float(), b["outcome"].long(), reduction="sum") / D["rows"]
    p["hp_ema"] = -(b["hp_target"] * torch.log_softmax(hp.float(), -1)).sum() / D["rows"]
    m = (b["hp_floor_target"] >= 0).float()
    p["hp_floor_ema"] = (((hpf.float() - b["hp_floor_target"].float().clamp(0, 1)) ** 2) * m).sum() / D["hpf"]
    B = net.aux_out.shape[0]
    lg = net.aux_out.float().view(B, sp.AUX_SLOTS, 2); t = b["aux_target"].float().view(B, sp.AUX_SLOTS, 2) / 255.0
    am_ = ((b["aux_mask"].long()[:, None] >> torch.arange(sp.AUX_SLOTS, device=DEV)) & 1).float()
    p["aux"] = (F.binary_cross_entropy_with_logits(lg, t, reduction="none").sum(-1) * am_).sum() / D["aux"]
    total = (W["w_policy"] * p["policy"] + W["w_outcome"] * p["outcome_ema"] + W["w_hp"] * p["hp_ema"]
             + W["w_soft_policy"] * p["soft_policy"] + W["w_hp_floor"] * p["hp_floor_ema"] + W["w_aux"] * p["aux"])
    return total, p


def loss(net, b):
    return sp.losses(net, b, W["w_policy"], W["w_outcome"], W["w_hp"], W["w_hp_floor"], W["w_soft_policy"], W["w_aux"])


# --- fixed unseen eval set: EVAL_RUNS whole runs drawn with a fixed seed
ufiles = sorted(glob.glob(os.path.join(sdir, "unseen_*.npz")))
allu = [(fi, nm) for fi, fn in enumerate(ufiles) for nm in sorted({k.split(".")[0] for k in np.load(fn).files})]
pick = np.random.default_rng(20261126).choice(len(allu), min(EVAL_RUNS, len(allu)), replace=False)
want = {}
for j in pick:
    fi, nm = allu[j]; want.setdefault(fi, set()).add(nm)
EVAL = [r for fi in sorted(want) for r in load_runs(ufiles[fi], want[fi])]
print(f"# eval: {len(EVAL)} unseen runs, {sum(len(r['outcome']) for r in EVAL)} samples", flush=True)


def evaluate(net):
    per = []   # train mode: the soft-policy and aux heads exist only there (no dropout in AmberNet)
    with torch.no_grad():
        for r in EVAL:
            n = len(r["outcome"]); acc = {}; D = denoms(r, np.arange(n))
            for c in range(0, n, ECHUNK):   # row chunks (RAM); exact: batch-level denominators
                tot, parts = loss_num(net, collate([(r, np.arange(c, min(n, c + ECHUNK)))]), D)
                for k, v in {"total": tot, **parts}.items():
                    acc[k] = acc.get(k, 0.0) + float(v)
            per.append({"n": n, **acc})

    n = np.array([p["n"] for p in per], float)
    agg = {k: float(np.dot(n, [p[k] for p in per]) / n.sum()) for k in per[0] if k != "n"}
    return agg, [p["total"] for p in per], n.tolist()


# --- identical batch sequence for every arm: prebuilt uniform batches of 1024 rows (build_batches.py), each run as
# CHUNK-row chunks (RAM) whose gradients add up to the 1024-row mean; accum = 1024-row batches per optimizer step
BDIR = os.environ["BATCH_DIR"]; CHUNK = int(os.environ.get("CHUNK", "256"))
bfiles = sorted(glob.glob(os.path.join(BDIR, "b*.npz")))
n_mb = min(SAMPLES // MB, len(bfiles))
lcm = int(np.lcm.reduce([a for _, a, _ in ARMS]))
n_mb -= n_mb % lcm
print(f"# {n_mb} batches of {MB} = {n_mb * MB} samples per arm (chunks of {CHUNK}); arms {ARMS}", flush=True)


def batch_chunks(i):
    z = np.load(bfiles[i]); d = {k: z[k] for k in z.files}; D = denoms(d, np.arange(MB))
    return [(collate([(d, np.arange(c, min(MB, c + CHUNK)))]), D) for c in range(0, MB, CHUNK)]


with torch.no_grad():
    z = np.load(bfiles[0]); d = {k: z[k][:256] for k in z.files}; ix = np.arange(256)
    ref, rp = loss(net0, collate([(d, ix)]))
    D = denoms(d, ix); mine = sum(float(loss_num(net0, collate([(d, ix[c:c + 64])]), D)[0]) for c in range(0, 256, 64))
    print(f"# check: sp.losses {float(ref):.6f} chunked exact {mine:.6f}", flush=True)
    assert abs(float(ref) - mine) < 1e-3 * abs(float(ref)), "chunked loss differs from selfplay.losses"
t0 = time.time()
base_agg, base_per, eval_n = evaluate(net0)
print("# base", json.dumps(base_agg), f"({time.time() - t0:.0f} s)", flush=True)
res = {"ckpt": ckpt_path, "samples": n_mb * MB, "micro_batch": MB, "W": W, "eval_n": eval_n,
       "base": base_agg, "base_per": base_per, "arms": {}}

for name, accum, lr in ARMS:
    net = copy.deepcopy(net0); opt = make_opt(net)
    for g in opt.param_groups:
        g["lr"] = lr * g.get("lr_scale", 1.0)
    done, k, steps, gns, tr_loss, t1 = 0, 0, 0, [], [], time.time()
    opt.zero_grad(set_to_none=True)
    mid = None
    for i in range(n_mb):
        tot_b = 0.0
        for b, D in batch_chunks(i):
            tot, _ = loss_num(net, b, D)
            (tot / accum).backward()
            tot_b += float(tot)
        tr_loss.append(tot_b); done += 1; k += 1
        if k == accum:
            gns.append(float(torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)))
            opt.step(); opt.zero_grad(set_to_none=True); k = 0; steps += 1
        if done == n_mb // 2 and mid is None:
            mid = evaluate(net)[0]
            print(f"# {name} mid {json.dumps(mid)}", flush=True)
        if done % 10 == 0:
            print(f"{name} mb {done}/{n_mb} steps {steps} train_loss {np.mean(tr_loss[-10:]):.4f} "
                  f"gn {np.mean(gns[-5:]) if gns else 0:.2f} ({time.time() - t1:.0f} s)", flush=True)
    agg, per, _ = evaluate(net)
    res["arms"][name] = {"accum": accum, "lr": lr, "steps": steps, "mid": mid, "end": agg, "per": per,
                         "grad_norm_mean": float(np.mean(gns)), "train_loss_first100": float(np.mean(tr_loss[:100])),
                         "train_loss_last100": float(np.mean(tr_loss[-100:])), "sec": time.time() - t1}
    print(f"# {name} end {json.dumps(agg)} gn {np.mean(gns):.2f} ({time.time() - t1:.0f} s)", flush=True)
    json.dump(res, open(out_json, "w"), indent=1)
    del net, opt
print("done", flush=True)
