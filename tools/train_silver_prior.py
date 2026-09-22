#!/usr/bin/env python3
"""Train/evaluate SilverPriorNetV1 using the frozen Silver prior projection.

The ordinary fitting path admits TRAIN and VALIDATION only. LOCKED_TEST is not
an accepted split value; its eventual evaluation is a separate future task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import pickle
import time
import resource
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import silver_prior_dataset as dataset
import silver_prior_projection as projection

SEED = 20260922
RELEASE = "b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419"
BINDING = "7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17"
SELECTION = "ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed"
PREPROCESS_SCHEMA = "silver_prior_v1_tensor_cache_3"
PROJECTION_FIELD_CONSUMPTION = {
    "schema": "REDUNDANT_BY_CONSTRUCTION",
    "global": "MODEL_INPUT", "player": "MODEL_INPUT",
    "evaluation_context": "MODEL_INPUT", "cards": "MODEL_INPUT",
    "monsters": "MODEL_INPUT", "potions": "MODEL_INPUT",
    "candidates": "MODEL_INPUT", "miscFlags": "MODEL_INPUT",
    "extraRollMoveSlots": "MODEL_INPUT", "skipMonsterTurnSlots": "MODEL_INPUT",
    "zones": "MODEL_INPUT", "piles": "MODEL_INPUT",
}
NUMERIC_GLOBAL = projection.GLOBAL
NUMERIC_PLAYER = projection.PLAYER


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_train_and_validation(directory):
    """Verify the release gate and return only TRAIN/VALIDATION L rows."""
    directory = Path(directory)
    release = dataset.read(directory / "release.json")
    dataset.check_seal(release)
    if release["sha256"] != RELEASE or not release["training_ready"]:
        raise ValueError("unexpected or unready release")
    binding, selection, vocab, plan = [dataset.read(directory / n) for n in
        ("binding.json", "selection.json", "vocabulary.json", "plan.json")]
    for item in (binding, selection, plan): dataset.check_seal(item)
    projection.validate_vocabulary(vocab)
    if binding["sha256"] != BINDING or selection["sha256"] != SELECTION or release["binding_sha256"]!=binding["sha256"] or release["selection_sha256"]!=selection["sha256"]:
        raise ValueError("frozen binding/selection mismatch")
    if binding["plan_sha256"]!=plan["sha256"] or selection["plan_sha256"]!=plan["sha256"] or selection["executable_git_sha"]!=binding["executable_git_sha"] or selection["pilot"]:
        raise ValueError("release plan/selection binding mismatch")
    if plan["vocabulary_sha256"]!=vocab["sha256"]: raise ValueError("vocabulary binding mismatch")
    checksums = {f["path"]: f["sha256"] for f in release["files"]}
    quarantine = set(release["quarantined_roots"])
    resolution_hash=release.get("quarantine_resolution_sha256")
    if bool(quarantine)!=bool(resolution_hash): raise ValueError("release quarantine resolution mismatch")
    if resolution_hash:
        resolution=dataset.read(directory/"resolutions"/f"{resolution_hash}.json");dataset.check_seal(resolution)
        if resolution["schema"]!="silver_prior_quarantine_v1" or resolution["sha256"]!=resolution_hash or resolution["binding_sha256"]!=binding["sha256"] or resolution["selection_sha256"]!=selection["sha256"] or set(resolution["quarantined_roots"])!=quarantine:
            raise ValueError("sealed quarantine resolution mismatch")
    result = {"TRAIN": [], "VALIDATION": []}
    for entry in selection["entries"]:
        split = entry["split"]
        if split not in result or entry["root"]["root_id"] in quarantine: continue
        root = entry["root"]
        rel = f"shards/L/{dataset.identity_hash(root)}.json.gz"
        if checksums.get(rel) != dataset.file_hash(directory / rel):
            raise ValueError("release shard checksum mismatch")
        job = dataset.job_for(entry, plan, binding["executable_git_sha"])
        stored = dataset.read(directory / rel)
        dataset.check_seal(stored)
        expected = dataset.shard(stored["replay"], job, vocab)
        if stored != expected: raise ValueError("projection/label/hash mismatch")
        result[split].append((stored["observation"], stored["values"], root["source_seed"], root["root_id"]))
    if not result["TRAIN"] or not result["VALIDATION"]: raise ValueError("empty split")
    if {r[2] for r in result["TRAIN"]} & {r[2] for r in result["VALIDATION"]}:
        raise ValueError("source leakage across splits")
    return result, release, binding, selection


def load_validation_j(directory, release, binding, selection):
    """Authenticate manifests, then read only preselected VALIDATION J shards."""
    directory = Path(directory)
    release = dataset.read(directory / "release.json")
    binding = dataset.read(directory / "binding.json")
    selection = dataset.read(directory / "selection.json")
    dataset.check_seal(release)
    plan = dataset.read(directory / "plan.json")
    vocab = dataset.read(directory / "vocabulary.json")
    for item in (binding, selection, plan): dataset.check_seal(item)
    projection.validate_vocabulary(vocab)
    if release["sha256"] != RELEASE or not release["training_ready"]:
        raise ValueError("unexpected or unready release")
    if (binding["sha256"] != BINDING or selection["sha256"] != SELECTION or
        release["binding_sha256"] != binding["sha256"] or
        release["selection_sha256"] != selection["sha256"]):
        raise ValueError("frozen binding/selection mismatch")
    if (binding["plan_sha256"] != plan["sha256"] or
        selection["plan_sha256"] != plan["sha256"] or
        selection["executable_git_sha"] != binding["executable_git_sha"] or
        selection["pilot"] or plan["vocabulary_sha256"] != vocab["sha256"]):
        raise ValueError("release plan/selection/vocabulary mismatch")
    checksums = {f["path"]: f["sha256"] for f in release["files"]}
    quarantine = set(release["quarantined_roots"])
    resolution_hash = release.get("quarantine_resolution_sha256")
    if bool(quarantine) != bool(resolution_hash): raise ValueError("release quarantine resolution mismatch")
    if resolution_hash:
        resolution = dataset.read(directory / "resolutions" / f"{resolution_hash}.json")
        dataset.check_seal(resolution)
        if (resolution["schema"] != "silver_prior_quarantine_v1" or
            resolution["sha256"] != resolution_hash or
            resolution["binding_sha256"] != binding["sha256"] or
            resolution["selection_sha256"] != selection["sha256"] or
            set(resolution["quarantined_roots"]) != quarantine):
            raise ValueError("sealed quarantine resolution mismatch")
    all_selected = [e for e in selection["entries"] if e["split"] == "VALIDATION" and e["judge_selected"]]
    selected = [e for e in all_selected if e["root"]["root_id"] not in quarantine]
    expected_count = len(all_selected) - sum(e["root"]["root_id"] in quarantine for e in all_selected)
    if len(all_selected) != 64 or len(selected) != expected_count or len({e["root"]["source_seed"] for e in selected}) != len(selected):
        raise ValueError(f"expected 64 preselected validation J roots before quarantine, got {len(all_selected)}")
    out = []
    for entry in selected:
        root = entry["root"]
        rel = f"raw/J/{dataset.identity_hash(root)}.json.gz"
        expected_checksum = checksums.get(rel)
        if expected_checksum is None: raise ValueError(f"selected validation J raw record absent from release manifest: {rel}")
        if expected_checksum != dataset.file_hash(directory / rel): raise ValueError("J raw checksum mismatch")
        raw = dataset.read(directory / rel)
        job=dataset.job_for(entry,plan,binding["executable_git_sha"],role="J")
        dataset.validate_raw(raw,job)
        projected=dataset.shard(raw,job,vocab)
        out.append((projected["observation"], projected["values"], root["source_seed"], root["root_id"]))
    return out


def _numeric_fields(obs):
    g, p = obs["global"], obs["player"]
    vals = [float(0 if k=="encounter" else g[k]) for k in NUMERIC_GLOBAL] + [float(0 if k in ("stance","lastTargetedMonster","characterClass") else p[k]) for k in NUMERIC_PLAYER]
    vals += [float(obs["evaluation_context"][k]) for k in ("effectiveGold", "maxHp")]
    # Explicit pooled identity/count flags. No provenance, UID, RNG, or action rank.
    vals += [len(obs["cards"]), len(obs["monsters"]), len(obs["potions"]),
             len(obs["miscFlags"]), len(obs["extraRollMoveSlots"]), len(obs["skipMonsterTurnSlots"])]
    vals += [float(i in obs["miscFlags"]) for i in range(32)]
    vals += [float(i in obs["extraRollMoveSlots"]) for i in range(8)]
    vals += [float(i in obs["skipMonsterTurnSlots"]) for i in range(8)]
    vals += [float(obs["piles"][z]["fullOrderObserved"]) for z in ("drawPile","discardPile","exhaustPile")]
    vals += [sum(c["zone"]==z for c in obs["cards"]) for z in ("hand","limbo","stasisCards","drawPile","discardPile","exhaustPile")]
    vals += [sum(c["segment"]==s for c in obs["cards"]) for s in ("observed","knownBottom","unknown","knownTop")]
    vals += [float(x["amount"]) for x in p["bombs"]]
    vals += [float(i in p["orangePelletsCardTypesPlayed"]) for i in range(8)]
    for z in ("limbo","stasisCards"):
        refs=obs["zones"][z]
        vals += [float(ref is not None) for ref in refs]
    return vals


def _cat_ids(obs):
    p = obs["player"]
    cats = [int(obs["global"]["encounter"]), int(p["stance"])]
    cats.extend(map(int, p["statusPresence"]))
    cats.extend(map(int, p["justApplied"]))
    cats.extend(map(int, p["relicPresence"]))
    return cats


def _card_numeric(c):
    return [float(c["specialData"]), float(c["cost"]), float(c["costForTurn"]),
            float(c["position"] or 0), float(c["position"] is not None),
            float(c["upgraded"]), float(c["freeToPlayOnce"]), float(c["retain"])]


def field_consumption_table(obs):
    """Exhaustive leaf-path accounting for the frozen projection."""
    table={}
    relation={"cards[].ref","monsters[].ref","candidates[].card_ref","candidates[].target_ref",
              "candidates[].potion_slot","zones","schema"}
    redundant={"candidates[].potion_id"}
    def classify(path):
        top=path.split(".",1)[0].split("[",1)[0]
        if top not in PROJECTION_FIELD_CONSUMPTION: raise ValueError(f"unclassified projection root field: {path}")
        if top=="schema": return "REDUNDANT_BY_CONSTRUCTION"
        if path in redundant:return "REDUNDANT_BY_CONSTRUCTION"
        if path in relation or (path.startswith("zones.") and path not in ("zones.limbo[]","zones.stasisCards[]")) or (path.startswith("piles.") and path.endswith("[]")): return "RELATIONSHIP_ONLY"
        return PROJECTION_FIELD_CONSUMPTION[top]
    def walk(value,path):
        if isinstance(value,dict):
            for k,v in value.items(): walk(v,f"{path}.{k}" if path else k)
        elif isinstance(value,list):
            if value:
                for v in value: walk(v,path+"[]")
            else: table[path+"[]"]=classify(path+"[]")
        else:
            table[path]=classify(path)
    walk(obs,"")
    return table


def validate_feature_table(obs):
    table=field_consumption_table(obs)
    if set(table.values())-{"MODEL_INPUT","RELATIONSHIP_ONLY","REDUNDANT_BY_CONSTRUCTION"}:
        raise ValueError("unclassified projection field")
    return table


def assert_disjoint_sources(train_rows,validation_rows):
    train={r[2] for r in train_rows};validation={r[2] for r in validation_rows}
    overlap=train&validation
    if overlap: raise ValueError(f"TRAIN/VALIDATION sources overlap: {sorted(overlap)[:4]}")


def collate_rows(rows, device="cpu"):
    """Flatten ragged entities once per minibatch; no per-root model loop."""
    b=len(rows); card_rows=[]; mon_rows=[]; pot_rows=[]; cand_rows=[]
    card_lookup={}; mon_lookup={}; pot_lookup={};
    contexts=[]; status_rows=[]; just_rows=[]; relic_rows=[]; context_cats=[]
    qvalues=[]; seeds=[]; rootids=[]
    for ri,(obs,q,seed,rid) in enumerate(rows):
        validate_feature_table(obs)
        if not 0<=int(obs["global"]["encounter"])<1024 or not 0<=int(obs["player"]["stance"])<32 or not 0<=int(obs["player"]["characterClass"])<16: raise ValueError("unmapped context category")
        contexts.append(_numeric_fields(obs))
        p=obs["player"]
        context_cats.append([int(obs["global"]["encounter"]),int(p["stance"]),int(p["characterClass"]),int(p["lastTargetedMonster"] if p["lastTargetedMonster"] is not None else 7)])
        if any(not 0<=int(k)<96 for k in p["statusPresence"]) or any(not 0<=int(k)<32 for k in p["justApplied"]): raise ValueError("unmapped status identity")
        if any(not 0<=int(x["kind"])<96 for x in p["statusAmounts"]): raise ValueError("unmapped status amount identity")
        if any(not 0<=int(k)<128 for k in p["relicPresence"]): raise ValueError("unmapped relic identity")
        if any(not 0<=int(x["counter_kind"])<128 for x in p["relicCounters"]): raise ValueError("unmapped relic counter kind")
        for c in obs["cards"]:
            if not 0 <= int(c["card_id"]) < 158: raise ValueError(f"excluded or unmapped compact card id {c['card_id']}")
            card_lookup[(ri,c["ref"])]=len(card_rows)
            card_rows.append((ri,c))
        for m in obs["monsters"]:
            if m["present"]:
                if not 0<=int(m["id"])<2048 or any(not 0<=int(v)<512 for v in (m["moveHistory"] or [])) or any(not 0<=int(v)<64 for v in (m["powers"] or [])): raise ValueError("unmapped monster identity/move/power")
                mon_lookup[(ri,m["ref"])]=len(mon_rows); mon_rows.append((ri,m))
        for po in obs["potions"]:
            if not 0<=int(po["potion_id"])<256 or not 0<=int(po["slot"])<8: raise ValueError("unmapped potion identity/slot")
            pot_lookup[(ri,po["slot"])]=len(pot_rows); pot_rows.append((ri,po))
        for s in p["statusAmounts"]: status_rows.append((ri,int(s["kind"]),float(s["amount"]),0.0))
        for k in p["statusPresence"]:
            if all(int(x["kind"])!=int(k) for x in p["statusAmounts"]): status_rows.append((ri,int(k),0.0,1.0))
        just_rows.extend((ri,int(k),1.0) for k in p["justApplied"])
        for relic in p["relicPresence"]: relic_rows.append((ri,int(relic),0.0,1.0))
        for r in p["relicCounters"]: relic_rows.append((ri,int(r["counter_kind"]),float(r["amount"]),0.0))
        for a in obs["candidates"]:
            if not 0<=int(a["type"])<16 or not 0<=int(a["source_zone"])<16: raise ValueError("unmapped candidate category")
            cand_rows.append((ri,a,card_lookup.get((ri,a["card_ref"]),-1) if a["card_ref"] is not None else -1,
                              mon_lookup.get((ri,a["target_ref"]),-1) if a["target_ref"] is not None else -1,
                              pot_lookup.get((ri,a["potion_slot"]),-1) if a["potion_slot"] is not None else -1))
        qvalues.append(q); seeds.append(seed); rootids.append(rid)
    def tensor(x,dtype=torch.float32): return torch.as_tensor(x,dtype=dtype,device=device)
    card_num=[]; card_id=[]; card_zone=[]; card_segment=[]; card_root=[]
    zone_names=("hand","limbo","stasisCards","drawPile","discardPile","exhaustPile")
    for ri,c in card_rows:
        card_root.append(ri); card_id.append(c["card_id"]); card_zone.append(zone_names.index(c["zone"]))
        card_segment.append({"observed":1,"knownBottom":2,"unknown":3,"knownTop":4}.get(c["segment"],0)); card_num.append(_card_numeric(c))
    mon_id=[]; mon_slot=[]; mon_root=[]; mon_num=[]; mon_move=[]; mon_powers=[]; mon_small=[]
    for ri,m in mon_rows:
        mon_id.append(m["id"]); mon_slot.append(m["ref"]); mon_root.append(ri)
        vals=[m[k] for k in ("curHp","maxHp","block","strength","vulnerable","weak","uniquePower0","uniquePower1","miscInfo")]
        vals += [int(m[k]) for k in ("isEscapingB","halfDead","escapeNext","alive")]
        mon_num.append(vals); mon_move.append([int(v) for v in (m["moveHistory"] or [])]); mon_powers.append([int(v) for v in m["powers"] or []]); mon_small.append([float(x["amount"]) for x in m["smallPowers"]])
    move_owner=[i for i,row in enumerate(mon_move) for _ in row];move_ids=[v for row in mon_move for v in row];move_pos=[j for row in mon_move for j,_ in enumerate(row)]
    power_owner=[i for i,row in enumerate(mon_powers) for _ in row];power_ids=[v for row in mon_powers for v in row]
    pot_id=[]; pot_slot=[]; pot_root=[]; pot_flags=[]
    for ri,p in pot_rows: pot_id.append(p["potion_id"]);pot_slot.append(p["slot"]);pot_root.append(ri);pot_flags.append([p["available"],p["empty"]])
    cand_root=[]; cand_card=[]; cand_mon=[]; cand_pot=[]; cand_features=[]; targets=[]
    for ri,a,ci,mi,pi in cand_rows:
        cand_root.append(ri); cand_card.append(ci); cand_mon.append(mi); cand_pot.append(pi)
        cand_features.append([a["type"],a["source_zone"],a["discardPotion"],a["skipCardSelect"],a["cardSelectTask"],a["potion_slot"] is not None])
    arr={"batch_size":b,"contexts":tensor(contexts),"card_root":tensor(card_root,torch.long),"card_id":tensor(card_id,torch.long),"card_zone":tensor(card_zone,torch.long),"card_segment":tensor(card_segment,torch.long),"card_num":tensor(card_num),
         "mon_root":tensor(mon_root,torch.long),"mon_id":tensor(mon_id,torch.long),"mon_slot":tensor(mon_slot,torch.long),"mon_num":tensor(mon_num),"move_owner":tensor(move_owner,torch.long),"move_ids":tensor(move_ids,torch.long),"move_pos":tensor(move_pos,torch.long),"power_owner":tensor(power_owner,torch.long),"power_ids":tensor(power_ids,torch.long),"mon_small":tensor(mon_small),
         "pot_root":tensor(pot_root,torch.long),"pot_id":tensor(pot_id,torch.long),"pot_slot":tensor(pot_slot,torch.long),"pot_flags":tensor(pot_flags),
         "status_rows":tensor(status_rows).reshape(-1,4),"just_rows":tensor(just_rows).reshape(-1,3),"relic_rows":tensor(relic_rows).reshape(-1,4),"context_cats":tensor(context_cats,torch.long),"candidate_root":tensor(cand_root,torch.long),"candidate_card":tensor(cand_card,torch.long),"candidate_mon":tensor(cand_mon,torch.long),"candidate_pot":tensor(cand_pot,torch.long),"candidate_features":tensor(cand_features).reshape(-1,6),"labels":tensor([v for q in qvalues for v in q]),"source_seed":seeds,"root_id":rootids,"root_values":qvalues,"candidate_lengths":[len(v) for v in qvalues]}
    return arr


ROOT_OWNER_KEYS=("card_root","mon_root","pot_root","candidate_root")
ENTITY_KEYS={"card":("card_root",("card_id","card_zone","card_segment","card_num")),
             "mon":("mon_root",("mon_id","mon_slot","mon_num","mon_small")),
             "pot":("pot_root",("pot_id","pot_slot","pot_flags"))}


def select_prepared(full, root_indices):
    """Tensor-only ragged minibatch gather from the immutable prepared cache."""
    root_indices=torch.as_tensor(root_indices,dtype=torch.long).sort().values
    device=full["contexts"].device;total=len(full["contexts"]);batch=len(root_indices)
    root_map=torch.full((total,),-1,dtype=torch.long,device=device);root_map[root_indices.to(device)]=torch.arange(batch,device=device)
    out={"batch_size":batch,"root_indices":root_indices.to(device),"contexts":full["contexts"][root_indices.to(device)],
         "context_cats":full["context_cats"][root_indices.to(device)],
         "source_seed":[full["source_seed"][int(i)] for i in root_indices],
         "root_id":[full["root_id"][int(i)] for i in root_indices],
         "root_values":[full["root_values"][int(i)] for i in root_indices]}
    entity_maps={}
    for name,(owner_key,keys) in ENTITY_KEYS.items():
        owner=full[owner_key];mask=root_map[owner]>=0;old=torch.nonzero(mask).flatten();emap=torch.full((len(owner),),-1,dtype=torch.long,device=device);emap[old]=torch.arange(len(old),device=device);entity_maps[name]=emap
        out[owner_key]=root_map[owner[mask]]
        for key in keys:out[key]=full[key][mask]
    # Monster move/power token ownership refers to flattened monster indices.
    for pre,owner_key,ids_key in (("move","move_owner","move_ids"),("power","power_owner","power_ids")):
        oldowner=full[owner_key];mask=entity_maps["mon"][oldowner]>=0
        out[owner_key]=entity_maps["mon"][oldowner[mask]];out[ids_key]=full[ids_key][mask]
        if pre=="move":out["move_pos"]=full["move_pos"][mask]
    for key in ("status_rows","just_rows","relic_rows"):
        r=full[key];mask=root_map[r[:,0].long()]>=0;out[key]=r[mask].clone();out[key][:,0]=root_map[r[mask,0].long()].to(out[key].dtype)
    # Candidates are filtered after their referenced entities are remapped.
    oldroot=full["candidate_root"];mask=root_map[oldroot]>=0
    out["candidate_root"]=root_map[oldroot[mask]]
    for name,key in (("card","candidate_card"),("mon","candidate_mon"),("pot","candidate_pot")):
        refs=full[key][mask];mapped=torch.full_like(refs,-1);valid=refs>=0
        if valid.any():mapped[valid]=entity_maps[name][refs[valid]]
        out[key]=mapped
    out["candidate_features"]=full["candidate_features"][mask]
    out["labels"]=full["labels"][mask]
    out["candidate_lengths"]=torch.bincount(out["candidate_root"],minlength=batch)
    return out


class SilverPriorNetV1(nn.Module):
    """Ragged DeepSets model; the forward pass never iterates over roots."""
    def __init__(self, context_dim):
        super().__init__()
        self.card=nn.Embedding(158,32);self.zone=nn.Embedding(8,8);self.segment=nn.Embedding(8,8)
        self.card_mlp=nn.Sequential(nn.Linear(56,64),nn.GELU(),nn.Linear(64,64),nn.GELU())
        self.monster=nn.Embedding(2048,16);self.slot=nn.Embedding(8,8);self.move=nn.Embedding(512,8);self.move_step=nn.Embedding(8,8);self.power=nn.Embedding(64,8);self.small_kind=nn.Embedding(11,8)
        self.mon_mlp=nn.Sequential(nn.Linear(16+8+13+8+8+8,64),nn.GELU(),nn.Linear(64,64),nn.GELU())
        self.potion=nn.Embedding(256,16);self.potion_slot=nn.Embedding(8,4);self.pot_mlp=nn.Sequential(nn.Linear(22,24),nn.GELU())
        self.status_kind=nn.Embedding(96,16);self.just_kind=nn.Embedding(32,16);self.relic_kind=nn.Embedding(128,16)
        self.encounter=nn.Embedding(1024,16);self.stance=nn.Embedding(32,8);self.character=nn.Embedding(16,8);self.last_target=nn.Embedding(8,8)
        self.context_mlp=nn.Sequential(nn.Linear(context_dim+32+40,128),nn.GELU(),nn.Linear(128,96),nn.GELU())
        self.state_mlp=nn.Sequential(nn.Linear(96+64+64+24,128),nn.GELU(),nn.Linear(128,96),nn.GELU())
        self.action_type=nn.Embedding(16,16);self.action_zone=nn.Embedding(16,8)
        self.null_card=nn.Parameter(torch.zeros(64));self.null_monster=nn.Parameter(torch.zeros(64));self.null_potion=nn.Parameter(torch.zeros(24))
        self.action_mlp=nn.Sequential(nn.Linear(16+8+64+64+24+4,128),nn.GELU(),nn.Linear(128,96),nn.GELU())
        self.scorer=nn.Sequential(nn.Linear(288,96),nn.GELU(),nn.Linear(96,1))
        self.normalization=None

    @staticmethod
    def _pool(values, owner, count, dim):
        out=values.new_zeros((count,dim)); sizes=values.new_zeros((count,1))
        if len(owner): out.index_add_(0,owner,values);sizes.index_add_(0,owner,values.new_ones((len(owner),1)))
        return out/sizes.clamp_min(1).sqrt()

    def forward(self,x):
        n=x["batch_size"]; device=x["contexts"].device; norm=self.normalization
        def normal(key,v):
            if norm is None:return v
            mean,std=norm[key+"_mean"],norm[key+"_std"];return (v-mean.to(device))/std.to(device)
        card_num=normal("card",x["card_num"])
        ce=self.card_mlp(torch.cat([self.card(x["card_id"]),self.zone(x["card_zone"]),self.segment(x["card_segment"]),card_num],-1))
        card_state=self._pool(ce,x["card_root"],n,64)
        if len(x["mon_id"]):
            move_sum=ce.new_zeros((len(x["mon_id"]),8));move_counts=ce.new_zeros((len(x["mon_id"]),1))
            if len(x["move_ids"]):
                move_values=self.move(x["move_ids"])+self.move_step(x["move_pos"])
                move_sum.index_add_(0,x["move_owner"],move_values);move_counts.index_add_(0,x["move_owner"],ce.new_ones((len(x["move_owner"]),1)))
            move_sum/=move_counts.clamp_min(1).sqrt()
            pow_sum=ce.new_zeros((len(x["mon_id"]),8));power_counts=ce.new_zeros((len(x["mon_id"]),1))
            if len(x["power_ids"]):
                pow_sum.index_add_(0,x["power_owner"],self.power(x["power_ids"]));power_counts.index_add_(0,x["power_owner"],ce.new_ones((len(x["power_owner"]),1)))
            pow_sum/=power_counts.clamp_min(1).sqrt()
            small_ids=torch.arange(11,device=device).expand(len(x["mon_id"]),-1)
            small=self.small_kind(small_ids)*normal("small",x["mon_small"]).unsqueeze(-1)
            small_pool=small.sum(1)/11**.5
            men=torch.cat([self.monster(x["mon_id"]),self.slot(x["mon_slot"]),normal("monster",x["mon_num"]),move_sum,pow_sum,small_pool],-1)
            me=self.mon_mlp(men)
        else: me=ce.new_zeros((0,64))
        monster_state=self._pool(me,x["mon_root"],n,64)
        pe=self.pot_mlp(torch.cat([self.potion(x["pot_id"]),self.potion_slot(x["pot_slot"]),x["pot_flags"]],-1))
        potion_state=self._pool(pe,x["pot_root"],n,24)
        status_pool=ce.new_zeros((n,16)); relic_pool=ce.new_zeros((n,16))
        if len(x["status_rows"]):
            r=x["status_rows"];o=r[:,0].long();k=r[:,1].long();raw=r[:,2:3];presence=r[:,3:4]
            a=torch.where(presence.bool(),torch.ones_like(raw),(raw-norm["status_mean"].to(device))/norm["status_std"].to(device)) if norm else torch.where(presence.bool(),torch.ones_like(raw),raw)
            status_pool.index_add_(0,o,self.status_kind(k)*a)
        if len(x["just_rows"]):
            r=x["just_rows"];o=r[:,0].long();k=r[:,1].long();a=r[:,2:3]
            status_pool.index_add_(0,o,self.just_kind(k)*a)
        if len(x["relic_rows"]):
            r=x["relic_rows"];o=r[:,0].long();k=r[:,1].long();raw=r[:,2:3];presence=r[:,3:4]
            a=torch.where(presence.bool(),torch.ones_like(raw),(raw-norm["relic_mean"].to(device))/norm["relic_std"].to(device)) if norm else torch.where(presence.bool(),torch.ones_like(raw),raw)
            relic_pool.index_add_(0,o,self.relic_kind(k)*a)
        cc=x["context_cats"]
        categorical=torch.cat([self.encounter(cc[:,0]),self.stance(cc[:,1]),self.character(cc[:,2]),self.last_target(cc[:,3])],-1)
        context=self.context_mlp(torch.cat([normal("context",x["contexts"]),status_pool,relic_pool,categorical],-1))
        state=self.state_mlp(torch.cat([context,card_state,monster_state,potion_state],-1))
        ca=x["candidate_features"].long();flags=x["candidate_features"][:,2:].float()
        card_bank=torch.cat([self.null_card[None],ce],0);mon_bank=torch.cat([self.null_monster[None],me],0);pot_bank=torch.cat([self.null_potion[None],pe],0)
        cr=x["candidate_card"]+1;mr=x["candidate_mon"]+1;pr=x["candidate_pot"]+1
        ac=self.action_mlp(torch.cat([self.action_type(ca[:,0]),self.action_zone(ca[:,1]),card_bank[cr],mon_bank[mr],pot_bank[pr],flags],-1))
        sr=state[x["candidate_root"]]
        return self.scorer(torch.cat([sr,ac,sr*ac],-1)).squeeze(-1)


def ragged_targets(values, temperatures, device="cpu"):
    qs=[torch.as_tensor(q,dtype=torch.float32) for q in values]
    q=torch.cat(qs).to(device); owner=torch.repeat_interleave(torch.arange(len(qs),device=device),torch.tensor([len(v) for v in qs],device=device))
    maximum=torch.full((len(qs),),-torch.inf,device=device).scatter_reduce_(0,owner,q,reduce="amax",include_self=True)
    exp=((q-maximum[owner])/temperatures).exp();den=q.new_zeros(len(qs)).index_add_(0,owner,exp)
    return (exp/den[owner]),owner,torch.tensor([len(v) for v in values],device=device)


def ragged_targets_flat(values,owner,root_count,tau):
    values=values.to(owner.device);maxima=torch.full((root_count,),-torch.inf,device=owner.device).scatter_reduce_(0,owner,values,reduce="amax",include_self=True)
    exp=((values-maxima[owner])/tau).exp();den=values.new_zeros(root_count).index_add_(0,owner,exp)
    return exp/den[owner]


def ragged_root_ce(logits, target, owner, lengths):
    maxima=torch.full((len(lengths),),-torch.inf,device=logits.device).scatter_reduce_(0,owner,logits,reduce="amax",include_self=True)
    exp=(logits-maxima[owner]).exp(); sums=logits.new_zeros(len(lengths)).index_add_(0,owner,exp)
    logp=logits-maxima[owner]-sums[owner].log(); root_loss=logits.new_zeros(len(lengths)).index_add_(0,owner,-target*logp)
    return root_loss.mean()


def bootstrap_summary(values, seeds, n_boot=5000, seed=20260922):
    values=np.asarray(values,dtype=np.float64);seeds=np.asarray(seeds);unique=np.unique(seeds)
    mask=np.isfinite(values);values=values[mask];seeds=seeds[mask];unique=np.unique(seeds)
    if len(values)==0:
        return {"mean":None,"median":None,"ci95":None,"bootstrap_replicates":n_boot,"cluster":"source_seed","sources":0,"roots":0}
    grouped=[values[seeds==s] for s in unique]
    rng=np.random.default_rng(seed);draws=rng.integers(0,len(unique),size=(n_boot,len(unique)))
    boot=np.asarray([np.concatenate([grouped[i] for i in draw]).mean() for draw in draws])
    return {"mean":float(values.mean()),"median":float(np.median(values)),"ci95":[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],"bootstrap_replicates":n_boot,"cluster":"source_seed","sources":len(unique),"roots":len(values)}


def root_metrics(logits,q,tau):
    logits=np.asarray(logits,dtype=np.float64);q=np.asarray(q,dtype=np.float64)
    z=logits-logits.max();p=np.exp(z);p/=p.sum();y=np.exp((q-q.max())/tau);y/=y.sum()
    qbest=float(q.max());qsecond=float(np.sort(q)[-2]);arg=int(np.argmax(logits));qarg=int(np.argmax(q))
    concord=pairwise_concordance(logits,q)
    ce=float(-(y*np.log(np.maximum(p,1e-300))).sum());kl=float((y*(np.log(np.maximum(y,1e-300))-np.log(np.maximum(p,1e-300)))).sum())
    return {"ce":ce,"kl":kl,"concordance":concord,"top_agreement":float(arg==qarg),"argmax_regret":qbest-float(q[arg]),"expected_regret":qbest-float(np.dot(p,q)),"uniform_regret":qbest-float(q.mean()),"entropy":float(-(p*np.log(np.maximum(p,1e-300))).sum()),"top_probability":float(p.max())}


def pairwise_concordance(logits, q):
    logits=np.asarray(logits,dtype=np.float64);q=np.asarray(q,dtype=np.float64)
    pairs=[(i,j) for i in range(len(q)) for j in range(i+1,len(q)) if q[i]!=q[j]]
    return sum((logits[i]-logits[j])*(q[i]-q[j])>0 for i,j in pairs)/len(pairs) if pairs else None


def predict_prepared(model,full,device,batch_size=128):
    model.eval();out=[]
    with torch.no_grad():
        for start in range(0,len(full["contexts"]),batch_size):
            indices=np.arange(start,min(start+batch_size,len(full["contexts"])))
            x=device_batch(select_prepared(full,indices),device);logits=model(x).detach().cpu().numpy();at=0
            for local,global_i in enumerate(indices):
                k=int(x["candidate_lengths"][local]);z=logits[at:at+k];p=np.exp(z-z.max());p/=p.sum()
                out.append({"q":full["root_values"][int(global_i)],"source_seed":full["source_seed"][int(global_i)],"root_id":full["root_id"][int(global_i)],"logits":z.tolist(),"probabilities":p.tolist()});at+=k
    return out


def write_validation_metrics(cache,artifact_dir,device="cpu"):
    rows=cache["prepared"]["VALIDATION"];result={}
    for arm in ("T0.5","T1","T2"):
        path=artifact_dir/f"{arm}.pt"
        cp=torch.load(path,map_location=device,weights_only=False);model=SilverPriorNetV1(rows["contexts"].shape[1]).to(device)
        model.load_state_dict(cp["state_dict"]);model.normalization=cp["normalization"]
        pred=predict_prepared(model,rows,device);tau=cp["tau"];metrics=[root_metrics(r["logits"],r["q"],tau) for r in pred]
        names=metrics[0].keys();summaries={k:bootstrap_summary([np.nan if m[k] is None else m[k] for m in metrics],[r["source_seed"] for r in pred]) for k in names}
        diffs=[m["expected_regret"]-m["uniform_regret"] for m in metrics]
        summaries["expected_regret_minus_uniform"]=bootstrap_summary(diffs,[r["source_seed"] for r in pred])
        result[arm]={"tau":tau,"metrics":summaries,"per_root": [{k:v for k,v in m.items()}|{"root_id":r["root_id"],"source_seed":r["source_seed"]} for m,r in zip(metrics,pred)]}
    (artifact_dir/"validation-metrics.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def evaluate_validation_j(corpus,cache,artifact_dir,device="cpu"):
    release=dataset.read(Path(corpus)/"release.json");binding=dataset.read(Path(corpus)/"binding.json");selection=dataset.read(Path(corpus)/"selection.json")
    jrows=collate_rows(load_validation_j(corpus,release,binding,selection));result={}
    for arm in ("T0.5","T1","T2"):
        cp=torch.load(artifact_dir/f"{arm}.pt",map_location=device,weights_only=False);model=SilverPriorNetV1(jrows["contexts"].shape[1]).to(device)
        model.load_state_dict(cp["state_dict"]);model.normalization=cp["normalization"];pred=predict_prepared(model,jrows,device);tau=cp["tau"]
        per=[]
        for r in pred:
            qj=np.asarray(r["q"],dtype=np.float64);p=np.asarray(r["probabilities"]);ql=np.asarray(cache["by_root"][r["root_id"]]["q"],dtype=np.float64);yl=np.exp((ql-ql.max())/tau);yl/=yl.sum()
            jbest=qj.max();lbest=qj[int(np.argmax(ql))];modelbest=qj[int(np.argmax(p))]
            concord=pairwise_concordance(r["logits"],qj)
            per.append({"root_id":r["root_id"],"source_seed":r["source_seed"],"model_expected_regret":float(jbest-p@qj),"uniform_expected_regret":float(jbest-qj.mean()),"l_target_expected_regret":float(jbest-yl@qj),"model_argmax_regret":float(jbest-modelbest),"l_argmax_regret":float(jbest-lbest),"pairwise_concordance":None if concord is None else float(concord)})
        metrics={}
        for name in per[0]:
            if name in ("root_id","source_seed"):continue
            metrics[name]=bootstrap_summary([r[name] for r in per],[r["source_seed"] for r in per])
        for name in metrics:
            if name=="pairwise_concordance":metrics[name]=bootstrap_summary([np.nan if r[name] is None else r[name] for r in per],[r["source_seed"] for r in per])
        diff=[r["model_expected_regret"]-r["uniform_expected_regret"] for r in per]
        metrics["model_minus_uniform"]=bootstrap_summary(diff,[r["source_seed"] for r in per])
        uniform_gain=float(np.mean([r["uniform_expected_regret"]-r["model_expected_regret"] for r in per]))
        teacher_headroom=float(np.mean([r["uniform_expected_regret"]-r["l_target_expected_regret"] for r in per]))
        result[arm]={"tau":tau,"metrics":metrics,"teacher_headroom":teacher_headroom,"model_improvement_over_uniform":uniform_gain,"soft_prior_headroom_recovery":uniform_gain/teacher_headroom if teacher_headroom>0 else None,"per_root":per}
    (artifact_dir/"validation-j-metrics.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def select_temperature(validation_l,validation_j,artifact_dir):
    eligible=[];detail={}
    for arm in ("T0.5","T1","T2"):
        lj=validation_l[arm]["metrics"]["expected_regret_minus_uniform"]["ci95"][1]
        jj=validation_j[arm]["metrics"]["model_minus_uniform"]["ci95"][1]
        jm=validation_j[arm]["metrics"]["model_minus_uniform"]["mean"]
        okay=(jm<0 and jj<0 and lj<0)
        detail[arm]={"eligible":okay,"validation_l_upper_ci":lj,"validation_j_upper_ci":jj,"validation_j_model_minus_uniform":jm}
        if okay:eligible.append(arm)
    # The teacher-headroom contrast is the L-target policy's J regret minus uniform.
    head={}
    for arm in ("T0.5","T1","T2"):
        roots=validation_j[arm]["per_root"]
        head[arm]=bootstrap_summary([r["l_target_expected_regret"]-r["uniform_expected_regret"] for r in roots],[r["source_seed"] for r in roots])
    if not eligible:
        result={"classification":"PRIOR_MODEL_VALIDATION_NOT_CONFIRMED","selected_temperature":None,"arms":detail,"validation_j_teacher_minus_uniform":head,"reason":"No arm passed both source-bootstrap upper-CI eligibility gates."}
    else:
        best=min(eligible,key=lambda a:validation_j[a]["metrics"]["model_minus_uniform"]["mean"])
        indist=[best]
        best_by={r["root_id"]:r["model_expected_regret"] for r in validation_j[best]["per_root"]}
        best_rows={r["root_id"]:r for r in validation_j[best]["per_root"]}
        for arm in eligible:
            if arm==best:continue
            other={r["root_id"]:r for r in validation_j[arm]["per_root"]}
            diff=[other[rid]["model_expected_regret"]-best_by[rid] for rid in best_by]
            src=[best_rows[rid]["source_seed"] for rid in best_by]
            ci=bootstrap_summary(diff,src)["ci95"];detail[arm]["paired_delta_vs_best_ci"]=ci
            if ci[0]<=0<=ci[1]:indist.append(arm)
        selected=max(indist,key=lambda a:validation_j[a]["tau"])
        result={"classification":"PRIOR_MODEL_VALIDATION_CONFIRMED","selected_temperature":selected,"arms":detail,"validation_j_teacher_minus_uniform":head,"tie_rule":"highest temperature among eligible arms whose paired source-bootstrap contrast with the best includes zero"}
    (artifact_dir/"temperature-comparison.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def fit_normalization(train_rows):
    """TRAIN-only population moments for continuous context/card/monster inputs."""
    context=np.asarray([_numeric_fields(o) for o,_,_,_ in train_rows],dtype=np.float64)
    cards=np.asarray([_card_numeric(c) for o,_,_,_ in train_rows for c in o["cards"]] or [[0.0]*8],dtype=np.float64)
    mons=[]; small=[]; status_amounts=[]; relic_amounts=[]
    for o,_,_,_ in train_rows:
        for m in o["monsters"]:
            if not m["present"]: continue
            x=[m[k] for k in ("curHp","maxHp","block","strength","vulnerable","weak","uniquePower0","uniquePower1","miscInfo")]
            x += [int(m[k]) for k in ("isEscapingB","halfDead","escapeNext","alive")]; mons.append(x)
            small.append([float(v["amount"]) for v in m["smallPowers"]])
        p=o["player"];status_amounts.extend(float(x["amount"]) for x in p["statusAmounts"])
        relic_amounts.extend(float(x["amount"]) for x in p["relicCounters"])
    def stats(a, no_scale=()):
        a=np.asarray(a,dtype=np.float64); mean=a.mean(0); std=a.std(0); std[std<1e-6]=1.0
        for i in no_scale: mean[i]=0.0;std[i]=1.0
        return torch.tensor(mean,dtype=torch.float32),torch.tensor(std,dtype=torch.float32)
    # Preserve categorical IDs and booleans as unscaled values.
    no_scale=[]; offs=0
    for k in NUMERIC_GLOBAL:
        if k in ("encounter","inputState","outcome","omamoriOwned","endTurnQueued","turnHasEnded","skipMonsterTurn","fullDrawOrderObserved","intentsHidden"): no_scale.append(offs)
        offs+=1
    for k in NUMERIC_PLAYER:
        if k in ("characterClass","stance","haveUsedNecronomiconThisTurn"): no_scale.append(offs)
        offs+=1
    no_scale += list(range(offs+2+6,offs+2+6+32+8+8+3))
    no_scale += list(range(offs+2+6+51+10+3,offs+2+6+51+10+3+8))
    no_scale += list(range(len(context[0])-12,len(context[0])))
    cm,cs=stats(context,no_scale); am,ass=stats(cards,[5,6,7]); mm,ms=stats(mons or [[0.0]*13],[9,10,11,12])
    sm,ss=stats(small or [[0.0]*11]); stm,sts=stats([[v] for v in (status_amounts or [0.0])]); rm,rs=stats([[v] for v in (relic_amounts or [0.0])])
    return {"context_mean":cm,"context_std":cs,"card_mean":am,"card_std":ass,"monster_mean":mm,"monster_std":ms,"small_mean":sm,"small_std":ss,"status_mean":stm,"status_std":sts,"relic_mean":rm,"relic_std":rs}


def grouped_softmax(logits, lengths):
    chunks=logits.split(lengths); return torch.cat([torch.softmax(c,0) for c in chunks])


def root_target(q,tau):
    x=torch.tensor(q,dtype=torch.float32); return torch.softmax((x-x.max())/tau,0)


def root_ce(logits,target): return -(target*torch.log_softmax(logits,0)).sum()


def _update_content_hash(h, value):
    if torch.is_tensor(value):
        tensor=value.detach().cpu().contiguous()
        h.update(b"tensor\0"+str(tensor.dtype).encode()+b"\0"+json.dumps(list(tensor.shape)).encode()+b"\0")
        h.update(tensor.numpy().tobytes())
    elif isinstance(value, dict):
        h.update(b"dict\0")
        for key in sorted(value):
            _update_content_hash(h,key);_update_content_hash(h,value[key])
    elif isinstance(value,(list,tuple)):
        h.update((b"list\0" if isinstance(value,list) else b"tuple\0")+str(len(value)).encode()+b"\0")
        for item in value:_update_content_hash(h,item)
    elif isinstance(value,(str,int,float,bool)) or value is None:
        h.update(type(value).__name__.encode()+b"\0"+json.dumps(value,sort_keys=True,allow_nan=False).encode()+b"\0")
    else:
        raise TypeError(f"unsupported cache content type: {type(value).__name__}")


def cache_content_sha256(cached):
    h=hashlib.sha256()
    for key in ("metadata","prepared","normalization"):_update_content_hash(h,cached[key])
    return h.hexdigest()


def cache_payload(corpus, cache_path):
    if cache_path.exists():
        with cache_path.open("rb") as f: cached=pickle.load(f)
        expected={"schema":PREPROCESS_SCHEMA,"trainer_sha256":sha256(Path(__file__)),"release_sha256":RELEASE,"binding_sha256":BINDING,"selection_sha256":SELECTION,"vocabulary_sha256":dataset.read(Path(corpus)/"vocabulary.json")["sha256"]}
        if cached.get("metadata")!=expected: raise ValueError("preprocessed cache provenance/schema mismatch; prepare a fresh cache path")
        if cached.get("content_sha256") != cache_content_sha256(cached): raise ValueError("preprocessed cache content integrity failure")
        return cached
    splits,release,binding,selection=load_train_and_validation(corpus)
    metadata={"schema":PREPROCESS_SCHEMA,"trainer_sha256":sha256(Path(__file__)),"release_sha256":release["sha256"],"binding_sha256":binding["sha256"],"selection_sha256":selection["sha256"],"vocabulary_sha256":dataset.read(Path(corpus)/"vocabulary.json")["sha256"]}
    prepared={split:collate_rows(rows) for split,rows in splits.items()}
    normalization=fit_normalization(splits["TRAIN"])
    result={"metadata":metadata,"prepared":prepared,"normalization":normalization}
    result["content_sha256"]=cache_content_sha256(result)
    cache_path.parent.mkdir(parents=True,exist_ok=True)
    with cache_path.open("wb") as f: pickle.dump(result,f,protocol=5)
    return result


def device_batch(batch, device):
    for k,v in list(batch.items()):
        if torch.is_tensor(v): batch[k]=v.to(device)
    return batch


def make_epoch_orders(prepared, rng, epochs=80):
    """Generate one permutation of every prepared root for each epoch."""
    root_count=len(prepared["contexts"])
    if root_count<=0: raise ValueError("empty TRAIN roots")
    orders=[rng.permutation(root_count) for _ in range(epochs)]
    for order in orders: assert_epoch_accounting(order,prepared,optimizer_steps=(root_count+127)//128,batch_size=128)
    return orders


def assert_epoch_accounting(root_indices, prepared, optimizer_steps, batch_size=128, action_count=None):
    root_count=len(prepared["contexts"]);expected_actions=len(prepared["labels"])
    indices=np.asarray(root_indices,dtype=np.int64)
    if (len(indices)!=root_count or not np.array_equal(np.sort(indices),np.arange(root_count))):
        raise ValueError("training epoch did not visit every TRAIN root exactly once")
    if action_count is not None and int(action_count)!=expected_actions:
        raise ValueError(f"training epoch action count mismatch: {action_count} != {expected_actions}")
    expected_steps=(root_count+batch_size-1)//batch_size
    if int(optimizer_steps)!=expected_steps:
        raise ValueError(f"training epoch optimizer-step count mismatch: {optimizer_steps} != {expected_steps}")
    return {"train_roots_per_epoch":root_count,"train_actions":expected_actions,"optimizer_steps":expected_steps}


def train_stage_a(corpus,cache_path,artifact_dir,seed=SEED,device="auto",probe_only=False):
    cache=cache_payload(corpus,cache_path); splits=cache["prepared"];train=splits["TRAIN"];val=splits["VALIDATION"]
    cache["by_root"]={rid:{"q":q,"source_seed":seed} for rid,q,seed in zip(val["root_id"],val["root_values"],val["source_seed"])}
    if set(train["source_seed"]) & set(val["source_seed"]): raise ValueError("TRAIN/VALIDATION source overlap")
    normalization=cache["normalization"]
    gaps=sorted(max(q)-sorted(q)[-2] for q in train["root_values"] if len(q)>1 and max(q)-sorted(q)[-2]>1e-6)
    if len(gaps)<100: raise ValueError("insufficient positive TRAIN top-two gaps")
    tau0=float(np.median(gaps));temps={"T0.5":tau0*.5,"T1":tau0,"T2":tau0*2}
    torch.manual_seed(seed);np.random.seed(seed);random.seed(seed);torch.use_deterministic_algorithms(True)
    dev="cuda" if device=="auto" and torch.cuda.is_available() else ("cpu" if device=="auto" else device)
    model=SilverPriorNetV1(train["contexts"].shape[1]).to(dev);model.normalization=normalization
    params=sum(p.numel() for p in model.parameters())
    artifact_dir.mkdir(parents=True,exist_ok=True)
    np.savez(artifact_dir/"normalization.npz",**{k:v.numpy() for k,v in normalization.items()})
    train_roots=len(train["contexts"]);train_actions=len(train["labels"]);steps_per_epoch=(train_roots+127)//128
    cfg={"seed":seed,"tau0":tau0,"temperatures":temps,"recipe":{"optimizer":"AdamW","lr":3e-4,"weight_decay":1e-4,"root_batch":128,"clip":1.0,"max_epochs":80,"patience":8,"precision":"FP32"},"train_roots_per_epoch":train_roots,"train_actions":train_actions,"optimizer_steps_per_epoch":steps_per_epoch,"release_sha256":cache["metadata"]["release_sha256"],"binding_sha256":cache["metadata"]["binding_sha256"],"selection_sha256":cache["metadata"]["selection_sha256"],"vocabulary_sha256":cache["metadata"]["vocabulary_sha256"],"trainer_sha256":cache["metadata"]["trainer_sha256"],"normalization_sha256":sha256(artifact_dir/"normalization.npz"),"parameter_count":params,"architecture":"SilverPriorNetV1","device":dev,"locked_test_labels_opened":False,"metadata_deviation":"LOCKED_TEST root/action counts observed before freeze; labels untouched"}
    (artifact_dir/"config.json").write_text(json.dumps(cfg,indent=2)+"\n")
    rng=np.random.default_rng(seed);orders=make_epoch_orders(train,rng,80)
    probe={"started":time.monotonic(),"roots":0,"actions":0}
    def iterate(rows,ids):
        for st in range(0,len(ids),128):
            ix=ids[st:st+128];x=device_batch(select_prepared(rows,ix),dev)
            probe["roots"]+=len(ix);probe["actions"]+=len(x["labels"])
            yield x
    if probe_only:
        opt=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-4);model.train();opt.zero_grad()
        for x in iterate(train,np.arange(len(train["contexts"]))):
            owner=x["candidate_root"];q=ragged_targets_flat(x["labels"],owner,x["batch_size"],tau0);lengths=x["candidate_lengths"]
            loss=ragged_root_ce(model(x),q,owner,lengths);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step();opt.zero_grad()
        elapsed=time.monotonic()-probe["started"]
        out={"roots":len(train["contexts"]),"actions":len(train["labels"]),"wall_seconds":elapsed,"roots_per_second":len(train["contexts"])/elapsed,"actions_per_second":len(train["labels"])/elapsed,"max_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"device":dev,"temperature":"T1","temperature_value":tau0,"epoch_count":1}
        (artifact_dir/"throughput-probe.json").write_text(json.dumps(out,indent=2)+"\n");print(json.dumps(out,indent=2));return out
    initial={k:v.detach().cpu().clone() for k,v in model.state_dict().items()};summaries={}
    for arm,tau in temps.items():
        model.load_state_dict(initial);opt=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-4);best=float("inf");patience=0;hist=[];accounting=[]
        for epoch,order in enumerate(orders,1):
            model.train()
            seen_roots=[];seen_actions=0;optimizer_steps=0
            for x in iterate(train,order):
                owner=x["candidate_root"];q=ragged_targets_flat(x["labels"],owner,x["batch_size"],tau);lengths=x["candidate_lengths"]
                opt.zero_grad();loss=ragged_root_ce(model(x),q,owner,lengths);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
                seen_roots.extend(x["root_indices"].detach().cpu().tolist());seen_actions+=len(x["labels"]);optimizer_steps+=1
            accounting.append(assert_epoch_accounting(seen_roots,train,optimizer_steps,batch_size=128,action_count=seen_actions))
            model.eval();vsum=0.;vcount=0
            with torch.no_grad():
                for x in iterate(val,np.arange(len(val["contexts"]))):
                    owner=x["candidate_root"];q=ragged_targets_flat(x["labels"],owner,x["batch_size"],tau);lengths=x["candidate_lengths"]
                    logits=model(x);vsum+=float(ragged_root_ce(logits,q,owner,lengths))*len(lengths);vcount+=len(lengths)
            v=vsum/vcount;hist.append(v)
            if v<best:
                best=v;patience=0;torch.save({"state_dict":model.state_dict(),"config":cfg,"normalization":{k:v.clone() for k,v in normalization.items()},"arm":arm,"tau":tau,"epoch":epoch},artifact_dir/f"{arm}.pt")
            else:patience+=1
            if patience>=8:break
        summaries[arm]={"best_validation_ce":best,"epochs":len(hist),"history":hist,"epoch_accounting":accounting,"checkpoint_sha256":sha256(artifact_dir/f"{arm}.pt")}
    (artifact_dir/"train-summary.json").write_text(json.dumps(summaries,indent=2)+"\n")
    validation=write_validation_metrics(cache,artifact_dir,dev)
    print(json.dumps({"config":cfg,"summary":summaries,"validation_metrics_path":str(artifact_dir/"validation-metrics.json")},indent=2));return {"summary":summaries,"validation":validation}


def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="command",required=True)
    p=sub.add_parser("prepare");p.add_argument("corpus",type=Path);p.add_argument("cache",type=Path)
    p=sub.add_parser("train-stage-a");p.add_argument("corpus",type=Path);p.add_argument("cache",type=Path);p.add_argument("artifact_dir",type=Path);p.add_argument("--seed",type=int,default=SEED);p.add_argument("--device",default="auto");p.add_argument("--probe-only",action="store_true")
    p=sub.add_parser("evaluate-validation-j");p.add_argument("corpus",type=Path);p.add_argument("cache",type=Path);p.add_argument("artifact_dir",type=Path);p.add_argument("--device",default="cpu")
    args=ap.parse_args()
    if args.command=="prepare":
        c=cache_payload(args.corpus,args.cache);print(json.dumps({"metadata":c["metadata"],"train_roots":len(c["prepared"]["TRAIN"]["contexts"]),"validation_roots":len(c["prepared"]["VALIDATION"]["contexts"])},indent=2))
    elif args.command=="train-stage-a":train_stage_a(args.corpus,args.cache,args.artifact_dir,args.seed,args.device,args.probe_only)
    else:
        c=cache_payload(args.corpus,args.cache);val=c["prepared"]["VALIDATION"];c["by_root"]={rid:{"q":q,"source_seed":seed} for rid,q,seed in zip(val["root_id"],val["root_values"],val["source_seed"])}
        lm=json.loads((args.artifact_dir/"validation-metrics.json").read_text())
        jm=evaluate_validation_j(args.corpus,c,args.artifact_dir,args.device)
        decision=select_temperature(lm,jm,args.artifact_dir)
        print(json.dumps(decision,indent=2))


if __name__=="__main__":main()
