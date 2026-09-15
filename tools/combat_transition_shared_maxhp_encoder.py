#!/usr/bin/env python3
"""Paired frozen HP-representation screen for the near-full maxHP head."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as composed_evaluate
from tools import combat_transition_near_full_refit as refit
from tools import combat_transition_potion_trajectory_evaluate as trajectory


RECIPE=dict(schema='shared_frozen_maxhp_encoder_screen_v1',seed=refit.RECIPE['seed'],epochs=refit.RECIPE['epochs'],
            batch=refit.RECIPE['batch'],lr=refit.RECIPE['headLr'],weightDecay=refit.RECIPE['weightDecay'],clip=refit.RECIPE['clip'],
            precision='cached FP32 representations; FP32 decoder fit',encoderArithmetic='FP32, MHA fastpath disabled identically for both arms',
            selection='independent earliest strict minimum VALIDATION maxHP-delta NLL',
            population='full-union original source-grouped TRAIN/VALIDATION victories',trained='fresh Linear(64,11) maxHP-delta head only',
            gates=dict(nllRelative=.01,accuracyDrop=.005,expectedPostMaxHpMaeDelta=.1),
            clearReject=dict(nllRelative=.012,accuracyDrop=.006,expectedPostMaxHpMaeDelta=.12))


def digest_array(value):return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def state_hash(module):
    digest=hashlib.sha256()
    for name,value in module.state_dict().items():digest.update(name.encode());digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def classify(reference,candidate):
    gates=dict(nllRelative=(candidate['nll']-reference['nll'])/reference['nll'],
               accuracyDrop=reference['accuracy']-candidate['accuracy'],
               expectedPostMaxHpMaeDelta=candidate['expectedPostMaxHpMae']-reference['expectedPostMaxHpMae'])
    passed=(gates['nllRelative']<=.01 and gates['accuracyDrop']<=.005 and gates['expectedPostMaxHpMaeDelta']<=.1)
    rejected=(gates['nllRelative']>.012 or gates['accuracyDrop']>.006 or gates['expectedPostMaxHpMaeDelta']>.12)
    return ('GO_TO_SHARED_HP_ENCODER_POTION_STAGE' if passed else ('SHARED_HP_ENCODER_MAXHP_REJECTED' if rejected else 'INCONCLUSIVE')),gates


def verify_component(folder,component,cache_meta):
    fit=json.loads((folder/'fit.json').read_text());path=folder/'component.pt';actual=c.base.sha256(path)
    if fit['component']!=component or fit['artifactSha256']!=actual:raise ValueError(f'{component} checkpoint binding differs')
    if fit['hashes']!=cache_meta['hashes'] or fit['preparationCacheSha256']!=cache_meta['cacheSha256']:raise ValueError(f'{component} source/cache differs')
    if 'original VALIDATION' not in fit['recipe']['selection'] or 'original source-grouped TRAIN' not in fit['recipe']['population']:
        raise ValueError(f'{component} is not a TRAIN-only current-main component')
    payload=torch.load(path,map_location='cpu',weights_only=False)
    if payload['metadata']!={k:v for k,v in fit.items() if k!='artifactSha256'}:raise ValueError(f'{component} embedded metadata differs')
    return fit,payload,actual


def prepare(parent,output):
    cache,_,meta=trajectory.load(parent/'potion-trajectory-v2')
    control_fit,control_payload,control_hash=verify_component(parent/'full-union-maxHP-v1','maxHP',meta)
    candidate_fit,candidate_payload,candidate_hash=verify_component(parent/'full-union-HP-v1','HP',meta)
    arrays,spec=c.base._load_prepared(composed_evaluate.PREPARED);c.base._prepare_target_indices(arrays,spec)
    models=c.FrozenModels('cuda');models.max_net.encoder.load_state_dict(control_payload['encoderStateDict']);models.hp_net.encoder.load_state_dict(candidate_payload['encoderStateDict'])
    encoders=dict(reference=models.max_net.encoder,candidate=models.hp_net.encoder)
    for encoder in encoders.values():encoder.eval().requires_grad_(False)
    if any(p.requires_grad for encoder in encoders.values() for p in encoder.parameters()):raise ValueError('encoder was not frozen')
    z={name:np.empty((len(cache['ids']),64),np.float32) for name in encoders};previous=torch.backends.mha.get_fastpath_enabled();torch.backends.mha.set_fastpath_enabled(False);started=time.monotonic()
    try:
        with torch.inference_mode():
            for start in range(0,len(cache['ids']),2048):
                local=np.arange(start,min(start+2048,len(cache['ids'])));inputs=c.base._torch_inputs(arrays,cache['ids'][local],'cuda',torch,trim_padding=True)
                for name,encoder in encoders.items():z[name][local]=encoder(*inputs).float().cpu().numpy()
                if start%51200==0:print(json.dumps(dict(stage='cache',rows=start,total=len(cache['ids']),seconds=time.monotonic()-started)),flush=True)
    finally:torch.backends.mha.set_fastpath_enabled(previous)
    np.savez_compressed(output/'representations.npz',**z)
    provenance=dict(componentCheckpoints=dict(maxHP=dict(sha256=control_hash,sourceSha=control_fit['sourceSha'],recipe=control_fit['recipe']),
                                              HP=dict(sha256=candidate_hash,sourceSha=candidate_fit['sourceSha'],recipe=candidate_fit['recipe'])),
                    preparationCacheSha256=meta['cacheSha256'],sourceHashes=meta['hashes'],rowIdsSha256=digest_array(cache['ids']),
                    sourceGroupsSha256=digest_array(cache['source']),representationSha256={k:digest_array(v) for k,v in z.items()},
                    representationFileSha256=c.base.sha256(output/'representations.npz'),cacheSeconds=time.monotonic()-started)
    return cache,models.delta_values,provenance


def metrics(prob,target,delta_values,pre_max,true_max):
    nll=-np.log(prob[np.arange(len(target)),target]);expected=pre_max+prob@delta_values;mode=prob.argmax(-1)
    return dict(rows=len(target),nll=float(nll.mean()),accuracy=float(np.mean(mode==target)),
                expectedPostMaxHpMae=float(np.abs(expected-true_max).mean()))


def train_arm(name,z,cache,delta_values):
    train=np.flatnonzero(cache['win']&(cache['split']==0));validation=np.flatnonzero(cache['win']&(cache['split']==1));target=cache['delta'].astype(np.int64)
    head=torch.nn.Linear(64,len(delta_values)).cuda();torch.manual_seed(RECIPE['seed']);torch.cuda.manual_seed_all(RECIPE['seed']);head.reset_parameters()
    initial=state_hash(head);optimizer=torch.optim.AdamW(head.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay']);rng=np.random.default_rng(RECIPE['seed']);batch_hash=hashlib.sha256();history=[];best=float('inf');started=time.monotonic()
    def score(ids):
        head.eval();prob=[]
        with torch.inference_mode():
            for start in range(0,len(ids),2048):prob.append(torch.softmax(head(torch.as_tensor(z[ids[start:start+2048]],device='cuda')),-1).cpu().numpy())
        p=np.concatenate(prob);return metrics(p,target[ids],delta_values,cache['preMax'][ids],cache['trueMax'][ids]),p
    for epoch in range(1,RECIPE['epochs']+1):
        head.train();order=rng.permutation(train);total=0.
        for start in range(0,len(order),RECIPE['batch']):
            ids=order[start:start+RECIPE['batch']];batch_hash.update(ids.tobytes());optimizer.zero_grad(set_to_none=True)
            loss=torch.nn.functional.cross_entropy(head(torch.as_tensor(z[ids],device='cuda')),torch.as_tensor(target[ids],device='cuda'))
            if not torch.isfinite(loss):raise ValueError('nonfinite loss')
            loss.backward();norm=torch.nn.utils.clip_grad_norm_(head.parameters(),RECIPE['clip'])
            if not torch.isfinite(norm):raise ValueError('nonfinite gradient')
            optimizer.step();total+=float(loss.detach())*len(ids)
        value,_=score(validation);history.append(dict(epoch=epoch,trainNll=total/len(train),validation=value));print(json.dumps(dict(arm=name,seconds=time.monotonic()-started,**history[-1])),flush=True)
        if value['nll']<best:best=value['nll'];selected=epoch;state=copy.deepcopy(head.state_dict())
    head.load_state_dict(state);value,prob=score(validation)
    if not np.all(np.isfinite(prob)) or np.any(prob<0) or np.max(np.abs(prob.sum(-1)-1))>1e-6:raise ValueError('invalid probabilities')
    nonzero=target[validation]!=np.flatnonzero(delta_values==0)[0]
    slices=dict(nonzeroDelta=metrics(prob[nonzero],target[validation][nonzero],delta_values,cache['preMax'][validation][nonzero],cache['trueMax'][validation][nonzero]),
                zeroDelta=metrics(prob[~nonzero],target[validation][~nonzero],delta_values,cache['preMax'][validation][~nonzero],cache['trueMax'][validation][~nonzero]))
    return dict(initializationSha256=initial,batchOrderSha256=batch_hash.hexdigest(),selectedEpoch=selected,history=history,validation=value,slices=slices,
                validity=dict(probabilityMaxNormalizationError=float(np.max(np.abs(prob.sum(-1)-1)))),fitSeconds=time.monotonic()-started),prob


def run(args):
    root=Path(__file__).resolve().parents[1];current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if current!=args.experiment_sha:raise ValueError('experiment SHA differs')
    output=Path(args.output_dir)
    if output.exists():raise ValueError('refusing overwrite')
    if not torch.cuda.is_available():raise ValueError('CUDA required')
    output.mkdir(parents=True);torch.set_num_threads(4);cache,delta_values,provenance=prepare(Path(args.artifact_root),output)
    with np.load(output/'representations.npz') as raw:z={k:raw[k].copy() for k in raw.files}
    arms={};predictions={}
    for name in ('reference','candidate'):arms[name],predictions[name]=train_arm(name,z[name],cache,delta_values)
    if arms['reference']['initializationSha256']!=arms['candidate']['initializationSha256']:raise ValueError('head initial states differ')
    if arms['reference']['batchOrderSha256']!=arms['candidate']['batchOrderSha256']:raise ValueError('batch orders differ')
    decision,gates=classify(arms['reference']['validation'],arms['candidate']['validation']);validation=np.flatnonzero(cache['win']&(cache['split']==1));train=np.flatnonzero(cache['win']&(cache['split']==0))
    result=dict(baselineSha=args.baseline_sha,experimentSha=current,recipe=RECIPE,provenance=provenance,
                counts=dict(TRAIN=dict(rows=len(train),sources=len(np.unique(cache['source'][train]))),VALIDATION=dict(rows=len(validation),sources=len(np.unique(cache['source'][validation])))),
                rowParity=True,validationInGradientUpdates=False,encoderParametersFrozen=True,headInitialStatesByteIdentical=True,batchOrdersIdentical=True,
                arms=arms,gates=gates,decision=decision)
    c.base.json_dump(output/'results.json',result);np.savez_compressed(output/'validation_predictions.npz',rowIds=cache['ids'][validation],sourceGroups=cache['source'][validation],deltaValues=delta_values,reference=predictions['reference'],candidate=predictions['candidate'])
    c.base.json_dump(output/'artifact-hashes.json',{p.name:c.base.sha256(p) for p in output.iterdir() if p.is_file() and p.name!='artifact-hashes.json'})
    print(json.dumps(dict(decision=decision,gates=gates,reference=arms['reference']['validation'],candidate=arms['candidate']['validation'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifact-root',required=True);parser.add_argument('--output-dir',required=True);parser.add_argument('--baseline-sha',required=True);parser.add_argument('--experiment-sha',required=True);run(parser.parse_args())
