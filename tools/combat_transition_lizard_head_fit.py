#!/usr/bin/env python3
"""Fit the missing Lizard trajectory head under the frozen relic recipe.

This is a source-grouped offline experiment. It trains only the existing
two-class Lizard linear head; the shared decoder and all other groups remain
frozen. It never changes production support or exports a runtime artifact.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess

import numpy as np
import torch
import torch.nn.functional as F

from tools import combat_transition_composed as c
from tools import combat_transition_lizard_offline_audit as audit
from tools import combat_transition_model_experiment as split_model
from tools import combat_transition_relic_trajectory as relic_fit

RECIPE = {
    'schema': 'active_lizard_head_fit_v1',
    'seeds': [20260912, 20260913, 20260914],
    'epochs': relic_fit.RECIPE['epochs'],
    'optimizer': relic_fit.RECIPE['optimizer'],
    'learningRate': relic_fit.RECIPE['lr'],
    'weightDecay': relic_fit.RECIPE['weightDecay'],
    'batch': relic_fit.RECIPE['batch'],
    'gradientClip': relic_fit.RECIPE['clip'],
    'precision': 'fp32',
    'trainableParameters': ['relic_net.heads.lizard.weight', 'relic_net.heads.lizard.bias'],
    'frozenParameters': 'shared relic decoder and every non-Lizard head',
    'partition': 'split_for_seed; TRAIN fit, VALIDATION descriptive only, TEST once',
    'properScoreGate': 'source-bootstrap 95% CI upper of trained-minus-TRAIN-prior NLL must be below zero',
    'ancestralGate': '32 draws per fully-supported TEST row; zero hard-validity failures',
    'bootstrapReps': relic_fit.RECIPE['bootstrapReps'],
    'bootstrapSeed': relic_fit.RECIPE['bootstrapSeed'],
    'samplingSeed': c.RECIPE['samplingSeed'] + 1,
    'drawsPerTestRow': c.RECIPE['draws'],
}


def classify(ci95, hard_failures):
    if hard_failures:
        return 'LIZARD_HEAD_REJECTED_HARD_VALIDITY'
    if ci95 is None or len(ci95) != 2 or not np.isfinite(ci95).all():
        return 'LIZARD_HEAD_INCONCLUSIVE'
    if ci95[1] < 0:
        return 'LIZARD_HEAD_QUALIFIED_OFFLINE'
    if ci95[0] > 0:
        return 'LIZARD_HEAD_REJECTED_PROPER_SCORE'
    return 'LIZARD_HEAD_INCONCLUSIVE'


def labels_for_row(row):
    lizard = c.base._RELIC_IDS['LIZARD_TAIL']
    pre = next((x['data'] for x in row['transition']['pre']['relics'] if x['id'] == lizard), None)
    post = next((x['data'] for x in row['transition']['post']['relics'] if x['id'] == lizard), None)
    if pre != 1 or post not in (0, 1):
        raise ValueError('active Lizard training row has invalid RAW state')
    return int(post == 0)


def select_rows(split, full_support, win):
    """Keep teacher-forced post-state scoring and ancestral cohorts distinct."""
    split = np.asarray(split)
    full_support = np.asarray(full_support, dtype=bool)
    win = np.asarray(win, dtype=bool)
    if not (len(split) == len(full_support) == len(win)):
        raise ValueError('row-selection inputs have different lengths')
    train = np.flatnonzero((split == 'train') & full_support & win)
    validation = np.flatnonzero((split == 'validation') & full_support & win)
    test_wins = np.flatnonzero((split == 'test') & full_support & win)
    test_ancestral = np.flatnonzero((split == 'test') & full_support)
    return train, validation, test_wins, test_ancestral


def _predict(model, z, signed, fraction, mask, device):
    model.eval()
    outputs = []
    with torch.inference_mode():
        for start in range(0, len(z), 2048):
            sl = slice(start, start + 2048)
            logits = model(
                torch.as_tensor(z[sl], device=device, dtype=torch.float32),
                torch.as_tensor(signed[sl], device=device, dtype=torch.long),
                torch.as_tensor(fraction[sl], device=device, dtype=torch.float32),
                torch.as_tensor(mask[sl], device=device, dtype=torch.long),
            )['lizard']
            outputs.append(torch.log_softmax(logits.float(), -1).cpu().numpy())
    return np.concatenate(outputs, axis=0)


def run(corpus: Path, manifest_path: Path, output_dir: Path, reviewed_sha: str) -> dict:
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if current != reviewed_sha or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise ValueError('fit requires the exact reviewed clean implementation SHA')
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(manifest_path.read_text())
    validated = c.base.validate_corpus(manifest)
    if manifest['csv']['path'] != str(corpus.resolve()) or manifest['csv']['sha256'] != c.base.sha256(corpus):
        raise ValueError('corpus path/hash differs from manifest')
    rows = list(c.base.iter_rows(corpus))
    if len(rows) != validated['rows']:
        raise ValueError('validated row count differs')
    invalid = [i for i, r in enumerate(rows) if r.get('runValid') is not True
               or r.get('captureCount') != 1 or r.get('captureStatus') != 'exactly_one'
               or r.get('quarantineReason')]
    if invalid:
        raise ValueError(f'fail-closed: {len(invalid)} invalid/nonunique rows')

    models = c.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    n = len(rows)
    source = np.asarray([int(r['sourceSeed']) for r in rows], dtype=np.int64)
    split = np.asarray([split_model.split_for_seed(int(s)) for s in source])
    outcome = np.asarray([int(r['transition']['combatOutcome']) for r in rows])
    win = outcome == c.base.WIN
    full = np.zeros(n, dtype=bool)
    support_reasons = {}
    for i, row in enumerate(rows):
        reasons = audit.offline_reasons(row['transition']['pre'], row['predictorInput'], models)
        full[i] = not reasons
        for reason in reasons:
            support_reasons[reason] = support_reasons.get(reason, 0) + 1
    eligible = full & win
    train_ids, validation_ids, test_ids, ancestral_test_ids = select_rows(split, full, win)
    if not len(train_ids) or not len(validation_ids) or not len(test_ids):
        raise ValueError('source split has no fully-supported winning rows in one partition')
    for ids in (train_ids, validation_ids, test_ids):
        if not np.all([any(x['id'] == c.base._RELIC_IDS['LIZARD_TAIL'] and x['data'] == 1
                           for x in rows[i]['transition']['pre']['relics']) for i in ids]):
            raise ValueError('eligible row lacks active Lizard pre-state')

    z = np.zeros((n, 64), dtype=np.float32)
    signed = np.zeros(n, dtype=np.int64)
    fraction = np.zeros(n, dtype=np.float32)
    masks = np.zeros(n, dtype=np.int64)
    labels = np.zeros(n, dtype=np.int64)
    for i in np.flatnonzero(eligible):
        labels[i] = labels_for_row(rows[int(i)])
    arrays = audit.stack_inputs(rows)
    prehp = np.asarray([r['transition']['pre']['curHp'] for r in rows], dtype=np.int64)
    premax = np.asarray([r['transition']['pre']['maxHp'] for r in rows], dtype=np.int64)
    posthp = np.asarray([r['transition']['post']['curHp'] for r in rows], dtype=np.int64)
    postmax = np.asarray([r['transition']['post']['maxHp'] for r in rows], dtype=np.int64)
    actual_delta = postmax - premax
    delta_index = {int(v): i for i, v in enumerate(models.delta_values)}
    hp_index = {int(v): i for i, v in enumerate(models.classes)}
    potion_slots = arrays['potions'][:, :, 1].astype(np.int64)
    capacities = np.asarray([r['transition']['pre']['potionCapacity'] for r in rows], dtype=np.int64)
    true_mask = c.potion.encode_masks(
        np.asarray([r['transition']['pre']['potions'] for r in rows], dtype=np.int64),
        np.asarray([r['transition']['post']['potions'] for r in rows], dtype=np.int64),
        capacities,
    )
    device = models.device
    with torch.inference_mode():
        for batch in audit.ev.batches(n, 256):
            inputs = c.base._torch_inputs(arrays, batch, device, torch, trim_padding=True)
            z[batch] = models.hp_encoding(inputs).cpu().numpy()
    for i in np.flatnonzero(eligible):
        delta = int(actual_delta[i])
        if delta not in delta_index:
            raise ValueError('eligible maxHP target outside frozen domain')
        signed_value = int(posthp[i] - prehp[i])
        if outcome[i] == c.base.WIN and signed_value not in hp_index:
            raise ValueError('eligible signed HP target outside frozen domain')
        if signed_value not in hp_index:
            # The downstream relic decoder is called on victories only.
            raise ValueError('eligible winning HP target outside frozen domain')
        signed[i] = hp_index[signed_value]
        fraction[i] = posthp[i] / postmax[i]
        masks[i] = int(true_mask[i])

    train_labels = labels[train_ids]
    prior_rate = float(train_labels.mean())
    if not 0 < prior_rate < 1:
        raise ValueError('TRAIN-only prior must contain both Lizard classes')
    prior_prob = np.asarray([1 - prior_rate, prior_rate], dtype=np.float64)
    prior_nll = -np.log(prior_prob[labels[test_ids]])
    original_state = copy.deepcopy(models.relic_net.state_dict())
    trainable_names = {'heads.lizard.weight', 'heads.lizard.bias'}
    state_rows = []
    holdout_logps = []
    validation_logps = []
    training_audits = []
    base_seed = tuple(RECIPE['seeds'])
    torch.set_num_threads(4)
    for seed in base_seed:
        models.relic_net.load_state_dict(original_state, strict=True)
        for name, parameter in models.relic_net.named_parameters():
            parameter.requires_grad_(name in trainable_names)
        trainable = [p for name, p in models.relic_net.named_parameters() if name in trainable_names]
        optimizer = torch.optim.AdamW(trainable, lr=RECIPE['learningRate'], weight_decay=RECIPE['weightDecay'])
        rng = np.random.default_rng(seed)
        history = []
        batch_hash = __import__('hashlib').sha256()
        for epoch in range(RECIPE['epochs']):
            order = train_ids[rng.permutation(len(train_ids))]
            total = 0.0
            for start in range(0, len(order), RECIPE['batch']):
                ids = order[start:start + RECIPE['batch']]
                batch_hash.update(ids.tobytes())
                logits = models.relic_net(
                    torch.as_tensor(z[ids], device=device),
                    torch.as_tensor(signed[ids], device=device),
                    torch.as_tensor(fraction[ids], device=device),
                    torch.as_tensor(masks[ids], device=device),
                )['lizard']
                target = torch.as_tensor(labels[ids], device=device, dtype=torch.long)
                loss = F.cross_entropy(logits.float(), target)
                if not torch.isfinite(loss):
                    raise ValueError('nonfinite Lizard loss')
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(trainable, RECIPE['gradientClip'])
                if not torch.isfinite(norm):
                    raise ValueError('nonfinite Lizard gradient')
                optimizer.step()
                total += float(loss.detach()) * len(ids)
            history.append(total / len(train_ids))
        for name, parameter in models.relic_net.named_parameters():
            if name not in trainable_names and parameter.grad is not None:
                raise ValueError(f'frozen relic parameter accumulated gradient: {name}')
        validation_logp = _predict(models.relic_net, z[validation_ids], signed[validation_ids],
                                   fraction[validation_ids], masks[validation_ids], device)
        holdout_logp = _predict(models.relic_net, z[test_ids], signed[test_ids],
                                fraction[test_ids], masks[test_ids], device)
        validation_logps.append(validation_logp)
        holdout_logps.append(holdout_logp)
        training_audits.append({
            'seed': seed, 'trainRows': len(train_ids),
            'trainSources': len(np.unique(source[train_ids])),
            'trainConsumed': int(train_labels.sum()),
            'trainRetained': int(len(train_labels) - train_labels.sum()),
            'epochs': RECIPE['epochs'], 'trainLoss': history,
            'batchOrderSha256': batch_hash.hexdigest(),
            'trainableParameters': sorted(trainable_names),
            'frozenSharedAndOtherHeads': True,
        })
        state_rows.append(c.base._safe_state_dict(models.relic_net))

    model_nlls = np.stack([
        -row[np.arange(len(test_ids)), labels[test_ids]] for row in holdout_logps
    ])
    difference = model_nlls.mean(0) - prior_nll
    paired = audit.grouped_bootstrap(source[test_ids], difference, seed=RECIPE['bootstrapSeed'])
    ci = paired['ci95']
    # Use the third preregistered fit for a single fixed ancestral diagnostic;
    # all three fits are retained for teacher-forced proper-score evaluation.
    models.relic_net.load_state_dict(state_rows[-1], strict=True)
    models.relic_net.eval().requires_grad_(False)
    original_relic_prob = audit.ev.relic_prob
    def candidate_relic_prob(m, zz, cls, frac, mask):
        result = original_relic_prob(m, zz, cls, frac, mask)
        result['lizard'] = audit.lizard_head_probabilities(models, zz, cls, frac, mask)
        return result
    audit.ev.relic_prob = candidate_relic_prob
    arrays['sourceSeed'] = source
    ancestral_failures = {}
    sampled_counts = {'death': 0, 'victory': 0, 'lizardRetained': 0, 'lizardConsumed': 0}
    sample_rng = np.random.default_rng(RECIPE['samplingSeed'])
    try:
        for _ in range(RECIPE['drawsPerTestRow']):
            for ids in audit.ev.batches(len(ancestral_test_ids), 128):
                global_ids = ancestral_test_ids[ids]
                prehp_batch = prehp[global_ids]
                premax_batch = premax[global_ids]
                slots = potion_slots[global_ids]
                caps = capacities[global_ids]
                sample = audit.ev.complete_batch(models, arrays, global_ids, prehp_batch,
                                                 premax_batch, slots, caps, sample_rng)
                sampled_counts['death'] += len(ids) - len(sample['chosen'])
                sampled_counts['victory'] += len(sample['chosen'])
                for k, local in enumerate(sample['chosen']):
                    row = rows[int(global_ids[local])]
                    try:
                        residues = {g: int(v[k]) for g, v in sample['residues'].items()}
                        post = c.assemble_victory(
                            row['transition']['pre'], row['predictorInput'],
                            int(sample['maximum'][k]), int(sample['ending'][k]),
                            int(sample['mask'][k]), residues, models.encounter_names,
                        )
                        state = next(x['data'] for x in post['relics']
                                     if x['id'] == c.base._RELIC_IDS['LIZARD_TAIL'])
                        sampled_counts['lizardRetained' if state == 1 else 'lizardConsumed'] += 1
                    except Exception as error:
                        key = f'{type(error).__name__}:{error}'
                        ancestral_failures[key] = ancestral_failures.get(key, 0) + 1
    finally:
        audit.ev.relic_prob = original_relic_prob

    hard_failures = sum(ancestral_failures.values())
    classification = classify(ci, hard_failures)
    result = {
        'schema': RECIPE['schema'], 'recipe': RECIPE,
        'reviewedImplementationSha': current,
        'corpus': {'path': str(corpus.resolve()), 'sha256': c.base.sha256(corpus),
                   'manifestPath': str(manifest_path.resolve()),
                   'manifestSha256': c.base.sha256(manifest_path),
                   'rows': validated['rows'], 'sourceSeeds': validated['sourceSeeds']},
        'sourceSplit': {
            name: {'sources': sorted({int(s) for s in source[split == name]}),
                   'rows': int(np.sum(split == name))}
            for name in ('train', 'validation', 'test')
        },
        'support': {'fullySupportedActiveLizardWinningRows': len(np.flatnonzero(eligible)),
                    'bySplit': {name: {'rows': int(np.sum((split == name) & eligible)),
                                       'sources': len(np.unique(source[(split == name) & eligible]))}
                                for name in ('train', 'validation', 'test')},
                    'unsupportedReasons': dict(sorted(support_reasons.items()))},
        'training': {'eligibleRows': len(train_ids), 'eligibleSources': len(np.unique(source[train_ids])),
                     'consumed': int(train_labels.sum()), 'retained': int(len(train_labels)-train_labels.sum()),
                     'trainOnlyPriorConsumptionRate': prior_rate, 'fits': training_audits},
        'validation': {'rows': len(validation_ids), 'sources': len(np.unique(source[validation_ids])),
                       'consumed': int(labels[validation_ids].sum()),
                       'retained': int(len(validation_ids)-labels[validation_ids].sum()),
                       'meanNllByFit': [float(-np.mean(lp[np.arange(len(lp)), labels[validation_ids]]))
                                        for lp in validation_logps]},
        'holdout': {'rows': len(test_ids), 'sources': len(np.unique(source[test_ids])),
                    'consumed': int(labels[test_ids].sum()),
                    'retained': int(len(test_ids)-labels[test_ids].sum()),
                    'meanNllByFit': [float(v.mean()) for v in model_nlls],
                    'trainPriorNll': float(prior_nll.mean()),
                    'trainedMinusPriorNll': paired,
                    'sourceBootstrapDifference': paired},
        'ancestral': {'rows': len(ancestral_test_ids),
                      'sources': len(np.unique(source[ancestral_test_ids])),
                      'observedOutcomes': {
                          'win': int(np.sum(win[ancestral_test_ids])),
                          'death': int(np.sum(~win[ancestral_test_ids])),
                      },
                      'drawsPerTestRow': RECIPE['drawsPerTestRow'],
                      'counts': sampled_counts, 'hardValidityFailures': ancestral_failures,
                      'hardValidityFailureCount': hard_failures},
        'frozenArtifacts': c.verify_hashes(),
        'classification': classification,
        'runtimeSupportChanged': False,
        'productionArtifactChanged': False,
    }
    for seed, state in zip(base_seed, state_rows):
        torch.save({'state_dict': state, 'seed': seed, 'recipe': RECIPE,
                    'reviewedImplementationSha': current}, output_dir / f'lizard-head-{seed}.pt')
    result['candidateArtifacts'] = {
        p.name: c.base.sha256(p) for p in sorted(output_dir.glob('lizard-head-*.pt'))
    }
    (output_dir / 'results.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    result['resultsSha256'] = c.base.sha256(output_dir / 'results.json')
    print(json.dumps({k: result[k] for k in ('classification','training','validation','holdout','ancestral','candidateArtifacts')},indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--reviewed-sha', required=True)
    args = parser.parse_args()
    run(args.corpus, args.manifest, args.output_dir, args.reviewed_sha)


if __name__ == '__main__':
    main()
