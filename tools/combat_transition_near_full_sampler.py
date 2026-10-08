#!/usr/bin/env python3
"""Offline RAW near-full sampler; runtime support is deliberately separate."""
import copy
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_near_full_support as support
from tools import combat_transition_near_full_downstream as downstream
from tools import combat_transition_potion_trajectory as trajectory
from tools import combat_transition_gold as gold,combat_transition_gold_proc_budget as budget
from tools import combat_transition_sparse_events as events


def sample_potions_batch(net,z,pres,delta,hp,planner,boss,escape=None):
    """Batched calls, independent native hypothetical origin per imagined row.

    escape (per row 0/1) conditions the trajectory on an escape drawn earlier."""
    inventory=np.asarray([pre['potions'] for pre in pres],np.int64)
    capacity=np.asarray([pre['potionCapacity'] for pre in pres],np.int64)
    original_bits=((inventory>1)*(1<<np.arange(5))).sum(-1)
    initial_mask=np.zeros(len(pres),np.int64);used=[[] for _ in pres];discarded=[[] for _ in pres];body=[[] for _ in pres]
    origins=[None for _ in pres];states=[None for _ in pres];escaped=np.zeros(len(pres),bool);pending=np.arange(len(pres))
    sozu=np.asarray([any(r['id']==c.base._RELIC_IDS['SOZU'] for r in pre['relics']) for pre in pres])
    while len(pending):
        lp=trajectory.log_probabilities(net,np.asarray(z)[pending],inventory[pending],capacity[pending],np.asarray(delta)[pending],np.asarray(hp)[pending],np.asarray(boss)[pending],
                                        None if escape is None else np.asarray(escape)[pending])
        probability=lp.detach().exp().cpu().numpy().astype(np.float64);probability/=probability.sum(-1,keepdims=True)
        actions=(planner.random(len(pending))[:,None]>=probability.cumsum(-1)).sum(-1).clip(max=63)
        next_pending=[]
        for row,action in zip(pending,actions):
            action=int(action);mask=action&31;use=action>=32;initial_mask[row]|=mask&original_bits[row]
            remaining,consumed=trajectory.consume(inventory[row],mask);inventory[row]=remaining
            used[row].extend(p for p in consumed if p not in (trajectory.BREW,trajectory.SMOKE) or use)
            discarded[row].extend(p for p in consumed if p in (trajectory.BREW,trajectory.SMOKE) and not use)
            if trajectory.SMOKE in consumed and use:escaped[row]=True;continue
            if trajectory.BREW in consumed and use:
                if states[row] is None:origins[row]=trajectory.brew.hypothetical_origin(planner);states[row]=dict(origins[row])
                generated,states[row]=trajectory.brew.generate(states[row],int(capacity[row]));body[row].extend(generated)
                inventory[row]=trajectory.brew.obtain(inventory[row],generated,bool(sozu[row]),int(capacity[row]));next_pending.append(row)
            elif not (mask==0 or (not any(p in (trajectory.BREW,trajectory.SMOKE) for p in consumed) and not any(p in (trajectory.BREW,trajectory.SMOKE) for p in inventory[row]))):next_pending.append(row)
        pending=np.asarray(next_pending,np.int64)
    return [dict(outcome='ESCAPE' if escaped[row] else 'VICTORY',potions=inventory[row].tolist(),potionCount=int((inventory[row]>1).sum()),initialMask=int(initial_mask[row]),consumed=list(map(int,used[row])),discarded=list(map(int,discarded[row])),generated=list(map(int,body[row])),brewUses=used[row].count(trajectory.BREW),hypotheticalOrigin=origins[row],potionRng=dict(pres[row]['combatRng'][4]) if states[row] is None else states[row]) for row in range(len(pres))]


def conditions(pre,pi,ending,maximum,mask,consumed,escaped):
    mode,mechanical=gold.mechanics(pi,pre,int(mask),consumed)
    mechanical[gold.MECHANICAL_FIELDS.index('eligibleKillCap')]-=int(escaped)
    omamori=next((r['data'] for r in pre['relics'] if r['id']==c.base._RELIC_IDS['OMAMORI']),0)
    darkstone=any(r['id']==c.base._RELIC_IDS['DARKSTONE_PERIAPT'] for r in pre['relics'])
    daggers=[card for card in pre['deck'] if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']]
    features=np.asarray([omamori/2,int(darkstone),len(daggers),sum(int(card['upgraded']) for card in daggers),int(pi['globals']['encounter']==c.base.WRITHING_MASS_ID),int(escaped),float(mechanical[9]),int(trajectory.EFFECT_IDS[0] in consumed)],np.float32)
    hp=np.asarray([(ending-pre['curHp'])/160,ending/maximum,(maximum-pre['maxHp'])/10],np.float32)
    return hp,c.potion.BITS[mask].astype(np.float32),mechanical,features


def event_probabilities(net,z,hp,bits,features,candidates,legal=None):
    if legal is None:legal=np.ones(len(candidates),bool)
    device=next(net.parameters()).device
    values=(np.asarray(z,np.float32)[None],hp[None],bits[None],features[None],np.asarray(candidates,np.float32)[None],np.asarray(legal)[None])
    return net(*(torch.as_tensor(v,device=device) for v in values))[0].exp().cpu().numpy().astype(float)


def batch_event_probabilities(net,z,hp,bits,features,candidates,legals):
    width=max(len(value) for value in candidates);cards=max(value.shape[1] for value in candidates)
    padded=np.zeros((len(candidates),width,cards,3),np.float32);legal=np.zeros((len(candidates),width),bool)
    for row,(value,allowed) in enumerate(zip(candidates,legals)):padded[row,:len(value),:value.shape[1]]=value;legal[row,:len(value)]=allowed
    device=next(net.parameters()).device
    values=(np.asarray(z,np.float32),np.asarray(hp,np.float32),np.asarray(bits,np.float32),np.asarray(features,np.float32),padded,legal)
    return net(*(torch.as_tensor(v,device=device) for v in values)).exp().cpu().numpy().astype(float)


def batch_gold_probabilities(net,z,hp,bits,mechanical,posts,gold_values):
    width=max(len(values) for values in posts);candidate=np.zeros((len(posts),width,6),np.float32);legal=np.zeros((len(posts),width),bool)
    for row,values in enumerate(posts):candidate[row,:len(values)]=gold.candidate_features(values,gold_values[row]);legal[row,:len(values)]=True
    device=next(net.parameters()).device
    values=(np.asarray(z,np.float32),np.asarray(mechanical,np.float32),np.asarray(hp,np.float32),np.asarray(bits,np.float32),candidate,legal)
    return net(*(torch.as_tensor(v,device=device) for v in values)).exp().cpu().numpy().astype(float)


def writhing_probabilities(net,z,pre,pi,ending,maximum,mask,consumed,escaped):
    hp,bits,mechanical,features=conditions(pre,pi,ending,maximum,mask,consumed,escaped)
    posts=events.writhing_posts(pre);omamori=features[0]>0
    candidates=np.asarray([[[0,0,0]],[[1,int(omamori),int(not omamori)]]],np.float32)[:len(posts)]
    legal=np.ones(len(posts),bool)
    if len(posts)>1 and features[1] and not omamori and maximum-pre['maxHp']<6:legal[1]=False
    return posts,event_probabilities(net,z,hp,bits,features,candidates,legal)


def ritual_probabilities(net,z,pre,pi,ending,maximum,mask,consumed,escaped):
    amounts=events.ritual_posts(pre,pi,mask,consumed,escaped)
    daggers=[card for card in pre['deck'] if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']]
    if not daggers:return amounts,np.ones(1)
    hp,bits,mechanical,features=conditions(pre,pi,ending,maximum,mask,consumed,escaped)
    candidates=np.asarray([[[card['misc']/100,int(card['upgraded']),amount/20] for card,amount in zip(daggers,values)] for values in amounts],np.float32)
    return amounts,event_probabilities(net,z,hp,bits,features,candidates)


def gold_probabilities(net,z,pre,pi,ending,maximum,mask,consumed,escaped,dagger_deltas):
    posts=budget.joint_gold_posts(pre,pi,mask,dagger_deltas,consumed,escaped)
    if not posts:raise ValueError('empty joint native gold support')
    if len(posts)==1:return posts,np.ones(1)
    hp,bits,mechanical,features=conditions(pre,pi,ending,maximum,mask,consumed,escaped);device=next(net.parameters()).device
    values=(np.asarray(z,np.float32)[None],mechanical[None],hp[None],bits[None],gold.candidate_features(posts,pre['gold'])[None],np.ones((1,len(posts)),bool))
    return posts,net(*(torch.as_tensor(v,device=device) for v in values))[0].exp().cpu().numpy().astype(float)


def assemble(pre,pi,ending,maximum,potion_trace,residues,writhing_event,dagger_deltas,pair):
    post={key:copy.deepcopy(pre[key]) for key in c.base.PERSISTENT_KEYS}
    post['combatRng']=copy.deepcopy(pre['combatRng'])
    post['curHp']=int(ending);post['maxHp']=int(maximum);post['gold'],post['stolenGold']=map(int,pair)
    post['potions']=potion_trace['potions'];post['potionCount']=potion_trace['potionCount'];post['smokeBombUsed']=potion_trace['outcome']=='ESCAPE'
    encounter=pi['globals']['encounter'];writhing=encounter==c.base.WRITHING_MASS_ID
    before=[r for r in pre['relics'] if not (writhing and r['id']==c.base._RELIC_IDS['OMAMORI'])]
    reconstructed=c.relic.reconstruct(before,residues,encounter,any(r['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pre['relics']))
    iterator=iter(reconstructed);post['relics']=[copy.deepcopy(r) if writhing and r['id']==c.base._RELIC_IDS['OMAMORI'] else next(iterator) for r in pre['relics']]
    if writhing:
        native=events.writhing_posts(pre)[writhing_event]
        for key in ('deck','cardTypeCounts','upgradeableCount','transformableCount','bottleIdxs'):post[key]=copy.deepcopy(native[key])
        omamori=next((r['data'] for r in native['relics'] if r['id']==c.base._RELIC_IDS['OMAMORI']),None)
        for relic in post['relics']:
            if relic['id']==c.base._RELIC_IDS['OMAMORI']:relic['data']=omamori
    dagger_index=0
    for card in post['deck']:
        if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']:
            misc=card['misc']+int(dagger_deltas[dagger_index]);dagger_index+=1
            if not -32768<=misc<=32767:raise ValueError('Ritual Dagger int16 misc overflow requires native scope audit')
            card['misc']=misc
    if dagger_index!=len(dagger_deltas):raise ValueError('Dagger native identity mismatch')
    post['combatRng'][2]=c.native_rng.replay_misc(pre['combatRng'][2],gold.encounter_name(encounter));post['combatRng'][4]=copy.deepcopy(potion_trace['potionRng'])
    return post


class NearFullSampler:
    def __init__(self,parent,folder=None,device='cuda',final_support=False,escape=None,writhing_ritual=False):
        """escape: an escape fit checkpoint (tools/ctm_escape.py); draws the escape before HP.
        writhing_ritual: support Writhing Mass with Ritual Dagger (the writhingRitual capability)."""
        self.final_support=final_support;self.writhing_ritual=writhing_ritual
        self.escape=None
        if escape is not None:
            from tools import ctm_escape
            self.escape=ctm_escape.TorchEscape.load(escape,device)
        parent=Path(parent);folder=parent/'full-union-downstream-v1' if folder is None else Path(folder)
        self.models,self.bindings=downstream.load_upstream(parent,device)
        import json
        receipt=json.loads((folder/'fit.json').read_text())
        if c.base.sha256(folder/'downstream.pt')!=receipt['artifactSha256']:raise ValueError('downstream binding differs')
        self.heads=downstream.models(parent).to(device).eval().requires_grad_(False)
        self.heads.load_state_dict(torch.load(folder/'downstream.pt',map_location=device,weights_only=False)['stateDict']);self.bindings['downstream']=receipt['artifactSha256']

    def sample_transition(self,pre,pi,planner):
        m=self.models
        escape=getattr(self,'escape',None)
        if getattr(self,'final_support',False):reasons=support.final_reasons(pi,pre,m,escape=escape is not None,writhing_ritual=getattr(self,'writhing_ritual',False))
        else:
            with support.candidate_contract():reasons=c.full_support_reasons(pre,pi,m)
        if reasons:return c.Transition('FULL_SURROGATE_FALLBACK',reasons=tuple(reasons))
        with torch.inference_mode():
            inputs=m.encode_visible(pi)
            if planner.random()>=m.survival(inputs):return c.Transition('DEATH')
            delta=c.categorical(m.max_hp(inputs),planner);maximum=pre['maxHp']+int(m.delta_values[delta]);z=m.hp_encoding(inputs)
            boss=gold.encounter_name(pi['globals']['encounter']) in trajectory.BOSSES;bit=None
            if escape is None:signed=c.categorical(m.hp_distribution(z,delta,pre['curHp'],maximum),planner)
            else:
                bit=0
                if escape.eligible(pre['potions'],pre['potionCapacity'],boss):bit=int(planner.random()<escape.probability(z)[0])
                signed=c.categorical(escape.hp_distribution(z,delta,pre['curHp'],maximum,bit,m.classes),planner)
            ending=pre['curHp']+int(m.classes[signed])
            zp=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy()[0]
            trace=trajectory.sample(m.potion_net,zp,pre,delta,ending/maximum,planner,boss,bit)
            mask=trace['initialMask'];consumed=tuple(trace['consumed']);escaped=trace['outcome']=='ESCAPE';raw_z=z.cpu().numpy()[0]
            logits=self.heads['relic'](z,torch.as_tensor([signed],device=m.device),torch.as_tensor([ending/maximum],device=m.device,dtype=torch.float32),torch.as_tensor([mask],device=m.device),torch.as_tensor([escaped],device=m.device,dtype=torch.float32))
            residues={name:c.categorical(torch.softmax(logits[name],-1)[0].cpu().numpy(),planner) for name in c.TRAINED_GROUPS}
            event=0
            if pi['globals']['encounter']==c.base.WRITHING_MASS_ID:
                _,p=writhing_probabilities(self.heads['writhing'],raw_z,pre,pi,ending,maximum,mask,consumed,escaped);event=c.categorical(p,planner)
            amounts,p=ritual_probabilities(self.heads['ritual'],raw_z,pre,pi,ending,maximum,mask,consumed,escaped);dagger=amounts[c.categorical(p,planner)]
            posts,p=gold_probabilities(self.heads['gold'],raw_z,pre,pi,ending,maximum,mask,consumed,escaped,dagger);pair=posts[c.categorical(p,planner)]
            post=assemble(pre,pi,ending,maximum,trace,residues,event,dagger,pair)
            return c.Transition(trace['outcome'],post)
