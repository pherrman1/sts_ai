#!/usr/bin/env python3
"""Train only Arm C's existing linear value head on §494 TRAIN/VALIDATION.

No game generation, TEST reader, runtime loader or encoder fine-tuning. The
existing head is affine, so source-balanced ridge least squares solves its MSE
objective directly. Fixed regularization candidates are selected on VALIDATION.
"""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time

import numpy as np
import torch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from heart_distill_native_fit import CORPUS_MANIFEST_SHA256, PRODUCER_SHA256, STUDENT_C_SHA256
from heart_rollout_distill import validate_rows, metrics

CHECKPOINT_SHA = '53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020'
SILVERBOT_COMMIT = '84ab3ead9d88c01c4be09a6773fb9a947f57d5ff'
HEAD_KEYS = {'value_head.weight', 'value_head.bias'}
SPLITS = {'train': list(range(110164000, 110164040)),
          'validation': list(range(110164040, 110164048))}
ALPHAS = (0., 1e-6, 1e-4, .01, 1., 100.)
BATCH = 32


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def write_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def dependencies(repo):
    """Bind local encoder code and compiled enum/observation dependency."""
    if subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() != SILVERBOT_COMMIT:
        raise ValueError('unexpected silverbot checkout')
    files = sorted((repo / 'silverbot').glob('*.py')) + sorted((repo / 'build').glob('slaythespire*.so'))
    if not any(p.suffix == '.so' for p in files):
        raise ValueError('missing compiled silverbot module')
    return {str(p.resolve()): sha(p) for p in files}


def identities(args):
    repo = Path(__file__).resolve().parents[2]
    return {'checkpointSha256': sha(args.checkpoint),
            'corpusManifestSha256': sha(args.corpus / 'corpus-manifest.json'),
            'trainValidationArchiveSha256': sha(args.corpus / 'corpus-train-validation.tar'),
            'dependencies': dependencies(args.silverbot),
            'tools': {str(repo / name): sha(repo / name) for name in (
                'tools/heart1/train_value_head.py', 'tools/heart_rollout_distill.py',
                'tools/heart_record_encoder.py', 'tools/heart_distill_native_fit.py',
                'tools/heart1_leaf_reference.py')},
            'python': sys.version, 'pythonSha256': sha(Path(sys.executable).resolve()),
            'torch': torch.__version__, 'numpy': np.__version__,
            'torchBinarySha256': sha(torch._C.__file__),
            'sourceSha': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()}


def freeze(args):
    ident = identities(args)
    manifest = json.loads((args.corpus / 'corpus-manifest.json').read_text())
    if ident['checkpointSha256'] != CHECKPOINT_SHA or ident['corpusManifestSha256'] != CORPUS_MANIFEST_SHA256:
        raise ValueError('not the frozen Arm C checkpoint/corpus')
    if (manifest['producerSha256'] != PRODUCER_SHA256 or manifest['studentcSha256'] != STUDENT_C_SHA256
            or ident['trainValidationArchiveSha256'] != manifest['corpus-train-validation.tar']):
        raise ValueError('producer/model/archive custody mismatch')
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'freeze.json', {'schema': 'arm-c-value-head-v1', 'identity': ident,
        'splits': SPLITS, 'trainable': sorted(HEAD_KEYS), 'alphas': ALPHAS,
        'selection': 'minimum source-balanced raw value MSE on VALIDATION; alpha order breaks ties',
        'prediction': 'raw affine output for MSE training/selection; clamp [0,1] for ranking diagnostics',
        'batch': BATCH, 'device': args.device, 'maxSeconds': 1800,
        'label': 'mean of 64 Arm C/CTM rollout3 returns ending in X2-B; not Heart outcomes',
        'testRead': False, 'nativeIntegration': False})


def member(archive, name):
    found = [m for m in archive.getmembers() if m.name == name]
    if len(found) != 1 or not found[0].isfile() or found[0].size > 64 * 1024**2:
        raise ValueError('invalid archive member ' + name)
    return archive.extractfile(found[0]).read()


def load_tv(corpus):
    """Verify original custody; never open or hash the sealed TEST archive."""
    if sha(corpus / 'corpus-manifest.json') != CORPUS_MANIFEST_SHA256:
        raise ValueError('corpus manifest changed')
    manifest = json.loads((corpus / 'corpus-manifest.json').read_text())
    archive_path = corpus / 'corpus-train-validation.tar'
    if sha(archive_path) != manifest['corpus-train-validation.tar']:
        raise ValueError('TRAIN/VALIDATION archive changed')
    result, custody = {}, {}
    with tarfile.open(archive_path) as outer:
        for split, seeds in SPLITS.items():
            rows, groups, coverage = [], [], {}
            for seed in seeds:
                entry = manifest['sources'][str(seed)]
                if entry['split'] != split or entry['returncode'] != 0 or entry['attempt'] != 1:
                    raise ValueError('source split/completion mismatch')
                shared = member(outer, f'receipts/seed-{seed}.receipt.json')
                source = member(outer, entry['archive'])
                if sha_bytes(shared) != entry['shareReceiptSha256'] or sha_bytes(source) != entry['archiveSha256']:
                    raise ValueError('source archive/share receipt changed')
                share = json.loads(shared)
                stem = Path(entry['archive']).name[:-len('.tar.gz')]
                with tarfile.open(fileobj=io.BytesIO(source), mode='r:gz') as inner:
                    receipt_data = member(inner, f'{stem}/seed-{seed}.receipt.json')
                    capture = member(inner, f'{stem}/seed-{seed}.sib.jsonl')
                receipt = json.loads(receipt_data)
                if (sha_bytes(receipt_data) != share['receiptSha256'] or receipt['seed'] != seed
                        or receipt['returncode'] != 0 or receipt['attempt'] != 1
                        or sha_bytes(capture) != receipt['captureSha256']
                        or share['files'][f'seed-{seed}.sib.jsonl'] != sha_bytes(capture)):
                    raise ValueError('source capture/receipt changed')
                rr, gg, counts = validate_rows((json.loads(line) for line in capture.splitlines()), seed, 'heart1')
                if counts['accepted'] != counts['raw'] or not gg:
                    raise ValueError('incomplete source coverage')
                groups.extend([[len(rows) + i for i in g] for g in gg])
                rows.extend(rr)
                coverage[str(seed)] = counts
                custody[str(seed)] = {'captureSha256': sha_bytes(capture), 'receiptSha256': sha_bytes(receipt_data)}
            if len(groups) < (500 if split == 'train' else 100):
                raise ValueError('insufficient sibling groups')
            result[split] = (rows, groups, coverage)
    return result, custody


def trim_record(record):
    record = copy.deepcopy(record)
    y = record['obs.mapY']
    if y >= 0:
        keep = [i for i, floor in enumerate(record['obs.map.ys']) if floor >= y]
        for key in ('obs.map.xs', 'obs.map.ys', 'obs.map.roomTypes', 'obs.map.pathXs'):
            record[key] = [record[key][i] for i in keep]
    return record


def load_net(repo, checkpoint, device):
    sys.path[:0] = [str(repo), str(repo / 'build')]
    from silverbot import network
    net = network.NN(network.ModelHP(dim=64, n_layers=2, n_heads=4, mlp_dim_mult=4, use_value_head=True))
    net.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True), strict=True)
    net.requires_grad_(False)
    net.eval().to(device)
    return network, net


def encode(network, net, rows, device, deadline):
    features, values = [], []
    policy = hashlib.sha256()
    for start in range(0, len(rows), BATCH):
        if time.monotonic() > deadline:
            raise TimeoutError('frozen 1800-second wall cap')
        records = [{**trim_record(r['record']), 'chosen_idx': 0, 'outcome': 0.} for r in rows[start:start+BATCH]]
        batch = network.move_to_device(network.collate_fn(records), device)
        with torch.inference_mode():
            logits, value, pooled = net(batch, return_pooled=True)
        if not torch.isfinite(pooled).all() or not torch.isfinite(value).all() or torch.isnan(logits).any():
            raise ValueError('nonfinite network output')
        policy.update(logits.cpu().contiguous().numpy().tobytes())
        features.append(pooled.cpu())
        values.append(value.cpu())
    return torch.cat(features), torch.cat(values).numpy(), policy.hexdigest()


def source_weights(rows):
    counts = Counter(r['seed'] for r in rows)
    return torch.tensor([1 / (len(counts) * counts[r['seed']]) for r in rows], dtype=torch.float64)


def solve_head(x, targets, weights, alpha):
    """Minimize sum(weights * squared error) + alpha * ||weight||²; free bias."""
    x = x.to(torch.float64)
    design = torch.cat((x, torch.ones(len(x), 1, dtype=x.dtype)), dim=1)
    a = design * weights.sqrt()[:, None]
    b = targets.to(torch.float64) * weights.sqrt()
    penalty = torch.eye(design.shape[1], dtype=x.dtype)[:-1] * alpha**.5
    solution = torch.linalg.lstsq(torch.cat((a, penalty)),
        torch.cat((b, torch.zeros(len(penalty), dtype=x.dtype))), driver='gelsd').solution
    if not torch.isfinite(solution).all():
        raise ValueError('nonfinite fitted head')
    return solution[:-1].float().unsqueeze(0), solution[-1:].float()


def assert_frozen(before, after):
    if before.keys() != after.keys():
        raise ValueError('checkpoint keys changed')
    changed = [key for key in before if not torch.equal(before[key], after[key])]
    if not changed or set(changed) - HEAD_KEYS:
        raise ValueError('frozen tensor changed or no training occurred: ' + str(changed))
    return changed


def fit(args):
    frozen = json.loads((args.out / 'freeze.json').read_text())
    if frozen['identity'] != identities(args) or frozen['splits'] != SPLITS or frozen['device'] != args.device:
        raise ValueError('frozen identities changed')
    # A consumed or interrupted attempt is never resumed implicitly.
    write_json(args.out / 'fit-started.json', {'freezeSha256': sha(args.out / 'freeze.json'), 'pid': __import__('os').getpid()})
    started = time.monotonic()
    deadline = started + frozen['maxSeconds']
    torch.set_num_threads(2)
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    data, custody = load_tv(args.corpus)
    write_json(args.out / 'custody.json', custody)
    network, net = load_net(args.silverbot, args.checkpoint, args.device)
    before = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    embeddings = {}
    for split, (rows, _, _) in data.items():
        print('encoding', split, len(rows), flush=True)
        embeddings[split] = encode(network, net, rows, args.device, deadline)
    torch.save({k: v[0] for k, v in embeddings.items()}, args.out / 'pooled.pt')
    train, tg, tc = data['train']
    val, vg, vc = data['validation']
    tx, initial_train, _ = embeddings['train']
    vx, initial_val, policy_before = embeddings['validation']
    ty = torch.tensor([r['target'] for r in train])
    tw = source_weights(train)
    candidates, best = [], None
    for alpha in ALPHAS:
        weight, bias = solve_head(tx, ty, tw, alpha)
        pred = torch.nn.functional.linear(vx, weight, bias).squeeze(1).numpy()
        diagnostic = metrics(val, vg, np.clip(pred, 0, 1))
        raw = metrics(val, vg, pred)['aggregate']['mse']
        candidates.append({'alpha': alpha, 'rawMse': raw, 'boundedMetrics': diagnostic})
        if best is None or raw < best[0]:
            best = (raw, alpha, weight, bias, pred)
    _, alpha, weight, bias, pred = best
    with torch.no_grad():
        net.value_head.weight.copy_(weight.to(args.device))
        net.value_head.bias.copy_(bias.to(args.device))
    after = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    changed = assert_frozen(before, after)
    # Whole VALIDATION pass checks real forward outputs and exact prior invariance.
    features_after, full_pred, policy_after = encode(network, net, val, args.device, deadline)
    if policy_before != policy_after or not torch.equal(vx, features_after):
        raise ValueError('policy/encoder forward parity failed')
    diff = float(np.max(np.abs(full_pred - pred)))
    if diff > 1e-5:
        raise ValueError('cached-head/full-network value mismatch')
    if time.monotonic() > deadline:
        raise TimeoutError('frozen wall cap')
    torch.save(after, args.out / 'arm-c-value.pt')
    train_mean = float((ty.double() * tw).sum())
    report = {'schema': 'arm-c-value-head-result-v1', 'verdict': 'VALIDATION_ONLY',
        'selectedAlpha': alpha, 'trainableParameters': weight.numel() + bias.numel(),
        'changedTensors': changed, 'frozenTensors': len(before) - len(changed),
        'policyLogitsBitwiseEqual': True, 'validationPolicySha256': policy_before,
        'pooledBitwiseEqual': True, 'fullVsCachedValueMaxAbs': diff,
        'validation': metrics(val, vg, np.clip(pred, 0, 1)),
        'validationRawMse': best[0],
        'baselines': {'x2b': metrics(val, vg, [r['x2b'] for r in val]),
            'initialHead': metrics(val, vg, np.clip(initial_val, 0, 1)),
            'trainMean': metrics(val, vg, [train_mean] * len(val))},
        'train': metrics(train, tg, np.clip(torch.nn.functional.linear(tx, weight, bias).squeeze(1).numpy(), 0, 1)),
        'coverage': {'train': tc, 'validation': vc}, 'candidates': candidates,
        'checkpointSha256': sha(args.out / 'arm-c-value.pt'),
        'pooledSha256': sha(args.out / 'pooled.pt'), 'custodySha256': sha(args.out / 'custody.json'),
        'freezeSha256': sha(args.out / 'freeze.json'), 'seconds': time.monotonic() - started,
        'testRead': False, 'nativeQualified': False, 'heartWinPredictionQualified': False,
        'runtimePromotion': False, 'gpu': torch.cuda.get_device_name() if args.device == 'cuda' else None}
    write_json(args.out / 'result.json', report)
    print(json.dumps({k: report[k] for k in ('verdict', 'selectedAlpha', 'validationRawMse', 'checkpointSha256', 'seconds')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'fit'))
    for name in ('corpus', 'checkpoint', 'silverbot', 'out'):
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
                write_json(args.out / 'failure.json', {'type': type(exc).__name__, 'message': str(exc)})
            raise


if __name__ == '__main__':
    main()
