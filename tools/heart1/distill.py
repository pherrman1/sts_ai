#!/usr/bin/env python3
"""Distill heart1 (recorded token logits) into a smaller silverbot NN.

Trainer of the heart1-distill thread (student C, 2026-10-15), moved into the repo with card-select support.
Input: STS_OOC_HEART1_CAPTURE rows (apps/one_combat/heart1_policy.h), gzipped JSON lines with "record",
teacher "logits" over the record's choice tokens and "token_bits". The 2026-10-15 capture rows also carry
the V4 prior ("v4", "src_bits"); newer rows carry "kind" (node/select) and the serving net's logits ("serve").

usage: distill.py SILVERBOT_REPO OUTDIR --data a.capture.jsonl.gz ... [--dim 64 --layers 2 --mult 2 --heads 4]
  [--trim-map] [--epochs 8] [--device cuda] [--workers 6] [--amp] [--init student.pt] [--select-repeat 1]
Validation = held-out seeds: files whose seed (from "-<seed>.capture" in the name) has seed % --val-mod ==
--val-mod - 1. Loss: KL(teacher softmax || student softmax) over the row's choice tokens (temperature 1).
Reports val KL and top-1 agreement with the teacher per screen and card-select type, and the agreement of
V4 / the serving net where rows carry them. SILVERBOT_REPO is daniel-ziegler/sts_lightspeed built at 84ab3ea
(silverbot.network imports its compiled module). The student exports with export_heart1_weights.py."""
import argparse, collections, gzip, json, os, random, re, sys, time
ap = argparse.ArgumentParser()
ap.add_argument("repo"); ap.add_argument("out"); ap.add_argument("--data", nargs="+", required=True)
ap.add_argument("--dim", type=int, default=128); ap.add_argument("--layers", type=int, default=2)
ap.add_argument("--mult", type=int, default=2); ap.add_argument("--heads", type=int, default=4)
ap.add_argument("--trim-map", action="store_true", help="drop map rows below the current floor")
ap.add_argument("--epochs", type=int, default=8); ap.add_argument("--bs", type=int, default=256)
ap.add_argument("--lr", type=float, default=1e-3); ap.add_argument("--wd", type=float, default=0.01)
ap.add_argument("--threads", type=int, default=4); ap.add_argument("--workers", type=int, default=0)
ap.add_argument("--max-train", type=int, default=0); ap.add_argument("--device", default="cpu")
ap.add_argument("--seed", type=int, default=0); ap.add_argument("--val-mod", type=int, default=8)
ap.add_argument("--amp", action="store_true", help="bf16 autocast forward (TF32 matmuls); loss/metrics fp32")
ap.add_argument("--init", help="start from this student state dict (fine-tune) instead of random weights")
ap.add_argument("--select-repeat", type=int, default=1, help="repeat card-select training rows this often")
a = ap.parse_args()
sys.path.insert(0, a.repo); sys.path.insert(0, os.path.join(a.repo, "build"))
import torch, torch.nn.functional as F
from silverbot import network
torch.set_num_threads(a.threads); torch.manual_seed(a.seed); random.seed(a.seed)
if a.amp: torch.backends.cuda.matmul.allow_tf32 = True; torch.backends.cudnn.allow_tf32 = True
SECTIONS = (("cards_offered.cards", 96), ("relics_offered", 3), ("potions_offered", 5), ("fixed_actions", 5), ("paths_offered", 7))
WIDTH = sum(w for _, w in SECTIONS)
SCREENS = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}
# GameContext::CardSelectScreenType order (include/game/GameContext.h)
SELECTS = ["INVALID", "TRANSFORM", "TRANSFORM_UPGRADE", "UPGRADE", "REMOVE", "DUPLICATE", "OBTAIN", "BOTTLE", "BONFIRE_SPIRITS"]

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

def group_of(r):
    s = r["screen"]
    if s == 4: return "card_select:" + SELECTS[r["record"]["select_screen_type"]].lower()
    return SCREENS.get(s, str(s))

def load(paths):
    rows = []
    for p in paths:
        op = gzip.open if p.endswith(".gz") else open
        with op(p, "rt") as f:
            for line in f:
                r = json.loads(line)
                if "record" not in r or len(r["logits"]) < 2: continue
                rec = r["record"]
                rows.append({"record": trim(rec) if a.trim_map else rec, "logits": r["logits"],
                             "token_bits": r["token_bits"], "v4": r.get("v4"), "src_bits": r.get("src_bits"),
                             "serve": r.get("serve"), "screen": r.get("screen", rec["screen_state"]),
                             "seed": seed_of(p)})
    return rows

files = sorted(a.data)
val_files = [f for f in files if seed_of(f) % a.val_mod == a.val_mod - 1]
train_files = [f for f in files if f not in val_files]
train, val = load(train_files), load(val_files)
if a.max_train: random.shuffle(train); train = train[:a.max_train]
if a.select_repeat > 1: train += [r for r in train if r["screen"] == 4] * (a.select_repeat - 1)
print(f"train {len(train)} rows / {len(train_files)} files, val {len(val)} rows / {len(val_files)} files", flush=True)

def positions(rec):
    pos, off = [], 0
    for key, width in SECTIONS:
        pos += list(range(off, off + len(rec[key]))); off += width
    return pos

def collate(rows):
    b = network.collate_fn([{**r["record"], "chosen_idx": 0, "outcome": 0.0} for r in rows])
    mask = torch.zeros(len(rows), WIDTH, dtype=torch.bool); tgt = torch.full((len(rows), WIDTH), -1e9)
    for i, r in enumerate(rows):
        p = positions(r["record"]); mask[i, p] = True; tgt[i, p] = torch.tensor(r["logits"], dtype=torch.float32)
    return b, mask, tgt

def to_dev(x):
    if isinstance(x, dict): return {k: to_dev(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return type(x)(to_dev(v) for v in x)
    return x.to(a.device, non_blocking=True) if hasattr(x, "to") else x

def loader(rows, shuffle):
    return torch.utils.data.DataLoader(rows, batch_size=a.bs, shuffle=shuffle, collate_fn=collate,
                                       num_workers=a.workers, persistent_workers=a.workers > 0, pin_memory=a.device != "cpu")

H = network.ModelHP(dim=a.dim, n_layers=a.layers, mlp_dim_mult=a.mult, n_heads=a.heads, use_value_head=True)
net = network.NN(H).to(a.device)
if a.init: net.load_state_dict(torch.load(a.init, map_location=a.device))
nparam = sum(p.numel() for p in net.parameters()); print("student params", nparam, flush=True)
opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
train_dl, val_dl = loader(train, True), loader(val, False)
sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * len(train_dl), pct_start=0.05)

def logits_of(b):
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=a.amp and a.device.startswith("cuda")):
        out = net(b)[0]
    return out.float()

def kl_rows(logits, mask, tgt):
    lp = F.log_softmax(logits.masked_fill(~mask, -1e9), -1); lt = F.log_softmax(tgt, -1)
    return (lt.exp() * (lt - lp)).masked_fill(~mask, 0).sum(-1)

def argmax(v): return max(range(len(v)), key=v.__getitem__)

def evaluate():
    net.eval(); kls, agr = [], []
    with torch.no_grad():
        for b, m, t in val_dl:
            b, m, t = to_dev(b), m.to(a.device), t.to(a.device)
            lg = logits_of(b)
            kls += kl_rows(lg, m, t).tolist(); agr += (lg.masked_fill(~m, -1e9).argmax(-1) == t.argmax(-1)).tolist()
    net.train()
    # per group: n, KL, top1, V4 n, V4 top1, serve n, serve top1
    per = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0, 0, 0])
    for r, k, g in zip(val, kls, agr):
        s = per[group_of(r)]; s[0] += 1; s[1] += k; s[2] += g
        top = r["token_bits"][argmax(r["logits"])]
        if r["v4"]:
            vb = r["src_bits"][argmax(r["v4"])]; s[3] += 1; s[4] += (vb == top) or (is_skip(vb) and is_skip(top))
        if r["serve"]:
            s[5] += 1; s[6] += argmax(r["serve"]) == argmax(r["logits"])
    n = len(val)
    tot = (sum(kls) / n, sum(agr) / n)
    rnd = lambda x, d: round(x / d, 4) if d else None
    return tot, {k: {"n": s[0], "kl": rnd(s[1], s[0]), "top1": rnd(s[2], s[0]), "v4_top1": rnd(s[4], s[3]),
                     "serve_top1": rnd(s[6], s[5])} for k, s in sorted(per.items())}

os.makedirs(a.out, exist_ok=True); t0 = time.time(); best = None; hist = []
if a.init:
    (kl, ag), per = evaluate(); print(f"init val KL {kl:.4f} top1 {ag:.4f}", json.dumps(per), flush=True)
    hist.append({"epoch": 0, "val_kl": kl, "val_top1": ag, "per_screen": per})
for ep in range(a.epochs):
    tot = n = 0
    for b, m, t in train_dl:
        b, m, t = to_dev(b), m.to(a.device), t.to(a.device)
        loss = kl_rows(logits_of(b), m, t).mean(); opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); sched.step()
        tot += loss.item() * len(m); n += len(m)
    (kl, ag), per = evaluate()
    hist.append({"epoch": ep + 1, "train_kl": tot / n, "val_kl": kl, "val_top1": ag, "sec": time.time() - t0})
    print(f"ep {ep+1} train KL {tot/n:.4f} val KL {kl:.4f} top1 {ag:.4f} {time.time()-t0:.0f}s", flush=True)
    if best is None or kl < best[0]:
        best = (kl, ag, per); torch.save(net.state_dict(), os.path.join(a.out, "student.pt"))
print("best per group:", json.dumps(best[2]), flush=True)
json.dump({"args": vars(a), "params": nparam, "train_rows": len(train), "val_rows": len(val),
           "best_val_kl": best[0], "best_val_top1": best[1], "per_screen": best[2], "history": hist},
          open(os.path.join(a.out, "summary.json"), "w"), indent=1)
