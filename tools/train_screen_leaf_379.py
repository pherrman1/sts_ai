#!/usr/bin/env python3
"""Fixed S1/S2 TRAIN/VALIDATION experiment. No TEST or native integration path."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import numpy as np
from audit_screen_leaf_379 import digest
from screen_leaf_data_379 import DecisionCorpus, read_cache
from screen_leaf_model_379 import (RECIPE, PROVISIONAL_MASK, CONTRACT, verify_feature_names,
    encode_state, pack_encoded, cached_batch, fit_train_normalization, build_model)
from tools.screen_leaf_metrics_379 import predictive_report


def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def encode_cache(directory, split):
    metadata = json.loads((directory / 'manifest.json').read_text())
    verify_feature_names(metadata['feature_names'])
    if metadata['source_limit'] is not None or set(metadata['screens']) != set(PROVISIONAL_MASK):
        raise ValueError('training requires the full frozen split and provisional mask')
    states, labels, identities = [], [], []
    for row in read_cache(directory, split):
        states.append(encode_state(row['base461'], row['screenContents'], row['optionKeys']))
        labels.append(row['label'])
        identities.append(dict(row['identity'], screen=row['screen']))
    result = pack_encoded(states)
    return result, np.asarray(labels, np.float32), identities


def predict(model, cache, batch_size=8192, device='cpu'):
    import torch
    model.eval()
    predictions = []
    with torch.no_grad():
        for start in range(0, len(cache['base']), batch_size):
            indices = np.arange(start, min(start + batch_size, len(cache['base'])))
            predictions.append(torch.sigmoid(model(cached_batch(cache, indices, device=device))).cpu().numpy())
    return np.concatenate(predictions)


def fit(arm, seed, train, labels, validation, val_labels, normalization, output, device):
    import torch
    torch.manual_seed(seed)
    if device == 'cuda': torch.cuda.manual_seed_all(seed)
    model = build_model(arm, normalization).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=RECIPE['lr'], weight_decay=RECIPE['weight_decay'])
    loss_fn = torch.nn.BCEWithLogitsLoss()
    generator = torch.Generator(device='cpu').manual_seed(seed)
    best_loss, best_epoch, best_state = float('inf'), 0, None
    history = []
    start = time.monotonic()
    for epoch in range(1, RECIPE['max_epochs'] + 1):
        model.train()
        order = torch.randperm(len(labels), generator=generator).numpy()
        train_loss = 0.
        for offset in range(0, len(order), RECIPE['batch_size']):
            ids = order[offset:offset + RECIPE['batch_size']]
            optimizer.zero_grad(set_to_none=True)
            logits = model(cached_batch(train, ids, device=device))
            loss = loss_fn(logits, torch.as_tensor(labels[ids], device=device))
            if not torch.isfinite(loss): raise ValueError('nonfinite training loss')
            loss.backward(); optimizer.step()
            train_loss += loss.item() * len(ids)
        model.eval()
        total = 0.
        with torch.no_grad():
            for offset in range(0, len(val_labels), RECIPE['batch_size']):
                ids = np.arange(offset, min(offset + RECIPE['batch_size'], len(val_labels)))
                loss = loss_fn(model(cached_batch(validation, ids, device=device)), torch.as_tensor(val_labels[ids], device=device))
                total += loss.item() * len(ids)
        score = total / len(val_labels)
        if not np.isfinite(score): raise ValueError('nonfinite validation loss')
        history.append({'epoch': epoch, 'train_nll': train_loss / len(labels), 'validation_nll': score})
        print(json.dumps({'arm': arm, 'seed': seed, **history[-1]}), flush=True)
        if score < best_loss:
            best_loss, best_epoch = score, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if epoch - best_epoch >= RECIPE['patience']: break
    if best_state is None: raise ValueError('no finite early-stopped checkpoint')
    model.load_state_dict(best_state)
    prediction = predict(model, validation, device=device)
    torch.save(best_state, output / f'{arm}-seed{seed}.pt')
    np.save(output / f'{arm}-seed{seed}-validation.npy', prediction, allow_pickle=False)
    record = {'arm': arm, 'seed': seed, 'best_epoch': best_epoch, 'best_validation_nll': best_loss,
              'epochs': history, 'wall_seconds': time.monotonic() - start,
              'parameters': sum(p.numel() for p in model.parameters()),
              'checkpoint_sha256': digest(output / f'{arm}-seed{seed}.pt'),
              'predictions_sha256': digest(output / f'{arm}-seed{seed}-validation.npy')}
    write_new(output / f'{arm}-seed{seed}.json', record)
    return prediction, record


def run(output, cache_root, device):
    import torch
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('training source must be reviewed, committed and clean')
    if device == 'cuda' and not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no automatic recipe/device change')
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    output.mkdir(parents=True, exist_ok=False)
    code = {str(ROOT / 'tools' / name): digest(ROOT / 'tools' / name) for name in
            ('screen_leaf_data_379.py', 'screen_leaf_model_379.py', 'screen_leaf_metrics_379.py', 'train_screen_leaf_379.py')}
    write_new(output / 'preregistered.json', {'source_sha': sha, 'code': code, 'recipe': RECIPE,
              'encoder_contract': CONTRACT, 'replacement_candidates': PROVISIONAL_MASK,
              'candidate_selection': 'VALIDATION only; fixed mean of seeds0,1,2 within each arm; S1 versus S2 assessed after full S0 and calibration',
              'device': device, 'torch': torch.__version__, 'numpy': np.__version__, 'threads': 4,
              'test_access': 'forbidden; only TRAIN and VALIDATION loader APIs',
              'failure_rule': 'Stop; preserve partial artifacts, no automatic retry or hyperparameter changes'})
    corpus = DecisionCorpus()
    verify_feature_names(corpus.feature_names)
    for split in ('TRAIN', 'VALIDATION'):
        path = cache_root / split
        if not path.exists(): corpus.build_cache(path, split)
    train, labels, train_metadata = encode_cache(cache_root / 'TRAIN', 'TRAIN')
    validation, val_labels, metadata = encode_cache(cache_root / 'VALIDATION', 'VALIDATION')
    if {r['sourceSeed'] for r in train_metadata} & {r['sourceSeed'] for r in metadata}:
        raise ValueError('source split overlap')
    for split, rows in (('TRAIN', train_metadata), ('VALIDATION', metadata)):
        if set(r['sourceSeed'] for r in rows) != set(corpus.expected_sources(split)):
            raise ValueError('incorrect fixed source populations')
        if dict(Counter(r['screen'] for r in rows)) != corpus.expected_counts(split, PROVISIONAL_MASK):
            raise ValueError('incomplete audited replacement-mask row population')
    del train_metadata
    normalization = fit_train_normalization(train['base'], split='TRAIN')
    np.savez(output / 'normalization.npz', **normalization)
    write_new(output / 'dataset.json', {'feature_names': corpus.feature_names,
              'train_rows': len(labels), 'validation_rows': len(val_labels),
              'train_manifest_sha256': digest(cache_root / 'TRAIN/manifest.json'),
              'validation_manifest_sha256': digest(cache_root / 'VALIDATION/manifest.json'),
              'normalization_sha256': digest(output / 'normalization.npz')})
    write_new(output / 'validation-identities.json', metadata)
    np.save(output / 'validation-labels.npy', val_labels, allow_pickle=False)
    trials = {}
    for arm in ('S1', 'S2'):
        predictions, reports = [], []
        for seed in RECIPE['seeds']:
            prediction, report = fit(arm, seed, train, labels, validation, val_labels, normalization, output, device)
            predictions.append(prediction); reports.append(report)
        mean = np.mean(predictions, axis=0, dtype=np.float64)
        np.save(output / f'{arm}-ensemble-validation.npy', mean, allow_pickle=False)
        trials[arm] = {'individual': reports, 'ensemble': predictive_report(val_labels, mean, metadata),
                       'ensemble_predictions_sha256': digest(output / f'{arm}-ensemble-validation.npy')}
        write_new(output / f'{arm}-validation-report.json', trials[arm])
    if any(digest(Path(path)) != value for path, value in code.items()): raise ValueError('training code changed during execution')
    write_new(output / 'result.json', {'status': 'TRAINING_COMPLETE_NOT_QUALIFIED', 'arms': trials,
                                      'pending': ['S0 comparison', 'calibration', 'candidate freeze', 'sealed TEST']})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cache-root', type=Path, required=True)
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    a = p.parse_args()
    run(a.output.resolve(), a.cache_root.resolve(), a.device)
