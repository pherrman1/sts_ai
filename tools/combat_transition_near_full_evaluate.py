#!/usr/bin/env python3
"""Whole-union source-grouped engineering composition and RAW validity."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_near_full_downstream as d,combat_transition_near_full_sampler as s
from tools import combat_transition_potion_trajectory as t,combat_transition_potion_trajectory_evaluate as te
from tools import combat_transition_sparse_events as events,combat_transition_sparse_evaluate as sparse
from tools import combat_transition_gold as gold,combat_transition_gold_proc_budget as budget

RECIPE=dict(seed=20260920,draws=32,batch=512,threshold=.1,partition='original source-grouped TEST; reused development evidence',
            hpExposure='exact eleven-class maxHP marginal',potionExposure='32 upstream HP/maxHP draws, exact observed-body trajectory DAG',
            downstreamExposure='32 complete upstream HP/potion/escape/Ritual draws; exact conditional native target probabilities',
            validity='32 complete sampled RAW transitions per TEST row, including model death short-circuit',supportChanged=False)


def pick(prob,rng):return e.draw_categories(np.asarray(prob,np.float64),rng)


def heads(nets,z,rows,ending,maximum,traces,rng,cache,teacher=False):
    """Batch downstream heads, native supports, and conditional target masses."""
    pres=[r['pre'] for r in rows];pis=[r['pi'] for r in rows];mask=np.asarray([x['initialMask'] for x in traces]);escaped=np.asarray([x['outcome']=='ESCAPE' for x in traces]);consumed=[tuple(x['consumed']) for x in traces]
    cond=[s.conditions(pre,pi,int(h),int(m),int(k),used,bool(esc)) for pre,pi,h,m,k,used,esc in zip(pres,pis,ending,maximum,mask,consumed,escaped)]
    hp=np.asarray([v[0] for v in cond]);bits=np.asarray([v[1] for v in cond]);mechanical=np.asarray([v[2] for v in cond]);features=np.asarray([v[3] for v in cond]);device=next(nets.parameters()).device
    def tensor(v):return torch.as_tensor(v,device=device)
    signed=ending-np.asarray([p['curHp'] for p in pres])-c.CLASSES[0];fraction=ending/maximum
    logits=nets['relic'](tensor(z),tensor(signed),tensor(fraction.astype(np.float32)),tensor(mask),tensor(escaped.astype(np.float32)))
    probabilities={name:e.probabilities(logits[name]) for name in c.TRAINED_GROUPS};residues={name:pick(value,rng) for name,value in probabilities.items()};target=np.ones((len(rows),4),np.float64)
    for j,name in enumerate(c.TRAINED_GROUPS):
        selected=cache['observed'][:,j];mass=(probabilities[name]*cache['compatible_'+name]).sum(-1);target[selected,0]*=mass[selected]
    writhing=np.asarray([pi['globals']['encounter']==c.base.WRITHING_MASS_ID for pi in pis]);ritual=np.asarray([any(card['id']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in pre['deck']) for pre in pres]);writhing_event=np.zeros(len(rows),np.int64);dagger=[() for _ in rows]
    selected=np.flatnonzero(writhing)
    if len(selected):
        candidates=[];legals=[]
        for i in selected:
            om=features[i,0]>0;candidate=np.asarray([[[0,0,0]],[[1,int(om),int(not om)]]],np.float32);legal=np.ones(2,bool)
            if features[i,1] and not om and maximum[i]-pres[i]['maxHp']<6:legal[1]=False
            candidates.append(candidate);legals.append(legal)
        probability=s.batch_event_probabilities(nets['writhing'],z[selected],hp[selected],bits[selected],features[selected],candidates,legals);writhing_event[selected]=pick(probability,rng)
        actual=cache['writhingTarget'][selected];target[selected,1]=probability[np.arange(len(selected)),actual]
    selected=np.flatnonzero(ritual)
    if len(selected):
        candidates=[];amounts=[];legals=[]
        for i in selected:
            values=events.ritual_posts(pres[i],pis[i],int(mask[i]),consumed[i],bool(escaped[i]));cards=[card for card in pres[i]['deck'] if card['id']==c.base._CARD_IDS['RITUAL_DAGGER']];amounts.append(values)
            candidates.append(np.asarray([[[card['misc']/100,int(card['upgraded']),delta/20] for card,delta in zip(cards,value)] for value in values],np.float32));legals.append(np.ones(len(values),bool))
        probability=s.batch_event_probabilities(nets['ritual'],z[selected],hp[selected],bits[selected],features[selected],candidates,legals);choices=pick(probability,rng)
        for j,i in enumerate(selected):
            dagger[i]=amounts[j][choices[j]];actual=cache['daggerTarget'][i];target[i,2]=probability[j,amounts[j].index(actual)] if actual in amounts[j] else 0.
    sampled_dagger=dagger
    if teacher:dagger=list(cache['daggerTarget'])
    posts=[budget.joint_gold_posts(pre,pi,int(k),amounts,used,bool(esc)) for pre,pi,k,amounts,used,esc in zip(pres,pis,mask,dagger,consumed,escaped)]
    impossible=np.asarray([not p for p in posts])
    if teacher:
        for i in np.flatnonzero(impossible):posts[i]=budget.joint_gold_posts(pres[i],pis[i],int(mask[i]),sampled_dagger[i],consumed[i],bool(escaped[i]))
    if any(not p for p in posts):raise ValueError('empty joint native particle gold support')
    pairs=[p[0] for p in posts];selected=np.asarray([i for i,p in enumerate(posts) if len(p)>1],np.int64)
    for i,p in enumerate(posts):
        if len(p)==1:target[i,3]=float(p[0]==cache['goldTarget'][i])
    if len(selected):
        probability=s.batch_gold_probabilities(nets['gold'],z[selected],hp[selected],bits[selected],mechanical[selected],[posts[i] for i in selected],[pres[i]['gold'] for i in selected]);choice=pick(probability,rng)
        for j,i in enumerate(selected):
            pairs[i]=posts[i][choice[j]];actual=cache['goldTarget'][i];target[i,3]=probability[j,posts[i].index(actual)] if actual in posts[i] else 0.
    target[impossible,3]=0.
    return dict(residues=residues,writhing=writhing_event,dagger=dagger,pairs=pairs,target=target)


def load(parent,final_support=False):
    cache,graphs,meta=te.load(parent/'potion-trajectory-v2');dc,ambiguous,records,dm=d.load(parent,parent/'full-union-downstream-v1');cache.update(dc)
    snapshot=json.loads((parent/'full-union-test-states-v1.json').read_text());file=parent/'full-union-test-states-v1.jsonl'
    if c.base.sha256(file)!=snapshot['snapshotSha256'] or snapshot['corpusSha256']!=c.base.sha256(e.CORPUS):raise ValueError('TEST snapshot differs')
    rows=list(map(json.loads,file.open()));ids=np.asarray([r['index'] for r in rows]);target_dagger=[];target_writhing=[]
    for r in rows:
        pre,post,pi=r['pre'],r['post'],r['pi'];win=r['outcome']==c.base.WIN;wr=pi['globals']['encounter']==c.base.WRITHING_MASS_ID
        event=events.writhing_target(pre,post) if win and wr else 0;target_writhing.append(event)
        adjusted=events.writhing_posts(pre)[event] if wr else pre
        target_dagger.append(tuple(x['delta'] for x in events.ritual_changes(adjusted,post)) if win else ())
    test={k:v[ids] for k,v in cache.items() if isinstance(v,np.ndarray) and v.shape and v.shape[0]==len(cache['ids'])}
    test['writhingTarget']=np.asarray(target_writhing);test['daggerTarget']=target_dagger;test['goldTarget']=[(r['post']['gold'],r['post']['stolenGold']) for r in rows]
    if final_support:
        chosen=np.flatnonzero(s.support.final_mask(rows));rows=[rows[i] for i in chosen];ids=ids[chosen];test=subset(test,chosen)
    return cache,graphs,ambiguous,records,dm,rows,ids,test,snapshot


def subset(test,indices):
    return {k:v[indices] if isinstance(v,np.ndarray) else [v[i] for i in indices] for k,v in test.items()}


def networks(parent,downstream="full-union-downstream-v1",maxhp="full-union-maxHP-v1"):
    from tools.combat_transition_near_full_models import load
    return load(parent,'cuda',downstream,maxhp)


def upstream(m,parent,ids,test):
    arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec);survival=np.empty(len(ids));pd=np.empty((len(ids),len(m.delta_values)))
    with torch.inference_mode():
        for start in range(0,len(ids),512):
            sub=np.arange(start,min(start+512,len(ids)));inputs=c.base._torch_inputs(arrays,ids[sub],'cuda',torch,trim_padding=True)
            survival[sub]=torch.sigmoid(m.survival_net.survival(m.fp32_encoding(m.survival_net.encoder,inputs))).flatten().cpu().numpy();pd[sub]=e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)))
    return survival,pd


def check_raw(pre,pi,post,trace,particle,row):
    if not 1<=post['curHp']<=post['maxHp'] or post['maxHp']-pre['maxHp'] not in (0,3,4,5,6,7,8,9,10,11,12):raise ValueError('illegal HP/maxHP')
    if post['potionCount']!=sum(p>1 for p in post['potions']):raise ValueError('potion count')
    if trace['outcome']=='ESCAPE' and gold.encounter_name(pi['globals']['encounter']) in t.BOSSES:raise ValueError('boss escape')
    if post['smokeBombUsed']!=(trace['outcome']=='ESCAPE'):raise ValueError('escape RAW flag')
    if len(trace['generated'])!=trace['brewUses']*pre['potionCapacity']:raise ValueError('native Brew draw count')
    if trace['hypotheticalOrigin'] is not None:
        state=dict(trace['hypotheticalOrigin']);body=[]
        for _ in range(trace['brewUses']):generated,state=t.brew.generate(state,pre['potionCapacity']);body.extend(generated)
        if body!=trace['generated'] or state!=post['combatRng'][4]:raise ValueError('hypothetical native generation/RNG continuation')
    elif post['combatRng'][4]!=pre['combatRng'][4]:raise ValueError('unconsumed Brew historical continuation')
    if any(not c.rng_valid(post['combatRng'][i]) for i in (2,4)):raise ValueError('invalid RNG')
    if post['combatRng'][2]!=c.native_rng.replay_misc(pre['combatRng'][2],gold.encounter_name(pi['globals']['encounter'])):raise ValueError('misc continuation')
    for i in (0,1,3,5):
        if post['combatRng'][i]!=pre['combatRng'][i]:raise ValueError('copy-through RNG')
    adjusted=events.writhing_posts(pre)[int(particle['writhing'][row])] if pi['globals']['encounter']==c.base.WRITHING_MASS_ID else pre
    changes=tuple(x['delta'] for x in events.ritual_changes(adjusted,post))
    if changes not in events.ritual_posts(pre,pi,trace['initialMask'],tuple(trace['consumed']),post['smokeBombUsed']):raise ValueError('native Dagger increments')
    if (post['gold'],post['stolenGold']) not in budget.joint_gold_posts(pre,pi,trace['initialMask'],changes,tuple(trace['consumed']),post['smokeBombUsed']):raise ValueError('joint gold/Dagger budget')
    for key in ('cardTypeCounts','bottleIdxs','upgradeableCount','transformableCount','relicBits'):
        if post[key]!=adjusted[key]:raise ValueError('native sparse/copy-through field')
    rid=c.base._RELIC_IDS['OMAMORI'];wr=pi['globals']['encounter']==c.base.WRITHING_MASS_ID
    before=[r for r in adjusted['relics'] if not (wr and r['id']==rid)];after=[r for r in post['relics'] if not (wr and r['id']==rid)]
    residues={name:int(values[row]) for name,values in particle['residues'].items()}
    if after!=c.relic.reconstruct(before,residues,pi['globals']['encounter'],any(r['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pre['relics'])):raise ValueError('shared relic residues')
    if wr and [r for r in post['relics'] if r['id']==rid]!=[r for r in adjusted['relics'] if r['id']==rid]:raise ValueError('native Writhing Omamori')


def hard(parent,output,sha,limit=None,downstream="full-union-downstream-v1",maxhp="full-union-maxHP-v1",final_support=False):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,ambiguous,records,meta,rows,ids,test,snapshot=load(parent,final_support);torch.set_num_threads(4);m,nets,bindings=networks(parent,downstream,maxhp);survival,pd=upstream(m,parent,ids,test);rng=np.random.default_rng(RECIPE['seed']);counts=Counter();violations={name:0 for name in ('hp','potions','goldDaggerBudget','writhing','relicResidues','rng','escape','deathShortCircuit')}
    if limit is not None:
        sub=np.arange(min(limit,len(rows)));rows=[rows[i] for i in sub];ids=ids[sub];test=subset(test,sub);survival=survival[sub];pd=pd[sub]
    with torch.inference_mode():
        for draw in range(32):
            alive=rng.random(len(rows))<survival;counts['draws']+=len(rows);counts['death']+=int((~alive).sum());counts['downstreamAfterDeath']+=0
            for start in range(0,len(rows),512):
                sub=np.arange(start,min(start+512,len(rows)));sub=sub[alive[sub]]
                if not len(sub):continue
                dindex=pick(pd[sub],rng);maximum=test['preMax'][sub]+m.delta_values[dindex];hp=e.hp_prob(m,test['z'][sub],dindex,test['preHp'][sub],maximum);ending=test['preHp'][sub]+c.CLASSES[pick(hp,rng)];rr=[rows[i] for i in sub]
                traces=s.sample_potions_batch(m.potion_net,test['potionZ'][sub],[r['pre'] for r in rr],dindex,ending/maximum,rng,test['boss'][sub]);particle=heads(nets,test['z'][sub],rr,ending,maximum,traces,rng,subset(test,sub))
                for row,(r,trace) in enumerate(zip(rr,traces)):
                    residues={name:int(value[row]) for name,value in particle['residues'].items()};post=s.assemble(r['pre'],r['pi'],int(ending[row]),int(maximum[row]),trace,residues,int(particle['writhing'][row]),particle['dagger'][row],particle['pairs'][row]);check_raw(r['pre'],r['pi'],post,trace,particle,row)
                    counts[trace['outcome'].lower()]+=1;counts['brewUses']+=trace['brewUses'];counts['recursiveSampledTrajectories']+=trace['brewUses']>sum(p==t.BREW for p in r['pre']['potions'])
            print('whole final union RAW validity',draw+1,dict(counts),flush=True)
    result=dict(finalSupport=final_support,sourceSha=sha,downstreamFolder=downstream,maxHpFolder=maxhp,recipe=RECIPE,bindings=bindings,testSnapshot=snapshot,counts=counts,violations=violations,classification='RAW_SMOKE_PASS' if limit is not None else 'WHOLE_UNION_RAW_VALIDITY_PASS',supportChanged=False,scope='offline RAW contract; native escape continuation has separate exact oracle')
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['hard']);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--limit',type=int);p.add_argument('--downstream',default='full-union-downstream-v1');p.add_argument('--maxhp',default='full-union-maxHP-v1');p.add_argument('--final-support',action='store_true');a=p.parse_args();globals()[a.command](a.parent,a.output,a.source_sha,a.limit,a.downstream,a.maxhp,a.final_support)
