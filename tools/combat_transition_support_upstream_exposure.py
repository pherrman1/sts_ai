#!/usr/bin/env python3
"""Bound affected-component exposure after the native sparse maxHP repair."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c, combat_transition_composed_evaluate as e
from tools import combat_transition_sparse_evaluate as s, combat_transition_gold_evaluate as g


def run(folder,refit,sha,gold=False):
    s.frozen(sha)
    output=folder/'upstream_encoder_refit_exposure.json'
    if output.exists():raise ValueError('refusing overwrite')
    meta=json.loads((folder/('preflight.json' if gold else 'preparation.json')).read_text())
    hashes=e.verify_data()
    if hashes!=meta['hashes'] or c.base.sha256(folder/'cache.npz')!=meta['cacheSha256']:raise ValueError('cache provenance differs')
    with np.load(folder/'cache.npz') as raw:cache={k:raw[k] for k in raw.files}
    if gold:
        for old,new in [('preMaxHp','preMax'),('trueMaxHp','trueMax'),('prePotions','potions'),('trueMask','mask')]:cache[new]=cache[old]
        records=[dict(local=r['local'],pre=r['pre'],post=r['post'],pi=r['predictorInput']) for r in map(json.loads,(folder/'test_rows.jsonl').read_text().splitlines())]
    else:records=json.loads((folder/'test_rows.json').read_text())
    records=[r for r in records if cache['win'][r['local']]]
    ids=np.asarray([r['local'] for r in records]);n=len(ids)
    if not np.all(cache['split'][ids]==2):raise ValueError('original TEST membership differs')
    refit_meta=json.loads((refit/'fit.json').read_text())
    if hashes!=refit_meta['hashes'] or c.base.sha256(refit/'maxhp-head.pt')!=refit_meta['artifactSha256']:raise ValueError('refit provenance differs')
    torch.set_num_threads(4);m=c.FrozenModels('cuda');payload=torch.load(refit/'maxhp-head.pt',map_location='cpu',weights_only=False)
    m.max_net.max_hp_delta.load_state_dict(payload['stateDict'])
    m.max_net.encoder.load_state_dict(payload['encoderStateDict'])
    arrays,_=c.base._load_prepared(e.PREPARED)
    delta=np.asarray([np.flatnonzero(m.delta_values==v)[0] for v in cache['trueMax'][ids]-cache['preMax'][ids]])
    cls=cache['trueHp'][ids]-cache['preHp'][ids]-c.CLASSES[0]
    compatible={group:np.ones((n,k),bool) for group,k in c.relic.HEAD_CLASSES.items() if group in c.TRAINED_GROUPS}
    observed=np.zeros(n,np.int64)
    om=c.base._RELIC_IDS['OMAMORI'];bloom=c.base._RELIC_IDS['MARK_OF_THE_BLOOM']
    for i,r in enumerate(records):
        # Omamori in Writhing is covered by the new exact native event head.
        pre=[x for x in r['pre']['relics'] if x['id']!=om];post=[x for x in r['post']['relics'] if x['id']!=om]
        for group,values in c.relic.trajectory_constraints(pre,post,r['pi']['globals']['encounter'],any(x['id']==bloom for x in pre)).items():
            if group not in compatible:raise ValueError('unqualified mutable relic')
            compatible[group][i]=np.isin(np.arange(c.relic.HEAD_CLASSES[group]),list(values));observed[i]+=1
    pdelta=np.zeros((n,len(m.delta_values)));pz=np.zeros((n,64),np.float32)
    teacher={k:np.zeros(n) for k in ('hp','potion','relic')};mass={k:np.zeros((32,n)) for k in ('potion','relic')}
    if gold:
        fitted=json.loads((folder/'fit.json').read_text())
        if c.base.sha256(folder/'gold.pt')!=fitted['artifactSha256']:raise ValueError('gold checkpoint differs')
        net=c.gold.new_decoder(torch).cuda().eval().requires_grad_(False)
        net.load_state_dict(torch.load(folder/'gold.pt',weights_only=False,map_location='cpu')['stateDict'])
        teacher['gold']=np.zeros(n);mass['gold']=np.zeros((32,n))
    with torch.inference_mode():
        for start in range(0,n,512):
            sl=slice(start,min(start+512,n));sub=ids[sl];inputs=c.base._torch_inputs(arrays,cache['ids'][sub],'cuda',torch,trim_padding=True)
            pdelta[sl]=e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)))
            pz[sl]=m.fp32_encoding(m.potion_encoder.encoder,inputs).cpu().numpy()
            hp=e.hp_prob(m,cache['z'][sub],delta[sl],cache['preHp'][sub],cache['trueMax'][sub])
            teacher['hp'][sl]=e.nll(hp[np.arange(len(sub)),cls[sl]])
            pp=e.potion_prob(m,pz[sl],cache['potions'][sub],cache['capacity'][sub],delta[sl],cache['trueHp'][sub]/cache['trueMax'][sub])
            teacher['potion'][sl]=e.nll(pp[np.arange(len(sub)),cache['mask'][sub]])
            rp=e.relic_prob(m,cache['z'][sub],cls[sl],cache['trueHp'][sub]/cache['trueMax'][sub],cache['mask'][sub])
            teacher['relic'][sl]=e.nll(e.constraint_probability(rp,{k:v[sl] for k,v in compatible.items()}))
            if gold:teacher['gold'][sl]=e.nll(g.target_probability(net,cache,sub,cache['mask'][sub],cache['trueHp'][sub],cache['trueMax'][sub]))
        hp_mass,_=e.exact_hp_target_probabilities(m,cache['z'][ids],pdelta,cache['preHp'][ids],cache['preMax'][ids],cls)
        rng=np.random.default_rng(20260920)
        for draw in range(32):
            for start in range(0,n,512):
                sl=slice(start,min(start+512,n));sub=ids[sl];d=e.draw_categories(pdelta[sl],rng);maximum=cache['preMax'][sub]+m.delta_values[d]
                hp=e.hp_prob(m,cache['z'][sub],d,cache['preHp'][sub],maximum);hcls=e.draw_categories(hp,rng);ending=cache['preHp'][sub]+c.CLASSES[hcls]
                pp=e.potion_prob(m,pz[sl],cache['potions'][sub],cache['capacity'][sub],d,ending/maximum)
                mass['potion'][draw,sl]=pp[np.arange(len(sub)),cache['mask'][sub]]
                for mask in range(32):
                    active=pp[:,mask]>0
                    if not active.any():continue
                    rp=e.relic_prob(m,cache['z'][sub[active]],hcls[active],ending[active]/maximum[active],np.full(active.sum(),mask,np.int64))
                    positions=np.flatnonzero(active)+start
                    mass['relic'][draw,positions]+=pp[active,mask]*e.constraint_probability(rp,{k:v[sl][active] for k,v in compatible.items()})
                    if gold:mass['gold'][draw,positions]+=pp[active,mask]*g.target_probability(net,cache,sub[active],np.full(active.sum(),mask,np.int64),ending[active],maximum[active])
            print('upstream exposure',folder.name,draw+1,32,flush=True)
    loss={k:e.nll(v.mean(0)) for k,v in mass.items()};loss['hp']=e.nll(hp_mass)
    results={};gaps={}
    for k in teacher:
        gap=loss[k]-teacher[k]
        informative=observed>0 if k=='relic' else np.ones(n,bool)
        if k=='relic':gap=np.divide(gap,observed,out=np.zeros(n),where=observed>0)
        gaps[k]=gap
        results[k]=dict(rows=int(informative.sum()),teacherNll=float(teacher[k][informative].mean()),mixtureNll=float(loss[k][informative].mean()),exposure=e.source_gap_bootstrap(cache['source'][ids][informative],gap[informative]))
    gate=all(np.isfinite(v).all() and v.mean()<=.1 for v in gaps.values())
    result=dict(evaluationSha=sha,classification='AFFECTED_UPSTREAM_EXPOSURE_PASS' if gate else 'AFFECTED_UPSTREAM_EXPOSURE_FAIL',gate=bool(gate),mechanism='gold' if gold else meta['mechanism'],results=results,maxHpRefit=refit_meta,hashes=hashes,supportChanged=False,
                estimator='exact maxHP marginal for HP; 32 maxHP/HP draws and exact conditional potion-mask marginal for downstream components')
    np.savez_compressed(output.with_suffix('.npz'),ids=cache['ids'][ids],source=cache['source'][ids],**{k+'Gap':v for k,v in gaps.items()})
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--maxhp-refit',type=Path,required=True);p.add_argument('--evaluation-sha',required=True);p.add_argument('--gold',action='store_true');a=p.parse_args();run(a.output_dir,a.maxhp_refit,a.evaluation_sha,a.gold)
