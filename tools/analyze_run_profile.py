#!/usr/bin/env python3
"""Validate STS_RUN_PROFILE accounting and describe cost/observed root stability."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
import math
import statistics
from pathlib import Path


def ranked(actions, rule):
    if rule == 'q_visits_id':
        return sorted((a for a in actions if a['visits']), key=lambda a: (-a['q'], -a['visits'], a['id']))
    if rule != 'visits_q_id':
        raise ValueError('unknown root selection rule')
    return sorted(actions, key=lambda a: (-a['visits'], -a['q'], a['id']))


def action_stats(actions, simulations, budget, rule):
    if not actions:
        return None
    if len({a['id'] for a in actions}) != len(actions):
        raise ValueError('duplicate root actions')
    if any(type(a['visits']) is not int or a['visits'] < 0 or not math.isfinite(a['q'])
           or not 0 <= a['q'] <= 1 or not math.isfinite(a['prior']) or a['prior'] < 0 for a in actions):
        raise ValueError('invalid root statistics')
    if sum(a['visits'] for a in actions) != simulations:
        raise ValueError('root visits do not sum to completed simulations')
    ordered = ranked(actions, rule)
    if not ordered:
        return None
    first = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None
    visit_sorted = sorted((a['visits'] for a in actions), reverse=True)
    margin = visit_sorted[0] - (visit_sorted[1] if len(visit_sorted) > 1 else 0)
    priors = sorted((a['prior'] for a in actions), reverse=True)
    return {'winner': first['id'], 'top1': first, 'top2': second,
            'visit_gap_share': margin / simulations if simulations else None,
            'q_gap': first['q'] - second['q'] if second else None,
            'strict_visit_lock': rule == 'visits_q_id' and simulations > 0
            and margin > budget - simulations,
            'prior_entropy': -sum(p * math.log(p) for p in priors if p),
            'top_prior': priors[0], 'second_prior': priors[1] if len(priors) > 1 else 0}


def decision(row):
    hist = row['expanded_action_histogram']
    if any(str(int(k)) != k or int(k) < 0 or type(v) is not int or v < 0 for k, v in hist.items()):
        raise ValueError('invalid branching histogram')
    if sum(hist.values()) != row['expanded_nodes']:
        raise ValueError('expanded-node histogram does not reconcile')
    n, budget = row['completed_simulations'], row['configured_simulations']
    if not 0 <= n <= budget:
        raise ValueError('invalid simulation count')
    points = row['checkpoints']
    expected = [b for b in (128, 256, 512, 1024, 2048, 4096) if b <= n]
    if not row['singleton_bypass'] and [p['simulations'] for p in points] != expected:
        raise ValueError('missing or unordered checkpoints')
    observed = []
    for point in points:
        stats = action_stats(point['actions'], point['simulations'], budget, row['selection_rule'])
        observed.append({'simulations': point['simulations'], **stats})
    final = None if row['aborted'] else action_stats(row['actions'], n, budget, row['selection_rule'])
    if final and final['winner'] != row['selected_action']:
        raise ValueError('final root selection disagrees with rule')
    if final and n and (not observed or observed[-1]['simulations'] != n):
        observed.append({'simulations': n, **final})
    stable = None
    if final and n:
        for i, point in enumerate(observed):
            if all(p['winner'] == final['winner'] for p in observed[i:]):
                stable = point['simulations']
                break
    return {**row, 'final_statistics': final, 'checkpoint_statistics': observed,
            'b_stable_observed': stable,
            'b_stable_full_budget': stable if n == budget and not row['aborted'] else None,
            'leader_changes': sum(a['winner'] != b['winner'] for a, b in zip(observed, observed[1:]))}


def analyze(rows):
    if not rows or any(r['schema'] != 1 or r['kind'] not in ('floor', 'ooc_decision') for r in rows):
        raise ValueError('empty or unknown profile schema')
    floors = [r for r in rows if r['kind'] == 'floor']
    decisions = [decision(r) for r in rows if r['kind'] == 'ooc_decision']
    fk = lambda r: (r['seed'], r['act'], r['floor'])
    if len({fk(r) for r in floors}) != len(floors):
        raise ValueError('duplicate floor')
    if len({(r['seed'], r['decision']) for r in decisions}) != len(decisions):
        raise ValueError('duplicate decision')
    grouped = defaultdict(list)
    for row in decisions:
        grouped[fk(row)].append(row)
    for row in floors:
        cohort = grouped.pop(fk(row), [])
        if row['status'] == 'abort':
            continue # partial work remains explicitly unqualified
        for floor_field, decision_field in [('ooc_simulations', 'completed_simulations'),
                ('leaf_evaluations', 'leaf_evaluations'), ('transition_samples', 'transition_samples'),
                ('outcome_particles', 'outcome_particles'), ('ctm_samples', 'ctm_samples')]:
            if row[floor_field] != sum(d[decision_field] for d in cohort):
                raise ValueError(f'floor {fk(row)} does not reconcile: {floor_field}')
    if grouped:
        raise ValueError('decision lacks a floor record (incomplete run)')
    hist = Counter()
    for row in decisions:
        hist.update({int(k): v for k, v in row['expanded_action_histogram'].items()})
    expanded = sum(hist.values())
    summary = {'floors': len(floors), 'decisions': len(decisions),
               'aborted_searches': sum(r['aborted'] for r in decisions),
               'expanded_nodes': expanded, 'exact_branching': dict(sorted(hist.items())),
               'branching_shares': {str(n): sum(v for k,v in hist.items() if k >= n) / expanded if expanded else None
                                    for n in (1, 3, 5, 10)},
               'singleton_share': hist[1] / expanded if expanded else None,
               'full_budget_stability': dict(sorted(Counter(r['b_stable_full_budget'] for r in decisions
                                            if r['b_stable_full_budget'] is not None).items())),
               'unknown_full_budget_stability': sum(r['b_stable_full_budget'] is None for r in decisions),
               'cost_by_room': {}, 'slowest_floors': sorted(floors, key=lambda r: -r['wall_seconds'])[:20],
               'decisions_detail': decisions,
               'interpretation': 'B_stable is retrospective agreement at observed checkpoints, not a safe stopping policy. '
               'Full-budget stability is null for aborted, singleton, or early-stopped searches. '
               'Real-combat timing includes the backend lifecycle, not only tree search. '
               'Floor wall/CPU totals include instrumentation overhead; nested components must not be added twice.'}
    cpu_order = sorted(floors, key=lambda r: -r['thread_cpu_seconds'])
    total_cpu = sum(r['thread_cpu_seconds'] for r in floors)
    summary['slowest_floors_by_cpu'] = cpu_order[:10]
    summary['top_floor_cpu_shares'] = {str(n): sum(r['thread_cpu_seconds'] for r in cpu_order[:n]) / total_cpu
                                      if total_cpu else None for n in (5, 10)}
    observed = [r for r in decisions if r['b_stable_observed'] is not None]
    summary['observed_stability'] = dict(sorted(Counter(r['b_stable_observed'] for r in observed).items()))
    summary['stable_by_budget_observed_only'] = {
        str(n): sum(r['b_stable_observed'] <= n for r in observed) / len(observed) if observed else None
        for n in (128, 256, 512, 1024, 2048, 4096)}
    eligible = [r for r in decisions if r['b_stable_full_budget'] is not None]
    summary['stable_by_budget_full_budget_only'] = {
        str(n): sum(r['b_stable_full_budget'] <= n for r in eligible) / len(eligible) if eligible else None
        for n in (128, 256, 512, 1024, 2048, 4096)}
    predictors = {
        'root_action_count': lambda r: len(r['actions']),
        'screen': lambda r: r['screen'], 'room': lambda r: r['room'],
        'prior_entropy_half_nat': lambda r: math.floor(r['final_statistics']['prior_entropy'] * 2) / 2,
        'prior_gap_tenth': lambda r: math.floor((r['final_statistics']['top_prior'] - r['final_statistics']['second_prior']) * 10) / 10,
        'first_checkpoint_visit_gap_tenth': lambda r: math.floor(r['checkpoint_statistics'][0]['visit_gap_share'] * 10) / 10,
        'first_checkpoint_q_gap_tenth': lambda r: math.floor((r['checkpoint_statistics'][0]['q_gap'] or 0) * 10) / 10,
    }
    for label, cohort, field in [('full_budget', eligible, 'b_stable_full_budget'),
                                  ('observed', observed, 'b_stable_observed')]:
        summary[label + '_stability_crosstabs'] = {}
        for name, key in predictors.items():
            bins = defaultdict(list)
            for r in cohort:
                bins[str(key(r))].append(r[field])
            summary[label + '_stability_crosstabs'][name] = {
                k: {'decisions': len(v), 'median_b_stable': statistics.median(v),
                    'histogram': dict(sorted(Counter(v).items()))} for k, v in sorted(bins.items())}
    for room in sorted({r['room'] for r in floors}):
        cohort = [r for r in floors if r['room'] == room]
        summary['cost_by_room'][room] = {k: sum(r[k] for r in cohort) for k in (
            'wall_seconds', 'thread_cpu_seconds', 'real_combat_wall_seconds', 'real_combat_cpu_seconds',
            'ooc_wall_seconds', 'ooc_cpu_seconds', 'combat_decisions', 'ooc_simulations')}
        summary['cost_by_room'][room]['floors'] = len(cohort)
        for field in ('wall_seconds', 'thread_cpu_seconds'):
            summary['cost_by_room'][room][field + '_mean'] = statistics.mean(r[field] for r in cohort)
            summary['cost_by_room'][room][field + '_median'] = statistics.median(r[field] for r in cohort)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    opener = gzip.open if args.profile.suffix == '.gz' else open
    with opener(args.profile, 'rt') as f:
        result = analyze([json.loads(line) for line in f if line.strip()])
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('decisions_detail', 'slowest_floors', 'slowest_floors_by_cpu', 'full_budget_stability_crosstabs', 'observed_stability_crosstabs')}, indent=2))
