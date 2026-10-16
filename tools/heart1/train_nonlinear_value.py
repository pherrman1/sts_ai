#!/usr/bin/env python3
"""Bounded §496 nonlinear value-head development on audited frozen Arm C features.

Commands freeze/fit. No game generation, TEST access, encoder updates or native
integration. All six learning-curve fits use the same fixed optimizer budget.
Only 40-source candidates may supply the selected value head.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import torch
from torch import nn

import train_value_head as linear

LINEAR_RESULT_SHA = 'ccd9ca840b9601b8361dbeac14e5fa9d5fe80b543651878f8fb3dbba44db66df'
LINEAR_FREEZE_SHA = '8c0f03ceb73cb0075dc72d96711365e7f3c94612a2825426d920b531746692f9'
SIZES = (10, 20, 40)
INITS = (0, 1)
STEPS = 1000
EVAL_EVERY = 50
BATCH = 512


class ValueHead(nn.Module):
    def __init__(self, train_features):
        super().__init__()
        # Standardization is fitted only on the relevant TRAIN prefix.
        self.register_buffer('mean', train_features.mean(0))
        self.register_buffer('scale', train_features.std(0, unbiased=False).clamp_min(1e-6))
        self.layers = nn.Sequential(nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 1))

    def forward(self, features):
        return self.layers((features - self.mean) / self.scale).squeeze(1)


def check_parent(cache, checkpoint):
    """Consume only the audited feature cache, never an old evaluator/TEST path."""
    if linear.sha(cache / 'result.json') != LINEAR_RESULT_SHA or linear.sha(cache / 'freeze.json') != LINEAR_FREEZE_SHA:
        raise ValueError('not the audited affine fit packet')
    result = json.loads((cache / 'result.json').read_text())
    if linear.sha(cache / 'pooled.pt') != result['pooledSha256']:
        raise ValueError('pooled feature cache changed')
    if linear.sha(cache / 'custody.json') != result['custodySha256']:
        raise ValueError('feature row custody changed')
    if linear.sha(checkpoint) != linear.CHECKPOINT_SHA:
        raise ValueError('original Arm C checkpoint changed')
    if not result['policyLogitsBitwiseEqual'] or not result['pooledBitwiseEqual']:
        raise ValueError('parent did not preserve policy/representation')
    return result


def identity(args):
    repo = Path(__file__).resolve().parents[2]
    files = [Path(__file__), Path(linear.__file__),
             repo / 'tools/heart_rollout_distill.py', repo / 'tools/heart_record_encoder.py',
             repo / 'tools/heart_distill_native_fit.py', repo / 'tools/heart1_leaf_reference.py',
             args.cache / 'result.json', args.cache / 'freeze.json', args.cache / 'pooled.pt',
             args.cache / 'custody.json', args.corpus / 'corpus-manifest.json',
             args.corpus / 'corpus-train-validation.tar', args.checkpoint]
    return {'files': {str(p.resolve()): linear.sha(p) for p in files},
        'sourceSha': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
        'torch': torch.__version__, 'numpy': np.__version__,
        'python': sys.version, 'pythonSha256': linear.sha(Path(sys.executable).resolve()),
        'cublasWorkspaceConfig': linear.os.environ['CUBLAS_WORKSPACE_CONFIG'],
        'torchBinarySha256': linear.sha(torch._C.__file__),
        'device': args.device, 'gpu': torch.cuda.get_device_name() if args.device == 'cuda' else None}


def freeze(args):
    check_parent(args.cache, args.checkpoint)
    if linear.sha(args.corpus / 'corpus-manifest.json') != linear.CORPUS_MANIFEST_SHA256:
        raise ValueError('wrong completed corpus')
    args.out.mkdir(parents=True, exist_ok=False)
    linear.write_json(args.out / 'freeze.json', {'schema': 'arm-c-nonlinear-head-v1',
        'identity': identity(args), 'architecture': 'TRAIN-standardize -> Linear64x64 -> ReLU -> Linear64x1',
        'parameters': 4225, 'sizes': SIZES, 'inits': INITS, 'steps': STEPS,
        'evaluationEvery': EVAL_EVERY, 'batch': BATCH,
        'optimizer': {'name': 'AdamW', 'lr': .001, 'weightDecay': .001},
        'objective': 'source-balanced raw MSE against existing64-rollout target means',
        'selection': 'minimum raw source-balanced VALIDATION MSE; only40-source runs eligible; first candidate breaks exact ties',
        'splits': linear.SPLITS, 'maxSeconds': 600, 'testRead': False,
        'nativeIntegration': False, 'encoderUpdated': False})


def load_inputs(args):
    parent = check_parent(args.cache, args.checkpoint)
    data, custody = linear.load_tv(args.corpus)
    if custody != json.loads((args.cache / 'custody.json').read_text()):
        raise ValueError('feature cache/source row custody mismatch')
    features = torch.load(args.cache / 'pooled.pt', map_location='cpu', weights_only=True)
    if set(features) != set(linear.SPLITS):
        raise ValueError('feature cache contains unexpected splits')
    for split in linear.SPLITS:
        x = features[split]
        if (x.shape != (len(data[split][0]), 64) or x.dtype != torch.float32
                or not torch.isfinite(x).all()):
            raise ValueError('invalid feature cache shape/dtype/values')
        if data[split][2] != parent['coverage'][split]:
            raise ValueError('parent/feature row coverage mismatch')
    return data, features, parent


def raw_mse(pred, target, weights):
    return float(((pred.double() - target.double()).square() * weights.double()).sum())


def eligible_improvement(size, candidate, current):
    return size == 40 and (current is None or candidate['validationRawMse'] < current['validationRawMse'])


def fit_one(x, target, rows, vx, vy, validation_weights, init, deadline,
            steps=STEPS, evaluate_every=EVAL_EVERY):
    torch.manual_seed(init)
    model = ValueHead(x).to(x.device)
    weights = linear.source_weights(rows).to(device=x.device, dtype=torch.float32)
    with torch.no_grad():
        model.layers[-1].bias.fill_(float((target * weights).sum()))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.001)
    logs, best = [], None
    order, cursor = torch.empty(0, device=x.device, dtype=torch.int64), 0
    for step in range(1, steps + 1):
        if time.monotonic() > deadline:
            raise TimeoutError('frozen600-second nonlinear fit cap')
        if cursor >= len(order):
            order, cursor = torch.randperm(len(x), device=x.device), 0
        ids = order[cursor:cursor+BATCH]
        cursor += BATCH
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = ((model(x[ids]) - target[ids]).square() * (weights[ids] * len(x))).mean()
        if not torch.isfinite(loss):
            raise ValueError('nonfinite training loss')
        loss.backward()
        optimizer.step()
        if step % evaluate_every == 0 or step == steps:
            model.eval()
            with torch.inference_mode():
                vp, tp = model(vx), model(x)
                vm = raw_mse(vp, vy, validation_weights)
                tm = raw_mse(tp, target, weights)
            if not np.isfinite([vm, tm]).all():
                raise ValueError('nonfinite evaluation loss')
            logs.append({'step': step, 'trainRawMse': tm, 'validationRawMse': vm})
            if best is None or vm < best['validationRawMse']:
                best = {'step': step, 'trainRawMse': tm, 'validationRawMse': vm,
                        'state': {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
    return best, logs


def fit(args):
    frozen = json.loads((args.out / 'freeze.json').read_text())
    if frozen['identity'] != identity(args):
        raise ValueError('frozen nonlinear fit identity changed')
    linear.write_json(args.out / 'fit-started.json', {'freezeSha256': linear.sha(args.out / 'freeze.json')})
    started = time.monotonic()
    deadline = started + frozen['maxSeconds']
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    data, features, parent = load_inputs(args)
    train, tg, _ = data['train']
    val, vg, _ = data['validation']
    vx = features['validation'].to(args.device)
    vy = torch.tensor([r['target'] for r in val], device=args.device, dtype=torch.float64)
    vw = linear.source_weights(val).to(args.device)
    candidates, history, selected = [], [], None
    for size in SIZES:
        indices = [i for i, r in enumerate(train) if r['seed'] in linear.SPLITS['train'][:size]]
        rows = [train[i] for i in indices]
        x = features['train'][indices].to(args.device)
        y = torch.tensor([r['target'] for r in rows], device=args.device)
        for init in INITS:
            best, logs = fit_one(x, y, rows, vx, vy, vw, init, deadline)
            best_state = best.pop('state')
            model = ValueHead(x).to(args.device)
            model.load_state_dict(best_state, strict=True)
            model.eval()
            with torch.inference_mode():
                pred = model(vx).cpu().numpy()
            candidate = {'sources': size, 'rows': len(rows), 'init': init, **best,
                         'validation': linear.metrics(val, vg, np.clip(pred, 0, 1))}
            candidates.append(candidate)
            history.append({'sources': size, 'init': init, 'checkpoints': logs})
            print(json.dumps({k: candidate[k] for k in ('sources', 'init', 'step', 'trainRawMse', 'validationRawMse')}), flush=True)
            if eligible_improvement(size, best, selected):
                selected = {**candidate, 'state': best_state}
    if time.monotonic() > deadline or frozen['identity'] != identity(args):
        raise ValueError('budget exceeded or frozen inputs changed during fit')
    state = selected.pop('state')
    payload = {'valueHead': state, 'encoderCheckpointSha256': linear.CHECKPOINT_SHA,
               'architecture': frozen['architecture'], 'freezeSha256': linear.sha(args.out / 'freeze.json')}
    torch.save(payload, args.out / 'nonlinear-head.pt')
    # Retain exact float32 tensors as portable JSON without native loading.
    linear.write_json(args.out / 'head.json', {k: v.tolist() for k, v in state.items()})
    linear.write_json(args.out / 'training.json', history)
    report = {'schema': 'arm-c-nonlinear-head-result-v1', 'verdict': 'VALIDATION_ONLY',
        'selected': selected, 'candidates': candidates,
        'baselines': {'x2b': linear.metrics(val, vg, [r['x2b'] for r in val]),
                      'affine': {'rawMse': parent['validationRawMse'], 'validation': parent['validation']}},
        'coverage': {split: data[split][2] for split in linear.SPLITS},
        'parameters': sum(p.numel() for p in model.parameters()),
        'encoderCheckpointUnchanged': linear.sha(args.checkpoint) == linear.CHECKPOINT_SHA,
        'encoderRecomputed': False, 'policyChanged': False, 'testRead': False,
        'nativeQualified': False, 'heartWinPredictionQualified': False, 'runtimePromotion': False,
        'headSha256': linear.sha(args.out / 'nonlinear-head.pt'),
        'portableHeadSha256': linear.sha(args.out / 'head.json'),
        'trainingSha256': linear.sha(args.out / 'training.json'),
        'parentResultSha256': LINEAR_RESULT_SHA, 'pooledSha256': parent['pooledSha256'],
        'freezeSha256': linear.sha(args.out / 'freeze.json'), 'seconds': time.monotonic() - started}
    linear.write_json(args.out / 'result.json', report)
    print(json.dumps({'verdict': report['verdict'], 'selected': {k: selected[k] for k in ('init', 'step', 'validationRawMse')},
                      'headSha256': report['headSha256'], 'seconds': report['seconds']}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'fit'))
    for name in ('corpus', 'cache', 'checkpoint', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cuda')
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args)
    else:
        try:
            fit(args)
        except Exception as exc:
            if args.out.is_dir() and not (args.out / 'failure.json').exists():
                linear.write_json(args.out / 'failure.json', {'type': type(exc).__name__, 'message': str(exc)})
            raise


if __name__ == '__main__':
    main()
