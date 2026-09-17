#!/usr/bin/env python3
"""One scratch width-96 survival DeepSets experiment, without TEST inference."""
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

from tools import combat_transition_survival_deepset_train as fit

RUNS = Path('/home/philippherrmann/sts_sweep/runs')
BASE_SHA = '6fa601d9429db1a1a266e34c63252ce4861f9d5a'
RECIPE = dict(fit.RECIPE, schema='survival_wide96_v1', weightDecay=1e-3,
              architecture='entity outputs 96; concat 384; trunk 384->192->96; head 96->1',
              training='from scratch, survival BCE only',
              normalization='all TRAIN rows, fixed throughout fitting')


def build_model(mean, std):
    torch.manual_seed(RECIPE['seed'])
    encoder = fit.screen.surrogate.DeepSetsEncoder(torch.nn, torch, mean, std).net
    for name in ('card_mlp', 'relic_mlp', 'potion_mlp'):
        input_width = getattr(encoder, name)[0].in_features
        setattr(encoder, name, torch.nn.Sequential(torch.nn.Linear(input_width, 96),
                torch.nn.ReLU(), torch.nn.Linear(96, 96), torch.nn.ReLU()))
    encoder.global_mlp = torch.nn.Sequential(
        torch.nn.Linear(encoder.global_mlp[0].in_features, 96), torch.nn.ReLU())
    encoder.trunk = torch.nn.Sequential(torch.nn.Linear(384, 192), torch.nn.ReLU(),
                                       torch.nn.Linear(192, 96), torch.nn.ReLU())
    model = fit.SurvivalNet(encoder)
    model.head = torch.nn.Linear(96, 1)
    return model


def normalization(arrays, cache, train):
    if not len(train) or not np.array_equal(train, np.flatnonzero(cache['split'] == 0)):
        raise ValueError('normalization requires all and only TRAIN rows')
    values = arrays['globals_continuous'][cache['ids'][train]]
    if not np.isfinite(values).all():
        raise ValueError('nonfinite normalization inputs')
    return values.mean(0), values.std(0)


def train_model(model, arrays, cache, train, validation, output, sha, device='cuda'):
    optimizer, proof = fit.make_optimizer(model)
    for group, record in zip(optimizer.param_groups, proof['groups']):
        group['weight_decay'] = RECIPE['weightDecay']
        record['weightDecay'] = group['weight_decay']
    generator = np.random.default_rng(RECIPE['seed'])
    norm_sha = fit.normalization_digest(model.encoder)
    history, best_nll, best_epoch = [], float('inf'), 0
    for epoch in range(1, RECIPE['maxEpochs'] + 1):
        started = time.perf_counter()
        order = generator.permutation(train)
        total = 0.
        for start in range(0, len(order), RECIPE['batch']):
            batch = order[start:start + RECIPE['batch']]
            loss, _ = fit.update_batch(model, optimizer,
                fit.inputs_for(arrays, cache, batch, device, 0),
                torch.as_tensor(cache['win'][batch], dtype=torch.float32, device=device))
            total += loss * len(batch)
        metrics = fit.summarize(fit.predict(model, arrays, cache, validation, device), cache, validation)
        if fit.normalization_digest(model.encoder) != norm_sha:
            raise ValueError('normalization changed')
        entry = dict(epoch=epoch, trainNll=total / len(train), validation=metrics,
                     seconds=time.perf_counter() - started, batchOrderSha256=fit.screen.array_digest(order))
        history.append(entry)
        if fit.strict_minimum(metrics['nll'], best_nll):
            best_nll, best_epoch = metrics['nll'], epoch
            torch.save(dict(stateDict=model.state_dict(), selectedEpoch=epoch, recipe=RECIPE,
                            experimentSha=sha), output / 'selected.pt')
        fit.screen.composed.base.json_dump(output / 'progress.json', dict(history=history, selectedEpoch=best_epoch))
        print(json.dumps(dict(epoch=epoch, nll=metrics['nll'], brier=metrics['brier'], selectedEpoch=best_epoch)), flush=True)
        if fit.should_stop(epoch, best_epoch):
            break
    model.load_state_dict(torch.load(output / 'selected.pt', map_location=device, weights_only=False)['stateDict'])
    return dict(history=history, selectedEpoch=best_epoch, completedEpochs=epoch,
                stoppingReason='patience' if fit.should_stop(epoch, best_epoch) else 'cap', optimizerScope=proof)


def run(args):
    if args.output.exists():
        raise ValueError('refusing output overwrite')
    if args.experiment_sha != fit.screen.current_head() or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('requires exact clean execution SHA')
    if not torch.cuda.is_available():
        raise ValueError('CUDA required')
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    cache, arrays, population, provenance = fit.load_population(args)
    train, validation = (np.flatnonzero(cache['split'] == split) for split in (0, 1))
    mean, std = normalization(arrays, cache, train)
    reference_encoder, reference_head, _ = fit.screen.load_reference(args)
    reference = fit.SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = fit.predict(reference, arrays, cache, validation, 'cuda')
    if abs(fit.summarize(reference_logits, cache, validation)['nll'] - fit.screen.REFERENCE_NLL) > 1e-7:
        raise ValueError('reference NLL does not reproduce')
    model = build_model(mean, std).cuda()
    initialization = dict(encoderSha256=fit.screen.state_digest(model.encoder.state_dict()),
                          headSha256=fit.screen.state_digest(model.head.state_dict()),
                          normalizationSha256=fit.normalization_digest(model.encoder),
                          normalizationRows=len(train), mean=mean.tolist(), std=std.tolist(),
                          rowIdsSha256=fit.screen.array_digest(cache['ids'][train]), checkpointLoaded=False)
    args.output.mkdir(parents=True)
    result = train_model(model, arrays, cache, train, validation, args.output, args.experiment_sha)
    logits = fit.predict(model, arrays, cache, validation, 'cuda')
    evaluation = fit.compare(reference_logits, logits, cache, validation)
    if evaluation['metrics']['DeepSets']['nll'] != min(entry['validation']['nll'] for entry in result['history']):
        raise ValueError('reloaded selected checkpoint NLL mismatch')
    np.savez(args.output / 'validation_predictions.npz', rowIds=validation, source=cache['source'][validation],
             logits=logits, labels=cache['win'][validation], referenceLogits=reference_logits)
    result.update(evaluation=evaluation, initialization=initialization, speedScreen=None,
                  recipe=RECIPE, baselineSha=BASE_SHA, experimentSha=args.experiment_sha,
                  population=population, provenance=provenance, parameters=sum(parameter.numel() for parameter in model.parameters()),
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
    parser.add_argument('--cache', type=Path, default=RUNS / 'near-full-combat-support-20260914/potion-trajectory-v2')
    parser.add_argument('--reference-component', type=Path, default=RUNS / 'near-full-combat-support-20260914/full-union-survival-v1/component.pt')
    run(parser.parse_args())
