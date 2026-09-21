#!/usr/bin/env python3
"""Summarize frozen hard64-dev Silver reroot diagnostic JSONL archives."""
import gzip
import json
import statistics
import sys
from pathlib import Path


def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if len(rows) != 64 or len({row['case_id'] for row in rows}) != 64:
        raise ValueError(f'{path}: expected 64 distinct cases')
    return rows


def summarize(rows):
    records = [d for row in rows for d in row['reroot_diagnostics']]
    attempts = [d for d in records if d['fallback'] != 'no_predecessor']
    deterministic = [d for d in attempts if not d['stochastic']]
    stochastic = [d for d in attempts if d['stochastic']]
    cap = {'allocated_cap', 'active_cap'}
    return {
        'cases': len(rows),
        'statuses': {status: sum(row['status'] == status for row in rows)
                     for status in sorted({row['status'] for row in rows})},
        'wins': sum(row['won'] for row in rows),
        'mean_terminal_hp_fraction': statistics.mean(row['hp_end'] / row['max_hp'] for row in rows),
        'nodes_per_simulation': sum(row['nodes_created'] for row in rows)
                                / sum(row['simulations'] for row in rows),
        'exact_reroots': sum(row['reroot_exact'] for row in rows),
        'cap_fallbacks': sum(d['fallback'] in cap for d in attempts),
        'deterministic_attempts': len(deterministic),
        'deterministic_exact_or_equivalent': sum(d['exact'] or d['equivalent_copy']
                                                 for d in deterministic),
        'deterministic_cap_blocked': sum(d['fallback'] in cap for d in deterministic),
        'deterministic_candidate_missing': sum(d['fallback'] == 'candidate_missing'
                                               for d in deterministic),
        'stochastic_attempts': len(stochastic),
        'stochastic_candidate_missing': sum(d['fallback'] == 'candidate_missing'
                                            for d in stochastic),
        'initial_roots': len(rows),
        'initial_no_predecessor_records': sum(d['fallback'] == 'no_predecessor'
                                               for d in records),
        'selected_edge_without_child': sum(d['without_child'] for d in attempts),
        'deterministic_hand_order_mismatch': sum(d['hand_order_mismatch'] for d in deterministic),
        'deterministic_uid_copy_match': sum(d['uid_copy_match'] for d in deterministic),
        'deterministic_other_mismatch': sum(d['other_mismatch'] and not d['uid_copy_match']
                                            for d in deterministic),
        'mean_inherited_visits_per_attempt': statistics.mean(d['inherited_visits']
                                                              for d in attempts),
    }


def main():
    directory = Path(__file__).resolve().parent
    before = load(directory / 'baseline-diagnostic.jsonl.gz')
    after = load(directory / 'corrected-diagnostic.jsonl.gz')
    baseline = load(directory / 'baseline-uninstrumented.jsonl.gz')
    ids = [row['case_id'] for row in before]
    if ids != [row['case_id'] for row in after] or ids != [row['case_id'] for row in baseline]:
        raise ValueError('case order or identity changed')
    print(json.dumps({
        'before': summarize(before),
        'after': summarize(after),
        'trace_discordance': sum(a['action_trace_hash'] != b['action_trace_hash']
                                 for a, b in zip(before, after)),
        'uninstrumented_baseline_trace_discordance': sum(
            a['action_trace_hash'] != b['action_trace_hash'] for a, b in zip(baseline, before)),
    }, sort_keys=True, indent=2))


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('usage: python3 summarize.py')
    main()
