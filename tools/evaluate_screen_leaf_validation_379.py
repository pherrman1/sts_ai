#!/usr/bin/env python3
"""Join frozen VALIDATION S0/model evidence and actual MAP calibration links.

This creates diagnostic reports only. No candidate choice, TEST access or latch.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from audit_screen_leaf_379 import EXPECTED, digest, source_split_function
from screen_leaf_data_379 import DecisionCorpus, PROVISIONAL_MASK
from run_screen_leaf_replay_379 import verify_temporal
from tools.screen_leaf_metrics_379 import predictive_report, transition_report
from tools.vwin_refresh_evaluation import predictive_metrics

UBJ = Path('/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2/model.ubj')
UBJ_SHA = '99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd'


def load(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def identity(row):
    return int(row['sourceSeed']), row['branchId'], int(row['rowIdx'])


def run(training, recovered, output):
    corpus = DecisionCorpus()
    protocol = load(recovered / 'protocol.json')
    final = load(recovered / 'result.json')
    if protocol['corpus_sha256'] != EXPECTED or final['status'] != 'PASS' or final['protocol_sha256'] != digest(recovered / 'protocol.json'):
        raise ValueError('full S0 recovery not qualified')
    if {r['seed'] for r in final['results']} != set(corpus.expected_sources('VALIDATION')):
        raise ValueError('S0 source population differs')
    training_final = load(training / 'result.json')
    if training_final['status'] != 'TRAINING_COMPLETE_NOT_QUALIFIED':
        raise ValueError('fixed training incomplete')
    prereg = load(training / 'preregistered.json')
    if tuple(prereg['replacement_candidates']) != tuple(PROVISIONAL_MASK):
        raise ValueError('training mask differs')
    for filename, sha in prereg['code'].items():
        if digest(Path(filename)) != sha: raise ValueError('reviewed training implementation changed')
    metadata = load(training / 'validation-identities.json')
    ids = [identity(r) for r in metadata]
    if {r['sourceSeed'] for r in metadata} != set(corpus.expected_sources('VALIDATION')):
        raise ValueError('training VALIDATION sources differ')
    labels = np.load(training / 'validation-labels.npy', allow_pickle=False)
    if len(set(ids)) != len(ids) or len(labels) != len(ids): raise ValueError('duplicate/unaligned validation identities')
    if dict(Counter(r['screen'] for r in metadata)) != corpus.expected_counts('VALIDATION'):
        raise ValueError('training VALIDATION row counts differ')
    # Rejoin original labels and public row identities, not merely saved counts.
    original = {identity(r['identity']): (r['label'], dict(r['identity'], screen=r['screen'])) for r in corpus.iter_rows('VALIDATION')}
    if list(original) != ids or any(original[key] != (int(labels[i]), metadata[i]) for i, key in enumerate(ids)):
        raise ValueError('saved VALIDATION labels/identities differ from corpus')
    s0, links, exclusions, evidence = {}, {}, Counter(), []
    expected_components = {c['sourceSeed']: c for c in corpus.components if c['split'] == 'VALIDATION'}
    protocol_sources = {s['seed']: s for s in protocol['sources']}
    if set(protocol_sources) != set(expected_components) or len(protocol['sources']) != 155:
        raise ValueError('recovery protocol source set differs')
    for result in final['results']:
        seed = result['seed']
        component, source = expected_components[seed], protocol_sources[seed]
        if Path(source['manifest']).resolve() != Path(component['manifest']).resolve() or source['manifest_sha256'] != component['manifest_sha256']:
            raise ValueError('recovery source not bound to corpus component')
        if digest(Path(source['manifest'])) != component['manifest_sha256']:
            raise ValueError('recovery source manifest changed')
        manifest = load(source['manifest'])
        if result['status'] != 'PASS': raise ValueError('failed recovered source')
        source_dir = recovered / str(seed)
        result_path = source_dir / 'result.json'
        if load(result_path) != result: raise ValueError('aggregate/source result differs')
        predictions = source_dir / 'predictions.jsonl'
        if digest(predictions) != result['predictions_sha256']: raise ValueError('S0 predictions changed')
        replay = Path(result['replay']['directory'])
        if digest(replay / 'receipt.json') != result['replay']['receipt_sha256'] or digest(replay / 'result.json') != result['replay']['result_sha256']:
            raise ValueError('replay receipt/result changed')
        if digest(replay / 'replay.map.csv') != manifest['outputs']['map.csv']:
            raise ValueError('replayed MAP is not the frozen original table')
        if digest(replay / 'snapshots.jsonl') != result['replay']['snapshots_sha256']:
            raise ValueError('recovered snapshots changed')
        if verify_temporal(replay, seed) != result['replay']['temporal']:
            raise ValueError('temporal evidence changed')
        with predictions.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['sourceSeed'] != seed or len(row['values']) != 1: raise ValueError('S0 protocol differs')
                key = identity(row)
                if key in s0: raise ValueError('duplicate S0 identity')
                s0[key] = row['values'][0]
        with (replay / 'snapshots.jsonl').open() as stream:
            for line in stream:
                row = json.loads(line)
                key = identity(row)
                if key not in original: continue
                link = row['calibrationLink']
                exclusions[(row['screenContents']['screen'], link['status'])] += 1
                if link['status'] == 'EXACT_LAST_CAPTURED_TO_OBSERVED_MAP': links[key] = link['map']
        evidence.append({'seed': seed, 'result_sha256': digest(result_path), 'predictions_sha256': digest(predictions)})
    if not set(ids) <= set(s0): raise ValueError('S0 missing model-evaluation rows')
    baseline = np.array([s0[key] for key in ids])
    if digest(UBJ) != UBJ_SHA: raise ValueError('X2-B source UBJ changed')
    import xgboost as xgb
    booster = xgb.Booster(params={'nthread': 1})
    booster.load_model(UBJ)
    # MAP rich order is the original full1017 header, not the selected461 order.
    first_source = protocol['sources'][0]
    if digest(Path(first_source['manifest'])) != first_source['manifest_sha256']:
        raise ValueError('MAP feature-order source manifest changed')
    full_header = load(first_source['manifest'])['stateFeatures']['header']
    if hashlib.sha256(full_header.encode()).hexdigest() != 'd8fdd003636fc00e537320f0406a2c36f890d8ba16edc10cc7c2b0fbdf7ed836':
        raise ValueError('MAP rich feature-order mismatch')
    full_names = full_header.split(',')
    selected_indices = [full_names.index(name) for name in corpus.feature_names]
    matched_ids = np.array([i for i, key in enumerate(ids) if key in links], dtype=np.int64)
    if not len(matched_ids): raise ValueError('no verified matched calibration transitions')
    map_features = np.array([[float(links[ids[i]]['features'].split(',')[j]) for j in selected_indices] for i in matched_ids], dtype=np.float32)
    map_values = booster.predict(xgb.DMatrix(map_features, feature_names=corpus.feature_names))
    matched_metadata = [metadata[i] for i in matched_ids]
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'custody.json', {'training_prereg_sha256': digest(training / 'preregistered.json'),
              'training_result_sha256': digest(training / 'result.json'), 's0_protocol_sha256': digest(recovered / 'protocol.json'),
              'sources': evidence, 'map_ubj_sha256': UBJ_SHA,
              'matched_coverage': dict(Counter(r['screen'] for r in matched_metadata)),
              'decision_act_to_map_act': dict(Counter(f"{metadata[i]['act']}->{links[ids[i]]['act']}" for i in matched_ids)),
              'link_status_counts': {screen + '/' + status: count for (screen, status), count in exclusions.items()},
              'test_access': 'NONE; VALIDATION only; no selection or frozen tolerance is implied'})
    np.savez(output / 'aligned-validation.npz', s0=baseline, matched_indices=matched_ids, map_values=map_values)
    write_new(output / 'S0.json', {'predictive': predictive_report(labels, baseline, metadata),
              'calibration': transition_report(baseline[matched_ids], map_values, matched_metadata)})
    for arm in ('S1', 'S2'):
        path = training / f'{arm}-ensemble-validation.npy'
        if digest(path) != training_final['arms'][arm]['ensemble_predictions_sha256']:
            raise ValueError('ensemble predictions changed')
        prediction = np.load(path, allow_pickle=False)
        individual = {}
        for seed in (0, 1, 2):
            seed_path = training / f'{arm}-seed{seed}-validation.npy'
            record = load(training / f'{arm}-seed{seed}.json')
            if record != training_final['arms'][arm]['individual'][seed]:
                raise ValueError('seed receipt differs from completed training evidence')
            if digest(seed_path) != record['predictions_sha256']: raise ValueError('seed prediction changed')
            p = np.load(seed_path, allow_pickle=False)
            individual[str(seed)] = {'overall': predictive_metrics(labels, p)}
            for family in PROVISIONAL_MASK:
                family_ids = np.array([i for i, r in enumerate(metadata) if r['screen'] == family])
                individual[str(seed)][family] = predictive_metrics(labels[family_ids], p[family_ids])
        write_new(output / f'{arm}.json', {'individual_seeds': individual,
                  'predictive': predictive_report(labels, prediction, metadata, baseline=baseline),
                  'calibration': transition_report(prediction[matched_ids], map_values, matched_metadata)})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training', required=True, type=Path)
    p.add_argument('--recovered', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    run(a.training.resolve(), a.recovered.resolve(), a.output.resolve())
