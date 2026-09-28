#!/usr/bin/env python3
"""Summarize the narrow frozen-state last-Defend census; no policy inference."""
import argparse
from collections import Counter
import json
from pathlib import Path


def analyze(rows):
    if not rows or any(r['schema'] != 1 for r in rows):
        raise ValueError('empty or invalid trace')
    examples = []
    for row in rows:
        if not row['provably_useless']:
            continue
        if row['proof_scope'] != 'frozen_concrete_state_forced_end_turn' or not row['snapshot']:
            raise ValueError('missing frozen-state evidence')
        actions = row['root_actions']
        # Stable max preserves the first enumerated edge on ties, exactly as C++.
        winner = max(actions, key=lambda a: a['edge_visits'])
        if winner['action'] != row['chosen_action']:
            raise ValueError('chosen action does not match most-visits/first-tie rule')
        chosen = next(a for a in actions if a['action'] == row['chosen_action'])
        comparator = next(a for a in actions if a['action'] == row['comparator_action'])
        q = None if chosen['q'] is None or comparator['q'] is None else chosen['q'] - comparator['q']
        expected = ('missing_q' if q is None else 'near_equal_q' if abs(q) <= 1e-6
                    else 'higher_q_for_useless_action' if q > 0 else 'lower_q_but_selected')
        if row['classification'] != expected or row['q_difference'] != q:
            raise ValueError('Q classification mismatch')
        examples.append({k: v for k,v in row.items() if k != 'snapshot'})
    return {'decisions': len(rows), 'verified_selected': len(examples),
            'rate_per_real_decision': len(examples) / len(rows),
            'seeds': sorted({r['seed'] for r in rows}, key=int),
            'reasons': dict(Counter(r['reason'] for r in rows)),
            'classification': dict(Counter(r['classification'] for r in examples)),
            'examples': examples,
            'interpretation': 'Only last-card Defend with no potions, powers or unqualified relics. '
            'The comparator is immediate End Turn at the same frozen concrete state/RNG. '
            'This is not a public-state pruning rule or a frequency estimate for all wasted block. '
            'Q uses heuristic units; a 1e-6 near-equality threshold is descriptive, not statistical significance. '
            'Unused-energy scoring and loop-guard headroom differences are recorded separately.'}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=analyze([json.loads(line) for line in a.trace.read_text().splitlines() if line.strip()])
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='examples'},indent=2))
