#!/usr/bin/env python3
"""Analyze raw fixed-action Searcher3 sibling CRN diagnostic rows."""
import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict

StateKey = tuple[int, int, int, int]


def state_key(row):
    # state_id is visible-state provenance only; captured decision provenance
    # makes this identity unique when two decisions share a visible hash.
    return (int(row['source_seed']), int(row['fight_idx']),
            int(row['decision_idx']), int(row['state_id']))


def quantile(values, q):
    values = sorted(values)
    if not values:
        return math.nan
    p = (len(values) - 1) * q
    lo = int(p)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] if hi == lo else values[lo] + (values[hi] - values[lo]) * (p - lo)


def sign(value, tolerance=1e-12):
    return 1 if value > tolerance else (-1 if value < -tolerance else 0)


def analyze(rows, bootstrap=2000, seed=20260824):
    # Keep every raw attempt, including invalid attempts. A batch is complete
    # only when it has exactly K rows and every row is valid.
    attempts = defaultdict(list)
    invalid = Counter()
    for row in rows:
        state = state_key(row)
        action = int(row['action_id'])
        k = int(row['K'])
        rep = int(row['replicate'])
        mode = row['sampling_mode']
        key = state, action, k, rep, mode
        if int(row['valid']):
            attempts[key].append(float(row['value']))
        else:
            attempts[key].append(None)
            invalid[mode, k, state] += 1

    def complete(key, k):
        values = attempts.get(key, [])
        return len(values) == k and all(value is not None for value in values)

    references = {}
    for (state, action, k, rep, mode), values in attempts.items():
        if mode == 'reference' and rep == 0 and complete((state, action, k, rep, mode), 128):
            references[state, action] = statistics.fmean(values)

    budgets = sorted({k for (state, action, k, rep, mode) in attempts
                      if mode in ('crn', 'independent')})
    report = {'invalid_attempts': sum(invalid.values()),
              'reference_actions': len(references), 'budgets': {}}
    rng = random.Random(seed)

    for k in budgets:
        k_states = sorted({state for state, action, kk, rep, mode in attempts
                           if kk == k and mode in ('crn', 'independent')})
        pair_records = []
        best_counts = Counter()
        stability = defaultdict(list)
        standardized_shifts = []
        total_reps = usable_reps = 0
        states_with_invalid = set()
        invalid_by_mode = Counter()

        for state in k_states:
            actions = sorted({action for ss, action, kk, rep, mode in attempts
                              if ss == state and kk == k and mode in ('crn', 'independent')})
            state_reps = {rep for ss, action, kk, rep, mode in attempts
                          if ss == state and kk == k and mode in ('crn', 'independent')}
            total_reps += len(state_reps)
            for mode in ('independent', 'crn'):
                invalid_by_mode[mode] += invalid[mode, k, state]
            if any(invalid[mode, k, state] for mode in ('independent', 'crn')):
                states_with_invalid.add(state)

            # Common-valid replicate intersection: both arms, every selected
            # action, exactly K valid rows, and no extra/invalid rows.
            common_reps = []
            for rep in sorted(state_reps):
                usable = all(
                    complete((state, action, k, rep, mode), k)
                    for mode in ('independent', 'crn')
                    for action in actions
                )
                if usable:
                    common_reps.append(rep)
            usable_reps += len(common_reps)
            if len(common_reps) < 1 or any((state, action) not in references for action in actions):
                continue

            ref_best = max(actions, key=lambda action: (references[state, action], -action))
            q_by_mode = {mode: {} for mode in ('independent', 'crn')}
            for mode in q_by_mode:
                choices = []
                for rep in common_reps:
                    q = {action: statistics.fmean(attempts[state, action, k, rep, mode])
                         for action in actions}
                    q_by_mode[mode][rep] = q
                    choice = max(actions, key=lambda action: (q[action], -action))
                    choices.append(choice)
                    best_counts[mode, 'n'] += 1
                    best_counts[mode, 'ok'] += choice == ref_best
                if choices:
                    stability[mode].append(max(Counter(choices).values()) / len(choices))

            for i, action_a in enumerate(actions):
                for action_b in actions[i + 1:]:
                    deltas = {
                        mode: [q_by_mode[mode][rep][action_a] - q_by_mode[mode][rep][action_b]
                               for rep in common_reps]
                        for mode in ('independent', 'crn')
                    }
                    if len(deltas['independent']) < 2:
                        continue
                    variance_independent = statistics.variance(deltas['independent'])
                    variance_crn = statistics.variance(deltas['crn'])
                    ratio = None if variance_independent <= 1e-12 else variance_crn / variance_independent
                    ref_sign = sign(references[state, action_a] - references[state, action_b])
                    record = {
                        'state': state, 'a': action_a, 'b': action_b,
                        'variance_independent': variance_independent,
                        'variance_crn': variance_crn, 'ratio': ratio,
                        'replicates': len(common_reps),
                    }
                    for mode in ('independent', 'crn'):
                        record[mode + '_sign_n'] = len(deltas[mode])
                        record[mode + '_sign_errors'] = sum(
                            sign(value) != ref_sign for value in deltas[mode])
                    pair_records.append(record)
                    if variance_independent > 1e-12:
                        standardized_shifts.append(
                            (statistics.fmean(deltas['crn']) - statistics.fmean(deltas['independent']))
                            / math.sqrt(variance_independent))

        ratios = [record['ratio'] for record in pair_records
                  if record['ratio'] is not None and math.isfinite(record['ratio'])]
        bootstrap_ratios = []
        if ratios:
            for _ in range(bootstrap):
                bootstrap_ratios.append(statistics.median(rng.choices(ratios, k=len(ratios))))

        def sign_error(mode):
            n = sum(record[mode + '_sign_n'] for record in pair_records)
            errors = sum(record[mode + '_sign_errors'] for record in pair_records)
            return {'errors': errors, 'n': n, 'rate': errors / n if n else math.nan}

        def agreement(mode):
            n = best_counts[mode, 'n']
            return best_counts[mode, 'ok'] / n if n else math.nan

        independent_agreement = agreement('independent')
        crn_agreement = agreement('crn')
        report['budgets'][str(k)] = {
            'total_replicates': total_reps,
            'usable_common_replicates': usable_reps,
            'dropped_replicates': total_reps - usable_reps,
            'invalid_attempts_independent': invalid_by_mode['independent'],
            'invalid_attempts_crn': invalid_by_mode['crn'],
            'states_with_any_invalid': len(states_with_invalid),
            'usable_pairs': len(pair_records),
            'degenerate_independent_pairs': sum(record['ratio'] is None for record in pair_records),
            'variance_ratio': {
                'median': statistics.median(ratios) if ratios else math.nan,
                'q1': quantile(ratios, .25), 'q3': quantile(ratios, .75),
                'fraction_below_1': sum(value < 1 for value in ratios) / len(ratios) if ratios else math.nan,
                'bootstrap95': [quantile(bootstrap_ratios, .025), quantile(bootstrap_ratios, .975)],
            },
            'sign_error': {'independent': sign_error('independent'), 'crn': sign_error('crn')},
            'best_action_agreement': {
                'independent': independent_agreement, 'crn': crn_agreement,
                'difference_pp': 100 * (crn_agreement - independent_agreement),
            },
            'best_action_stability': {
                mode: statistics.fmean(stability[mode]) if stability[mode] else math.nan
                for mode in ('independent', 'crn')
            },
            'standardized_mean_shift': (
                statistics.fmean(standardized_shifts) if standardized_shifts else math.nan
            ),
        }
    return report


def _sample_rows(state, mode, k=4, reps=8, invalid=None, noise_scale=1.0):
    rows = []
    source, fight, decision, visible = state
    for rep in range(reps):
        for action in (0, 1):
            for sample in range(k):
                bad = invalid == (mode, rep, action, sample)
                value = 10 - action + (rep - reps / 2) * noise_scale * (1 if action == 0 else -1)
                rows.append({
                    'source_seed': str(source), 'fight_idx': str(fight),
                    'decision_idx': str(decision), 'state_id': str(visible),
                    'action_id': str(action), 'K': str(k), 'replicate': str(rep),
                    'sampling_mode': mode, 'valid': '0' if bad else '1',
                    'value': str(value),
                })
    return rows


def _reference_rows(states):
    rows = []
    for state in states:
        source, fight, decision, visible = state
        for action in (0, 1):
            for sample in range(128):
                rows.append({
                    'source_seed': str(source), 'fight_idx': str(fight),
                    'decision_idx': str(decision), 'state_id': str(visible),
                    'action_id': str(action), 'K': '128', 'replicate': '0',
                    'sampling_mode': 'reference', 'valid': '1',
                    'value': str(10 - action),
                })
    return rows


def self_test():
    # Two distinct captured decisions share a visible hash but remain separate.
    state_a = (1, 0, 0, 777)
    state_b = (2, 3, 4, 777)
    rows = (_sample_rows(state_a, 'independent', noise_scale=1.0)
            + _sample_rows(state_a, 'crn', noise_scale=.25)
            + _sample_rows(state_b, 'independent', noise_scale=1.0)
            + _sample_rows(state_b, 'crn', noise_scale=.25)
            + _reference_rows((state_a, state_b)))
    result = analyze(rows, bootstrap=50)
    budget = result['budgets']['4']
    assert budget['usable_pairs'] == 2
    assert budget['total_replicates'] == 16
    assert budget['dropped_replicates'] == 0
    assert budget['variance_ratio']['median'] < .1

    # Replicate 7 is complete in independent but has one invalid CRN row.
    asymmetric = (_sample_rows((3, 0, 0, 888), 'independent')
                  + _sample_rows((3, 0, 0, 888), 'crn', invalid=('crn', 7, 1, 3))
                  + _reference_rows(((3, 0, 0, 888),)))
    asymmetric_result = analyze(asymmetric, bootstrap=50)['budgets']['4']
    assert asymmetric_result['total_replicates'] == 8
    assert asymmetric_result['usable_common_replicates'] == 7
    assert asymmetric_result['dropped_replicates'] == 1
    assert asymmetric_result['invalid_attempts_independent'] == 0
    assert asymmetric_result['invalid_attempts_crn'] == 1
    assert asymmetric_result['states_with_any_invalid'] == 1
    assert asymmetric_result['sign_error']['independent']['n'] == 7
    assert asymmetric_result['sign_error']['crn']['n'] == 7
    print('analyze_s3_sibling_crn self-test PASS')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', nargs='?')
    parser.add_argument('--output')
    parser.add_argument('--bootstrap', type=int, default=2000)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.csv:
        parser.error('csv is required')
    with open(args.csv, newline='') as stream:
        result = analyze(csv.DictReader(stream), args.bootstrap)
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=True)
    if args.output:
        with open(args.output, 'w') as stream:
            stream.write(text + '\n')
    else:
        print(text)


if __name__ == '__main__':
    main()
