#!/usr/bin/env python3
"""TRAIN/VALIDATION-only frozen replay canary, with exact output parity.

Does not run S0, fit models, open TEST, or reuse/overwrite an output directory.
Derived source/binary and teacher identities are recorded before seed execution.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from audit_screen_leaf_379 import EXPECTED, digest, source_split_function


def verify_temporal(output, seed):
    """Bind new temporal observations to byte-identical original MAP rows."""
    maps = {}
    with (output / 'replay.map.csv').open(newline='') as stream:
        reader = csv.reader(stream)
        header = next(reader)
        if header[:9] != ['sourceSeed', 'branchId', 'deviationIdx', 'rowIdx', 'act', 'floor', 'mapX', 'mapY', 'teacherId'] or len(header) != 1026:
            raise ValueError('temporal MAP schema mismatch')
        if hashlib.sha256(','.join(header[9:]).encode()).hexdigest() != 'd8fdd003636fc00e537320f0406a2c36f890d8ba16edc10cc7c2b0fbdf7ed836':
            raise ValueError('temporal MAP rich header mismatch')
        for row in reader:
            if len(row) != len(header): raise ValueError('temporal MAP row width mismatch')
            key = (int(row[0]), row[1], int(row[3]))
            if key in maps: raise ValueError('duplicate MAP identity')
            maps[key] = {'features': ','.join(row[9:]), 'act': int(row[4]), 'floor': int(row[5]),
                         'mapX': int(row[6]), 'mapY': int(row[7])}
    temporal_path = output / 'snapshots.jsonl.temporal.jsonl'
    observed, branches, captures, timelines = set(), set(), {}, {}
    with temporal_path.open() as stream:
        for line in stream:
            trajectory = json.loads(line)
            if trajectory['sourceSeed'] != seed or trajectory['schema'] != 'screen_leaf_temporal_v1':
                raise ValueError('temporal source/schema mismatch')
            branch = trajectory['branchId']
            if branch in branches: raise ValueError('duplicate temporal trajectory')
            branches.add(branch)
            timelines[branch] = trajectory['observations']
            previous = -1
            for event in trajectory['observations']:
                if event['observationSeq'] <= previous: raise ValueError('nonmonotone observation order')
                previous = event['observationSeq']
                if event['kind'] == 'map':
                    key = (seed, branch, event['mapRowIdx'])
                    if key in observed or key not in maps or any(event[k] != v for k, v in maps[key].items()):
                        raise ValueError('temporal MAP observation differs from original CSV')
                    observed.add(key)
                elif event['finalRowIdx'] >= 0:
                    key = (seed, branch, event['finalRowIdx'])
                    if key in captures: raise ValueError('duplicate temporal captured row')
                    captures[key] = event['observationSeq']
    # Forced MAP branches append their initial MAP row outside the observation
    # hook. They are not eligible temporal endpoints without an observed link.
    with (output / 'replay.branches.csv').open(newline='') as stream:
        allowed_missing = {(seed, r['branchId'], 0) for r in csv.DictReader(stream)
                           if int(r['sourceSeed']) == seed and r['type'] == 'MAP'}
    if not (set(maps) - observed) <= allowed_missing:
        raise ValueError('unexplained missing temporal MAP observation')
    snapshots = set()
    with (output / 'snapshots.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            key = (row['sourceSeed'], row['branchId'], row['rowIdx'])
            if key in snapshots or captures.get(key) != row['observationSeq']:
                raise ValueError('temporal snapshot mapping differs')
            snapshots.add(key)
            link = row['calibrationLink']
            expected = {'status': 'NO_SUBSEQUENT_OBSERVED_MAP',
                        'definition': 'last_captured_supported_nonsingleton_across_all_screen_families',
                        'interveningSingletons': 0, 'interveningUnsupported': 0}
            later_captured, unresolved = False, False
            for event in timelines[row['branchId']]:
                if event['observationSeq'] <= row['observationSeq']: continue
                if event['kind'] == 'map':
                    expected['map'] = event
                    expected['status'] = ('LATER_CAPTURED_DECISION' if later_captured else
                                          'INTERVENING_UNRESOLVED_SUPPORTED_DECISION' if unresolved else
                                          'EXACT_LAST_CAPTURED_TO_OBSERVED_MAP')
                    break
                if event['finalRowIdx'] >= 0: later_captured = True
                elif event['supported'] and event['complete']:
                    if event['optionCount'] > 1: unresolved = True
                    else: expected['interveningSingletons'] += 1
                else: expected['interveningUnsupported'] += 1
            if expected['interveningUnsupported'] and expected['status'] == 'EXACT_LAST_CAPTURED_TO_OBSERVED_MAP':
                expected['status'] = 'INTERVENING_UNSUPPORTED_DECISION'
            if link != expected: raise ValueError('calibration link does not match observed timeline')
            if 'map' in link:
                event = link['map']
                key_map = (seed, row['branchId'], event['mapRowIdx'])
                if key_map not in maps or any(event[k] != v for k, v in maps[key_map].items()):
                    raise ValueError('calibration MAP differs from original CSV')
    if snapshots != set(captures): raise ValueError('temporal captured row coverage differs')
    return {'temporal_sha256': digest(temporal_path), 'map_observations': len(observed),
            'map_csv_rows': len(maps), 'map_rows_without_observation': len(set(maps) - observed),
            'captured_observations': len(captures), 'trajectories': len(branches)}


def run(index, seed, derived, output, coordinator_sha, budget):
    if budget <= 0:
        raise ValueError('positive wall budget required')
    repo = Path(__file__).resolve().parents[1]
    current_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    if coordinator_sha != current_sha:
        raise ValueError('coordinator SHA differs from current checkout')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True).strip():
        raise ValueError('reviewed reconstruction checkout must be clean')
    split, _ = source_split_function()
    if split(seed) == 'TEST':
        raise ValueError('DECISION TEST replay sealed; this tool never permits TEST')
    if digest(index) != EXPECTED:
        raise ValueError('corpus identity mismatch')
    corpus = json.loads(index.read_text())
    selected = None
    for entry in corpus['components']:
        path = (index.parent / entry['manifest']).resolve()
        # No numerical CSV reads: select by the source manifest.
        manifest = json.loads(path.read_text())
        if manifest['seedSpec'] == {'start': seed, 'count': 1, 'ascension': 0}:
            if digest(path) != entry['sha256'] or selected is not None:
                raise ValueError('manifest identity mismatch or duplicate source')
            selected = path, manifest, entry['sha256']
    if selected is None:
        raise ValueError('source absent from frozen corpus')
    path, manifest, manifest_hash = selected
    derived_manifest = json.loads((derived / 'derived-producer.json').read_text())
    if derived_manifest['original_source_sha'] != manifest['producerGitSha']:
        raise ValueError('wrong frozen producer for source')
    for relative, expected in derived_manifest['derived_files'].items():
        if digest(derived / relative) != expected:
            raise ValueError(f'derived source changed: {relative}')
    original_teacher = Path(manifest['teacherPath'])
    if digest(original_teacher) != manifest['teacherManifestSha256']:
        raise ValueError('original teacher custody mismatch')
    teacher = json.loads(original_teacher.read_text())
    executable = derived / 'build/one_combat'
    # This SHA identifies the reviewed reconstruction code; original producer
    # SHA plus the derived file hashes separately identify the program built.
    if len(coordinator_sha) != 40:
        raise ValueError('coordinator SHA required')
    teacher['git_sha'] = coordinator_sha
    teacher['executable_sha256'] = digest(executable)
    teacher['environment']['STS_EXECUTABLE_GIT_SHA'] = coordinator_sha
    cwd = original_teacher.parent
    model_hashes = {}
    for model in teacher['model_artifacts'] + teacher['ooc_policy']['model_artifacts']:
        model_path = cwd / model['path']
        if digest(model_path) != model['sha256']:
            raise ValueError('original reconstruction model custody mismatch')
        model_hashes[str(model_path)] = model['sha256']
    output.mkdir(parents=True, exist_ok=False)
    teacher_path = output / 'derived-teacher.json'
    teacher_path.write_text(json.dumps(teacher, indent=2) + '\n')
    prefix = output / 'replay'
    runtime_path = cwd / 'runtime-environment.json'
    freeze = json.loads((cwd / 'freeze.json').read_text())
    if digest(runtime_path) != freeze['artifacts']['runtime-environment.json']:
        raise ValueError('frozen runtime environment changed')
    frozen_runtime = json.loads(runtime_path.read_text())
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'], **frozen_runtime,
           **teacher['environment'], 'STS_VWIN_DECISION_SINK': '1',
           'STS_SCREEN_LEAF_SNAPSHOT_OUT': str(output / 'snapshots.jsonl')}
    sampling = manifest['sampling']
    k = sampling['samplesPerType']
    parity = manifest['branchParity']['percent']
    argv = ['bash', str(derived / 'tools/seed_guard.sh'), str(executable),
            'vwinrefreshgen', '1', '10000', '0', str(prefix), str(seed), str(teacher_path),
            str(k), str(parity)]
    receipt = {'purpose': 'Frozen trajectory reconstruction parity, no model selection',
               'split': split(seed), 'seed': seed, 'source_count': 1, 'threads': 1,
               'wall_budget_seconds': budget, 'source_manifest': str(path),
               'source_manifest_sha256': manifest_hash,
               'original_teacher_sha256': manifest['teacherManifestSha256'],
               'original_runtime_environment_sha256': digest(runtime_path),
               'derived_teacher_sha256': digest(teacher_path), 'derived': derived_manifest,
               'binary_sha256': digest(executable), 'model_hashes': model_hashes,
               'coordinator_sha': coordinator_sha, 'cwd': str(cwd), 'argv': argv, 'env': env,
               'decision_rule': 'All frozen CSV outputs must be byte-identical; any mismatch stops S0'}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    start = time.monotonic()
    with (output / 'stdout').open('x') as stdout, (output / 'stderr').open('x') as stderr:
        # timeout owns the child process group and escalates only this new run.
        result = subprocess.run(['timeout', '-k', '10', str(budget), '/usr/bin/time', '-v', *argv],
                                cwd=cwd, env=env, stdout=stdout, stderr=stderr)
    summary = {'exit_code': result.returncode, 'wall_seconds': time.monotonic() - start,
               'csv_parity': {}, 'status': 'FAIL'}
    if result.returncode == 0:
        for suffix, expected in manifest['outputs'].items():
            actual = digest(Path(str(prefix) + '.' + suffix))
            summary['csv_parity'][suffix] = {'expected': expected, 'actual': actual,
                                            'equal': actual == expected}
        if all(v['equal'] for v in summary['csv_parity'].values()):
            try:
                summary['temporal'] = verify_temporal(output, seed)
                summary['status'] = 'PASS'
                summary['snapshots_sha256'] = digest(output / 'snapshots.jsonl')
            except Exception as error:
                summary['temporal_error'] = f'{type(error).__name__}: {error}'
    (output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if summary['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', required=True, type=Path)
    p.add_argument('--seed', required=True, type=int)
    p.add_argument('--derived', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--coordinator-sha', required=True)
    p.add_argument('--wall-budget', type=int, default=1200)
    a = p.parse_args()
    run(a.index.resolve(), a.seed, a.derived.resolve(), a.output.resolve(),
        a.coordinator_sha, a.wall_budget)
