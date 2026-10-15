#!/usr/bin/env python3
"""Train a direct graph path-action model from paired full-run route branches.

Usage:
  train_path_cf.py PATH_CF.csv MAPS.csv OUT_PREFIX
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


CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/path_buffer/path_cf.csv"
MAP_CSV = sys.argv[2] if len(sys.argv) > 2 else "selfplay/path_buffer/path_maps.csv"
OUT = sys.argv[3] if len(sys.argv) > 3 else "selfplay/models/path_cf"
INIT_MODEL = os.environ.get("PATH_CF_INIT", "selfplay/models/meta_graph_full21k.pt")
EPOCHS = int(os.environ.get("PATH_CF_EPOCHS", "50"))
BATCH = int(os.environ.get("PATH_CF_BATCH", "256"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
DEVICE = os.environ.get("PATH_CF_DEVICE", "cpu")
FREEZE_EPOCHS = int(os.environ.get("PATH_CF_FREEZE_ENCODER_EPOCHS", "3"))
MIN_DECISIONS = int(os.environ.get("PATH_CF_MIN_DECISIONS", "100"))
WIN_BONUS = float(os.environ.get("STS_PATH_CF_WIN_BONUS", "10.0"))

if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.manual_seed(0)
torch.set_num_threads(THREADS)

LABELS = {"seed", "decisionIdx", "actionIdx", "candidateX", "heuristicX",
          "branchWon", "branchFloor", "branchHp"}
ENCOUNTER_CATS = ["bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2"]
BOTTLE_CATS = ["bottledAtkId", "bottledSkillId", "bottledPowId"]
DECK_COLS = [f"d{i}" for i in range(372)]
UPGRADE_COLS = [f"u{i}" for i in range(372)]
RELIC_COLS = [f"r{i}" for i in range(181)]
POTION_COLS = [f"pot{i}" for i in range(48)]

print(f"loading paired path decisions {CSV} ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
missing = LABELS - set(df.columns)
if missing:
    raise ValueError(f"path-CF CSV missing columns: {sorted(missing)}")
groups = list(df.groupby(["seed", "decisionIdx"], sort=False))
if len(groups) < MIN_DECISIONS:
    raise ValueError(f"need >= {MIN_DECISIONS} paired path decisions, got {len(groups)}")
max_actions = max(len(g) for _, g in groups)
if max_actions > 7:
    raise ValueError(f"unexpected path action count {max_actions}")

nd = len(groups)
first_rows = np.empty(nd, np.int64)
decision_seed = np.empty(nd, np.int64)
candidate = np.zeros((nd, max_actions), np.int64)
action_mask = np.zeros((nd, max_actions), bool)
score = np.full((nd, max_actions), -1e9, np.float32)
heuristic_pos = np.zeros(nd, np.int64)

for di, ((seed_key, _), g) in enumerate(groups):
    first_rows[di] = g.index[0]
    decision_seed[di] = int(seed_key)
    hx = int(g["heuristicX"].iloc[0])
    if g["heuristicX"].nunique() != 1 or g["candidateX"].nunique() != len(g):
        raise ValueError(f"malformed path decision {seed_key}")
    found_heuristic = False
    for ai, (_, row) in enumerate(g.iterrows()):
        x = int(row["candidateX"])
        candidate[di, ai] = x
        action_mask[di, ai] = True
        score[di, ai] = float(row["branchFloor"] + WIN_BONUS * row["branchWon"])
        if x == hx:
            heuristic_pos[di] = ai
            found_heuristic = True
    if not found_heuristic:
        raise ValueError(f"heuristic child {hx} missing from decision {seed_key}")

state = df.loc[first_rows]
entity_cols = set(DECK_COLS + UPGRADE_COLS + RELIC_COLS + POTION_COLS
                  + ENCOUNTER_CATS + BOTTLE_CATS)
scalar_cols = [c for c in df.columns if c not in LABELS and c not in entity_cols]
deck = state[DECK_COLS].to_numpy(np.uint8)
upgrades = state[UPGRADE_COLS].to_numpy(np.uint8)
relics = np.maximum(state[RELIC_COLS].to_numpy(np.float32), 0).astype(np.float32)
potions = np.maximum(state[POTION_COLS].to_numpy(np.float32), 0).astype(np.float32)
encounters = np.clip(state[ENCOUNTER_CATS].to_numpy(np.int64)+1, 0, 127).astype(np.uint8)
bottles = np.clip(state[BOTTLE_CATS].to_numpy(np.int64)+1, 0, 372).astype(np.int16)
scalars = state[scalar_cols].to_numpy(np.float32)
map_position = state[["curMapX", "curMapY"]].to_numpy(np.int16)

print(f"loading map graphs {MAP_CSV} ...", flush=True)
map_df = pd.read_csv(MAP_CSV).set_index(["seed", "ascension", "act"])
state_keys = pd.MultiIndex.from_arrays([
    state["seed"].astype(np.int64), state["ascension"].astype(np.int64),
    state["act"].astype(np.int64)], names=["seed", "ascension", "act"])
aligned = map_df.reindex(state_keys)
if aligned[["room0", "edges0"]].isna().any().any():
    raise ValueError("map table does not cover every path decision")
map_rooms = aligned[[f"room{i}" for i in range(105)]].to_numpy(np.uint8)
map_edges = aligned[[f"edges{i}" for i in range(105)]].to_numpy(np.uint8)
map_special = np.zeros((nd, 105), np.uint8)
bx = aligned["burningEliteX"].to_numpy(np.int16)
by = aligned["burningEliteY"].to_numpy(np.int16)
active = (bx >= 0) & (by >= 0) & (state["greenKey"].to_numpy() < 0.5)
map_special[np.flatnonzero(active), by[active]*7 + bx[active]] = 1

tr, va = next(GroupShuffleSplit(1, test_size=0.20, random_state=0)
              .split(np.arange(nd), groups=decision_seed))
initializer = torch.load(INIT_MODEL, map_location="cpu", weights_only=False) if INIT_MODEL else None
if initializer:
    if list(initializer["scalar_cols"]) != scalar_cols:
        raise ValueError("initializer scalar schema mismatch")
    scalar_mean = np.asarray(initializer["scalar_mean"], np.float32)
    scalar_inv = np.asarray(initializer["scalar_inv"], np.float32)
else:
    scalar_mean = scalars[tr].mean(0, dtype=np.float64).astype(np.float32)
    scalar_inv = 1 / np.maximum(scalars[tr].std(0, dtype=np.float64).astype(np.float32), 1e-6)
scalars = (scalars-scalar_mean)*scalar_inv

valid_count = action_mask.sum(1, keepdims=True)
mean_score = np.where(action_mask, score, 0).sum(1, keepdims=True) / valid_count
advantage = (score-mean_score)/10.0
advantage[~action_mask] = 0
print(f"decisions {nd:,}, actions {int(action_mask.sum()):,}, max {max_actions}, "
      f"train {len(tr):,}, val {len(va):,}", flush=True)


class MapNodeEncoder(nn.Module):
    def __init__(self, dnode=32):
        super().__init__()
        self.room = nn.Embedding(10, dnode)
        self.row = nn.Embedding(15, dnode)
        self.col = nn.Embedding(7, dnode)
        self.burning = nn.Embedding(2, dnode)
        self.update = nn.Sequential(
            nn.Linear(3*dnode+1, 64), nn.LayerNorm(64), nn.SiLU(), nn.Linear(64, dnode))
        self.norm = nn.LayerNorm(dnode)
        self.register_buffer("row_ids", torch.arange(15))
        self.register_buffer("col_ids", torch.arange(7))
        self.register_buffer("edge_bits", torch.arange(7))

    def forward(self, rooms, edges, special):
        b = rooms.shape[0]
        rooms = rooms.long().view(b, 15, 7)
        edges = edges.long().view(b, 15, 7)
        special = special.long().view(b, 15, 7)
        base = (self.room(rooms) + self.row(self.row_ids)[None,:,None,:]
                + self.col(self.col_ids)[None,None,:,:] + self.burning(special))
        adjacency = ((edges.unsqueeze(-1) >> self.edge_bits) & 1).bool()
        rows = [base[:,14]]
        for y in range(13, -1, -1):
            child = rows[-1]; edge = adjacency[:,y]
            mean = torch.bmm(edge.float(), child) / edge.sum(2,keepdim=True).clamp_min(1.0)
            expanded = child[:,None,:,:].expand(-1,7,-1,-1)
            maximum = expanded.masked_fill(~edge.unsqueeze(-1), -1e9).max(2).values
            maximum = torch.where(edge.any(2,keepdim=True), maximum, torch.zeros_like(maximum))
            degree = torch.log1p(edge.sum(2,keepdim=True).float())
            rows.append(self.norm(base[:,y] + self.update(
                torch.cat((base[:,y],mean,maximum,degree),2))))
        return torch.stack(list(reversed(rows)), 1)


class PathActionValue(nn.Module):
    def __init__(self, nscalar):
        super().__init__()
        self.card_id = nn.Embedding(372, 32)
        self.card_count = nn.Linear(2, 32, bias=False)
        self.relic_id = nn.Embedding(181, 16)
        self.relic_value = nn.Linear(1, 16, bias=False)
        self.potion_id = nn.Embedding(48, 8)
        self.potion_value = nn.Linear(1, 8, bias=False)
        self.encounter = nn.Parameter(torch.randn(5,128,8)*0.02)
        self.bottle = nn.Parameter(torch.randn(3,373,12)*0.02)
        self.trunk = nn.Sequential(
            nn.Linear(nscalar+64+32+16+40+36,192), nn.LayerNorm(192), nn.SiLU(),
            nn.Dropout(0.05), nn.Linear(192,96), nn.SiLU())
        self.map_graph = MapNodeEncoder()
        self.state_to_node = nn.Linear(96,32)
        self.head = nn.Sequential(
            nn.Linear(96+64,128), nn.LayerNorm(128), nn.SiLU(), nn.Dropout(0.08),
            nn.Linear(128,64), nn.SiLU(), nn.Linear(64,1))
        self.register_buffer("card_ids",torch.arange(372))
        self.register_buffer("relic_ids",torch.arange(181))
        self.register_buffer("potion_ids",torch.arange(48))

    @staticmethod
    def pool(entity, weight, mask):
        denom=torch.sqrt(weight.sum(1,keepdim=True).clamp_min(1.0))
        summed=(entity*torch.sqrt(weight).unsqueeze(-1)).sum(1)/denom
        maximum=entity.masked_fill(~mask.unsqueeze(-1),-1e9).max(1).values
        maximum=torch.where(mask.any(1,keepdim=True),maximum,torch.zeros_like(maximum))
        return torch.cat((summed,maximum),1)

    def forward(self, scalar, deck, upgrades, relics, potions, encounters, bottles,
                map_rooms, map_edges, map_special, map_position, candidate, action_mask):
        dc=deck.float()
        card_feat=torch.stack((torch.log1p(dc),upgrades.float()/dc.clamp_min(1)),-1)
        card=torch.relu(self.card_id(self.card_ids)[None]+self.card_count(card_feat))
        card=self.pool(card,dc,dc>0)
        rv=relics.float(); rel=torch.relu(self.relic_id(self.relic_ids)[None]
            +self.relic_value(torch.log1p(rv).unsqueeze(-1)))
        rel=self.pool(rel,rv,rv>0)
        pv=potions.float(); pot=torch.relu(self.potion_id(self.potion_ids)[None]
            +self.potion_value(torch.log1p(pv).unsqueeze(-1)))
        pot=self.pool(pot,pv,pv>0)
        enc=torch.stack([self.encounter[i,encounters[:,i].long()] for i in range(5)],1).flatten(1)
        bot=torch.stack([self.bottle[i,bottles[:,i].long()] for i in range(3)],1).flatten(1)
        state=self.trunk(torch.cat((scalar,card,rel,pot,enc,bot),1))
        graph=self.map_graph(map_rooms,map_edges,map_special)
        b,a=candidate.shape
        row=(map_position[:,1].long()+1).clamp(0,14)[:,None].expand(-1,a)
        bid=torch.arange(b,device=candidate.device)[:,None].expand(-1,a)
        node=graph[bid,row,candidate.long().clamp(0,6)]
        interaction=self.state_to_node(state)[:,None,:]*node
        expanded=state[:,None,:].expand(-1,a,-1)
        q=self.head(torch.cat((expanded,node,interaction),2)).squeeze(-1)
        q=q.masked_fill(~action_mask,-1e9)
        center=q.masked_fill(~action_mask,0).sum(1,keepdim=True)/action_mask.sum(1,keepdim=True).clamp_min(1)
        return (q-center).masked_fill(~action_mask,-1e9)


arrays=[scalars,deck,upgrades,relics,potions,encounters,bottles,map_rooms,map_edges,
        map_special,map_position,candidate,action_mask,advantage,score]
tensors=[torch.from_numpy(np.ascontiguousarray(a)) for a in arrays]

def forward_batch(model, ids):
    return model(*[t[ids].to(DEVICE) for t in tensors[:13]])

@torch.no_grad()
def evaluate(model, ids, tag):
    model.eval(); pred=[]
    for lo in range(0,len(ids),BATCH):
        ix=torch.from_numpy(ids[lo:lo+BATCH].astype(np.int64,copy=False))
        pred.append(forward_batch(model,ix).cpu())
    pred=torch.cat(pred).numpy(); mask=action_mask[ids]; actual=score[ids]
    chosen=np.where(mask,pred,-1e9).argmax(1)
    selected=actual[np.arange(len(ids)),chosen]
    heuristic=actual[np.arange(len(ids)),heuristic_pos[ids]]
    oracle=np.where(mask,actual,-1e9).max(1)
    top=(selected>=oracle-1e-6).mean()
    rmse=np.sqrt(np.mean((pred[mask]-advantage[ids][mask])**2))*10
    delta=selected-heuristic; se=delta.std(ddof=1)/math.sqrt(len(delta))
    out={"decisions":int(len(ids)),"top1_or_tie":float(top),"selected_score":float(selected.mean()),
         "heuristic_score":float(heuristic.mean()),"oracle_score":float(oracle.mean()),
         "regret":float((oracle-selected).mean()),"adv_rmse":float(rmse),
         "delta_vs_heuristic":float(delta.mean()),"delta_se":float(se),
         "delta_ci99":[float(delta.mean()-2.575829*se),float(delta.mean()+2.575829*se)]}
    print(f"{tag}: top1/tie {top:.3f}, selected {selected.mean():.3f}, heuristic {heuristic.mean():.3f}, "
          f"oracle {oracle.mean():.3f}, regret {(oracle-selected).mean():.3f}, RMSE {rmse:.3f}, "
          f"delta {delta.mean():+.3f} +/-99% {2.575829*se:.3f}",flush=True)
    return out,pred

model=PathActionValue(len(scalar_cols)).to(DEVICE)
if initializer:
    current=model.state_dict(); copied=0
    with torch.no_grad():
        for name,src in initializer["state_dict"].items():
            if name in current and current[name].shape==src.shape:
                current[name].copy_(src); copied+=src.numel()
        model.load_state_dict(current)
    print(f"initialized {copied:,} parameters from {INIT_MODEL}",flush=True)
if FREEZE_EPOCHS:
    for name,p in model.named_parameters():
        if not (name.startswith("state_to_node.") or name.startswith("head.")):
            p.requires_grad_(False)
print(f"model parameters {sum(p.numel() for p in model.parameters()):,}; device {DEVICE}",flush=True)
opt=torch.optim.AdamW(model.parameters(),lr=8e-4,weight_decay=2e-4)
rng=np.random.default_rng(0); best=None; best_obj=float("inf"); stale=0
for epoch in range(1,EPOCHS+1):
    if FREEZE_EPOCHS and epoch==FREEZE_EPOCHS+1:
        for p in model.parameters(): p.requires_grad_(True)
        print("unfroze full path model",flush=True)
    model.train(); order=rng.permutation(tr); losses=[]
    for lo in range(0,len(order),BATCH):
        ids_np=order[lo:lo+BATCH]; ids=torch.from_numpy(ids_np.astype(np.int64,copy=False))
        q=forward_batch(model,ids); mask=tensors[12][ids].to(DEVICE)
        target=tensors[13][ids].to(DEVICE); actual=tensors[14][ids].to(DEVICE)
        huber=nn.functional.smooth_l1_loss(q[mask],target[mask],beta=0.5)
        bestv=actual.masked_fill(~mask,-1e9).max(1,keepdim=True).values
        bestmask=mask&(actual>=bestv-1e-6)
        targetp=bestmask.float()/bestmask.sum(1,keepdim=True)
        ranking=-(targetp*torch.log_softmax(q.masked_fill(~mask,-1e9),1)).sum(1).mean()
        loss=huber+0.25*ranking
        opt.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),5.0); opt.step()
        losses.append(float(loss.detach()))
    vm,_=evaluate(model,va,f"epoch {epoch:02d} val")
    obj=vm["regret"]+0.05*vm["adv_rmse"]
    if obj<best_obj:
        improvement=best_obj-obj; best_obj=obj; best=copy.deepcopy(model.state_dict())
        stale=0 if improvement>0.01 else stale+1
    else: stale+=1
    print(f"epoch {epoch:02d} loss {np.mean(losses):.5f} objective {obj:.4f}",flush=True)
    if stale>=7: break

model.load_state_dict(best)
metrics,pred=evaluate(model,va,"BEST direct path NN")
os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
torch.save({"state_dict":model.state_dict(),"scalar_cols":scalar_cols,"scalar_mean":scalar_mean,
            "scalar_inv":scalar_inv,"max_actions":max_actions,"metrics":metrics,
            "initializer":INIT_MODEL,"map_csv":MAP_CSV},OUT+".pt")
np.savez(OUT+".npz",scalar_cols=np.asarray(scalar_cols),scalar_mean=scalar_mean,scalar_inv=scalar_inv)
example_ids=torch.from_numpy(va[:min(2,len(va))].astype(np.int64,copy=False))
model.eval(); torch.jit.trace(model,tuple(t[example_ids].to(DEVICE) for t in tensors[:13])).save(OUT+".torchscript")
records=[]
for j,di in enumerate(va):
    for ai in np.flatnonzero(action_mask[di]):
        records.append({"seed":int(decision_seed[di]),"candidateX":int(candidate[di,ai]),
                        "heuristic":bool(ai==heuristic_pos[di]),"score":float(score[di,ai]),
                        "prediction":float(pred[j,ai]*10)})
pd.DataFrame(records).to_csv(OUT+"_val.csv",index=False)
with open(OUT+"_metrics.json","w") as f:
    json.dump({"decisions":nd,"actions":int(action_mask.sum()),"train":len(tr),"val":len(va),
               "initializer":INIT_MODEL,"map_csv":MAP_CSV,"nn":metrics},f,indent=2)
print(f"saved {OUT}.pt, .torchscript, .npz, _val.csv and _metrics.json",flush=True)
