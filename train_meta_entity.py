#!/usr/bin/env python3
"""Train an entity-aware multi-head out-of-combat value model.

The model predicts both P(run win) and expected final floor. Card counts and
upgrade counts are encoded as a learned set of card entities; relics and potions
use analogous learned set encoders. Boss/future-fight and bottled-card IDs use
categorical embeddings rather than ordinal scalar IDs.

Optional MAPS.csv adds a full 15x7 map-DAG encoder. Generate it with:
  ./one_combat_cardcf.elf mapbatch META.csv MAPS.csv

Usage:
  train_meta_entity.py META.csv V_WIN_REFERENCE.json V_FLOOR_REFERENCE.json OUT_PREFIX [MAPS.csv]
"""
import copy
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import torch
from torch import nn
import xgboost as xgb
from sklearn.metrics import log_loss, roc_auc_score, r2_score
from sklearn.model_selection import GroupShuffleSplit


CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/buffer/_train.csv"
WIN_REF = sys.argv[2] if len(sys.argv) > 2 else "selfplay/current/v_win.json"
FLOOR_REF = sys.argv[3] if len(sys.argv) > 3 else "models/v_rich_xgb.json"
OUT = sys.argv[4] if len(sys.argv) > 4 else "selfplay/models/meta_entity"
MAP_CSV = sys.argv[5] if len(sys.argv) > 5 else ""

EPOCHS = int(os.environ.get("META_ENTITY_EPOCHS", "40"))
BATCH = int(os.environ.get("META_ENTITY_BATCH", "2048"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
DEVICE = os.environ.get("META_ENTITY_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
BASE_MODEL = os.environ.get("META_ENTITY_BASE_INIT", "")
FREEZE_BASE_EPOCHS = int(os.environ.get("META_ENTITY_FREEZE_BASE_EPOCHS", "0"))
torch.manual_seed(0)
torch.set_num_threads(THREADS)
if DEVICE.startswith("cuda"):
    torch.cuda.set_per_process_memory_fraction(
        float(os.environ.get("META_ENTITY_GPU_FRACTION", "0.70")))

LABELS = {"seed", "won", "finalFloor", "endHp"}
ENCOUNTER_CATS = ["bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2"]
BOTTLE_CATS = ["bottledAtkId", "bottledSkillId", "bottledPowId"]

print(f"loading {CSV} ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
header = list(df.columns)
for required in LABELS | set(ENCOUNTER_CATS) | set(BOTTLE_CATS):
    if required not in df:
        raise RuntimeError(f"missing required meta column {required}")

deck_cols = [f"d{i}" for i in range(372)]
upgrade_cols = [f"u{i}" for i in range(372)]
relic_cols = [f"r{i}" for i in range(181)]
potion_cols = [f"pot{i}" for i in range(48)]
entity_cols = set(deck_cols + upgrade_cols + relic_cols + potion_cols
                  + ENCOUNTER_CATS + BOTTLE_CATS)
scalar_cols = [c for c in header if c not in LABELS and c not in entity_cols]

seed = df["seed"].to_numpy(np.int64)
won = df["won"].to_numpy(np.float32)
final_floor = df["finalFloor"].to_numpy(np.float32)
current_floor = df["floor"].to_numpy(np.float32)
deck = df[deck_cols].to_numpy(np.uint8)
upgrades = df[upgrade_cols].to_numpy(np.uint8)
relics = np.maximum(df[relic_cols].to_numpy(np.float32), 0).astype(np.float32)
potions = np.maximum(df[potion_cols].to_numpy(np.float32), 0).astype(np.float32)
encounters = np.clip(df[ENCOUNTER_CATS].to_numpy(np.int64) + 1, 0, 127).astype(np.uint8)
bottles = np.clip(df[BOTTLE_CATS].to_numpy(np.int64) + 1, 0, 372).astype(np.int16)
scalars = df[scalar_cols].to_numpy(np.float32)

if MAP_CSV:
    print(f"loading full map graphs {MAP_CSV} ...", flush=True)
    map_df = pd.read_csv(MAP_CSV).set_index(["seed", "ascension", "act"])
    state_keys = pd.MultiIndex.from_arrays([
        df["seed"].astype(np.int64), df["ascension"].astype(np.int64),
        df["act"].astype(np.int64)], names=["seed", "ascension", "act"])
    aligned_maps = map_df.reindex(state_keys)
    if aligned_maps[["room0", "edges0"]].isna().any().any():
        missing_keys = state_keys[aligned_maps["room0"].isna()]
        raise ValueError(f"map table is missing {len(missing_keys)} states; first={missing_keys[0]}")
    map_rooms = aligned_maps[[f"room{i}" for i in range(105)]].to_numpy(np.uint8)
    map_edges = aligned_maps[[f"edges{i}" for i in range(105)]].to_numpy(np.uint8)
    map_special = np.zeros((len(df), 105), np.uint8)
    bx = aligned_maps["burningEliteX"].to_numpy(np.int16)
    by = aligned_maps["burningEliteY"].to_numpy(np.int16)
    active_burning = (bx >= 0) & (by >= 0) & (df["greenKey"].to_numpy() < 0.5)
    map_special[np.flatnonzero(active_burning),
                by[active_burning] * 7 + bx[active_burning]] = 1
    map_position = np.concatenate([
        df[["curMapX", "curMapY"]].to_numpy(np.int16),
        np.full((len(df), 1), -1, np.int16)], axis=1)
else:
    map_rooms = map_edges = map_special = map_position = None

# Same group split as train_winrate.py: no decisions from one run cross the split.
_, run = np.unique(seed, return_inverse=True)
tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0)
              .split(scalars, won, groups=run))
print(f"rows {len(df):,}, runs {run.max()+1:,}, train {len(tr):,}, val {len(va):,}, "
      f"win base {won.mean():.3f}, scalar features {len(scalar_cols)}", flush=True)

if BASE_MODEL:
    base_checkpoint = torch.load(BASE_MODEL, map_location="cpu", weights_only=False)
    if list(base_checkpoint["scalar_cols"]) != scalar_cols:
        raise ValueError("base meta model scalar schema does not match this dataset")
    scalar_mean = np.asarray(base_checkpoint["scalar_mean"], np.float32)
    scalar_inv = np.asarray(base_checkpoint["scalar_inv"], np.float32)
else:
    scalar_mean = scalars[tr].mean(0, dtype=np.float64).astype(np.float32)
    scalar_inv = 1 / np.maximum(scalars[tr].std(0, dtype=np.float64).astype(np.float32), 1e-6)
scalars = (scalars - scalar_mean) * scalar_inv

# Predict remaining progress rather than raw floor. This guarantees the served
# expected floor stays between the current floor and the terminal floor 51.
floor_room = np.maximum(51.0 - current_floor, 1.0)
progress = np.clip((final_floor - current_floor) / floor_room, 0, 1).astype(np.float32)


class FullMapGraphEncoder(nn.Module):
    """Bottom-up map-DAG encoder with optional singleton next-child readout."""
    def __init__(self, dnode=32, dout=96):
        super().__init__()
        self.room = nn.Embedding(10, dnode)
        self.row = nn.Embedding(15, dnode)
        self.col = nn.Embedding(7, dnode)
        self.burning = nn.Embedding(2, dnode)
        self.update = nn.Sequential(
            nn.Linear(3*dnode + 1, 64), nn.LayerNorm(64), nn.SiLU(),
            nn.Linear(64, dnode))
        self.norm = nn.LayerNorm(dnode)
        self.readout = nn.Sequential(
            nn.Linear(2*dnode, 128), nn.LayerNorm(128), nn.SiLU(),
            nn.Linear(128, dout), nn.SiLU())
        self.register_buffer("row_ids", torch.arange(15))
        self.register_buffer("col_ids", torch.arange(7))
        self.register_buffer("edge_bits", torch.arange(7))

    @staticmethod
    def masked_pool(nodes, mask):
        weight = mask.float()
        mean = (nodes * weight.unsqueeze(-1)).sum(1) / weight.sum(1, keepdim=True).clamp_min(1.0)
        maximum = nodes.masked_fill(~mask.unsqueeze(-1), -1e9).max(1).values
        maximum = torch.where(mask.any(1, keepdim=True), maximum, torch.zeros_like(maximum))
        return mean, maximum

    def forward(self, rooms, edges, special, position):
        batch = rooms.shape[0]
        rooms = rooms.long().view(batch, 15, 7)
        edges = edges.long().view(batch, 15, 7)
        special = special.long().view(batch, 15, 7)
        base = (self.room(rooms) + self.row(self.row_ids)[None, :, None, :]
                + self.col(self.col_ids)[None, None, :, :] + self.burning(special))
        adjacency = ((edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        encoded_rows = [base[:, 14]]
        for y in range(13, -1, -1):
            child = encoded_rows[-1]
            edge = adjacency[:, y]
            mean = torch.bmm(edge.float(), child) / edge.sum(2, keepdim=True).clamp_min(1.0)
            expanded = child[:, None, :, :].expand(-1, 7, -1, -1)
            maximum = expanded.masked_fill(~edge.unsqueeze(-1), -1e9).max(2).values
            maximum = torch.where(edge.any(2, keepdim=True), maximum, torch.zeros_like(maximum))
            degree = torch.log1p(edge.sum(2, keepdim=True).float())
            encoded_rows.append(self.norm(base[:, y] + self.update(
                torch.cat((base[:, y], mean, maximum, degree), 2))))
        graph = torch.stack(list(reversed(encoded_rows)), 1)

        px = position[:, 0].long().clamp(0, 6)
        py = position[:, 1].long()
        chosen_x = position[:, 2].long()
        safe_y = py.clamp(0, 14)
        batch_ids = torch.arange(batch, device=rooms.device)
        current_edges = edges[batch_ids, safe_y, px]
        child_mask = ((current_edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        root_mask = edges[:, 0] > 0
        future_mask = torch.where((py < 0).unsqueeze(1), root_mask, child_mask)
        # Training uses chosen_x=-1 and pools every legal continuation. During
        # path inference, selecting one legal x exposes precisely that subtree.
        singleton = self.col_ids[None, :] == chosen_x.unsqueeze(1)
        future_mask = torch.where((chosen_x >= 0).unsqueeze(1), future_mask & singleton, future_mask)
        future_mask = future_mask & (py < 14).unsqueeze(1)
        future_y = (py + 1).clamp(0, 14)
        future_nodes = graph[batch_ids, future_y]
        mean, maximum = self.masked_pool(future_nodes, future_mask)
        return self.readout(torch.cat((mean, maximum), 1))


class MetaEntityNet(nn.Module):
    def __init__(self, nscalar, use_map=False):
        super().__init__()
        self.use_map = use_map
        self.card_id = nn.Embedding(372, 32)
        self.card_count = nn.Linear(2, 32, bias=False)
        self.relic_id = nn.Embedding(181, 16)
        self.relic_value = nn.Linear(1, 16, bias=False)
        self.potion_id = nn.Embedding(48, 8)
        self.potion_value = nn.Linear(1, 8, bias=False)
        self.encounter = nn.Parameter(torch.randn(5, 128, 8) * 0.02)
        self.bottle = nn.Parameter(torch.randn(3, 373, 12) * 0.02)
        self.map_graph = FullMapGraphEncoder() if use_map else None
        self.map_adapter = nn.Linear(96, 192, bias=False) if use_map else None
        if self.map_adapter is not None:
            nn.init.zeros_(self.map_adapter.weight)
        nin = nscalar + 64 + 32 + 16 + 40 + 36
        self.trunk = nn.Sequential(
            nn.Linear(nin, 192), nn.LayerNorm(192), nn.SiLU(), nn.Dropout(0.05),
            nn.Linear(192, 96), nn.SiLU())
        self.win = nn.Linear(96, 1)
        self.progress = nn.Linear(96, 1)
        self.register_buffer("card_ids", torch.arange(372))
        self.register_buffer("relic_ids", torch.arange(181))
        self.register_buffer("potion_ids", torch.arange(48))

    @staticmethod
    def pool(entity, weight, mask):
        denom = torch.sqrt(weight.sum(1, keepdim=True).clamp_min(1.0))
        summed = (entity * torch.sqrt(weight).unsqueeze(-1)).sum(1) / denom
        maximum = entity.masked_fill(~mask.unsqueeze(-1), -1e9).max(1).values
        maximum = torch.where(mask.any(1, keepdim=True), maximum, torch.zeros_like(maximum))
        return torch.cat((summed, maximum), 1)

    def forward(self, scalar, deck, upgrades, relics, potions, encounters, bottles,
                map_rooms=None, map_edges=None, map_special=None, map_position=None):
        dcount = deck.float()
        card_feat = torch.stack((torch.log1p(dcount), upgrades.float() / dcount.clamp_min(1)), -1)
        card = torch.relu(self.card_id(self.card_ids)[None] + self.card_count(card_feat))
        card = self.pool(card, dcount, dcount > 0)

        rvalue = relics.float()
        relic = torch.relu(self.relic_id(self.relic_ids)[None]
                           + self.relic_value(torch.log1p(rvalue).unsqueeze(-1)))
        relic = self.pool(relic, rvalue, rvalue > 0)

        pvalue = potions.float()
        potion = torch.relu(self.potion_id(self.potion_ids)[None]
                            + self.potion_value(torch.log1p(pvalue).unsqueeze(-1)))
        potion = self.pool(potion, pvalue, pvalue > 0)

        enc = torch.stack([self.encounter[i, encounters[:, i].long()]
                           for i in range(5)], 1).flatten(1)
        bottle = torch.stack([self.bottle[i, bottles[:, i].long()]
                              for i in range(3)], 1).flatten(1)
        trunk_pre = self.trunk[0](torch.cat((scalar, card, relic, potion, enc, bottle), 1))
        if self.use_map:
            map_value = self.map_graph(map_rooms, map_edges, map_special, map_position)
            trunk_pre = trunk_pre + self.map_adapter(map_value)
        z = self.trunk[1:](trunk_pre)
        return self.win(z).squeeze(1), self.progress(z).squeeze(1)


arrays = [scalars, deck, upgrades, relics, potions, encounters, bottles]
if MAP_CSV:
    arrays += [map_rooms, map_edges, map_special, map_position]
arrays += [won, progress, current_floor, final_floor]
tensors = [torch.from_numpy(a) for a in arrays]
input_count = 11 if MAP_CSV else 7
won_idx, progress_idx = input_count, input_count + 1


def forward_batch(model, ids):
    x = [t[ids].to(DEVICE) for t in tensors[:input_count]]
    return model(*x)


@torch.no_grad()
def predict(model, indices):
    model.eval()
    wp, fp = [], []
    for lo in range(0, len(indices), BATCH):
        ids = torch.from_numpy(indices[lo:lo+BATCH].astype(np.int64, copy=False))
        wl, pl = forward_batch(model, ids)
        wp.append(torch.sigmoid(wl).cpu())
        fp.append(torch.sigmoid(pl).cpu())
    pwin = torch.cat(wp).numpy()
    pprog = torch.cat(fp).numpy()
    pfloor = current_floor[indices] + (51-current_floor[indices])*pprog
    return pwin, pfloor


def metrics(indices, pwin, pfloor, tag):
    ywin = won[indices]
    yfloor = final_floor[indices]
    out = {
        "auc": float(roc_auc_score(ywin, pwin)),
        "logloss": float(log_loss(ywin, np.clip(pwin, 1e-6, 1-1e-6))),
        "brier": float(np.mean((pwin-ywin)**2)),
        "floor_rmse": float(np.sqrt(np.mean((pfloor-yfloor)**2))),
        "floor_mae": float(np.mean(np.abs(pfloor-yfloor))),
        "floor_r2": float(r2_score(yfloor, pfloor)),
    }
    print(f"{tag}: AUC={out['auc']:.4f} logloss={out['logloss']:.4f} "
          f"Brier={out['brier']:.4f} floorRMSE={out['floor_rmse']:.3f} "
          f"MAE={out['floor_mae']:.3f} R2={out['floor_r2']:.4f}", flush=True)
    return out


model = MetaEntityNet(len(scalar_cols), use_map=bool(MAP_CSV)).to(DEVICE)
if BASE_MODEL:
    old = base_checkpoint["state_dict"]
    current = model.state_dict()
    copied = 0
    with torch.no_grad():
        for name, src in old.items():
            if name in current and src.shape == current[name].shape:
                current[name].copy_(src); copied += src.numel()
        model.load_state_dict(current)
    print(f"initialized {copied:,} shared parameters from {BASE_MODEL}", flush=True)
if MAP_CSV and BASE_MODEL and FREEZE_BASE_EPOCHS:
    for name, parameter in model.named_parameters():
        if not (name.startswith("map_graph.") or name.startswith("map_adapter.")):
            parameter.requires_grad_(False)
    print(f"freezing pretrained meta model for {FREEZE_BASE_EPOCHS} epoch(s)", flush=True)
print(f"model parameters {sum(p.numel() for p in model.parameters()):,}", flush=True)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
bce = nn.BCEWithLogitsLoss()
rng = np.random.default_rng(0)
if MAP_CSV and BASE_MODEL:
    initial_win, initial_floor = predict(model, va)
    initial_metrics = metrics(va, initial_win, initial_floor, "exact pretrained baseline")
    best = copy.deepcopy(model.state_dict())
    best_objective = initial_metrics["logloss"] + initial_metrics["floor_rmse"]/25.0
else:
    best = None
    best_objective = float("inf")
stale = 0
print(f"training on {DEVICE}, CPU preprocessing threads={THREADS} ...", flush=True)
for epoch in range(1, EPOCHS+1):
    if FREEZE_BASE_EPOCHS and epoch == FREEZE_BASE_EPOCHS + 1:
        for parameter in model.parameters():
            parameter.requires_grad_(True)
        print("unfroze full meta model", flush=True)
    model.train()
    order = rng.permutation(tr)
    losses = []
    for lo in range(0, len(order), BATCH):
        ids_np = order[lo:lo+BATCH]
        ids = torch.from_numpy(ids_np.astype(np.int64, copy=False))
        wl, pl = forward_batch(model, ids)
        yw = tensors[won_idx][ids].to(DEVICE)
        yp = tensors[progress_idx][ids].to(DEVICE)
        pp = torch.sigmoid(pl)
        loss_win = bce(wl, yw)
        loss_floor = nn.functional.smooth_l1_loss(pp, yp, beta=0.05)
        loss = loss_win + 4.0*loss_floor
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()
        losses.append(float(loss.detach()))
    pwin, pfloor = predict(model, va)
    m = metrics(va, pwin, pfloor, f"epoch {epoch:02d} val")
    objective = m["logloss"] + m["floor_rmse"]/25.0
    if objective < best_objective:
        improvement = best_objective-objective
        best_objective = objective
        best = copy.deepcopy(model.state_dict())
        stale = 0 if improvement > 0.001 else stale+1
    else:
        stale += 1
    print(f"epoch {epoch:02d} train_loss={np.mean(losses):.5f} objective={objective:.5f}", flush=True)
    if stale >= 5:
        break

model.load_state_dict(best)
pwin, pfloor = predict(model, va)
nn_metrics = metrics(va, pwin, pfloor, "BEST entity meta NN")


def tree_predict(path, indices):
    booster = xgb.Booster()
    booster.load_model(path)
    feats = list(booster.feature_names)
    X = df.iloc[indices][feats].to_numpy(np.float32)
    return booster.predict(xgb.DMatrix(X, feature_names=feats))


tree_win = tree_predict(WIN_REF, va)
tree_floor = tree_predict(FLOOR_REF, va)
tree_metrics = metrics(va, tree_win, tree_floor, "tree references")

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.state_dict(), "scalar_cols": scalar_cols,
            "scalar_mean": scalar_mean, "scalar_inv": scalar_inv,
            "nn_metrics": nn_metrics, "tree_metrics": tree_metrics,
            "base_initializer": BASE_MODEL, "map_csv": MAP_CSV}, OUT + ".pt")

# TorchScript keeps server inference independent of this trainer's Python class.
example = [torch.from_numpy(a[:2]).to(DEVICE) for a in arrays[:input_count]]
model.eval()
traced = torch.jit.trace(model, tuple(example))
traced.save(OUT + ".torchscript")
np.savez(OUT + ".npz", scalar_cols=np.asarray(scalar_cols),
         scalar_mean=scalar_mean, scalar_inv=scalar_inv)

# Exact held-out rows for server/TorchScript parity checks.
sample_ids = va[:200]
sample = df.iloc[sample_ids][[c for c in header if c not in LABELS]].copy()
sample["pyWin"] = pwin[:len(sample_ids)]
sample["pyFloor"] = pfloor[:len(sample_ids)]
sample.to_csv(OUT + "_val.csv", index=False)
with open(OUT + "_metrics.json", "w") as f:
    json.dump({"rows": len(df), "runs": int(run.max()+1), "train": len(tr), "val": len(va),
               "base_initializer": BASE_MODEL, "map_csv": MAP_CSV,
               "nn": nn_metrics, "trees": tree_metrics}, f, indent=2)
print(f"saved {OUT}.pt, .torchscript, .npz, _val.csv and _metrics.json", flush=True)
