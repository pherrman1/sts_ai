#!/usr/bin/env python3
"""Learned combat-state encoder for the Silver root prior (follows ledger §400).

Reads the §397 silversynthgen corpus directly (each root's BattleStateWire and
its flat-10k edge statistics), tokenizes the state (cards by zone, monsters,
potions, player statuses, relics, one player/context token), and trains a
small transformer whose per-action logits are fitted to the 10k visit shares
with a per-root softmax cross-entropy (as §400). Actions point at the tokens
they use (the played card, its target, the potion slot, selected cards).

Folds, test roots, teacher and replay harness are the §400 ones, so the
encoder is compared with v1/v2/plain on the same 4,094 test roots.

  build CORPUS_DIR OUT_DIR             tokenize every root row
  train OUT_DIR                        train, early-stop on fold 3
  fit OUT_DIR ROOTS_TEST.json          top-1 on fold 4 (all / agree roots)
  tasks CORPUS_DIR OUT_DIR val|test V2_ROOTS_DIR
  pickweight OUT_DIR
  report OUT_DIR
"""
import glob
import gzip
import json
import math
import os
import pickle
import sys
from multiprocessing import Pool

import numpy as np

BASE = {"natural": 56000000, "perturbed": 56002000}
TEST, VAL = 4, 3
WEIGHTS = [200, 400, 800, 1600, 3200]
BUDGETS = [256, 1000, 2000]
REPLAY_SEEDS = [11, 12]
BOOT = 2000

# Token kinds and card zones.
K_CTX, K_CARD, K_MON, K_POT, K_STATUS, K_RELIC = range(6)
Z_HAND, Z_DRAW, Z_DRAW_TOP, Z_DRAW_BOTTOM, Z_DISCARD, Z_EXHAUST, Z_OPTION = range(1, 8)
SOURCE_ZONES = {1: (Z_HAND,), 2: (Z_DRAW, Z_DRAW_TOP, Z_DRAW_BOTTOM), 3: (Z_DISCARD,), 4: (Z_EXHAUST,),
                5: (Z_OPTION,)}
NUM = 24          # numeric slots per token
MAX_SEL = 8       # selected cards per action


def sl(x):
    """Signed log scaling for counts and hit points."""
    return math.copysign(math.log1p(abs(x)), x)


def fold(seed, variant):
    return (seed - BASE[variant]) % 5


def card_token(c, zone):
    num = [c["cost"], c["costForTurn"], float(c["upgraded"]), float(c["retain"]), float(c["freeToPlayOnce"]),
           sl(c["specialData"])]
    return (K_CARD, c["id"], zone, num)


def tokenize(w):
    """Tokens: (kind, id, sub, numeric list). Returns tokens and card uniqueId -> token index by zone."""
    p = w["player"]
    toks = []
    ctx = [sl(p["curHp"]), sl(p["maxHp"]), p["curHp"] / max(1, p["maxHp"]), sl(p["block"]), p["energy"],
           p["energyPerTurn"], p["strength"], p["dexterity"], p["artifact"], p["cardsPlayedThisTurn"],
           p["attacksPlayedThisTurn"], p["skillsPlayedThisTurn"], p["cardsDiscardedThisTurn"], sl(w["turn"]),
           p["cardDrawPerTurn"], w["act"], w["inputState"], w["potionCapacity"], sl(p["timesDamagedThisCombat"]),
           float(w["endTurnQueued"]), w["cardSelect"]["pickCount"], float(w["cardSelect"]["canPickZero"]),
           float(w["cardSelect"]["canPickAnyNumber"]), sl(len(w["drawPile"]["unknown"]))]
    toks.append((K_CTX, w["cardSelect"]["task"], p["stance"], ctx))
    uid = {}
    def add_card(c, zone):
        uid.setdefault((zone, c["uniqueId"]), len(toks))
        toks.append(card_token(c, zone))
    for c in w["hand"]:
        add_card(c, Z_HAND)
    for key, zone in (("unknown", Z_DRAW), ("knownTop", Z_DRAW_TOP), ("knownBottom", Z_DRAW_BOTTOM)):
        for c in w["drawPile"][key]:
            add_card(c, zone)
    for pile, zone in (("discardPile", Z_DISCARD), ("exhaustPile", Z_EXHAUST)):
        for key in ("unknown", "knownTop", "knownBottom"):
            for c in w[pile][key]:
                add_card(c, zone)
    options = {}
    if w["cardSelect"]["task"] != 0:
        for i, cid in enumerate(w["cardSelect"]["cards"]):
            if cid:
                options[i] = len(toks)
                toks.append((K_CARD, cid, Z_OPTION, [0.0] * 6))
    mons = {}
    for m in w["monsters"][:w["monsterCount"]]:
        if m["idx"] < 0:
            continue
        mons[m["idx"]] = len(toks)
        num = [sl(m["curHp"]), sl(m["maxHp"]), m["curHp"] / max(1, m["maxHp"]), sl(m["block"]), m["strength"],
               m["vulnerable"], m["weak"], float(m["halfDead"]), float(m["escapeNext"]), float(m["curHp"] > 0),
               sl(m["uniquePower0"]), sl(m["uniquePower1"])] + [sl(x) for x in m["smallPowers"]]
        toks.append((K_MON, m["id"], m["moveHistory"][0], num + [m["moveHistory"][1]]))
    pots = {}
    for slot, pid in enumerate(w["potions"]):
        pots[slot] = len(toks)
        toks.append((K_POT, pid, slot, []))
    for sid, amount in p["statusMap"]:
        toks.append((K_STATUS, sid, 0, [sl(amount)]))
    for word, bits in enumerate((p["relicBits0"], p["relicBits1"])):
        for b in range(64):
            if bits >> b & 1:
                toks.append((K_RELIC, word * 64 + b, 0, []))
    return toks, uid, options, mons, pots


def parse_semantic(s):
    out = {}
    for part in s.split("/")[1:]:
        k, _, v = part.partition("=")
        out[k] = v
    return out


def card_uid(fp):
    return int(fp.split("_")[1])


def action_row(sem, uid, options, mons, pots, tokens):
    """[type, ptr_card, ptr_target, ptr_potion, discard, skip, task, sel ptrs...]; -1 = none."""
    a = parse_semantic(sem)
    t, src = int(a["t"]), int(a["s"])
    card = ptr_tgt = ptr_pot = -1
    if t in (1, 3, 4) and a["c"] and not a["c"].startswith("0_0_"):
        u = card_uid(a["c"])
        for z in SOURCE_ZONES.get(src, ()):
            if (z, u) in uid:
                card = uid[(z, u)]
                break
    if src == 5 and int(a["o"]) != 0:
        oid = int(a["o"])
        card = next((i for i in options.values() if tokens[i][1] == oid), -1)
    x = int(a["x"])
    if x >= 0 and x in mons:
        ptr_tgt = mons[x]
    pid, _, pslot = a["p"].partition("_")
    if t == 2 and int(pslot) in pots:
        ptr_pot = pots[int(pslot)]
    sel = []
    if a["sel"]:
        for fp in a["sel"].split("+"):
            u = card_uid(fp)
            for z in SOURCE_ZONES.get(src, ()) or (Z_HAND,):
                if (z, u) in uid:
                    sel.append(uid[(z, u)])
                    break
    sel = (sel + [-1] * MAX_SEL)[:MAX_SEL]
    missing = (t in (1,) and card < 0) or (t == 2 and ptr_pot < 0)
    return [t, card, ptr_tgt, ptr_pot, int(a["d"]), int(a["k"]), int(a["task"])] + sel, missing


def teacher(edges, second):
    q2 = {e["bits"]: e["q"] for e in (second or [])}
    t = []
    for e in edges:
        qs = [q for q in (e.get("q"), q2.get(e["bits"])) if q is not None]
        t.append(float(np.mean(qs)) if qs else None)
    low = min(x for x in t if x is not None)
    return [low if x is None else x for x in t]


def build_file(args):
    path, out_dir = args
    roots, missing = [], 0
    for line in gzip.open(path, "rt"):
        if '"kind":"root"' not in line:
            continue
        r = json.loads(line)
        if r.get("wire") is None or len(r["edges"]) < 2:
            continue
        toks, uid, options, mons, pots = tokenize(r["wire"])
        acts = []
        bad = False
        for e in r["edges"]:
            row, miss = action_row(e["semantic"], uid, options, mons, pots, toks)
            bad |= miss
            acts.append(row)
        missing += bad
        v = np.array([e["visits"] for e in r["edges"]], dtype=np.float32)
        second = r.get("second")
        roots.append({
            "rid": f'{r["variant"]}|{r["seed"]}|{r["fight"]}|{r["decision"]}',
            "fold": fold(r["seed"], r["variant"]), "variant": r["variant"], "seed": r["seed"],
            "kind": np.array([t[0] for t in toks], np.int8), "id": np.array([t[1] for t in toks], np.int16),
            "sub": np.array([t[2] for t in toks], np.int16),
            "num": np.array([(t[3] + [0.0] * NUM)[:NUM] for t in toks], np.float16),
            "act": np.array(acts, np.int16), "y": v / max(v.sum(), 1),
            "y2": None if not second else np.array(
                [next((s["visits"] for s in second if s["bits"] == e["bits"]), 0) for e in r["edges"]],
                np.float32),
            "bits": [e["bits"] for e in r["edges"]], "teacher": teacher(r["edges"], second),
        })
    name = os.path.basename(path).replace(".jsonl.gz", ".pkl")
    pickle.dump(roots, open(os.path.join(out_dir, name), "wb"))
    return name, len(roots), missing


def cmd_build(corpus_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(corpus_dir, "*.jsonl.gz")))
    with Pool(4) as pool:
        res = pool.map(build_file, [(f, out_dir) for f in files])
    summary = {"files": len(res), "roots": sum(r[1] for r in res), "rootsWithUnresolvedAction": sum(r[2] for r in res)}
    json.dump(summary, open(os.path.join(out_dir, "build.json"), "w"), indent=2)
    print(json.dumps(summary))


def load_roots(out_dir):
    roots = []
    for f in sorted(glob.glob(os.path.join(out_dir, "*.pkl"))):
        roots.extend(pickle.load(open(f, "rb")))
    return roots


# ---------------------------------------------------------------- model

ID_OFF = {K_CTX: 0, K_CARD: 64, K_MON: 640, K_POT: 832, K_STATUS: 960, K_RELIC: 1472}
ID_CAP = {K_CTX: 63, K_CARD: 575, K_MON: 191, K_POT: 127, K_STATUS: 511, K_RELIC: 127}
SUB_OFF = {K_CTX: 0, K_CARD: 16, K_MON: 32, K_POT: 544, K_STATUS: 560, K_RELIC: 561}
SUB_CAP = {K_CTX: 15, K_CARD: 15, K_MON: 511, K_POT: 15, K_STATUS: 0, K_RELIC: 0}
N_ID, N_SUB = 1600, 562
A_FIX = 7


def collate(batch):
    import torch
    T = max(len(r["kind"]) for r in batch)
    A = max(len(r["act"]) for r in batch)
    B = len(batch)
    kind = np.zeros((B, T), np.int64)
    ids = np.zeros((B, T), np.int64)
    sub = np.zeros((B, T), np.int64)
    num = np.zeros((B, T, NUM), np.float32)
    pad = np.ones((B, T), bool)
    act = np.full((B, A, A_FIX + MAX_SEL), -1, np.int64)
    amask = np.zeros((B, A), bool)
    y = np.zeros((B, A), np.float32)
    for b, r in enumerate(batch):
        n = len(r["kind"])
        k = r["kind"].astype(np.int64)
        kind[b, :n] = k
        off = np.array([ID_OFF[x] for x in k])
        cap = np.array([ID_CAP[x] for x in k])
        ids[b, :n] = off + np.clip(r["id"].astype(np.int64), 0, cap)
        soff = np.array([SUB_OFF[x] for x in k])
        scap = np.array([SUB_CAP[x] for x in k])
        sub[b, :n] = soff + np.clip(r["sub"].astype(np.int64), 0, scap)
        num[b, :n] = r["num"]
        pad[b, :n] = False
        m = len(r["act"])
        act[b, :m] = r["act"]
        amask[b, :m] = True
        y[b, :m] = r["y"]
    t = torch.from_numpy
    return t(kind), t(ids), t(sub), t(num), t(pad), t(act), t(amask), t(y)


def make_model(d=128, layers=3, heads=4):
    import torch
    import torch.nn as nn

    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.kind = nn.Embedding(6, d)
            self.id = nn.Embedding(N_ID, d)
            self.sub = nn.Embedding(N_SUB, d)
            self.num = nn.Linear(NUM, d)
            layer = nn.TransformerEncoderLayer(d, heads, 2 * d, dropout=0.0, batch_first=True, norm_first=True)
            self.enc = nn.TransformerEncoder(layer, layers)
            self.norm = nn.LayerNorm(d)
            self.atype = nn.Embedding(8, d)
            self.atask = nn.Embedding(32, d)
            self.flags = nn.Linear(2, d)
            self.roles = nn.ModuleList([nn.Linear(d, d, bias=False) for _ in range(4)])
            self.head = nn.Sequential(nn.Linear(2 * d, 2 * d), nn.GELU(), nn.Linear(2 * d, d), nn.GELU(),
                                      nn.Linear(d, 1))

        def forward(self, kind, ids, sub, num, pad, act, amask):
            x = self.kind(kind) + self.id(ids) + self.sub(sub) + self.num(num)
            h = self.norm(self.enc(x, src_key_padding_mask=pad))
            B, A, _ = act.shape
            hz = torch.cat([h, torch.zeros(B, 1, h.shape[-1])], 1)   # index T = "none"
            T = h.shape[1]
            def gather(ptr):
                idx = torch.where(ptr < 0, torch.full_like(ptr, T), ptr)
                return torch.gather(hz, 1, idx.unsqueeze(-1).expand(-1, -1, h.shape[-1]))
            a = self.atype(act[..., 0].clamp(0, 7)) + self.atask(act[..., 6].clamp(0, 31))
            a = a + self.flags(act[..., 4:6].float())
            a = a + self.roles[0](gather(act[..., 1])) + self.roles[1](gather(act[..., 2]))
            a = a + self.roles[2](gather(act[..., 3]))
            sel = act[..., A_FIX:]
            cnt = (sel >= 0).sum(-1, keepdim=True).clamp(min=1).float()
            sel_h = torch.stack([gather(sel[..., j]) for j in range(sel.shape[-1])], -2).sum(-2) / cnt
            a = a + self.roles[3](sel_h)
            ctx = h[:, :1].expand(-1, A, -1)
            logit = self.head(torch.cat([ctx, a], -1)).squeeze(-1)
            return logit.masked_fill(~amask, -1e9)

    return Encoder()


def batches(roots, size, shuffle, rng=None):
    order = np.arange(len(roots))
    if shuffle:
        rng.shuffle(order)
    for i in range(0, len(order), size):
        yield [roots[j] for j in order[i:i + size]]


def evaluate(model, roots):
    import torch
    model.eval()
    ce = top = agree_top = agree_n = 0.0
    with torch.no_grad():
        for batch in batches(roots, 512, False):
            kind, ids, sub, num, pad, act, amask, y = collate(batch)
            logit = model(kind, ids, sub, num, pad, act, amask)
            logp = torch.log_softmax(logit, -1)
            ce += float(-(y * logp.masked_fill(~amask, 0)).sum())
            pick = logit.argmax(-1).numpy()
            for b, r in enumerate(batch):
                hit = pick[b] == int(np.argmax(r["y"]))
                top += hit
                if r["y2"] is not None and int(np.argmax(r["y2"])) == int(np.argmax(r["y"])):
                    agree_n += 1
                    agree_top += hit
    model.train()
    return {"ce": ce / len(roots), "top1": top / len(roots), "agreeTop1": agree_top / max(agree_n, 1),
            "agreeRoots": int(agree_n)}


def cmd_train(out_dir, epochs="30", d="128", layers="3", lr="1e-3"):
    import torch
    torch.manual_seed(1)
    torch.set_num_threads(4)
    rng = np.random.default_rng(1)
    roots = load_roots(out_dir)
    tr = [r for r in roots if r["fold"] in (0, 1, 2)]
    va = [r for r in roots if r["fold"] == VAL]
    model = make_model(int(d), int(layers))
    opt = torch.optim.AdamW(model.parameters(), lr=float(lr), weight_decay=0.01)
    steps = int(epochs) * math.ceil(len(tr) / 256)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=float(lr), total_steps=steps, pct_start=0.05)
    best, best_ep, log = None, -1, []
    for ep in range(int(epochs)):
        tot = 0.0
        for batch in batches(tr, 256, True, rng):
            kind, ids, sub, num, pad, act, amask, y = collate(batch)
            logit = model(kind, ids, sub, num, pad, act, amask)
            loss = -(y * torch.log_softmax(logit, -1).masked_fill(~amask, 0)).sum(-1).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += float(loss) * len(batch)
        ev = evaluate(model, va)
        ev.update(epoch=ep, trainCe=tot / len(tr))
        log.append(ev)
        print(json.dumps(ev), flush=True)
        if best is None or ev["ce"] < best:
            best, best_ep = ev["ce"], ep
            torch.save(model.state_dict(), os.path.join(out_dir, "encoder.pt"))
    json.dump({"train": len(tr), "val": len(va), "bestEpoch": best_ep, "bestValCe": best,
               "config": {"epochs": int(epochs), "d": int(d), "layers": int(layers), "lr": float(lr)},
               "log": log}, open(os.path.join(out_dir, "train-encoder.json"), "w"), indent=2)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"build": cmd_build, "train": cmd_train}[cmd](*args)
