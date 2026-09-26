#!/usr/bin/env python3
"""Validate and summarize STS_SILVER_TREE_PROFILE JSONL. No third-party modules."""
import argparse
from collections import Counter, defaultdict
import json
import gzip
import math
from pathlib import Path

KINDS = ('victory', 'death', 'turn_limit', 'engine_stop', 'nonterminal')


def natural(value):
    if type(value) is not int or value < 0:
        raise ValueError(f'expected nonnegative integer, got {value!r}')
    return value


def validate(row):
    if row['schema'] != 1 or row['error'] or row['descent_aborts']:
        raise ValueError('unsupported schema or incomplete/aborted search')
    completed = natural(row['completed_simulations'])
    if set(row['endpoints']) != set(KINDS):
        raise ValueError('endpoint classes do not match schema')
    total = 0
    for endpoint in row['endpoints'].values():
        count = natural(endpoint['count'])
        total += count
        for field in ('tree_depth', 'total_depth'):
            hist = endpoint[field]
            for depth, n in hist.items():
                if str(natural(int(depth))) != depth:
                    raise ValueError('invalid depth')
                natural(n)
            if sum(hist.values()) != count:
                raise ValueError('histogram count mismatch')
    if total != completed or row['heuristic_evaluations'] != completed or row['neural_evaluations'] != 0:
        raise ValueError('endpoint/evaluator denominator mismatch')
    if not 0 <= row['nonterminal_rollout_starts'] <= row['rollout_calls'] <= completed:
        raise ValueError('rollout denominator mismatch')
    if completed > natural(row['configured_simulations']):
        raise ValueError('completed exceeds configured budget')
    return row


def depths(hist):
    n = sum(hist.values())
    if not n:
        return {'count': 0, 'histogram': {}}
    ordered = sorted(hist.items())
    def quantile(q):
        target = math.ceil(q * n)
        seen = 0
        for depth, count in ordered:
            seen += count
            if seen >= target:
                return depth
    return {'count': n, 'histogram': dict(ordered), 'max': ordered[-1][0],
            'p50': quantile(.5), 'p90': quantile(.9), 'p99': quantile(.99)}


def summarize(rows):
    counts = Counter({kind: 0 for kind in KINDS})
    hists = defaultdict(Counter)
    for row in rows:
        for kind, endpoint in row['endpoints'].items():
            counts[kind] += endpoint['count']
            group = 'terminal' if kind in ('victory', 'death') else kind
            for field in ('tree_depth', 'total_depth'):
                hist = {int(k): v for k, v in endpoint[field].items()}
                hists['all_' + field].update(hist)
                hists[group + '_' + field].update(hist)
    n = sum(counts.values())
    return {'decisions': len(rows), 'simulations': n, 'counts': dict(counts),
            'shares': {k: v / n if n else None for k, v in counts.items()},
            'ordinary_terminal_share': (counts['victory'] + counts['death']) / n if n else None,
            'nonterminal_rollout_starts': sum(r['nonterminal_rollout_starts'] for r in rows),
            'depths': {k: depths(v) for k, v in sorted(hists.items())}}


def analyze(rows, minimum=20):
    groups = {
        'act': lambda r: r['act'], 'room': lambda r: r['room'],
        'encounter': lambda r: r['encounter'], 'turn': lambda r: r['turn'],
        'decision': lambda r: r['decision'],
        'hp_quarter': lambda r: min(3, int(4 * r['hp'] / max(1, r['max_hp']))),
        'enemy_hp_25': lambda r: int(r['enemy_hp'] // 25) * 25,
        'budget': lambda r: r['configured_simulations'],
    }
    by = {}
    for name, key in groups.items():
        grouped = defaultdict(list)
        for row in rows:
            grouped[str(key(row))].append(row)
        by[name] = {k: summarize(v) for k, v in sorted(grouped.items())}
    eligible = sorted(({'encounter': k, **v} for k, v in by['encounter'].items()
                       if v['decisions'] >= minimum and v['simulations']),
                      key=lambda v: (v['ordinary_terminal_share'], v['encounter']))
    # One complete fight per encounter; all decisions remain in the raw sidecar.
    examples = {}
    for row in rows:
        encounter = row['encounter']
        identity = (row['seed'], row['combat_id'], row['act'], row['floor'])
        if encounter not in examples:
            examples[encounter] = {'fight': identity, 'decisions': []}
        if examples[encounter]['fight'] == identity:
            examples[encounter]['decisions'].append({
                **{k: row[k] for k in ('decision', 'turn', 'hp', 'enemy_hp', 'nodes')},
                **summarize([row])})
    return {'overall': summarize(rows), 'by': by, 'minimum_decisions': minimum,
            'lowest_terminal_encounters': eligible[:5],
            'highest_terminal_encounters': list(reversed(eligible[-5:])),
            'fight_evolution': examples,
            'interpretation': 'Descriptive search samples, not independent outcomes or gameplay quality. '
            'Ordinary terminal = victory + death; engine/turn-limit stops stay separate. '
            'Total depth includes rollout actions; tree depth counts action edges only. '
            'Reused visits excluded. Empty-search shares are null.'}


def read_rows(path):
    rows = []
    seen = set()
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        lines = stream.readlines()
    for line, raw in enumerate(lines, 1):
        try:
            row = validate(json.loads(raw))
            key = tuple(row[k] for k in ('seed', 'combat_id', 'decision'))
            if key in seen:
                raise ValueError('duplicate decision (use a fresh sidecar for each run)')
            seen.add(key)
            rows.append(row)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f'{path}:{line}: {exc}') from exc
    if not rows:
        raise ValueError('empty profile')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile')
    parser.add_argument('--output', required=True)
    parser.add_argument('--minimum-decisions', type=int, default=20)
    args = parser.parse_args()
    result = analyze(read_rows(args.profile), args.minimum_decisions)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in result['overall'].items() if k != 'depths'}, indent=2))
