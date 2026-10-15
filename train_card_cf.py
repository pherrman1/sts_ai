#!/usr/bin/env python3
"""Train a card-reward action-value model from paired full-run branches.

Each decision contains every offered card plus skip, evaluated from an identical
pre-choice GameContext with common future RNG/agent seeds.  The network predicts
the paired canonical-score advantage of each action over skip.  Its state encoder
uses separate base/upgraded card embeddings and its action encoder attends to the
current deck, so candidate/deck interactions are learned directly.

When MAPS.csv is supplied, a bottom-up graph encoder reads every room and edge
in the deterministic 15x7 act map and summarizes the reachable future graph
from the current node.  Generate that companion table with:
  ./one_combat_cardcf.elf mapbatch CARD_CF.csv MAPS.csv

Usage:
  train_card_cf.py CARD_CF.csv OUT_PREFIX [V_FLOOR_REFERENCE.json] [MAPS.csv]
"""
import copy
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupShuffleSplit
from torch import nn


CSV = sys.argv[1] if len(sys.argv) > 1 else "build/card_cf.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/card_cf"
TREE_REF = sys.argv[3] if len(sys.argv) > 3 else ""
MAP_CSV = sys.argv[4] if len(sys.argv) > 4 else ""
EXTRA_CSV = os.environ.get("CARD_CF_EXTRA_CSV", "")
EXTRA_MAP_CSV = os.environ.get("CARD_CF_EXTRA_MAP_CSV", "")
BASE_MODEL = os.environ.get("CARD_CF_BASE_INIT", "")
WIN_BONUS = float(os.environ.get("STS_CARD_CF_WIN_BONUS", "10.0"))
SKIP_THRESHOLD = float(os.environ.get("STS_CARD_CF_TREE_SKIP", "-0.5"))
SURVIVAL_LOSS_WEIGHT = float(os.environ.get("STS_CARD_CF_SURVIVAL_LOSS_WEIGHT", "0.30"))
EPOCHS = int(os.environ.get("CARD_CF_EPOCHS", "40"))
BATCH = int(os.environ.get("CARD_CF_BATCH", "256"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
MIN_DECISIONS = int(os.environ.get("CARD_CF_MIN_DECISIONS", "100"))
DEVICE = os.environ.get("CARD_CF_DEVICE", "cpu")
INIT_MODEL = os.environ.get("CARD_CF_INIT", "")
FREEZE_BASE_EPOCHS = int(os.environ.get("CARD_CF_FREEZE_BASE_EPOCHS", "0"))

# This trainer is CPU-only by default and must not claim VRAM from an interactive
# game.  CUDA is an explicit opt-in, never an availability-based default.
if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.manual_seed(0)
torch.set_num_threads(THREADS)

BASE_LABELS = {
    "seed", "decisionIdx", "actionIdx", "candidateId", "candidateUpgraded",
    "branchWon", "branchFloor", "branchHp",
}
PROBE_LABELS = {
    "branchNextCombatSeen", "branchNextCombatPassed",
    "branchNextEliteSeen", "branchNextElitePassed",
    "branchNextBossSeen", "branchNextBossPassed", "branchFutureComplete",
}
OPTIONAL_LABELS = {"branchFutures"}
ENCOUNTER_CATS = ["bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2"]
BOTTLE_CATS = ["bottledAtkId", "bottledSkillId", "bottledPowId"]
DECK_COLS = [f"d{i}" for i in range(372)]
UPGRADE_COLS = [f"u{i}" for i in range(372)]
RELIC_COLS = [f"r{i}" for i in range(181)]
POTION_COLS = [f"pot{i}" for i in range(48)]


print(f"loading paired card decisions {CSV} ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
if EXTRA_CSV:
    print(f"adding survival-labeled card decisions {EXTRA_CSV} ...", flush=True)
    # The historic ranker rows do not contain probe columns.  Pandas supplies
    # NaN for those rows; the per-action probe mask below therefore trains Q on
    # every row but survival only on freshly simulated branches.
    df = pd.concat((df, pd.read_csv(EXTRA_CSV, dtype=np.float32)), ignore_index=True, sort=False)
missing = BASE_LABELS - set(df.columns)
if missing:
    raise ValueError(f"card-CF CSV missing columns: {sorted(missing)}")
has_survival_probes = PROBE_LABELS <= set(df.columns)
if PROBE_LABELS & set(df.columns) and not has_survival_probes:
    raise ValueError("card-CF CSV has a partial future-fight probe schema")
LABELS = BASE_LABELS | (PROBE_LABELS if has_survival_probes else set())

groups = list(df.groupby(["seed", "decisionIdx"], sort=False))
if len(groups) < MIN_DECISIONS:
    raise ValueError(f"need >= {MIN_DECISIONS} paired decisions, got {len(groups)}")
max_actions = max(len(g) for _, g in groups)
if max_actions > 8:
    raise ValueError(f"unexpected card-reward action count {max_actions}")

nd = len(groups)
first_rows = np.empty(nd, np.int64)
decision_seed = np.empty(nd, np.int64)
candidate = np.zeros((nd, max_actions), np.int64)  # 0=skip, card id is shifted +1
candidate_up = np.zeros((nd, max_actions), np.int64)
action_mask = np.zeros((nd, max_actions), bool)
score = np.full((nd, max_actions), -1e9, np.float32)
row_lookup = np.full((nd, max_actions), -1, np.int64)
survival = np.zeros((nd, max_actions, 3), np.float32)
survival_mask = np.zeros((nd, max_actions, 3), bool)

for di, ((seed_key, _), g) in enumerate(groups):
    first_rows[di] = g.index[0]
    decision_seed[di] = int(seed_key)
    if (g["candidateId"] < 0).sum() != 1:
        raise ValueError(f"decision {di} does not contain exactly one skip action")
    for ai, (row_idx, row) in enumerate(g.iterrows()):
        cid = int(row["candidateId"])
        candidate[di, ai] = cid + 1
        candidate_up[di, ai] = int(row["candidateUpgraded"])
        action_mask[di, ai] = True
        score[di, ai] = float(row["branchFloor"] + WIN_BONUS * row["branchWon"])
        row_lookup[di, ai] = row_idx
        if has_survival_probes:
            # A passed target means the continuation reached and cleared it.
            # An elite avoided by the route is deliberately unsupervised, not
            # treated as a failed elite.
            probe_available = pd.notna(row["branchFutureComplete"])
            survival[di, ai] = (float(row["branchNextCombatPassed"]) if probe_available else 0.0,
                                float(row["branchNextElitePassed"]) if probe_available else 0.0,
                                float(row["branchNextBossPassed"]) if probe_available else 0.0)
            # A bounded probe that stopped before a target is censored, not a
            # failure. Terminal branches that die before it are complete and
            # correctly teach a failed required-survival outcome.
            complete = probe_available and float(row["branchFutureComplete"]) > 0
            survival_mask[di, ai] = (probe_available and (float(row["branchNextCombatSeen"]) > 0 or complete),
                                      probe_available and float(row["branchNextEliteSeen"]) > 0,
                                      probe_available and (float(row["branchNextBossSeen"]) > 0 or complete))

state = df.loc[first_rows]
entity_cols = set(DECK_COLS + UPGRADE_COLS + RELIC_COLS + POTION_COLS
                  + ENCOUNTER_CATS + BOTTLE_CATS)
scalar_cols = [c for c in df.columns
               if c not in LABELS and c not in OPTIONAL_LABELS and c not in entity_cols]

deck = state[DECK_COLS].to_numpy(np.uint8)
upgrades = state[UPGRADE_COLS].to_numpy(np.uint8)
relics = np.maximum(state[RELIC_COLS].to_numpy(np.float32), 0).astype(np.float32)
potions = np.maximum(state[POTION_COLS].to_numpy(np.float32), 0).astype(np.float32)
encounters = np.clip(state[ENCOUNTER_CATS].to_numpy(np.int64) + 1, 0, 127).astype(np.uint8)
bottles = np.clip(state[BOTTLE_CATS].to_numpy(np.int64) + 1, 0, 372).astype(np.int16)
scalars = state[scalar_cols].to_numpy(np.float32)

if MAP_CSV:
    print(f"loading full map graphs {MAP_CSV} ...", flush=True)
    map_df = pd.read_csv(MAP_CSV)
    if EXTRA_MAP_CSV:
        print(f"adding survival-labeled map graphs {EXTRA_MAP_CSV} ...", flush=True)
        map_df = pd.concat((map_df, pd.read_csv(EXTRA_MAP_CSV)), ignore_index=True)
        map_df = map_df.drop_duplicates(["seed", "ascension", "act"], keep="last")
    map_index = map_df.set_index(["seed", "ascension", "act"])
    state_keys = pd.MultiIndex.from_arrays([
        state["seed"].astype(np.int64), state["ascension"].astype(np.int64),
        state["act"].astype(np.int64)], names=["seed", "ascension", "act"])
    aligned_maps = map_index.reindex(state_keys)
    if aligned_maps[["room0", "edges0"]].isna().any().any():
        missing_keys = state_keys[aligned_maps["room0"].isna()]
        raise ValueError(f"map table is missing {len(missing_keys)} states; first={missing_keys[0]}")
    map_rooms = aligned_maps[[f"room{i}" for i in range(105)]].to_numpy(np.uint8)
    map_edges = aligned_maps[[f"edges{i}" for i in range(105)]].to_numpy(np.uint8)
    map_special = np.zeros((nd, 105), np.uint8)
    bx = aligned_maps["burningEliteX"].to_numpy(np.int16)
    by = aligned_maps["burningEliteY"].to_numpy(np.int16)
    active_burning = (bx >= 0) & (by >= 0) & (state["greenKey"].to_numpy() < 0.5)
    map_special[np.flatnonzero(active_burning),
                by[active_burning] * 7 + bx[active_burning]] = 1
    map_position = state[["curMapX", "curMapY"]].to_numpy(np.int16)
else:
    # Keep the original no-map training path and TorchScript signature intact.
    map_rooms = map_edges = map_special = map_position = None

tr, va = next(GroupShuffleSplit(1, test_size=0.20, random_state=0)
              .split(np.arange(nd), groups=decision_seed))
if BASE_MODEL:
    base_meta = torch.load(BASE_MODEL, map_location="cpu", weights_only=False)
    if list(base_meta["scalar_cols"]) != scalar_cols:
        raise ValueError("base card-action model scalar schema mismatch")
    scalar_mean = np.asarray(base_meta["scalar_mean"], np.float32)
    scalar_inv = np.asarray(base_meta["scalar_inv"], np.float32)
else:
    scalar_mean = scalars[tr].mean(0, dtype=np.float64).astype(np.float32)
    scalar_inv = 1 / np.maximum(scalars[tr].std(0, dtype=np.float64).astype(np.float32), 1e-6)
scalars = (scalars - scalar_mean) * scalar_inv

skip_pos = (candidate == 0) & action_mask
skip_score = (score * skip_pos).sum(1)
advantage = (score - skip_score[:, None]) / 10.0
advantage[~action_mask] = 0

print(f"decisions {nd:,} from {len(np.unique(decision_seed)):,} runs; "
      f"actions {int(action_mask.sum()):,}, max {max_actions}, "
      f"train {len(tr):,}, val {len(va):,}; scalars {len(scalar_cols)}; "
      f"future-fight probes {'on' if has_survival_probes else 'off'}", flush=True)


class FullMapGraphEncoder(nn.Module):
    """Encode the complete layered map DAG, then read out the reachable future."""
    def __init__(self, dnode=32, dout=96):
        super().__init__()
        self.room = nn.Embedding(10, dnode)
        self.row = nn.Embedding(15, dnode)
        self.col = nn.Embedding(7, dnode)
        self.burning = nn.Embedding(2, dnode)
        self.update = nn.Sequential(
            nn.Linear(3*dnode + 1, 64), nn.LayerNorm(64), nn.SiLU(),
            nn.Linear(64, dnode),
        )
        self.norm = nn.LayerNorm(dnode)
        self.readout = nn.Sequential(
            nn.Linear(2*dnode, 128), nn.LayerNorm(128), nn.SiLU(),
            nn.Linear(128, dout), nn.SiLU(),
        )
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

        # The map only points to the next row, so one reverse sweep propagates
        # every descendant route to its ancestors. Mean preserves the typical
        # continuation; max preserves rare strategically important branches.
        encoded_rows = [base[:, 14]]
        for y in range(13, -1, -1):
            child = encoded_rows[-1]
            edge = adjacency[:, y]
            mean = torch.bmm(edge.float(), child) / edge.sum(2, keepdim=True).clamp_min(1.0)
            expanded = child[:, None, :, :].expand(-1, 7, -1, -1)
            maximum = expanded.masked_fill(~edge.unsqueeze(-1), -1e9).max(2).values
            maximum = torch.where(edge.any(2, keepdim=True), maximum, torch.zeros_like(maximum))
            degree = torch.log1p(edge.sum(2, keepdim=True).float())
            update = self.update(torch.cat((base[:, y], mean, maximum, degree), 2))
            encoded_rows.append(self.norm(base[:, y] + update))
        graph = torch.stack(list(reversed(encoded_rows)), 1)

        px = position[:, 0].long().clamp(0, 6)
        py = position[:, 1].long()
        safe_y = py.clamp(0, 14)
        batch_ids = torch.arange(batch, device=rooms.device)
        current_edges = edges[batch_ids, safe_y, px]
        child_mask = ((current_edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        root_mask = edges[:, 0] > 0
        future_mask = torch.where((py < 0).unsqueeze(1), root_mask, child_mask)
        future_mask = future_mask & (py < 14).unsqueeze(1)
        future_y = (py + 1).clamp(0, 14)
        future_nodes = graph[batch_ids, future_y]
        mean, maximum = self.masked_pool(future_nodes, future_mask)
        return self.readout(torch.cat((mean, maximum), 1))


class CardActionValue(nn.Module):
    def __init__(self, nscalar, use_map=False):
        super().__init__()
        dcard, drelic, dpot = 32, 16, 8
        self.use_map = use_map
        self.card_base = nn.Embedding(372, dcard)
        self.card_up = nn.Embedding(372, dcard)
        self.relic_id = nn.Embedding(181, drelic)
        self.relic_value = nn.Linear(1, drelic, bias=False)
        self.potion_id = nn.Embedding(48, dpot)
        self.potion_value = nn.Linear(1, dpot, bias=False)
        self.encounter = nn.Parameter(torch.randn(5, 128, 8) * 0.02)
        self.bottle = nn.Parameter(torch.randn(3, 373, 12) * 0.02)
        self.action_base = nn.Embedding(373, dcard)  # index 0 is skip
        self.action_up = nn.Embedding(373, dcard)
        self.map_graph = FullMapGraphEncoder() if use_map else None
        self.map_adapter = nn.Linear(96, 192, bias=False) if use_map else None
        if self.map_adapter is not None:
            nn.init.zeros_(self.map_adapter.weight)
        state_in = nscalar + 2*dcard + 2*drelic + 2*dpot + 40 + 36
        self.state = nn.Sequential(
            nn.Linear(state_in, 192), nn.LayerNorm(192), nn.SiLU(),
            nn.Linear(192, 128), nn.SiLU(),
        )
        self.state_action = nn.Linear(128, dcard)
        self.action_query = nn.Linear(dcard, dcard, bias=False)
        self.head = nn.Sequential(
            nn.Linear(128 + 3*dcard, 128), nn.LayerNorm(128), nn.SiLU(),
            nn.Dropout(0.08), nn.Linear(128, 64), nn.SiLU(), nn.Linear(64, 1),
        )
        # Direct simulator-derived expert supervision: clear next combat,
        # next routed elite, and current-act boss.  It shares every encoder
        # with the action-value head, so it improves the representation even
        # when policy selection remains purely value-based.
        self.survival_head = nn.Sequential(
            nn.Linear(128 + 3*dcard, 128), nn.LayerNorm(128), nn.SiLU(),
            nn.Dropout(0.08), nn.Linear(128, 64), nn.SiLU(), nn.Linear(64, 3),
        )
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
                candidate, candidate_up, action_mask, map_rooms=None, map_edges=None,
                map_special=None, map_position=None):
        base_count = (deck.float() - upgrades.float()).clamp_min(0)
        up_count = upgrades.float()
        total = base_count + up_count
        card_token = (base_count.unsqueeze(-1) * self.card_base(self.card_ids)[None]
                      + up_count.unsqueeze(-1) * self.card_up(self.card_ids)[None]) \
                     / total.clamp_min(1).unsqueeze(-1)
        card_token = torch.relu(card_token)
        card_pool = self.pool(card_token, total, total > 0)

        rv = relics.float()
        relic_token = torch.relu(self.relic_id(self.relic_ids)[None]
                                 + self.relic_value(torch.log1p(rv).unsqueeze(-1)))
        relic_pool = self.pool(relic_token, rv, rv > 0)
        pv = potions.float()
        potion_token = torch.relu(self.potion_id(self.potion_ids)[None]
                                  + self.potion_value(torch.log1p(pv).unsqueeze(-1)))
        potion_pool = self.pool(potion_token, pv, pv > 0)
        enc = torch.stack([self.encounter[i, encounters[:, i].long()]
                           for i in range(5)], 1).flatten(1)
        bottle = torch.stack([self.bottle[i, bottles[:, i].long()]
                              for i in range(3)], 1).flatten(1)
        state_parts = [scalar, card_pool, relic_pool, potion_pool, enc, bottle]
        state_pre = self.state[0](torch.cat(state_parts, 1))
        if self.use_map:
            map_value = self.map_graph(map_rooms, map_edges, map_special, map_position)
            state_pre = state_pre + self.map_adapter(map_value)
        state = self.state[1:](state_pre)

        abase = self.action_base(candidate)
        aup = self.action_up(candidate)
        action = torch.where(candidate_up.unsqueeze(-1).bool(), aup, abase)
        query = self.action_query(action)
        attn_logits = torch.einsum("bad,bcd->bac", query, card_token) / math.sqrt(32.0)
        deck_mask = total > 0
        attn_logits = attn_logits.masked_fill(~deck_mask[:, None, :], -1e9)
        attn = torch.softmax(attn_logits, -1)
        context = torch.einsum("bac,bcd->bad", attn, card_token)
        interaction = self.state_action(state)[:, None, :] * action
        expanded = state[:, None, :].expand(-1, candidate.shape[1], -1)
        head_in = torch.cat((expanded, action, context, interaction), -1)
        q = self.head(head_in).squeeze(-1)
        survival = self.survival_head(head_in)
        q = q.masked_fill(~action_mask, -1e9)
        is_skip = (candidate == 0) & action_mask
        skip_q = q.masked_fill(~is_skip, 0).sum(1, keepdim=True)
        return ((q - skip_q).masked_fill(~action_mask, -1e9), survival)


arrays = [scalars, deck, upgrades, relics, potions, encounters, bottles,
          candidate, candidate_up, action_mask]
if MAP_CSV:
    arrays += [map_rooms, map_edges, map_special, map_position]
arrays += [advantage, score, survival, survival_mask]
tensors = [torch.from_numpy(np.ascontiguousarray(a)) for a in arrays]
input_count = 14 if MAP_CSV else 10
target_idx = input_count
score_idx = input_count + 1
survival_idx = input_count + 2
survival_mask_idx = input_count + 3


def forward_batch(model, ids):
    x = [t[ids].to(DEVICE) for t in tensors[:input_count]]
    return model(*x)


@torch.no_grad()
def evaluate(model, indices, tag):
    model.eval()
    preds, survival_preds = [], []
    for lo in range(0, len(indices), BATCH):
        ids = torch.from_numpy(indices[lo:lo+BATCH].astype(np.int64, copy=False))
        q, p = forward_batch(model, ids)
        preds.append(q.cpu())
        survival_preds.append(p.cpu())
    pred = torch.cat(preds).numpy()
    survival_pred = torch.cat(survival_preds).numpy()
    mask = action_mask[indices]
    actual = score[indices]
    safe_pred = np.where(mask, pred, -1e9)
    selected_idx = safe_pred.argmax(1)
    selected = actual[np.arange(len(indices)), selected_idx]
    oracle = np.where(mask, actual, -1e9).max(1)
    skip = skip_score[indices]
    best_mask = mask & (actual >= oracle[:, None] - 1e-6)
    top1 = best_mask[np.arange(len(indices)), selected_idx].mean()
    non_skip = mask & (candidate[indices] != 0)
    sign = ((pred >= 0) == (advantage[indices] >= 0))[non_skip].mean()
    rmse = np.sqrt(np.mean((pred[mask] - advantage[indices][mask])**2)) * 10
    out = {
        "decisions": int(len(indices)), "top1_or_tie": float(top1),
        "selected_score": float(selected.mean()), "skip_score": float(skip.mean()),
        "oracle_score": float(oracle.mean()), "regret": float((oracle-selected).mean()),
        "sign_vs_skip": float(sign), "adv_rmse": float(rmse),
    }
    if has_survival_probes:
        sm = survival_mask[indices] & mask[:, :, None]
        sp, st = survival_pred[sm], survival[indices][sm]
        out["survival_bce"] = float(nn.functional.binary_cross_entropy_with_logits(
            torch.from_numpy(sp), torch.from_numpy(st)).item())
        out["survival_accuracy"] = float(((sp >= 0) == (st >= 0.5)).mean())
    print(f"{tag}: top1/tie {top1:.3f}, selected {selected.mean():.3f}, "
          f"skip {skip.mean():.3f}, oracle {oracle.mean():.3f}, "
          f"regret {(oracle-selected).mean():.3f}, sign {sign:.3f}, RMSE {rmse:.3f}", flush=True)
    return out, pred


model = CardActionValue(len(scalar_cols), use_map=bool(MAP_CSV)).to(DEVICE)
if INIT_MODEL:
    init = torch.load(INIT_MODEL, map_location="cpu", weights_only=False)["state"]
    required = {
        "E_base.weight": model.card_base.weight,
        "E_up.weight": model.card_up.weight,
        "E_rel.weight": model.relic_id.weight,
        "E_pot.weight": model.potion_id.weight,
    }
    with torch.no_grad():
        for name, dst in required.items():
            src = init[name]
            if src.shape != dst.shape:
                raise ValueError(f"initializer {name} shape {tuple(src.shape)} != {tuple(dst.shape)}")
            dst.copy_(src.to(dst.device))
        # Candidate identities live at shifted indices 1..372; skip remains a
        # separately learned index 0.  Starting state/action identities in the
        # same semantic space makes candidate-to-deck attention meaningful from
        # the first paired example.
        model.action_base.weight[1:].copy_(init["E_base.weight"].to(DEVICE))
        model.action_up.weight[1:].copy_(init["E_up.weight"].to(DEVICE))
    print(f"initialized entity/action embeddings from {INIT_MODEL}", flush=True)
if BASE_MODEL:
    old = torch.load(BASE_MODEL, map_location="cpu", weights_only=False)["state_dict"]
    current = model.state_dict()
    copied = 0
    with torch.no_grad():
        for name, src in old.items():
            if name not in current:
                continue
            dst = current[name]
            if src.shape == dst.shape:
                dst.copy_(src); copied += src.numel()
            elif name == "state.0.weight" and src.shape[0] == dst.shape[0] and src.shape[1] < dst.shape[1]:
                dst.zero_(); dst[:, :src.shape[1]].copy_(src); copied += src.numel()
        model.load_state_dict(current)
    print(f"initialized {copied:,} shared parameters from card-action model {BASE_MODEL}", flush=True)
print(f"model parameters {sum(p.numel() for p in model.parameters()):,}; device {DEVICE}; "
      f"CPU threads {THREADS}", flush=True)
if MAP_CSV and BASE_MODEL and FREEZE_BASE_EPOCHS:
    for name, parameter in model.named_parameters():
        # Preserve the proven card-ranking function initially; only the new
        # expert head sees gradients until it has a sensible calibration.
        if not name.startswith("survival_head."):
            parameter.requires_grad_(False)
    print(f"freezing pretrained card model for {FREEZE_BASE_EPOCHS} epoch(s)", flush=True)
opt = torch.optim.AdamW(model.parameters(), lr=8e-4, weight_decay=2e-4)
rng = np.random.default_rng(0)
if MAP_CSV and BASE_MODEL:
    initial_metrics, _ = evaluate(model, va, "exact pretrained baseline")
    best_objective = initial_metrics["regret"] + 0.05 * initial_metrics["adv_rmse"]
    best_state = copy.deepcopy(model.state_dict())
else:
    best_state, best_objective = None, float("inf")
stale = 0

for epoch in range(1, EPOCHS + 1):
    if FREEZE_BASE_EPOCHS and epoch == FREEZE_BASE_EPOCHS + 1:
        for parameter in model.parameters():
            parameter.requires_grad_(True)
        print("unfroze full card-action model", flush=True)
    model.train()
    order = rng.permutation(tr)
    losses = []
    for lo in range(0, len(order), BATCH):
        ids_np = order[lo:lo+BATCH]
        ids = torch.from_numpy(ids_np.astype(np.int64, copy=False))
        q, survival_logit = forward_batch(model, ids)
        mask = tensors[9][ids].to(DEVICE)
        target = tensors[target_idx][ids].to(DEVICE)
        actual = tensors[score_idx][ids].to(DEVICE)
        huber = nn.functional.smooth_l1_loss(q[mask], target[mask], beta=0.5)
        best_value = actual.masked_fill(~mask, -1e9).max(1, keepdim=True).values
        best_mask = mask & (actual >= best_value - 1e-6)
        target_prob = best_mask.float() / best_mask.sum(1, keepdim=True)
        logp = torch.log_softmax(q.masked_fill(~mask, -1e9), 1)
        ranking = -(target_prob * logp).sum(1).mean()
        loss = huber + 0.25 * ranking
        if has_survival_probes:
            survival_target = tensors[survival_idx][ids].to(DEVICE)
            survival_valid = tensors[survival_mask_idx][ids].to(DEVICE) & mask[:, :, None]
            survival_loss = nn.functional.binary_cross_entropy_with_logits(
                survival_logit[survival_valid], survival_target[survival_valid])
            loss = loss + SURVIVAL_LOSS_WEIGHT * survival_loss
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()
        losses.append(float(loss.detach()))
    vm, _ = evaluate(model, va, f"epoch {epoch:02d} val")
    objective = vm["regret"] + 0.05 * vm["adv_rmse"]
    meaningful_improvement = objective < best_objective - 0.01
    if objective < best_objective:
        best_objective = objective
        best_state = copy.deepcopy(model.state_dict())
    if meaningful_improvement:
        stale = 0
    else:
        stale += 1
    print(f"epoch {epoch:02d}: train loss {np.mean(losses):.5f}, objective {objective:.4f}", flush=True)
    if stale >= 7:
        break

model.load_state_dict(best_state)
val_metrics, val_pred = evaluate(model, va, "BEST card action NN")


def tree_reference_metrics(indices):
    if not TREE_REF:
        return None
    import xgboost as xgb
    booster = xgb.Booster()
    booster.load_model(TREE_REF)
    feats = list(booster.feature_names)
    base = state.iloc[indices][feats].to_numpy(np.float32)
    chosen = []
    for j, di in enumerate(indices):
        rows = [base[j].copy()]
        positions = [int(np.flatnonzero((candidate[di] == 0) & action_mask[di])[0])]
        for ai in np.flatnonzero(action_mask[di] & (candidate[di] != 0)):
            row = base[j].copy()
            cid = int(candidate[di, ai] - 1)
            if "deckSize" in feats: row[feats.index("deckSize")] += 1
            if f"d{cid}" in feats: row[feats.index(f"d{cid}")] += 1
            if candidate_up[di, ai] and f"u{cid}" in feats: row[feats.index(f"u{cid}")] += 1
            rows.append(row); positions.append(int(ai))
        pred = booster.predict(xgb.DMatrix(np.stack(rows), feature_names=feats))
        marginal = pred[1:] - pred[0]
        if len(marginal) and marginal.max() >= SKIP_THRESHOLD:
            chosen.append(positions[1 + int(marginal.argmax())])
        else:
            chosen.append(positions[0])
    actual = score[indices]
    selected = actual[np.arange(len(indices)), np.asarray(chosen)]
    oracle = np.where(action_mask[indices], actual, -1e9).max(1)
    best = actual[np.arange(len(indices)), np.asarray(chosen)] >= oracle - 1e-6
    out = {"selected_score": float(selected.mean()), "regret": float((oracle-selected).mean()),
           "top1_or_tie": float(best.mean())}
    print(f"tree reference: top1/tie {best.mean():.3f}, selected {selected.mean():.3f}, "
          f"regret {(oracle-selected).mean():.3f}", flush=True)
    return out


tree_metrics = tree_reference_metrics(va)
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.state_dict(), "scalar_cols": scalar_cols,
            "scalar_mean": scalar_mean, "scalar_inv": scalar_inv,
            "max_actions": max_actions, "metrics": val_metrics,
            "tree_metrics": tree_metrics, "initializer": INIT_MODEL,
            "base_initializer": BASE_MODEL, "map_csv": MAP_CSV,
            "future_fight_probes": has_survival_probes,
            "survival_loss_weight": SURVIVAL_LOSS_WEIGHT if has_survival_probes else 0.0}, OUT + ".pt")
np.savez(OUT + ".npz", scalar_cols=np.asarray(scalar_cols),
         scalar_mean=scalar_mean, scalar_inv=scalar_inv)
example_ids = torch.from_numpy(va[:min(2, len(va))].astype(np.int64, copy=False))
example = [t[example_ids].to(DEVICE) for t in tensors[:input_count]]
model.eval()
torch.jit.trace(model, tuple(example)).save(OUT + ".torchscript")

records = []
for j, di in enumerate(va):
    for ai in np.flatnonzero(action_mask[di]):
        records.append({"seed": int(decision_seed[di]), "decisionIdx": int(df.loc[first_rows[di], "decisionIdx"]),
                        "candidateId": int(candidate[di, ai]-1), "score": float(score[di, ai]),
                        "advantage": float(advantage[di, ai]*10), "prediction": float(val_pred[j, ai]*10)})
pd.DataFrame(records).to_csv(OUT + "_val.csv", index=False)
with open(OUT + "_metrics.json", "w") as f:
    json.dump({"decisions": nd, "runs": int(len(np.unique(decision_seed))),
               "actions": int(action_mask.sum()), "train": len(tr), "val": len(va),
               "initializer": INIT_MODEL, "base_initializer": BASE_MODEL,
               "map_csv": MAP_CSV, "future_fight_probes": has_survival_probes,
               "survival_loss_weight": SURVIVAL_LOSS_WEIGHT if has_survival_probes else 0.0,
               "nn": val_metrics, "trees": tree_metrics}, f, indent=2)
print(f"saved {OUT}.pt, .torchscript, .npz, _val.csv and _metrics.json", flush=True)
