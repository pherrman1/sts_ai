#!/usr/bin/env python3
"""Train the combat net on tensorize.py arrays (combat plan stage 2, 2026-11-08).

usage: train.py DATA_DIR OUT_DIR [--epochs N] [--batch B] [--lr LR] [--d D] [--layers L] [--no-aux] [--no-value]
                [--max-steps N] [--device cpu|cuda] [--seed S] [--init CKPT] [--workers N] [--no-bucket] [--no-amp]
                [--value-weight W] [--train-frac F] [--policy-target visits|cq:S|cq:paper] [--q-source mean|backed]

Splits by run (never inside a run), h = (seed * 2654435761) % 2^32 % 10: h == 0 is the gate holdout, which this
script never reads (gate.py does); h == 1 is the validation split for learning curves and the choice of epochs;
the rest trains. Writes OUT_DIR/model.pt, OUT_DIR/log.jsonl (one line per evaluation) and OUT_DIR/eval.json (final
validation metrics): policy cross-entropy and top-1 agreement with the played action on multi-edge roots, value NLL and death
Brier score / 10-bin ECE, aux HP-loss MAE, each also by room (monster / elite / boss).

Speed (none of it changes the targets or the splits): batches are drawn by length buckets (random pools of 64
batches are sorted by card count before they are cut, then the batch order is shuffled), so a batch pads to similar
rows; batches are collated by `--workers` DataLoader processes ahead of the GPU; on CUDA the forward pass runs under
bfloat16 autocast (losses in float32). `--no-bucket` and `--no-amp` restore plain shuffled float32 batches.

T0 options (Gumbel distillation plan, 2026-11-10); the defaults reproduce the stage-2 runs:
- `--train-frac F` keeps the training runs with u(seed) < F (u: 64-bit Fibonacci hash of the seed in [0, 1)), so smaller
  fractions are nested in larger ones. The validation and gate splits do not change.
- `--policy-target cq:S` trains the policy on the completed-Q policy softmax(log prior + S * q01) instead of the
  visit shares (see completed_q_policy); `cq:paper` uses Gumbel MuZero's S = (c_visit + max visits) * c_scale with
  the teacher's c_visit 50 and c_scale 1. Needs tensorize.py's q.npy and visits.npy. Validation always measures
  the policy CE to the visit shares, so runs with different targets stay comparable.
- With q.npy and visits.npy present, evaluation adds top-1 agreement with the Gumbel pick (`top1_gumbel`) and with
  the finalists' best Q (`top1_qpick`: argmax Q over the edges with at least half the root's largest visit count),
  and `q_regret`: best finalist Q minus the Q of the net's argmax, on rows where that edge was visited.
- `--rooms 2` (comma list of elite_boss codes: 0 monster, 1 elite, 2 boss, 3 other) keeps only those rows in the
  training and the validation split (specialist runs). `--eval-only` evaluates `--init` on the validation split and
  writes eval.json without training (e.g. the generalist on the boss rows).
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M  # noqa: E402


def split_of(seeds):
    """0 = gate holdout, 1 = validation, 2..9 = training."""
    return (seeds.astype(np.uint64) * np.uint64(2654435761)) % np.uint64(2 ** 32) % np.uint64(10)


def train_frac_mask(seeds, frac):
    """Nested subset of runs: u(seed) < frac, u = 64-bit Fibonacci hash of the seed in [0, 1) (well spread over
    consecutive seed blocks)."""
    with np.errstate(over="ignore"):
        h = seeds.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
    u = (h >> np.uint64(11)).astype(np.float64) / 2.0 ** 53
    return u < frac


def completed_q_policy(A, scale):
    """Per-edge completed-Q policy for every multi-edge row with Q (Gumbel MuZero's improved policy, as
    SilverSearcher::selectGumbelNonRoot forms it): visited edges keep their Q, unvisited ones get v_mix; Q is
    min-max normalized over the visited edges to q01; target = softmax(log prior + sigma * q01), sigma = scale, or
    (50 + max visits) * 1 when scale is None. Rows without a root prior use a uniform prior; rows without any visited
    edge keep their visit shares."""
    a = A.a
    off = np.asarray(a["act_off"])
    prior_all, q_all, vis_all = np.asarray(a["prior"]), np.asarray(a["q"]), np.asarray(a["visits"])
    out = np.array(a["policy"], dtype=np.float32, copy=True)
    multi = np.asarray(a["multi"])
    for r in np.nonzero(multi)[0]:
        s, e = off[r], off[r + 1]
        q, vis = q_all[s:e].astype(np.float64), vis_all[s:e].astype(np.float64)
        visited = ~np.isnan(q) & (vis > 0)
        if not visited.any():
            continue
        p = prior_all[s:e].astype(np.float64)
        if np.isnan(p).any() or p.sum() <= 0:
            p = np.full(e - s, 1.0 / (e - s))
        total = vis.sum()
        v_hat = (vis[visited] * q[visited]).sum() / vis[visited].sum()
        pv = p[visited].sum()
        v_mix = (v_hat + total / pv * (p[visited] * q[visited]).sum()) / (1 + total) if pv > 0 else v_hat
        qc = np.where(visited, q, v_mix)
        lo, hi = q[visited].min(), q[visited].max()
        q01 = np.clip((qc - lo) / (hi - lo), 0, 1) if hi > lo else np.full(e - s, 0.5)
        sigma = (50.0 + vis.max()) * 1.0 if scale is None else scale
        z = np.log(np.maximum(p, 1e-12)) + sigma * q01
        z = np.exp(z - z.max())
        out[s:e] = z / z.sum()
    return out


def holdout_mask(seeds):
    return split_of(seeds) == 0


def bucket_batches(idx, ncards, batch, rng, pool=64):
    """Shuffled batches of `idx` whose rows have similar card counts (each pool of `pool` batches is sorted by
    length before it is cut)."""
    perm = rng.permutation(idx)
    out = []
    for s in range(0, len(perm), batch * pool):
        chunk = perm[s:s + batch * pool]
        chunk = chunk[np.argsort(ncards[chunk], kind="stable")]
        out += [chunk[k:k + batch] for k in range(0, len(chunk) - batch + 1, batch)]
    rng.shuffle(out)
    return out


class BatchSet(torch.utils.data.Dataset):
    def __init__(self, A, batches, policy_key="policy"):
        self.A, self.batches, self.policy_key = A, batches, policy_key

    def __len__(self):
        return len(self.batches)

    def __getitem__(self, i):
        return M.collate(self.A, self.batches[i], self.policy_key)


@torch.no_grad()
def evaluate(net, A, idx, batch, device, amp=False):
    if len(idx) == 0:
        return None
    net.eval()
    nc = np.diff(np.asarray(A.a["card_off"]))
    idx = np.asarray(idx)[np.argsort(nc[idx], kind="stable")]   # sums only, so the order is free
    sums = {"n": 0, "multi": 0, "pol_ce": 0.0, "top1": 0, "top1_n": 0, "nll": 0.0, "brier": 0.0, "aux_mae1": 0.0,
            "aux_mae2": 0.0, "g_hit": 0, "g_n": 0, "qp_hit": 0, "qp_n": 0, "regret": 0.0, "regret_n": 0}
    room = {r: {"multi": 0, "top1": 0, "top1_n": 0, "nll": 0.0, "n": 0} for r in range(4)}
    # Q head (value-net-as-leaf V1), on edges with >= 256 visits (V0's truth set): level and sibling-difference MSE,
    # order accuracy on sibling pairs with |dQ| >= 2, and the zero-difference baseline; overall and per room.
    qs = {r: {"lvl": 0.0, "lvl_n": 0, "dif": 0.0, "zero": 0.0, "dif_n": 0, "ord": 0.0, "ord_n": 0} for r in range(5)}
    pdeath, died = [], []
    for s in range(0, len(idx), batch):
        b = {k: v.to(device) for k, v in M.collate(A, idx[s:s + batch]).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            outs = net(b, want_q=True) if net.q_on else net(b)
        logits, vlog, aux = outs[0].float(), outs[1].float(), outs[2].float()
        if net.q_on and "q" in b:
            qhat, qv = outs[3].float(), b["q"]
            ok = b["act_mask"] & (b["visits"] >= 256) & ~torch.isnan(qv)
            qv0, qh0 = torch.nan_to_num(qv), qhat
            for r in (2, 4):   # 4 = all rows
                sel = ok & ((b["elite_boss"] == r)[:, None] if r < 4 else torch.ones_like(ok))
                qs[r]["lvl"] += float((((qh0 - qv0) ** 2) * sel).sum())
                qs[r]["lvl_n"] += int(sel.sum())
                E_ = sel.shape[1]
                pm = sel[:, :, None] & sel[:, None, :] & torch.triu(torch.ones(E_, E_, dtype=torch.bool, device=sel.device), 1)
                dT = qv0[:, :, None] - qv0[:, None, :]
                dH = qh0[:, :, None] - qh0[:, None, :]
                npair = pm.sum((1, 2)).float()
                rows = npair > 0
                qs[r]["dif"] += float(((((dH - dT) ** 2) * pm).sum((1, 2))[rows] / npair[rows]).sum())
                qs[r]["zero"] += float((((dT ** 2) * pm).sum((1, 2))[rows] / npair[rows]).sum())
                qs[r]["dif_n"] += int(rows.sum())
                big = pm & (dT.abs() >= 2)
                agree = (torch.sign(dH) == torch.sign(dT)).float() + 0.5 * (dH == 0).float()
                qs[r]["ord"] += float((agree * big).sum())
                qs[r]["ord_n"] += int(big.sum())
        logp = torch.log_softmax(logits, -1).masked_fill(~b["act_mask"], 0)
        multi = b["multi"] > 0
        ce = -(b["policy"] * logp).sum(-1)
        pick = logits.argmax(-1)
        has = multi & (b["chosen"] >= 0)
        hit = (pick == b["chosen"]) & has
        if "gumbelChoice" in b:
            gh = multi & (b["gumbelChoice"] >= 0)
            sums["g_hit"] += int(((pick == b["gumbelChoice"]) & gh).sum())
            sums["g_n"] += int(gh.sum())
        if "q" in b:
            qv, vis = b["q"], b["visits"]
            fin = (vis * 2 >= vis.max(-1, keepdim=True).values) & (vis > 0) & ~torch.isnan(qv)
            qfin = torch.where(fin, qv, torch.full_like(qv, -float("inf")))
            best, qpick = qfin.max(-1)
            ok = multi & fin.any(-1)
            sums["qp_hit"] += int(((pick == qpick) & ok).sum())
            sums["qp_n"] += int(ok.sum())
            qn = torch.gather(qv, 1, pick[:, None]).squeeze(1)
            rk = ok & ~torch.isnan(qn)
            sums["regret"] += float(torch.where(rk, best - qn, torch.zeros_like(qn)).sum())
            sums["regret_n"] += int(rk.sum())
        vc = M.value_class(b["won"], b["endFrac"])
        nll = torch.nn.functional.cross_entropy(vlog, vc, reduction="none")
        pd = torch.softmax(vlog, -1)[:, 0]
        d = (b["won"] == 0).float()
        sums["n"] += len(vc)
        sums["multi"] += int(multi.sum())
        sums["pol_ce"] += float((ce * multi).sum())
        sums["top1"] += int(hit.sum())
        sums["top1_n"] += int(has.sum())
        sums["nll"] += float(nll.sum())
        sums["brier"] += float(((pd - d) ** 2).sum())
        sums["aux_mae1"] += float((aux[:, 0] * 10 - b["hpLoss1"]).abs().sum())
        sums["aux_mae2"] += float((aux[:, 1] * 10 - b["hpLoss2"]).abs().sum())
        pdeath.append(pd.cpu().numpy())
        died.append(d.cpu().numpy())
        for r in range(4):
            sel = b["elite_boss"] == r
            room[r]["n"] += int(sel.sum())
            room[r]["nll"] += float(nll[sel].sum())
            room[r]["multi"] += int((multi & sel).sum())
            room[r]["top1"] += int((hit & sel).sum())
            room[r]["top1_n"] += int((has & sel).sum())
    pdeath, died = np.concatenate(pdeath), np.concatenate(died)
    bins = np.minimum((pdeath * 10).astype(int), 9)
    ece = sum(abs(pdeath[bins == k].mean() - died[bins == k].mean()) * (bins == k).sum()
              for k in range(10) if (bins == k).any()) / len(pdeath)
    n, mm = max(1, sums["n"]), max(1, sums["multi"])
    out = {"rows": sums["n"], "multiRows": sums["multi"], "policy_ce": sums["pol_ce"] / mm,
           "top1": sums["top1"] / max(1, sums["top1_n"]), "value_nll": sums["nll"] / n, "death_brier": sums["brier"] / n,
           "death_ece": float(ece), "death_rate": float(died.mean()), "aux_mae1": sums["aux_mae1"] / n,
           "aux_mae2": sums["aux_mae2"] / n,
           "top1_gumbel": sums["g_hit"] / sums["g_n"] if sums["g_n"] else None, "top1_gumbel_n": sums["g_n"],
           "top1_qpick": sums["qp_hit"] / sums["qp_n"] if sums["qp_n"] else None, "top1_qpick_n": sums["qp_n"],
           "q_regret": sums["regret"] / sums["regret_n"] if sums["regret_n"] else None, "q_regret_n": sums["regret_n"],
           "by_room": {name: {"rows": room[r]["n"], "value_nll": room[r]["nll"] / max(1, room[r]["n"]),
                              "top1": room[r]["top1"] / max(1, room[r]["top1_n"])}
                       for r, name in enumerate(("monster", "elite", "boss", "other"))}}
    if net.q_on:
        for r, name in ((4, "q"), (2, "q_boss")):
            v = qs[r]
            out[name] = {"level_mse": v["lvl"] / max(1, v["lvl_n"]), "edges": v["lvl_n"],
                         "diff_mse": v["dif"] / max(1, v["dif_n"]), "zero_diff_mse": v["zero"] / max(1, v["dif_n"]),
                         "roots": v["dif_n"], "order_acc": v["ord"] / max(1, v["ord_n"]), "pairs": v["ord_n"]}
    net.train()
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--d", type=int, default=128)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--no-aux", action="store_true")
    ap.add_argument("--no-value", action="store_true")
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--eval-every", type=int, default=2000)
    ap.add_argument("--eval-rows", type=int, default=50000)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=20261108)
    ap.add_argument("--init", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-bucket", action="store_true")
    ap.add_argument("--no-amp", action="store_true")
    ap.add_argument("--value-weight", type=float, default=1.0, help="weight of the value loss (policy and aux: 1)")
    ap.add_argument("--train-frac", type=float, default=1.0, help="nested fraction of the training runs (T0)")
    ap.add_argument("--policy-target", default="visits", help="visits | cq:S | cq:paper (T0)")
    ap.add_argument("--rooms", default="", help="comma list of elite_boss codes to keep (T0 specialists)")
    ap.add_argument("--eval-only", action="store_true", help="evaluate --init on the validation split, no training")
    ap.add_argument("--encounters", default="", help="comma list of encounter names to keep (T1 per-boss specialists)")
    ap.add_argument("--q-head", action="store_true",
                    help="value-net-as-leaf V1: add the per-edge Q head (needs --q-source backed); default off")
    ap.add_argument("--q-weight", type=float, default=1.0, help="weight of the Q head loss (with --q-head)")
    ap.add_argument("--q-pair-weight", type=float, default=4.0, help="weight of the sibling-contrast term in it")
    ap.add_argument("--q-min-visits", type=int, default=64, help="edges with fewer visits carry no Q target")
    ap.add_argument("--q-source", default="mean", choices=("mean", "backed"),
                    help="Q for cq targets and q_regret: mean (q.npy) or max-backed (qb.npy, D2 / T1)")
    args = ap.parse_args(argv)
    if args.q_head and args.q_source != "backed":
        raise SystemExit("--q-head trains on the max-backed Q: pass --q-source backed")
    os.makedirs(args.out, exist_ok=True)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    A = M.Arrays(args.data)
    if args.q_source == "backed":
        if "qb" not in A.a:
            raise SystemExit("--q-source backed needs tensorize.py's qb.npy (max-backup rows)")
        A.a["q"] = A.a["qb"]   # cq targets and q_regret / top1_qpick then use the max-backed Q
    seeds = np.asarray(A.a["seed"])
    split = split_of(seeds)
    if not 0 < args.train_frac <= 1:
        raise SystemExit("--train-frac must be in (0, 1]")
    train_idx = np.nonzero((split >= 2) & train_frac_mask(seeds, args.train_frac))[0]
    val_idx = np.nonzero(split == 1)[0]
    if args.rooms:
        keep = np.isin(np.asarray(A.a["elite_boss"]), [int(x) for x in args.rooms.split(",")])
        train_idx, val_idx = train_idx[keep[train_idx]], val_idx[keep[val_idx]]
    if args.encounters:
        names = A.meta["encounters"]
        want = [x for x in args.encounters.split(",") if x]
        if any(w not in names for w in want):
            raise SystemExit(f"--encounters: unknown name in {want}")
        keep = np.isin(np.asarray(A.a["encounter"]), [names.index(w) for w in want])
        train_idx, val_idx = train_idx[keep[train_idx]], val_idx[keep[val_idx]]
    policy_key = "policy"
    if args.policy_target != "visits":
        if not args.policy_target.startswith("cq:") or "q" not in A.a or "visits" not in A.a:
            raise SystemExit("--policy-target must be visits or cq:S / cq:paper, and cq needs q.npy and visits.npy")
        arg = args.policy_target[3:]
        A.a["policy_train"] = completed_q_policy(A, None if arg == "paper" else float(arg))
        policy_key = "policy_train"
    eval_idx = val_idx if len(val_idx) <= args.eval_rows else rng.choice(val_idx, args.eval_rows, replace=False)
    caps = A.meta["caps"]
    net = M.CombatNet(d=args.d, layers=args.layers, g_len=caps["G_LEN"], m_num=caps["M_NUM"], q_len=caps["Q_LEN"],
                      a_len=caps["A_LEN"], aux=not args.no_aux, value=not args.no_value,
                      qhead=args.q_head).to(args.device)
    if args.init:
        sd = torch.load(args.init, map_location=args.device)
        missing, unexpected = net.load_state_dict(sd, strict=False)
        # a Q-head run may start from a checkpoint without one; anything else must match exactly
        if unexpected or any(not k.startswith("qh.") for k in missing) or (missing and not args.q_head):
            raise SystemExit(f"--init mismatch: missing {missing}, unexpected {unexpected}")
    params = sum(p.numel() for p in net.parameters())
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=0.01)
    steps = 0 if args.eval_only else int(args.epochs * len(train_idx) / args.batch)
    if args.max_steps and not args.eval_only:
        steps = min(steps, args.max_steps)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(1, steps), pct_start=0.05)
    log = open(os.path.join(args.out, "log.jsonl"), "w")
    cfg = {k: v for k, v in vars(args).items()}
    cfg.update({"params": params, "trainRows": int(len(train_idx)), "valRows": int(len(val_idx)),
                "gateRowsUntouched": int((split == 0).sum()),
                "trainRuns": int(len(np.unique(seeds[split >= 2]))), "valRuns": int(len(np.unique(seeds[split == 1]))),
                "steps": steps, "data_meta": A.meta})
    log.write(json.dumps({"config": cfg}) + "\n")
    print(json.dumps({k: cfg[k] for k in ("params", "trainRows", "valRows", "steps", "device")}), flush=True)
    amp = args.device.startswith("cuda") and not args.no_amp
    ncards = np.diff(np.asarray(A.a["card_off"]))

    def epoch_batches():
        if args.no_bucket:
            perm = rng.permutation(train_idx)
            return [perm[k:k + args.batch] for k in range(0, len(perm) - args.batch + 1, args.batch)]
        return bucket_batches(train_idx, ncards, args.batch, rng)

    def batch_stream():
        while True:
            dl = torch.utils.data.DataLoader(BatchSet(A, epoch_batches(), policy_key), batch_size=None, shuffle=False,
                                             num_workers=args.workers, pin_memory=args.device.startswith("cuda"),
                                             prefetch_factor=4 if args.workers else None)
            yield from dl

    t0 = time.time()
    stream = batch_stream()
    for step in range(steps):
        b = {k: v.to(args.device, non_blocking=True) for k, v in next(stream).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            outs = net(b, want_q=True) if args.q_head else net(b)
        logits, vlog, aux = outs[:3]
        loss, parts = M.losses(net, b, logits.float(), vlog.float(), aux.float(), args.value_weight)
        if args.q_head:
            ql, qlev, qpair = M.q_losses(outs[3].float(), b, args.q_min_visits, args.q_pair_weight)
            loss = loss + args.q_weight * ql
            parts.update({"q_level": qlev.item(), "q_pair": qpair.item()})
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        sched.step()
        if (step + 1) % args.eval_every == 0 or step + 1 == steps:
            ev = evaluate(net, A, eval_idx, 512, args.device, amp)
            rec = {"step": step + 1, "sec": round(time.time() - t0, 1), "train": parts, "val": ev}
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(json.dumps({"step": step + 1, "sec": rec["sec"], **({k: round(ev[k], 4) for k in
                              ("policy_ce", "top1", "value_nll", "death_ece", "aux_mae1")} if ev else {}),
                              **({k: round(ev[k], 4) for k in ("top1_gumbel", "top1_qpick", "q_regret")
                                  if ev and ev.get(k) is not None}),
                              **({k: {m: round(x, 4) for m, x in ev[k].items()} for k in ("q", "q_boss")
                                  if ev and k in ev})}), flush=True)
    if not args.eval_only:
        torch.save(net.state_dict(), os.path.join(args.out, "model.pt"))
    final = evaluate(net, A, val_idx, 512, args.device, amp)
    json.dump({"config": {k: cfg[k] for k in cfg if k != "data_meta"}, "validation": final},
              open(os.path.join(args.out, "eval.json"), "w"), indent=1)
    if final:
        print(json.dumps({"final_val": {k: final[k] for k in ("rows", "policy_ce", "top1", "value_nll", "death_ece",
                                                               "top1_gumbel", "top1_qpick", "q_regret", "q", "q_boss")
                                        if k in final}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
