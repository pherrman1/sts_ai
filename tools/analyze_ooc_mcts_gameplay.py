#!/usr/bin/env python3
"""Analyze the frozen 32-seed paired live OOC-MCTS engineering gameplay gate."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def read_rows(path):
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    keyed = {int(row['seed']): row for row in rows}
    if len(keyed) != len(rows):
        raise ValueError(f'duplicate seeds: {path}')
    return keyed


def discordant_pvalue(treatment_only, control_only):
    n = treatment_only + control_only
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(treatment_only, control_only) + 1)) / 2**n) if n else 1.0


def analyze(control_path, treatment_path, bootstrap_samples=200000):
    control, treatment = read_rows(control_path), read_rows(treatment_path)
    seeds = list(range(970000, 970032))
    expected = set(seeds)
    if set(control) != expected or set(treatment) != expected:
        raise ValueError('gate must contain exactly paired fresh seeds 970000..970031')
    traces = [read_rows(Path(str(p) + '.mcts.csv')) for p in (control_path, treatment_path)]
    if any(set(trace) != expected for trace in traces):
        raise ValueError('trace seed accounting mismatch')
    configs = [json.loads(p.with_suffix('.config.json').read_text())['env'] for p in (control_path, treatment_path)]
    def common(config):
        return {k: v for k, v in config.items() if not k.startswith('STS_OOC_MCTS')}
    if common(configs[0]) != common(configs[1]) or configs[0]['STS_OOC_MCTS'] != '0' or configs[1]['STS_OOC_MCTS'] != '1':
        raise ValueError('arm configuration mismatch')
    required_silver = {'STS_SILVER_SEARCH': '1', 'STS_SILVER_EXACT_ROOT_BUDGETS': '1',
                       'STS_SILVER_REUSE_CAP_MODE': 'allocated', 'STS_SILVER_ADAPTIVE': '0',
                       'STS_SILVER_VNET_LEAF_DIRECT': '0', 'STS_SILVER_TELEMETRY': '1'}
    if any(config.get(key) != value for config in configs for key, value in required_silver.items()):
        raise ValueError('frozen Silver configuration mismatch')
    if configs[1].get('STS_OOC_MCTS_SIMS') != '128':
        raise ValueError('frozen treatment MCTS budget mismatch')
    metas = [json.loads(Path(str(p) + '.meta.json').read_text()) for p in (control_path, treatment_path)]
    if metas[0]['config']['executableGitSha'] != metas[1]['config']['executableGitSha']:
        raise ValueError('arm executable SHA mismatch')
    for meta in metas:
        if meta['sims'] != 1000 or meta['asc'] != 0 or meta['config']['searcher3'] or not meta['config']['silverSearchEnabled'] or meta['config']['effectiveCombatBackend'] != 'silver' or not meta['config']['silverExactRootBudgets'] or not meta['config']['fairPlay']:
            raise ValueError('actual combat configuration mismatch')
    for off, on in zip((traces[0][s] for s in seeds), (traces[1][s] for s in seeds)):
        for row, enabled in ((off, False), (on, True)):
            decisions, owned, fallback, simulations = [int(row[k]) for k in ('oocDecisions', 'mctsOwned', 'mctsFallback', 'simulations')]
            if (enabled and decisions != owned + fallback) or (not enabled and owned + fallback + simulations != 0):
                raise ValueError('ownership trace does not reconcile')
            if simulations != owned * 128 or int(row['combatSurrogateSamples']) > int(row['transitionSamples']) or not 0 <= int(row['maxDepth']) <= 32 or int(row['realCombats']) <= 0:
                raise ValueError('search/real-combat trace does not reconcile')
    if not sum(int(row['mctsOwned']) for row in traces[1].values()) or not sum(int(row['combatSurrogateSamples']) for row in traces[1].values()):
        raise ValueError('treatment arm had no ownership or imagined combat samples')
    rng = np.random.Generator(np.random.PCG64(20260914))
    indices = rng.integers(0, 32, size=(bootstrap_samples, 32))
    differences = {}
    for key in ('won', 'floor', 'hpEnd', 'fightsLost', 'deathCombat', 'sec'):
        a, b = (np.array([float(arm[s][key]) for s in seeds]) for arm in (control, treatment))
        delta = b - a
        ci = np.quantile(delta[indices].mean(axis=1), [.025, .975], method='linear')
        differences[key] = {'control_mean': float(a.mean()), 'treatment_mean': float(b.mean()), 'treatment_minus_control': float(delta.mean()), 'paired_bootstrap_95_ci': ci.tolist()}
    control_wins = sum(int(control[s]['won']) for s in seeds)
    treatment_wins = sum(int(treatment[s]['won']) for s in seeds)
    treatment_only = sum(int(treatment[s]['won']) == 1 and int(control[s]['won']) == 0 for s in seeds)
    control_only = sum(int(control[s]['won']) == 1 and int(treatment[s]['won']) == 0 for s in seeds)
    lo, hi = differences['won']['paired_bootstrap_95_ci']
    classification = 'OOC_MCTS_WINRATE_UP' if lo > 0 else 'OOC_MCTS_WINRATE_DOWN' if hi < 0 else 'OOC_MCTS_WINRATE_INCONCLUSIVE'
    trace = traces[1]
    totals = {k: sum(float(trace[s][k]) for s in seeds) for k in trace[seeds[0]] if k not in ('seed', 'maxDepth')}
    runtime_total = sum(float(treatment[s]['sec']) for s in seeds)
    diagnostics = {f'mean_{k}_per_run': v / 32 for k, v in totals.items()}
    diagnostics.update(fallback_rate=totals['mctsFallback'] / totals['oocDecisions'], max_depth_distribution=dict(sorted(Counter(int(trace[s]['maxDepth']) for s in seeds).items())), mcts_fraction_of_total_run_wall_time=totals['mctsWallSec'] / runtime_total)
    both_dead = [s for s in seeds if int(control[s]['deathCombat']) >= 0 and int(treatment[s]['deathCombat']) >= 0]
    return {'classification': classification, 'seeds': seeds, 'benchmark_sha': metas[0]['config']['executableGitSha'], 'control_wins': control_wins, 'treatment_wins': treatment_wins, 'treatment_only_wins': treatment_only, 'control_only_wins': control_only, 'same_result_seeds': 32 - treatment_only - control_only, 'win_difference_pp': differences['won']['treatment_minus_control'] * 100, 'win_difference_95_ci_pp': [lo * 100, hi * 100], 'exact_two_sided_discordant_binomial_p': discordant_pvalue(treatment_only, control_only), 'paired_outcomes': differences, 'runtime_ratio_of_mean_per_run_seconds': differences['sec']['treatment_mean'] / differences['sec']['control_mean'], 'diagnostics': diagnostics, 'both_dead_seeds': both_dead, 'deathCombat_note': 'Raw paired mean includes -1 survivor sentinel; also identify both-dead seeds for conditional comparison.', 'bootstrap': {'replicates': bootstrap_samples, 'rng': 'NumPy PCG64', 'seed': 20260914, 'interval': 'paired seed percentile 2.5/97.5 quantiles, linear interpolation'}, 'configurations': configs, 'input_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (control_path, treatment_path)}, 'known_limitation': 'Copied hidden noncombat RNG can bias imagined futures. Actual gameplay uses real combat in both arms; this engineering policy A/B does not qualify unbiased MCTS values or deployment.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('control', type=Path)
    parser.add_argument('treatment', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    assert discordant_pvalue(0, 0) == 1 and discordant_pvalue(1, 1) == 1 and discordant_pvalue(4, 0) == .125
    result = analyze(args.control, args.treatment)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
