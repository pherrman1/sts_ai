#!/usr/bin/env python3
"""Read-only GEN=2 canary verifier; emits no evaluation-future outcomes."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def table(p):
    with Path(p).open(newline='') as f:
        return list(csv.DictReader(f))


def rowkey(row):
    return (int(row['sourceSeed']), int(row['decisionIdx']), row['type'],
            int(row['optionIdx']), int(row.get('k', 0)))


def public_count(policy):
    found = []
    def visit(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ('public_futures', 'ooc_public_futures', 'native_ooc_public_futures'):
                    found.append(v)
                visit(v)
        elif isinstance(obj, list):
            for v in obj:
                visit(v)
    visit(policy)
    return found


def verify_optional_recall_contract(freeze, teacher):
    """Old unlaunched freezes stay readable; corrected freezes bind the repair."""
    frozen_env = freeze.get('environment')
    env = teacher['environment']
    if frozen_env is not None:
        require(env == frozen_env, 'teacher/freeze effective environment mismatch')
    required = bool(frozen_env and frozen_env.get('STS_OOC_SKIP_OPTIONAL_RECALL') == '1')
    require(env.get('STS_OOC_SKIP_OPTIONAL_RECALL', '0') != '1' or required,
            'Recall-enabled teacher lacks corrected freeze binding')
    if required:
        require(teacher['ooc_policy']['flags'].get('skip_optional_recall') is True,
                'corrected policy must serialize skip_optional_recall=true')
    return required


def verify(freeze, prefixes, freeze_path):
    expected = set(freeze['source_seeds'])
    require(len(expected) == len(freeze['source_seeds']), 'duplicate source allocation')
    require(sha(freeze['binary']) == freeze['binary_sha256'], 'frozen binary changed')
    for path, expected_hash in freeze['artifacts'].items():
        require(sha(Path(freeze['root']) / path) == expected_hash, 'frozen artifact changed: ' + path)
    require(not any(610083000 <= s <= 610083511 for s in expected), 'confirmation seeds forbidden')
    require(freeze['futures'] in (4, 8), 'reviewed split-future contracts require K4 or K8')
    teacher_path = Path(freeze['teacher'])
    require(sha(teacher_path) == freeze['teacher_sha256'], 'teacher hash')
    teacher = json.loads(teacher_path.read_text())
    require(teacher['git_sha'] == freeze['source_sha'], 'teacher source identity')
    require(teacher['executable_sha256'] == freeze['binary_sha256'], 'teacher binary identity')
    env = teacher['environment']
    recall_required = verify_optional_recall_contract(freeze, teacher)
    if 'policy' in freeze:
        policy_path = Path(freeze['policy'])
        require(sha(policy_path) == freeze['policy_sha256'], 'frozen native policy changed')
        require(json.loads(policy_path.read_text()) == teacher['ooc_policy'], 'native policy/teacher mismatch')
    require(freeze.get('future_start', 0) == 0, 'this canary verifier requires the preregistered k=0 start')
    required_env = {'STS_OOC_PUBLIC_FUTURES': '8', 'STS_STOP_AFTER_ACT': '3',
                    'STS_COLLECT_KEYS': '0', 'STS_FAIR': '1', 'STS_OOC_MCTS': '0',
                    'STS_SILVER_EXACT_ROOT_BUDGETS': '0', 'STS_SILVER_LEARNED_STOP': '1'}
    require(all(env.get(k) == v for k, v in required_env.items()), 'teacher effective environment')
    require(public_count(teacher['ooc_policy']) == [8], 'policy must serialize exactly one public_futures=8')
    require(teacher['ooc_policy']['parameters']['stop_after_act'] == 3, 'policy Act-3 cutoff')
    for model in teacher['model_artifacts']:
        require(sha(Path(freeze['root']) / model['path']) == model['sha256'], 'teacher model hash ' + model['role'])
    labels, options, sources, maps, coverage, inputs = [], [], [], [], set(), []
    wall_seconds, tree_rows, early_nontrivial_roots, singleton_skips = 0.0, 0, 0, 0
    for prefix in prefixes:
        prefix = prefix.resolve()
        receipt_path = Path(str(prefix) + '.receipt.json')
        receipt = json.loads(receipt_path.read_text())
        require(receipt['status'] == 'completed' and receipt['exit_code'] == 0, 'source subprocess incomplete/failed')
        require(receipt['source_sha'] == freeze['source_sha'] and receipt['binary_sha256'] == freeze['binary_sha256'], 'invocation producer mismatch')
        require(receipt['freeze_sha256'] == sha(freeze_path) and Path(receipt['freeze']).resolve() == freeze_path.resolve(), 'invocation freeze mismatch')
        seed = receipt['source_seed']
        require(seed in expected, 'unreserved invocation source')
        command = ['bash','tools/seed_guard.sh',freeze['binary'],'ooccfpilotgen','1',str(prefix),str(seed),
                   freeze['teacher'],str(freeze['futures']),str(freeze['states_per_seed']),'1','2',','.join(freeze['types'])]
        require(receipt['command'] == command, 'invocation command mismatch')
        expected_env = dict(env, STS_SILVER_TREE_PROFILE=str(prefix) + '.tree.jsonl')
        require(receipt['environment'] == expected_env, 'invocation environment mismatch')
        expected_outputs = {'labels.csv','options.csv','sources.csv','map.csv','manifest.json','log','tree.jsonl'}
        require(set(receipt['outputs']) == expected_outputs, 'invocation emitted output coverage')
        for suffix, record in receipt['outputs'].items():
            path = Path(str(prefix) + '.' + suffix)
            require(Path(record['path']).resolve() == path, 'invocation output path mismatch')
            require(path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], 'invocation output changed')
        log_path = Path(str(prefix) + '.log'); log = log_path.read_text()
        require('[native OOC public encounter mixture: 8 futures]' in log, 'missing public mixture banner')
        if recall_required:
            require('[native OOC optional Ruby Recall excluded when keys off and another action is legal]' in log,
                    'missing corrected optional Recall startup banner')
        require('[benchmark stops after Act 3 boss]' in log, 'missing Act3 banner')
        require('learned stop; one-action roots unsearched' in log, 'missing native learned-stop banner')
        require(math.isfinite(receipt['wall_seconds']) and receipt['wall_seconds'] >= 0, 'invalid invocation wall time')
        wall_seconds += receipt['wall_seconds']
        tree_path = Path(str(prefix) + '.tree.jsonl')
        local_tree_rows = 0
        with tree_path.open() as tree_file:
            for line in tree_file:
                root = json.loads(line)
                require(int(root['seed']) == seed and not root['adaptive'] and not root['error'], 'invalid root source/budget/error')
                require(root['configured_simulations'] >= 0 and root['completed_simulations'] >= 0, 'invalid root simulations')
                singleton_skips += int(root['singleton_skip'])
                early_nontrivial_roots += int(root['root_actions'] > 1 and 0 < root['completed_simulations'] < root['configured_simulations'])
                local_tree_rows += 1
        require(local_tree_rows > 0, 'missing runtime combat profile')
        tree_rows += local_tree_rows
        for path in (receipt_path, log_path, tree_path):
            inputs.append({'path': str(path), 'sha256': sha(path)})
        mp = Path(str(prefix) + '.manifest.json')
        manifest = json.loads(mp.read_text())
        require(manifest['schemaVersion'] == 'ooc_cf_pilot_v2', 'GEN2 required')
        require(manifest['producerGitSha'] == freeze['source_sha'], 'manifest source')
        require(manifest['producerExecutableSha256'] == freeze['binary_sha256'], 'manifest binary')
        require(manifest['teacherManifestSha256'] == freeze['teacher_sha256'], 'manifest teacher hash')
        require(manifest['teacherId'] == teacher['teacher_id'], 'manifest teacher id')
        require(manifest['combatTeacher'] == teacher, 'manifest complete teacher')
        require(manifest['policy'] == teacher['ooc_policy'], 'manifest policy')
        require(manifest['seedSpec']['ascension'] == 0, 'ascension')
        spec = manifest['seedSpec']
        require(spec['start'] == seed and spec['count'] == 1, 'manifest/invocation seed mismatch')
        seeds = set(range(spec['start'], spec['start'] + spec['count']))
        require(not coverage & seeds and seeds <= expected, 'duplicate/unreserved source seed')
        coverage |= seeds
        require(manifest['futures']['count'] == freeze['futures'], 'futures count')
        require(manifest['statesPerSeed'] == freeze['states_per_seed'], 'states per source')
        require(set(manifest['selection']['types']) == set(freeze['types']), 'screen scope')
        for name in ('quarantinedSeeds', 'fatalFailures', 'simulatorHealthFailures'):
            if name in manifest['integrity']:
                require(manifest['integrity'][name] == 0, 'nonzero ' + name)
        local = {}
        for suffix in ('labels.csv', 'options.csv', 'sources.csv', 'map.csv'):
            path = Path(str(prefix) + '.' + suffix)
            digest = sha(path)
            require(digest == manifest['outputs'][suffix], suffix + ' hash')
            local[suffix] = table(path)
            inputs.append({'path': str(path.resolve()), 'sha256': digest})
        require(len(local['labels.csv']) == manifest['integrity']['labelRows'], 'manifest label count')
        require(manifest['integrity']['labelRows'] == manifest['integrity']['validLabelRows'], 'invalid branch count')
        require(set(int(r['sourceSeed']) for r in local['sources.csv']) == seeds, 'source-table coverage')
        require(all(int(r['trajectoryValid']) == 1 for r in local['sources.csv']), 'source trajectory invalid')
        selected_sources = [r for r in local['sources.csv'] if int(r['decisionIdx']) >= 0]
        require(len(selected_sources) == manifest['integrity']['selectedStates'], 'selected state count')
        labels.extend(local['labels.csv']); options.extend(local['options.csv'])
        sources.extend(local['sources.csv']); maps.extend(local['map.csv'])
        inputs.append({'path': str(mp.resolve()), 'sha256': sha(mp)})
    require(coverage == expected, 'source coverage incomplete')
    source_states = {}
    for r in sources:
        if int(r['decisionIdx']) < 0:
            continue
        key = (int(r['sourceSeed']), int(r['decisionIdx']), r['type'])
        require(key not in source_states, 'duplicate source decision')
        source_states[key] = r
    require(all(n <= freeze['states_per_seed'] for n in Counter(s for s,d,t in source_states).values()), 'too many states')
    opt = defaultdict(list)
    for row in options:
        opt[rowkey(row)[:3]].append(row)
    require(set(opt) == set(source_states), 'option/source decision coverage')
    expected_labels = set()
    for key, rows in opt.items():
        require(key[2] in freeze['types'], 'wrong decision type')
        require(1 <= len(rows) <= 6 and len(rows) == int(source_states[key]['options']), 'option count')
        require(sum(int(r['chosen']) for r in rows) == 1, 'source chosen retention')
        canonical = [re.sub(r'occurrence=[0-9]+', 'occurrence=*', r['optionKey']) for r in rows]
        require(len(set(canonical)) == len(rows), 'duplicate semantic occurrence class')
        require(len({int(r['optionIdx']) for r in rows}) == len(rows), 'duplicate option index')
        for r in rows:
            for k in range(freeze['futures']):
                expected_labels.add((*key, int(r['optionIdx']), k))
    label_lookup = {}
    invalid_errors = Counter()
    for row in labels:
        key = rowkey(row)
        require(key not in label_lookup, 'duplicate label')
        label_lookup[key] = row
        require(row['finalWon'] in ('0', '1'), 'invalid terminal win label')
        if row['valid'] != '1' or row['error']:
            invalid_errors[row['error'] or 'invalid'] += 1
        require(math.isfinite(float(row['cpuSeconds'])) and float(row['cpuSeconds']) >= 0, 'invalid CPU')
        digest = hashlib.sha256(f'ooc-cf-pilot-v2-future:{key[0]}:{key[1]}:{key[4]}'.encode()).hexdigest()
        require(int(row['futureSeed']) == int(digest[:16], 16), 'future identity/coupling')
        option = next(r for r in opt[key[:3]] if int(r['optionIdx']) == key[3])
        require(row['optionKey'] == option['optionKey'] and row['chosen'] == option['chosen'], 'option identity mismatch')
    require(not invalid_errors, 'invalid branch errors: ' + str(dict(invalid_errors)))
    require(set(label_lookup) == expected_labels, 'missing/extra sibling futures')
    map_lookup = {}
    for row in maps:
        key = rowkey(row)
        require(key not in map_lookup, 'duplicate MAP row')
        map_lookup[key] = row
        label = label_lookup[key]
        require(row['optionKey'] == label['optionKey'] and row['chosen'] == label['chosen'], 'MAP action identity')
        require(row['mapAct'] == label['mapAct'] and row['mapFloor'] == label['mapFloor'], 'MAP boundary identity')
    require(set(map_lookup) == expected_labels, 'missing MAP row (terminal branches must not be dropped)')
    source_cpu = {}
    for r in sources:
        seed, cpu = int(r['sourceSeed']), float(r['sourceCpuSeconds'])
        require(math.isfinite(cpu) and cpu >= 0, 'invalid source CPU')
        require(seed not in source_cpu or source_cpu[seed] == cpu, 'inconsistent repeated source CPU')
        source_cpu[seed] = cpu
    return {'status': 'CONTRACT_RECEIPT_PASS', 'source_seeds': sorted(coverage),
            'states': len(source_states), 'states_by_type': dict(Counter(k[2] for k in source_states)),
            'states_by_type_act': dict(Counter(f'{k[2]}:A{r["act"]}' for k,r in source_states.items())),
            'label_rows': len(labels), 'source_cpu_seconds': sum(source_cpu.values()),
            'branch_cpu_seconds': sum(float(r['cpuSeconds']) for r in labels),
            'invocation_wall_seconds_sum': wall_seconds, 'native_tree_profile_rows': tree_rows,
            'native_early_nontrivial_roots': early_nontrivial_roots, 'native_singleton_skips': singleton_skips,
            'runtime_budget_limit': 'Profiles combine source and branches; teacher contract and source inspection bind both to learned stopping',
            'evaluation_outcomes_reported': False, 'source_trajectory_valid': True,
            'optional_recall_policy_bound_and_banner_checked': recall_required,
            'source_counter_limit': 'GEN2 has trajectoryValid but no explicit source fatal/quarantine counters; any present manifest counters checked zero',
            'coverage_limit': 'retained option set only; uncapped legal actions not serialized', 'inputs': inputs}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--freeze', type=Path, required=True)
    p.add_argument('--prefix', type=Path, action='append', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    require(not a.out.exists(), 'refusing overwrite')
    receipt = {'schema': 'overnight_gen2_receipt_v1', 'freeze': str(a.freeze.resolve()),
               'freeze_sha256': sha(a.freeze), 'verifier_sha256': sha(__file__)}
    try:
        receipt.update(verify(json.loads(a.freeze.read_text()), a.prefix, a.freeze))
    except (ValueError, KeyError, OSError, StopIteration) as exc:
        receipt.update(status='INVALID', error=str(exc), evaluation_outcomes_reported=False)
    with a.out.open('x') as out:
        out.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k:v for k,v in receipt.items() if k != 'inputs'}, indent=2))
    return 0 if receipt['status'] == 'CONTRACT_RECEIPT_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
