#!/usr/bin/env python3
"""Supplement a hash-bound COMPLETE full-run report; never compute efficacy."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

KINDS = ('victory', 'death', 'turn_limit', 'engine_stop', 'nonterminal')
CHECKPOINTS = {250, 500, 1000, 2000, 4000, 8000, 10000}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def natural(value):
    require(type(value) is int and value >= 0, 'expected nonnegative integer')
    return value


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key: ' + key)
        out[key] = value
    return out


def parse(text):
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + x)))


def read(path):
    result = parse(Path(path).read_text())
    require(isinstance(result, dict), 'artifact must be a JSON object')
    return result


def profile_counts(row, learned, exact):
    """Conservation mirrors SilverTreeProfile::record, not inherited visits."""
    require(isinstance(row, dict), 'profile must be object')
    require(type(row['schema']) is int and row['schema'] == 1, 'unknown profile schema')
    require(isinstance(row['error'], str), 'error must be string')
    for key in ('adaptive', 'singleton_skip'):
        require(type(row[key]) is bool, 'budget flag must be explicit bool')
    require(not row['adaptive'], 'campaign profile must not be adaptive')
    fields = ('completed_simulations', 'configured_simulations', 'heuristic_evaluations',
              'neural_evaluations', 'rollout_calls', 'cycle_rollouts',
              'nonterminal_rollout_starts', 'descent_aborts', 'root_actions', 'inherited_visits')
    for field in fields:
        natural(row[field])
    completed = row['completed_simulations']
    require(isinstance(row['endpoints'], dict), 'endpoints must be object')
    require(set(row['endpoints']) == set(KINDS), 'endpoint classes mismatch')
    counts = {}
    for kind, endpoint in row['endpoints'].items():
        require(isinstance(endpoint, dict), 'endpoint must be object')
        count = natural(endpoint['count'])
        for field in ('tree_depth', 'total_depth'):
            histogram = endpoint[field]
            require(isinstance(histogram, dict), 'depth histogram must be object')
            for depth, number in histogram.items():
                require(re.fullmatch(r'0|[1-9][0-9]*', depth) is not None, 'invalid depth key')
                natural(number)
            require(sum(histogram.values()) == count, 'histogram count mismatch')
        require(sum(int(k)*v for k,v in endpoint['total_depth'].items()) >=
                sum(int(k)*v for k,v in endpoint['tree_depth'].items()), 'total depth below tree depth')
        counts[kind] = count
    require(sum(counts.values()) == completed, 'endpoint denominator mismatch')
    require(row['heuristic_evaluations'] == completed and row['neural_evaluations'] == 0,
            'evaluator denominator mismatch')
    require(row['nonterminal_rollout_starts'] <= row['rollout_calls'] and
            row['cycle_rollouts'] <= row['rollout_calls'], 'rollout counter mismatch')
    # A caught exception may start a rollout without recording its endpoint.
    # Its error/abort is fatal below; do not pretend its partial budget is complete.
    if not row['error'] and not row['descent_aborts']:
        require(row['rollout_calls'] <= completed, 'completed rollout denominator mismatch')
        require(row['configured_simulations'] == 10000, 'unsupported configured campaign budget')
        if row['singleton_skip']:
            require(not exact and row['root_actions'] == 1 and completed == 0,
                    'invalid singleton skip')
        else:
            require(completed in CHECKPOINTS if learned else completed == 10000,
                    'completed budget incompatible with effective mode')
    return counts


def empty_summary():
    return {'roots': 0, 'completed_simulations': 0, 'singleton_skips': 0,
            'error_strings': {}, 'descent_aborts': 0, 'cycle_rollouts': 0,
            'rollout_calls': 0, 'nonterminal_rollout_starts': 0,
            'endpoints': {kind: 0 for kind in KINDS}}


def add(summary, row, counts):
    summary['roots'] += 1
    for field in ('completed_simulations', 'descent_aborts', 'cycle_rollouts',
                  'rollout_calls', 'nonterminal_rollout_starts'):
        summary[field] += row[field]
    summary['singleton_skips'] += int(row['singleton_skip'])
    if row['error']:
        summary['error_strings'][row['error']] = summary['error_strings'].get(row['error'], 0) + 1
    for kind in KINDS:
        summary['endpoints'][kind] += counts[kind]


def audit(report_path, report_sha):
    report_path = Path(report_path).resolve()
    require(sha(report_path) == report_sha, 'completed report hash mismatch')
    report = read(report_path)
    require(report.get('all_pairs_complete') is True and report.get('arms'), 'report is not COMPLETE')
    inputs = {}
    for item in report['inputs']:
        path = str(Path(item['path']).resolve())
        require(path not in inputs, 'duplicate report input')
        require(sha(path) == item['sha256'], 'bound input hash changed: ' + path)
        inputs[path] = item
    receipts = [Path(p) for p,x in inputs.items() if x['kind'] == 'receipt']
    require(receipts, 'no completed invocation receipts')
    manifests = {str(Path(read(p)['manifest']).resolve()) for p in receipts}
    require(len(manifests) == 1, 'multiple manifests')
    manifest_path = Path(next(iter(manifests)))
    require(sha(manifest_path) == report['manifest_sha256'], 'manifest hash changed')
    manifest = read(manifest_path)
    require(manifest['source_sha'] == report['source_sha'] and
            manifest['binary_sha256'] == report['binary_sha256'], 'report/manifest producer mismatch')
    expected = manifest['analysis_seeds']
    require(expected and all(type(s) is int and s >= 0 for s in expected) and len(set(expected)) == len(expected),
            'invalid allocated source list')
    expected = set(expected)
    require(set(manifest['analysis_arms']) == set(report['arms']), 'analysis arm coverage mismatch')
    arms = {arm: empty_summary() for arm in report['arms']}
    seed_summaries = {arm: {} for arm in arms}
    errors, diagnostic_limits, shards = [], [], []
    used_trees, used_csvs = set(), set()
    for rp in sorted(receipts):
        receipt = read(rp); arm = receipt['arm']
        require(arm in arms and receipt['status'] == 'completed' and receipt['exit_code'] == 0,
                'unsuccessful/unknown invocation')
        require(receipt['manifest_sha256'] == report['manifest_sha256'] and
                receipt['source_sha'] == report['source_sha'] and receipt['binary_sha256'] == report['binary_sha256'],
                'receipt producer mismatch')
        env = receipt['environment']
        declared = dict(manifest['profiles']['common']); declared.update(manifest['profiles']['arms'][arm])
        require(all(env.get(k) == declared.get(k) for k in
                    ('STS_SILVER_ADAPTIVE', 'STS_SILVER_LEARNED_STOP', 'STS_SILVER_EXACT_ROOT_BUDGETS',
                     'STS_SILVER_LEARNED_STOP_BOSS_MAX', 'STS_SILVER_LEARNED_STOP_BOSS_FALLBACK')),
                'receipt budget mode differs from manifest')
        require(env.get('STS_SILVER_ADAPTIVE') == '0' and env.get('STS_SILVER_LEARNED_STOP') in ('0','1') and
                env.get('STS_SILVER_EXACT_ROOT_BUDGETS') in ('0','1'), 'unsupported budget mode')
        require(env.get('STS_SILVER_LEARNED_STOP_BOSS_MAX', '0') == '0' and
                env.get('STS_SILVER_LEARNED_STOP_BOSS_FALLBACK', '0') == '0', 'unsupported boss extension')
        paths = {}
        prefix = str(rp)[:-len('.receipt.json')]
        for kind, suffix in [('csv', '.csv'), ('tree', '.tree.jsonl')]:
            item = receipt['outputs'][kind]; p = str(Path(item['path']).resolve())
            require(p == prefix + suffix and p in inputs and inputs[p]['kind'] == kind and
                    inputs[p]['sha256'] == item['sha256'] and Path(p).stat().st_size == item['bytes'],
                    'receipt/report output binding mismatch')
            paths[kind] = Path(p)
        require(str(paths['tree']) not in used_trees and str(paths['csv']) not in used_csvs, 'reused shard outputs')
        used_trees.add(str(paths['tree'])); used_csvs.add(str(paths['csv']))
        require(env.get('STS_SILVER_TREE_PROFILE') == str(paths['tree']), 'tree output not enabled/bound')
        # Only source identities are interpreted from gameplay CSV, never outcomes.
        with paths['csv'].open(newline='') as f:
            csv_seeds = [int(row['seed']) for row in csv.DictReader(f)]
        require(csv_seeds and len(set(csv_seeds)) == len(csv_seeds) and set(csv_seeds) <= expected,
                'CSV source allocation mismatch')
        require(not set(csv_seeds) & set(seed_summaries[arm]), 'duplicate arm/source shard')
        for seed in csv_seeds:
            seed_summaries[arm][seed] = empty_summary()
        seen = set(); observed = set(); row_count = 0
        with paths['tree'].open() as f:
            for line, raw in enumerate(f, 1):
                locator = str(paths['tree']) + ':' + str(line)
                try:
                    row = parse(raw)
                    require(isinstance(row, dict), 'profile must be object')
                    require(isinstance(row['seed'], str) and re.fullmatch(r'0|[1-9][0-9]*', row['seed']),
                            'noncanonical source seed')
                    seed = int(row['seed']); require(seed in csv_seeds, 'tree source outside invocation')
                    identity = (seed, natural(row['combat_id']), natural(row['decision']))
                    require(identity not in seen, 'duplicate real decision')
                    seen.add(identity); observed.add(seed)
                    counts = profile_counts(row, env['STS_SILVER_LEARNED_STOP'] == '1',
                                            env['STS_SILVER_EXACT_ROOT_BUDGETS'] == '1')
                    add(arms[arm], row, counts); add(seed_summaries[arm][seed], row, counts); row_count += 1
                    if row['error'] or row['descent_aborts'] or counts['nonterminal']:
                        errors.append({'locator': locator, 'seed': seed, 'arm': arm, 'error': row['error'],
                                       'descent_aborts': row['descent_aborts'], 'nonterminal_endpoints': counts['nonterminal']})
                    if counts['engine_stop'] or counts['turn_limit']:
                        diagnostic_limits.append({'locator': locator, 'seed': seed, 'arm': arm,
                                                  'engine_stop': counts['engine_stop'], 'turn_limit': counts['turn_limit']})
                except (ValueError, KeyError, TypeError) as exc:
                    errors.append({'locator': locator, 'arm': arm, 'malformed_profile': str(exc)})
        if observed != set(csv_seeds):
            errors.append({'path': str(paths['tree']), 'arm': arm, 'missing_tree_sources': sorted(set(csv_seeds)-observed)})
        shards.append({'receipt': str(rp), 'tree': str(paths['tree']), 'seeds': csv_seeds, 'valid_rows': row_count})
    require(used_trees == {p for p,x in inputs.items() if x['kind'] == 'tree'}, 'orphan/missing report tree')
    require(used_csvs == {p for p,x in inputs.items() if x['kind'] == 'csv'}, 'orphan/missing report CSV')
    for arm in arms:
        require(set(seed_summaries[arm]) == expected and report['arms'][arm]['n'] == len(expected), 'arm source coverage')
    return {'schema': 'supplementary_fullrun_health_v1',
            'status': 'INVALID_RUNTIME_HEALTH' if errors else 'PASS_WITH_DIAGNOSTIC_LIMITS' if diagnostic_limits else 'PASS',
            'report': str(report_path), 'report_sha256': report_sha, 'manifest': str(manifest_path),
            'manifest_sha256': report['manifest_sha256'], 'source_sha': report['source_sha'],
            'binary_sha256': report['binary_sha256'], 'phase': report['phase'],
            'auditor_sha256': sha(__file__), 'input_hashes_rechecked': len(inputs), 'inputs': list(inputs.values()),
            'arms': arms, 'per_arm_seed': seed_summaries, 'shards': shards,
            'fatal_contract_findings': errors, 'diagnostic_safety_limits': diagnostic_limits,
            'interpretation': {'denominator': 'newly completed search simulations; inherited visits excluded',
                'cycle_rollouts': 'expected on-path transposition fallback; counts alone are not failures',
                'engine_stop': 'positive-HP simulator loss, including no-damage and loop-guard stops; not a sampled death',
                'turn_limit': 'simulator loss beyond turn500; classified before HP death',
                'nonterminal': 'unresolved search endpoint, invalid runtime-health evidence',
                'limits': 'Tree counters alone do not distinguish engine-stop causes or establish live-game health, fairness, calibrated win probability or efficacy. No quality threshold or frozen decision rule is changed.'}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('report', type=Path); p.add_argument('--report-sha256', required=True)
    p.add_argument('--out', type=Path, required=True); a = p.parse_args()
    require(not a.out.exists(), 'refusing overwrite')
    try:
        result = audit(a.report, a.report_sha256)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        result = {'status': 'INVALID_INPUT_CONTRACT', 'report': str(a.report),
                  'report_sha256': a.report_sha256, 'error': str(exc), 'auditor_sha256': sha(__file__)}
    with a.out.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps({'status': result['status'], 'output': str(a.out), 'sha256': sha(a.out),
                      'arms': result.get('arms'), 'fatal_findings': len(result.get('fatal_contract_findings', []))}, indent=2))
    return int(result['status'].startswith('INVALID'))


if __name__ == '__main__':
    raise SystemExit(main())
