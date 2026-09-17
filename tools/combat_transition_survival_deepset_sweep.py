#!/usr/bin/env python3
"""Preregistered six-arm survival DeepSets LR/weight-decay sweep."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_survival_deepset_train as fit


BASELINE_SHA = "0b7d4607c49b5db8082f4cad89579f3e33635f41"
RECIPE = dict(
    schema="survival_specific_deepset_lr_wd_sweep_v1", seed=20260912, batch=512,
    precision="FP32", optimizer="AdamW", gradientClip=1.0,
    loss="unweighted BCEWithLogitsLoss; 1=survived, 0=death",
    maxEpochs=40, minEpochs=12, patience=6,
    selection="per-arm earliest strict minimum VALIDATION NLL",
    stageA="fresh PR205 warm-start for each arm",
    continuation="not part of this six-arm sweep; optional separate follow-up",
)
ARMS = {
    "baseline": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=1e-4),
    "lowerLr": dict(encoderLr=5e-5, headLr=5e-4, weightDecay=1e-4),
    "muchLowerLr": dict(encoderLr=2e-5, headLr=2e-4, weightDecay=1e-4),
    "moreWd": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=5e-4),
    "strongWd": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=1e-3),
    "lowerLrWd": dict(encoderLr=5e-5, headLr=5e-4, weightDecay=5e-4),
}
ARM_ORDER = ("baseline", "lowerLr", "muchLowerLr", "moreWd", "strongWd", "lowerLrWd")
GATES = dict(fit.GATES)


def arm_recipe(arm):
    recipe = dict(RECIPE)
    recipe.update(ARMS[arm], name=arm, training="PR205 encoder plus fresh Linear(64,1), TRAIN only")
    return recipe


def fit_arm(model, arrays, cache, train, validation, output, experiment_sha, arm):
    optimizer, proof = fit.make_optimizer(model)
    for group, learning_rate in zip(optimizer.param_groups,
                                    (ARMS[arm]["encoderLr"], ARMS[arm]["headLr"])):
        group["lr"] = learning_rate
    optimizer.param_groups[0]["weight_decay"] = ARMS[arm]["weightDecay"]
    optimizer.param_groups[1]["weight_decay"] = ARMS[arm]["weightDecay"]
    for group_proof, group in zip(proof["groups"], optimizer.param_groups):
        group_proof.update(lr=group["lr"], weightDecay=group["weight_decay"])
    generator = np.random.default_rng(fit.RECIPE["seed"])
    best_nll, best_epoch, epoch = math.inf, 0, 0
    history = []
    initial_normalization = fit.normalization_digest(model.encoder)
    while epoch < fit.RECIPE["maxEpochs"]:
        epoch += 1
        started = time.perf_counter()
        order = generator.permutation(train)
        total_loss = 0.0
        for start in range(0, len(order), fit.RECIPE["batch"]):
            batch = order[start:start + fit.RECIPE["batch"]]
            loss, _ = fit.update_batch(model, optimizer,
                fit.inputs_for(arrays, cache, batch, "cuda", 0),
                torch.as_tensor(cache["win"][batch], dtype=torch.float32, device="cuda"))
            total_loss += loss * len(batch)
        validation_nll = fit.summarize(
            fit.predict(model, arrays, cache, validation, "cuda"), cache, validation)["nll"]
        if fit.normalization_digest(model.encoder) != initial_normalization:
            raise ValueError("warm-start normalization buffers changed")
        entry = dict(epoch=epoch, trainNll=total_loss / len(train), validationNll=validation_nll,
            seconds=time.perf_counter() - started, batchOrderSha256=fit.screen.array_digest(order))
        history.append(entry)
        if fit.strict_minimum(validation_nll, best_nll):
            best_nll, best_epoch = validation_nll, epoch
            torch.save(dict(stateDict=model.state_dict(), selectedEpoch=epoch,
                experimentSha=experiment_sha, recipe=arm_recipe(arm)), output / "selected.pt")
        fit.screen.composed.base.json_dump(output / "progress.json", dict(history=history,
            selectedEpoch=best_epoch, experimentSha=experiment_sha))
        print(json.dumps(dict(arm=arm, **entry)), flush=True)
        if fit.should_stop(epoch, best_epoch):
            break
    model.load_state_dict(torch.load(output / "selected.pt", map_location="cuda", weights_only=False)["stateDict"])
    return dict(history=history, selectedEpoch=best_epoch,
        stoppingReason="patience" if fit.should_stop(epoch, best_epoch) else "max epoch",
        optimizationUncertainty=epoch == fit.RECIPE["maxEpochs"] and not fit.should_stop(epoch, best_epoch),
        optimizerScope=proof)


def run(args):
    if args.output.exists():
        raise ValueError(f"refusing overwrite of {args.output}")
    if fit.screen.current_head() != args.experiment_sha or subprocess_status() != "":
        raise ValueError("freeze the exact clean implementation SHA before sweep")
    if not torch.cuda.is_available():
        raise ValueError("CUDA required")
    args.output.mkdir(parents=True)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.mha.set_fastpath_enabled(True)
    cache, arrays, population, provenance = fit.load_population(args)
    train = np.flatnonzero(cache["split"] == 0)
    validation = np.flatnonzero(cache["split"] == 1)
    reference_encoder, reference_head, _ = fit.screen.load_reference(args)
    reference = fit.SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = fit.predict(reference, arrays, cache, validation, "cuda")
    reference_metrics = fit.summarize(reference_logits, cache, validation)
    if abs(reference_metrics["nll"] - fit.screen.REFERENCE_NLL) > 1e-6:
        raise ValueError("reference NLL did not reproduce")
    payload = torch.load(args.deepset_run / "student.pt", map_location="cpu", weights_only=False)
    original_encoder_state = {key.removeprefix("encoder."): value for key, value in
                              payload["stateDict"].items() if key.startswith("encoder.")}
    result = dict(schema=RECIPE["schema"], baselineSha=args.base_sha, experimentSha=args.experiment_sha,
        recipe=RECIPE, armRecipes={name: dict(values) for name, values in ARMS.items()}, arms={}, armOrder=ARM_ORDER, fixedGates=fit.GATES, population=population,
        provenance=provenance, reference=dict(metrics=reference_metrics,
            originalNll=fit.screen.REFERENCE_NLL), initialization=dict(
            encoderSha256=fit.screen.state_digest(original_encoder_state),
            normalizationSha256=fit.screen.state_digest({
                key: value for key, value in original_encoder_state.items()
                if key in ("scalar_mean", "scalar_inv")})),
        stageB=None, testEncodedRows=0, testInferenceRows=0, testScoredRows=0,
        environment=dict(torch=torch.__version__, cuda=torch.version.cuda,
                         gpu=torch.cuda.get_device_name(), cpuThreads=4, tf32=False))
    fit.screen.composed.base.json_dump(args.output / "progress.json", dict(status="running"))
    selected_arms = ARM_ORDER
    for name in selected_arms:
        encoder, _ = fit.screen.load_candidate_encoder(args)
        encoder.load_state_dict(original_encoder_state, strict=True)
        torch.manual_seed(fit.RECIPE["seed"])
        torch.cuda.manual_seed_all(fit.RECIPE["seed"])
        model = fit.SurvivalNet(encoder).cuda()
        arm_dir = args.output / name
        arm_dir.mkdir()
        stage_a = fit_arm(model, arrays, cache, train, validation, arm_dir, args.experiment_sha, name)
        result["arms"][name] = dict(stageA=stage_a, selected=stage_a["selectedEpoch"],
            metrics=fit.summarize(fit.predict(model, arrays, cache, validation, "cuda"), cache, validation),
            evaluation=fit.compare(reference_logits, fit.predict(model, arrays, cache, validation, "cuda"),
                                   cache, validation))
        fit.screen.composed.base.json_dump(args.output / "progress.json", result)
    result["selection"] = dict(referenceNll=reference_metrics["nll"], armNll={name: value["metrics"]["nll"] for name, value in result["arms"].items()},
        selectedArm=min(ARM_ORDER, key=lambda name: result["arms"][name]["metrics"]["nll"]))
    selected_arm = result["selection"]["selectedArm"]
    result["decision"] = compare_selected(result, reference_metrics)
    screen = fit.screen
    screen.composed.base.json_dump(args.output / "results.json", result)
    print(json.dumps(dict(decision=result["decision"]["decision"], output=str(args.output))), flush=True)


def subprocess_status():
    import subprocess
    return subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()


def compare_selected(result, reference_metrics):
    arm_name = result["selection"]["selectedArm"]
    evaluation = result["arms"][arm_name]["evaluation"]
    passed = dict(evaluation["gatesPassed"])
    if set(passed) != set(GATES) | {"validity"}:
        raise ValueError("selected arm is missing required gates")
    return dict(arm=arm_name, thresholds=GATES, gatesPassed=passed,
                decision="SURVIVAL_DEEPSET_SWEEP_GO" if all(passed.values())
                else "SURVIVAL_DEEPSET_SWEEP_REJECTED", stageBEvaluated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/potion-trajectory-v2"))
    parser.add_argument("--reference-component", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/full-union-survival-v1/component.pt"))
    parser.add_argument("--deepset-run", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916"))
    parser.add_argument("--deepset-evidence", type=Path, default=ROOT / "docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-sha", default=BASELINE_SHA)
    parser.add_argument("--experiment-sha", required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
