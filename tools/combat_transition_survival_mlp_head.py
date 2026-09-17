#!/usr/bin/env python3
"""Frozen-encoder nonlinear survival-head diagnostic; no TEST inference."""
from __future__ import annotations

import argparse
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

from tools import combat_transition_survival_mlp as mlp
from tools import combat_transition_survival_deepset_train as fit
from tools import combat_transition_survival_platt as platt

RECIPE = dict(mlp.RECIPE, training='strong-WD epoch-20 encoder frozen; fresh MLP survival head only',
              schema='survival_mlp_head_only_v1')


def freeze_encoder(model):
    model.encoder.requires_grad_(False)
    return model


def head_optimizer(model):
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=RECIPE['headLr'],
                                  weight_decay=RECIPE['weightDecay'])
    encoder_ids = {id(parameter) for parameter in model.encoder.parameters()}
    head_ids = {id(parameter) for parameter in model.head.parameters()}
    actual = {id(parameter) for group in optimizer.param_groups for parameter in group['params']}
    if actual != head_ids or encoder_ids & actual:
        raise ValueError('optimizer must contain exactly trainable head parameters')
    proof = dict(exactHeadParameterIds=True, encoderParameterIdsExcluded=True, frozenEncoder=True,
                 parameters=sum(parameter.numel() for parameter in model.head.parameters()),
                 lr=RECIPE['headLr'], weightDecay=RECIPE['weightDecay'])
    return optimizer, proof


def train(model, arrays, cache, train_ids, validation, output, sha, device='cuda'):
    initial_encoder = fit.screen.state_digest(model.encoder.state_dict())
    optimizer, proof = head_optimizer(model)
    generator = np.random.default_rng(RECIPE['seed'])
    history, best, best_epoch = [], float('inf'), 0
    for epoch in range(1, RECIPE['maxEpochs'] + 1):
        started = time.perf_counter()
        order = generator.permutation(train_ids)
        total = 0.
        model.train()
        for start in range(0, len(order), RECIPE['batch']):
            batch = order[start:start + RECIPE['batch']]
            optimizer.zero_grad(set_to_none=True)
            logits = model(mlp.fit.inputs_for(arrays, cache, batch, device, 0))
            labels = torch.as_tensor(cache['win'][batch], dtype=torch.float32, device=device)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
            if not torch.isfinite(logits).all() or not torch.isfinite(loss):
                raise ValueError('nonfinite TRAIN logits/loss')
            loss.backward()
            gradients = [parameter.grad for parameter in model.head.parameters()]
            if not all(gradient is not None and torch.isfinite(gradient).all() for gradient in gradients):
                raise ValueError('invalid head gradients')
            if any(parameter.grad is not None for parameter in model.encoder.parameters()):
                raise ValueError('encoder gradient produced despite frozen parameters')
            torch.nn.utils.clip_grad_norm_(model.head.parameters(), RECIPE['gradientClip'], error_if_nonfinite=True)
            optimizer.step()
            total += float(loss.detach()) * len(batch)
        if fit.screen.state_digest(model.encoder.state_dict()) != initial_encoder:
            raise ValueError('frozen encoder mutated')
        metrics = fit.summarize(fit.predict(model, arrays, cache, validation, device), cache, validation)
        entry = dict(epoch=epoch, trainNll=total / len(train_ids), validation=metrics,
                     seconds=time.perf_counter() - started, batchOrderSha256=fit.screen.array_digest(order))
        history.append(entry)
        if fit.strict_minimum(metrics['nll'], best):
            best, best_epoch = metrics['nll'], epoch
            torch.save(dict(stateDict=model.state_dict(), selectedEpoch=epoch, experimentSha=sha,
                            recipe=RECIPE, encoderStateSha256=initial_encoder), output / 'selected.pt')
        fit.screen.composed.base.json_dump(output / 'progress.json', dict(history=history, selectedEpoch=best_epoch))
        print(json.dumps(dict(epoch=epoch, nll=metrics['nll'], brier=metrics['brier'], selectedEpoch=best_epoch)), flush=True)
        if fit.should_stop(epoch, best_epoch):
            break
    payload = torch.load(output / 'selected.pt', map_location=device, weights_only=False)
    model.load_state_dict(payload['stateDict'], strict=True)
    return dict(history=history, selectedEpoch=best_epoch, completedEpochs=epoch,
                stoppingReason='patience' if fit.should_stop(epoch, best_epoch) else 'cap',
                encoderStateSha256=initial_encoder, optimizerScope=proof)


def run(args):
    if args.output.exists():
        raise ValueError('refusing output overwrite')
    if args.experiment_sha != fit.screen.current_head() or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('requires frozen clean execution SHA')
    if not torch.cuda.is_available():
        raise ValueError('CUDA required')
    checkpoint = platt.RUNS / 'survival-specific-deepset-sweep-20260917-final/strongWd/selected.pt'
    if fit.screen.digest(checkpoint) != platt.CHECKPOINT_SHA:
        raise ValueError('strong-WD checkpoint differs')
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    cache, arrays, population, provenance = fit.load_population(args)
    train_ids = np.flatnonzero(cache['split'] == 0)
    validation = np.flatnonzero(cache['split'] == 1)
    encoder, _ = fit.screen.load_candidate_encoder(args)
    model = fit.SurvivalNet(encoder)
    model.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=False)['stateDict'], strict=True)
    model.cuda()
    encoder_sha = fit.screen.state_digest(model.encoder.state_dict())
    linear_logits = fit.predict(model, arrays, cache, validation, 'cuda')
    reference_encoder, reference_head, _ = fit.screen.load_reference(args)
    reference = fit.SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = fit.predict(reference, arrays, cache, validation, 'cuda')
    baseline = fit.compare(reference_logits, linear_logits, cache, validation)
    if abs(baseline['metrics']['DeepSets']['nll'] - .06293081492185593) > 1e-7:
        raise ValueError('strong-WD metric mismatch')
    if abs(baseline['metrics']['Attention']['nll'] - fit.screen.REFERENCE_NLL) > 1e-7:
        raise ValueError('Attention metric mismatch')
    mlp.replace_head(model)
    if fit.screen.state_digest(model.encoder.state_dict()) != encoder_sha:
        raise ValueError('head replacement changed encoder')
    freeze_encoder(model).cuda()
    args.output.mkdir(parents=True)
    result = train(model, arrays, cache, train_ids, validation, args.output, args.experiment_sha)
    if fit.screen.state_digest(model.encoder.state_dict()) != encoder_sha:
        raise ValueError('frozen encoder mutated during training')
    logits = fit.predict(model, arrays, cache, validation, 'cuda')
    evaluation = fit.compare(reference_logits, logits, cache, validation)
    if abs(evaluation['metrics']['DeepSets']['nll'] - min(item['validation']['nll'] for item in result['history'])) > 1e-8:
        raise ValueError('selected checkpoint NLL mismatch')
    np.savez(args.output / 'validation_predictions.npz', rowIds=validation, source=cache['source'][validation],
             labels=cache['win'][validation], logits=logits, referenceLogits=reference_logits, linearLogits=linear_logits)
    result.update(evaluation=evaluation, baseline=baseline, speedScreen=None,
                  initialization=dict(checkpoint=str(checkpoint), checkpointSha256=platt.CHECKPOINT_SHA,
                                      encoderSha256=encoder_sha, headParameters=4225, addedParameters=4160),
                  experimentSha=args.experiment_sha, recipe=RECIPE, population=population, provenance=provenance,
                  checkpoint=str(args.output / 'selected.pt'), checkpointSha256=fit.screen.digest(args.output / 'selected.pt'),
                  predictionsSha256=fit.screen.digest(args.output / 'validation_predictions.npz'),
                  testEncodedRows=0, testInferenceRows=0, testScoredRows=0,
                  environment=dict(torch=torch.__version__, cuda=torch.version.cuda, gpu=torch.cuda.get_device_name(),
                                   threads=4, tf32=False))
    if all(evaluation['gatesPassed'].values()):
        result['speedScreen'] = fit.speed_screen(reference, model, arrays, cache, validation)
    fit.screen.composed.base.json_dump(args.output / 'results.json', result)
    print(json.dumps(dict(decision=evaluation['decision'], output=str(args.output))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--experiment-sha', required=True)
    parser.add_argument('--cache', type=Path, default=platt.RUNS / 'near-full-combat-support-20260914/potion-trajectory-v2')
    parser.add_argument('--reference-component', type=Path, default=platt.RUNS / 'near-full-combat-support-20260914/full-union-survival-v1/component.pt')
    parser.add_argument('--deepset-run', type=Path, default=platt.RUNS / 'shared-transition-deepset-distill-corrected-20260916')
    parser.add_argument('--deepset-evidence', type=Path, default=ROOT / 'docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json')
    run(parser.parse_args())
