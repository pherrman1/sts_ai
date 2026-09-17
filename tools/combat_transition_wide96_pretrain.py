#!/usr/bin/env python3
"""One PR205-style width-96 pretraining fit, then strong-WD survival transfer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_deepset_distill as distill
from tools import combat_transition_survival_wide96 as wide

fit = wide.fit
BASELINE_SHA = '35402d1e59ae5e9e66fe277f853f3ec62213c157'
DELTA_SHA = '8795adf502265abf3fb75161e89c42d79481fd69a218ecc485a2066820423858'
PRETRAIN_RECIPE = dict(distill.RECIPE, schema='wide96_maxhp_hp_pretrain_v1',
    encoder=wide.RECIPE['architecture'].split('; head')[0],
    encoderSource='tools/combat_transition_survival_wide96.py::build_model',
    hpBranch='copied specialist 8-D delta embedding; fresh 104->64->304 ReLU MLP',
    maxHpBranch='fresh Linear(96,11)')
SURVIVAL_RECIPE = dict(wide.RECIPE, schema='wide96_pretrained_survival_v1',
    training='selected width-96 maxHP/HP pretrained encoder plus fresh Linear(96,1); survival BCE only',
    normalization='unchanged victory-only TRAIN pretraining scalar_mean/scalar_inv buffers')


def student_factory(torch_module, mean, std, delta_count, classes, seed):
    if seed != PRETRAIN_RECIPE['seed'] or delta_count != 11 or len(classes) != 304:
        raise ValueError('pretraining dimensions or seed differ from frozen contract')
    student = distill._student_model(torch_module, mean, std, delta_count, classes, seed)
    student.encoder = wide.build_model(mean, std).encoder
    student.hp = torch.nn.Sequential(torch.nn.Linear(104, 64), torch.nn.ReLU(),
                                     torch.nn.Linear(64, 304))
    return student


def initialize_delta(student, teachers):
    encoder_before = distill.reference.state_hash(student.encoder)
    hp_before = distill.reference.state_hash(student.hp)
    if distill.reference.state_hash(teachers.hp_net.delta_embedding) != DELTA_SHA:
        raise ValueError('specialist delta embedding hash mismatch')
    student.delta_embedding.load_state_dict(teachers.hp_net.delta_embedding.state_dict(), strict=True)
    if distill.reference.state_hash(student.delta_embedding) != DELTA_SHA:
        raise ValueError('delta embedding copy mismatch')
    if encoder_before != distill.reference.state_hash(student.encoder) or hp_before != distill.reference.state_hash(student.hp):
        raise ValueError('delta copy changed fresh encoder or HP MLP')
    return dict(deltaEmbeddingSha256=DELTA_SHA, copiedDeltaOnly=True,
                freshHpHeadSha256=hp_before, freshEncoderSha256=encoder_before,
                hpHeadMatchesSpecialist=False)


def transfer_encoder(payload, mean, std):
    if payload['recipe'] != PRETRAIN_RECIPE:
        raise ValueError('pretraining recipe mismatch')
    state = {name.removeprefix('encoder.'): value for name, value in payload['stateDict'].items()
             if name.startswith('encoder.')}
    model = wide.build_model(mean, std)
    normalization_sha = fit.normalization_digest(model.encoder)
    model.encoder.load_state_dict(state, strict=True)
    if fit.normalization_digest(model.encoder) != normalization_sha:
        raise ValueError('pretrained normalization differs from victory-only TRAIN')
    if fit.screen.state_digest(model.encoder.state_dict()) != fit.screen.state_digest(state):
        raise ValueError('encoder-only transfer mismatch')
    torch.manual_seed(SURVIVAL_RECIPE['seed'])
    model.head = torch.nn.Linear(96, 1)
    return model


def run(args):
    if fit.screen.current_head() != args.experiment_sha or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('requires exact clean frozen execution SHA')
    if args.output.exists():
        raise ValueError('refusing output overwrite')
    pretrain_dir = args.output / 'pretraining'
    pretrain = distill.run(SimpleNamespace(artifact_root=args.artifact_root,
        reference_dir=args.reference_dir, control_dir=args.control_dir, output_dir=pretrain_dir,
        baseline_sha=BASELINE_SHA, experiment_sha=args.experiment_sha), recipe=PRETRAIN_RECIPE,
        student_factory=student_factory, hp_initializer=initialize_delta, latent_width=96)
    checkpoint = pretrain_dir / 'student.pt'
    if fit.screen.digest(checkpoint) != pretrain['checkpointSha256']:
        raise ValueError('selected pretraining checkpoint hash mismatch')
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    if payload['experimentSha'] != args.experiment_sha or payload['selectedEpoch'] != pretrain['selectedEpoch']:
        raise ValueError('selected pretraining provenance mismatch')
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    cache, arrays, population, provenance = fit.load_population(args)
    train, validation = (np.flatnonzero(cache['split'] == split) for split in (0, 1))
    victories = train[cache['win'][train] == 1]
    mean, std, row_ids = distill.normalization_stats(cache, arrays, victories)
    if len(victories) != 393677 or distill.digest_array(row_ids) != pretrain['scalarNormalization']['rowIdsSha256']:
        raise ValueError('victory normalization population mismatch')
    model = transfer_encoder(payload, mean, std).cuda()
    initialization = dict(encoderSha256=fit.screen.state_digest(model.encoder.state_dict()),
        headSha256=fit.screen.state_digest(model.head.state_dict()),
        normalizationSha256=fit.normalization_digest(model.encoder), encoderOnly=True,
        pretrainingCheckpointSha256=pretrain['checkpointSha256'],
        pretrainingSelectedEpoch=pretrain['selectedEpoch'],
        normalization=pretrain['scalarNormalization'])
    reference_encoder, reference_head, _ = fit.screen.load_reference(args)
    reference = fit.SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = fit.predict(reference, arrays, cache, validation, 'cuda')
    if abs(fit.summarize(reference_logits, cache, validation)['nll'] - fit.screen.REFERENCE_NLL) > 1e-7:
        raise ValueError('Attention reference NLL does not reproduce')
    output = args.output / 'survival'
    output.mkdir()
    result = wide.train_model(model, arrays, cache, train, validation, output,
                              args.experiment_sha, recipe=SURVIVAL_RECIPE)
    logits = fit.predict(model, arrays, cache, validation, 'cuda')
    evaluation = fit.compare(reference_logits, logits, cache, validation)
    if evaluation['metrics']['DeepSets']['nll'] != min(entry['validation']['nll'] for entry in result['history']):
        raise ValueError('selected survival checkpoint NLL mismatch')
    np.savez(output / 'validation_predictions.npz', rowIds=cache['ids'][validation],
        sourceGroups=cache['source'][validation], logits=logits, labels=cache['win'][validation],
        referenceLogits=reference_logits)
    result.update(evaluation=evaluation, recipe=SURVIVAL_RECIPE, fixedGates=fit.GATES,
        initialization=initialization, baselineSha=BASELINE_SHA, experimentSha=args.experiment_sha,
        population=population, provenance=provenance,
        parameters=sum(parameter.numel() for parameter in model.parameters()),
        checkpointSha256=fit.screen.digest(output / 'selected.pt'),
        predictionsSha256=fit.screen.digest(output / 'validation_predictions.npz'),
        testEncodedRows=0, testInferenceRows=0, testScoredRows=0,
        speedScreen=dict(skipped='quality gate rejected'),
        environment=dict(torch=torch.__version__, cuda=torch.version.cuda,
            gpu=torch.cuda.get_device_name(), cpuThreads=4, tf32=False))
    if evaluation['decision'] == 'SURVIVAL_DEEPSET_GO':
        result['speedScreen'] = fit.speed_screen(reference, model, arrays, cache, validation)
    fit.screen.composed.base.json_dump(output / 'results.json', result)
    receipt = dict(baselineSha=BASELINE_SHA, experimentSha=args.experiment_sha,
        pretraining=pretrain, survival=result, decision=evaluation['decision'],
        pretrainingReceiptSha256=fit.screen.digest(pretrain_dir / 'results.json'),
        survivalReceiptSha256=fit.screen.digest(output / 'results.json'),
        testInferenceRows=0, testScoredRows=0, runtimeExport=False, promotion=False)
    fit.screen.composed.base.json_dump(args.output / 'results.json', receipt)
    print(json.dumps(dict(decision=evaluation['decision'], output=str(args.output))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--experiment-sha', required=True)
    parser.add_argument('--artifact-root', type=Path, default=wide.RUNS / 'near-full-combat-support-20260914')
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--control-dir', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=wide.RUNS / 'near-full-combat-support-20260914/potion-trajectory-v2')
    parser.add_argument('--reference-component', type=Path, default=wide.RUNS / 'near-full-combat-support-20260914/full-union-survival-v1/component.pt')
    run(parser.parse_args())
