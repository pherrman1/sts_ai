#!/usr/bin/env python3
"""Strict paired campaign analysis using the repository bootstrap implementation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import paired_analysis as pa

SUFFIXES = {'csv': '.csv', 'meta': '.csv.meta.json', 'log': '.log',
            'trace': '.trace.jsonl', 'tree': '.tree.jsonl', 'profile': '.profile.jsonl',
            'strategic': '.strategic.jsonl', 'combat': '.combat.jsonl', 'public': '.public.jsonl'}
TRACE_ENV = {'STS_OOC_DECISION_TRACE': 'trace', 'STS_OOC_STRATEGIC_TRACE': 'strategic',
             'STS_RUN_PROFILE': 'profile', 'STS_SILVER_TREE_PROFILE': 'tree',
             'STS_SILVER_USELESS_TRACE': 'combat', 'STS_SILVER_PUBLIC_TRACE': 'public'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def unique(values, label):
    require(isinstance(values, list) and bool(values), label + ' must be a nonempty list')
    require(len(values) == len(set(values)), label + ' duplicates')
    return set(values)


def wilson95(wins, n):
    z = 1.959963984540054
    p = wins / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return [max(0.0, center-radius), min(1.0, center+radius)]


def validate_manifest(m):
    require(m.get('schema') == 1, 'manifest schema must be 1')
    require(m.get('phase') in ('smoke','discovery','development','confirmation'), 'unknown phase')
    require(re.fullmatch('[0-9a-f]{40}', m['source_sha']) is not None, 'invalid source SHA')
    require(re.fullmatch('[0-9a-f]{64}', m['binary_sha256']) is not None, 'invalid binary hash')
    expected = unique(m['analysis_seeds'], 'analysis_seeds')
    allowed = unique(m['allowed_seeds'], 'allowed_seeds')
    require(all(type(s) is int and s >= 0 for s in allowed | expected), 'invalid source seed')
    require(expected <= allowed, 'analysis seeds outside allocation')
    arms = unique(m['analysis_arms'], 'analysis_arms')
    require(all(isinstance(a, str) and re.fullmatch('[A-Za-z][A-Za-z0-9]*', a) for a in arms), 'invalid arm identifier')
    require(arms <= set(m['profiles']['arms']), 'unknown analysis arm')
    require(isinstance(m['comparisons'], list) and m['comparisons'], 'missing comparisons')
    pairs = []
    for pair in m['comparisons']:
        require(isinstance(pair, list) and len(pair) == 2, 'comparison must be [candidate,control]')
        require(pair[0] in arms and pair[1] in arms and pair[0] != pair[1], 'invalid comparison arms')
        pairs.append(tuple(pair))
    require(len(set(pairs)) == len(pairs), 'duplicate comparison')
    if m['phase'] != 'confirmation':
        require(not any(610083000 <= s <= 610083511 for s in expected), 'confirmation cohort cannot become development')
    else:
        c = m['confirmation']
        require(all(610083000 <= s <= 610083511 for s in allowed), 'confirmation seeds outside reserved cohort')
        require(c['comparator'] == 'Fprod' and c['champion'] != 'Fprod', 'confirmation comparator must be Fprod')
        require(arms == {'Fprod', c['champion']}, 'confirmation requires exactly two frozen arms')
        require(pairs == [(c['champion'], 'Fprod')], 'confirmation requires one champion-Fprod contrast')
        require(type(c['fixed_pairs']) is int and c['fixed_pairs'] == len(expected), 'confirmation fixed N mismatch')
        require(math.isfinite(c['frozen_epoch']) and c['frozen_epoch'] > 0, 'invalid champion freeze time')
        for gate in ('implementation_review','scientific_review','information_boundary','holdout_unopened_at_freeze'):
            require(c['gates'].get(gate) is True, 'confirmation gate missing: ' + gate)
    for arm in arms:
        env = dict(m['profiles']['common']); env.update(m['profiles']['arms'][arm])
        require(all(isinstance(k,str) and isinstance(v,str) for k,v in env.items()), 'environment must be strings')
        for key, value in {'STS_FAIR':'1', 'STS_STOP_AFTER_ACT':'3', 'STS_COLLECT_KEYS':'0',
                           'STS_OOC_MCTS':'0', 'STS_OOC_PUBLIC_FUTURES':'8',
                           'OMP_NUM_THREADS':'1'}.items():
            require(env.get(key) == value, arm + ': expected ' + key + '=' + value)
    return expected


def analyze(manifest_path, run_dir):
    m = json.loads(manifest_path.read_text())
    manifest_hash = digest(manifest_path)
    if 'analysis_script_sha256' in m:
        require(digest(__file__) == m['analysis_script_sha256'], 'frozen analysis script changed')
    expected = validate_manifest(m)
    root, binary = Path(m['root']).resolve(), Path(m['binary']).resolve()
    require(binary.name == 'one_combat' and digest(binary) == m['binary_sha256'], 'frozen binary changed')
    require(isinstance(m['artifacts'],dict) and bool(m['artifacts']), 'missing model/source artifacts')
    artifact_paths = {}
    for path, expected_hash in m['artifacts'].items():
        actual = (root / path).resolve()
        require(digest(actual) == expected_hash, 'artifact changed: ' + path)
        artifact_paths[actual] = expected_hash
    data, summary, inputs = {}, {}, []
    for arm in m['analysis_arms']:
        rows, wall, scorer_calls, cpu_seconds, cpu_rows = {}, 0.0, 0, 0.0, 0
        declared_env = dict(m['profiles']['common']); declared_env.update(m['profiles']['arms'][arm])
        receipts = sorted(run_dir.glob(arm + '_*.receipt.json'))
        receipt_prefixes = {str(p.resolve())[:-len('.receipt.json')] for p in receipts}
        csv_prefixes = {str(p.resolve())[:-4] for p in run_dir.glob(arm + '_*.csv')}
        require(csv_prefixes <= receipt_prefixes, 'CSV without invocation receipt')
        for receipt_path in receipts:
            receipt_path = receipt_path.resolve()
            prefix = str(receipt_path)[:-len('.receipt.json')]
            csv_path = Path(prefix + '.csv')
            paths = {k: Path(prefix + suffix) for k,suffix in SUFFIXES.items()}
            receipt = json.loads(receipt_path.read_text())
            require(receipt['arm'] == arm, 'receipt arm mismatch')
            require(receipt['status'] == 'completed' and receipt['exit_code'] == 0, arm + ': unsuccessful subprocess')
            require(receipt['manifest_sha256'] == manifest_hash, 'receipt frozen manifest hash mismatch')
            require(Path(receipt['manifest']).resolve() == manifest_path.resolve(), 'receipt manifest path mismatch')
            require(receipt['source_sha'] == m['source_sha'] and receipt['binary_sha256'] == m['binary_sha256'], 'receipt source/binary mismatch')
            if m['phase'] == 'confirmation':
                require(receipt['started_epoch'] >= m['confirmation']['frozen_epoch'], 'confirmation launched before champion freeze')
            actual_outputs = {k for k,p in paths.items() if p.exists()}
            require({'csv','meta','log'} <= actual_outputs, 'required output missing')
            require(set(receipt['outputs']) == actual_outputs, 'unrecorded/missing/unknown emitted output')
            for key, output in receipt['outputs'].items():
                require(Path(output['path']).resolve() == paths[key], 'output path not bound to invocation: ' + key)
                require(paths[key].stat().st_size == output['bytes'] and digest(paths[key]) == output['sha256'], 'output hash/size changed: ' + key)
                inputs.append({'kind': key, 'path': str(paths[key]), 'sha256': output['sha256']})
            expected_env = dict(declared_env, STS_EXECUTABLE_GIT_SHA=m['source_sha'])
            for key, output_key in TRACE_ENV.items():
                if key in receipt['environment']:
                    require(output_key in actual_outputs, 'trace flag without trace output: ' + key)
                    expected_env[key] = str(paths[output_key])
            require(receipt['environment'] == expected_env, 'undeclared or mismatched environment')
            meta_lines = paths['meta'].read_text().splitlines()
            require(len(meta_lines) == 1, 'expected one sidecar record')
            meta = json.loads(meta_lines[0]); config = meta['config']
            require(meta['asc'] == 0 and meta['threads'] == 1 and meta['sims'] == 10000, 'effective ascension/thread/budget argument')
            require(config['fairPlay'] and not config['collectKeys'], 'effective fair/key contract')
            require(config['executableGitSha'] == m['source_sha'], 'sidecar source mismatch')
            require(config['effectiveCombatBackend'] == 'native_silver', 'unexpected combat backend')
            require(config['silverExactRootBudgets'] == (declared_env['STS_SILVER_EXACT_ROOT_BUDGETS'] == '1'), 'effective exact-budget mismatch')
            require(bool(config['silverLearnedStopModel']) == (declared_env['STS_SILVER_LEARNED_STOP'] == '1'), 'effective learned-stop mismatch')
            require(not config['silverAdaptiveEnabled'], 'unexpected adaptive budget')
            require(config['silverReuseCapMode'] == 'allocated' and config['silverReuseCap'] == 32768, 'effective reuse cap mismatch')
            require(not config['silverLearnedStopBossFallback'] and config['silverLearnedStopBossMax'] == 0, 'unexpected learned-stop boss treatment')
            expected_win = declared_env.get('STS_WIN_NET', 'models/v_win_trees.txt')
            if expected_win == '1': expected_win = 'models/v_win_trees.txt'
            for role, path in {'floor':'models/v_rich_trees.txt', 'win':expected_win}.items():
                require(meta['models'][role] == path, 'loaded model path mismatch: ' + role)
                require((root / path).resolve() in artifact_paths, 'loaded model not frozen: ' + role)
            part = pa.load(str(csv_path))[0]
            require(len(part) == meta['nSeeds'], 'CSV/sidecar row count mismatch')
            part_seeds = {r['seed'] for r in part}
            block = meta['seedBlock']
            require(part_seeds == set(range(block['lo'], block['hi'] + 1)), 'CSV/sidecar source block mismatch')
            command = ['bash','tools/seed_guard.sh',str(binary),'bestbench','10000',str(len(part)),
                       '0',str(block['lo']),str(csv_path)]
            require(receipt['command'] == command, 'command does not match frozen invocation')
            log = paths['log'].read_text()
            require('[native OOC public encounter mixture: 8 futures]' in log, 'missing effective public mixture banner')
            require('[benchmark stops after Act 3 boss]' in log, 'missing effective Act-3 cutoff banner')
            if declared_env.get('STS_OOC_SKIP_OPTIONAL_RECALL') == '1':
                require('[native OOC optional Ruby Recall excluded when keys off and another action is legal]' in log,
                        'missing effective optional Recall filter banner')
            full_hp_banner = '[native OOC full-HP REST excluded when Smith is legal and Dream Catcher is absent]'
            require((full_hp_banner in log) == (declared_env.get('STS_OOC_SKIP_FULL_HP_REST', '0') == '1'),
                    'effective full-health REST filter banner mismatch')
            public = re.findall(r'\[public OOC receipt seed=(\d+) futures=(\d+) scorers=(\d+)\]', log)
            require(len(public) == len(part) and {int(s) for s,n,c in public} == part_seeds, 'public receipt source coverage')
            require(all(int(n) == 8 and int(c) > 0 for s,n,c in public), 'public future count or inference use missing')
            scorer_calls += sum(int(c) for s,n,c in public)
            if 'profile' in actual_outputs:
                for line in paths['profile'].read_text().splitlines():
                    profile = json.loads(line)
                    require(int(profile['seed']) in part_seeds, 'profile source outside invocation')
                    if 'thread_cpu_seconds' in profile:
                        cpu = profile['thread_cpu_seconds']
                        require(math.isfinite(cpu) and cpu >= 0, 'invalid observed thread CPU time')
                        cpu_seconds += cpu
                        cpu_rows += 1
            for row in part:
                require(row['seed'] not in rows, arm + ': duplicate source seed')
                require(row['seed'] in expected, arm + ': unreserved source seed')
                require(row['won'] in (0,1) and np.isfinite(row['sec']) and row['sec'] >= 0, 'invalid endpoint/runtime')
                rows[row['seed']] = row
            require(math.isfinite(receipt['wall_seconds']) and receipt['wall_seconds'] >= 0, 'invalid process time')
            wall += receipt['wall_seconds']
            inputs.append({'kind':'receipt','path':str(receipt_path),'sha256':digest(receipt_path)})
        require(set(rows) == expected, arm + ': missing source seeds ' + str(sorted(expected-set(rows))))
        data[arm] = rows
        wins = sum(r['won'] for r in rows.values())
        summary[arm] = {'n':len(rows), 'wins':wins, 'win_rate':wins/len(rows), 'win_rate_wilson95':wilson95(wins,len(rows)),
                        'mean_floor':float(np.mean([r['floor'] for r in rows.values()])),
                        'run_seconds_sum':sum(r['sec'] for r in rows.values()),
                        'process_wall_seconds_sum':wall, 'public_scorer_calls':scorer_calls,
                        'observed_profile_thread_cpu_seconds_sum':cpu_seconds if cpu_rows else None,
                        'observed_profile_thread_cpu_rows':cpu_rows}
    comparisons = {}
    for candidate, control in m['comparisons']:
        seeds = sorted(expected)
        delta = np.array([data[candidate][s]['won'] - data[control][s]['won'] for s in seeds],dtype=float)
        mean, low, high = pa.bootstrap_ci(delta,n_boot=10000,ci=.95,rng=np.random.default_rng(20261008))
        comparisons[candidate+'-'+control] = {'pairs':len(seeds), 'gain':mean, 'ci95':[low,high],
            'candidate_only':int((delta>0).sum()), 'control_only':int((delta<0).sum()),
            'both_win':sum(data[candidate][s]['won'] == data[control][s]['won'] == 1 for s in seeds),
            'decision':('CONFIRMED_IMPROVEMENT' if low>0 and mean>=.02 else 'NO_CONFIRMED_IMPROVEMENT')
                       if m['phase']=='confirmation' else 'DISCOVERY_OR_DEVELOPMENT_ONLY'}
    return {'phase':m['phase'], 'source_sha':m['source_sha'], 'binary_sha256':m['binary_sha256'],
            'manifest_sha256':manifest_hash, 'analysis_script_sha256':digest(__file__),
            'arms':summary,'comparisons':comparisons,'all_pairs_complete':True,
            'bootstrap_replicates':10000,'bootstrap_seed':20261008,'inputs':inputs,
            'comparison_scope':'Candidates compared with fair-corrected Fprod/Fflat; original hidden-queue Bprod is diagnostic-only.',
            'binomial_bounds':'Per-arm Wilson95 intervals are descriptive; the preregistered paired bootstrap governs the final decision.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('manifest',type=Path); p.add_argument('run_dir',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    require(not a.out.exists(), 'refusing to overwrite analysis output')
    report=analyze(a.manifest,a.run_dir)
    with a.out.open('x') as f:
        json.dump(report,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k!='inputs'},indent=2))


if __name__=='__main__':
    main()
