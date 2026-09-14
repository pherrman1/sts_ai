#!/usr/bin/env python3
"""Affected maxHP head refit after exact Writhing exposure degradation."""
import argparse
import copy
import json
from pathlib import Path
import time
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_gold_evaluate as gold
from tools import combat_transition_sparse_evaluate as sparse

RECIPE=dict(seed=20260912,epochs=12,batch=512,lr=.001,weightDecay=.0001,
            refit='existing maxHP linear head only; historical encoder frozen',selection='earliest strict minimum original VALIDATION NLL',
            population='historical prepared supported rows plus gold-only and Stage-2 consumption-only candidates')


def run(folder,sha):
    sparse.frozen(sha)
    if folder.exists():raise ValueError('refusing overwrite')
    hashes=e.verify_data();arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec)
    parent=Path('/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914')
    gc,gm=gold.load_cache(parent/'shared-gold-v1')
    eligible=arrays['supported'].copy();eligible[gc['ids']]=True;bindings={'gold':gm['cacheSha256']}
    for mechanism in ('writhing','ritual'):
        run=parent/(mechanism+'-v1');meta=json.loads((run/'preparation.json').read_text())
        if c.base.sha256(run/'cache.npz')!=meta['cacheSha256'] or meta['hashes']!=hashes:raise ValueError('candidate binding differs')
        with np.load(run/'cache.npz') as raw:eligible[raw['ids']]=True
        bindings[mechanism]=meta['cacheSha256']
    ids=np.flatnonzero(eligible&(arrays['y_win']==1))
    if np.any(arrays['delta_index'][ids]<0):raise ValueError('new maxHP target outside frozen class domain')
    torch.set_num_threads(4);m=c.FrozenModels('cuda');z=np.empty((len(ids),64),np.float32)
    with torch.inference_mode():
        for start in range(0,len(ids),512):
            sub=ids[start:start+512];inputs=c.base._torch_inputs(arrays,sub,'cuda',torch,trim_padding=True)
            z[start:start+len(sub)]=m.fp32_encoding(m.max_net.encoder,inputs).cpu().numpy()
            if start%51200==0:print('refit frozen maxHP encoding',start,len(ids),flush=True)
    splits=arrays['split_id'][ids];target=arrays['delta_index'][ids]
    train=np.flatnonzero(splits==0);val=np.flatnonzero(splits==1);test=np.flatnonzero(splits==2)
    torch.manual_seed(RECIPE['seed']);head=copy.deepcopy(m.max_net.max_hp_delta).requires_grad_(True)
    opt=torch.optim.AdamW(head.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay']);rng=np.random.default_rng(RECIPE['seed']);history=[];best=float('inf')
    def losses(sub):return torch.nn.functional.cross_entropy(head(torch.as_tensor(z[sub],device='cuda')),torch.as_tensor(target[sub],device='cuda',dtype=torch.long),reduction='none')
    with torch.inference_mode():original=float(torch.cat([losses(val[s:s+512]) for s in range(0,len(val),512)]).mean())
    for epoch in range(RECIPE['epochs']):
        head.train();order=rng.permutation(train)
        for start in range(0,len(order),512):
            sub=order[start:start+512];opt.zero_grad();loss=losses(sub).mean();loss.backward();torch.nn.utils.clip_grad_norm_(head.parameters(),1);opt.step()
        head.eval()
        with torch.inference_mode():score=float(torch.cat([losses(val[s:s+512]) for s in range(0,len(val),512)]).mean())
        history.append(dict(epoch=epoch+1,validationNll=score));print(json.dumps(history[-1]),flush=True)
        if score<best:best=score;selected=epoch+1;state=copy.deepcopy(head.state_dict())
    head.load_state_dict(state)
    with torch.inference_mode():test_nll=float(torch.cat([losses(test[s:s+512]) for s in range(0,len(test),512)]).mean())
    folder.mkdir(parents=True)
    meta=dict(sourceSha=sha,recipe=RECIPE,hashes=hashes,candidateCacheBindings=bindings,
              trainRows=len(train),validationRows=len(val),testRows=len(test),selectedEpoch=selected,originalValidationNll=original,history=history,testNll=test_nll,
              encoderChanged=False,otherHeadsChanged=False,supportChanged=False)
    torch.save(dict(stateDict=state,metadata=meta),folder/'maxhp-head.pt');meta['artifactSha256']=c.base.sha256(folder/'maxhp-head.pt')
    c.base.json_dump(folder/'fit.json',meta);print(json.dumps(meta),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args();run(a.output_dir,a.source_sha)
