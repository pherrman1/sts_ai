#!/usr/bin/env python3
"""Paired frozen-representation screen for the near-full signed-HP decoder."""
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
from tools import combat_transition_stochastic_hp as stochastic_hp


RECIPE = dict(
    schema="shared_frozen_hp_encoder_screen_v1",
    seed=refit.RECIPE["seed"],
    epochs=refit.RECIPE["epochs"],
    batch=refit.RECIPE["batch"],
    lr=refit.RECIPE["headLr"],
    weightDecay=refit.RECIPE["weightDecay"],
    clip=refit.RECIPE["clip"],
    precision="cached FP32 representations; AMP-FP16 decoder fit",
    encoderArithmetic="FP32, MHA fastpath disabled identically for both arms",
    selection="independent earliest strict minimum VALIDATION signed-HP NLL",
    population="full-union original source-grouped TRAIN/VALIDATION victories",
    trained="maxHP-delta embedding and 72/64/304 ReLU signed-HP head only",
)


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def state_hash(module):
    digest = hashlib.sha256()
    for name, value in module.state_dict().items():
        digest.update(name.encode())
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def new_decoder(delta_count, classes, seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    return torch.nn.ModuleDict(dict(
        delta_embedding=torch.nn.Embedding(delta_count, 8),
        hp=torch.nn.Sequential(torch.nn.Linear(72, 64), torch.nn.ReLU(), torch.nn.Linear(64, len(classes))),
    ))


def classify(reference, candidate, slice_deltas):
    nll_relative=(candidate["nll"]-reference["nll"])/reference["nll"]
    crps_relative=(candidate["crps"]-reference["crps"])/reference["crps"]
    mae_delta=candidate["expectedMae"]-reference["expectedMae"]
    obvious_slice_regression=any(v["nllRelative"] > .05 or v["crpsRelative"] > .05 or v["expectedMaeDelta"] > .5
                                 for v in slice_deltas.values() if v["rows"] >= 100)
    gates=dict(nllRelative=nll_relative,crpsRelative=crps_relative,expectedMaeDelta=mae_delta,
               obviousSliceRegression=obvious_slice_regression)
    passed=nll_relative <= .01 and crps_relative <= .01 and mae_delta <= .1 and not obvious_slice_regression
    clearly_failed=nll_relative > .012 or crps_relative > .012 or mae_delta > .12 or obvious_slice_regression
    decision="GO_TO_SHARED_ENCODER_NEXT_STAGE" if passed else ("SHARED_ENCODER_HP_REJECTED" if clearly_failed else "INCONCLUSIVE")
    return decision,gates


def verify_component(folder, component, cache_meta):
    fit=json.loads((folder/"fit.json").read_text())
    checkpoint=folder/"component.pt"
    actual=c.base.sha256(checkpoint)
    if fit["component"] != component or actual != fit["artifactSha256"]:
        raise ValueError(f"{component} checkpoint binding differs")
    if fit["hashes"] != cache_meta["hashes"] or fit["preparationCacheSha256"] != cache_meta["cacheSha256"]:
        raise ValueError(f"{component} source/cache provenance differs")
    if fit["recipe"]["population"] != refit.RECIPE["population"] or "original VALIDATION" not in fit["recipe"]["selection"]:
        raise ValueError(f"{component} TRAIN/VALIDATION provenance is not the current-main component recipe")
    payload=torch.load(checkpoint,map_location="cpu",weights_only=False)
    if payload["metadata"] != {k:v for k,v in fit.items() if k != "artifactSha256"}:
        raise ValueError(f"{component} embedded metadata differs")
    return fit,payload,actual


def cache_representations(parent, output):
    cache,_,cache_meta=trajectory.load(parent/"potion-trajectory-v2")
    survival_fit,survival_payload,survival_hash=verify_component(parent/"full-union-survival-v1","survival",cache_meta)
    hp_fit,hp_payload,hp_hash=verify_component(parent/"full-union-HP-v1","HP",cache_meta)
    arrays,spec=c.base._load_prepared(composed_evaluate.PREPARED)
    c.base._prepare_target_indices(arrays,spec)
    models=c.FrozenModels("cuda")
    models.survival_net.encoder.load_state_dict(survival_payload["encoderStateDict"])
    models.hp_net.encoder.load_state_dict(hp_payload["encoderStateDict"])
    for encoder in (models.survival_net.encoder,models.hp_net.encoder):
        encoder.eval().requires_grad_(False)
        if any(p.requires_grad for p in encoder.parameters()):
            raise ValueError("encoder was not frozen")
    representations={name:np.empty((len(cache["ids"]),64),np.float32) for name in ("reference","candidate")}
    previous=torch.backends.mha.get_fastpath_enabled()
    torch.backends.mha.set_fastpath_enabled(False)
    started=time.monotonic()
    try:
        with torch.inference_mode():
            for start in range(0,len(cache["ids"]),2048):
                local=np.arange(start,min(start+2048,len(cache["ids"])))
                inputs=c.base._torch_inputs(arrays,cache["ids"][local],"cuda",torch,trim_padding=True)
                representations["reference"][local]=models.hp_net.encoder(*inputs).float().cpu().numpy()
                representations["candidate"][local]=models.survival_net.encoder(*inputs).float().cpu().numpy()
                if start % 51200 == 0:
                    print(json.dumps(dict(stage="cache",rows=start,total=len(cache["ids"]),seconds=time.monotonic()-started)),flush=True)
    finally:
        torch.backends.mha.set_fastpath_enabled(previous)
    np.savez_compressed(output/"representations.npz",reference=representations["reference"],candidate=representations["candidate"])
    row_ids=cache["ids"].astype(np.int64)
    sources=cache["source"].astype(np.int64)
    metadata=dict(
        componentCheckpoints=dict(survival=dict(sha256=survival_hash,sourceSha=survival_fit["sourceSha"],recipe=survival_fit["recipe"]),
                                  HP=dict(sha256=hp_hash,sourceSha=hp_fit["sourceSha"],recipe=hp_fit["recipe"])),
        sourceHashes=cache_meta["hashes"],preparationCacheSha256=cache_meta["cacheSha256"],
        rowIdsSha256=sha256_bytes(row_ids.tobytes()),sourceGroupsSha256=sha256_bytes(sources.tobytes()),
        representationSha256={name:sha256_bytes(value.tobytes()) for name,value in representations.items()},
        representationFileSha256=c.base.sha256(output/"representations.npz"),cacheSeconds=time.monotonic()-started,
    )
    return cache,arrays,models.delta_values,models.classes,metadata


def summarize(prob, classes, pre, maximum, actual, targets, mask=None):
    if mask is not None:
        prob,pre,maximum,actual,targets=(x[mask] for x in (prob,pre,maximum,actual,targets))
    if not len(actual):
        return dict(rows=0)
    nll=-np.log(prob[np.arange(len(targets)),targets])
    rows=stochastic_hp.row_scores(prob,classes,pre,maximum,actual,nll)
    return stochastic_hp.summarize(rows)


def train_arm(name,z,cache,classes,delta_values):
    train=np.flatnonzero(cache["win"]&(cache["split"]==0))
    validation=np.flatnonzero(cache["win"]&(cache["split"]==1))
    pre=cache["preHp"].astype(np.int64);maximum=cache["trueMax"].astype(np.int64);actual=cache["trueHp"].astype(np.int64)
    targets=stochastic_hp.check_targets(classes,pre[cache["win"]],maximum[cache["win"]],actual[cache["win"]])
    all_targets=np.zeros(len(pre),np.int64);all_targets[cache["win"]]=targets
    decoder=new_decoder(len(delta_values),classes,RECIPE["seed"]).cuda()
    initial=state_hash(decoder)
    optimizer=torch.optim.AdamW(decoder.parameters(),lr=RECIPE["lr"],weight_decay=RECIPE["weightDecay"])
    scaler=torch.amp.GradScaler("cuda",init_scale=16384)
    rng=np.random.default_rng(RECIPE["seed"]);batch_digest=hashlib.sha256();history=[];best=float("inf")
    def logits(ids):
        features=torch.cat((torch.as_tensor(z[ids],device="cuda"),decoder["delta_embedding"](torch.as_tensor(cache["delta"][ids],device="cuda"))),-1)
        with torch.autocast("cuda",dtype=torch.float16): raw=decoder["hp"](features).float()
        legal=stochastic_hp.legal_support(classes,pre[ids],maximum[ids])
        return raw.masked_fill(~torch.as_tensor(legal,device="cuda"),-torch.inf)
    def score(ids):
        decoder.eval();probs=[]
        with torch.inference_mode():
            for start in range(0,len(ids),2048):
                selected=ids[start:start+2048];probs.append(torch.softmax(logits(selected),-1).cpu().numpy())
        probability=np.concatenate(probs)
        return summarize(probability,classes,pre[ids],maximum[ids],actual[ids],all_targets[ids]),probability
    started=time.monotonic()
    for epoch in range(1,RECIPE["epochs"]+1):
        decoder.train();order=rng.permutation(train);total=0.
        for start in range(0,len(order),RECIPE["batch"]):
            ids=order[start:start+RECIPE["batch"]];batch_digest.update(ids.tobytes());optimizer.zero_grad(set_to_none=True)
            loss=torch.nn.functional.cross_entropy(logits(ids),torch.as_tensor(all_targets[ids],device="cuda"))
            if not torch.isfinite(loss):raise ValueError("nonfinite training loss")
            scaler.scale(loss).backward();scaler.unscale_(optimizer);norm=torch.nn.utils.clip_grad_norm_(decoder.parameters(),RECIPE["clip"])
            if not torch.isfinite(norm):raise ValueError("nonfinite decoder gradient")
            scaler.step(optimizer);scaler.update();total+=float(loss.detach())*len(ids)
        metrics,_=score(validation);history.append(dict(epoch=epoch,trainNll=total/len(train),validation=metrics))
        print(json.dumps(dict(arm=name,seconds=time.monotonic()-started,**history[-1])),flush=True)
        if metrics["nll"] < best:
            best=metrics["nll"];selected_epoch=epoch;state=copy.deepcopy(decoder.state_dict())
    decoder.load_state_dict(state);metrics,probability=score(validation)
    legal=stochastic_hp.legal_support(classes,pre[validation],maximum[validation])
    validity=dict(probabilityMaxNormalizationError=float(np.max(np.abs(probability.sum(1)-1))),
                  unsupportedProbabilityMax=float(np.max(np.where(legal,0,probability))))
    if validity["probabilityMaxNormalizationError"]>1e-6 or validity["unsupportedProbabilityMax"]!=0:
        raise ValueError("signed-HP probability validity failed")
    masks=dict(lowHp=pre[validation]/cache["preMax"][validation]<.25,healing=actual[validation]>pre[validation],damage=actual[validation]<pre[validation])
    slices={slice_name:summarize(probability,classes,pre[validation],maximum[validation],actual[validation],all_targets[validation],mask)
            for slice_name,mask in masks.items()}
    return dict(initializationSha256=initial,batchOrderSha256=batch_digest.hexdigest(),selectedEpoch=selected_epoch,
                history=history,validation=metrics,slices=slices,validity=validity,fitSeconds=time.monotonic()-started),probability


def run(args):
    if subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=Path(__file__).resolve().parents[1]).strip()!=args.experiment_sha:
        raise ValueError("experiment SHA differs")
    output=Path(args.output_dir)
    if output.exists():raise ValueError("refusing overwrite")
    if not torch.cuda.is_available():raise ValueError("CUDA is required by the fixed recipe")
    output.mkdir(parents=True)
    torch.set_num_threads(4)
    cache,arrays,delta_values,classes,provenance=cache_representations(Path(args.artifact_root),output)
    with np.load(output/"representations.npz") as raw:representations={k:raw[k].copy() for k in raw.files}
    results={};probabilities={}
    for arm in ("reference","candidate"):
        results[arm],probabilities[arm]=train_arm(arm,representations[arm],cache,classes,delta_values)
    if results["reference"]["initializationSha256"] != results["candidate"]["initializationSha256"]:
        raise ValueError("decoder initial states differ")
    if results["reference"]["batchOrderSha256"] != results["candidate"]["batchOrderSha256"]:
        raise ValueError("batch orders differ")
    validation=np.flatnonzero(cache["win"]&(cache["split"]==1))
    if np.any(cache["split"][np.flatnonzero(cache["win"]&(cache["split"]==0))]!=0):raise ValueError("VALIDATION entered gradients")
    slice_deltas={}
    for name in results["reference"]["slices"]:
        a,b=results["reference"]["slices"][name],results["candidate"]["slices"][name]
        slice_deltas[name]=dict(rows=a["rows"],nllDelta=b["nll"]-a["nll"],nllRelative=(b["nll"]-a["nll"])/a["nll"],
                                     crpsDelta=b["crps"]-a["crps"],crpsRelative=(b["crps"]-a["crps"])/a["crps"],
                                     expectedMaeDelta=b["expectedMae"]-a["expectedMae"])
    decision,gates=classify(results["reference"]["validation"],results["candidate"]["validation"],slice_deltas)
    counts={name:dict(rows=int(len(ids)),sources=int(len(np.unique(cache["source"][ids])))) for name,ids in
            (("TRAIN",np.flatnonzero(cache["win"]&(cache["split"]==0))),("VALIDATION",validation))}
    receipt=dict(baselineSha=args.baseline_sha,experimentSha=args.experiment_sha,recipe=RECIPE,provenance=provenance,counts=counts,
                 rowParity=True,validationInGradientUpdates=False,decoderInitialStatesByteIdentical=True,batchOrdersIdentical=True,
                 arms=results,sliceDeltas=slice_deltas,gates=gates,decision=decision)
    c.base.json_dump(output/"results.json",receipt)
    np.savez_compressed(output/"validation_predictions.npz",rowIds=cache["ids"][validation],sourceGroups=cache["source"][validation],classes=classes,
                        reference=probabilities["reference"],candidate=probabilities["candidate"])
    c.base.json_dump(output/"artifact-hashes.json",{p.name:c.base.sha256(p) for p in output.iterdir() if p.is_file() and p.name!="artifact-hashes.json"})
    print(json.dumps(dict(decision=decision,gates=gates,reference=results["reference"]["validation"],candidate=results["candidate"]["validation"])),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root",required=True)
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--baseline-sha",required=True)
    parser.add_argument("--experiment-sha",required=True)
    run(parser.parse_args())
