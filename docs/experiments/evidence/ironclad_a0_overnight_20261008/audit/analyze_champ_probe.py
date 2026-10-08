#!/usr/bin/env python3
"""Fixed public Champ contrast, with separate outcome-blind cost canary report."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
import run_champ_probe as run

sys.path.insert(0, str(run.ROOT))
from paired_analysis import bootstrap_ci


def nonnegative(value, name):
    run.require(isinstance(value, (float, int)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0, 'invalid ' + name)


def validate_branches(rows, k, spec):
    run.require(len(rows) == 2 and {r['arm'] for r in rows} == {'END', 'SHRUG'}, 'incomplete/duplicate arms')
    future = str(int(hashlib.sha256(f"{spec['future_domain']}:{run.ROW_SHA}:{k}".encode()).hexdigest()[:16], 16))
    for r in rows:
        run.require(r['kind'] == 'branch' and r['k'] == k and r['valid'] is True and not r.get('error'), 'invalid branch')
        run.require(type(r['combat_won']) is bool and r['environment_seed'] == future, 'win/future coupling')
        expected = spec['baseline_fingerprint'] if r['arm'] == 'END' else spec['alternative_fingerprint']
        run.require(r['forced_fingerprint'] == expected and r['action_fingerprints'][0] == expected,
                    'forced action mismatch')
        run.require(type(r['decisions']) is int and 1 <= r['decisions'] <= 1000
            and len(r['action_fingerprints']) == r['decisions'], 'decision/trace denominator')
        run.require(r['continuation_simulations'] == 10000 * (r['decisions'] - 1), 'exact continuation budget')
        e = r['search_endpoints']
        run.require(set(e) == {'victory', 'death', 'turn_limit', 'engine_stop', 'nonterminal'}
            and all(type(n) is int and n >= 0 for n in e.values()), 'search endpoint schema')
        run.require(sum(e.values()) == r['continuation_simulations']
            and e['turn_limit'] == e['engine_stop'] == e['nonterminal'] == 0, 'search health/denominator')
        run.require((r['combat_won'] and r['terminal_outcome'] == 1 and r['terminal_hp'] > 0)
            or (not r['combat_won'] and r['terminal_outcome'] == 2 and r['terminal_hp'] <= 0), 'actual terminal mismatch')
        run.require(type(r['terminal_turn']) is int and 1 <= r['terminal_turn'] <= 500
            and type(r['terminal_potion_count']) is int and 0 <= r['terminal_potion_count'] <= 5, 'terminal resources')
        run.require(len(r['endpoint_sha256']) == 64 and all(c in '0123456789abcdef' for c in r['endpoint_sha256']),
                    'endpoint hash')
        for name in ('cpu_seconds', 'wall_seconds'):
            nonnegative(r[name], name)


def invocation(f, freeze_sha, tools_sha, stage, k):
    p = run.prefix(stage, k)
    receipt_path = Path(str(p) + '.receipt.json')
    receipt = run.load(receipt_path)
    run.require(receipt['status'] == 'completed' and receipt['exit_code'] == 0, 'failed/incomplete invocation')
    run.require(receipt['stage'] == stage and receipt['k'] == k and receipt['freeze_sha256'] == freeze_sha
        and receipt['tools_sha256'] == tools_sha, 'invocation freeze/stage mismatch')
    run.require(run.sha(receipt['freeze']) == freeze_sha and run.sha(receipt['tools']) == tools_sha,
                'invocation manifest paths changed')
    run.require(receipt['source_sha'] == f['source_sha'] and receipt['binary_sha256'] == f['binary_sha256'], 'producer mismatch')
    run.require(receipt['script_sha256'] == run.sha(run.__file__) and receipt['command'] == run.command(f, stage, k)
        and receipt['environment'] == run.environment(f), 'launcher/command/environment mismatch')
    run.require(set(receipt['outputs']) == {'jsonl', 'stderr.log'}, 'missing/unexpected outputs')
    inputs = [{'path': str(receipt_path), 'sha256': run.sha(receipt_path)}]
    for suffix, record in receipt['outputs'].items():
        path = Path(str(p) + '.' + suffix)
        run.require(Path(record['path']) == path and path.stat().st_size == record['bytes']
            and run.sha(path) == record['sha256'], 'raw output changed')
        inputs.append({'path': str(path), 'sha256': record['sha256']})
    run.require(not Path(str(p) + '.stderr.log').read_text().strip(), 'nonempty diagnostic stderr')
    rows = [json.loads(line) for line in Path(str(p) + '.jsonl').read_text().splitlines()]
    run.require(len(rows) == (2 if stage == 'check' else 4), 'JSONL record coverage')
    h = rows[0]
    spec = run.load(f['specification'])
    run.require(h['kind'] == 'header' and h['schema'] == 'champ_d13_public_pair_result_v1' and h['mode'] == stage,
                'header schema/stage')
    run.require(h['source_sha'] == f['source_sha'] and h['binary_sha256'] == f['binary_sha256']
        and h['specification_sha256'] == run.SPEC_SHA and h['public_row_sha256'] == run.ROW_SHA, 'header identity')
    run.require(h['act'] == 2 and h['boss_context'] is True and h['models'] == []
        and h['maximum_decisions'] == 1000 and h['continuation_policy'] == 'fresh_exact_10000_public_seed_0', 'header policy/context')
    run.require(h['forced_fingerprints'] == [spec['baseline_fingerprint'], spec['alternative_fingerprint']], 'header contrast')
    if stage == 'check':
        run.require(rows[1]['kind'] == 'check' and rows[1]['status'] == 'PASS' and rows[1]['search_simulations'] == 0,
                    'one-step contract failed')
        branches = []
    else:
        validate_branches(rows[1:3], k, spec)
        run.require(rows[3] == {'kind': 'pair', 'k': k, 'valid': True, 'branches': 2}, 'pair footer mismatch')
        branches = rows[1:3]
    for name in ('wall_seconds', 'started_epoch', 'finished_epoch'):
        nonnegative(receipt[name], name)
    run.require(receipt['started_epoch'] <= receipt['finished_epoch'], 'negative invocation duration')
    if stage == 'evaluation':
        a = run.authorization(receipt['authorization'], receipt['authorization_sha256'], freeze_sha, tools_sha)
        run.require(receipt['started_epoch'] >= a['approved_epoch'], 'evaluation predates cost authorization')
        inputs.append({'path': receipt['authorization'], 'sha256': receipt['authorization_sha256']})
    return receipt, branches, inputs


def analyze(f, freeze_sha, tools_sha, stage):
    allocation = [0, 1] if stage == 'canary' else list(range(2, 64))
    inputs, failures, branches, walls, finished = [], [], [], [], []
    try:
        _, _, check_inputs = invocation(f, freeze_sha, tools_sha, 'check', None)
        inputs.extend(check_inputs)
    except Exception as error:
        failures.append({'stage': 'check', 'error': repr(error)})
    # Enumerate receipts and output attempts first, including failed and orphan files.
    expected_names = {run.prefix(stage, k).name + '.' + suffix for k in allocation
                      for suffix in ('receipt.json', 'jsonl', 'stderr.log')}
    actual_names = {p.name for p in run.RAW.glob(stage + '-*') if p.is_file()}
    if actual_names != expected_names:
        failures.append({'missing_files': sorted(expected_names - actual_names), 'extra_files': sorted(actual_names - expected_names)})
    for k in allocation:
        try:
            receipt, pair, pair_inputs = invocation(f, freeze_sha, tools_sha, stage, k)
            inputs.extend(pair_inputs); branches.extend(pair); walls.append(receipt['wall_seconds']); finished.append(receipt['finished_epoch'])
        except Exception as error:
            failures.append({'k': k, 'error': repr(error)})
    base = {'schema': 'champ_d13_analysis_v1', 'stage': stage, 'allocated_k': allocation,
        'build_freeze_sha256': freeze_sha, 'tools_freeze_sha256': tools_sha,
        'source_sha': f['source_sha'], 'binary_sha256': f['binary_sha256'], 'inputs': inputs,
        'independent_source_decisions': 1, 'failures': failures, 'analysis_script_sha256': run.sha(__file__)}
    if failures:
        return dict(base, status='INVALID_STOP_LANE', valid_branch_rows=len(branches))
    costs = {arm: sum(r['cpu_seconds'] for r in branches if r['arm'] == arm) for arm in ('END', 'SHRUG')}
    base.update(pairs=len(allocation), branches=len(branches), cpu_seconds_by_arm=costs,
        process_wall_seconds=sum(walls), latest_invocation_finished_epoch=max(finished),
        continuation_simulations=sum(r['continuation_simulations'] for r in branches),
        search_health={'turn_limit': 0, 'engine_stop': 0, 'nonterminal': 0})
    if stage == 'canary':
        return dict(base, status='CANARY_CONTRACT_PASS', outcome_summary_emitted=False,
            projected_evaluation_wall_seconds_one_worker=sum(walls) * 31,
            projection_note='Linear extrapolation from two pairs; coordinator must assess reserve and overhead.')
    indexed = {(r['k'], r['arm']): r for r in branches}
    delta = np.array([int(indexed[k, 'SHRUG']['combat_won']) - int(indexed[k, 'END']['combat_won']) for k in allocation])
    mean, low, high = bootstrap_ci(delta, n_boot=10000, ci=.95, rng=np.random.default_rng(20261008))
    base.update(status='EVALUATION_INTEGRITY_PASS', wins={arm: sum(indexed[k, arm]['combat_won'] for k in allocation)
        for arm in ('END', 'SHRUG')}, paired_gain=mean, paired_bootstrap_ci95=[low, high],
        shrug_only=int((delta > 0).sum()), end_only=int((delta < 0).sum()),
        both_win=sum(indexed[k, 'END']['combat_won'] and indexed[k, 'SHRUG']['combat_won'] for k in allocation),
        both_lose=sum(not indexed[k, 'END']['combat_won'] and not indexed[k, 'SHRUG']['combat_won'] for k in allocation),
        bootstrap_replicates=10000, bootstrap_seed=20261008,
        classification='LOCAL_CONDITIONAL_POSITIVE_SIGNAL' if low > 0 else 'LOCAL_CONDITIONAL_NEGATIVE_SIGNAL' if high < 0 else 'LOCAL_CONDITIONAL_INCONCLUSIVE',
        limitations=['One outcome-informed historical public root, not62 independent source decisions.',
            'Fresh exact10k per decision with fixed public search seed0; original retained learned-stop policy is unavailable.',
            'Conditional public-future sampling, not reconstruction of the historical hidden RNG.',
            'No Act3 population-strength or production-promotion claim; canaries excluded; no extension.'])
    return base


def main():
    ap = argparse.ArgumentParser()
    for field in ('freeze', 'tools'):
        ap.add_argument('--' + field, required=True, type=Path)
        ap.add_argument('--' + field + '-sha256', required=True)
    ap.add_argument('--stage', choices=('canary', 'evaluation'), required=True)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    run.require(not args.out.exists(), 'refusing prior analysis output')
    try:
        f, _, _ = run.custody(args.freeze, args.freeze_sha256, args.tools, args.tools_sha256)
        result = analyze(f, args.freeze_sha256, args.tools_sha256, args.stage)
        result['inputs'].extend({'path': str(p.resolve()), 'sha256': run.sha(p)} for p in (args.freeze, args.tools))
    except Exception as error:
        result = {'status': 'INVALID_STOP_LANE', 'error': repr(error), 'analysis_script_sha256': run.sha(__file__)}
    result['created_epoch'] = time.time()
    with args.out.open('x') as out:
        json.dump(result, out, indent=2); out.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'inputs'}, indent=2))
    return 0 if result['status'] in ('CANARY_CONTRACT_PASS', 'EVALUATION_INTEGRITY_PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
