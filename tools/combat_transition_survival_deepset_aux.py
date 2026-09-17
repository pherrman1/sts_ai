#!/usr/bin/env python3
"""Paired PR205-warm versus scratch DeepSets survival/HP recipe; no TEST."""
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
RECIPE = dict(seed=20260911, batch=2048, maxEpochs=12, patience=3,
              optimizer='AdamW', lr=1e-3, weightDecay=1e-4, gradientClip=1.,
              precision='FP32', normalization='all TRAIN rows, fixed during fit',
              loss='mean BCE survival + mean survivor-only MSE(sigmoid HP, postHP/postMaxHP)',
              selection='earliest strict minimum VALIDATION survival NLL',
              hpMetrics='diagnostic only', arms=['warm', 'scratch'])


class JointNet(fit.SurvivalNet):
    def __init__(self, encoder):
        super().__init__(encoder)
        self.hp = torch.nn.Linear(64, 1)

    def joint(self, inputs):
        features = self.encoder(*inputs)
        return self.head(features).flatten(), self.hp(features).flatten()


def normalization(arrays, cache, train):
    if not np.array_equal(train, np.flatnonzero(cache['split'] == 0)):
        raise ValueError('normalization requires all and only TRAIN rows')
    values = arrays['globals_continuous'][cache['ids'][train]]
    if not np.isfinite(values).all():
        raise ValueError('nonfinite normalization inputs')
    return values.mean(0), values.std(0)


def initialize(mean, std, warm_state=None):
    torch.manual_seed(RECIPE['seed'])
    encoder = fit.screen.surrogate.DeepSetsEncoder(torch.nn, torch, mean, std).net
    model = JointNet(encoder)
    if warm_state is not None:
        encoder.load_state_dict(warm_state, strict=True)
        with torch.no_grad():
            encoder.scalar_mean.copy_(torch.as_tensor(mean))
            encoder.scalar_inv.copy_(torch.as_tensor(1. / np.maximum(std, 1e-6)))
    return model


def joint_loss(logits, hp_logits, labels, hp_targets):
    survival = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
    survivors = labels > .5
    auxiliary = hp_logits.sum() * 0.
    if survivors.any():
        targets = hp_targets[survivors]
        if not torch.isfinite(targets).all() or not ((targets >= 0.) & (targets <= 1.)).all():
            raise ValueError('invalid surviving HP fraction')
        auxiliary = torch.nn.functional.mse_loss(torch.sigmoid(hp_logits[survivors]), targets)
    return survival, auxiliary


def hp_metrics(model, arrays, cache, validation, device):
    survivors = validation[cache['win'][validation].astype(bool)]
    predictions = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(survivors), RECIPE['batch']):
            batch = survivors[start:start + RECIPE['batch']]
            _, logits = model.joint(fit.inputs_for(arrays, cache, batch, device, 1))
            predictions.append(torch.sigmoid(logits).cpu().numpy())
    predicted = np.concatenate(predictions)
    targets = arrays['y_hp'][cache['ids'][survivors]]
    residual = predicted.astype(float) - targets
    if not np.isfinite(residual).all():
        raise ValueError('nonfinite HP diagnostics')
    return dict(rows=len(survivors), mae=float(np.abs(residual).mean()),
                rmse=float(np.sqrt(np.square(residual).mean())), bias=float(residual.mean()))


def fit_arm(model, arrays, cache, train, validation, output, experiment_sha, device='cuda'):
    optimizer = torch.optim.AdamW(model.parameters(), lr=RECIPE['lr'], weight_decay=RECIPE['weightDecay'])
    expected = {id(parameter) for parameter in model.parameters()}
    actual = [id(parameter) for group in optimizer.param_groups for parameter in group['params']]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('optimizer parameter scope differs')
    initial_norm = fit.normalization_digest(model.encoder)
    generator = np.random.default_rng(RECIPE['seed'])
    history, best_nll, best_epoch = [], float('inf'), 0
    for epoch in range(1, RECIPE['maxEpochs'] + 1):
        started = time.perf_counter()
        order = generator.permutation(train)
        survival_sum, hp_sum, winning_rows = 0., 0., 0
        model.train()
        for start in range(0, len(order), RECIPE['batch']):
            batch = order[start:start + RECIPE['batch']]
            logits, hp_logits = model.joint(fit.inputs_for(arrays, cache, batch, device, 0))
            labels = torch.as_tensor(cache['win'][batch], dtype=torch.float32, device=device)
            hp_targets = torch.as_tensor(arrays['y_hp'][cache['ids'][batch]], device=device)
            survival, auxiliary = joint_loss(logits, hp_logits, labels, hp_targets)
            loss = survival + auxiliary
            if not torch.isfinite(loss):
                raise ValueError('nonfinite training loss')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), RECIPE['gradientClip'], error_if_nonfinite=True)
            optimizer.step()
            count = int((labels > .5).sum())
            survival_sum += float(survival.detach()) * len(batch)
            hp_sum += float(auxiliary.detach()) * count
            winning_rows += count
        metrics = fit.summarize(fit.predict(model, arrays, cache, validation, device), cache, validation)
        diagnostics = hp_metrics(model, arrays, cache, validation, device)
        if fit.normalization_digest(model.encoder) != initial_norm:
            raise ValueError('TRAIN normalization mutated')
        entry = dict(epoch=epoch, trainSurvivalNll=survival_sum / len(train),
                     trainWinningHpMse=hp_sum / winning_rows, validation=metrics,
                     validationWinningHp=diagnostics, seconds=time.perf_counter() - started,
                     batchOrderSha256=fit.screen.array_digest(order))
        history.append(entry)
        if fit.strict_minimum(metrics['nll'], best_nll):
            best_nll, best_epoch = metrics['nll'], epoch
            torch.save(dict(stateDict=model.state_dict(), selectedEpoch=epoch,
                            experimentSha=experiment_sha, recipe=RECIPE), output / 'selected.pt')
        fit.screen.composed.base.json_dump(output / 'progress.json', dict(history=history, selectedEpoch=best_epoch))
        print(json.dumps(dict(arm=output.name, epoch=epoch, nll=metrics['nll'], brier=metrics['brier'],
                              selectedEpoch=best_epoch)), flush=True)
        if epoch - best_epoch >= RECIPE['patience']:
            break
    payload = torch.load(output / 'selected.pt', map_location=device, weights_only=False)
    model.load_state_dict(payload['stateDict'], strict=True)
    return dict(history=history, selectedEpoch=best_epoch, completedEpochs=epoch,
                stoppingReason='patience' if epoch - best_epoch >= RECIPE['patience'] else 'cap',
                optimizerScope=dict(exactParameterIds=True, parameters=sum(parameter.numel() for parameter in model.parameters()),
                                    lr=RECIPE['lr'], weightDecay=RECIPE['weightDecay']),
                checkpointSha256=fit.screen.digest(output / 'selected.pt'), checkpoint=str(output / 'selected.pt'))


def run(args):
    if args.output.exists():
        raise ValueError('refusing output overwrite')
    if args.experiment_sha != fit.screen.current_head() or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('requires exact frozen clean execution SHA')
    if not torch.cuda.is_available():
        raise ValueError('CUDA required')
    torch.set_num_threads(8)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    cache, arrays, population, provenance = fit.load_population(args)
    train, validation = (np.flatnonzero(cache['split'] == split) for split in (0, 1))
    mean, std = normalization(arrays, cache, train)
    warm_encoder, binding = fit.screen.load_candidate_encoder(args)
    warm_state = {key: value.detach().cpu().clone() for key, value in warm_encoder.state_dict().items()}
    reference_encoder, reference_head, _ = fit.screen.load_reference(args)
    reference = fit.SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = fit.predict(reference, arrays, cache, validation, 'cuda')
    if abs(fit.summarize(reference_logits, cache, validation)['nll'] - fit.screen.REFERENCE_NLL) > 1e-7:
        raise ValueError('Attention reference does not reproduce')
    args.output.mkdir(parents=True)
    receipt = dict(schema='survival_deepset_aux_two_arm_v1', experimentSha=args.experiment_sha,
                   recipe=RECIPE, gates=fit.GATES, population=population, provenance=provenance,
                   warmStart=binding, normalization=dict(rows=len(train), mean=mean.tolist(), std=std.tolist(),
                       rowIdsSha256=fit.screen.array_digest(cache['ids'][train])), arms={},
                   testEncodedRows=0, testInferenceRows=0, testScoredRows=0,
                   environment=dict(torch=torch.__version__, cuda=torch.version.cuda,
                                    gpu=torch.cuda.get_device_name(), cpuThreads=8, tf32=False))
    for arm in RECIPE['arms']:
        output = args.output / arm
        output.mkdir()
        model = initialize(mean, std, warm_state if arm == 'warm' else None).cuda()
        initialization = dict(encoderSha256=fit.screen.state_digest(model.encoder.state_dict()),
                              headSha256=fit.screen.state_digest(model.head.state_dict()),
                              hpHeadSha256=fit.screen.state_digest(model.hp.state_dict()),
                              normalizationSha256=fit.normalization_digest(model.encoder))
        result = fit_arm(model, arrays, cache, train, validation, output, args.experiment_sha)
        logits = fit.predict(model, arrays, cache, validation, 'cuda')
        result.update(initialization=initialization, evaluation=fit.compare(reference_logits, logits, cache, validation),
                      winningHp=hp_metrics(model, arrays, cache, validation, 'cuda'), speedScreen=None)
        if abs(result['evaluation']['metrics']['DeepSets']['nll'] - min(entry['validation']['nll'] for entry in result['history'])) > 1e-8:
            raise ValueError('selected checkpoint NLL mismatch')
        np.savez(output / 'validation_predictions.npz', rowIds=validation, source=cache['source'][validation],
                 logits=logits, referenceLogits=reference_logits, labels=cache['win'][validation])
        result['predictionsSha256'] = fit.screen.digest(output / 'validation_predictions.npz')
        if all(result['evaluation']['gatesPassed'].values()):
            torch.set_num_threads(4)
            result['speedScreen'] = fit.speed_screen(reference, model, arrays, cache, validation)
            torch.set_num_threads(8)
        receipt['arms'][arm] = result
        fit.screen.composed.base.json_dump(args.output / 'progress.json', receipt)
    warm, scratch = (receipt['arms'][arm] for arm in RECIPE['arms'])
    for key in ('headSha256', 'hpHeadSha256', 'normalizationSha256'):
        if warm['initialization'][key] != scratch['initialization'][key]:
            raise ValueError('paired initialization mismatch')
    for left, right in zip(warm['history'], scratch['history']):
        if left['batchOrderSha256'] != right['batchOrderSha256']:
            raise ValueError('paired order mismatch')
    receipt['pairedChecksPassed'] = True
    receipt['selectedArm'] = min(RECIPE['arms'], key=lambda arm: receipt['arms'][arm]['evaluation']['metrics']['DeepSets']['nll'])
    fit.screen.composed.base.json_dump(args.output / 'results.json', receipt)
    print(json.dumps(dict(output=str(args.output), selectedArm=receipt['selectedArm'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--experiment-sha', required=True)
    parser.add_argument('--cache', type=Path, default=RUNS / 'near-full-combat-support-20260914/potion-trajectory-v2')
    parser.add_argument('--reference-component', type=Path, default=RUNS / 'near-full-combat-support-20260914/full-union-survival-v1/component.pt')
    parser.add_argument('--deepset-run', type=Path, default=RUNS / 'shared-transition-deepset-distill-corrected-20260916')
    parser.add_argument('--deepset-evidence', type=Path, default=ROOT / 'docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json')
    run(parser.parse_args())
