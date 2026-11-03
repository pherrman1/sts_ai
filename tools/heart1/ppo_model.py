"""Self-contained torch mirror of the native heart1 forward (apps/one_combat/heart1_policy.cpp) for PPO.

No silverbot import: the record featurisation and the transformer follow Net::forwardRecord token by token, so a
checkpoint in the native .bin format loads here, trains, and exports back to .bin for the C++ actors.

The decision net (S0, Philipp 2026-11-01) is heart1-size (d256, 4 layers, 8 heads) with every optional input:
- student inputs x_deck_misc, x_relic_counter, x_act (tools/heart1/student_inputs.py);
- v2 inputs x2_run, x2_fought, x2_price (#941);
- PPO coverage tokens: fixed-action ids 166..177 (potion discard, Match and Keep, unmapped event options) and the
  potion table on discard tokens (FixedChoice::potion).
Inputs a checkpoint lacks are added zero-initialised (the fixed-action table is padded with zero rows), so the
extended net reproduces the source checkpoint exactly until trained. Export always writes the full set.

    net = PolicyNet.from_bin("heart1.bin")             # or student_sel.bin (d64, trim_map)
    feats = [featurize(rec) for rec in records]         # once per record
    batch = collate(feats)
    logits, value = net(batch)                          # logits (B, C) with -inf padding, value (B,)
    net.to_bin("out.bin")

Parity: `python3 tools/heart1/ppo_model.py score NET.bin records.jsonl out.jsonl` writes {"logits", "value"} per
record line (a bare record or a row with "record"), the same shape as `one_combat heart1score`.
"""
import json
import os
import math
import struct
import sys
from collections import OrderedDict

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

MAGIC = b"HEART1W\x01"
NORM_EPS = 1e-5
MAP_AGG_CAP = 15
LIMIT = 999
FA_COUNT = 178            # heart1_policy.h kFaCount
FA_PPO_FIRST = 166        # kFaDiscardPotion
ROOM_ELITE, ROOM_REST = None, None   # set from the engine enum below
FOUGHT_ROWS = 80
MAX_FOUGHT = 32   # native kMaxFoughtEncounters (#946): only the first 32 fought encounters are embedded
RUN_COUNTERS = 2

# include/constants/Rooms.h Room enum order (heart1_policy.cpp reads static_cast<int>(Room::ELITE / REST)).
ROOMS = ["SHOP", "REST", "EVENT", "ELITE", "MONSTER", "TREASURE", "BOSS", "BOSS_TREASURE", "NONE", "INVALID"]

O = "obs_embed.component_embeddings."
FO = O + "fixed_obs.scalar_embedding.component_embeddings."
M = O + "map_nodes.element_embedding.component_embeddings."
C = "choice_embed.component_embeddings."
FX = C + "fixed.element_embedding.component_embeddings."
PA = C + "paths.element_embedding.component_embeddings."

# Embedding tables (name -> short key) and FixedVec embeddings (prefix -> (short key, features)).
TABLES = OrderedDict([
    ("card", O + "deck.element_embedding.component_embeddings.0.embedding.weight"),
    ("upgrade", O + "deck.element_embedding.component_embeddings.1.weight"),
    ("relic", O + "relics.element_embedding.embedding.weight"),
    ("potion", O + "potions.element_embedding.embedding.weight"),
    ("boss", FO + "boss.weight"),
    ("ascension", FO + "ascension.weight"),
    ("key_ruby", FO + "key_ruby.weight"),
    ("key_emerald", FO + "key_emerald.weight"),
    ("key_sapphire", FO + "key_sapphire.weight"),
    ("screen", FO + "screen_state.embedding.weight"),
    ("map_room", M + "room.embedding.weight"),
    ("is_current", M + "is_current.embedding.weight"),
    ("reachable", M + "reachable.embedding.weight"),
    ("burning", M + "burning.weight"),
    ("obs_pos", "obs_embed.position_embedding.weight"),
    ("select_screen", C + "cards.element_embedding.component_embeddings.2.embedding.weight"),
    ("fixed_action", FX + "action.embedding.weight"),
    ("info", FX + "info.embedding.weight"),
    ("path_room", PA + "room.embedding.weight"),
    ("reaches_burn", PA + "reaches_burn.weight"),
    ("choice_pos", "choice_embed.position_embedding.weight"),
    ("x_act", "x_act.weight"),
    ("x2_fought", "x2_fought.weight"),
])
FIXEDVECS = OrderedDict([
    ("fixed_obs", (FO + "fixed_observation", 5)),
    ("pos", (M + "pos", 2)),
    ("path_xs", (M + "path_xs", 3)),
    ("rel", (M + "rel", 2)),
    ("agg", (M + "agg", 3)),
    ("gold", (FX + "gold", 1)),
    ("path_x", (PA + "x", 1)),
    ("cone", (PA + "cone", 3)),
    ("x_deck_misc", ("x_deck_misc", 1)),
    ("x_relic_counter", ("x_relic_counter", 1)),
    ("x2_run", ("x2_run", RUN_COUNTERS)),
    ("x2_price", ("x2_price", 1)),
])
# Optional inputs a net has only when built with them (ppo_model.construct(inputs=...), or a .bin that holds
# them): featurize always emits them, the trunk adds those its net has. x3_deck = the arch screen's IN_DECK.
X3_DECK_COUNT = 10
OPTIONAL_FIXEDVECS = OrderedDict([("x3_deck", ("x3_deck", X3_DECK_COUNT))])
ALL_FIXEDVECS = OrderedDict(list(FIXEDVECS.items()) + list(OPTIONAL_FIXEDVECS.items()))
TABLE_INDEX = {k: i for i, k in enumerate(TABLES)}
TABLE_NAMES = list(TABLES)
ZERO_INIT_TABLES = {"x_act": 5, "x2_fought": FOUGHT_ROWS}
ZERO_INIT_FIXEDVECS = {"x_deck_misc", "x_relic_counter", "x2_run", "x2_price"}
# silverbot's EmbedCache duplicates (export_heart1_weights.py SHARED): written on export for completeness.
SHARED_ALIASES = {
    "card": [C + "cards.element_embedding.component_embeddings.0.embedding.weight", FX + "card.embedding.weight"],
    "upgrade": [C + "cards.element_embedding.component_embeddings.1.weight"],
    "relic": [C + "relics.element_embedding.embedding.weight", FX + "relic.embedding.weight"],
    "potion": [C + "potions.element_embedding.embedding.weight"],
}


def read_bin(path):
    out = OrderedDict()
    with open(path, "rb") as f:
        if f.read(8) != MAGIC:
            raise ValueError(f"{path}: bad magic")
        (n,) = struct.unpack("<I", f.read(4))
        for _ in range(n):
            (length,) = struct.unpack("<I", f.read(4))
            name = f.read(length).decode()
            (ndim,) = struct.unpack("<I", f.read(4))
            shape = struct.unpack(f"<{ndim}I", f.read(4 * ndim)) if ndim else ()
            count = 1
            for d in shape:
                count *= d
            data = torch.frombuffer(bytearray(f.read(4 * count)), dtype=torch.float32).reshape(shape)
            out[name] = data.clone()
    return out


def write_bin(path, tensors):
    with open(path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<I", len(tensors)))
        for name, t in tensors.items():
            data = t.detach().to(torch.float32).contiguous().cpu()
            enc = name.encode()
            f.write(struct.pack("<I", len(enc)))
            f.write(enc)
            f.write(struct.pack("<I", data.dim()))
            f.write(struct.pack(f"<{data.dim()}I", *data.shape))
            f.write(data.numpy().astype("<f4").tobytes())


def _key(name):
    return name.replace(".", "__")


# ---------------------------------------------------------------- featurisation (Net::forwardRecord)

def _clamp(v, lo, hi):
    return float(min(max(int(v), lo), hi))


def trimmed_map(rec):
    """distill.py trim(): drop the map rows below the current floor (Net::forward for trim_map nets)."""
    y0 = rec["obs.mapY"]
    keep = [j for j, y in enumerate(rec["obs.map.ys"]) if y >= y0]
    r = dict(rec)
    for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs"):
        r[k] = [rec[k][j] for j in keep]
    return r


def map_dag_features(rec):
    """mapDagFeatures: per map row minE/maxE/dR/reach, per path option destination room, cone and burn reach."""
    xs, ys, rooms, pxs = rec["obs.map.xs"], rec["obs.map.ys"], rec["obs.map.roomTypes"], rec["obs.map.pathXs"]
    n = len(xs)
    idx = {}
    for j in range(n):
        idx.setdefault((xs[j], ys[j]), j)
    succ = [[] for _ in range(n)]
    for j in range(n):
        for e in pxs[j]:
            k = idx.get((e, ys[j] + 1), -1)
            if e >= 0 and k >= 0:
                succ[j].append(k)
    elite, rest = ROOMS.index("ELITE"), ROOMS.index("REST")
    minE, maxE, dR = [0] * n, [0] * n, [MAP_AGG_CAP] * n
    order = sorted(range(n), key=lambda j: -ys[j])   # stable, as std::stable_sort
    for j in order:
        e = 1 if rooms[j] == elite else 0
        mn = mx = 0
        dr = None
        if succ[j]:
            mn = min(minE[k] for k in succ[j]); mx = max(maxE[k] for k in succ[j]); dr = min(dR[k] for k in succ[j])
        minE[j] = e + mn
        maxE[j] = e + mx
        if rooms[j] == rest:
            dR[j] = 0
        elif succ[j]:
            dR[j] = min(MAP_AGG_CAP, 1 + dr)
    reaches_burn = [False] * n
    bx, by = rec.get("obs.map.burningEliteX", -1), rec.get("obs.map.burningEliteY", -1)
    bn = idx.get((bx, by), -1) if bx >= 0 else -1
    if bn >= 0:
        for j in order:
            reaches_burn[j] = j == bn or any(reaches_burn[k] for k in succ[j])
    cur = idx.get((rec["obs.mapX"], rec["obs.mapY"]), -1)
    frontier = list(succ[cur]) if cur >= 0 else [j for j in range(n) if ys[j] == 0]
    for px in rec["paths_offered"]:
        k = idx.get((px, rec["obs.mapY"] + 1), -1)
        if k >= 0 and k not in frontier:
            frontier.append(k)
    reach = [False] * n
    stack = list(frontier)
    while stack:
        j = stack.pop()
        if not reach[j]:
            reach[j] = True
            stack.extend(succ[j])
    dest, cone, burn = [], [], []
    for px in rec["paths_offered"]:
        k = idx.get((px, rec["obs.mapY"] + 1), -1)
        dest.append(rooms[k] if k >= 0 else 0)
        cone.append((minE[k], maxE[k], dR[k]) if k >= 0 else (0, 0, MAP_AGG_CAP))
        burn.append(1 if k >= 0 and reaches_burn[k] else 0)
    return minE, maxE, dR, reach, dest, cone, burn


X3_CARD_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "x3_card_table.json")
_card_table = None


def _cards():
    """The engine's per-card facts (`one_combat heart1cardtable`, committed as x3_card_table.json)."""
    global _card_table
    if _card_table is None:
        with open(X3_CARD_TABLE) as f:
            t = json.load(f)
        if t.get("schema") != "heart1-x3-card-table-v1":
            raise ValueError(f"{X3_CARD_TABLE}: schema {t.get('schema')}")
        _card_table = t["cards"]
    return _card_table


def _rounded_percent(num, den):
    return (200 * num + den) // (2 * den) if den > 0 else 0


def deck_aggregates(rec):
    """x3_deck inputs (mirror of heart1_policy.cpp deckAggregates): attacks, skills, powers, starter
    Strikes+Defends, exhausting cards, drawing cards, upgraded share (percent), mean energy cost of cards with
    cost >= 0 (x100), deck size, curses; integers clamped to [-1, 999]."""
    cards = _cards()
    a = sk = pw = st = ex = dr = upg = cost_sum = costed = cu = 0
    ids, ups = rec["obs.deck.cards"], rec["obs.deck.upgrades"]
    for i, cid in enumerate(ids):
        if not 0 <= cid < len(cards):
            continue
        c = cards[cid]
        up = 1 if i < len(ups) and ups[i] != 0 else 0
        t = c["type"]
        a += t == "ATTACK"; sk += t == "SKILL"; pw += t == "POWER"; cu += t == "CURSE"
        st += bool(c["starter"]); ex += bool(c["exhaust"][up]); dr += bool(c["draws"]); upg += up
        if c["cost"][up] >= 0:
            cost_sum += c["cost"][up]; costed += 1
    v = [a, sk, pw, st, ex, dr, _rounded_percent(upg, len(ids)), _rounded_percent(cost_sum, costed), len(ids), cu]
    return [_clamp(x, -1, LIMIT) for x in v]


def featurize(rec, trim_map=False):
    """One record -> token component lists. Every token is a sum of table rows and FixedVec projections.

    Returns {"n": tokens, "n_obs": observation tokens, "n_choice": choice tokens,
             "emb": int16 array (k, 3) of (table index in TABLES, token, row),
             "fv": {fixedvec: (int16 tokens (k,), float32 features (k, width))}}.
    Packed numpy arrays keep a featurised record at a few KB (Python tuples cost ~100 KB per record, 22 GB of host
    RAM for 2,048 games in the 3060 Ti bench).
    All optional inputs are listed; the net adds those it has (zero-initialised ones add exactly zero)."""
    if trim_map and rec["obs.mapY"] >= 0:
        rec = trimmed_map(rec)
    emb, fv = {}, {}
    t = [0]

    def e(table, row, tok=None):
        emb.setdefault(table, []).append((t[0] if tok is None else tok, int(row)))

    def f(name, feats, tok=None):
        fv.setdefault(name, []).append((t[0] if tok is None else tok, [float(x) for x in feats]))

    fo = rec["obs.fixed_observation"]
    misc = rec.get("obs.deck.misc") or []
    counters = rec.get("obs.relics.relic_counters") or []
    for i, (cid, up) in enumerate(zip(rec["obs.deck.cards"], rec["obs.deck.upgrades"])):
        e("card", cid); e("upgrade", up); e("obs_pos", 0)
        f("x_deck_misc", [_clamp(misc[i] if i < len(misc) else 0, -1, LIMIT)])
        t[0] += 1
    for i, rid in enumerate(rec["obs.relics.relics"]):
        e("relic", rid); e("obs_pos", 1)
        f("x_relic_counter", [_clamp(counters[i] if i < len(counters) else 0, -1, LIMIT)])
        t[0] += 1
    for pid in rec["obs.potions"]:
        e("potion", pid); e("obs_pos", 2); t[0] += 1
    f("fixed_obs", [fo[0], fo[1], fo[2], fo[3], fo[5]])
    e("boss", fo[4]); e("ascension", fo[6]); e("key_ruby", fo[7]); e("key_emerald", fo[8]); e("key_sapphire", fo[9])
    e("screen", rec["screen_state"]); e("obs_pos", 3)
    e("x_act", int(_clamp(rec.get("obs.act", 0) or 0, 0, 4)))
    run = rec.get("obs.v2.run_counters") or []
    f("x2_run", [_clamp(run[k] if k < len(run) else -1, -1, LIMIT) for k in range(RUN_COUNTERS)])
    for enc in (rec.get("obs.v2.fought") or [])[:MAX_FOUGHT]:
        e("x2_fought", enc)
    f("x3_deck", deck_aggregates(rec))
    t[0] += 1
    minE, maxE, dR, reach, dest, cone, burn = map_dag_features(rec)
    mx_, my_ = rec["obs.mapX"], rec["obs.mapY"]
    bx, by = rec.get("obs.map.burningEliteX", -1), rec.get("obs.map.burningEliteY", -1)
    for j, (x, y, room, pxs) in enumerate(zip(rec["obs.map.xs"], rec["obs.map.ys"], rec["obs.map.roomTypes"],
                                              rec["obs.map.pathXs"])):
        e("map_room", room); e("is_current", 1 if (x == mx_ and y == my_) else 0)
        f("pos", [x, y]); f("path_xs", pxs); f("rel", [x - mx_, y - my_])
        e("reachable", 1 if reach[j] else 0)
        f("agg", [minE[j] / MAP_AGG_CAP, maxE[j] / MAP_AGG_CAP, dR[j] / MAP_AGG_CAP])
        e("burning", 1 if (bx >= 0 and x == bx and y == by) else 0)
        e("obs_pos", 4)
        t[0] += 1
    n_obs = t[0]
    prices = rec.get("offer_prices") or []
    pi = [0]

    def price():
        i = pi[0]; pi[0] += 1
        if i < len(prices) and prices[i] >= 0:
            f("x2_price", [_clamp(prices[i], -1, LIMIT)])

    for cid, up in zip(rec["cards_offered.cards"], rec["cards_offered.upgrades"]):
        e("card", cid); e("upgrade", up); e("select_screen", rec["select_screen_type"]); e("choice_pos", 0)
        price(); t[0] += 1
    for rid in rec["relics_offered"]:
        e("relic", rid); e("choice_pos", 1); price(); t[0] += 1
    for pid in rec["potions_offered"]:
        e("potion", pid); e("choice_pos", 2); price(); t[0] += 1
    for fa in rec["fixed_actions"]:
        e("fixed_action", fa["action"]); f("gold", [fa.get("gold", 0)])
        e("card", fa.get("card", 0)); e("relic", fa.get("relic", 180)); e("info", fa.get("info", 0))
        if fa.get("potion", -1) >= 0:
            e("potion", fa["potion"])
        e("choice_pos", 3)
        t[0] += 1
    for k, px in enumerate(rec["paths_offered"]):
        f("path_x", [px]); e("path_room", dest[k]); f("cone", [c / MAP_AGG_CAP for c in cone[k]])
        e("reaches_burn", burn[k]); e("choice_pos", 4)
        t[0] += 1
    packed = np.array([(TABLE_INDEX[name], tok, row) for name, items in emb.items() for tok, row in items],
                      dtype=np.int16).reshape(-1, 3)
    fvp = {name: (np.array([tok for tok, _ in items], dtype=np.int16),
                  np.array([x for _, x in items], dtype=np.float32).reshape(len(items), -1))
           for name, items in fv.items()}
    return {"n": t[0], "n_obs": n_obs, "n_choice": t[0] - n_obs, "emb": packed, "fv": fvp}


def collate(feats):
    """Batch featurised records: flat (token, row) index tensors per table, padding masks, choice positions."""
    B = len(feats)
    T = max(x["n"] for x in feats)
    Cn = max(max(x["n_choice"] for x in feats), 1)
    allemb = np.concatenate([x["emb"].astype(np.int64) + np.array([0, b * T, 0]) for b, x in enumerate(feats)])
    emb = {}
    for ti in np.unique(allemb[:, 0]):   # TABLES order
        sel = allemb[allemb[:, 0] == ti]
        emb[TABLE_NAMES[ti]] = (torch.from_numpy(sel[:, 1].copy()), torch.from_numpy(sel[:, 2].copy()))
    fvl = {}
    for b, x in enumerate(feats):
        for name, (tok, feat) in x["fv"].items():
            lst = fvl.setdefault(name, ([], []))
            lst[0].append(tok.astype(np.int64) + b * T); lst[1].append(feat)
    fv = {k: (torch.from_numpy(np.concatenate(fvl[k][0])), torch.from_numpy(np.concatenate(fvl[k][1])))
          for k in ALL_FIXEDVECS if k in fvl}   # fixed order: the trunk sums in dict order
    pad = torch.ones(B, T, dtype=torch.bool)
    choice_index = torch.zeros(B, Cn, dtype=torch.long)
    choice_mask = torch.ones(B, Cn, dtype=torch.bool)   # True = padding
    for b, x in enumerate(feats):
        pad[b, :x["n"]] = False
        nc = x["n_choice"]
        choice_index[b, :nc] = torch.arange(x["n_obs"], x["n"])
        choice_mask[b, :nc] = False
    return {
        "B": B, "T": T,
        "emb": emb, "fv": fv,
        "pad": pad, "choice_index": choice_index, "choice_mask": choice_mask,
    }


class FeatureStore:
    """All featurised records of an update in flat arrays; batch(indices) == collate([feats[i] for i in indices])
    (same tensors, same order) with vectorised numpy gathers instead of per-record Python loops."""

    def __init__(self, feats):
        self.n = np.array([x["n"] for x in feats], dtype=np.int64)
        self.n_obs = np.array([x["n_obs"] for x in feats], dtype=np.int64)
        self.n_choice = self.n - self.n_obs
        self.emb = {}
        N = len(feats)
        cnt = np.array([len(x["emb"]) for x in feats], dtype=np.int64)
        allemb = np.concatenate([x["emb"] for x in feats])   # int16: int64 copies cost ~1 GB per 100k decisions
        rec = np.repeat(np.arange(N, dtype=np.int32), cnt)
        # rec is already ascending, so a stable sort by table gives table, then record, then in-record order.
        order = np.argsort(allemb[:, 0], kind="stable")
        allemb, rec = allemb[order], rec[order]
        bounds = np.searchsorted(allemb[:, 0], np.arange(len(TABLE_NAMES) + 1))
        for ti, name in enumerate(TABLE_NAMES):
            lo, hi = bounds[ti], bounds[ti + 1]
            lens = np.bincount(rec[lo:hi], minlength=N).astype(np.int64)
            start = np.concatenate([[0], np.cumsum(lens)[:-1]]).astype(np.int64)
            self.emb[name] = (start, lens, allemb[lo:hi, 1].copy(), allemb[lo:hi, 2].copy())
        names = []
        for x in feats:
            for k in x["fv"]:
                if k not in names:
                    names.append(k)
        self.fv_order = [k for k in ALL_FIXEDVECS if k in names]
        self.fv = {}
        for k in self.fv_order:
            w = ALL_FIXEDVECS[k][1]
            toks = [x["fv"][k][0] if k in x["fv"] else np.zeros(0, np.int16) for x in feats]
            vals = [x["fv"][k][1] if k in x["fv"] else np.zeros((0, w), np.float32) for x in feats]
            self.fv[k] = self._flat(toks, vals)

    @staticmethod
    def _flat(toks, vals):
        lens = np.array([len(t) for t in toks], dtype=np.int64)
        start = np.concatenate([[0], np.cumsum(lens)[:-1]]).astype(np.int64)
        tok = np.concatenate(toks) if len(toks) else np.zeros(0, np.int16)
        val = np.concatenate(vals) if len(vals) else np.zeros(0)
        return start, lens, tok, val

    @staticmethod
    def _gather(entry, idx, T):
        start, lens, tok, val = entry
        ln = lens[idx]
        total = int(ln.sum())
        if total == 0:
            return None
        b = np.repeat(np.arange(len(idx)), ln)
        off = np.arange(total) - np.repeat(np.cumsum(ln) - ln, ln)
        src = np.repeat(start[idx], ln) + off
        return tok[src].astype(np.int64) + b * T, val[src]

    def batch(self, indices):
        idx = np.asarray(indices, dtype=np.int64)
        B = len(idx)
        n, n_obs, n_choice = self.n[idx], self.n_obs[idx], self.n_choice[idx]
        T = int(n.max())
        Cn = max(int(n_choice.max()), 1)
        emb, fv = {}, {}
        for name, entry in self.emb.items():
            g = self._gather(entry, idx, T)
            if g is not None:
                emb[name] = (torch.from_numpy(g[0]), torch.from_numpy(g[1].astype(np.int64)))
        for name in self.fv_order:
            g = self._gather(self.fv[name], idx, T)
            if g is not None:
                fv[name] = (torch.from_numpy(g[0]), torch.from_numpy(np.ascontiguousarray(g[1], dtype=np.float32)))
        ar_t = np.arange(T)
        pad = torch.from_numpy(ar_t[None, :] >= n[:, None])
        ar_c = np.arange(Cn)
        choice_mask = torch.from_numpy(ar_c[None, :] >= n_choice[:, None])
        choice_index = torch.from_numpy(np.where(choice_mask.numpy(), 0, n_obs[:, None] + ar_c[None, :]))
        return {"B": B, "T": T, "emb": emb, "fv": fv, "pad": pad, "choice_index": choice_index,
                "choice_mask": choice_mask}


def batch_to(batch, device):
    out = dict(batch)
    nb = device.type == "cuda" if isinstance(device, torch.device) else str(device).startswith("cuda")
    out["emb"] = {k: (a.to(device, non_blocking=nb), b.to(device, non_blocking=nb)) for k, (a, b) in batch["emb"].items()}
    out["fv"] = {k: (a.to(device, non_blocking=nb), b.to(device, non_blocking=nb)) for k, (a, b) in batch["fv"].items()}
    for k in ("pad", "choice_index", "choice_mask"):
        out[k] = batch[k].to(device, non_blocking=nb)
    return out


# ---------------------------------------------------------------- network

class RMSNorm(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.w = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + NORM_EPS) * self.w


class Block(nn.Module):
    def __init__(self, dim, heads, hidden):
        super().__init__()
        self.heads = heads
        self.norm1, self.norm2 = RMSNorm(dim), RMSNorm(dim)
        self.in_proj_weight = nn.Parameter(torch.zeros(3 * dim, dim))
        self.in_proj_bias = nn.Parameter(torch.zeros(3 * dim))
        self.out_proj = nn.Linear(dim, dim)
        self.w1 = nn.Linear(dim, hidden)
        self.w2 = nn.Linear(hidden, dim, bias=False)
        self.v = nn.Linear(dim, hidden, bias=False)

    def forward(self, x, pad):
        B, T, D = x.shape
        h = self.heads
        q, k, v = F.linear(self.norm1(x), self.in_proj_weight, self.in_proj_bias).chunk(3, dim=-1)
        q, k, v = (t.view(B, T, h, D // h).transpose(1, 2) for t in (q, k, v))
        mask = (~pad)[:, None, None, :]   # True = attend
        att = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        x = x + self.out_proj(att.transpose(1, 2).reshape(B, T, D))
        xn = self.norm2(x)
        return x + self.w2(F.silu(self.w1(xn)) * self.v(xn))


class FixedVec(nn.Module):
    def __init__(self, dim, features, inv_freq):
        super().__init__()
        self.register_buffer("inv_freq", inv_freq.clone())
        self.proj = nn.Linear(features * dim, dim)

    def forward(self, x):   # x (N, features)
        a = x[..., None] * self.inv_freq          # (N, F, half)
        s = torch.cat([a.sin(), a.cos()], dim=-1)  # (N, F, dim)
        return self.proj(s.flatten(-2))


class PolicyNet(nn.Module):
    """The native Net with every optional input; see the module docstring."""

    def __init__(self, dim, heads, hidden, layers, table_rows, trim_map=False):
        super().__init__()
        self.dim, self.heads, self.hidden, self.trim_map = dim, heads, hidden, trim_map
        self.tables = nn.ParameterDict({k: nn.Parameter(torch.zeros(rows, dim)) for k, rows in table_rows.items()})
        inv = 10.0 * (1e-4 ** (torch.arange(dim // 2, dtype=torch.float32) / (dim // 2 - 1)))
        self.fixedvecs = nn.ModuleDict({k: FixedVec(dim, n, inv) for k, (_, n) in FIXEDVECS.items()})
        self.blocks = nn.ModuleList([Block(dim, heads, hidden) for _ in range(layers)])
        self.norm = RMSNorm(dim)
        self.value_head_norm = RMSNorm(dim)
        self.choice_logits = nn.Linear(dim, 1)
        self.value_head = nn.Linear(dim, 1)
        self.extra_blocks, self.critic_mode, self.aux_names = 0, "shared", ()   # set by construct()
        self.extra_inputs = ()   # optional inputs (OPTIONAL_FIXEDVECS) by construct() or from_bin

    # -- native .bin <-> module
    @classmethod
    def from_bin(cls, path):
        s = read_bin(path)
        dim = s["norm.w"].shape[0]
        hidden = s["layers.0.mlp.w1.weight"].shape[0]
        heads = int(s["meta.n_heads"].reshape(-1)[0]) if "meta.n_heads" in s else 8
        trim = bool(s["meta.trim_map"].reshape(-1)[0]) if "meta.trim_map" in s else False
        layers = 0
        while f"layers.{layers}.norm1.w" in s:
            layers += 1
        rows = {}
        for k, name in TABLES.items():
            if name in s:
                rows[k] = s[name].shape[0]
            elif k in ZERO_INIT_TABLES:
                rows[k] = ZERO_INIT_TABLES[k]
            else:
                raise KeyError(f"{path}: missing {name}")
        rows["fixed_action"] = max(rows["fixed_action"], FA_COUNT)
        net = cls(dim, heads, hidden, layers, rows, trim)
        with torch.no_grad():
            for k, name in TABLES.items():
                if name in s:
                    net.tables[k][: s[name].shape[0]] = s[name]
            for k, (prefix, _) in FIXEDVECS.items():
                m = net.fixedvecs[k]
                if prefix + ".proj.weight" in s:
                    m.inv_freq.copy_(s[prefix + ".num_embed.inv_freq"])
                    m.proj.weight.copy_(s[prefix + ".proj.weight"]); m.proj.bias.copy_(s[prefix + ".proj.bias"])
                elif k in ZERO_INIT_FIXEDVECS:
                    m.inv_freq.copy_(s[FIXEDVECS["fixed_obs"][0] + ".num_embed.inv_freq"])
                    nn.init.zeros_(m.proj.weight); nn.init.zeros_(m.proj.bias)
                else:
                    raise KeyError(f"{path}: missing {prefix}")
            for k, (prefix, n) in OPTIONAL_FIXEDVECS.items():   # only nets built with them hold them
                if prefix + ".proj.weight" in s:
                    m = FixedVec(dim, n, s[prefix + ".num_embed.inv_freq"])
                    m.proj.weight.copy_(s[prefix + ".proj.weight"]); m.proj.bias.copy_(s[prefix + ".proj.bias"])
                    net.fixedvecs[k] = m
                    net.extra_inputs = net.extra_inputs + (k,)
            for i, b in enumerate(net.blocks):
                L = f"layers.{i}."
                b.norm1.w.copy_(s[L + "norm1.w"]); b.norm2.w.copy_(s[L + "norm2.w"])
                b.in_proj_weight.copy_(s[L + "attn.in_proj_weight"]); b.in_proj_bias.copy_(s[L + "attn.in_proj_bias"])
                b.out_proj.weight.copy_(s[L + "attn.out_proj.weight"]); b.out_proj.bias.copy_(s[L + "attn.out_proj.bias"])
                b.w1.weight.copy_(s[L + "mlp.w1.weight"]); b.w1.bias.copy_(s[L + "mlp.w1.bias"])
                b.w2.weight.copy_(s[L + "mlp.w2.weight"]); b.v.weight.copy_(s[L + "mlp.v.weight"])
            net.norm.w.copy_(s["norm.w"]); net.value_head_norm.w.copy_(s["value_head_norm.w"])
            net.choice_logits.weight.copy_(s["choice_logits.weight"]); net.choice_logits.bias.copy_(s["choice_logits.bias"])
            net.value_head.weight.copy_(s["value_head.weight"]); net.value_head.bias.copy_(s["value_head.bias"])
        return net

    def native_state(self):
        """Tensors in the native .bin layout (all optional inputs included)."""
        out = OrderedDict()
        for k, name in TABLES.items():
            out[name] = self.tables[k].detach()
            for alias in SHARED_ALIASES.get(k, []):
                out[alias] = self.tables[k].detach()
        for k, (prefix, _) in ALL_FIXEDVECS.items():
            if k not in self.fixedvecs:   # an optional input this net does not have
                continue
            m = self.fixedvecs[k]
            out[prefix + ".num_embed.inv_freq"] = m.inv_freq
            out[prefix + ".proj.weight"] = m.proj.weight.detach(); out[prefix + ".proj.bias"] = m.proj.bias.detach()
        for i, b in enumerate(self.blocks):
            L = f"layers.{i}."
            out[L + "norm1.w"] = b.norm1.w.detach(); out[L + "norm2.w"] = b.norm2.w.detach()
            out[L + "attn.in_proj_weight"] = b.in_proj_weight.detach(); out[L + "attn.in_proj_bias"] = b.in_proj_bias.detach()
            out[L + "attn.out_proj.weight"] = b.out_proj.weight.detach(); out[L + "attn.out_proj.bias"] = b.out_proj.bias.detach()
            out[L + "mlp.w1.weight"] = b.w1.weight.detach(); out[L + "mlp.w1.bias"] = b.w1.bias.detach()
            out[L + "mlp.w2.weight"] = b.w2.weight.detach(); out[L + "mlp.v.weight"] = b.v.weight.detach()
        out["norm.w"] = self.norm.w.detach(); out["value_head_norm.w"] = self.value_head_norm.w.detach()
        out["choice_logits.weight"] = self.choice_logits.weight.detach(); out["choice_logits.bias"] = self.choice_logits.bias.detach()
        out["value_head.weight"] = self.value_head.weight.detach(); out["value_head.bias"] = self.value_head.bias.detach()
        out["meta.n_heads"] = torch.tensor([float(self.heads)])
        if self.trim_map:
            out["meta.trim_map"] = torch.tensor([1.0])
        return out

    def to_bin(self, path):
        write_bin(path, self.native_state())

    # -- forward
    def trunk(self, batch):
        B, T, D = batch["B"], batch["T"], self.dim
        p = self.tables["card"]
        # One index_add over all components (tables in order, then fixed vectors): per token the same summation
        # order as one call per component, without a full (B*T, D) copy per component. index_select instead of
        # tables[k][row]: its backward is an index_add, not the sort-based index_put kernel (23% of CUDA time).
        toks, srcs = [], []
        for k, (tok, row) in batch["emb"].items():
            toks.append(tok); srcs.append(self.tables[k].index_select(0, row).to(p.dtype))
        for k, (tok, feat) in batch["fv"].items():
            if k not in self.fixedvecs:   # optional input (x3_deck) the net was not built with
                continue
            toks.append(tok); srcs.append(self.fixedvecs[k](feat).to(p.dtype))  # Linear output is bf16 under autocast
        x = torch.zeros(B * T, D, device=p.device, dtype=p.dtype).index_add(0, torch.cat(toks), torch.cat(srcs))
        x = x.view(B, T, D)
        for b in self.blocks:
            x = b(x, batch["pad"])
        return x

    def heads_out(self, x, batch):
        """(logits (B, C) with -inf on padding, value (B,), pooled (B, D)).

        The two output Linears run in fp32 even inside a bf16 autocast region (the trunk may stay bf16): the
        actor records its behaviour log-probs from the native fp32 net, and a bf16 final layer alone moves the
        learner's log-probs by up to ~3e-2 against them, which the PPO ratio would read as a policy change. This
        removes only the final-layer rounding: a bf16 trunk still leaves a gap (on heart1.bin under CPU bf16
        autocast, mean |dlogp| against full fp32 drops from 0.013 to 0.008, while the max, ~0.1, comes from the trunk)."""
        xn = self.norm(x)
        idx = batch["choice_index"]
        xc = torch.gather(xn, 1, idx[..., None].expand(-1, -1, xn.shape[-1]))
        valid = (~batch["pad"]).to(xn.dtype)[..., None]
        pooled = (self.value_head_norm(xn) * valid).sum(1) / valid.sum(1)
        with torch.autocast(x.device.type, enabled=False):
            logits = self.choice_logits(xc.float()).squeeze(-1).masked_fill(batch["choice_mask"], float("-inf"))
            value = self.value_head(pooled.float()).squeeze(-1)
        return logits, value, pooled

    def forward(self, batch):
        """(logits, value), or (logits, value, aux) when the net has auxiliary heads (see construct()).

        With a separate critic (critic_net) the value comes from the critic's own trunk and head, so the policy
        trunk gets no value gradient; the net's own value_head is then unused (and stays in the native export)."""
        logits, value, pooled = self.heads_out(self.trunk(batch), batch)
        critic = getattr(self, "critic_net", None)
        if critic is not None:
            _, value, _ = critic.heads_out(critic.trunk(batch), batch)
        aux_head = getattr(self, "aux_head", None)
        if aux_head is None:
            return logits, value
        with torch.autocast(pooled.device.type, enabled=False):
            aux = aux_head(pooled.float())
        return logits, value, aux


# ---------------------------------------------------------------- architecture constructions (arch screen, P2)

AUX_TARGETS = ("floor", "act4")   # final floor / 57 (MSE); Act 4 reached (BCE on a logit)


def construct(net, extra_blocks=0, critic="shared", aux=(), seed=0, inputs=()):
    """A copy of `net` with the arch screen's policy-preserving changes (PREREG ppo_arch_screen_20261102):

    - extra_blocks N: N transformer blocks appended after the last one, with out_proj (weight and bias) and w2
      zero, so each new pre-norm residual block is the identity; their other weights are drawn from `seed`.
    - critic "separate": critic_net, a full copy of the trunk (embeddings, fixed vectors, blocks, norms) with the
      net's value head; the value then comes from it alone.
    - aux names (subset of AUX_TARGETS): aux_head, a zero-initialised Linear(dim, len(aux)) on the pooled trunk.
    - inputs (subset of OPTIONAL_FIXEDVECS, e.g. x3_deck): zero-initialised optional input projections (exported,
      so a native net built with them reads them; inv_freq as the fixed observation's).
    Policy logits (and, before training, the value) equal the source net's; the native export writes only the
    policy net (to_bin: depth included, critic and aux heads not, since actors use the policy logits alone)."""
    import copy
    if critic not in ("shared", "separate"):
        raise ValueError(f"critic {critic!r}: shared or separate")
    aux = tuple(aux)
    if any(a not in AUX_TARGETS for a in aux) or len(set(aux)) != len(aux):
        raise ValueError(f"aux heads {aux}: a subset of {AUX_TARGETS}")
    inputs = tuple(inputs)
    if any(k not in OPTIONAL_FIXEDVECS for k in inputs) or len(set(inputs)) != len(inputs):
        raise ValueError(f"inputs {inputs}: a subset of {tuple(OPTIONAL_FIXEDVECS)}")
    if getattr(net, "critic_net", None) is not None or getattr(net, "aux_head", None) is not None:
        raise ValueError("construct() applies to a plain net, not to one already constructed")
    if any(k in net.fixedvecs for k in inputs):
        raise ValueError(f"the net already has inputs {[k for k in inputs if k in net.fixedvecs]}")
    out = copy.deepcopy(net)
    g = torch.Generator().manual_seed(int(seed))
    D = out.dim
    with torch.no_grad():
        for _ in range(extra_blocks):
            b = Block(D, out.heads, out.hidden).to(out.norm.w.device, out.norm.w.dtype)
            bound = math.sqrt(6.0 / (D + D))   # xavier-uniform per q/k/v slice, as nn.MultiheadAttention
            b.in_proj_weight.copy_((torch.rand(3 * D, D, generator=g) * 2 - 1) * bound)
            b.in_proj_bias.zero_()
            for lin, fan_in in ((b.w1, D), (b.v, D)):   # nn.Linear's default range
                r = 1.0 / math.sqrt(fan_in)
                lin.weight.copy_((torch.rand(lin.weight.shape, generator=g) * 2 - 1) * r)
                if lin.bias is not None:
                    lin.bias.copy_((torch.rand(lin.bias.shape, generator=g) * 2 - 1) * r)
            b.out_proj.weight.zero_(); b.out_proj.bias.zero_(); b.w2.weight.zero_()
            out.blocks.append(b)
        for k in inputs:
            m = FixedVec(D, OPTIONAL_FIXEDVECS[k][1], out.fixedvecs["fixed_obs"].inv_freq).to(out.norm.w.device)
            nn.init.zeros_(m.proj.weight); nn.init.zeros_(m.proj.bias)
            out.fixedvecs[k] = m
    if critic == "separate":
        out.critic_net = copy.deepcopy(net)   # the plain trunk (no extra blocks or inputs)
    if aux:
        out.aux_head = nn.Linear(D, len(aux))
        with torch.no_grad():
            out.aux_head.weight.zero_(); out.aux_head.bias.zero_()
    out.extra_blocks = int(extra_blocks) + getattr(net, "extra_blocks", 0)
    out.critic_mode, out.aux_names = critic, aux
    out.extra_inputs = tuple(getattr(net, "extra_inputs", ())) + inputs
    return out


def _records(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                yield row.get("record", row)


def score_main(argv):
    if len(argv) != 3:
        sys.exit("usage: ppo_model.py score NET.bin records.jsonl out.jsonl")
    net = PolicyNet.from_bin(argv[0]).eval()
    recs = list(_records(argv[1]))
    with torch.no_grad(), open(argv[2], "w") as out:
        for i in range(0, len(recs), 64):
            chunk = recs[i:i + 64]
            batch = collate([featurize(r, net.trim_map) for r in chunk])
            logits, value = net(batch)
            for b, r in enumerate(chunk):
                n = len(r["cards_offered.cards"]) + len(r["relics_offered"]) + len(r["potions_offered"]) \
                    + len(r["fixed_actions"]) + len(r["paths_offered"])
                out.write(json.dumps({"logits": logits[b, :n].tolist(), "value": float(value[b])}) + "\n")


def extend_main(argv):
    """extend IN.bin OUT.bin: write IN with every optional input (zero-initialised where absent)."""
    if len(argv) != 2:
        sys.exit("usage: ppo_model.py extend IN.bin OUT.bin")
    PolicyNet.from_bin(argv[0]).to_bin(argv[1])


def perturb_main(argv):
    """perturb IN.bin OUT.bin [seed]: random values in every optional input and the PPO fixed-action rows (parity)."""
    if len(argv) not in (2, 3):
        sys.exit("usage: ppo_model.py perturb IN.bin OUT.bin [seed]")
    net = PolicyNet.from_bin(argv[0])
    g = torch.Generator().manual_seed(int(argv[2]) if len(argv) == 3 else 0)
    with torch.no_grad():
        for k in ZERO_INIT_TABLES:
            net.tables[k].copy_(0.3 * torch.randn(net.tables[k].shape, generator=g))
        net.tables["fixed_action"][FA_PPO_FIRST:] = 0.3 * torch.randn(FA_COUNT - FA_PPO_FIRST, net.dim, generator=g)
        for k in list(ZERO_INIT_FIXEDVECS) + [k for k in OPTIONAL_FIXEDVECS if k in net.fixedvecs]:
            m = net.fixedvecs[k].proj
            m.weight.copy_(0.02 * torch.randn(m.weight.shape, generator=g)); m.bias.copy_(0.1 * torch.randn(m.bias.shape, generator=g))
    net.to_bin(argv[1])


def addinputs_main(argv):
    """addinputs IN.bin OUT.bin NAME[,NAME]: IN with zero-initialised optional inputs (x3_deck) added."""
    if len(argv) != 3:
        sys.exit("usage: ppo_model.py addinputs IN.bin OUT.bin x3_deck")
    construct(PolicyNet.from_bin(argv[0]), inputs=[x for x in argv[2].split(",") if x]).to_bin(argv[1])


if __name__ == "__main__":
    cmds = {"score": score_main, "extend": extend_main, "perturb": perturb_main, "addinputs": addinputs_main}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: ppo_model.py {score|extend|perturb|addinputs} ...")
    cmds[sys.argv[1]](sys.argv[2:])
