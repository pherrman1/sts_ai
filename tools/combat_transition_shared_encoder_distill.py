#!/usr/bin/env python3
"""Purpose-trained shared maxHP/signed-HP encoder distillation screen."""
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
from tools import combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_stochastic_hp as stochastic_hp


RECIPE = dict(
    schema="shared_transition_encoder_distillation_v1", seed=20260912,
    encoder="AttentionEncoder:64/2/4/128 initialized from current HP specialist",
    hpBranch="copied maxHP-delta embedding and 72/64/304 ReLU head",
    maxHpBranch="fresh Linear(64,11)", loss="0.5 KL(maxHP teacher||student) + 0.5 KL(HP teacher||student)",
    temperature=1, epochs=12, batch=512, encoderLr=1e-4, headLr=1e-3,
    optimizer="AdamW", weightDecay=1e-4, clip=1.0,
    trainingPrecision="AMP-FP16 established attention path", teacherPrecision="FP32",
    selection="earliest strict minimum 0.5 VALIDATION maxHP KL + 0.5 VALIDATION HP KL",
    population="exact current final-union source-grouped TRAIN/VALIDATION victories",
)

try:
    from tools import ctm_pins as _pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins as _pins
EXPECTED = _pins.value("combat_transition_shared_encoder_distill.EXPECTED", {
    "maxHP": "2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0",
    "HP": "0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b",
})


def digest_array(value):
    return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def state_hash(module):
    digest = hashlib.sha256()
    for name, value in module.state_dict().items():
        digest.update(name.encode()); digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def verify_component(folder, component, cache_meta):
    fit = json.loads((folder / "fit.json").read_text()); path = folder / "component.pt"
    actual = c.base.sha256(path)
    if fit["component"] != component or fit["artifactSha256"] != actual or actual != EXPECTED[component]:
        raise ValueError(f"{component} checkpoint binding differs")
    if fit["hashes"] != cache_meta["hashes"] or fit["preparationCacheSha256"] != cache_meta["cacheSha256"]:
        raise ValueError(f"{component} source/cache provenance differs")
    if "original VALIDATION" not in fit["recipe"]["selection"] or "original source-grouped TRAIN" not in fit["recipe"]["population"]:
        raise ValueError(f"{component} TRAIN/VALIDATION provenance differs")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload["metadata"] != _pins.strip({k: v for k, v in fit.items() if k != "artifactSha256"}):
        raise ValueError(f"{component} embedded metadata differs")
    return fit, payload, actual


def maxhp_metrics(prob, target, delta_values, pre_max, true_max):
    if not len(target): return dict(rows=0)
    nll = -np.log(prob[np.arange(len(target)), target]); expected = pre_max + prob @ delta_values
    return dict(rows=len(target), nll=float(nll.mean()), accuracy=float(np.mean(prob.argmax(-1) == target)),
                expectedPostMaxHpMae=float(np.abs(expected - true_max).mean()))


def hp_metrics(prob, classes, pre, maximum, actual, target):
    nll = -np.log(prob[np.arange(len(target)), target])
    return stochastic_hp.summarize(stochastic_hp.row_scores(prob, classes, pre, maximum, actual, nll))


def kl(teacher, student):
    selected = teacher > 0
    terms = np.zeros_like(teacher, dtype=np.float64)
    terms[selected] = teacher[selected] * (np.log(teacher[selected]) - np.log(student[selected]))
    return float(terms.sum(-1).mean())


def torch_kl(teacher, logits):
    log_student = torch.log_softmax(logits, -1)
    positive = teacher > 0
    log_teacher = torch.where(positive, teacher.log(), torch.zeros_like(teacher))
    return torch.where(positive, teacher * (log_teacher - log_student), torch.zeros_like(teacher)).sum(-1).mean()


def classify(teacher, student):
    hp_t, hp_s = teacher["HP"]["overall"], student["HP"]["overall"]
    max_t, max_s = teacher["maxHP"]["overall"], student["maxHP"]["overall"]
    hp_slices = {}
    for name in teacher["HP"]["slices"]:
        a, b = teacher["HP"]["slices"][name], student["HP"]["slices"][name]
        hp_slices[name] = dict(rows=a["rows"], nllRelative=(b["nll"]-a["nll"])/a["nll"],
                               crpsRelative=(b["crps"]-a["crps"])/a["crps"], expectedMaeDelta=b["expectedMae"]-a["expectedMae"])
    nonzero_t, nonzero_s = teacher["maxHP"]["slices"]["nonzeroDelta"], student["maxHP"]["slices"]["nonzeroDelta"]
    gates = dict(
        hpNllRelative=(hp_s["nll"]-hp_t["nll"])/hp_t["nll"], hpCrpsRelative=(hp_s["crps"]-hp_t["crps"])/hp_t["crps"],
        hpExpectedMaeDelta=hp_s["expectedMae"]-hp_t["expectedMae"], hpSlices=hp_slices,
        maxHpNllRelative=(max_s["nll"]-max_t["nll"])/max_t["nll"], maxHpAccuracyDrop=max_t["accuracy"]-max_s["accuracy"],
        maxHpExpectedMaeDelta=max_s["expectedPostMaxHpMae"]-max_t["expectedPostMaxHpMae"],
        maxHpNonzeroAccuracyDrop=nonzero_t["accuracy"]-nonzero_s["accuracy"],
        maxHpNonzeroNllDelta=nonzero_s["nll"]-nonzero_t["nll"],
    )
    hp_slice_fail = any(v["nllRelative"] > .05 or v["crpsRelative"] > .05 or v["expectedMaeDelta"] > .5 for v in hp_slices.values())
    numeric_pass = (gates["hpNllRelative"] <= .02 and gates["hpCrpsRelative"] <= .02 and gates["hpExpectedMaeDelta"] <= .15
                    and not hp_slice_fail and gates["maxHpNllRelative"] <= .02 and gates["maxHpAccuracyDrop"] <= .005
                    and gates["maxHpExpectedMaeDelta"] <= .10 and gates["maxHpNonzeroAccuracyDrop"] <= .05)
    # "Catastrophic" is intentionally only a clear-failure guard, not a tuned pass threshold.
    catastrophic_nonzero_nll = (not np.isfinite(nonzero_s["nll"]) or
                                (gates["maxHpNonzeroNllDelta"] > .5 and nonzero_s["nll"] > 1.5 * nonzero_t["nll"]))
    gates["maxHpNonzeroNllCatastrophic"] = bool(catastrophic_nonzero_nll)
    passed = numeric_pass and not catastrophic_nonzero_nll
    clearly_failed = (gates["hpNllRelative"] > .02 or gates["hpCrpsRelative"] > .02 or gates["hpExpectedMaeDelta"] > .15
                      or hp_slice_fail or gates["maxHpNllRelative"] > .02 or gates["maxHpAccuracyDrop"] > .005
                      or gates["maxHpExpectedMaeDelta"] > .10 or gates["maxHpNonzeroAccuracyDrop"] > .05 or catastrophic_nonzero_nll)
    return ("SHARED_TRANSITION_ENCODER_GO" if passed else ("SHARED_TRANSITION_ENCODER_REJECTED" if clearly_failed else "INCONCLUSIVE")), gates


def narrow_miss(gates):
    """The preregistered epoch-12 exception: at most 20% beyond each numeric gate."""
    slice_close = all(v["nllRelative"] <= .06 and v["crpsRelative"] <= .06 and v["expectedMaeDelta"] <= .6
                      for v in gates["hpSlices"].values())
    return (gates["hpNllRelative"] <= .024 and gates["hpCrpsRelative"] <= .024 and gates["hpExpectedMaeDelta"] <= .18
            and slice_close and gates["maxHpNllRelative"] <= .024 and gates["maxHpAccuracyDrop"] <= .006
            and gates["maxHpExpectedMaeDelta"] <= .12 and gates["maxHpNonzeroAccuracyDrop"] <= .06
            and not gates["maxHpNonzeroNllCatastrophic"])


def prepare(parent, output):
    cache, _, meta = trajectory.load(parent / "potion-trajectory-v2")
    max_fit, max_payload, max_hash = verify_component(parent / "full-union-maxHP-v1", "maxHP", meta)
    hp_fit, hp_payload, hp_hash = verify_component(parent / "full-union-HP-v1", "HP", meta)
    arrays, spec = c.base._load_prepared(composed_evaluate.PREPARED); c.base._prepare_target_indices(arrays, spec)
    models = c.FrozenModels("cuda")
    models.max_net.encoder.load_state_dict(max_payload["encoderStateDict"]); models.max_net.max_hp_delta.load_state_dict(max_payload["headStateDicts"][0])
    models.hp_net.encoder.load_state_dict(hp_payload["encoderStateDict"]); models.hp_net.delta_embedding.load_state_dict(hp_payload["headStateDicts"][0]); models.hp_net.hp.load_state_dict(hp_payload["headStateDicts"][1])
    models.max_net.eval().requires_grad_(False); models.hp_net.eval().requires_grad_(False)
    ids = np.flatnonzero(cache["win"] & (cache["split"] < 2)); n = len(cache["ids"])
    max_prob = np.lib.format.open_memmap(output / "teacher-maxHP.npy", mode="w+", dtype=np.float32, shape=(n, len(models.delta_values)))
    hp_prob = np.lib.format.open_memmap(output / "teacher-HP.npy", mode="w+", dtype=np.float32, shape=(n, len(models.classes)))
    max_prob[:] = 0; hp_prob[:] = 0
    started = time.monotonic()
    with torch.inference_mode():
        for start in range(0, len(ids), 1024):
            local = ids[start:start+1024]; inputs = c.base._torch_inputs(arrays, cache["ids"][local], "cuda", torch, trim_padding=True)
            with c.attention_backend(torch, True): zmax = models.max_net.encoder(*inputs)
            max_prob[local] = torch.softmax(models.max_net.max_hp_delta(zmax), -1).cpu().numpy()
            with c.attention_backend(torch, False): zhp = models.hp_net.encoder(*inputs)
            delta = torch.as_tensor(cache["delta"][local], device="cuda"); features = torch.cat((zhp, models.hp_net.delta_embedding(delta)), -1)
            raw = models.hp_net.hp(features).float(); legal = stochastic_hp.legal_support(models.classes, cache["preHp"][local], cache["trueMax"][local])
            hp_prob[local] = torch.softmax(raw.masked_fill(~torch.as_tensor(legal, device="cuda"), -torch.inf), -1).cpu().numpy()
            if start % 51200 == 0: print(json.dumps(dict(stage="teachers", rows=start, total=len(ids), seconds=time.monotonic()-started)), flush=True)
    max_prob.flush(); hp_prob.flush()
    train = np.flatnonzero(cache["win"] & (cache["split"] == 0)); validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    counts = {name: dict(rows=len(selected), sources=len(np.unique(cache["source"][selected]))) for name, selected in (("TRAIN",train),("VALIDATION",validation))}
    if counts != _pins.value("combat_transition_shared_encoder_distill.UNION_COUNTS", {"TRAIN":{"rows":393677,"sources":19986},"VALIDATION":{"rows":48590,"sources":2496}}): raise ValueError("final-union population differs")
    teacher_validity = dict(allFinite=bool(np.isfinite(max_prob[ids]).all() and np.isfinite(hp_prob[ids]).all()),
                            maxHpNormalizationError=float(np.max(np.abs(max_prob[ids].sum(1)-1))),
                            hpNormalizationError=float(np.max(np.abs(hp_prob[ids].sum(1)-1))))
    if not teacher_validity["allFinite"] or max(teacher_validity["maxHpNormalizationError"],teacher_validity["hpNormalizationError"]) > 1e-6:
        raise ValueError("teacher probability validity failed")
    provenance = dict(componentCheckpoints={"maxHP":{"sha256":max_hash,"sourceSha":max_fit["sourceSha"]},"HP":{"sha256":hp_hash,"sourceSha":hp_fit["sourceSha"]}},
                      sourceHashes=meta["hashes"], preparationCacheSha256=meta["cacheSha256"], rowIdsSha256=digest_array(cache["ids"][ids]),
                      sourceGroupsSha256=digest_array(cache["source"][ids]), teacherOutputs={"maxHP":c.base.sha256(output/"teacher-maxHP.npy"),"HP":c.base.sha256(output/"teacher-HP.npy")},
                      teacherValidity=teacher_validity,
                      teacherParametersFrozen=not any(p.requires_grad for m in (models.max_net,models.hp_net) for p in m.parameters()), teacherSeconds=time.monotonic()-started)
    return cache, arrays, models, train, validation, counts, provenance


def evaluate(max_prob, hp_prob, cache, models, ids):
    max_target = cache["delta"][ids].astype(np.int64); zero = int(np.flatnonzero(models.delta_values == 0)[0]); nonzero = max_target != zero
    hp_target = stochastic_hp.check_targets(models.classes, cache["preHp"][ids], cache["trueMax"][ids], cache["trueHp"][ids])
    hp_masks = dict(healing=cache["trueHp"][ids] > cache["preHp"][ids], lowPreHp=cache["preHp"][ids]/cache["preMax"][ids] < .25, damage=cache["trueHp"][ids] < cache["preHp"][ids])
    return {"maxHP":{"overall":maxhp_metrics(max_prob,max_target,models.delta_values,cache["preMax"][ids],cache["trueMax"][ids]),
                     "slices":{"zeroDelta":maxhp_metrics(max_prob[~nonzero],max_target[~nonzero],models.delta_values,cache["preMax"][ids][~nonzero],cache["trueMax"][ids][~nonzero]),
                               "nonzeroDelta":maxhp_metrics(max_prob[nonzero],max_target[nonzero],models.delta_values,cache["preMax"][ids][nonzero],cache["trueMax"][ids][nonzero])}},
            "HP":{"overall":hp_metrics(hp_prob,models.classes,cache["preHp"][ids],cache["trueMax"][ids],cache["trueHp"][ids],hp_target),
                  "slices":{name:hp_metrics(hp_prob[mask],models.classes,cache["preHp"][ids][mask],cache["trueMax"][ids][mask],cache["trueHp"][ids][mask],hp_target[mask]) for name,mask in hp_masks.items()}}}


def run(args):
    root = Path(__file__).resolve().parents[1]; current = subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    if current != args.experiment_sha or subprocess.check_output(["git","status","--porcelain"],cwd=root,text=True).strip(): raise ValueError("fit requires clean frozen experiment SHA")
    if not torch.cuda.is_available(): raise ValueError("CUDA required by fixed recipe")
    output = Path(args.output_dir)
    if output.exists(): raise ValueError("refusing overwrite")
    output.mkdir(parents=True); torch.set_num_threads(4); torch.manual_seed(RECIPE["seed"]); torch.cuda.manual_seed_all(RECIPE["seed"])
    cache, arrays, teachers, train, validation, counts, provenance = prepare(Path(args.artifact_root), output)
    if args.teachers_only:
        # Retrain (#418): the DeepSets distill needs only the frozen teacher cache, not the shared-Attention control.
        result=dict(baselineSha=args.baseline_sha,experimentSha=current,counts=counts,provenance=provenance,testInferenceRows=0,decision="TEACHER_CACHE_ONLY")
        c.base.json_dump(output/"results.json",result);print(json.dumps(dict(decision=result["decision"],counts=counts)),flush=True);return
    width = len(c.base.CONTINUOUS_GLOBAL_FIELDS)
    student = stochastic_hp.new_model(torch, np.zeros(width,np.float32), np.ones(width,np.float32),
                                      len(teachers.delta_values), teachers.classes, RECIPE["seed"]).cuda()
    student.load_state_dict(teachers.hp_net.state_dict()); student.train().requires_grad_(True)
    if state_hash(student) != state_hash(teachers.hp_net): raise ValueError("student HP initialization differs")
    initial_hp_hash = state_hash(student)
    max_head = torch.nn.Linear(64,len(teachers.delta_values)).cuda(); torch.manual_seed(RECIPE["seed"]); torch.cuda.manual_seed_all(RECIPE["seed"]); max_head.reset_parameters(); initial_max_hash = state_hash(max_head)
    groups=[dict(params=student.encoder.parameters(),lr=RECIPE["encoderLr"]),dict(params=list(student.delta_embedding.parameters())+list(student.hp.parameters())+list(max_head.parameters()),lr=RECIPE["headLr"])]
    optimizer=torch.optim.AdamW(groups,weight_decay=RECIPE["weightDecay"]); scaler=torch.amp.GradScaler("cuda",init_scale=16384); rng=np.random.default_rng(RECIPE["seed"]); batch_digest=hashlib.sha256()
    teacher_max=np.load(output/"teacher-maxHP.npy",mmap_mode="r"); teacher_hp=np.load(output/"teacher-HP.npy",mmap_mode="r")
    pre=cache["preHp"].astype(np.int64); maximum=cache["trueMax"].astype(np.int64)
    def forward(ids, amp):
        inputs=c.base._torch_inputs(arrays,cache["ids"][ids],"cuda",torch,trim_padding=True); context=torch.autocast("cuda",dtype=torch.float16,enabled=amp)
        with c.attention_backend(torch,False), context:
            z=student.encoder(*inputs); max_logits=max_head(z).float(); features=torch.cat((z,student.delta_embedding(torch.as_tensor(cache["delta"][ids],device="cuda"))),-1); hp_logits=student.hp(features).float()
        legal=stochastic_hp.legal_support(teachers.classes,pre[ids],maximum[ids]); hp_logits=hp_logits.masked_fill(~torch.as_tensor(legal,device="cuda"),-torch.inf)
        return max_logits,hp_logits
    def score(ids):
        student.eval();max_out=[];hp_out=[];total_max=total_hp=0.
        with torch.inference_mode():
            for start in range(0,len(ids),1024):
                local=ids[start:start+1024];a,b=forward(local,False)
                tm=torch.as_tensor(np.array(teacher_max[local]),device="cuda");th=torch.as_tensor(np.array(teacher_hp[local]),device="cuda")
                total_max+=float(torch_kl(tm,a))*len(local);total_hp+=float(torch_kl(th,b))*len(local)
                max_out.append(torch.softmax(a,-1).cpu().numpy());hp_out.append(torch.softmax(b,-1).cpu().numpy())
        a,b=np.concatenate(max_out),np.concatenate(hp_out);return a,b,total_max/len(ids),total_hp/len(ids)
    history=[];best=float("inf");started=time.monotonic()
    for epoch in range(1,RECIPE["epochs"]+1):
        student.train();max_head.train();order=rng.permutation(train);total_max=total_hp=0.
        for start in range(0,len(order),RECIPE["batch"]):
            ids=order[start:start+RECIPE["batch"]];batch_digest.update(ids.tobytes());optimizer.zero_grad(set_to_none=True);a,b=forward(ids,True)
            tm=torch.as_tensor(np.array(teacher_max[ids]),device="cuda");th=torch.as_tensor(np.array(teacher_hp[ids]),device="cuda")
            lm=torch_kl(tm,a);lh=torch_kl(th,b);loss=.5*(lm+lh)
            if not torch.isfinite(loss):raise ValueError("nonfinite distillation loss")
            scaler.scale(loss).backward();scaler.unscale_(optimizer);norm=torch.nn.utils.clip_grad_norm_(list(student.parameters())+list(max_head.parameters()),RECIPE["clip"])
            if not torch.isfinite(norm):raise ValueError("nonfinite gradient")
            scaler.step(optimizer);scaler.update();total_max+=float(lm.detach())*len(ids);total_hp+=float(lh.detach())*len(ids)
        _,_,vm,vh=score(validation);entry=dict(epoch=epoch,trainMaxHpKl=total_max/len(train),trainHpKl=total_hp/len(train),validationMaxHpKl=vm,validationHpKl=vh,selectionLoss=.5*(vm+vh),seconds=time.monotonic()-started);history.append(entry);print(json.dumps(entry),flush=True)
        if entry["selectionLoss"]<best:best=entry["selectionLoss"];selected=epoch;student_state=copy.deepcopy(student.state_dict());max_state=copy.deepcopy(max_head.state_dict())
    student.load_state_dict(student_state);max_head.load_state_dict(max_state);student_max,student_hp,max_kl,hp_kl=score(validation)
    legal=stochastic_hp.legal_support(teachers.classes,pre[validation],maximum[validation]);validity=dict(maxHpNormalizationError=float(np.max(np.abs(student_max.sum(1)-1))),hpNormalizationError=float(np.max(np.abs(student_hp.sum(1)-1))),hpUnsupportedProbability=float(np.max(np.where(legal,0,student_hp))),allFinite=bool(np.isfinite(student_max).all() and np.isfinite(student_hp).all()))
    if not validity["allFinite"] or max(validity["maxHpNormalizationError"],validity["hpNormalizationError"])>1e-6 or validity["hpUnsupportedProbability"]!=0:raise ValueError("student probability validity failed")
    teacher_metrics=evaluate(teacher_max[validation],teacher_hp[validation],cache,teachers,validation);student_metrics=evaluate(student_max,student_hp,cache,teachers,validation);decision,gates=classify(teacher_metrics,student_metrics)
    if selected == RECIPE["epochs"] and decision == "SHARED_TRANSITION_ENCODER_REJECTED" and narrow_miss(gates): decision="INCONCLUSIVE"
    checkpoint=output/"student.pt";torch.save(dict(stateDict=student_state,maxHpHeadStateDict=max_state,recipe=RECIPE,experimentSha=current,selectedEpoch=selected),checkpoint)
    result=dict(baselineSha=args.baseline_sha,experimentSha=current,recipe=RECIPE,counts=counts,provenance=provenance,testInferenceRows=0,testMetricsComputed=False,validationInGradientUpdates=False,studentHpInitializationMatches=True,studentHpInitializationSha256=initial_hp_hash,studentMaxHpHeadInitializationSha256=initial_max_hash,batchOrderSha256=batch_digest.hexdigest(),history=history,selectedEpoch=selected,studentToTeacherKl={"maxHP":max_kl,"HP":hp_kl},teacher=teacher_metrics,student=student_metrics,gates=gates,validity=validity,trainingSeconds=time.monotonic()-started,checkpointSha256=c.base.sha256(checkpoint),decision=decision)
    c.base.json_dump(output/"results.json",result);np.savez_compressed(output/"validation_predictions.npz",rowIds=cache["ids"][validation],sourceGroups=cache["source"][validation],deltaValues=teachers.delta_values,classes=teachers.classes,studentMaxHP=student_max,studentHP=student_hp)
    c.base.json_dump(output/"artifact-hashes.json",{p.name:c.base.sha256(p) for p in output.iterdir() if p.is_file() and p.name!="artifact-hashes.json"});print(json.dumps(dict(decision=decision,selectedEpoch=selected,gates=gates)),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--artifact-root",required=True);parser.add_argument("--output-dir",required=True);parser.add_argument("--baseline-sha",required=True);parser.add_argument("--experiment-sha",required=True)
    parser.add_argument("--teachers-only",action="store_true",help="write the teacher cache and its receipt; skip the shared-Attention control fit");run(parser.parse_args())
