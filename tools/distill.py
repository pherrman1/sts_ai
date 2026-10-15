"""Distill heart1 into a smaller silverbot NN on captured OOC MCTS tree nodes (STS_OOC_HEART1_CAPTURE rows).

  distill.py prep  REPO SHARDDIR --data *.capture.jsonl.gz [--trim-map] [--procs 8]
      Collate every row once with silverbot's collate_fn into compact tensors, one shard per capture file.
  distill.py train REPO OUTDIR --shards SHARDDIR [--dim 128 --layers 2 --mult 2 --heads 4 --epochs 8 --device cuda]
      Train on seeds with seed % 8 != 7, validate on seed % 8 == 7 (held-out seeds).

Loss: KL(heart1 softmax || student softmax) over each node's valid choice tokens. Reports val KL, top-1 agreement
with heart1, and V4's top-1 agreement with heart1 on the same rows (V4's best source vs heart1's best token; the
two skip encodings count as equal), overall and per screen."""
import argparse, collections, glob, gzip, json, math, os, random, re, sys, time

SECTIONS = (("cards_offered.cards", 96), ("relics_offered", 3), ("potions_offered", 5), ("fixed_actions", 5), ("paths_offered", 7))
WIDTH = sum(w for _, w in SECTIONS)
SCREENS = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}

def setup(repo):
    sys.path.insert(0, repo); sys.path.insert(0, os.path.join(repo, "build"))
    from silverbot import network
    return network

def is_skip(b): return b == 0x30000000 or (((b >> 27) & 7) == 0 and ((b >> 8) & 0xFF) == 5)

def trim(rec):
    y0 = rec["obs.mapY"]
    if y0 < 0: return rec
    keep = [i for i, y in enumerate(rec["obs.map.ys"]) if y >= y0]
    rec = dict(rec)
    for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs"):
        rec[k] = [rec[k][i] for i in keep]
    return rec

def seed_of(path):
    m = re.search(r"-(\d{6,})\.capture", path); return int(m.group(1)) if m else 0

def flatten(d, p=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flatten(v, p + k + "/"))
        else: out[p + k] = v
    return out

def unflatten(flat):
    out = {}
    for k, v in flat.items():
        cur = out; parts = k.split("/")
        for q in parts[:-1]: cur = cur.setdefault(q, {})
        cur[parts[-1]] = v
    return out

def prep_file(args):
    repo, path, outdir, do_trim = args
    import torch
    network = setup(repo)
    rows = []
    with gzip.open(path, "rt") as f:
        for line in f:
            r = json.loads(line)
            if "record" in r: rows.append(r)
    chunks = []
    for i in range(0, len(rows), 2048):
        part = rows[i:i + 2048]
        b = flatten(network.collate_fn([{**(trim(r["record"]) if do_trim else r["record"]), "chosen_idx": 0, "outcome": 0.0}
                                        for r in part]))
        b = {k: v for k, v in b.items() if k not in ("chosen_idx", "outcome", "aux_dest_room")}
        mask = torch.zeros(len(part), WIDTH, dtype=torch.bool); tgt = torch.zeros(len(part), WIDTH)
        for j, r in enumerate(part):
            pos, off = [], 0
            for key, width in SECTIONS:
                pos += list(range(off, off + len(r["record"][key]))); off += width
            assert len(pos) == len(r["logits"]), path
            mask[j, pos] = True; tgt[j, pos] = torch.tensor(r["logits"])
        b["_mask"] = mask; b["_tgt"] = tgt
        b["_screen"] = torch.tensor([r["screen"] for r in part], dtype=torch.int16)
        v4ok = []
        for r in part:
            lg, tb = r["logits"], r["token_bits"]; top = tb[max(range(len(lg)), key=lg.__getitem__)]
            v = r["v4"]; vb = r["src_bits"][max(range(len(v)), key=v.__getitem__)]
            v4ok.append(bool(vb == top or (is_skip(vb) and is_skip(top))))
        b["_v4ok"] = torch.tensor(v4ok)
        chunks.append(b)
    cat = {k: torch.cat([c[k] for c in chunks]) for k in chunks[0]}
    for k, v in cat.items():  # compact storage
        if v.dtype == torch.int32 and v.numel() and v.abs().max() < 32767: cat[k] = v.to(torch.int16)
        elif v.dtype == torch.float32 and k != "_tgt": cat[k] = v.to(torch.float16)
    out = os.path.join(outdir, os.path.basename(path).replace(".capture.jsonl.gz", ".pt"))
    torch.save({"seed": seed_of(path), "rows": len(rows), "data": cat}, out)
    return out, len(rows)

def cmd_prep(a):
    import multiprocessing as mp
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.repo, p, a.out, a.trim_map) for p in sorted(a.data)]
    t0 = time.time(); n = 0
    with mp.get_context("spawn").Pool(a.procs) as pool:
        for out, k in pool.imap_unordered(prep_file, jobs):
            n += k; print(f"{out} {k} rows ({time.time()-t0:.0f}s)", flush=True)
    print("prep done", n, "rows", flush=True)

def cmd_train(a):
    import torch, torch.nn.functional as F
    network = setup(a.repo)
    torch.manual_seed(a.seed); random.seed(a.seed); torch.set_num_threads(a.threads)
    tr, va = [], []
    for p in sorted(glob.glob(os.path.join(a.shards, "*.pt"))):
        s = torch.load(p, weights_only=False); (va if s["seed"] % 8 == 7 else tr).append(s["data"])
    cat = lambda parts: {k: torch.cat([q[k] for q in parts]) for k in parts[0]}
    tr, va = cat(tr), cat(va)
    ntr, nva = len(tr["_tgt"]), len(va["_tgt"])
    print(f"train {ntr} rows, val {nva} rows", flush=True)
    dev = a.device
    def batch(d, idx):
        out = {}
        for k, v in d.items():
            x = v[idx].to(dev, non_blocking=True)
            if x.dtype == torch.int16: x = x.to(torch.int32)
            elif x.dtype == torch.float16: x = x.to(torch.float32)
            out[k] = x
        m, t = out.pop("_mask"), out.pop("_tgt"); out.pop("_screen"); out.pop("_v4ok")
        return unflatten(out), m, t
    H = network.ModelHP(dim=a.dim, n_layers=a.layers, mlp_dim_mult=a.mult, n_heads=a.heads, use_value_head=True)
    net = network.NN(H).to(dev)
    nparam = sum(p.numel() for p in net.parameters()); print("student params", nparam, flush=True)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    steps_per = math.ceil(ntr / a.bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * steps_per, pct_start=0.05)
    def kl_rows(lg, m, t):
        lp = F.log_softmax(lg.masked_fill(~m, -1e9), -1); lt = F.log_softmax(t.masked_fill(~m, -1e9), -1)
        return (lt.exp() * (lt - lp)).masked_fill(~m, 0).sum(-1)
    def evaluate():
        net.eval(); kls, agr = [], []
        with torch.no_grad():
            for i in range(0, nva, 256):
                idx = torch.arange(i, min(i + 256, nva)); b, m, t = batch(va, idx)
                lg = net(b)[0]; kls.append(kl_rows(lg, m, t).cpu())
                agr.append((lg.masked_fill(~m, -1e9).argmax(-1) == t.masked_fill(~m, -1e9).argmax(-1)).cpu())
        net.train(); kls, agr = torch.cat(kls), torch.cat(agr).float()
        per = {}
        for s in va["_screen"].unique().tolist():
            sel = va["_screen"] == s
            per[SCREENS.get(s, str(s))] = (int(sel.sum()), round(kls[sel].mean().item(), 4), round(agr[sel].mean().item(), 4),
                                           round(va["_v4ok"][sel].float().mean().item(), 4))
        return kls.mean().item(), agr.mean().item(), va["_v4ok"].float().mean().item(), per
    os.makedirs(a.out, exist_ok=True); t0 = time.time(); best = None; hist = []
    for ep in range(a.epochs):
        perm = torch.randperm(ntr); tot = 0.0
        for i in range(steps_per):
            b, m, t = batch(tr, perm[i * a.bs:(i + 1) * a.bs])
            loss = kl_rows(net(b)[0], m, t).mean(); opt.zero_grad(set_to_none=True); loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); sched.step(); tot += loss.item() * len(m)
        kl, ag, v4, per = evaluate()
        hist.append({"epoch": ep + 1, "train_kl": tot / ntr, "val_kl": kl, "val_top1": ag, "v4_top1": v4, "sec": round(time.time() - t0)})
        print(f"ep {ep+1} train KL {tot/ntr:.4f} val KL {kl:.4f} top1 {ag:.4f} (V4 {v4:.4f}) {time.time()-t0:.0f}s", flush=True)
        if best is None or kl < best[0]:
            best = (kl, ag, per); torch.save(net.state_dict(), os.path.join(a.out, "student.pt"))
    print("best per screen (n, KL, top1, V4 top1):", json.dumps(best[2]), flush=True)
    json.dump({"args": vars(a), "params": nparam, "train_rows": ntr, "val_rows": nva, "best_val_kl": best[0],
               "best_val_top1": best[1], "per_screen": best[2], "history": hist},
              open(os.path.join(a.out, "summary.json"), "w"), indent=1)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep"); p.add_argument("repo"); p.add_argument("out"); p.add_argument("--data", nargs="+", required=True)
    p.add_argument("--trim-map", action="store_true"); p.add_argument("--procs", type=int, default=8)
    t = sub.add_parser("train"); t.add_argument("repo"); t.add_argument("out"); t.add_argument("--shards", required=True)
    for k, v in (("dim", 128), ("layers", 2), ("mult", 2), ("heads", 4), ("epochs", 8), ("bs", 256), ("threads", 4), ("seed", 0)):
        t.add_argument("--" + k, type=int, default=v)
    t.add_argument("--lr", type=float, default=1e-3); t.add_argument("--wd", type=float, default=0.01); t.add_argument("--device", default="cpu")
    a = ap.parse_args()
    cmd_prep(a) if a.cmd == "prep" else cmd_train(a)
