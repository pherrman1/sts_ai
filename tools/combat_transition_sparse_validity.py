#!/usr/bin/env python3
"""Combined Stage-2 native accounting and 32-draw ancestral validity."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_gold as gold
from tools import combat_transition_gold_proc_budget as budget
from tools import combat_transition_sparse_events as native
from tools import combat_transition_sparse_evaluate as sparse


def run(parent,sha):
    sparse.frozen(sha);output=parent/'sparse-combined-validity-v1.json'
    if output.exists():raise ValueError('refusing overwrite')
    hashes=e.verify_data();torch.set_num_threads(4);m=c.FrozenModels('cuda');arrays,_=c.base._load_prepared(e.PREPARED)
    refitmeta=json.loads((parent/'maxhp-encoder-v1/fit.json').read_text())
    if refitmeta['hashes']!=hashes or c.base.sha256(parent/'maxhp-encoder-v1/maxhp-head.pt')!=refitmeta['artifactSha256']:raise ValueError('maxHP refit binding')
    refit=torch.load(parent/'maxhp-encoder-v1/maxhp-head.pt',weights_only=False,map_location='cpu');m.max_net.max_hp_delta.load_state_dict(refit['stateDict']);m.max_net.encoder.load_state_dict(refit['encoderStateDict'])
    payloads={};cache={};models={};locals_by_global={};rows={};bindings={}
    for name in ('writhing','ritual'):
        folder=parent/(name+'-v1');meta=json.loads((folder/'preparation.json').read_text());fit=json.loads((folder/'fit.json').read_text())
        if meta['hashes']!=hashes or c.base.sha256(folder/'cache.npz')!=meta['cacheSha256'] or c.base.sha256(folder/'event.pt')!=fit['artifactSha256']:raise ValueError('sparse binding')
        with np.load(folder/'cache.npz') as z:cache[name]={k:z[k] for k in z.files}
        payloads[name]=torch.load(folder/'event.pt',weights_only=False,map_location='cpu');models[name]=sparse.net().cuda().eval().requires_grad_(False);models[name].load_state_dict(payloads[name]['stateDict'])
        locals_by_global[name]={int(g):i for i,g in enumerate(cache[name]['ids'])}
        bindings[name]=fit['artifactSha256']
        for r in json.loads((folder/'test_rows.json').read_text()):rows[int(cache[name]['ids'][r['local']])]=r
    goldmeta=json.loads((parent/'shared-gold-v1/fit.json').read_text())
    if c.base.sha256(parent/'shared-gold-v1/gold.pt')!=goldmeta['artifactSha256']:raise ValueError('gold binding')
    goldpayload=torch.load(parent/'shared-gold-v1/gold.pt',weights_only=False,map_location='cpu');goldnet=gold.new_decoder(torch).cuda().eval().requires_grad_(False);goldnet.load_state_dict(goldpayload['stateDict'])
    ids=np.asarray(sorted(rows),np.int64);preHp=np.asarray([rows[i]['pre']['curHp'] for i in ids]);preMax=np.asarray([rows[i]['pre']['maxHp'] for i in ids]);potions=np.asarray([rows[i]['pre']['potions'] for i in ids]);capacity=np.asarray([rows[i]['pre']['potionCapacity'] for i in ids])
    if not np.all(arrays['split_id'][ids]==2):raise ValueError('TEST grouping')
    rng=np.random.default_rng(20260921);hard=Counter();counts=Counter();sampled_deaths=0;events=0
    with torch.inference_mode():
        for draw in range(32):
            for start in range(0,len(ids),256):
                sub=ids[start:start+256];sl=slice(start,start+len(sub));sample=e.complete_batch(m,arrays,sub,preHp[sl],preMax[sl],potions[sl],capacity[sl],rng)
                counts.update(sample['counts']);chosen=sample['chosen'];sampled_deaths+=len(sub)-len(chosen)
                for j,index in enumerate(sub[chosen]):
                    row=rows[index];pre,pi=row['pre'],row['pi'];mask=int(sample['mask'][j]);maximum=int(sample['maximum'][j]);ending=int(sample['ending'][j]);residues={g:int(v[j]) for g,v in sample['residues'].items()}
                    post={k:copy.deepcopy(pre[k]) for k in c.base.PERSISTENT_KEYS};post.update(maxHp=maximum,curHp=ending)
                    post['potions']=c.potion.decode_masks(np.asarray([pre['potions']]),np.asarray([pre['potionCapacity']]),np.asarray([mask]))[0].tolist();post['potionCount']=sum(p>1 for p in post['potions'])
                    deltas=()
                    if index in locals_by_global['ritual']:
                        local=np.asarray([locals_by_global['ritual'][index]]);p=sparse.forward(models['ritual'],cache['ritual'],local,np.asarray([mask]),np.asarray([ending]),np.asarray([maximum])).exp().cpu().numpy()
                        event=int(e.draw_categories(p,rng)[0]);daggers=[k for k,v in enumerate(pre['deck']) if v['id']==c.base._CARD_IDS['RITUAL_DAGGER']]
                        deltas=tuple(int(np.rint(cache['ritual']['candidates'][local[0],event,k,2]*20)) for k in range(len(daggers)))
                        hard['nonNativeDaggerEvent']+=deltas not in native.ritual_posts(pre,pi,mask)
                        for k,delta in zip(daggers,deltas):post['deck'][k]['misc']+=delta
                    writh_event=0
                    if index in locals_by_global['writhing']:
                        local=np.asarray([locals_by_global['writhing'][index]]);p=sparse.forward(models['writhing'],cache['writhing'],local,np.asarray([mask]),np.asarray([ending]),np.asarray([maximum])).exp().cpu().numpy();writh_event=int(e.draw_categories(p,rng)[0])
                        candidate=native.writhing_posts(pre)[writh_event]
                        # Preserve already reconstructed Dagger misc at existing positions.
                        for field in ('cardTypeCounts','transformableCount','upgradeableCount','bottleIdxs'):post[field]=copy.deepcopy(candidate[field])
                        post['deck'].extend(copy.deepcopy(candidate['deck'][len(pre['deck']):]))
                    omamori=c.base._RELIC_IDS['OMAMORI'];bloom=any(r['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pre['relics'])
                    base_relics=[r for r in pre['relics'] if r['id']!=omamori]
                    try:
                        reconstructed=iter(c.relic.reconstruct(base_relics,residues,pi['globals']['encounter'],bloom));omamori_post=native.writhing_posts(pre)[writh_event]['relics'] if index in locals_by_global['writhing'] else pre['relics']
                        omamori_data=next((r['data'] for r in omamori_post if r['id']==omamori),None)
                        post['relics']=[dict(r,data=omamori_data) if r['id']==omamori else next(reconstructed) for r in pre['relics']]
                        constraints=c.relic.trajectory_constraints(base_relics,[r for r in post['relics'] if r['id']!=omamori],pi['globals']['encounter'],bloom)
                        hard['sharedResidueMismatch']+=any(residues[g] not in values for g,values in constraints.items())
                    except (ValueError,KeyError):hard['unqualifiedRelicTransition']+=1
                    posts=budget.joint_gold_posts(pre,pi,mask,deltas)
                    if not posts:raise ValueError('empty joint kill budget')
                    mode,features=gold.mechanics(pi,pre,mask);name=gold.encounter_name(pi['globals']['encounter']);all_posts=gold.native_posts(pre['gold'],name,pi['globals']['ascension'],mode)
                    # Use the reviewed scorer with a narrower native joint budget mask.
                    cache_name='ritual' if index in locals_by_global['ritual'] else 'writhing';local=locals_by_global[cache_name][index];z=cache[cache_name]['z'][local:local+1]
                    hp=np.asarray([[(ending-pre['curHp'])/160,ending/maximum,(maximum-pre['maxHp'])/10]],np.float32)
                    values=(z,features[None],hp,c.potion.BITS[np.asarray([mask])].astype(np.float32),gold.candidate_features(all_posts,pre['gold'])[None],np.asarray([[p in posts for p in all_posts]]))
                    p=goldnet(*(torch.as_tensor(v,device='cuda') for v in values)).exp().cpu().numpy();pair=all_posts[int(e.draw_categories(p,rng)[0])];post['gold'],post['stolenGold']=pair
                    hard['jointGoldDaggerViolation']+=pair not in posts
                    hard['illegalHp']+=not 1<=ending<=maximum;hard['illegalGold']+=not 0<=pair[0]<=32767
                    hard['illegalPotionCount']+=post['potionCount']!=sum(p>1 for p in post['potions'])
                    post['oocContinuationRng']=dict(miscRng=c.native_rng.replay_misc(pre['combatRng'][2],name),potionRng=copy.deepcopy(pre['combatRng'][4]))
                    hard['invalidRng']+=not all(c.rng_valid(v) for v in post['oocContinuationRng'].values())
                    hard['writhingStructureViolation']+=index in locals_by_global['writhing'] and native.writhing_target(pre,post)!=writh_event
                    allowed={'maxHp','curHp','potions','potionCount','relics','gold','stolenGold','deck','cardTypeCounts','transformableCount'}
                    hard['otherPersistentMutation']+=any(post[k]!=pre[k] for k in c.base.PERSISTENT_KEYS if k not in allowed)
                    events+=1
            print('sparse complete validity',draw+1,flush=True)
    hard['downstreamAfterDeath']=int(events+sampled_deaths!=32*len(ids))
    result=dict(evaluationSha=sha,classification='SPARSE_COMBINED_HARD_VALIDITY_PASS' if not any(hard.values()) else 'SPARSE_COMBINED_HARD_VALIDITY_FAIL',testRows=len(ids),draws=32*len(ids),survivingSparseCalls=events,sampledDeaths=sampled_deaths,hardValidity=dict(hard),upstreamCalls=dict(counts),
                componentHashes=bindings,goldHash=goldmeta['artifactSha256'],maxHpHash=refitmeta['artifactSha256'],supportChanged=False,scope='consumption-only Stage-2 candidates; Brew/Smoke overlaps deferred to Stages3/4')
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-parent',type=Path,required=True);p.add_argument('--evaluation-sha',required=True);a=p.parse_args();run(a.run_parent,a.evaluation_sha)
