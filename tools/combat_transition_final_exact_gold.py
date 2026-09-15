#!/usr/bin/env python3
"""Exact finite ancestral gold marginal for ordinary-potion MC-zero diagnostics.

This changes no sampler distribution, weight, support, or random draw. Preserve
original Monte Carlo zeros, replacing only their qualification estimate by the
full maxHP/HP/potion-mask/gold marginal. Recursive Brew requires another method.
"""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_near_full_models as models,combat_transition_near_full_sampler as s
from tools import combat_transition_near_full_exposure as exposure,combat_transition_near_full_evaluate as q
from tools import combat_transition_potion_trajectory as t,combat_transition_gold_proc_budget as budget


def exact(m,nets,row):
    pre,pi=row['pre'],row['pi']
    if any(p in (t.BREW,t.SMOKE) for p in pre['potions']) or any(card['id']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in pre['deck']):raise ValueError('MC-zero exact fallback requires ordinary inventory without Dagger')
    inputs=m.encode_visible(pi);z=m.hp_encoding(inputs).cpu().numpy();zp=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy();pd=m.max_hp(inputs);target=(row['post']['gold'],row['post']['stolenGold']);total=0.;normalization=0.
    masks=np.flatnonzero(t.legal_actions(pre['potions'],pre['potionCapacity'])[:32])
    for d,weight in enumerate(pd):
        maximum=pre['maxHp']+int(m.delta_values[d]);hp=m.hp_distribution(torch.as_tensor(z,device=m.device),d,pre['curHp'],maximum);hindex=np.flatnonzero(hp>0);ending=pre['curHp']+c.CLASSES[hindex];n=len(ending)
        lp=t.log_probabilities(m.potion_net,np.repeat(zp,n,0),np.tile(pre['potions'],(n,1)),np.full(n,pre['potionCapacity']),np.full(n,d),ending/maximum,np.zeros(n,bool)).exp().cpu().numpy();conditional=np.zeros(n)
        for mask in masks:
            _,consumed=t.consume(pre['potions'],int(mask));posts=budget.joint_gold_posts(pre,pi,int(mask),(),consumed,False)
            if target not in posts:continue
            if len(posts)==1:mass=np.ones(n)
            else:
                conditions=[s.conditions(pre,pi,int(h),maximum,int(mask),consumed,False) for h in ending];prob=s.batch_gold_probabilities(nets['gold'],np.repeat(z,n,0),np.asarray([v[0] for v in conditions]),np.asarray([v[1] for v in conditions]),np.asarray([v[2] for v in conditions]),[posts]*n,[pre['gold']]*n);mass=prob[:,posts.index(target)]
            conditional+=lp[:,mask]*mass
        total+=float(weight*np.dot(hp[hindex],conditional));normalization+=float(weight*hp.sum()*lp.sum(-1).mean())
    if not 0<total<=1 or abs(normalization-1)>1e-5:raise ValueError('exact marginal invalid')
    return total,normalization


def resolve(parent,original,output):
    if output.exists():raise ValueError('refusing overwrite')
    report=json.loads(original.read_text());
    if c.base.sha256(original.with_suffix('.npz'))!=report['rowEvidenceSha256']:raise ValueError('original exposure row evidence differs')
    z=np.load(original.with_suffix('.npz'));data={k:z[k].copy() for k in z.files};bad=np.flatnonzero(~np.isfinite(data['mixtureNll'][:,5]));ids=data['ids'];snapshot={r['index']:r for r in map(json.loads,(parent/'full-union-test-states-v1.jsonl').open())};torch.set_num_threads(4);m,nets,bindings=models.load(parent,'cpu');assert report['bindings']==bindings;corrections=[]
    with torch.inference_mode():
        for i in bad:
            mass,total=exact(m,nets,snapshot[int(ids[i])]);data['mixtureNll'][i,5]=-np.log(mass);data['exposureGap'][i,5]=data['mixtureNll'][i,5]-data['teacherNll'][i,5];corrections.append(dict(index=int(ids[i]),originalMonteCarloMass=0.,exactTargetMass=mass,ancestralNormalization=total))
    _,_,_,records,_,rows,allids,test,_=q.load(parent,True);alive=np.flatnonzero(test['win']);test=q.subset(test,alive);rows=[rows[i] for i in alive];assert np.array_equal(allids[alive],ids)
    recursive={int(r['index']) for r in json.loads((parent/'brew-native-label-audit-v1.json').read_text())['recursiveExamples']}
    cohorts=dict(entireFinalUnion=np.ones(len(ids),bool),previous179=test['old'],recovered=~test['old'],brew=np.any(test['potions']==t.BREW,-1),smoke=np.any(test['potions']==t.SMOKE,-1),writhing=test['writhing'],ritual=test['dagger'],gold=np.asarray([int(i) in records for i in ids]),recursiveBrew=np.isin(ids,list(recursive)),escape=test['escaped'],transmutationPlus=np.asarray([any(card['cardId']==c.base._CARD_IDS['TRANSMUTATION'] and card['upgraded'] for card in r['pi']['cards']) for r in rows]))
    for name,value in report['components']['gold'].items():
        selected=cohorts[name]&cohorts['gold'];gap=data['exposureGap'][selected,5];value.update(teacherNll=float(data['teacherNll'][selected,5].mean()),mixtureNll=float(data['mixtureNll'][selected,5].mean()),exposure=e.source_gap_bootstrap(test['source'][selected],gap),zeroExactMassRows=0,gate=bool(np.isfinite(gap).all() and gap.mean()<=.1))
    passed=all(value['gate'] and value['zeroExactMassRows']==0 for component in report['components'].values() for value in component.values());report.update(cohort='all',classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_'+('PASS' if passed else 'FAIL'),exactFiniteCorrections=corrections,originalExposureSha256=c.base.sha256(original),correctionSourceSha=e.snapshot(),independentHoldout=False)
    np.savez_compressed(output.with_suffix('.npz'),**data);report['rowEvidenceSha256']=c.base.sha256(output.with_suffix('.npz'));c.base.json_dump(output,report);print(json.dumps(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();resolve(a.parent,a.original,a.output)
