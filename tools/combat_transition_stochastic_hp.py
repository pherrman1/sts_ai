#!/usr/bin/env python3
"""Frozen categorical signed-HP experiment; external artifacts, no runtime integration."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from tools import combat_transition_hp_targets as hp
from tools import combat_transition_surrogate as base
from tools import ctm_pins as _pins

ROOT = hp.ROOT
CONTROL_HASH = _pins.value('combat_transition_stochastic_hp.CONTROL_HASH', '22b285413bb31caac4dfe23dba79e80437ec91a42ed2ae534105370db6bca184')
RECIPE = dict(schema='stochastic_signed_hp_v1', seeds=hp.RECIPE['seeds'], epochs=10,
              batch=2048, lr=1e-3, weightDecay=1e-4, clip=1., precision='amp-fp16',
              initialScale=16384, encoder='AttentionEncoder:64/2/4/128', deltaEmbedding=8,
              head='72/64/K ReLU', loss='masked categorical NLL',
              conditioning='observed max-HP delta class', bootstrapReps=1000,
              bootstrapSeed=20260914, samplingSeed=20260915, samplesPerRow=16,
              intervals='equal-tailed inclusive integer quantiles',
              meanComparator='raw continuous #170 reconstructed delta point',
              crpsComparator='floor(postHP+0.5), native clamp [1,postMaxHP]',
              decision='CRPS CI below zero and mean MAE CI not above zero; either above rejects')


def freeze_domain(pre, pre_max, max_delta_values, supported):
    """Only predictor-visible HP and the upstream frozen class domain enter here."""
    p, m = np.asarray(pre)[supported], np.asarray(pre_max)[supported]
    d = np.asarray(max_delta_values)
    if not len(p) or not len(d) or any(not np.all(np.isfinite(v)) or not np.all(v == np.floor(v)) for v in (p,m,d)):
        raise ValueError('noninteger or empty state envelope')
    if np.any(p < 1) or np.any(p > m):
        raise ValueError('invalid supported pre HP')
    low, high = int(1-p.max()), int(np.max(m-p)+d.max())
    provenance = dict(min=low, max=high, classes=high-low+1,
                      envelope='all globally supported pre-combat states',
                      preCurHpRange=[int(p.min()),int(p.max())],
                      preMaxHpRange=[int(m.min()),int(m.max())],
                      maxHpDeltaValues=d.tolist(), rule='[min(1-preCurHp),max(preMaxHp-preCurHp)+max(deltaMaxHp)]')
    provenance['sha256'] = hashlib.sha256(json.dumps(provenance,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return np.arange(low,high+1,dtype=np.int64), provenance


def legal_support(classes, pre, maximum):
    post = np.asarray(pre)[:,None]+np.asarray(classes)[None,:]
    legal = (post >= 1) & (post <= np.asarray(maximum)[:,None])
    if np.any(~legal.any(1)):
        raise ValueError('empty legal support')
    return legal


def check_targets(classes, pre, maximum, post):
    legal = legal_support(classes,pre,maximum)
    target = np.asarray(post)-np.asarray(pre)
    index = target-classes[0]
    if np.any(index != np.floor(index)) or np.any(index < 0) or np.any(index >= len(classes)):
        raise ValueError('winning target outside frozen domain')
    index = index.astype(np.int64)
    if not np.all(legal[np.arange(len(index)),index]):
        raise ValueError('illegal winning target')
    return index


def new_model(torch, mean, std, delta_count, classes, seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    class HpNet(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = hp.attention.AttentionEncoder(torch,mean,std).net
            self.delta_embedding = torch.nn.Embedding(delta_count,8)
            self.hp = torch.nn.Sequential(torch.nn.Linear(72,64),torch.nn.ReLU(),torch.nn.Linear(64,len(classes)))
            self.register_buffer('classes',torch.as_tensor(classes,dtype=torch.long))

        def forward(self, inputs, delta, pre, maximum):
            logits = self.hp(torch.cat((self.encoder(*inputs),self.delta_embedding(delta)),-1)).float()
            post = pre[:,None]+self.classes[None,:]
            legal = (post >= 1) & (post <= maximum[:,None])
            if not bool(legal.any(1).all()):
                raise ValueError('empty legal support')
            return logits.masked_fill(~legal,float('-inf'))
    return HpNet()


def row_scores(prob, classes, pre, maximum, actual, nll):
    prob = np.asarray(prob,dtype=np.float64)
    if np.any(prob < 0) or not np.all(np.isfinite(prob)) or not np.allclose(prob.sum(1),1,atol=1e-6):
        raise ValueError('invalid categorical probabilities')
    legal = legal_support(classes,pre,maximum)
    if np.any(prob[~legal] != 0):
        raise ValueError('unsupported class probability')
    cdf = prob.cumsum(1)
    truth = (classes[None,:] >= (actual-pre)[:,None]).astype(float)
    # Integer unit-spaced CRPS; last class is excluded (both CDFs end at one).
    crps = np.sum((cdf[:,:-1]-truth[:,:-1])**2,axis=1)
    expected = pre+prob@classes
    mode = pre+classes[prob.argmax(1)]
    rows = dict(nll=nll,crps=crps,expectedMae=np.abs(expected-actual),
                expectedSquaredError=(expected-actual)**2,modeMae=np.abs(mode-actual),
                modeExact=(mode==actual).astype(float))
    for level in (.5,.8,.95):
        alpha=(1-level)/2
        lower=classes[np.argmax(cdf>=alpha,axis=1)]+pre
        upper=classes[np.argmax(cdf>=1-alpha,axis=1)]+pre
        rows[f'coverage{int(level*100)}']=((actual>=lower)&(actual<=upper)).astype(float)
        rows[f'width{int(level*100)}']=upper-lower
    return rows


def summarize(rows, mask=None):
    selected = {k:np.asarray(v) if mask is None else np.asarray(v)[mask] for k,v in rows.items()}
    n=len(selected['nll'])
    if not n:
        return dict(rows=0)
    result=dict(rows=n,**{k:float(v.mean()) for k,v in selected.items() if k!='expectedSquaredError'})
    result['expectedRmse']=float(np.sqrt(selected['expectedSquaredError'].mean()))
    return result


def sample_hp(prob, classes, pre, maximum, rng, draws=16):
    legal=legal_support(classes,pre,maximum)
    if np.any(prob[~legal] != 0) or not np.allclose(prob.sum(1),1,atol=1e-6):
        raise ValueError('invalid sampling distribution')
    cdf=np.asarray(prob,dtype=np.float64).cumsum(1)
    # Use normalized CDF to eliminate numerical tail gaps, without clipping HP.
    cdf/=cdf[:,-1:]
    uniforms=rng.random((len(pre),draws))
    indices=np.empty(uniforms.shape,dtype=np.int64)
    for i in range(len(pre)):
        indices[i]=np.searchsorted(cdf[i],uniforms[i],side='right')
    post=pre[:,None]+classes[indices]
    return post, post/maximum[:,None]


def classify(crps_ci, mae_ci):
    if crps_ci[0]>0 or mae_ci[0]>0:
        return 'STOCHASTIC_DELTA_HP_REJECTED'
    if crps_ci[1]<0 and mae_ci[0]<=0:
        return 'STOCHASTIC_DELTA_HP_QUALIFIED'
    return 'STOCHASTIC_DELTA_HP_INCONCLUSIVE'


def load(args):
    arrays,train,holdout,pre,post,maximum,delta,_,_,metadata=hp.load(Path(args.prepared_dir))
    if (len(train),len(holdout)) != (286581,32345):
        raise ValueError('frozen victory counts differ')
    classes,domain=freeze_domain(pre,arrays['preMaxHp'],metadata['deltaValues'],arrays['supported'])
    winners=np.flatnonzero(arrays['supported'] & (arrays['y_win']==1))
    target=np.zeros(len(pre),dtype=np.int64)
    target[winners]=check_targets(classes,pre[winners],maximum[winners],post[winners])
    control_path=Path(args.control_dir)/'predictions.npz'
    if base.sha256(control_path)!=CONTROL_HASH:
        raise ValueError('point controls hash differs')
    with np.load(control_path) as raw:
        if not np.array_equal(raw['rowIds'],holdout) or not np.array_equal(raw['sourceSeed'],arrays['sourceSeed'][holdout]):
            raise ValueError('point controls row alignment differs')
        controls={s:raw[f'{s}-delta'].copy() for s in RECIPE['seeds']}
    metadata.pop('normalization')
    metadata.update(domain=domain,controlPredictionsSha256=CONTROL_HASH,
                    structuralWinningRows=len(winners),allWinningTargetsRepresentable=True)
    return arrays,train,holdout,pre,post,maximum,delta,target,classes,metadata,controls


def run(args):
    output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    arrays,train,holdout,pre,post,maximum,delta,target,classes,metadata,controls=load(args)
    recipe=dict(RECIPE,baselineSha=args.baseline_sha)
    if args.command=='prepare':
        for name,value in [('recipe.json',recipe),('preflight.json',metadata)]:
            if (output/name).exists():
                raise ValueError('refusing to overwrite preflight')
            base.json_dump(output/name,value)
        print(json.dumps({k:v for k,v in metadata.items() if k not in ('trainSources','holdoutSources')}),flush=True)
        return
    current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if current!=args.reviewed_sha or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('fit requires clean reviewed SHA')
    if json.loads((output/'recipe.json').read_text())!=recipe or json.loads((output/'preflight.json').read_text())!=metadata:
        raise ValueError('preflight changed')
    if list(output.glob('*.pt')) or (output/'results.json').exists():
        raise ValueError('refusing to overwrite fit')
    import torch
    if not torch.cuda.is_available():
        raise ValueError('frozen AMP protocol requires CUDA')
    torch.set_num_threads(4)
    torch.backends.mha.set_fastpath_enabled(False)
    mean=arrays['globals_continuous'][train].mean(0)
    std=arrays['globals_continuous'][train].std(0)
    def forward(model,ids):
        return model(base._torch_inputs(arrays,ids,'cuda',torch,trim_padding=True),
                     torch.as_tensor(delta[ids],device='cuda',dtype=torch.long),
                     torch.as_tensor(pre[ids],device='cuda'),torch.as_tensor(maximum[ids],device='cuda'))
    audits=[]
    # Complete every fit before computing HOLDOUT predictions or metrics.
    for seed in RECIPE['seeds']:
        started=time.monotonic()
        model=new_model(torch,mean,std,len(metadata['deltaValues']),classes,seed).cuda()
        initial=hp.state_hash(model)
        optimizer=torch.optim.AdamW(model.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay'])
        scaler=torch.amp.GradScaler('cuda',init_scale=RECIPE['initialScale'])
        rng=np.random.default_rng(seed)
        batch_hash,condition_hash=hashlib.sha256(),hashlib.sha256()
        history=[]
        for epoch in range(RECIPE['epochs']):
            model.train()
            total=0.
            for ids in base._batches(train,RECIPE['batch'],rng):
                batch_hash.update(ids.tobytes()); condition_hash.update(delta[ids].tobytes())
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast('cuda',dtype=torch.float16):
                    loss=torch.nn.functional.cross_entropy(forward(model,ids),torch.as_tensor(target[ids],device='cuda',dtype=torch.long))
                if not torch.isfinite(loss):
                    raise ValueError('nonfinite loss')
                scaler.scale(loss).backward(); scaler.unscale_(optimizer)
                norm=torch.nn.utils.clip_grad_norm_(model.parameters(),RECIPE['clip'])
                if not torch.isfinite(norm):
                    raise ValueError('nonfinite gradient; fixed recipe aborted')
                scaler.step(optimizer); scaler.update()
                total+=float(loss.detach())*len(ids)
            history.append(total/len(train))
            print(json.dumps(dict(seed=seed,epoch=epoch+1,nll=history[-1],seconds=time.monotonic()-started)),flush=True)
        audit=dict(seed=seed,initialization=initial,batches=batch_hash.hexdigest(),conditioning=condition_hash.hexdigest(),trainNll=history)
        audits.append(audit)
        torch.save(dict(state_dict=base._safe_state_dict(model),metadata=metadata,recipe=recipe,reviewedSha=current,seed=seed,audit=audit),output/f'{seed}.pt')
        del model,optimizer
        torch.cuda.empty_cache()
    predictions=dict(rowIds=holdout,sourceSeed=arrays['sourceSeed'][holdout],classes=classes)
    metrics,crps_diffs,mae_diffs={},{},{}
    masks=hp.slices(arrays,holdout,pre,post)
    for seed in RECIPE['seeds']:
        model=new_model(torch,mean,std,len(metadata['deltaValues']),classes,seed).cuda()
        checkpoint=torch.load(output/f'{seed}.pt',map_location='cpu',weights_only=False)
        model.load_state_dict(checkpoint['state_dict']); model.eval()
        probs,nlls=[],[]
        with torch.no_grad():
            for start in range(0,len(holdout),RECIPE['batch']):
                ids=holdout[start:start+RECIPE['batch']]
                with torch.autocast('cuda',dtype=torch.float16):
                    logprob=torch.log_softmax(forward(model,ids),-1)
                probs.append(logprob.exp().cpu().numpy())
                nlls.append((-logprob[torch.arange(len(ids),device='cuda'),torch.as_tensor(target[ids],device='cuda')]).cpu().numpy())
        prob=np.concatenate(probs); nll=np.concatenate(nlls)
        p,m,a=pre[holdout],maximum[holdout],post[holdout]
        rows=row_scores(prob,classes,p,m,a,nll)
        sampled,fraction=sample_hp(prob,classes,p,m,np.random.default_rng(RECIPE['samplingSeed']+seed),RECIPE['samplesPerRow'])
        validity=dict(draws=sampled.size,belowOne=int(np.sum(sampled<1)),aboveMax=int(np.sum(sampled>m[:,None])),
                      unsupportedProbability=float(np.max(np.where(legal_support(classes,p,m),0,prob))),
                      derivedFractionConsistent=bool(np.array_equal(fraction,sampled/m[:,None])))
        if validity['belowOne'] or validity['aboveMax'] or validity['unsupportedProbability']:
            raise ValueError('sampling validity failed')
        point=controls[seed]
        operational=np.clip(np.floor(point+.5),1,m)
        crps_diffs[seed]=rows['crps']-np.abs(operational-a)
        mae_diffs[seed]=rows['expectedMae']-np.abs(point-a)
        metrics[str(seed)]=dict(overall=summarize(rows),slices={name:summarize(rows,mask) for name,mask in masks.items()},
                               samplingValidity=validity,control=dict(crps=float(np.abs(operational-a).mean()),mae=float(np.abs(point-a).mean())),
                               pairedCrpsDifference=float(crps_diffs[seed].mean()),pairedMeanMaeDifference=float(mae_diffs[seed].mean()))
        predictions[f'{seed}-probabilities']=prob; predictions[f'{seed}-nll']=nll
        predictions[f'{seed}-samples']=sampled.astype(np.int32)
        del model
        torch.cuda.empty_cache()
    crps=hp.bootstrap(arrays['sourceSeed'][holdout],np.stack(list(crps_diffs.values())).mean(0))
    mae=hp.bootstrap(arrays['sourceSeed'][holdout],np.stack(list(mae_diffs.values())).mean(0))
    np.savez_compressed(output/'predictions.npz',**predictions)
    results=dict(reviewedSha=current,recipe=recipe,provenance=metadata,trainingAudits=audits,metrics=metrics,
                 crpsBootstrap=crps,meanMaeBootstrap=mae,classification=classify(crps['ci95'],mae['ci95']))
    base.json_dump(output/'results.json',results)
    base.json_dump(output/'artifact-hashes.json',{p.name:base.sha256(p) for p in output.iterdir() if p.is_file() and p.suffix!='.log' and p.name!='artifact-hashes.json'})
    print(json.dumps(dict(classification=results['classification'],crps=crps,meanMae=mae)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','fit'])
    parser.add_argument('--prepared-dir',required=True)
    parser.add_argument('--control-dir',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--baseline-sha',required=True)
    parser.add_argument('--reviewed-sha')
    run(parser.parse_args())
