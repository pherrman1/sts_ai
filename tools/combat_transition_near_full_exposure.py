#!/usr/bin/env python3
"""Frozen whole-union component exposure; original TEST is development evidence."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_near_full_evaluate as q
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_potion_trajectory as t


def teacher_traces(cache,ambiguous,index):
    options=ambiguous.get(index)
    if options is None:options={int(cache['traces'][index]):1.}
    else:options={int(i):float(options[i]) for i in np.flatnonzero(options>0)}
    return [(dict(initialMask=code&31,consumed=[p for bit,p in enumerate(t.EFFECT_IDS) if (code>>5)&(1<<bit)],outcome='ESCAPE' if cache['escaped'][index] else 'VICTORY'),weight) for code,weight in options.items()]


def escape_hp(head,m,z,delta,pre,maximum,bit):
    return head.probabilities(z,delta,pre,maximum,bit,m.classes)


def evaluate(parent,output,sha,limit=None,downstream="full-union-downstream-v1",maxhp="full-union-maxHP-v1",cohort="all",final_support=False,escape=None):
    """escape: an escape fit checkpoint (tools/ctm_escape.py). Each draw then samples the
    escape before HP and conditions HP and the potion trajectory on it."""
    requested_cohort=cohort
    q.sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,ambiguous,records,meta,allrows,allids,test,snapshot=q.load(parent,final_support);torch.set_num_threads(4);m,nets,bindings=q.networks(parent,downstream,maxhp)
    eligible=test['win'].copy()
    if cohort=='smoke':eligible&=np.any(test['potions']==t.SMOKE,-1)
    selected=np.flatnonzero(eligible)
    if limit is not None:selected=selected[:limit]
    rows=[allrows[i] for i in selected];ids=allids[selected];test=q.subset(test,selected);n=len(rows)
    survival,pd=q.upstream(m,parent,ids,test);rng=np.random.default_rng(q.RECIPE['seed'])
    head=None
    if escape is not None:
        from tools import ctm_escape
        head=ctm_escape.TorchEscape.load(escape,m.device)
        eligible_rows=np.asarray([ctm_escape.eligible(r['pre']['potions'],r['pre']['potionCapacity'],bool(b)) for r,b in zip(rows,test['boss'])])
        p_escape=np.where(eligible_rows,head.probability(test['z']),0.)
        observed_bit=(test['escaped'].astype(bool)&eligible_rows).astype(np.int64)
    teacher=np.ones((n,6));mixture=np.zeros((n,6));brew_frequency=np.zeros(n);escape_frequency=np.zeros(n);hp_expected=np.zeros(n)
    targets=test['trueHp']-test['preHp']-c.CLASSES[0]
    if head is None:exact,_=e.exact_hp_target_probabilities(m,test['z'],pd,test['preHp'],test['preMax'],targets)
    else:
        exact=np.zeros(n)
        for d in range(len(m.delta_values)):
            for bit,weight in ((0,1-p_escape),(1,p_escape)):
                for start in range(0,n,512):
                    sub=np.arange(start,min(start+512,n))
                    hp=escape_hp(head,m,test['z'][sub],np.full(len(sub),d),test['preHp'][sub],test['preMax'][sub]+m.delta_values[d],np.full(len(sub),bit))
                    exact[sub]+=pd[sub,d]*weight[sub]*hp[np.arange(len(sub)),targets[sub]]
    mixture[:,0]=exact
    with torch.inference_mode():
        for start in range(0,n,512):
            sub=np.arange(start,min(start+512,n))
            if head is None:hp=e.hp_prob(m,test['z'][sub],test['delta'][sub],test['preHp'][sub],test['trueMax'][sub])
            else:hp=escape_hp(head,m,test['z'][sub],test['delta'][sub],test['preHp'][sub],test['trueMax'][sub],observed_bit[sub])
            teacher[sub,0]=hp[np.arange(len(sub)),targets[sub]]
            teacher[sub,1]=(-q.te.losses(m.potion_net,cache,graphs,ids[sub],z=test['potionZ'][sub])).exp().cpu().numpy()
            owners=[];traces=[];weights=[]
            for i in sub:
                for trace,weight in teacher_traces(cache,ambiguous,int(ids[i])):owners.append(i);traces.append(trace);weights.append(weight)
            own=np.asarray(owners);tmp=q.subset(test,own);particle=q.heads(nets,test['z'][own],[rows[i] for i in own],test['trueHp'][own],test['trueMax'][own],traces,rng,tmp,teacher=True)
            teacher[sub,2:]=0.
            np.add.at(teacher[:,2:],own,np.asarray(weights)[:,None]*particle['target'])
        for draw in range(q.RECIPE['draws']):
            for start in range(0,n,512):
                sub=np.arange(start,min(start+512,n));delta=q.pick(pd[sub],rng);maximum=test['preMax'][sub]+m.delta_values[delta];rr=[rows[i] for i in sub];bit=None
                if head is None:hp=e.hp_prob(m,test['z'][sub],delta,test['preHp'][sub],maximum)
                else:
                    bit=(rng.random(len(sub))<p_escape[sub]).astype(np.int64)
                    hp=escape_hp(head,m,test['z'][sub],delta,test['preHp'][sub],maximum,bit)
                ending=test['preHp'][sub]+c.CLASSES[q.pick(hp,rng)]
                if head is None:mixture[sub,1]+=(-q.te.losses(m.potion_net,cache,graphs,ids[sub],delta=delta,hp=ending/maximum,z=test['potionZ'][sub])).exp().cpu().numpy()/q.RECIPE['draws']
                else:mixture[sub,1]+=t.batch_target_log_probabilities(m.potion_net,q.te.row_graphs(cache,graphs,ids[sub]),test['potionZ'][sub],cache['capacity'][ids[sub]],delta,ending/maximum,cache['boss'][ids[sub]],False,bit).exp().cpu().numpy()/q.RECIPE['draws']
                traces=q.s.sample_potions_batch(m.potion_net,test['potionZ'][sub],[r['pre'] for r in rr],delta,ending/maximum,rng,test['boss'][sub],bit);particle=q.heads(nets,test['z'][sub],rr,ending,maximum,traces,rng,q.subset(test,sub));mixture[sub,2:]+=particle['target']/q.RECIPE['draws']
                brew_frequency[sub]+=np.asarray([tr['brewUses']>0 for tr in traces])/q.RECIPE['draws'];escape_frequency[sub]+=np.asarray([tr['outcome']=='ESCAPE' for tr in traces])/q.RECIPE['draws'];hp_expected[sub]+=ending/q.RECIPE['draws']
            print('whole final union exposure',draw+1,flush=True)
    teacher_nll=e.nll(teacher);mixture_nll=e.nll(mixture);gap=mixture_nll-teacher_nll
    groups=test['observed'].sum(-1).clip(min=1);teacher_nll[:,2]/=groups;mixture_nll[:,2]/=groups;gap[:,2]/=groups
    recursive_ids={int(r['index']) for r in json.loads((parent/'brew-native-label-audit-v1.json').read_text())['recursiveExamples']}
    cohorts=dict(entireFinalUnion=np.ones(n,bool),previous179=test['old'],recovered=~test['old'],brew=np.any(test['potions']==t.BREW,-1),smoke=np.any(test['potions']==t.SMOKE,-1),writhing=test['writhing'],ritual=test['dagger'],gold=np.asarray([int(i) in records for i in ids]),recursiveBrew=np.isin(ids,list(recursive_ids)),escape=test['escaped'])
    transplus=c.base._CARD_IDS['TRANSMUTATION'];cohorts['transmutationPlus']=np.asarray([any(card['cardId']==transplus and card['upgraded'] for card in r['pi']['cards']) for r in rows])
    names=('hp','potion','relic','writhing','ritual','gold');components={};passes=[]
    for j,name in enumerate(names):
        active=np.ones(n,bool)
        if name=='relic':active=test['observed'].any(-1)
        if name=='writhing':active=test['writhing']
        if name=='ritual':active=test['dagger']
        if name=='gold':active=cohorts['gold']
        component={}
        for cohort,mask in cohorts.items():
            chosen=mask&active
            if not chosen.any():continue
            gate=bool(np.isfinite(gap[chosen,j]).all() and gap[chosen,j].mean()<=q.RECIPE['threshold']);diagnostic=(not final_support) and cohort in ('recursiveBrew','transmutationPlus')
            component[cohort]=dict(rows=int(chosen.sum()),teacherNll=float(teacher_nll[chosen,j].mean()),mixtureNll=float(mixture_nll[chosen,j].mean()),exposure=e.source_gap_bootstrap(test['source'][chosen],gap[chosen,j]),zeroExactMassRows=int((mixture[chosen,j]<=0).sum()),gate=gate,diagnosticOnly=diagnostic)
            if not diagnostic:passes.append(gate)
        components[name]=component
    def binary_metric(p,y):return dict(rows=len(y),brier=float(np.mean((p-y)**2)),probabilityResolution=1/q.RECIPE['draws'],zeroFrequencyRows=int((p==0).sum()),scope='ancestral Monte Carlo diagnostic, not exact finite target-mass gate')
    brew_target=np.asarray([i in graphs and graphs[i].rounds>0 for i in ids]);metrics=dict(conditionalBrewUse=binary_metric(brew_frequency,brew_target),conditionalEscape=binary_metric(escape_frequency,test['escaped']),sampledHpMeanAbsoluteError=float(np.mean(abs(hp_expected-test['trueHp']))))
    np.savez_compressed(output.with_suffix('.npz'),ids=ids,source=test['source'],teacherNll=teacher_nll,mixtureNll=mixture_nll,exposureGap=gap,brewFrequency=brew_frequency,escapeFrequency=escape_frequency)
    if head is not None:
        metrics['escapeHead']=dict(eligibleRows=int(eligible_rows.sum()),**{k:v for k,v in binary_metric(p_escape[eligible_rows],observed_bit[eligible_rows]).items() if k in ('rows','brier')},
                                   nll=float(-np.mean(np.log(np.where(observed_bit[eligible_rows]==1,p_escape[eligible_rows],1-p_escape[eligible_rows]).clip(1e-12)))),
                                   unrepresentableEscapes=int((test['escaped'].astype(bool)&~eligible_rows).sum()))
        bindings=dict(bindings,escapeCheckpoint=c.base.sha256(escape))
    result=dict(finalSupport=final_support,sourceSha=sha,downstreamFolder=downstream,maxHpFolder=maxhp,cohort=requested_cohort,recipe=q.RECIPE,bindings=bindings,snapshot=snapshot,components=components,metrics=metrics,rows=n,classification=('FULL_UNION' if requested_cohort=='all' and limit is None else 'SLICE')+'_EXPOSURE_DEVELOPMENT_'+('PASS' if all(passes) else 'FAIL'),supportChanged=False,independentHoldout=False,rowEvidenceSha256=c.base.sha256(output.with_suffix('.npz')))
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--limit',type=int);p.add_argument('--downstream',default='full-union-downstream-v1');p.add_argument('--maxhp',default='full-union-maxHP-v1');p.add_argument('--cohort',choices=['all','smoke'],default='all');p.add_argument('--final-support',action='store_true');p.add_argument('--escape',type=Path,help='escape fit checkpoint (tools/ctm_escape.py)');a=p.parse_args();evaluate(a.parent,a.output,a.source_sha,a.limit,a.downstream,a.maxhp,a.cohort,a.final_support,a.escape)
