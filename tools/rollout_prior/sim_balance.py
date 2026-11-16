#!/usr/bin/env python3
"""Simulation balancing for the prior-playout policy (issue #1053, research).

Trains a combat_policy_mlp_v2 playout policy so that the MEAN of its sampled playouts matches the played fight's
outcome (Silver & Tesauro 2009, "Monte-Carlo simulation balancing"), instead of imitating search visit shares.

Objective per root s with reference value V*(s) (score of the fight G16 actually played from s) and the policy's
playout value V(s) = E_pi[z]:  J = 1/2 (V(s) - V*(s))^2.  Gradient  (V(s) - V*(s)) * E_pi[(z - b) sum_t grad log pi(a_t|s_t)],
estimated per playout i with leave-one-out means of the other playouts for V(s) and the baseline b, and with a random
fraction r of the multi-edge steps traced (weight 1/r). The policy samples from softmax(logit / T).

Data come from `one_combat playoutvaluebench` with a sampling arm `st=MODEL@T` and STS_PVB_TRACE / _RATE.

  sim_balance.py check MODEL.txt TRACE_PREFIX T                       parity of this module's logits with the trace
  sim_balance.py loop  MODEL.txt ROWS.jsonl VAL_ROWS.jsonl OUTDIR [--iters N --roots R --playouts P --temp T ...]
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import silver_az_mlp as M  # noqa: E402

S, A, NCARD, NT, MON_OFF, CARD_COL = M.S, M.A, M.NCARD, M.NT, M.MON_OFF, M.CARD_COL
ID_COLS = [1664, 1673, 1682, 1691, 1700]
INTENT_COLS = [1668, 1677, 1686, 1695, 1704]
KEYS = ("state_w", "action_w", "card", "target_w", "b1", "w2", "b2", "w3", "b3")
TABLES = ("enc", "mon_id", "mon_dmg")


# ---------------------------------------------------------------- model text <-> arrays
def load_txt(path):
    head, feats, W = [], [], {}
    with open(path) as f:
        lines = f.read().split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln:
            i += 1; continue
        tok = ln.split()
        if tok[0] in KEYS and len(tok) == 1:
            W[tok[0]] = np.array(lines[i + 1].split(), np.float64); i += 2; continue
        if tok[0] in TABLES and len(tok) == 2:
            W[tok[0]] = np.array(lines[i + 1].split(), np.float64).reshape(int(tok[1]), -1); i += 2; continue
        if tok[0] == "feat":
            feats.append(ln[5:])
        else:
            head.append(ln)
        i += 1
    if head[0] != "combat_policy_mlp_v2":
        raise SystemExit(f"{path}: not a combat_policy_mlp_v2 model")
    h1 = int(dict(x.split() for x in head[1:3])["h1"]); h2 = int(dict(x.split() for x in head[1:3])["h2"])
    W["state_w"] = W["state_w"].reshape(S, h1); W["action_w"] = W["action_w"].reshape(A, h1)
    W["card"] = W["card"].reshape(NCARD, h1); W["target_w"] = W["target_w"].reshape(NT, h1)
    W["w2"] = W["w2"].reshape(h2, h1)
    return {"head": head, "feats": feats, "h1": h1, "h2": h2, "W": W}


def save_txt(model, W, path):
    with open(path + ".tmp", "w") as f:
        f.write("\n".join(model["head"]) + "\n")
        for n in model["feats"]:
            f.write(f"feat {n}\n")
        for key in KEYS:
            f.write(key + "\n" + " ".join(f"{x:.9g}" for x in np.asarray(W[key], np.float32).ravel()) + "\n")
        for key in TABLES:
            tab = W[key]
            f.write(f"{key} {tab.shape[0]}\n" + " ".join(f"{x:.9g}" for x in np.asarray(tab, np.float32).ravel()) + "\n")
    os.replace(path + ".tmp", path)


def make_net(torch, model):
    nn = torch.nn

    class Folded(nn.Module):
        """The exported (folded) v2 MLP as trainable parameters; same forward as train.py's Net with unit scales."""

        def __init__(s):
            super().__init__()
            for k, v in model["W"].items():
                setattr(s, k, nn.Parameter(torch.tensor(v, dtype=torch.float32)))

        def forward(s, b):
            hs = torch.nn.functional.embedding_bag(b["idx"], s.state_w, b["off"], mode="sum",
                                                   per_sample_weights=b["w"])
            mid, mint = b["mon"][:, :5], b["mon"][:, 5:]
            present = (mid > 0).float().unsqueeze(2)
            hs = hs + ((s.mon_id[mid] + s.mon_dmg[mint]) * present).sum(1) + s.enc[b["enc"]]
            ea = b["act"] @ s.action_w + s.card[b["card"]] + b["tv"] @ s.target_w + s.b1
            x = torch.relu(hs[b["eroot"]] + ea)
            x = torch.relu(x @ s.w2.T + s.b2)
            return x @ s.w3 + s.b3

        def arrays(s):
            return {k: getattr(s, k).detach().double().cpu().numpy() for k in model["W"]}

    return Folded()


# ---------------------------------------------------------------- traces
def load_trace(prefix):
    """Sparse trace rows -> step arrays (state sparse block, dense action block per edge, pick, prob, ids)."""
    nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
    ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
    idx = np.fromfile(prefix + ".idx", dtype=np.uint16).astype(np.int64)
    val = np.fromfile(prefix + ".val", dtype=np.float32)
    steps, acts = [], []
    with open(prefix + ".meta.jsonl") as f:
        for i, line in enumerate(f):
            m = json.loads(line)
            if m["k"] == "state":
                steps.append((i, m)); acts.append([])
            else:
                acts[-1].append((i, m["tgt"]))
    st_idx, st_val, st_ptr = [], [], [0]
    e_act, e_tgt, nedge, meta = [], [], [], []
    for (row, m), al in zip(steps, acts):
        sl = slice(ptr[row], ptr[row + 1])
        st_idx.append(idx[sl]); st_val.append(val[sl]); st_ptr.append(st_ptr[-1] + int(nnz[row]))
        blk = np.zeros((len(al), A), np.float32)
        for j, (ar, tgt) in enumerate(al):
            s2 = slice(ptr[ar], ptr[ar + 1])
            blk[j, idx[s2] - S] = val[s2]
            e_tgt.append(tgt)
        e_act.append(blk); nedge.append(len(al))
        meta.append((m["row"], m["p"], m["t"], m["pick"], m["prob"]))
    T = {"st_idx": np.concatenate(st_idx) if st_idx else np.zeros(0, np.int64),
         "st_val": np.concatenate(st_val) if st_val else np.zeros(0, np.float32),
         "st_ptr": np.array(st_ptr, np.int64), "e_act": np.concatenate(e_act) if e_act else np.zeros((0, A), np.float32),
         "e_tgt": np.array(e_tgt, np.int64), "nedge": np.array(nedge, np.int64),
         "meta": np.array(meta, np.float64).reshape(-1, 5)}
    n = len(T["nedge"])
    T["e_ptr"] = np.concatenate([[0], np.cumsum(T["nedge"])])
    st_root = np.repeat(np.arange(n), np.diff(T["st_ptr"]))
    mon_t = np.zeros((n, 5 * NT), np.float32)
    sel = (T["st_idx"] >= MON_OFF) & (T["st_idx"] < MON_OFF + 5 * NT)
    mon_t[st_root[sel], T["st_idx"][sel] - MON_OFF] = T["st_val"][sel]
    e_root = np.repeat(np.arange(n), T["nedge"])
    tv = np.zeros((len(T["e_tgt"]), NT), np.float32)
    has = np.flatnonzero(T["e_tgt"] >= 0)
    cols = T["e_tgt"][has][:, None] * NT + np.arange(NT)[None, :]
    tv[has] = mon_t[e_root[has][:, None], cols]
    T["tv"] = tv
    mon = np.zeros((n, 10), np.int64)
    for k, c in enumerate(ID_COLS + INTENT_COLS):
        m = T["st_idx"] == c
        mon[st_root[m], k] = np.rint(T["st_val"][m]).astype(np.int64) + (1 if k < 5 else 0)
    T["mon"] = np.clip(mon, 0, 127)
    enc = np.zeros(n, np.int64)
    m = T["st_idx"] == 1
    enc[st_root[m]] = np.rint(T["st_val"][m]).astype(np.int64)
    T["enc"] = np.clip(enc, 0, 127)
    card = T["e_act"][:, CARD_COL].astype(np.int64) + 1
    card[(card < 0) | (card >= NCARD)] = 0
    T["card"] = card
    return T


def step_batch(torch, T, sel, dev):
    sel = np.asarray(sel)
    lens = np.diff(T["st_ptr"])[sel]
    pos = np.concatenate([np.arange(T["st_ptr"][r], T["st_ptr"][r + 1]) for r in sel]) if len(sel) else np.zeros(0, int)
    ne = T["nedge"][sel]
    epos = np.concatenate([np.arange(T["e_ptr"][r], T["e_ptr"][r + 1]) for r in sel])
    t = lambda x: torch.from_numpy(np.ascontiguousarray(x)).to(dev)  # noqa: E731
    return {"idx": t(T["st_idx"][pos]), "off": t(np.concatenate([[0], np.cumsum(lens)[:-1]]).astype(np.int64)),
            "w": t(T["st_val"][pos].astype(np.float32)), "mon": t(T["mon"][sel]), "enc": t(T["enc"][sel]),
            "act": t(T["e_act"][epos]), "card": t(T["card"][epos]), "tv": t(T["tv"][epos]),
            "eroot": t(np.repeat(np.arange(len(sel)), ne).astype(np.int64)), "n": len(sel),
            "first": t(np.concatenate([[0], np.cumsum(ne)[:-1]]).astype(np.int64))}


def group_logp(torch, logit, b, temp):
    z = logit / temp
    m = torch.full((b["n"],), -1e30, device=z.device).index_reduce_(0, b["eroot"], z.detach(), "amax", include_self=True)
    ex = torch.exp(z - m[b["eroot"]])
    tot = torch.zeros(b["n"], device=z.device).index_add_(0, b["eroot"], ex)
    return z - m[b["eroot"]] - torch.log(tot[b["eroot"]])


# ---------------------------------------------------------------- engine runs
def run_bench(binary, env, rows_path, out_prefix, model_path, playouts, temp, trace_rate, jobs):
    """playoutvaluebench on ROWS split into `jobs` parts; returns result jsonl paths and trace prefixes."""
    lines = open(rows_path).read().splitlines()
    parts = [lines[i::jobs] for i in range(jobs)]
    procs, outs, traces = [], [], []
    for j, part in enumerate(parts):
        inp = f"{out_prefix}.in{j}"
        open(inp, "w").write("\n".join(part) + "\n")
        out = f"{out_prefix}.out{j}.jsonl"
        e = dict(os.environ, **env)
        if trace_rate > 0:
            tp = f"{out_prefix}.tr{j}"
            for suf in (".nnz", ".idx", ".val", ".meta.jsonl"):
                if os.path.exists(tp + suf):
                    os.remove(tp + suf)
            e["STS_PVB_TRACE"] = tp; e["STS_PVB_TRACE_RATE"] = str(trace_rate); traces.append(tp)
        else:
            e.pop("STS_PVB_TRACE", None)
        arm = f"st={model_path}@{temp}" if temp > 0 else f"st={model_path}"
        procs.append(subprocess.Popen([binary, "playoutvaluebench", out, str(playouts), arm], stdin=open(inp),
                                      stdout=subprocess.DEVNULL, stderr=open(out + ".log", "w"), env=e))
        outs.append(out)
    for p in procs:
        if p.wait() != 0:
            raise RuntimeError(f"playoutvaluebench failed rc {p.returncode} (see {out_prefix}.out*.log)")
    return outs, traces


def read_results(outs, rows_meta, j_offsets):
    """Per (part, row index within part): scores array and reference score."""
    res = {}
    for j, out in enumerate(outs):
        local = 0
        for line in open(out):
            r = json.loads(line)
            if "error" in r:
                local += 1; continue
            key = (int(r["seed"]), int(r["fight"]), int(r["decision"]))
            res[(j, local)] = (np.array(r["scores"], np.float64), rows_meta[key])
            local += 1
    return res


def value_error(outs, ref):
    err, n = [], 0
    for out in outs:
        for line in open(out):
            r = json.loads(line)
            if "error" in r:
                continue
            key = (int(r["seed"]), int(r["fight"]), int(r["decision"]))
            if key in ref:
                err.append((np.mean(r["scores"]) - ref[key]) ** 2)
    return float(np.mean(err)), len(err)


def refs(rows_path):
    out = {}
    for line in open(rows_path):
        r = json.loads(line)
        k = r.get("k") or {}
        if k.get("ref") and k["ref"].get("score") is not None:
            out[(int(r["seed"]), int(r["fight"]), int(r["decision"]))] = float(k["ref"]["score"])
    return out


# ---------------------------------------------------------------- commands
def cmd_check(a):
    import torch
    model = load_txt(a.model)
    net = make_net(torch, model)
    T = load_trace(a.trace)
    sel = np.arange(min(len(T["nedge"]), 5000))
    b = step_batch(torch, T, sel, "cpu")
    with torch.no_grad():
        lp = group_logp(torch, net(b), b, a.temp)
    pick = T["meta"][sel, 3].astype(np.int64)
    got = np.exp(lp[b["first"].numpy() + pick].numpy())
    want = T["meta"][sel, 4]
    d = np.abs(got - want)
    print(json.dumps({"steps": len(sel), "max_abs": float(d.max()), "mean_abs": float(d.mean())}))
    if d.max() > 1e-3:
        raise SystemExit("parity FAILED")


def cmd_loop(a):
    import torch
    torch.manual_seed(a.seed); torch.set_num_threads(a.threads)
    rng = np.random.default_rng(a.seed)
    os.makedirs(a.out, exist_ok=True)
    model = load_txt(a.model)
    net = make_net(torch, model)
    init = {k: v.detach().clone() for k, v in net.state_dict().items()}
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    env = {k: v for k, v in (x.split("=", 1) for x in a.env)} if a.env else {}
    train_lines = open(a.rows).read().splitlines()
    ref_train = refs(a.rows)
    ref_val = refs(a.val)
    log = open(os.path.join(a.out, "log.jsonl"), "a")

    def evaluate(it, path):
        outs, _ = run_bench(a.binary, env, a.val, os.path.join(a.out, f"val{it:03d}"), path, a.val_playouts,
                            a.temp, 0, a.jobs)
        mse, n = value_error(outs, ref_val)
        row = {"iter": it, "val_mse": mse, "val_rows": n, "t": time.time()}
        if a.eval_argmax:
            outs, _ = run_bench(a.binary, env, a.val, os.path.join(a.out, f"vala{it:03d}"), path, a.val_playouts,
                                0, 0, a.jobs)
            row["val_mse_argmax"], _ = value_error(outs, ref_val)
        print(json.dumps(row), flush=True); log.write(json.dumps(row) + "\n"); log.flush()

    cur = os.path.join(a.out, "model_000.txt")
    save_txt(model, net.arrays(), cur)
    evaluate(0, cur)
    for it in range(1, a.iters + 1):
        t0 = time.time()
        pick = rng.choice(len(train_lines), min(a.roots, len(train_lines)), replace=False)
        rows_path = os.path.join(a.out, "iter.rows.jsonl")
        open(rows_path, "w").write("\n".join(train_lines[i] for i in pick) + "\n")
        outs, traces = run_bench(a.binary, env, rows_path, os.path.join(a.out, "iter"), cur, a.playouts, a.temp,
                                 a.trace_rate, a.jobs)
        # Per (row, playout): weight w = (V_-i - V*) * (z_i - b_-i) / (N * rate); loss = sum w * sum_t log pi.
        wts, err2 = {}, []
        for j, out in enumerate(outs):
            for line in open(out):
                r = json.loads(line)
                if "error" in r:
                    continue
                key = (int(r["seed"]), int(r["fight"]), int(r["decision"]))
                if key not in ref_train:
                    continue
                z = np.array(r["scores"], np.float64); N = len(z)
                loo = (z.sum() - z) / (N - 1)
                err = loo - ref_train[key]
                err2.append((z.mean() - ref_train[key]) ** 2)
                for i in range(N):
                    wts[(j, key, i)] = err[i] * (z[i] - loo[i]) / (N * a.trace_rate)
        # Traces: rows are indexed per part in input order; map row index -> key.
        part_keys = []
        for j in range(a.jobs):
            ks = []
            for line in open(os.path.join(a.out, f"iter.in{j}")):
                if line.strip():
                    r = json.loads(line); ks.append((int(r["seed"]), int(r["fight"]), int(r["decision"])))
            part_keys.append(ks)
        Ts, W = [], []
        for j, tp in enumerate(traces):
            T = load_trace(tp)
            if len(T["nedge"]) == 0:
                continue
            w = np.array([wts.get((j, part_keys[j][int(m[0])], int(m[1])), 0.0) for m in T["meta"]], np.float32)
            Ts.append(T); W.append(w)
        nsteps = sum(len(w) for w in W)
        nroots = max(len(err2), 1)
        net.train()
        loss_tot = 0.0
        for T, w in zip(Ts, W):
            order = rng.permutation(len(w))
            for s0 in range(0, len(order), a.batch):
                sel = order[s0:s0 + a.batch]
                b = step_batch(torch, T, sel, "cpu")
                lp = group_logp(torch, net(b), b, a.temp)
                lpick = lp[b["first"] + torch.from_numpy(T["meta"][sel, 3].astype(np.int64))]
                loss = (torch.from_numpy(w[sel]) * lpick).sum() / nroots
                if a.kl > 0:
                    with torch.no_grad():
                        sd = net.state_dict(); net.load_state_dict(init); lp0 = group_logp(torch, net(b), b, a.temp)
                        net.load_state_dict(sd)
                    loss = loss + a.kl * (torch.exp(lp) * (lp - lp0)).sum() / len(sel)
                opt.zero_grad(); loss.backward()
                if a.clip > 0:
                    torch.nn.utils.clip_grad_norm_(net.parameters(), a.clip)
                opt.step(); loss_tot += float(loss.detach())
        cur = os.path.join(a.out, f"model_{it:03d}.txt")
        save_txt(model, net.arrays(), cur)
        row = {"iter": it, "train_mse": float(np.mean(err2)) if err2 else None, "roots": len(err2), "steps": nsteps,
               "loss": loss_tot, "seconds": round(time.time() - t0, 1)}
        print(json.dumps(row), flush=True); log.write(json.dumps(row) + "\n"); log.flush()
        if it % a.eval_every == 0 or it == a.iters:
            evaluate(it, cur)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("model"); c.add_argument("trace"); c.add_argument("temp", type=float)
    lp = sub.add_parser("loop"); lp.add_argument("model"); lp.add_argument("rows"); lp.add_argument("val")
    lp.add_argument("out")
    lp.add_argument("--binary", default="build/linux-gcc-release/one_combat")
    lp.add_argument("--env", nargs="*", help="KEY=VALUE for the engine (the playoutvaluebench environment)")
    lp.add_argument("--iters", type=int, default=20); lp.add_argument("--roots", type=int, default=1000)
    lp.add_argument("--playouts", type=int, default=16); lp.add_argument("--temp", type=float, default=1.0)
    lp.add_argument("--trace-rate", type=float, default=0.25); lp.add_argument("--jobs", type=int, default=4)
    lp.add_argument("--lr", type=float, default=1e-4); lp.add_argument("--batch", type=int, default=2048)
    lp.add_argument("--kl", type=float, default=0.0); lp.add_argument("--clip", type=float, default=1.0)
    lp.add_argument("--val-playouts", type=int, default=32); lp.add_argument("--eval-every", type=int, default=5)
    lp.add_argument("--eval-argmax", action="store_true"); lp.add_argument("--threads", type=int, default=4)
    lp.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    {"check": cmd_check, "loop": cmd_loop}[a.cmd](a)


if __name__ == "__main__":
    main()
