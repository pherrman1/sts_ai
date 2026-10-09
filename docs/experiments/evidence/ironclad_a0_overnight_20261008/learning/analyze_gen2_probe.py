#!/usr/bin/env python3
"""Two-stage diagnostic only: freeze k0/1 choices, then inspect fixed k2/3 contrasts."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from tools.analysis.vwin_tree_utils import load_trees, predict_rows

E = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008/learning'
RAW = ROOT / 'build/overnight_20261008/learning/gen2-canary-3ed9'
FREEZE = E / 'gen2_canary_3ed9/freeze.json'
FREEZE_SHA = '8c7a1b9060159983b3a09e43e673e891c59be918e82c405784455143235d10bf'
VERIFIER_SHA = '8f9c9a790fa8cd350572de516df80120134a8fdb4072de661876fdd945f4d3aa'
EXPORT_SHA = '928e3520cc00fa87808ff2ae9533529895dade9cade7b9324a3425de1397714d'
PARITY_SHA = 'ae1daf771077d31aa6b013b44b4c4e6cb25327e21b99183c83f41698efa3c4f9'
TREE_UTIL_SHA = 'ab6f2df86101d97a7ecbef2f5b1910992cabdce217f8de953e37b5dd19ae9e47'
SEEDS = list(range(610084000, 610084004))
RULES = ['rollout', 'P0-s0', 'F2-s0']
CHOICES = E / 'gen2_probe_3ed9_choices.json'
RESULT = E / 'gen2_probe_3ed9_evaluation.json'
LIMITS = [
    'Four allocated source runs and at most eight selected states: contract/representation diagnostic only, no population-strength claim.',
    'Retained action set only; early eligible CARD_REWARD/BOSS_RELIC states need not represent important later decisions.',
    'One future k is paired between sibling actions; different decisions within a source are not independent runs.',
    'Historical P0/F2 models omit four hidden encounter-queue features but retain E1 latent potion/rarity counters and privileged-teacher labels.',
    'Model predictions are averaged over legitimate selection-future post-action MAP states; no realized evaluation MAP is used for action selection.',
    'Historical export/native parity establishes arithmetic compatibility, not current-policy calibration or fair deployment qualification.',
    'No training, test-split access, policy installation, adaptive extension, or final confirmation qualification.'
]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def state_key(row):
    return (int(row['sourceSeed']), int(row['decisionIdx']), row['type'])


def read_rows(path, ks=None):
    # After CSV tokenization, inspect k first. Out-of-stage outcomes/features
    # are never interpreted, retained, ranked, summarized, or returned.
    with Path(path).open(newline='') as f:
        for row in csv.DictReader(f):
            if ks is not None and int(row['k']) not in ks:
                continue
            yield row


def checked_input(path, expected, inputs):
    path = Path(path).resolve()
    require(sha(path) == expected, 'changed input: ' + str(path))
    inputs[str(path)] = expected
    return path


def context(contract_path, contract_sha):
    """Consume a reviewed complete contract receipt; do not reopen labels here."""
    inputs = {}
    checked_input(FREEZE, FREEZE_SHA, inputs)
    freeze = read_json(FREEZE)
    require(freeze['source_seeds'] == SEEDS and freeze['futures'] == 4 and
            freeze['selection_k'] == [0, 1] and freeze['evaluation_k'] == [2, 3], 'frozen allocation')
    require(freeze['states_per_seed'] == 2 and freeze['types'] == ['CARD_REWARD', 'BOSS_RELIC'], 'scope changed')
    checked_input(freeze['binary'], freeze['binary_sha256'], inputs)
    checked_input(freeze['teacher'], freeze['teacher_sha256'], inputs)
    checked_input(freeze['policy'], freeze['policy_sha256'], inputs)
    for path, digest in freeze['artifacts'].items():
        checked_input(ROOT / path, digest, inputs)
    checked_input(E / 'verify_gen2.py', VERIFIER_SHA, inputs)
    contract_path = checked_input(contract_path, contract_sha, inputs)
    contract = read_json(contract_path)
    require(contract['status'] == 'CONTRACT_RECEIPT_PASS', 'invalid/incomplete canary')
    require(contract['freeze_sha256'] == FREEZE_SHA and Path(contract['freeze']).resolve() == FREEZE, 'receipt freeze mismatch')
    require(contract['verifier_sha256'] == VERIFIER_SHA and contract['source_seeds'] == SEEDS, 'receipt producer/allocation')
    require(contract['source_trajectory_valid'] and contract['optional_recall_policy_bound_and_banner_checked'], 'source validity/corrected baseline')
    require(contract['evaluation_outcomes_reported'] is False and 0 < contract['states'] <= 8, 'contract scope')
    tables = defaultdict(list)
    raw_inputs = set()
    for item in contract['inputs']:
        path = Path(item['path']).resolve()
        require(path.parent == RAW, 'receipt outside frozen raw directory')
        require(path not in raw_inputs, 'duplicate contract input')
        raw_inputs.add(path)
        checked_input(path, item['sha256'], inputs)
        for suffix in ('options.csv', 'sources.csv', 'labels.csv', 'map.csv', 'receipt.json', 'manifest.json', 'log', 'tree.jsonl'):
            if path.name.endswith('.' + suffix):
                tables[suffix].append(path)
                break
        else:
            raise ValueError('unexpected contract file ' + str(path))
    require(set(tables) == {'options.csv', 'sources.csv', 'labels.csv', 'map.csv', 'receipt.json', 'manifest.json', 'log', 'tree.jsonl'}, 'contract file roles')
    require(all(len(paths) == 4 for paths in tables.values()), 'exact four complete source receipts required')
    require({p.name[:-len('.options.csv')] for p in tables['options.csv']} ==
            {p.name[:-len('.receipt.json')] for p in tables['receipt.json']}, 'prefix mismatch')
    options = defaultdict(dict)
    for path in tables['options.csv']:
        for r in read_rows(path):
            key = state_key(r)
            require(key[0] in SEEDS and key[2] in freeze['types'], 'unreserved option state')
            require(r['optionKey'] not in options[key], 'duplicate semantic key')
            options[key][r['optionKey']] = r
    require(len(options) == contract['states'], 'state coverage')
    sources = {}
    for path in tables['sources.csv']:
        for r in read_rows(path):
            require(r['trajectoryValid'] == '1', 'invalid source trajectory')
            if int(r['decisionIdx']) < 0:
                continue
            key = state_key(r)
            require(key not in sources and key in options, 'source duplicate/option coverage')
            require(len(options[key]) == int(r['options']), 'source retained option count')
            sources[key] = {k: r[k] for k in ('act', 'floor', 'sourceSeed', 'decisionIdx', 'type')}
    require(set(sources) == set(options), 'source coverage')
    for rows in options.values():
        require(sum(int(r['chosen']) for r in rows.values()) == 1, 'actual baseline retention')
    return freeze, contract, tables, options, sources, inputs


def stage_tables(tables, options, ks, with_maps):
    labels, maps = {}, {}
    expected = {(s, option, k) for s, rows in options.items() for option in rows for k in ks}
    for path in tables['labels.csv']:
        for r in read_rows(path, ks):
            state = state_key(r); key = (state, r['optionKey'], int(r['k']))
            require(key in expected and key not in labels, 'stage duplicate/extra label')
            require(r['valid'] == '1' and not r['error'] and r['finalWon'] in ('0', '1'), 'invalid stage label')
            opt = options[state][r['optionKey']]
            require(r['optionIdx'] == opt['optionIdx'] and r['chosen'] == opt['chosen'], 'label action binding')
            future = int(hashlib.sha256(f'ooc-cf-pilot-v2-future:{state[0]}:{state[1]}:{key[2]}'.encode()).hexdigest()[:16], 16)
            require(int(r['futureSeed']) == future, 'stage coupling')
            labels[key] = r
    require(set(labels) == expected, 'stage incomplete sibling labels')
    if with_maps:
        for path in tables['map.csv']:
            for r in read_rows(path, ks):
                key = (state_key(r), r['optionKey'], int(r['k']))
                require(key in expected and key not in maps, 'stage duplicate/extra MAP')
                require(all(r[f] == labels[key][f] for f in ('optionIdx', 'chosen', 'mapAct', 'mapFloor')), 'stage MAP join')
                maps[key] = r
        require(set(maps) == expected, 'stage missing MAP')
    return labels, maps


def model_predictions(maps, inputs):
    checked_input(E / 'export_receipt.json', EXPORT_SHA, inputs)
    checked_input(E / 'native_export_parity_receipt.json', PARITY_SHA, inputs)
    checked_input(ROOT / 'tools/analysis/vwin_tree_utils.py', TREE_UTIL_SHA, inputs)
    exports = read_json(E / 'export_receipt.json')['exports']
    parity = {r['arm']: r for r in read_json(E / 'native_export_parity_receipt.json')['results']}
    require({r['arm'] for r in exports} == {'P0-s0', 'F2-s0'}, 'fixed historical models')
    output = {}
    for record in exports:
        arm = record['arm']; pr = parity[arm]
        require(pr['status'] == 'PASS' and pr['rows'] == 64 and pr['native_xgboost_max_abs_error'] < 1e-5, 'native arithmetic parity')
        require(pr['model_sha256'] == record['sha256'] and pr['native_sha256'] == record['native_sha256'], 'parity custody')
        model = checked_input(record['path'], record['sha256'], inputs)
        checked_input(model.parent / 'predictor.json', record['predictor_sha256'], inputs)
        native = checked_input(record['native_path'], record['native_sha256'], inputs)
        checked_input(pr['log'], pr['log_sha256'], inputs)
        features, trees, logistic, _, margin = load_trees(native)
        require(features == read_json(model.parent / 'predictor.json')['feature_names'] and len(features) == 457, 'feature order')
        require(not set(features) & {'nextEliteId', 'nextFight0', 'nextFight1', 'nextFight2'}, 'hidden future model feature')
        require(logistic == 1, 'probability output expected')
        keys = sorted(maps)
        matrix = np.asarray([[float(maps[k][f]) for f in features] for k in keys], dtype=np.float32)
        require(np.isfinite(matrix).all(), 'invalid model feature')
        scores = predict_rows(matrix, trees, logistic, margin)
        require(np.isfinite(scores).all() and ((scores >= 0) & (scores <= 1)).all(), 'invalid model score')
        output[arm] = dict(zip(keys, map(float, scores)))
    return output


def choose(scores, baseline):
    require(all(math.isfinite(v) for v in scores.values()), 'nonfinite selection score')
    best = max(scores.values())
    tied = [key for key, score in scores.items() if score == best]
    return baseline if baseline in tied else min(tied)


def select(contract_path, contract_sha):
    freeze, contract, tables, options, sources, inputs = context(contract_path, contract_sha)
    labels, maps = stage_tables(tables, options, [0, 1], True)
    predictions = model_predictions(maps, inputs)
    states = []
    for state, opts in sorted(options.items()):
        baseline = next(key for key, r in opts.items() if r['chosen'] == '1')
        scores = {'rollout': {key: sum(int(labels[(state, key, k)]['finalWon']) for k in (0, 1)) / 2 for key in opts}}
        for arm in ('P0-s0', 'F2-s0'):
            scores[arm] = {key: sum(predictions[arm][(state, key, k)] for k in (0, 1)) / 2 for key in opts}
        states.append({'source_seed': state[0], 'decision_idx': state[1], 'type': state[2],
                       'act': int(sources[state]['act']), 'floor': int(sources[state]['floor']),
                       'baseline_option_key': baseline, 'scores': scores,
                       'choices': {rule: choose(scores[rule], baseline) for rule in RULES}})
    return {'schema': 'overnight_gen2_probe_choices_v1', 'status': 'CHOICES_FROZEN',
            'freeze_sha256': FREEZE_SHA, 'source_sha': freeze['source_sha'], 'binary_sha256': freeze['binary_sha256'],
            'contract': str(Path(contract_path).resolve()), 'contract_sha256': contract_sha,
            'selection_k': [0, 1], 'evaluation_k': [2, 3], 'evaluation_outcomes_opened': False,
            'tie_rule': 'highest mean, actual source baseline favored exact ties, then semantic key lexicographic',
            'rules': RULES, 'states': states, 'source_seeds': SEEDS,
            'inputs': [{'path': p, 'sha256': h} for p, h in sorted(inputs.items())],
            'frozen_epoch': time.time(), 'limits': LIMITS}


def evaluate(choice_sha):
    require(sha(CHOICES) == choice_sha, 'frozen choice hash')
    choice = read_json(CHOICES)
    require(choice['status'] == 'CHOICES_FROZEN' and choice['analysis_script_sha256'] == sha(__file__), 'reviewed frozen selector')
    require(choice['selection_k'] == [0, 1] and choice['evaluation_k'] == [2, 3] and choice['evaluation_outcomes_opened'] is False, 'frozen split')
    require(choice['rules'] == RULES and choice['source_seeds'] == SEEDS, 'frozen scope/rules')
    require(choice['frozen_epoch'] < time.time(), 'choice must precede evaluation')
    inputs = {}
    for item in choice['inputs']:
        checked_input(item['path'], item['sha256'], inputs)
    freeze, contract, tables, options, sources, current_inputs = context(choice['contract'], choice['contract_sha256'])
    inputs.update(current_inputs)
    frozen = {(s['source_seed'], s['decision_idx'], s['type']): s for s in choice['states']}
    require(len(frozen) == len(choice['states']) and set(frozen) == set(options), 'frozen states coverage')
    # No new predictions or selection rankings in the evaluation stage.
    labels, _ = stage_tables(tables, options, [2, 3], False)
    states = []
    source_gains = {rule: defaultdict(list) for rule in RULES}
    for state, opts in sorted(options.items()):
        fixed = frozen[state]; baseline = fixed['baseline_option_key']
        require(baseline in opts and opts[baseline]['chosen'] == '1', 'fixed baseline binding')
        base = [int(labels[(state, baseline, k)]['finalWon']) for k in (2, 3)]
        item = {'source_seed': state[0], 'decision_idx': state[1], 'type': state[2],
                'act': int(sources[state]['act']), 'floor': int(sources[state]['floor']),
                'baseline_option_key': baseline, 'baseline_wins': sum(base), 'future_pairs': 2, 'rules': {}}
        for rule in RULES:
            selected = fixed['choices'][rule]
            require(selected in opts, 'frozen action absent')
            win = [int(labels[(state, selected, k)]['finalWon']) for k in (2, 3)]
            delta = [a-b for a, b in zip(win, base)]
            gain = sum(delta) / 2
            source_gains[rule][state[0]].append(gain)
            item['rules'][rule] = {'option_key': selected, 'selected_wins': sum(win), 'paired_gain': gain,
                                  'selected_only': sum(d > 0 for d in delta), 'baseline_only': sum(d < 0 for d in delta),
                                  'both_win': sum(a == b == 1 for a, b in zip(win, base)),
                                  'both_lose': sum(a == b == 0 for a, b in zip(win, base))}
        states.append(item)
    summaries = {}
    for rule in RULES:
        per_source = {str(seed): (sum(source_gains[rule][seed])/len(source_gains[rule][seed]) if source_gains[rule][seed] else None) for seed in SEEDS}
        observed = [v for v in per_source.values() if v is not None]
        summaries[rule] = {'per_source_mean_paired_gain': per_source, 'observed_source_clusters': len(observed),
                           'allocated_source_clusters': 4, 'equal_source_mean_paired_gain': sum(observed)/len(observed),
                           'pooled_state_mean_paired_gain': sum(s['rules'][rule]['paired_gain'] for s in states)/len(states),
                           'action_changes': sum(s['rules'][rule]['option_key'] != s['baseline_option_key'] for s in states)}
    checked_input(CHOICES, choice_sha, inputs)
    return {'schema': 'overnight_gen2_probe_evaluation_v1', 'status': 'DIAGNOSTIC_EVALUATION_COMPLETE',
            'choice_sha256': choice_sha, 'freeze_sha256': FREEZE_SHA, 'selection_k': [0, 1], 'evaluation_k': [2, 3],
            'source_seeds': SEEDS, 'states': states, 'summaries': summaries, 'confidence_intervals': None,
            'inference': 'Descriptive contrasts only; four source clusters cannot qualify any challenger or establish a ranking.',
            'contract_cost': {k: contract[k] for k in ('source_cpu_seconds', 'branch_cpu_seconds', 'invocation_wall_seconds_sum', 'label_rows')},
            'inputs': [{'path': p, 'sha256': h} for p, h in sorted(inputs.items())], 'limits': LIMITS}


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='stage', required=True)
    selection = sub.add_parser('select')
    selection.add_argument('--contract', type=Path, required=True)
    selection.add_argument('--contract-sha256', required=True)
    evaluation = sub.add_parser('evaluate')
    evaluation.add_argument('--choice-sha256', required=True)
    args = p.parse_args()
    output = CHOICES if args.stage == 'select' else RESULT
    require(not output.exists(), 'refusing overwrite')
    try:
        result = select(args.contract, args.contract_sha256) if args.stage == 'select' else evaluate(args.choice_sha256)
    except Exception as error:
        result = {'status': 'INVALID_STOP_LANE', 'error': repr(error), 'stage': args.stage}
    result['analysis_script_sha256'] = sha(__file__)
    with output.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps({'status': result['status'], 'path': str(output), 'sha256': sha(output)}, indent=2))
    return 0 if result['status'] != 'INVALID_STOP_LANE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
