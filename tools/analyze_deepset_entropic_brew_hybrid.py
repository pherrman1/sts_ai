#!/usr/bin/env python3
"""Validate and summarize paired standard-vs-hybrid OOC MCTS evidence."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np


def keyed_csv(path):
    with path.open() as f:
        rows = list(csv.DictReader(f))
    keyed = {int(r['seed']): r for r in rows}
    if len(keyed) != len(rows):
        raise ValueError(f'duplicate seed in {path}')
    return keyed


def load_arm(path, seeds, expected_arm):
    results = keyed_csv(path / 'results.csv')
    traces = keyed_csv(path / 'mcts.csv')
    expected = set(seeds)
    if set(results) != expected or set(traces) != expected:
        raise ValueError(f'{expected_arm}: results/trace seeds do not exactly match paired block')
    meta = json.loads((path / 'results.csv.meta.json').read_text())
    config = json.loads((path / 'config.json').read_text())
    if config['arm'] != expected_arm or config['pinnedExperimentCommit'] != '9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351':
        raise ValueError(f'{expected_arm}: arm/source config mismatch')
    if meta['config']['executableGitSha'] != config['pinnedExperimentCommit']:
        raise ValueError(f'{expected_arm}: executable SHA differs from frozen reviewed commit')
    if (meta['nSeeds'], meta['sims'], meta['threads'], meta['asc']) != (len(seeds), 10000, 24, 0):
        raise ValueError(f'{expected_arm}: benchmark metadata mismatch')
    if config['environment'].get('STS_OOC_MCTS') != '1' or config['environment'].get('STS_OOC_MCTS_SIMS') != '2048':
        raise ValueError(f'{expected_arm}: OOC MCTS setting mismatch')
    for seed in seeds:
        row = traces[seed]
        decisions, owned, fallback = (int(row[k]) for k in ('oocDecisions', 'mctsOwned', 'mctsFallback'))
        if decisions != owned + fallback or int(row['simulations']) <= 0 or int(row['realCombats']) <= 0:
            raise ValueError(f'{expected_arm}: invalid per-seed OOC accounting at {seed}')
    reasons = [json.loads(line) for line in (path / 'mcts.csv.support.jsonl').read_text().splitlines() if line.strip()]
    if len(reasons) != len(seeds) or {int(r['seed']) for r in reasons} != expected:
        raise ValueError(f'{expected_arm}: support reason seed mismatch')
    for row in reasons:
        seed = int(row['seed'])
        unsupported = int(traces[seed]['unsupportedCombats'])
        if sum(row['reasons'].values()) != unsupported:
            raise ValueError(f'{expected_arm}: unsupported-combat reasons do not reconcile at {seed}')
    return results, traces, reasons, meta, config


def exact_discordant_p(a, b):
    n = a + b
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a, b) + 1)) / (2**n)
    return min(1.0, 2 * tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('control', type=Path)
    ap.add_argument('hybrid', type=Path)
    ap.add_argument('summary', type=Path)
    ap.add_argument('per_seed', type=Path)
    ap.add_argument('--seed-start', type=int, default=980000)
    ap.add_argument('--seed-count', type=int, default=64)
    ap.add_argument('--bootstrap', type=int, default=200000)
    args = ap.parse_args()
    seeds = list(range(args.seed_start, args.seed_start + args.seed_count))
    c = load_arm(args.control, seeds, 'control')
    h = load_arm(args.hybrid, seeds, 'hybrid')
    cr, ct, c_reasons, cm, cc = c
    hr, ht, h_reasons, hm, hc = h
    common_c = {k: v for k, v in cc['environment'].items()
                if k not in ('STS_OOC_MCTS_COMBAT_MODEL', 'STS_OOC_MCTS_BREW_FALLBACK_MODEL', 'STS_OOC_MCTS_TRACE')}
    common_h = {k: v for k, v in hc['environment'].items()
                if k not in ('STS_OOC_MCTS_COMBAT_MODEL', 'STS_OOC_MCTS_BREW_FALLBACK_MODEL', 'STS_OOC_MCTS_TRACE')}
    if common_c != common_h:
        raise ValueError('arms differ outside CTM model paths/trace output')
    if cm['config']['executableGitSha'] != hm['config']['executableGitSha']:
        raise ValueError('arm executable hashes differ')
    if any(int(ct[s][k]) for s in seeds for k in ('hybridPreparations', 'hybridFastPreparations', 'hybridFallbackPreparations')):
        raise ValueError('standard control unexpectedly contains hybrid counters')
    for s in seeds:
        t = ht[s]
        if int(t['hybridPreparations']) != int(t['hybridFastPreparations']) + int(t['hybridFallbackPreparations']):
            raise ValueError(f'hybrid preparation counters do not reconcile at {s}')

    metrics = {
        'win': lambda r, t: int(r['won']),
        'floor': lambda r, t: int(r['floor']),
        'act': lambda r, t: int(r['act']),
        'hpEnd': lambda r, t: int(r['hpEnd']),
        'maxHp': lambda r, t: int(r['maxHp']),
        'fightsLost': lambda r, t: int(r['fightsLost']),
        'wholeRunSeconds': lambda r, t: float(r['sec']),
        'oocDecisions': lambda r, t: int(t['oocDecisions']),
        'mctsOwned': lambda r, t: int(t['mctsOwned']),
        'mctsFallback': lambda r, t: int(t['mctsFallback']),
        'mctsSimulations': lambda r, t: int(t['simulations']),
        'realCombats': lambda r, t: int(t['realCombats']),
        'imaginedCombats': lambda r, t: int(t['imaginedCombats']),
        'unsupportedCombats': lambda r, t: int(t['unsupportedCombats']),
        'mctsSupportAborts': lambda r, t: int(t['mctsSupportAborts']),
        'mctsCpuSeconds': lambda r, t: float(t['mctsCpuSec']),
        'mctsWallSeconds': lambda r, t: float(t['mctsWallSec']),
        'ctmPreparations': lambda r, t: int(t['preparedCombats']),
        'combatEdgeSamples': lambda r, t: int(t['combatEdgeSamples']),
        'hybridPreparations': lambda r, t: int(t['hybridPreparations']),
        'hybridFastPreparations': lambda r, t: int(t['hybridFastPreparations']),
        'hybridFallbackPreparations': lambda r, t: int(t['hybridFallbackPreparations']),
        'hybridFastSamples': lambda r, t: int(t['hybridFastSamples']),
        'hybridFallbackSamples': lambda r, t: int(t['hybridFallbackSamples']),
        'hybridUniqueBrewStates': lambda r, t: int(t['hybridUniqueBrewStates']),
    }
    rng = np.random.Generator(np.random.PCG64(20260924))
    ix = rng.integers(0, len(seeds), size=(args.bootstrap, len(seeds)))
    paired = {}
    for name, get in metrics.items():
        a = np.array([get(cr[s], ct[s]) for s in seeds], dtype=float)
        b = np.array([get(hr[s], ht[s]) for s in seeds], dtype=float)
        delta = b - a
        ci = np.quantile(delta[ix].mean(axis=1), [.025, .975], method='linear')
        paired[name] = {'controlMean': float(a.mean()), 'hybridMean': float(b.mean()),
                        'hybridMinusControl': float(delta.mean()), 'pairedBootstrap95CI': [float(ci[0]), float(ci[1])]}
    c_wins = sum(int(cr[s]['won']) for s in seeds)
    h_wins = sum(int(hr[s]['won']) for s in seeds)
    h_only = sum(int(hr[s]['won']) == 1 and int(cr[s]['won']) == 0 for s in seeds)
    c_only = sum(int(cr[s]['won']) == 1 and int(hr[s]['won']) == 0 for s in seeds)
    support_counts = lambda rows: dict(sorted(Counter(k for row in rows for k, n in row['reasons'].items() for _ in range(int(n))).items()))
    hybrid_preps = sum(int(ht[s]['hybridPreparations']) for s in seeds)
    fallback_preps = sum(int(ht[s]['hybridFallbackPreparations']) for s in seeds)
    summary = {
        'classification': 'OOC_HYBRID_WINRATE_INCONCLUSIVE',
        'reviewedExecutableCommit': '9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351',
        'baselineCommit': '41c0f5af5711c452b6e133e6dc66c7756f50874c',
        'seedRange': [seeds[0], seeds[-1]], 'seedCount': len(seeds),
        'controlWins': c_wins, 'hybridWins': h_wins,
        'hybridOnlyWins': h_only, 'controlOnlyWins': c_only,
        'bothWinOrBothLose': len(seeds) - h_only - c_only,
        'winDifferencePercentagePoints': paired['win']['hybridMinusControl'] * 100,
        'winDifference95CIPercentagePoints': [v * 100 for v in paired['win']['pairedBootstrap95CI']],
        'exactTwoSidedDiscordantBinomialP': exact_discordant_p(h_only, c_only),
        'pairedMetrics': paired,
        'aggregateHybridFallbackRate': fallback_preps / hybrid_preps if hybrid_preps else 0,
        'aggregateHybridPreparations': hybrid_preps,
        'aggregateHybridFallbackPreparations': fallback_preps,
        'aggregateHybridFastSupportFailures': sum(int(ht[s]['hybridFastSupportFailures']) for s in seeds),
        'aggregateHybridFallbackSupportFailures': sum(int(ht[s]['hybridFallbackSupportFailures']) for s in seeds),
        'controlSupportReasons': support_counts(c_reasons),
        'hybridSupportReasons': support_counts(h_reasons),
        'configuration': {'combatSimulations': 10000, 'oocMctsSimulations': 2048,
                          'ascension': 0, 'threads': 24, 'fairPlay': True,
                          'silverSearch': True, 'seedBlock': [seeds[0], seeds[-1]]},
        'limits': ['64 seeds are an engineering screen, not default-promotion evidence.',
                   'Whole-run sec is bestbench elapsed time; total whole-process CPU was not recorded.',
                   'Hidden noncombat RNG copied into imagined futures can bias OOC estimates; conclusions are limited to this engineering setup.'],
        'bootstrap': {'replicates': args.bootstrap, 'rng': 'NumPy PCG64', 'seed': 20260924,
                      'interval': 'paired seed percentile 2.5/97.5 quantiles, linear interpolation'},
    }
    with args.per_seed.open('w', newline='') as f:
        fields = ['seed']
        fields += [f'control_{k}' for k in ('won', 'floor', 'act', 'hpEnd', 'maxHp', 'fightsLost', 'sec')]
        fields += [f'hybrid_{k}' for k in ('won', 'floor', 'act', 'hpEnd', 'maxHp', 'fightsLost', 'sec')]
        fields += [f'control_{k}' for k in ('oocDecisions', 'simulations', 'realCombats', 'imaginedCombats', 'unsupportedCombats', 'mctsSupportAborts', 'mctsCpuSec', 'mctsWallSec', 'preparedCombats')]
        fields += [f'hybrid_{k}' for k in ('oocDecisions', 'simulations', 'realCombats', 'imaginedCombats', 'unsupportedCombats', 'mctsSupportAborts', 'mctsCpuSec', 'mctsWallSec', 'preparedCombats', 'hybridPreparations', 'hybridFastPreparations', 'hybridFallbackPreparations', 'hybridFastSamples', 'hybridFallbackSamples', 'hybridFallbackRate', 'hybridUniqueBrewStates', 'hybridFastSupportFailures', 'hybridFallbackSupportFailures')]
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); w.writeheader()
        for s in seeds:
            row = {'seed': s}
            for arm, results, traces in (('control', cr, ct), ('hybrid', hr, ht)):
                for k in ('won', 'floor', 'act', 'hpEnd', 'maxHp', 'fightsLost', 'sec'):
                    row[f'{arm}_{k}'] = results[s][k]
                for k in ('oocDecisions', 'simulations', 'realCombats', 'imaginedCombats', 'unsupportedCombats', 'mctsSupportAborts', 'mctsCpuSec', 'mctsWallSec', 'preparedCombats'):
                    row[f'{arm}_{k}'] = traces[s][k]
                if arm == 'hybrid':
                    for k in ('hybridPreparations', 'hybridFastPreparations', 'hybridFallbackPreparations', 'hybridFastSamples', 'hybridFallbackSamples', 'hybridFallbackRate', 'hybridUniqueBrewStates', 'hybridFastSupportFailures', 'hybridFallbackSupportFailures'):
                        row[f'{arm}_{k}'] = traces[s][k]
            w.writerow(row)
    args.summary.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
