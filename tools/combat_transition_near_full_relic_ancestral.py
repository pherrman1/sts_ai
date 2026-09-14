#!/usr/bin/env python3
"""Relic head repair with fixed ancestral context noise, original corpus only."""
import argparse,copy,json,shutil
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_near_full_downstream as d,combat_transition_near_full_sampler as s
from tools import combat_transition_near_full_relic_refit as r
from tools import combat_transition_potion_trajectory as t
from tools import combat_transition_sparse_evaluate as sparse

RECIPE=dict(seed=20260912,contextSeed=20260923,contexts=2,epochs=12,batch=512,lr=.001,weightDecay=.0001,clip=1.,selection='earliest strict minimum original VALIDATION teacher/ancestral-context partial-target NLL',loss='0.5 exact teacher-context NLL +0.25 each of two fixed ancestral-context NLLs',population='all informative final-union original TRAIN survivors',scope='existing relic decoder only; retain HP, potion-mask and explicit escape inputs',evidence='engineering repair following original reused TEST exposure failure; not untouched confirmation')


def partial(net,cache,ids,signed,fraction,mask,escaped):
    device=next(net.parameters()).device
    def tensor(x):return torch.as_tensor(x,device=device)
    outputs=net(tensor(cache['z'][ids]),tensor(signed),tensor(np.asarray(fraction,np.float32)),tensor(mask),tensor(np.asarray(escaped,np.float32)));lp=torch.zeros(len(ids),device=device)
    for j,name in enumerate(c.TRAINED_GROUPS):
        value=torch.logsumexp(torch.log_softmax(outputs[name],-1).masked_fill(~tensor(cache['compatible_'+name][ids]),-torch.inf),-1);lp+=value*tensor(cache['observed'][ids,j])
    return -lp/tensor(cache['observed'][ids].sum(-1).clip(min=1).astype(np.float32))


def teacher(net,cache,ambiguous,ids):
    owners=[];masks=[];weights=[]
    for owner,i in enumerate(ids):
        options=ambiguous.get(int(i));options={int(cache['traces'][i]):1.} if options is None else {int(k):float(options[k]) for k in np.flatnonzero(options>0)}
        for code,weight in options.items():owners.append(owner);masks.append(code&31);weights.append(weight)
    owner=np.asarray(owners);rows=ids[owner];loss=partial(net,cache,rows,cache['trueHp'][rows]-cache['preHp'][rows]-c.CLASSES[0],cache['trueHp'][rows]/cache['trueMax'][rows],np.asarray(masks),cache['escaped'][rows]);count=cache['observed'][rows].sum(-1).clip(min=1);device=loss.device
    mass=torch.zeros(len(ids),device=device).index_add(0,torch.as_tensor(owner,device=device),torch.as_tensor(np.asarray(weights,np.float32),device=device)*(-loss*torch.as_tensor(count,device=device)).exp());return -mass.log()/torch.as_tensor(cache['observed'][ids].sum(-1).clip(min=1),device=device)


def fit(parent,output,sha,balanced=False,reuse=None):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    warm=parent/('full-union-downstream-v3' if balanced else 'full-union-downstream-v1');receipt=json.loads((warm/'fit.json').read_text());artifact=warm/'downstream.pt'
    if c.base.sha256(artifact)!=receipt['artifactSha256']:raise ValueError('warm artifact differs')
    cache,ambiguous,records,meta=d.load(parent,warm);m,bindings=d.load_upstream(parent);arrays,spec=c.base._load_prepared(e.PREPARED);c.base._prepare_target_indices(arrays,spec);torch.set_num_threads(4);torch.manual_seed(RECIPE['seed']);nets=d.models(parent).cuda().eval().requires_grad_(False);nets.load_state_dict(torch.load(artifact,map_location='cuda',weights_only=False)['stateDict']);net=nets['relic'].requires_grad_(True)
    ids=np.flatnonzero(cache['win']&cache['observed'].any(-1));conditions={key:np.zeros((2,len(cache['ids'])),dtype) for key,dtype in [('signed',np.int64),('fraction',np.float32),('mask',np.int64),('escaped',bool)]};rng=np.random.default_rng(RECIPE['contextSeed'])
    if reuse is not None:
        ref=json.loads((reuse/'fit.json').read_text());path=reuse/'ancestral_contexts.npz'
        if c.base.sha256(path)!=ref['contextsSha256'] or ref['upstreamBindings']!=bindings:raise ValueError('fixed ancestral context binding differs')
        with np.load(path) as raw:conditions={key:raw[key] for key in ('signed','fraction','mask','escaped')}
    else:
        with torch.inference_mode():
            for start in range(0,len(ids),512):
                sub=ids[start:start+512];inputs=c.base._torch_inputs(arrays,cache['ids'][sub],'cuda',torch,trim_padding=True);pd=e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder,inputs)));pres=[]
                for i in sub:
                    if i in records:pres.append(records[i]['pre'])
                    else:
                        if t.BREW in cache['potions'][i]:raise ValueError('missing actual Brew pre-state')
                        pres.append(dict(potions=cache['potions'][i].tolist(),potionCapacity=int(cache['capacity'][i]),relics=[],combatRng=[dict(counter=0,seed0=1,seed1=2)]*6))
                for k in range(2):
                    delta=e.draw_categories(pd,rng);maximum=cache['preMax'][sub]+m.delta_values[delta];hp=e.hp_prob(m,cache['z'][sub],delta,cache['preHp'][sub],maximum);ending=cache['preHp'][sub]+c.CLASSES[e.draw_categories(hp,rng)];traces=s.sample_potions_batch(m.potion_net,cache['potionZ'][sub],pres,delta,ending/maximum,rng,cache['boss'][sub]);conditions['signed'][k,sub]=ending-cache['preHp'][sub]-c.CLASSES[0];conditions['fraction'][k,sub]=ending/maximum;conditions['mask'][k,sub]=[v['initialMask'] for v in traces];conditions['escaped'][k,sub]=[v['outcome']=='ESCAPE' for v in traces]
    train=ids[cache['split'][ids]==0];val=ids[cache['split'][ids]==1];test=ids[cache['split'][ids]==2];opt=torch.optim.AdamW(net.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay']);rng=np.random.default_rng(RECIPE['seed']);best=float('inf');history=[]
    route=np.any(np.isin(cache['potions'],[t.BREW,t.SMOKE]),-1)
    importance=np.ones(len(cache['ids']),np.float32)
    if balanced:
        for partition in (train,val,test):
            special=route[partition];importance[partition]=.5+.5*len(partition)/max(1,int(special.sum()))*special
    def losses(ids):return .5*teacher(net,cache,ambiguous,ids)+sum(.25*partial(net,cache,ids,*(conditions[key][k,ids] for key in ('signed','fraction','mask','escaped'))) for k in range(2))
    def score(ids,teacher_only=False):
        net.eval()
        with torch.inference_mode():return float(torch.cat([(teacher(net,cache,ambiguous,ids[s:s+512]) if teacher_only else losses(ids[s:s+512])*torch.as_tensor(importance[ids[s:s+512]],device='cuda')) for s in range(0,len(ids),512)]).mean())
    original=score(val)
    for epoch in range(1,RECIPE['epochs']+1):
        net.train();order=rng.permutation(train)
        for start in range(0,len(order),512):
            sub=order[start:start+512];opt.zero_grad();loss=(losses(sub)*torch.as_tensor(importance[sub],device='cuda')).mean()
            if not torch.isfinite(loss):raise ValueError('nonfinite ancestral-context relic loss')
            loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),RECIPE['clip']);opt.step()
        nll=score(val);history.append(dict(epoch=epoch,validationContextNll=nll));print(json.dumps(history[-1]),flush=True)
        if nll<best:best=nll;selected=epoch;state=copy.deepcopy(net.state_dict())
    net.load_state_dict(state);test_context=score(test);test_teacher=score(test,True);output.mkdir()
    for name in ('preparation.json','cache.npz','ambiguous_traces.npz','affected_rows.jsonl'):shutil.copyfile(warm/name,output/name)
    np.savez_compressed(output/'ancestral_contexts.npz',**conditions)
    payload=torch.load(artifact,map_location='cpu',weights_only=False);new=nets.cpu().state_dict()
    if any(not torch.equal(value,new[key]) for key,value in payload['stateDict'].items() if not key.startswith('relic.')):raise ValueError('unrelated learned component changed')
    payload['stateDict']=new;payload['relicRepair']=RECIPE;torch.save(payload,output/'downstream.pt')
    result=dict(sourceSha=sha,balancedNativeRoutes=balanced,balance='equal mixture of full union and pre-Brew/Smoke native trajectory routes' if balanced else 'ordinary corpus weights',reusedContexts=str(reuse) if reuse is not None else None,preparation=meta,recipe=RECIPE,upstreamBindings=bindings,warmArtifactSha256=receipt['artifactSha256'],artifactSha256=c.base.sha256(output/'downstream.pt'),history=history,selectedEpoch=selected,originalValidationContextNll=original,validationContextNll=best,testContextNll=test_context,testRelicNll=test_teacher,trainRows=len(train),validationRows=len(val),testRows=len(test),unrelatedHeadsBitIdentical=True,contextsSha256=c.base.sha256(output/'ancestral_contexts.npz'),supportChanged=False)
    c.base.json_dump(output/'fit.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--balanced',action='store_true');p.add_argument('--reuse-contexts',type=Path);a=p.parse_args();fit(a.parent,a.output,a.source_sha,a.balanced,a.reuse_contexts)
