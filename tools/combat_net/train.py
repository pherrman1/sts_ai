#!/usr/bin/env python3
"""Train the combat net on tensorize.py arrays (combat plan stage 2, 2026-11-08).

usage: train.py DATA_DIR OUT_DIR [--epochs N] [--batch B] [--lr LR] [--d D] [--layers L] [--no-aux] [--no-value]
                [--max-steps N] [--device cpu|cuda] [--seed S] [--init CKPT] [--workers N] [--no-bucket] [--no-amp]

Splits by run (never inside a run), h = (seed * 2654435761) % 2^32 % 10: h == 0 is the gate holdout, which this
script never reads (gate.py does); h == 1 is the validation split for learning curves and the choice of epochs;
the rest trains. Writes OUT_DIR/model.pt, OUT_DIR/log.jsonl (one line per evaluation) and OUT_DIR/eval.json (final
validation metrics): policy cross-entropy and top-1 agreement with the played action on multi-edge roots, value NLL and death
Brier score / 10-bin ECE, aux HP-loss MAE, each also by room (monster / elite / boss).

Speed (none of it changes the targets or the splits): batches are drawn by length buckets (random pools of 64
batches are sorted by card count before they are cut, then the batch order is shuffled), so a batch pads to similar
rows; batches are collated by `--workers` DataLoader processes ahead of the GPU; on CUDA the forward pass runs under
bfloat16 autocast (losses in float32). `--no-bucket` and `--no-amp` restore plain shuffled float32 batches.
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
    def __init__(self, A, batches):
        self.A, self.batches = A, batches

    def __len__(self):
        return len(self.batches)

    def __getitem__(self, i):
        return M.collate(self.A, self.batches[i])


@torch.no_grad()
def evaluate(net, A, idx, batch, device, amp=False):
    if len(idx) == 0:
        return None
    net.eval()
    nc = np.diff(np.asarray(A.a["card_off"]))
    idx = np.asarray(idx)[np.argsort(nc[idx], kind="stable")]   # sums only, so the order is free
    sums = {"n": 0, "multi": 0, "pol_ce": 0.0, "top1": 0, "top1_n": 0, "nll": 0.0, "brier": 0.0, "aux_mae1": 0.0,
            "aux_mae2": 0.0}
    room = {r: {"multi": 0, "top1": 0, "top1_n": 0, "nll": 0.0, "n": 0} for r in range(4)}
    pdeath, died = [], []
    for s in range(0, len(idx), batch):
        b = {k: v.to(device) for k, v in M.collate(A, idx[s:s + batch]).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            logits, vlog, aux = net(b)
        logits, vlog, aux = logits.float(), vlog.float(), aux.float()
        logp = torch.log_softmax(logits, -1).masked_fill(~b["act_mask"], 0)
        multi = b["multi"] > 0
        ce = -(b["policy"] * logp).sum(-1)
        pick = logits.argmax(-1)
        has = multi & (b["chosen"] >= 0)
        hit = (pick == b["chosen"]) & has
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
           "by_room": {name: {"rows": room[r]["n"], "value_nll": room[r]["nll"] / max(1, room[r]["n"]),
                              "top1": room[r]["top1"] / max(1, room[r]["top1_n"])}
                       for r, name in enumerate(("monster", "elite", "boss", "other"))}}
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
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    A = M.Arrays(args.data)
    seeds = np.asarray(A.a["seed"])
    split = split_of(seeds)
    train_idx, val_idx = np.nonzero(split >= 2)[0], np.nonzero(split == 1)[0]
    eval_idx = val_idx if len(val_idx) <= args.eval_rows else rng.choice(val_idx, args.eval_rows, replace=False)
    caps = A.meta["caps"]
    net = M.CombatNet(d=args.d, layers=args.layers, g_len=caps["G_LEN"], m_num=caps["M_NUM"], q_len=caps["Q_LEN"],
                      a_len=caps["A_LEN"], aux=not args.no_aux, value=not args.no_value).to(args.device)
    if args.init:
        net.load_state_dict(torch.load(args.init, map_location=args.device))
    params = sum(p.numel() for p in net.parameters())
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=0.01)
    steps = int(args.epochs * len(train_idx) / args.batch)
    if args.max_steps:
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
            dl = torch.utils.data.DataLoader(BatchSet(A, epoch_batches()), batch_size=None, shuffle=False,
                                             num_workers=args.workers, pin_memory=args.device.startswith("cuda"),
                                             prefetch_factor=4 if args.workers else None)
            yield from dl

    t0 = time.time()
    stream = batch_stream()
    for step in range(steps):
        b = {k: v.to(args.device, non_blocking=True) for k, v in next(stream).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            logits, vlog, aux = net(b)
        loss, parts = M.losses(net, b, logits.float(), vlog.float(), aux.float())
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
                              ("policy_ce", "top1", "value_nll", "death_ece", "aux_mae1")} if ev else {})}), flush=True)
    torch.save(net.state_dict(), os.path.join(args.out, "model.pt"))
    final = evaluate(net, A, val_idx, 512, args.device, amp)
    json.dump({"config": {k: cfg[k] for k in cfg if k != "data_meta"}, "validation": final},
              open(os.path.join(args.out, "eval.json"), "w"), indent=1)
    if final:
        print(json.dumps({"final_val": {k: final[k] for k in ("rows", "policy_ce", "top1", "value_nll", "death_ece")}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
