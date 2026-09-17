#!/usr/bin/env python3
"""One fixed, warm-started survival DeepSets experiment; no TEST inference."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_deepset_survival as screen


BASELINE_SHA = "be5b6ac2c9914b0a56244f2522b7573f81360067"
RECIPE = dict(
    seed=20260912, batch=512, precision="FP32", optimizer="AdamW",
    encoderLr=1e-4, headLr=1e-3, weightDecay=1e-4, gradientClip=1.0,
    maxEpochs=40, minEpochs=12, patience=6,
    loss="unweighted BCEWithLogitsLoss; 1=survived, 0=death",
    selection="earliest strict minimum VALIDATION NLL",
    normalization="unchanged PR205 scalar_mean/scalar_inv buffers",
    training="PR205 encoder plus fresh Linear(64,1), TRAIN only",
)
GATES = dict(nllRelative=0.02, brierRelative=0.05,
             deathNllRelative=0.10, lowPreHpNllRelative=0.10)


class SurvivalNet(torch.nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder.requires_grad_(True)
        self.head = torch.nn.Linear(64, 1)

    def forward(self, inputs):
        return self.head(self.encoder(*inputs)).flatten()


def normalization_digest(encoder):
    return screen.state_digest({name: value for name, value in encoder.state_dict().items()
                                if name in ("scalar_mean", "scalar_inv")})


def make_optimizer(model):
    optimizer = torch.optim.AdamW([
        dict(params=model.encoder.parameters(), lr=RECIPE["encoderLr"]),
        dict(params=model.head.parameters(), lr=RECIPE["headLr"]),
    ], weight_decay=RECIPE["weightDecay"])
    expected = {id(parameter) for parameter in model.parameters()}
    actual = [id(parameter) for group in optimizer.param_groups for parameter in group["params"]]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("optimizer scope differs or contains duplicate parameters")
    if not all(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("candidate contains frozen parameters")
    proof = dict(exactParameterIds=True, duplicateParameterIds=False, groups=[
        dict(name=name, lr=group["lr"], tensors=len(group["params"]),
             elements=sum(parameter.numel() for parameter in group["params"]))
        for name, group in zip(("encoder", "survivalHead"), optimizer.param_groups)
    ], parameterNames=[name for name, _ in model.named_parameters()])
    return optimizer, proof


def validate_population(cache, arrays, members):
    if not np.array_equal(cache["source"], arrays["sourceSeed"]):
        raise ValueError("prepared/cache source identity differs")
    if not np.array_equal(cache["win"], arrays["y_win"]):
        raise ValueError("prepared/cache survival labels differ")
    population = {}
    for split, name, rows, sources in ((0, "train", 408183, 19986),
                                       (1, "validation", 50406, 2496),
                                       (2, "test", 51441, 2517)):
        indices = np.flatnonzero(cache["split"] == split)
        source_ids = np.unique(cache["source"][indices])
        if len(indices) != rows or len(source_ids) != sources:
            raise ValueError(f"{name} population differs")
        if not np.array_equal(source_ids, np.sort(members[name])):
            raise ValueError(f"{name} original source split differs")
        population[name.upper()] = dict(rows=rows, sources=sources,
            rowIdsSha256=screen.array_digest(cache["ids"][indices]),
            sourceIdsSha256=screen.array_digest(source_ids))
    source_sets = [set(members[name]) for name in ("train", "validation", "test")]
    if any(source_sets[first] & source_sets[second]
           for first, second in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("source splits overlap")
    population["TEST"].update(encodedRows=0, inferenceRows=0, scoredRows=0)
    return population


def load_population(args):
    cache, preparation = screen.load_cache(args)
    prepared = screen.composed_eval.PREPARED
    corpus = Path("/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl")
    split = Path("/home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/split_manifest.json")
    verified = {}
    for path in (corpus, split, prepared / "prepared.npz",
                 prepared / "prepared_manifest.json", prepared / "target_spec.json"):
        expected = preparation["hashes"].get(str(path))
        if not expected or screen.digest(path) != expected:
            raise ValueError(f"input provenance mismatch: {path}")
        verified[str(path)] = expected
    if verified[str(corpus)] != screen.CORPUS_SHA:
        raise ValueError("frozen corpus differs")
    arrays, _ = screen.load_prepared()
    population = validate_population(cache, arrays, json.loads(split.read_text())["members"])
    return cache, arrays, population, dict(verifiedFiles=verified,
        preparationSha256=screen.digest(args.cache / "preparation.json"),
        preparationCacheSha256=screen.PREPARATION_CACHE_SHA, sourceSha=screen.SOURCE_SHA)


def inputs_for(arrays, cache, indices, device, allowed_split):
    if allowed_split not in (0, 1) or not len(indices) or not np.all(cache["split"][indices] == allowed_split):
        raise ValueError("empty batch or forbidden split, including TEST")
    return screen.surrogate._torch_inputs(arrays, cache["ids"][indices], device,
                                          torch, trim_padding=True)


def predict(model, arrays, cache, indices, device):
    model.eval()
    values = []
    with torch.inference_mode():
        for start in range(0, len(indices), RECIPE["batch"]):
            batch = indices[start:start + RECIPE["batch"]]
            logits = model(inputs_for(arrays, cache, batch, device, 1))
            if not torch.isfinite(logits).all():
                raise ValueError("nonfinite VALIDATION logits")
            values.append(logits.cpu().numpy())
    return np.concatenate(values)


def summarize(logits, cache, indices):
    return screen.metrics(torch.nn.Identity(), logits[:, None], cache, indices,
                          "cpu", np.arange(len(indices)))


def compare(reference, candidate, cache, validation, population_bound=True):
    metrics = {"Attention": summarize(reference, cache, validation),
               "DeepSets": summarize(candidate, cache, validation)}
    slices = screen.validation_slices(torch.nn.Identity(), torch.nn.Identity(),
        reference[:, None], candidate[:, None], cache, validation, validation, "cpu")
    relative = dict(
        nllRelative=metrics["DeepSets"]["nll"] / metrics["Attention"]["nll"] - 1,
        brierRelative=metrics["DeepSets"]["brier"] / metrics["Attention"]["brier"] - 1,
        deathNllRelative=slices["deaths"]["B"]["nll"] / slices["deaths"]["A"]["nll"] - 1,
        lowPreHpNllRelative=slices["lowPreHp"]["B"]["nll"] / slices["lowPreHp"]["A"]["nll"] - 1,
    )
    validity = population_bound and all(value[key] for value in metrics.values() for key in
        ("finiteLogits", "finiteProbabilities", "probabilitiesInUnitInterval"))
    passed = {name: bool(relative[name] <= threshold) for name, threshold in GATES.items()}
    passed["validity"] = bool(validity)
    return dict(metrics=metrics, slices=slices, comparison=relative, thresholds=GATES,
                gatesPassed=passed, decision="SURVIVAL_DEEPSET_GO" if all(passed.values())
                else "SURVIVAL_DEEPSET_REJECTED")


def update_batch(model, optimizer, inputs, labels):
    model.train()
    optimizer.zero_grad(set_to_none=True)
    logits = model(inputs)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
    if not torch.isfinite(logits).all() or not torch.isfinite(loss):
        raise ValueError("nonfinite TRAIN logits/loss")
    loss.backward()
    norms = {}
    for name, module in (("encoder", model.encoder), ("head", model.head)):
        gradients = [parameter.grad for parameter in module.parameters()]
        if not all(gradient is not None and torch.isfinite(gradient).all() for gradient in gradients):
            raise ValueError(f"invalid {name} gradients")
        norms[name] = float(torch.sqrt(sum(gradient.square().sum() for gradient in gradients)))
    torch.nn.utils.clip_grad_norm_(model.parameters(), RECIPE["gradientClip"], error_if_nonfinite=True)
    optimizer.step()
    return float(loss.detach()), norms


def should_stop(epoch, best_epoch):
    return epoch >= RECIPE["minEpochs"] and epoch - best_epoch >= RECIPE["patience"]


def strict_minimum(value, best_value):
    if not np.isfinite(value):
        raise ValueError("nonfinite validation NLL cannot select a checkpoint")
    return value < best_value


def fit(model, arrays, cache, train, validation, output, experiment_sha):
    optimizer, proof = make_optimizer(model)
    generator = np.random.default_rng(RECIPE["seed"])
    best_nll, best_epoch = float("inf"), 0
    history = []
    initial_normalization = normalization_digest(model.encoder)
    for epoch in range(1, RECIPE["maxEpochs"] + 1):
        started = time.perf_counter()
        order = generator.permutation(train)
        total_loss = 0.0
        for start in range(0, len(order), RECIPE["batch"]):
            batch = order[start:start + RECIPE["batch"]]
            loss, _ = update_batch(model, optimizer, inputs_for(arrays, cache, batch, "cuda", 0),
                torch.as_tensor(cache["win"][batch], dtype=torch.float32, device="cuda"))
            total_loss += loss * len(batch)
        logits = predict(model, arrays, cache, validation, "cuda")
        validation_nll = summarize(logits, cache, validation)["nll"]
        if normalization_digest(model.encoder) != initial_normalization:
            raise ValueError("warm-start normalization buffers changed")
        entry = dict(epoch=epoch, trainNll=total_loss / len(train), validationNll=validation_nll,
                     seconds=time.perf_counter() - started, batchOrderSha256=screen.array_digest(order))
        history.append(entry)
        if strict_minimum(validation_nll, best_nll):
            best_nll, best_epoch = validation_nll, epoch
            torch.save(dict(stateDict=model.state_dict(), selectedEpoch=epoch,
                experimentSha=experiment_sha, recipe=RECIPE), output / "selected.pt")
        screen.composed.base.json_dump(output / "progress.json", dict(history=history,
            selectedEpoch=best_epoch, experimentSha=experiment_sha))
        print(json.dumps(entry), flush=True)
        if should_stop(epoch, best_epoch):
            break
    model.load_state_dict(torch.load(output / "selected.pt", map_location="cuda", weights_only=False)["stateDict"])
    return dict(history=history, selectedEpoch=best_epoch,
        stoppingReason="patience" if should_stop(epoch, best_epoch) else "max epoch",
        optimizationUncertainty=best_epoch == RECIPE["maxEpochs"], optimizerScope=proof)


def speed_screen(reference, candidate, arrays, cache, validation):
    inputs = inputs_for(arrays, cache, validation[:512], "cpu", 1)
    result = dict(rows=512, threads=4, precision="FP32", warmups=10, repetitions=100,
        rowIdsSha256=screen.array_digest(cache["ids"][validation[:512]]),
        convention="prebuilt trimmed tensors; inference_mode; MHA fastpath enabled; same process", timings={})
    with torch.inference_mode():
        for name, model in (("Attention", reference), ("DeepSets", candidate)):
            model.cpu().eval()
            result["timings"][name] = {}
            for label, forward in (("encoder", lambda: model.encoder(*inputs)),
                                    ("survival", lambda: model(inputs))):
                for _ in range(10):
                    forward()
                samples = []
                for _ in range(100):
                    started = time.perf_counter()
                    forward()
                    samples.append(1000 * (time.perf_counter() - started))
                result["timings"][name][label] = dict(medianMs=float(np.median(samples)))
    result["attentionOverDeepSetsSpeedup"] = {name:
        result["timings"]["Attention"][name]["medianMs"] /
        result["timings"]["DeepSets"][name]["medianMs"] for name in ("encoder", "survival")}
    result["scope"] = "Python implementation-level only; not native/OOC speedup"
    return result


def run(args):
    if args.output.exists():
        raise ValueError(f"refusing overwrite of {args.output}")
    if not torch.cuda.is_available():
        raise ValueError("CUDA is required for this fit")
    if args.command == "fit":
        if not args.experiment_sha or screen.current_head() != args.experiment_sha:
            raise ValueError("freeze and supply the exact implementation SHA before fitting")
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            raise ValueError("fit requires a clean implementation tree")
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.mha.set_fastpath_enabled(True)
    args.output.mkdir(parents=True)
    cache, arrays, population, provenance = load_population(args)
    train = np.flatnonzero(cache["split"] == 0)
    validation = np.flatnonzero(cache["split"] == 1)
    reference_encoder, reference_head, reference_fit = screen.load_reference(args)
    reference = SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = predict(reference, arrays, cache, validation, "cuda")
    reference_metrics = summarize(reference_logits, cache, validation)
    if abs(reference_metrics["nll"] - screen.REFERENCE_NLL) > 1e-6:
        raise ValueError(f"reference NLL did not reproduce: {reference_metrics['nll']}")
    print(json.dumps(dict(referenceNll=reference_metrics["nll"], referenceReproduced=True)), flush=True)
    encoder, binding = screen.load_candidate_encoder(args)
    payload = torch.load(args.deepset_run / "student.pt", map_location="cpu", weights_only=False)
    original_state = {key.removeprefix("encoder."): value for key, value in payload["stateDict"].items()
                      if key.startswith("encoder.")}
    if screen.state_digest(original_state) != screen.state_digest(encoder.state_dict()):
        raise ValueError("warm-start encoder state differs")
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"])
    model = SurvivalNet(encoder).cuda()
    initial = copy.deepcopy(model.state_dict())
    initialization = dict(encoderSha256=screen.state_digest(encoder.state_dict()),
        headSha256=screen.state_digest(model.head.state_dict()),
        normalizationSha256=normalization_digest(encoder), exactEncoderLoad=True, binding=binding)
    optimizer, proof = make_optimizer(model)
    batch = train[:32]
    loss, gradients = update_batch(model, optimizer, inputs_for(arrays, cache, batch, "cuda", 0),
        torch.as_tensor(cache["win"][batch], dtype=torch.float32, device="cuda"))
    if not all(np.isfinite(norm) and norm > 0 for norm in gradients.values()):
        raise ValueError("32-row encoder/head gradients must be finite and nonzero")
    for batch in (train[32:544], train[544:1056]):
        update_batch(model, optimizer, inputs_for(arrays, cache, batch, "cuda", 0),
            torch.as_tensor(cache["win"][batch], dtype=torch.float32, device="cuda"))
    smoke_logits = predict(model, arrays, cache, validation[:512], "cuda")
    smoke = dict(rows=32, loss=loss, gradientNorms=gradients, optimizerScope=proof,
        additionalTrainBatchRows=[512, 512], validation=summarize(smoke_logits, cache, validation[:512]))
    model.load_state_dict(initial)
    if screen.state_digest(model.state_dict()) != screen.state_digest(initial):
        raise ValueError("smoke state did not restore")
    if normalization_digest(model.encoder) != initialization["normalizationSha256"]:
        raise ValueError("initial normalization changed during smoke")
    result = dict(schema="survival_specific_deepset_v1", baselineSha=args.base_sha,
        experimentSha=screen.current_head(), recipe=RECIPE, fixedGates=GATES,
        implementationFileSha256=screen.digest(Path(__file__)),
        population=population, provenance=provenance, initialization=initialization, smoke=smoke,
        reference=dict(componentSha256=screen.REFERENCE_COMPONENT_SHA, metrics=reference_metrics,
                       originalNll=screen.REFERENCE_NLL, fit=reference_fit),
        testEncodedRows=0, testInferenceRows=0, testScoredRows=0,
        environment=dict(torch=torch.__version__, cuda=torch.version.cuda,
                         gpu=torch.cuda.get_device_name(), cpuThreads=4, tf32=False))
    if args.command == "smoke":
        result["decision"] = "SMOKE_PASSED_NOT_QUALIFIED"
    else:
        result["fit"] = fit(model, arrays, cache, train, validation, args.output, args.experiment_sha)
        candidate_logits = predict(model, arrays, cache, validation, "cuda")
        result.update(compare(reference_logits, candidate_logits, cache, validation))
        result["selected"] = dict(checkpointSha256=screen.digest(args.output / "selected.pt"),
            encoderSha256=screen.state_digest(model.encoder.state_dict()),
            normalizationSha256=normalization_digest(model.encoder))
        np.savez(args.output / "validation_predictions.npz", rowIds=cache["ids"][validation],
                 attentionLogits=reference_logits, deepsetLogits=candidate_logits)
        result["validationPredictionsSha256"] = screen.digest(args.output / "validation_predictions.npz")
        if result["decision"] == "SURVIVAL_DEEPSET_GO":
            result["speedScreen"] = speed_screen(reference, model, arrays, cache, validation)
        else:
            result["speedScreen"] = dict(skipped="quality gate rejected")
    screen.composed.base.json_dump(args.output / "results.json", result)
    print(json.dumps(dict(decision=result["decision"], output=str(args.output))), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke", "fit"))
    parser.add_argument("--cache", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/potion-trajectory-v2"))
    parser.add_argument("--reference-component", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/full-union-survival-v1/component.pt"))
    parser.add_argument("--deepset-run", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916"))
    parser.add_argument("--deepset-evidence", type=Path, default=ROOT / "docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-sha", default=BASELINE_SHA)
    parser.add_argument("--experiment-sha")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
