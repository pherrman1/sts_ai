#!/usr/bin/env python3
"""Exact finite Writhing exposure; Brew/Smoke overlap retains full-trajectory evidence."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_near_full_evaluate as q
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_potion_trajectory as t


def evaluate(parent,output,sha,downstream):
    q.sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,ambiguous,records,meta,rows,ids,test,snapshot=q.load(parent);torch.set_num_threads(4);m,nets,bindings=q.networks(parent,downstream)
    take=np.flatnonzero(test['win']&test['writhing']&~np.any(np.isin(test['potions'],[t.BREW,t.SMOKE]),-1));rows=[rows[i] for i in take];ids=ids[take];test=q.subset(test,take);_,pd=q.upstream(m,parent,ids,test);mixture=np.zeros(len(ids));teacher=np.zeros(len(ids))
    device='cuda'
    def tensor(v):return torch.as_tensor(v,device=device)
    with torch.inference_mode():
        for row,r in enumerate(rows):
            pre,pi=r['pre'],r['pi'];z=test['z'][row];pz=test['potionZ'][row];actual=int(test['writhingTarget'][row]);native_candidates=np.asarray([[[0,0,0]],[[1,0,1]]],np.float32)
            masks=np.flatnonzero(t.legal_actions(pre['potions'],pre['potionCapacity'],False));assert np.all(masks<32)
            conditions=[q.s.conditions(pre,pi,pre['curHp'],pre['maxHp'],int(k),[p for slot,p in enumerate(pre['potions']) if k&(1<<slot)],False) for k in masks];bits=np.asarray([v[1] for v in conditions]);features=np.asarray([v[3] for v in conditions]);om=features[0,0]>0;native_candidates[1,0,1:]=[int(om),int(not om)]
            for delta in range(len(m.delta_values)):
                maximum=pre['maxHp']+int(m.delta_values[delta]);hp=e.hp_prob(m,z[None],np.asarray([delta]),np.asarray([pre['curHp']]),np.asarray([maximum]))[0];classes=np.flatnonzero(hp>0);ending=pre['curHp']+c.CLASSES[classes];fraction=ending/maximum
                lp=t.log_probabilities(m.potion_net,np.broadcast_to(pz,(len(classes),64)).copy(),np.broadcast_to(pre['potions'],(len(classes),5)).copy(),np.full(len(classes),pre['potionCapacity']),np.full(len(classes),delta),fraction,np.zeros(len(classes),bool));potions=lp.exp().cpu().numpy()[:,masks]
                owners=np.repeat(np.arange(len(classes)),len(masks));hps=np.stack(((ending[owners]-pre['curHp'])/160,fraction[owners],np.full(len(owners),(maximum-pre['maxHp'])/10)),-1).astype(np.float32);legal=np.ones((len(owners),2),bool)
                if features[0,1] and not om and maximum-pre['maxHp']<6:legal[:,1]=False
                probability=nets['writhing'](tensor(np.broadcast_to(z,(len(owners),64)).copy()),tensor(hps),tensor(np.tile(bits,(len(classes),1))),tensor(np.tile(features,(len(classes),1))),tensor(np.broadcast_to(native_candidates,(len(owners),2,1,3)).copy()),tensor(legal)).exp().cpu().numpy()[:,actual].reshape(len(classes),len(masks))
                mixture[row]+=pd[row,delta]*np.sum(hp[classes,None]*potions*probability)
            code=int(cache['traces'][ids[row]]);mask=code&31;used=[p for bit,p in enumerate(t.EFFECT_IDS) if (code>>5)&(1<<bit)]
            hpcond,bitcond,_,feat=q.s.conditions(pre,pi,int(test['trueHp'][row]),int(test['trueMax'][row]),mask,used,False);legal=np.ones(2,bool)
            if feat[1] and not om and test['trueMax'][row]-pre['maxHp']<6:legal[1]=False
            teacher[row]=q.s.event_probabilities(nets['writhing'],z,hpcond,bitcond,feat,native_candidates,legal)[actual]
            if (row+1)%50==0:print('exact Writhing',row+1,len(ids),flush=True)
    gap=e.nll(mixture)-e.nll(teacher);ritual=test['dagger'];slices={}
    for name,chosen in dict(writhingNoSpecial=np.ones(len(ids),bool),writhingRitual=ritual).items():
        slices[name]=dict(rows=int(chosen.sum()),teacherNll=float(e.nll(teacher[chosen]).mean()),mixtureNll=float(e.nll(mixture[chosen]).mean()),exposure=e.source_gap_bootstrap(test['source'][chosen],gap[chosen]),zeroExactMassRows=int((mixture[chosen]<=0).sum()),gate=bool(np.isfinite(gap[chosen]).all() and gap[chosen].mean()<=.1))
    np.savez_compressed(output.with_suffix('.npz'),ids=ids,source=test['source'],teacherNll=e.nll(teacher),mixtureNll=e.nll(mixture),gap=gap)
    result=dict(sourceSha=sha,bindings=bindings,slices=slices,partition='original TEST reused engineering development',protocol='exact all eleven maxHP classes, all legal signed HP and initial ordinary potion actions; special Brew/Smoke rows separately retain full trajectory composition',supportChanged=False,rowsSha256=c.base.sha256(output.with_suffix('.npz')))
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--downstream',required=True);a=p.parse_args();evaluate(a.parent,a.output,a.source_sha,a.downstream)
