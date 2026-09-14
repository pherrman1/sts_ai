#!/usr/bin/env python3
"""Native potion microtrajectory with shared inventory-conditioned probabilities.

The observed generation body is a teacher OUTPUT label, never a learned input.
Its exact native prior and all compatible consumption orderings are marginalized.
Imagined generation uses one fresh hypothetical native RNG through recursion.
"""
from collections import deque
import copy
from dataclasses import dataclass
import numpy as np
import torch
from tools import combat_transition_brew as brew
from tools import combat_transition_potion_decoder as decoder
from tools import combat_transition_surrogate as base

BREW=base._POTION_IDS['ENTROPIC_BREW'];SMOKE=base._POTION_IDS['SMOKE_BOMB'];EMPTY=1
EFFECT_IDS=tuple(base._POTION_IDS[n] for n in ('COLORLESS_POTION','SKILL_POTION','BLESSING_OF_THE_FORGE'))
BOSSES={'SLIME_BOSS','THE_GUARDIAN','HEXAGHOST','CHAMP','COLLECTOR','AUTOMATON','AWAKENED_ONE','DONU_AND_DECA','TIME_EATER','THE_HEART'}


def legal_masks(inventory,capacity,boss=False):
    slots=np.asarray(inventory)
    masks=decoder.legal_masks(slots[None],np.asarray([capacity]))[0]
    trigger=np.isin(slots,[BREW,SMOKE])
    masks &= (decoder.BITS & trigger).sum(-1)<=1
    return masks


def legal_actions(inventory,capacity,boss=False):
    masks=legal_masks(inventory,capacity,boss);slots=np.asarray(inventory)
    trigger=np.any(decoder.BITS&np.isin(slots,[BREW,SMOKE]),axis=-1)
    use=masks&trigger
    if boss:use &= ~np.any(decoder.BITS&(slots==SMOKE),axis=-1)
    # Low 5 bits select cleared slots. Bit 5 distinguishes native trigger USE
    # from DISCARD; ordinary masks need no duplicate action category.
    return np.concatenate((masks,use))


def new_decoder(delta_count,warm=None):
    net=decoder.new_decoder('joint',delta_count) if warm is None else copy.deepcopy(warm)
    old=net.mlp[2];new=torch.nn.Linear(64,64,device=old.weight.device)
    with torch.no_grad():
        new.weight.copy_(old.weight.repeat(2,1));new.bias.copy_(old.bias.repeat(2)-np.log(2.))
    net.mlp[2]=new
    return net


def log_probabilities(net,z,inventory,capacity,delta,hp,boss):
    """Same shared joint-mask architecture; exact native trigger restrictions."""
    device=next(net.parameters()).device
    values=[torch.as_tensor(v,device=device) for v in (z,inventory,delta,np.asarray(hp,np.float32))]
    z,slots,delta,hp=values
    if z.requires_grad:
        shared=torch.cat((z,net.delta(delta),hp[:,None]),-1)
        inventory_features=torch.cat((net.potion(slots),net.slot.weight[None].expand(len(z),-1,-1)),-1)
        logits=net.mlp(torch.cat((shared,inventory_features.flatten(1)),-1))
    else:logits=net.output_logits(z,slots,delta,hp)
    slots=values[1];bits=torch.as_tensor(decoder.BITS,device=device)
    active=(slots>1)&(torch.arange(5,device=device)[None]<torch.as_tensor(capacity,device=device)[:,None])
    legal=~torch.any(bits[None]&~active[:,None],-1)
    trigger=(slots==BREW)|(slots==SMOKE)
    legal &= (bits[None]&trigger[:,None]).sum(-1)<=1
    trigger_selected=torch.any(bits[None]&trigger[:,None],-1)
    use=legal&trigger_selected
    use &= ~torch.any(bits[None]&(slots==SMOKE)[:,None],-1)|~torch.as_tensor(boss,device=device)[:,None]
    legal=torch.cat((legal,use),-1)
    return torch.log_softmax(logits.masked_fill(~legal,-torch.inf),-1)


def consume(inventory,mask):
    used=tuple(p for i,p in enumerate(inventory) if mask&(1<<i))
    return tuple(EMPTY if mask&(1<<i) else p for i,p in enumerate(inventory)),used


@dataclass
class Graph:
    inventories: np.ndarray
    edges: tuple
    target_edges: tuple
    generation_log_prior: float
    rounds: int


def target_graph(pre,post,generated,boss=False):
    """Finite DAG for an observed native generation body and retained inventory.

    Nontrigger masks clear at least one slot; Brew edges advance the observed
    body. No target-hit Monte Carlo or canonical-order label guessing is used.
    """
    capacity=pre['potionCapacity'];sozu=any(r['id']==base._RELIC_IDS['SOZU'] for r in pre['relics'])
    if len(generated)%capacity:raise ValueError('partial native generation round')
    rounds=len(generated)//capacity;target=tuple(post['potions']);escape=bool(post['smokeBombUsed'])
    initial=(tuple(pre['potions']),0);states=[initial];index={initial:0};queue=deque([initial]);edges=[];terminals=[]
    while queue:
        inventory,used_rounds=queue.popleft();owner=index[inventory,used_rounds]
        for action in np.flatnonzero(legal_actions(inventory,capacity,boss)):
            mask=int(action)&31;use=action>=32
            remaining,used=consume(inventory,mask)
            if SMOKE in used and use:
                if escape and used_rounds==rounds and remaining==target:terminals.append((owner,int(action)))
                continue
            if BREW in used and use:
                if used_rounds==rounds:continue
                body=generated[used_rounds*capacity:(used_rounds+1)*capacity]
                remaining=tuple(brew.obtain(remaining,body,sozu,capacity));next_round=used_rounds+1
            elif mask==0 or (not any(p in (BREW,SMOKE) for p in used) and not any(p in (BREW,SMOKE) for p in remaining)):
                if not escape and used_rounds==rounds and remaining==target:terminals.append((owner,int(action)))
                continue
            else:next_round=used_rounds
            child=(remaining,next_round)
            if child not in index:index[child]=len(states);states.append(child);queue.append(child)
            edges.append((owner,int(action),index[child]))
    if not terminals:raise ValueError('observed native potion trajectory unrepresentable')
    # Topological order: each round advances, and otherwise occupied count falls.
    order=sorted(range(len(states)),key=lambda i:(states[i][1],-sum(p>1 for p in states[i][0])))
    rank={old:new for new,old in enumerate(order)}
    return Graph(np.asarray([states[i][0] for i in order],np.int64),
                 tuple((rank[a],m,rank[b]) for a,m,b in edges),
                 tuple((rank[a],m) for a,m in terminals),
                 sum(np.log(brew.PROBABILITY[p]) for p in generated),rounds)


def target_log_probability(logp,graph,include_generation=True):
    # Probability-space DAG avoids undefined logaddexp gradients for unreachable
    # nodes. All masks are normalized native distributions; mass cannot exceed 1.
    incoming=[[] for _ in graph.inventories]
    for owner,mask,child in graph.edges:incoming[child].append((owner,mask))
    masses=[];prob=logp.exp()
    for i,parents in enumerate(incoming):
        masses.append(logp.new_tensor(1.) if i==0 else sum((masses[a]*prob[a,m] for a,m in parents),logp.new_tensor(0.)))
    mass=sum((masses[a]*prob[a,m] for a,m in graph.target_edges),logp.new_tensor(0.))
    if not torch.isfinite(mass) or mass<=0:raise ValueError('zero/nonfinite exact trajectory mass')
    return torch.log(mass)+(graph.generation_log_prior if include_generation else 0.)


def batch_target_log_probabilities(net,graphs,z,capacity,delta,hp,boss,include_generation=True):
    """One network call and level-wise differentiable DAG marginal per batch."""
    owners=[];inventories=[];roots=[];edges=[];terminals=[];priors=[];offset=0
    for row,graph in enumerate(graphs):
        count=len(graph.inventories);owners.extend([row]*count);inventories.extend(graph.inventories);roots.append(offset)
        levels=[0]*count
        for a,m,b in sorted(graph.edges,key=lambda edge:edge[2]):levels[b]=max(levels[b],levels[a]+1)
        edges.extend((a+offset,m,b+offset,levels[b]) for a,m,b in graph.edges)
        terminals.extend((a+offset,m,row) for a,m in graph.target_edges);priors.append(graph.generation_log_prior);offset+=count
    owners=np.asarray(owners,np.int64);device=next(net.parameters()).device
    z=torch.as_tensor(z,device=device)[torch.as_tensor(owners,device=device)]
    lp=log_probabilities(net,z,np.asarray(inventories),np.asarray(capacity)[owners],np.asarray(delta)[owners],np.asarray(hp)[owners],np.asarray(boss)[owners])
    probability=lp.exp();mass=lp.new_zeros(offset).index_fill(0,torch.as_tensor(roots,device=device),1.)
    if edges:
        raw=np.asarray(edges,np.int64)
        for level in range(1,int(raw[:,3].max())+1):
            selected=raw[raw[:,3]==level]
            a,m,b=(torch.as_tensor(selected[:,i],device=device) for i in range(3))
            mass=mass.index_add(0,b,mass[a]*probability[a,m])
    terminal=np.asarray(terminals,np.int64);a,m,row=(torch.as_tensor(terminal[:,i],device=device) for i in range(3))
    target=lp.new_zeros(len(graphs)).index_add(0,row,mass[a]*probability[a,m])
    if not torch.isfinite(target).all() or (target<=0).any():raise ValueError('zero/nonfinite exact trajectory target probability')
    return target.log()+(torch.as_tensor(priors,device=device) if include_generation else 0.)


def sample(net,z,pre,delta,hp,planner,boss=False):
    inventory=tuple(pre['potions']);capacity=pre['potionCapacity'];sozu=any(r['id']==base._RELIC_IDS['SOZU'] for r in pre['relics'])
    origin=None;state=None;body=[];uses=[];discards=[];initial_mask=0
    while True:
        lp=log_probabilities(net,np.asarray(z)[None],np.asarray(inventory)[None],np.asarray([capacity]),np.asarray([delta]),np.asarray([hp]),np.asarray([boss]))
        probability=lp[0].detach().exp().cpu().numpy().astype(float)
        action=int(planner.choice(64,p=probability/probability.sum()));mask=action&31;use=action>=32
        for slot,potion in enumerate(inventory):
            if mask&(1<<slot) and pre['potions'][slot]>1 and not initial_mask&(1<<slot):initial_mask|=1<<slot
        inventory,consumed=consume(inventory,mask)
        uses.extend(p for p in consumed if p not in (BREW,SMOKE) or use)
        discards.extend(p for p in consumed if p in (BREW,SMOKE) and not use)
        if SMOKE in consumed and use:outcome='ESCAPE';break
        if BREW in consumed and use:
            if state is None:origin=brew.hypothetical_origin(planner);state=dict(origin)
            generated,state=brew.generate(state,capacity);body.extend(generated)
            inventory=tuple(brew.obtain(inventory,generated,sozu,capacity))
        elif mask==0 or (not any(p in (BREW,SMOKE) for p in consumed) and not any(p in (BREW,SMOKE) for p in inventory)):outcome='VICTORY';break
    return dict(outcome=outcome,potions=list(inventory),potionCount=sum(p>1 for p in inventory),initialMask=initial_mask,
                consumed=list(uses),discarded=discards,generated=body,brewUses=uses.count(BREW),hypotheticalOrigin=origin,
                potionRng=dict(pre['combatRng'][4]) if state is None else state)
