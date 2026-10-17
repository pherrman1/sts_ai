#!/usr/bin/env python3
"""§500 development-only weighting ablation on the frozen §498 feature cache.

No archive reader, encoder forward, TEST evaluation, or gameplay entry point.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np
import torch
from torch.nn import functional as F

import heart_outcome_value as value
from heart_outcome_collect import sha, write

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO/'docs/experiments/evidence/heart_outcome_weighting_20261017/PROTOCOL.md'
PARENT = {
    'pooled.pt':'a066eb69a74c16fc5e2d4e75b3c269937e269be1b82e5d2cbfb667cdbd442a25',
    'freeze.json':'b5d2e023ecb4c4ba8ff82c827c43a0aa4c5a11b5d5106d5bec79c0984d2b2a44',
    'result.json':'eeee2c1ace7382fa5fa3c4f51b4caeb6e08ea3d04bc54553d299e7f7e22c356c',
    'result-reviewed.json':'c3cc779e11a641b2e6b0e84137ccdd71309e2c28575062f99e5e9e5b42b9b669',
    'value-head.pt':'68c20b521b53a72896293b72442839eb5abfbb7c43222030556874b0a7593de1',
}
ARMS = ('source', 'visitation')
LANDMARKS = ('start', 'act1_floor8', 'act1_floor16')
CONSTANT = 126/1080
STEPS, EVERY, BATCH = 2000, 100, 512


def tensor_sha(state):
    h = hashlib.sha256()
    for key,t in sorted(state.items()):
        h.update(key.encode());h.update(t.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def inputs(args):
    value.require(all(sha(args.parent/k) == v for k,v in PARENT.items()), 'parent artifact changed')
    report = args.import_root/'audit/import-audit.json'
    review = args.import_root/'import-reviewed.json'
    manifest = args.import_root/'audit/train-validation-sources.jsonl'
    value.require([sha(p) for p in (report,review,manifest)] == [value.AUDIT,value.REVIEW,value.MANIFEST], 'development import changed')
    rows = [json.loads(s) for s in manifest.read_text().splitlines()]
    cache = torch.load(args.parent/'pooled.pt',map_location='cpu',weights_only=True)
    value.validate_cache(cache,rows)
    parent_review = json.loads((args.parent/'result-reviewed.json').read_text())
    value.require(parent_review['verdict'] == 'PASS' and parent_review['resultSha256'] == PARENT['result.json'], 'parent not approved')
    frozen_head = torch.load(args.parent/'value-head.pt',map_location='cpu',weights_only=True)
    value.require(frozen_head['encoderCheckpointSha256'] == value.CHECKPOINT, 'wrong original encoder')
    norm = {k:frozen_head['valueHead'][k] for k in ('mean','scale')}
    value.require(all(torch.isfinite(t).all().item() for t in norm.values()) and (norm['scale']>0).all().item(), 'invalid TRAIN normalization')
    # Reuse audited features only: no raw archive access, including consumed TEST.
    return cache,norm,{'parentRoot':str(args.parent.resolve()),'parent':PARENT,
        'importReportSha256':value.AUDIT,'importReviewSha256':value.REVIEW,'manifestSha256':value.MANIFEST,
        'normalizationTensorSha256':tensor_sha(norm),
        'policySha256':{k:v['policySha256'] for k,v in cache.items()}}


def identity(args):
    ident = value.identity(args)
    parent_ident = json.loads((args.parent/'freeze.json').read_text())['identity']
    for key in ident.keys()-{'sourceSha','tools'}:
        value.require(ident[key] == parent_ident[key], 'parent encoder/runtime changed: '+key)
    for p in (Path(__file__),REPO/'tests/test_heart_outcome_weighting.py',PROTOCOL):
        ident['tools'][str(p.relative_to(REPO))] = sha(p)
    return ident


def sampling_weights(meta,arm):
    value.require(arm in ARMS and len(meta)>0, 'invalid weighting arm')
    if arm == 'source':
        return value.source_weights([r['seed'] for r in meta])
    return np.full(len(meta),1/len(meta),dtype=np.float64)


def make_head(norm,init,device):
    torch.manual_seed(init)
    head = value.ValueHead(torch.zeros(1,64),torch.ones(1,dtype=torch.float64))
    with torch.no_grad():
        head.mean.copy_(norm['mean']);head.scale.copy_(norm['scale'])
        head.layers[-1].bias.fill_(math.log(CONSTANT/(1-CONSTANT)))
    return head.to(device)


def fit(x,y,vx,vy,norm,weights,init,deadline,steps=STEPS,every=EVERY):
    head = make_head(norm,init,x.device)
    initial = tensor_sha(head.state_dict())
    optimizer = torch.optim.AdamW(head.parameters(),lr=.001,weight_decay=.001)
    generator = torch.Generator(device='cpu').manual_seed(init)
    weights = torch.as_tensor(weights,dtype=torch.float64,device='cpu')
    value.require(len(weights)==len(x) and torch.isfinite(weights).all().item()
                  and (weights>0).all().item() and abs(weights.sum().item()-1)<1e-9, 'bad sampling weights')
    history,best = [],None
    for step in range(1,steps+1):
        value.require(time.monotonic()<deadline,'fitting wall cap')
        ids = torch.multinomial(weights,BATCH,replacement=True,generator=generator).to(x.device)
        optimizer.zero_grad(set_to_none=True)
        loss = F.binary_cross_entropy_with_logits(head(x[ids]),y[ids])
        value.require(torch.isfinite(loss).item(),'nonfinite fitting loss')
        loss.backward();optimizer.step()
        if step%every == 0 or step == steps:
            with torch.inference_mode():
                vl = F.binary_cross_entropy_with_logits(head(vx),vy,reduction='none').double().mean().item()
            value.require(math.isfinite(vl),'nonfinite validation loss')
            row = {'step':step,'validationVisitationBce':vl};history.append(row)
            if best is None or vl < best['validationVisitationBce']:
                best = {**row,'state':{k:v.detach().cpu().clone() for k,v in head.state_dict().items()}}
    value.require(all(torch.equal(head.state_dict()[k].cpu(),v) for k,v in norm.items()),'normalization changed')
    return best,history,initial


def landmark_indices(meta,kind):
    value.require(kind in LANDMARKS,'unknown landmark')
    chosen = {};threshold = {'act1_floor8':8,'act1_floor16':16}.get(kind)
    for i,r in enumerate(meta):
        eligible = r['index']==0 if kind=='start' else r['act']==1 and r['floor']>=threshold
        if eligible and r['seed'] not in chosen: chosen[r['seed']] = i
    return np.array([chosen[s] for s in sorted(chosen)],dtype=np.int64)


def interval(values,seed):
    values = np.asarray(values,dtype=np.float64)
    value.require(len(values)>0 and np.isfinite(values).all(),'empty/nonfinite bootstrap')
    rng = np.random.default_rng(seed);samples = []
    for _ in range(100):
        samples.append(values[rng.integers(0,len(values),size=(100,len(values)))].mean(1))
    return {'mean':values.mean(0).tolist(),'descriptive95':np.quantile(np.concatenate(samples),[.025,.975],axis=0).tolist()}


def diagnostics(meta,z):
    y = np.array([r['label'] for r in meta]);z = np.asarray(z,dtype=np.float64)
    p = torch.sigmoid(torch.from_numpy(z)).numpy()
    result = {'visitation':value.metric(y,p,np.ones(len(y)),z),
        'source':value.metric(y,p,value.source_weights([r['seed'] for r in meta]),z),'landmarks':{}}
    for n,kind in enumerate(LANDMARKS):
        ids = landmark_indices(meta,kind);ly,lp,lz = y[ids],p[ids],z[ids]
        value.require(len(ids)>0,'landmark empty')
        bias = interval(lp-ly,500+n)
        adequate = len(ids)>=100 and min(int(ly.sum()),int(len(ids)-ly.sum()))>=5
        if kind=='start': adequate = adequate and len(ids)==len({r['seed'] for r in meta})
        result['landmarks'][kind] = {'sources':len(ids),'wins':int(ly.sum()),'notReached':len({r['seed'] for r in meta})-len(ids),
            'model':value.metric(ly,lp,np.ones(len(ids)),lz),'bias':bias,'adequate':adequate,
            'meanBiasPass':bool(adequate and bias['descriptive95'][0]>=-.05 and bias['descriptive95'][1]<=.05)}
    return result


def compare(meta,control,treatment):
    y = np.array([r['label'] for r in meta]);seeds = np.array([r['seed'] for r in meta])
    c,t = (np.asarray(a,dtype=np.float64) for a in (control,treatment))
    cp,tp = (torch.sigmoid(torch.from_numpy(a)).numpy() for a in (c,t))
    delta = np.stack((np.logaddexp(0,t)-y*t-np.logaddexp(0,c)+y*c,(tp-y)**2-(cp-y)**2),axis=1)
    stats = np.array([[*delta[seeds==s].sum(0),np.sum(seeds==s)] for s in sorted(set(seeds))])
    rng = np.random.default_rng(500);ratios=[]
    for _ in range(100):
        sums = stats[rng.integers(0,len(stats),size=(100,len(stats)))].sum(1)
        ratios.append(sums[:,:2]/sums[:,2:])
    return {'metrics':['bce','brier'],'treatmentMinusControl':delta.mean(0).tolist(),
        'sourceClusterDescriptive95':np.quantile(np.concatenate(ratios),[.025,.975],axis=0).tolist(),
        'landmarkBiasChange':{kind:interval(tp[landmark_indices(meta,kind)]-cp[landmark_indices(meta,kind)],510+n)
            for n,kind in enumerate(LANDMARKS)}}


def selection_key(candidate):
    return (candidate['validationVisitationBce'],candidate['step'],candidate['init'])


def verdict(control,treatment):
    scores = all(treatment['visitation'][k]<control['visitation'][k] for k in ('bce','brier'))
    bias = all(abs(treatment['landmarks'][k]['bias']['mean'])<abs(control['landmarks'][k]['bias']['mean']) for k in LANDMARKS)
    return 'VALIDATION_WEIGHTING_SIGNAL' if scores and bias else 'VALIDATION_WEIGHTING_NOT_SHOWN'


def freeze(args):
    value.require(not value.git(REPO,'status','--porcelain'),'clean source required')
    ident = identity(args);_,_,custody = inputs(args)
    review = json.loads(args.review.read_text())
    value.require(review['verdict']=='PASS' and review['sourceSha']==ident['sourceSha']
        and review['toolSha256']==sha(Path(__file__)) and review['protocolSha256']==sha(PROTOCOL)
        and review['testAccessAuthorized'] is False,'exact source/design approval absent')
    args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/'freeze.json',{'schema':'heart-outcome-weighting-freeze-v1','identity':ident,'custody':custody,
        'reviewSha256':sha(args.review),'arms':list(ARMS),'initializations':[0,1],
        'steps':STEPS,'every':EVERY,'batch':BATCH,'selection':'common validation visitation BCE; step then init tie order',
        'maxSeconds':600,'testAccessAuthorized':False})


def run(args):
    frozen = json.loads((args.out/'freeze.json').read_text())
    value.require(frozen['identity']==identity(args) and frozen['reviewSha256']==sha(args.review),'frozen source/runtime/review changed')
    cache,norm,custody = inputs(args)
    value.require(frozen['custody']==custody and frozen['arms']==list(ARMS)
        and frozen['initializations']==[0,1] and (frozen['steps'],frozen['every'],frozen['batch'],frozen['maxSeconds'])==(STEPS,EVERY,BATCH,600)
        and frozen['testAccessAuthorized'] is False,'freeze changed')
    # Exclusive latch precedes any optimization; consumed output roots cannot resume.
    write(args.out/'fit-started.json',{'freezeSha256':sha(args.out/'freeze.json'),'pid':os.getpid()})
    start = time.monotonic();deadline = start+600
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    x,vx = (cache[k]['x'].cuda() for k in ('train','validation'))
    y,vy = (torch.tensor([r['label'] for r in cache[k]['meta']],device='cuda',dtype=torch.float32) for k in ('train','validation'))
    value.require(sum(r['label'] for r in {r['seed']:r for r in cache['train']['meta']}.values())==126,'TRAIN class rate changed')
    candidates=[];selected={};predictions={};paired_initial={}
    for arm in ARMS:
        weights = sampling_weights(cache['train']['meta'],arm)
        for init in frozen['initializations']:
            best,history,initial = fit(x,y,vx,vy,norm,weights,init,deadline)
            state = best.pop('state');path = args.out/f'{arm}-{init}.pt';torch.save(state,path)
            if init in paired_initial: value.require(paired_initial[init]==initial,'unmatched initialization')
            paired_initial[init]=initial
            record = {'arm':arm,'init':init,**best,'history':history,'sha256':sha(path),'initialTensorSha256':initial}
            candidates.append(record)
            if arm not in selected or selection_key(record)<selection_key(selected[arm]):
                selected[arm] = {k:v for k,v in record.items() if k!='history'}
            print(json.dumps({k:v for k,v in record.items() if k!='history'}),flush=True)
        chosen = selected[arm];state=torch.load(args.out/f"{arm}-{chosen['init']}.pt",weights_only=True)
        head=make_head(norm,0,'cuda');head.load_state_dict(state,strict=True);head.eval()
        value.require(sum(p.numel() for p in head.parameters())==4225,'architecture changed')
        with torch.inference_mode(): predictions[arm]={k:head(z).cpu() for k,z in (('train',x),('validation',vx))}
    value.require(time.monotonic()<deadline,'fitting wall cap')
    arms = {arm:{k:diagnostics(cache[k]['meta'],predictions[arm][k].numpy()) for k in ('train','validation')} for arm in ARMS}
    for arm in ARMS:
        value.require(abs(arms[arm]['validation']['visitation']['bce']-selected[arm]['validationVisitationBce'])<1e-6,'selection/report mismatch')
    torch.save(predictions,args.out/'predictions.pt')
    value.require(inputs(args)[2]==custody and identity(args)==frozen['identity'],'inputs/runtime changed during run')
    report={'schema':'heart-outcome-weighting-result-v1','verdict':verdict(arms['source']['validation'],arms['visitation']['validation']),
        'arms':arms,'selected':selected,'candidates':candidates,
        'pairedValidationComparison':compare(cache['validation']['meta'],predictions['source']['validation'].numpy(),predictions['visitation']['validation'].numpy()),
        'constant':{k:{'probability':CONSTANT,'visitation':value.metric([r['label'] for r in cache[k]['meta']],np.full(len(cache[k]['meta']),CONSTANT),np.ones(len(cache[k]['meta'])))} for k in cache},
        'seconds':time.monotonic()-start,'freezeSha256':sha(args.out/'freeze.json'),
        'predictionsSha256':sha(args.out/'predictions.pt'),'normalizationTensorSha256':tensor_sha(norm),
        'cachedEncoderOnly':True,'testRead':False,'nativeIntegration':False,'runtimePromotion':False,
        'generalizationQualified':False,'bootstrapSelectionAdjusted':False}
    value.require(time.monotonic()<deadline,'fitting/analytics wall cap')
    write(args.out/'result.json',report)
    print(json.dumps({'verdict':report['verdict'],'selected':selected,'comparison':report['pairedValidationComparison']}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('freeze','run'))
    for name in ('parent','import-root','checkpoint','silverbot','review','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try: freeze(args) if args.command=='freeze' else run(args)
    except Exception as exc:
        if args.out.is_dir() and not (args.out/'failure.json').exists():
            write(args.out/'failure.json',{'type':type(exc).__name__,'message':str(exc)})
        raise


if __name__=='__main__': main()
