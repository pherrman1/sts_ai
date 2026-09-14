#!/usr/bin/env python3
"""Exact finite maxHP/HP/potion marginal; never interprets empirical zeros as support."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_sparse_evaluate as s


def run(folder,sha,maxhp_refit=None):
    s.frozen(sha)
    suffix='encoder_refit' if maxhp_refit and json.loads((maxhp_refit/'fit.json').read_text()).get('encoderChanged') else 'refit'
    output=folder/('exact_exposure_'+suffix+'.json' if maxhp_refit else 'exact_exposure.json')
    if output.exists():raise ValueError('refusing overwrite')
    meta=json.loads((folder/'preparation.json').read_text());fit=json.loads((folder/'fit.json').read_text())
    if e.verify_data()!=meta['hashes'] or c.base.sha256(folder/'cache.npz')!=meta['cacheSha256'] or c.base.sha256(folder/'event.pt')!=fit['artifactSha256']:raise ValueError('frozen inputs differ')
    with np.load(folder/'cache.npz') as raw:cache={k:raw[k] for k in raw.files}
    payload=torch.load(folder/'event.pt',weights_only=False,map_location='cpu')
    if payload['metadata']!=meta:raise ValueError('checkpoint differs')
    torch.set_num_threads(4);model=s.net().cuda().eval().requires_grad_(False);model.load_state_dict(payload['stateDict']);m=c.FrozenModels('cuda')
    refit_binding=None
    if maxhp_refit:
        refit_binding=json.loads((maxhp_refit/'fit.json').read_text())
        if refit_binding['hashes']!=meta['hashes'] or c.base.sha256(maxhp_refit/'maxhp-head.pt')!=refit_binding['artifactSha256']:raise ValueError('refit provenance differs')
        refit=torch.load(maxhp_refit/'maxhp-head.pt',weights_only=False,map_location='cpu')
        m.max_net.max_hp_delta.load_state_dict(refit['stateDict'],strict=True)
        if refit.get('encoderStateDict') is not None:m.max_net.encoder.load_state_dict(refit['encoderStateDict'],strict=True)
        arrays,_=c.base._load_prepared(e.PREPARED)
        with torch.inference_mode():
            for start in range(0,len(cache['ids']),512):
                sub=np.arange(start,min(start+512,len(cache['ids'])));inputs=c.base._torch_inputs(arrays,cache['ids'][sub],'cuda',torch,trim_padding=True)
                cache['pDelta'][sub]=e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)))
    test=np.flatnonzero(cache['win']&(cache['split']==2));teacher=np.empty(len(test));mixture=np.zeros(len(test))
    with torch.inference_mode():
        for start in range(0,len(test),16):
            ids=test[start:start+16];n=len(ids)
            tp=s.forward(model,cache,ids).exp().cpu().numpy();teacher[start:start+n]=e.nll(tp[np.arange(n),cache['target'][ids]])
            joint=np.zeros(n)
            for delta in range(len(m.delta_values)):
                maximum=cache['preMax'][ids]+m.delta_values[delta]
                hp=e.hp_prob(m,cache['z'][ids],np.full(n,delta,np.int64),cache['preHp'][ids],maximum)
                owner,cls=np.nonzero(hp>0);sub=ids[owner];ending=cache['preHp'][sub]+c.CLASSES[cls];maxima=maximum[owner]
                pp=e.potion_prob(m,cache['potionZ'][sub],cache['potions'][sub],cache['capacity'][sub],np.full(len(sub),delta,np.int64),ending/maxima)
                target=np.zeros(len(sub))
                for mask in range(32):
                    active=pp[:,mask]>0
                    if active.any():
                        p=s.forward(model,cache,sub[active],np.full(active.sum(),mask,np.int64),ending[active],maxima[active]).exp().cpu().numpy()
                        target[active]+=pp[active,mask]*p[np.arange(active.sum()),cache['target'][sub[active]]]
                conditional=np.bincount(owner,weights=hp[owner,cls]*target,minlength=n)
                joint+=cache['pDelta'][ids,delta]*conditional
            mixture[start:start+n]=joint
            if start%160==0:print('exact',meta['mechanism'],start,len(test),flush=True)
    loss=e.nll(mixture);gap=loss-teacher;gate=bool(np.isfinite(gap).all() and gap.mean()<=.1)
    result=dict(evaluationSha=sha,modelSourceSha=meta['sourceSha'],mechanism=meta['mechanism'],classification='EXACT_SPARSE_EXPOSURE_PASS' if gate else 'EXACT_SPARSE_EXPOSURE_FAIL',
                eventExposureGate=gate,estimator='exact weighted marginal over all maxHP classes, legal HP classes and legal potion masks',
                rows=len(test),teacherNll=float(teacher.mean()),mixtureNll=float(loss.mean()),exposure=e.source_gap_bootstrap(cache['source'][test],gap),zeroMixtureProbabilityRows=int((mixture==0).sum()),
                artifactSha256=fit['artifactSha256'],maxHpRefit=refit_binding,supportChanged=False)
    np.savez_compressed(folder/('exact_exposure_'+suffix+'_rows.npz' if maxhp_refit else 'exact_exposure_rows.npz'),ids=cache['ids'][test],source=cache['source'][test],teacherNll=teacher,mixtureNll=loss,exposureGap=gap,targetMixtureProbability=mixture)
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--evaluation-sha',required=True);p.add_argument('--maxhp-refit',type=Path);a=p.parse_args();run(a.output_dir,a.evaluation_sha,a.maxhp_refit)
