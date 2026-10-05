#!/usr/bin/env python3
"""Frozen 155-source VALIDATION replay and full S0 coordinator; never TRAIN/TEST.

No automatic retry or resume. Existing canaries may be reused only after complete
hash/parity checks. This command performs expensive work: launch only after the
coordinator commit and scientific protocol have been reviewed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import math
import os
from pathlib import Path
import subprocess
import time
from threading import Event

from audit_screen_leaf_379 import EXPECTED, digest, source_split_function
from run_screen_leaf_replay_379 import run as replay_source, verify_temporal
from run_screen_leaf_s0_pilot_379 import X2B

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'build/issue379-replay'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def load(path):
    return json.loads(path.read_text())


def clean_sha(expected=None):
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    require(expected is None or sha == expected, 'coordinator HEAD changed')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip(),
            'coordinator checkout must remain clean')
    return sha


def check_hashes(files):
    for filename, expected in files.items():
        require(digest(Path(filename)) == expected, 'custody mismatch: ' + filename)


def frozen_sources(index):
    require(digest(index) == EXPECTED, 'sealed corpus index mismatch')
    corpus = load(index)
    split, _ = source_split_function()
    require(len(corpus['sourceSeeds']) == 1024 and len(set(corpus['sourceSeeds'])) == 1024,
            'invalid corpus source identities')
    wanted = {s for s in corpus['sourceSeeds'] if split(s) == 'VALIDATION'}
    require(len(wanted) == 155, 'expected exactly 155 VALIDATION sources')
    sources = {}
    for component in corpus['components']:
        path = (index.parent / component['manifest']).resolve()
        # Manifest metadata only; numerical CSVs are never inspected here.
        manifest = load(path)
        seed = manifest['seedSpec']['start']
        if seed not in wanted:
            continue
        require(manifest['seedSpec'] == {'start': seed, 'count': 1, 'ascension': 0}, 'source schema mismatch')
        require(seed not in sources and digest(path) == component['sha256'], 'duplicate or changed manifest')
        sources[seed] = {'seed': seed, 'split': 'VALIDATION', 'manifest': str(path),
                         'manifest_sha256': component['sha256'],
                         'producer_sha': manifest['producerGitSha'], 'outputs': manifest['outputs'],
                         'decision_rows': manifest['decisionSink']['rows']}
    require(set(sources) == wanted, 'incomplete VALIDATION manifest coverage')
    return [sources[s] for s in sorted(sources)]


def verify_replay(directory, source):
    receipt, result = load(directory / 'receipt.json'), load(directory / 'result.json')
    require(receipt['seed'] == source['seed'] and receipt['split'] == 'VALIDATION', 'replay source mismatch')
    require(Path(receipt['source_manifest']).resolve() == Path(source['manifest']) and
            receipt['source_manifest_sha256'] == source['manifest_sha256'], 'replay manifest mismatch')
    require(digest(Path(source['manifest'])) == source['manifest_sha256'], 'source manifest changed')
    require(receipt['derived']['original_source_sha'] == source['producer_sha'], 'replay producer mismatch')
    require(result['status'] == 'PASS' and result['exit_code'] == 0, 'replay is not qualified')
    require(set(result['csv_parity']) == set(source['outputs']), 'incomplete replay parity')
    for suffix, expected in source['outputs'].items():
        entry = result['csv_parity'][suffix]
        require(entry['equal'] is True and entry['expected'] == expected and entry['actual'] == expected,
                'replay parity identity mismatch')
        require(digest(directory / ('replay.' + suffix)) == expected, 'replay CSV changed')
    snapshot = directory / 'snapshots.jsonl'
    require(digest(snapshot) == result['snapshots_sha256'], 'snapshot hash mismatch')
    temporal = verify_temporal(directory, source['seed'])
    require(result.get('temporal') == temporal, 'missing or changed temporal replay evidence')
    return {'directory': str(directory), 'receipt_sha256': digest(directory / 'receipt.json'),
            'result_sha256': digest(directory / 'result.json'), 'snapshots_sha256': digest(snapshot),
            'temporal': temporal}


def snapshot_identities(path, source):
    identities = set()
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            require(row['sourceSeed'] == source['seed'], 'snapshot has foreign source')
            identity = (row['sourceSeed'], row['branchId'], row['rowIdx'])
            require(identity not in identities, 'duplicate snapshot identity')
            identities.add(identity)
    require(len(identities) == source['decision_rows'] and identities, 'incomplete snapshot coverage')
    return identities


def one_source(source, protocol, deadline, failed):
    started = time.monotonic()
    source_deadline = min(deadline, started + protocol['per_source_seconds'])
    directory = Path(protocol['output']) / str(source['seed'])
    directory.mkdir(exist_ok=False)
    result = {'seed': source['seed'], 'status': 'FAIL'}
    try:
        clean_sha(protocol['code_sha'])
        check_hashes(protocol['runtime_hashes'])
        replay = Path(protocol['reuse'][str(source['seed'])]['directory']) if str(source['seed']) in protocol['reuse'] else directory / 'replay'
        if str(source['seed']) not in protocol['reuse']:
            remaining = int(source_deadline - time.monotonic())
            require(remaining > 0, 'source/global budget exhausted before replay')
            derived = Path(protocol['derived'][source['producer_sha']]['directory'])
            replay_source(Path(protocol['corpus']), source['seed'], derived, replay,
                          protocol['code_sha'], remaining)
        custody = verify_replay(replay, source)
        if str(source['seed']) in protocol['reuse']:
            require(custody == protocol['reuse'][str(source['seed'])], 'reuse evidence changed after freeze')
        snapshot = replay / 'snapshots.jsonl'
        identities = snapshot_identities(snapshot, source)
        clean_sha(protocol['code_sha'])
        check_hashes(protocol['runtime_hashes'])
        remaining = int(source_deadline - time.monotonic())
        require(remaining > 0, 'source/global budget exhausted before S0')
        env = dict(protocol['s0_environment'])
        argv = ['bash', str(REPO / 'tools/seed_guard.sh'), protocol['s0_binary'], 'screenleafs0',
                str(snapshot), str(directory / 'predictions.jsonl'), str(len(identities)), '1']
        write_new(directory / 's0-receipt.json', {'source': source, 'replay': custody,
                  'protocol_sha256': protocol['protocol_sha256'], 'argv': argv, 'env': env,
                  'wall_budget_seconds': remaining, 'replicates': 1})
        with (directory / 'stdout').open('x') as out, (directory / 'stderr').open('x') as err:
            process = subprocess.run(['timeout', '-k', '10', str(remaining), '/usr/bin/time', '-v', *argv],
                                     cwd=REPO, env=env, stdout=out, stderr=err)
        result['s0_exit_code'] = process.returncode
        require(process.returncode == 0, 'S0 evaluator failed; preserve partial predictions')
        observed = set()
        by_screen = {}
        with (directory / 'predictions.jsonl').open() as stream:
            for line in stream:
                row = json.loads(line)
                identity = (row['sourceSeed'], row['branchId'], row['rowIdx'])
                require(identity in identities and identity not in observed, 'S0 prediction identity mismatch')
                require(len(row['values']) == 1 and math.isfinite(row['values'][0]) and 0 <= row['values'][0] <= 1,
                        'invalid S0 prediction')
                observed.add(identity)
                stats = by_screen.setdefault(row['screen'], {'rows': 0, 'leaf_cpu_seconds': 0, 'projection_steps': 0})
                stats['rows'] += 1
                stats['leaf_cpu_seconds'] += row['leafCpuSeconds']
                stats['projection_steps'] += row['projectionSteps']
        require(observed == identities, 'S0 missing predictions')
        require(digest(snapshot) == custody['snapshots_sha256'], 'snapshot changed during S0')
        check_hashes(protocol['runtime_hashes'])
        result.update(status='PASS', rows=len(observed), by_screen=by_screen,
                      predictions_sha256=digest(directory / 'predictions.jsonl'), replay=custody)
    except (Exception, SystemExit) as error:
        failed.set()
        result['error'] = f'{type(error).__name__}: {error}'
    result['wall_seconds'] = time.monotonic() - started
    write_new(directory / 'result.json', result)
    return result


def run(index, output, derived_dirs, reuse_dirs, pilot_receipt, workers, per_source_seconds, global_seconds):
    require(1 <= workers <= 6 and workers <= (os.cpu_count() or 1), 'workers must be 1..6')
    require(0 < per_source_seconds <= 3600 and 0 < global_seconds <= 43200, 'resource budget exceeds frozen maximum')
    sha = clean_sha()
    sources = frozen_sources(index)
    by_seed = {s['seed']: s for s in sources}
    derived, runtime_hashes = {}, {}
    for directory in derived_dirs:
        manifest_path = directory / 'derived-producer.json'
        manifest = load(manifest_path)
        producer = manifest['original_source_sha']
        require(producer not in derived, 'duplicate derived producer')
        files = {str(directory / p): h for p, h in manifest['derived_files'].items()}
        check_hashes(files)
        runtime_hashes.update(files)
        runtime_hashes[str(manifest_path)] = digest(manifest_path)
        runtime_hashes[str(directory / 'build/one_combat')] = digest(directory / 'build/one_combat')
        derived[producer] = {'directory': str(directory), 'manifest': manifest,
                             'manifest_sha256': digest(manifest_path),
                             'binary_sha256': runtime_hashes[str(directory / 'build/one_combat')]}
    require(set(derived) == {s['producer_sha'] for s in sources}, 'derived producer coverage mismatch')
    # Pin the original producers' runtime/model custody before scheduling any seed.
    original_teachers = {}
    for source in sources:
        manifest = load(Path(source['manifest']))
        teacher_path = Path(manifest['teacherPath'])
        runtime_hashes[str(teacher_path)] = manifest['teacherManifestSha256']
        if str(teacher_path) in original_teachers:
            continue
        teacher = load(teacher_path)
        freeze_path = teacher_path.parent / 'freeze.json'
        freeze = load(freeze_path)
        runtime_path = teacher_path.parent / 'runtime-environment.json'
        runtime_hashes[str(freeze_path)] = digest(freeze_path)
        runtime_hashes[str(runtime_path)] = freeze['artifacts']['runtime-environment.json']
        for artifact in teacher['model_artifacts'] + teacher['ooc_policy']['model_artifacts']:
            runtime_hashes[str(teacher_path.parent / artifact['path'])] = artifact['sha256']
        original_teachers[str(teacher_path)] = {'teacher_sha256': manifest['teacherManifestSha256'],
            'runtime_sha256': runtime_hashes[str(runtime_path)], 'freeze_sha256': digest(freeze_path)}
    reuse = {}
    for directory in reuse_dirs:
        seed = load(directory / 'receipt.json')['seed']
        require(seed in by_seed and str(seed) not in reuse, 'non-VALIDATION or duplicate reuse source')
        reuse[str(seed)] = verify_replay(directory, by_seed[seed])
    pilot = load(pilot_receipt)
    pilot_result = load(pilot_receipt.parent / 'result.json')
    require(pilot_result['status'] == 'PASS' and pilot_result['exit_code'] == 0, 'S0 pilot did not pass')
    require(pilot['corpus_sha256'] == EXPECTED and pilot['x2b_sha256'] == X2B and pilot['replicates'] == 1,
            'pilot protocol identity mismatch')
    binary = REPO / 'build/linux-gcc-release/one_combat'
    require(digest(binary) == pilot['binary_sha256'], 'S0 binary changed since qualified pilot')
    runtime_hashes[str(binary)] = pilot['binary_sha256']
    for path, expected in pilot['auxiliary_models'].items():
        runtime_hashes[str(REPO / path)] = expected
    model = REPO / 'models/candidates/v_win_x2b_trees.txt'
    runtime_hashes[str(model)] = X2B
    runtime_hashes[str(pilot_receipt)] = digest(pilot_receipt)
    runtime_hashes[str(REPO / 'tools/seed_guard.sh')] = digest(REPO / 'tools/seed_guard.sh')
    for name in ('audit_screen_leaf_379.py', 'run_screen_leaf_replay_379.py', 'run_screen_leaf_validation_379.py'):
        runtime_hashes[str(REPO / 'tools' / name)] = digest(REPO / 'tools' / name)
    check_hashes(runtime_hashes)
    env = dict(pilot['env'])
    env.update(STS_WIN_NET=str(model), STS_EXECUTABLE_GIT_SHA=sha, OMP_NUM_THREADS='1', STS_OOC_MCTS='0')
    env.pop('STS_OOC_MCTS_TRACE', None)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {'schema': 'screen_leaf_379_full_validation_v1', 'code_sha': sha,
                'corpus': str(index), 'corpus_sha256': EXPECTED, 'sources': sources,
                'source_count': 155, 'original_teachers': original_teachers, 'workers': workers, 'logical_cpus': os.cpu_count(),
                'per_source_seconds': per_source_seconds, 'global_seconds': global_seconds,
                'replicates': 1, 'output': str(output), 'derived': derived, 'reuse': reuse,
                's0_binary': str(binary), 's0_environment': env, 'runtime_hashes': runtime_hashes,
                'pilot_receipt': str(pilot_receipt), 'pilot_source_sha': pilot['source_sha'],
                'test_access': 'No TEST or TRAIN numerical rows; only VALIDATION reconstruction and S0.',
                'failure_rule': 'No retry. Stop scheduling on first failure or deadline; preserve active source jobs and all outputs.',
                'deadline_note': 'Source timeouts share the remaining global budget; timeout may take up to 10 extra seconds to kill its own child group.'}
    write_new(output / 'protocol.json', protocol)
    protocol['protocol_sha256'] = digest(output / 'protocol.json')
    start = time.monotonic()
    deadline = start + global_seconds
    results, pending, next_source, stopped = [], {}, 0, False
    failed = Event()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        while pending or (not stopped and next_source < len(sources)):
            if time.monotonic() >= deadline or failed.is_set():
                stopped = True
            while not stopped and not failed.is_set() and len(pending) < workers and next_source < len(sources):
                source = sources[next_source]
                pending[executor.submit(one_source, source, protocol, deadline, failed)] = source['seed']
                next_source += 1
            if not pending:
                break
            completed, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
            for future in completed:
                seed = pending.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = {'seed': seed, 'status': 'FAIL', 'error': repr(error)}
                results.append(result)
                print(json.dumps({'seed': seed, 'status': result['status'], 'completed': len(results)}, sort_keys=True), flush=True)
                if result['status'] != 'PASS':
                    stopped = True
    summary = {'status': 'PASS' if len(results) == 155 and all(r['status'] == 'PASS' for r in results) else 'FAIL',
               'protocol_sha256': protocol['protocol_sha256'], 'results': sorted(results, key=lambda r: r['seed']),
               'unscheduled_sources': [s['seed'] for s in sources[next_source:]], 'wall_seconds': time.monotonic() - start}
    write_new(output / 'result.json', summary)
    require(summary['status'] == 'PASS', 'VALIDATION qualification incomplete; see preserved results')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'full-validation')
    parser.add_argument('--derived', action='append', type=Path, required=True)
    parser.add_argument('--reuse', action='append', type=Path, default=[])
    parser.add_argument('--pilot-receipt', type=Path, default=ROOT / 's0-pilot-two-producers/receipt.json')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--per-source-seconds', type=int, default=3600)
    parser.add_argument('--global-seconds', type=int, default=43200)
    args = parser.parse_args()
    run(args.index.resolve(), args.output.resolve(), [p.resolve() for p in args.derived],
        [p.resolve() for p in args.reuse], args.pilot_receipt.resolve(), args.workers,
        args.per_source_seconds, args.global_seconds)
