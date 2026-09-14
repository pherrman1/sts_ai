#!/usr/bin/env python3
"""Source-bound quality of the complete final union, without gameplay."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_near_full_evaluate as q
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e


def categorical_metrics(p,target,values):
    target=np.asarray(target,np.int64);values=np.asarray(values);mass=p[np.arange(len(p)),target]
    brier=(p*p).sum(-1)-2*mass+1
    crps=(((p.cumsum(-1)[:,:-1]-(values[target,None]<=values[None,:-1]))**2)*np.diff(values)).sum(-1)
    mae=abs(p@values-values[target])
    return dict(nll=e.nll(mass),brier=brier,crps=crps,meanAbsoluteError=mae)


def evaluate(parent,output,sha,downstream="full-union-downstream-v1",maxhp="full-union-maxHP-v1"):
    q.sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,ambiguous,records,meta,rows,ids,test,snapshot=q.load(parent);torch.set_num_threads(4);m,nets,bindings=q.networks(parent,downstream,maxhp);survival,pd=q.upstream(m,parent,ids,test)
    win=test['win'];alive=np.flatnonzero(win);probability=np.zeros((len(alive),len(c.CLASSES)))
    with torch.inference_mode():
        for delta in range(len(m.delta_values)):
            for start in range(0,len(alive),512):
                own=np.arange(start,min(start+512,len(alive)));sub=alive[own];p=e.hp_prob(m,test['z'][sub],np.full(len(sub),delta),test['preHp'][sub],test['preMax'][sub]+m.delta_values[delta]);probability[own]+=pd[sub,delta,None]*p
    hp_target=test['trueHp'][alive]-test['preHp'][alive]-c.CLASSES[0];hp=categorical_metrics(probability,hp_target,c.CLASSES);maximum=categorical_metrics(pd[alive],test['delta'][alive],m.delta_values)
    if not np.allclose(probability.sum(-1),1,atol=1e-6):raise ValueError('HP exact marginal normalization')
    sm=dict(nll=e.nll(np.where(win,survival,1-survival)),brier=(survival-win)**2)
    selected=dict(entireFinalUnion=np.ones(len(rows),bool),previous179=test['old'],recovered=~test['old'],brew=np.any(test['potions']==q.t.BREW,-1),smoke=np.any(test['potions']==q.t.SMOKE,-1),writhing=np.asarray([r['pi']['globals']['encounter']==c.base.WRITHING_MASS_ID for r in rows]),ritual=np.asarray([any(card['id']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in r['pre']['deck']) for r in rows]),escape=test['escaped'])
    metrics={}
    for name,mask in selected.items():
        if not mask.any():continue
        survived=mask[alive];metrics[name]=dict(rows=int(mask.sum()),survivingRows=int(survived.sum()),survival={k:float(v[mask].mean()) for k,v in sm.items()})
        if survived.any():
            metrics[name]['hpExactMaxHpMarginal']={k:float(v[survived].mean()) for k,v in hp.items()};metrics[name]['maxHp']={k:float(v[survived].mean()) for k,v in maximum.items()}
    generated=[int(i) for i in ids[alive] if i in graphs and graphs[i].rounds>0]
    native_identity=dict(rows=len(generated),generationRounds=sum(graphs[i].rounds for i in generated),jointBodyNll=float(np.mean([-graphs[i].generation_log_prior for i in generated])),mechanism='exact native rarity/rejection law; learned use/retention likelihood reported separately',rngOrigin='planner-owned native hypothetical origin; historical origin used for teacher labels only')
    np.savez_compressed(output.with_suffix('.npz'),ids=ids,survival=survival,maxHp=pd,hpIds=ids[alive],hpTarget=hp_target,**{'hp_'+k:v for k,v in hp.items()})
    result=dict(sourceSha=sha,bindings=bindings,snapshot=snapshot,metrics=metrics,generatedPotionIdentity=native_identity,rowsSha256=c.base.sha256(output.with_suffix('.npz')),supportChanged=False,scope='original grouped TEST development quality; no independent holdout or gameplay')
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--downstream',default='full-union-downstream-v1');p.add_argument('--maxhp',default='full-union-maxHP-v1');a=p.parse_args();evaluate(a.parent,a.output,a.source_sha,a.downstream,a.maxhp)
