#!/usr/bin/env python3
"""Affected relic decoder repair after explicit-outcome composition exposure failure."""
import argparse,copy,json,shutil
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_near_full_downstream as d
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_sparse_evaluate as sparse

RECIPE=dict(seed=20260912,epochs=12,batch=512,lr=.001,weightDecay=.0001,clip=1.,selection='earliest strict minimum original VALIDATION relic partial-target NLL',scope='existing relic embeddings/shared layer/heads only; all informative final-union TRAIN survivors',repair='added explicit escape condition fixed to zero; preserve visible state, signed HP and potion-clear-mask conditions',evidence='development repair motivated by original reused TEST, not untouched confirmation')


def losses(net,cache,ambiguous,ids):
    owners=[];masks=[];weights=[]
    for owner,i in enumerate(ids):
        options=ambiguous.get(int(i))
        if options is None:options={int(cache['traces'][i]):1.}
        else:options={int(t):float(options[t]) for t in np.flatnonzero(options>0)}
        for code,weight in options.items():owners.append(owner);masks.append(code&31);weights.append(weight)
    owner=np.asarray(owners);rows=ids[owner];device=next(net.parameters()).device
    def tensor(x):return torch.as_tensor(x,device=device)
    output=net(tensor(cache['z'][rows]),tensor(cache['trueHp'][rows]-cache['preHp'][rows]-c.CLASSES[0]),tensor((cache['trueHp'][rows]/cache['trueMax'][rows]).astype(np.float32)),tensor(np.asarray(masks)),tensor(np.zeros(len(rows),np.float32)))
    lp=torch.zeros(len(rows),device=device)
    for j,name in enumerate(c.TRAINED_GROUPS):
        value=torch.logsumexp(torch.log_softmax(output[name],-1).masked_fill(~tensor(cache['compatible_'+name][rows]),-torch.inf),-1)
        lp+=value*tensor(cache['observed'][rows,j])
    mass=torch.zeros(len(ids),device=device).index_add(0,tensor(owner),tensor(np.asarray(weights,np.float32))*lp.exp())
    if not torch.isfinite(mass).all() or (mass<=0).any():raise ValueError('zero/nonfinite exact relic teacher target mass')
    return -mass.log()/tensor(cache['observed'][ids].sum(-1).clip(min=1).astype(np.float32))


def fit(parent,output,sha):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    warm=parent/'full-union-downstream-v1';receipt=json.loads((warm/'fit.json').read_text());artifact=warm/'downstream.pt'
    if c.base.sha256(artifact)!=receipt['artifactSha256']:raise ValueError('warm checkpoint differs')
    cache,ambiguous,records,meta=d.load(parent,warm);torch.set_num_threads(4);torch.manual_seed(RECIPE['seed']);nets=d.models(parent).cuda().requires_grad_(False);nets.load_state_dict(torch.load(artifact,map_location='cuda',weights_only=False)['stateDict']);net=nets['relic'].requires_grad_(True)
    with torch.no_grad():net.shared[0].weight[:,-1].zero_()
    active=cache['win']&cache['observed'].any(-1);train=np.flatnonzero(active&(cache['split']==0));val=np.flatnonzero(active&(cache['split']==1));test=np.flatnonzero(active&(cache['split']==2));opt=torch.optim.AdamW(net.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay']);rng=np.random.default_rng(RECIPE['seed']);best=float('inf');history=[]
    def score(ids):
        net.eval()
        with torch.inference_mode():return float(torch.cat([losses(net,cache,ambiguous,ids[s:s+512]) for s in range(0,len(ids),512)]).mean())
    original=score(val)
    for epoch in range(1,RECIPE['epochs']+1):
        net.train();order=rng.permutation(train)
        for start in range(0,len(order),512):
            sub=order[start:start+512];opt.zero_grad();loss=losses(net,cache,ambiguous,sub).mean();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),RECIPE['clip']);opt.step()
        nll=score(val);history.append(dict(epoch=epoch,validationRelicNll=nll));print(json.dumps(history[-1]),flush=True)
        if nll<best:best=nll;selected=epoch;state=copy.deepcopy(net.state_dict())
    net.load_state_dict(state)
    if torch.count_nonzero(net.shared[0].weight[:,-1]):raise ValueError('escape ablation coefficient changed')
    output.mkdir()
    for name in ('preparation.json','cache.npz','ambiguous_traces.npz','affected_rows.jsonl'):shutil.copyfile(warm/name,output/name)
    payload=torch.load(artifact,map_location='cpu',weights_only=False);payload['stateDict']=nets.cpu().state_dict();payload['relicRepair']=RECIPE;torch.save(payload,output/'downstream.pt')
    result=dict(sourceSha=sha,preparation=meta,recipe=RECIPE,warmArtifactSha256=receipt['artifactSha256'],artifactSha256=c.base.sha256(output/'downstream.pt'),history=history,selectedEpoch=selected,originalValidationRelicNll=original,validationRelicNll=best,testRelicNll=score(test),trainRows=len(train),validationRows=len(val),testRows=len(test),supportChanged=False,classification='AFFECTED_RELIC_REFIT_COMPLETE_PENDING_COMPOSITION')
    c.base.json_dump(output/'fit.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args();fit(a.parent,a.output,a.source_sha)
