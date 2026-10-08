#!/usr/bin/env python3
"""Read existing outcome-informed discovery traces; never simulate a game."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
RAW = ROOT / 'build/overnight_20261008/wave1'
OUT = Path(__file__).with_name('SHOP_WORKED_CASE.json')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
canonical = lambda obj: json.dumps(obj, sort_keys=True, separators=(',', ':'))
objsha = lambda obj: hashlib.sha256(canonical(obj).encode()).hexdigest()


def load_trace(path, seed):
    return [(line, row) for line, raw in enumerate(path.open(), 1)
            if (row := json.loads(raw))['seed'] == seed]


def difference(seed):
    shard = (seed - 610081000) // 4
    traces, receipts, inputs = {}, {}, []
    for arm in ('Fprod', 'ShopFix'):
        prefix = RAW / f'{arm}_{shard}'
        receipt_path = Path(str(prefix) + '.receipt.json')
        receipt = json.loads(receipt_path.read_text())
        assert receipt['status'] == 'completed' and receipt['exit_code'] == 0
        receipts[arm] = receipt
        for suffix, key in (('trace.jsonl', 'trace'), ('strategic.jsonl', 'strategic'), ('tree.jsonl', 'tree'), ('csv', 'csv')):
            path = Path(str(prefix) + '.' + suffix)
            assert sha(path) == receipt['outputs'][key]['sha256']
            inputs.append({'arm': arm, 'kind': key, 'path': str(path), 'sha256': sha(path)})
        inputs.append({'arm': arm, 'kind': 'receipt', 'path': str(receipt_path), 'sha256': sha(receipt_path)})
        traces[arm] = load_trace(Path(str(prefix) + '.trace.jsonl'), seed)
    a, b = receipts['Fprod'], receipts['ShopFix']
    assert a['source_sha'] == b['source_sha'] and a['binary_sha256'] == b['binary_sha256']
    diagnostic = {'STS_OOC_DECISION_TRACE', 'STS_OOC_STRATEGIC_TRACE', 'STS_RUN_PROFILE',
                  'STS_SILVER_TREE_PROFILE', 'STS_SILVER_USELESS_TRACE'}
    envdiff = {k: [a['environment'].get(k), b['environment'].get(k)]
               for k in set(a['environment']) | set(b['environment'])
               if k not in diagnostic and a['environment'].get(k) != b['environment'].get(k)}
    assert envdiff == {'STS_OOC_SHOP_DECK_SIZE_FIX': ['0', '1']}
    n = next(i for i, (x, y) in enumerate(zip(traces['Fprod'], traces['ShopFix'])) if x[1] != y[1])
    left, right = traces['Fprod'][n], traces['ShopFix'][n]
    assert left[1]['pre'] == right[1]['pre'] and left[1]['offer'] == right[1]['offer']
    assert {k for k in left[1] if left[1][k] != right[1].get(k)} == {'post'}
    floor, act = left[1]['pre']['floor'], left[1]['pre']['act']
    strategic = {}
    for arm in ('Fprod', 'ShopFix'):
        path = RAW / f'{arm}_{shard}.strategic.jsonl'
        candidates = [(i, r) for i, r in enumerate(csv.DictReader(path.open()), 2)
                      if int(r['seed']) == seed and int(r['floor']) == floor and r['screen'] == '8']
        i, r = candidates[0]
        strategic[arm] = {'line': i, 'record': {k: v for k, v in r.items()
                             if k not in ('won', 'finalFloor', 'finalHp')}}
    assert strategic['Fprod']['record'] == strategic['ShopFix']['record']
    assert strategic['Fprod']['record']['owned'] == '0'
    chain = {}
    for arm in ('Fprod', 'ShopFix'):
        chain[arm] = [{'line': i, 'record': r} for i, r in traces[arm][n:]
                      if r['pre']['floor'] == floor and r['pre']['screen'] in ('SHOP', 'CARD_SELECT')]
    prior_trees = {}
    for arm in ('Fprod', 'ShopFix'):
        path = RAW / f'{arm}_{shard}.tree.jsonl'
        prior_trees[arm] = [{k: v for k, v in row.items() if k != 'combat_id'}
                           for raw in path.open() if int((row := json.loads(raw))['seed']) == seed
                           and row['floor'] < floor]
    assert prior_trees['Fprod'] == prior_trees['ShopFix']
    outcomes = {}
    for arm in ('Fprod', 'ShopFix'):
        path = RAW / f'{arm}_{shard}.csv'
        outcomes[arm] = next(r for r in csv.DictReader(path.open()) if int(r['seed']) == seed)
    root = left[1]['pre']
    return {
        'seed': seed, 'act': act, 'floor': floor, 'trace_idx': left[1]['idx'],
        'producer_source': a['source_sha'], 'binary_sha256': a['binary_sha256'],
        'policy_environment_difference': envdiff, 'inputs': inputs,
        'identical_trace_prefix_rows': n,
        'identical_trace_prefix_sha256': objsha([r for _, r in traces['Fprod'][:n]]),
        'prior_shop_roots': sum(r['pre']['screen'] == 'SHOP' for _, r in traces['Fprod'][:n]),
        'identical_prior_combat_profile_rows': len(prior_trees['Fprod']),
        'combat_profile_comparison_excludes': ['combat_id (process-global diagnostic counter)'],
        'first_difference': {'Fprod_line': left[0], 'ShopFix_line': right[0], 'changed_fields': ['post']},
        'serialized_public_pre': root, 'serialized_public_pre_sha256': objsha(root),
        'shop_offer': left[1]['offer'], 'shop_offer_sha256': objsha(left[1]['offer']),
        'strategic_root': strategic, 'shop_chain': chain, 'outcomes': outcomes,
        'all_relics_unaffordable': all(price > root['gold'] for _, price in left[1]['offer']['relics']),
        'minimum_relic_price': min(price for _, price in left[1]['offer']['relics']),
        'limitations': ['Trace public state omits counters, bottle/misc metadata and complete map.',
                       'Native bundle identities beyond their first token and native value scores are unlogged.',
                       'This is an outcome-selected forensic case, not independent policy qualification.']
    }


def main():
    if OUT.exists():
        raise RuntimeError('refusing overwrite')
    report = {'schema': 'overnight_shop_worked_case_v1', 'analysis_script_sha256': sha(__file__),
              'primary': difference(610081023), 'secondary': difference(610081002),
              'source_runs_executed': 0, 'interpretation': 'Feature repair changes an actual first-shop ranking; final win causality is not isolated.'}
    report['primary']['deck_size_frontier'] = [
        {'candidate': 'remove only', 'legacy': 13, 'corrected': 12, 'true': 12, 'gold_after': 61},
        {'candidate': 'Wild Strike only', 'legacy': 14, 'corrected': 14, 'true': 14, 'gold_after': 85},
        {'candidate': 'Wild Strike plus remove', 'legacy': 14, 'corrected': 13, 'true': 13, 'gold_after': 10}]
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(OUT), 'sha256': sha(OUT),
                      'primary_seed': report['primary']['seed'],
                      'equal_prefix_rows': report['primary']['identical_trace_prefix_rows'],
                      'equal_prior_combat_roots': report['primary']['identical_prior_combat_profile_rows'],
                      'source_runs_executed': 0}, indent=2))


if __name__ == '__main__':
    main()
