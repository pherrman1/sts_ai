"""Test 3 (heads thread, Philipp's go 2026-11-26 21:27 CET): what does the soft-policy head (live weight 8) do to the
trunk? Read-only, CPU, no seeds. Two parts on the checkpoint:
 (a) GRAD: per-head gradients of each weighted loss term on the shared parameters (everything but the heads' own
     MLPs), on NB batches of SEEN runs: norms, share of the summed squared norm, cosine of each head's gradient with
     the policy / outcome gradient. Answers: does w 8 dominate the shared gradient, and does it pull with or against
     the policy and outcome terms?
 (b) FT: continue training from the checkpoint with its optimizer state and LR, arms w_soft_policy = 8 (control),
     2 and 0, same batches in the same order, STEPS steps of ~1,024 samples (whole runs); held-out on UNSEEN runs every
     EVAL steps: policy CE, outcome CE (final + EMA), hp CE, policy argmax agreement with the checkpoint.
Pre-registered reading (before data): w 2 / 0 is "not worse" if policy CE and outcome CE on UNSEEN are each within
+0.2 % relative of w 8 at the end; "better" if either improves >= 0.5 % relative with the other not worse. A short
offline fine-tune cannot show long-run representation effects; a positive result would only justify a live A/B,
which is an Amber-fidelity decision for Philipp (the page gives no weight; 8 is KataGo's).
usage: python3 -I softpol_probe.py REPO CKPT SLICE_DIR OUT_JSON [STEPS=300] [EVAL=50] [NB=16] [THREADS=4] [EVAL_RUNS=300]"""
import copy, glob, importlib.util, json, os, sys, time
import numpy as np
import torch

repo, ckpt_path, sdir, out_json = sys.argv[1:5]
STEPS = int(sys.argv[5]) if len(sys.argv) > 5 else 300
EVAL = int(sys.argv[6]) if len(sys.argv) > 6 else 50
NB = int(sys.argv[7]) if len(sys.argv) > 7 else 16
torch.set_num_threads(int(sys.argv[8]) if len(sys.argv) > 8 else 4)
EVAL_RUNS = int(sys.argv[9]) if len(sys.argv) > 9 else 300
ARMS = [float(x) for x in os.environ.get("ARMS", "8,2,0").split(",")]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
import netload
ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}


def runs(pattern, limit):
    n = 0
    for fn in sorted(glob.glob(os.path.join(sdir, pattern))):
        z = np.load(fn)
        names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
        for nm in names:
            if n >= limit: return
            bt = {}
            for k in z.files:
                if k.startswith(nm + ".") and not k.endswith((".abs", ".run_id")):
                    key = k.split(".", 1)[1]; v = z[k]
                    t = torch.from_numpy(v.astype(np.int64) if key in INT else v)
                    bt[key] = t.float() if t.dtype == torch.float16 else t
            if "has_policy" not in bt:
                bt["has_policy"] = (bt["policy"].sum(-1) > 0).to(torch.uint8)
            n += 1
            yield bt


def steps_of(rs, target=int(os.environ.get("STEP_SAMPLES", "1024"))):
    """Groups whole runs into steps of ~target samples (a list of per-run batches per step)."""
    out, cur, n = [], [], 0
    for bt in rs:
        cur.append(bt); n += bt["mask"].shape[0]
        if n >= target:
            out.append(cur); cur, n = [], 0
    return out


HEADS = ("w_policy", "w_soft_policy", "w_outcome", "w_hp", "w_hp_floor", "w_aux")
net0, order, names, W, A = netload.build(sp, ck)
shared = [p for n, p in net0.named_parameters()
          if not n.startswith(("pol.", "pol_soft.", "outcome.", "hp.", "hp_floor.", "aux_fight."))]
res = {"ckpt": os.path.basename(ckpt_path), "step": ck.get("step"), "weights": W}

# (a) GRAD
t0 = time.time()
seen = list(runs("seen_*.npz", 10 ** 9))
rng = np.random.default_rng(7)
grad_steps = steps_of([seen[i] for i in rng.permutation(len(seen))])[:NB]
net0.train()
G = {h: [] for h in HEADS}
for grp in grad_steps:
    for h in HEADS:
        if W.get(h, 0) == 0: continue
        w = {k: (W[k] if k == h else 0.0) for k in HEADS}
        net0.zero_grad(set_to_none=True)
        for bt in grp:
            loss, _ = sp.losses(net0, bt, **w)
            (loss / len(grp)).backward()
        G[h].append(torch.cat([(p.grad if p.grad is not None else torch.zeros_like(p)).flatten() for p in shared]).clone())
grad = {}
mean = {h: torch.stack(v).mean(0) for h, v in G.items() if v}
tot = sum(float((g ** 2).sum()) for g in mean.values())
cos = lambda a, b: float((a @ b) / (a.norm() * b.norm() + 1e-30))
for h, g in mean.items():
    per = [float(x.norm()) for x in G[h]]
    grad[h] = {"norm_mean_grad": float(g.norm()), "norm_per_batch_median": float(np.median(per)),
               "share_sq": float((g ** 2).sum()) / tot,
               "cos_policy": cos(g, mean["w_policy"]), "cos_outcome": cos(g, mean["w_outcome"]),
               "cos_policy_per_batch_mean": float(np.mean([cos(a, b) for a, b in zip(G[h], G["w_policy"])]))}
res["grad"] = {"batches": len(grad_steps), "shared_params": int(sum(p.numel() for p in shared)), "heads": grad,
               "secs": round(time.time() - t0)}
print(json.dumps(res["grad"], indent=1), flush=True)
del G, mean

# (b) FT
test = list(runs("unseen_*.npz", EVAL_RUNS))
ref_arg = []
with torch.no_grad():
    net0.train()
    for bt in test:
        ref_arg.append(net0(bt)[0].argmax(-1))


def evaluate(net):
    # training mode (dropout is 0): the soft-policy and aux heads only compute in training mode
    net.train()
    acc, n, agree, nag = {}, 0, 0.0, 0
    with torch.no_grad():
        for bt, ra in zip(test, ref_arg):
            _, parts = sp.losses(net, bt, **W)
            S = bt["mask"].shape[0]
            for k, v in parts.items():
                acc[k] = acc.get(k, 0.0) + float(v) * S
            n += S
            has = bt["has_policy"].bool()
            agree += float((net(bt)[0].argmax(-1) == ra)[has].float().sum()); nag += int(has.sum())
    net.train()
    out = {k: v / n for k, v in acc.items()}
    out["argmax_agree"] = agree / max(1, nag)
    return out


ft_steps = steps_of([seen[i] for i in np.random.default_rng(11).permutation(len(seen))])
res["ft"] = {"steps": STEPS, "eval_runs": len(test), "available_steps": len(ft_steps), "arms": {}}
for ws in ARMS:
    t0 = time.time()
    net, order, names, Wa, _ = netload.build(sp, ck)
    Wa = dict(Wa, w_soft_policy=ws)
    lr = float(ck["opt"]["param_groups"][0]["lr"])
    named = dict(net.named_parameters())
    fix = getattr(sp.amber_net, "INPUT_FIX_PARAMS", ())
    main_p = [named[n] for n in names if not sp.extra_param(n) and n not in fix]
    aux_p = [named[n] for n in names if n.startswith("aux_fight.")]
    en_p = [named[n] for n in names if n in ("enemy_bias", "enemy_gate")]
    a_ = ck["args"] if isinstance(ck["args"], dict) else vars(ck["args"])
    opt = torch.optim.AdamW([{"params": main_p}] + ([{"params": aux_p}] if aux_p else [])
                            + ([{"params": en_p, "lr_scale": a_.get("enemy_lr_scale", 0.01), "weight_decay": 0.0}]
                               if en_p else []) + [{"params": [named[n]]} for n in names if n in fix],
                            lr=lr, weight_decay=a_.get("weight_decay", 1e-4))
    try:
        sp.load_opt_state(opt, ck["opt"])
    except Exception as e:   # group layout differs: fall back to a fresh Adam state (recorded)
        res["ft"].setdefault("notes", []).append(f"w{ws}: optimizer state not loaded ({e})")
    for g in opt.param_groups:
        g["lr"] = lr * g.get("lr_scale", 1.0)
    net.train()
    log = [{"step": 0, **evaluate(net)}]
    for s in range(1, STEPS + 1):
        grp = ft_steps[(s - 1) % len(ft_steps)]
        opt.zero_grad(set_to_none=True)
        for bt in grp:
            loss, _ = sp.losses(net, bt, **Wa)
            (loss / len(grp)).backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        if s % EVAL == 0 or s == STEPS:
            log.append({"step": s, **evaluate(net)})
            print(f"w{ws}", json.dumps(log[-1]), f"({time.time() - t0:.0f} s)", flush=True)
    res["ft"]["arms"][str(ws)] = log
c = res["ft"]["arms"].get("8.0")
if c:
    res["ft"]["vs_w8_end"] = {a: {k: (v[-1][k] - c[-1][k]) / c[-1][k] for k in ("policy", "outcome", "outcome_ema", "hp")
                                  if k in v[-1]} for a, v in res["ft"]["arms"].items() if a != "8.0"}
with open(out_json, "w") as fh:
    json.dump(res, fh, indent=1)
print(json.dumps(res.get("ft", {}).get("vs_w8_end"), indent=1))
