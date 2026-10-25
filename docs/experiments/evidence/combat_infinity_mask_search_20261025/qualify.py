#!/usr/bin/env python3
"""One flag-off patched-runtime qualification; no treatment and no oracle."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = HERE.parent / 'combat_infinity_reconstruction_20261024'
RUNTIME = REPO / 'build/infinity-heart-mask-search-20261025'
SOURCE = RUNTIME / 'source'
MODEL_BUNDLE = Path('/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-collection-20261016-v1/bundle')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def difference(expected, actual, pointer=''):
    if type(expected) is not type(actual):
        return {'pointer': pointer, 'expected': expected, 'actual': actual}
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            return {'pointer': pointer, 'expected_keys': sorted(expected), 'actual_keys': sorted(actual)}
        for k in sorted(expected):
            found = difference(expected[k], actual[k], pointer + '/' + k)
            if found:
                return found
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return {'pointer': pointer, 'expected_length': len(expected), 'actual_length': len(actual)}
        for i, (a, b) in enumerate(zip(expected, actual)):
            found = difference(a, b, pointer + '/' + str(i))
            if found:
                return found
    elif expected != actual:
        return {'pointer': pointer, 'expected': expected, 'actual': actual}
    return None


def complete_rows(path):
    if not path.exists():
        return []
    data = path.read_bytes()
    return [json.loads(line) for line in data.split(b'\n')[:-1] if line]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('seed', type=int, choices=[111101032])
    parser.add_argument('--reviewed-sha', required=True)
    args = parser.parse_args()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip() == args.reviewed_sha
    frozen = next(r for r in json.loads((BASE / 'frozen-prefixes.json').read_text()) if r['seed'] == args.seed)
    expected_path = BASE / frozen['expected_file']
    assert sha(expected_path) == frozen['expected_sha256']
    expected = json.loads(gzip.decompress(expected_path.read_bytes()))
    preflight = json.loads((HERE.parent / 'combat_infinity_capture_20261024/PREFLIGHT.json').read_text())
    lead = next(r for r in preflight['leads'] if r['source_seed'] == args.seed)
    build = json.loads((HERE / 'build-result.json').read_text())
    binary = Path(build['binary_path'])
    assert sha(binary) == build['binary_sha256']
    plan = json.loads((BASE / 'source-build-plan.json').read_text())
    assert all(sha(SOURCE / p) == build['patched_file_hashes'].get(p, h) for p, h in plan['tracked_files_sha256'].items())
    assert all(sha(SOURCE / p) == h for p,h in build['patched_file_hashes'].items())
    for model in lead['models']:
        assert sha(Path(model['path'])) == model['expected_sha256']
    run = RUNTIME / 'parity'
    run.mkdir()  # Never overwrite or retry an existing run.
    for name in ['models', 'selfplay', 'studentc.bin']:
        (run / name).symlink_to(MODEL_BUNDLE / name, target_is_directory=name != 'studentc.bin')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('STS_', 'OMP_'))}
    original = {k: v for k, v in lead['original_environment'].items() if k.startswith(('STS_', 'OMP_'))}
    env.update(original)
    for key, suffix in [('STS_OOC_DECISION_TRACE', 'trace.jsonl'), ('STS_OOC_MCTS_ROOT_TRACE', 'roots.jsonl'),
                        ('STS_OOC_MCTS_TRACE', 'mcts.csv'), ('STS_OOC_SIBLING_CAPTURE', 'sib.jsonl')]:
        env[key] = str(run / suffix)
    env['STS_SILVER_PUBLIC_TRACE'] = str(run / 'public.jsonl')
    env['STS_SILVER_PUBLIC_TARGET'] = frozen['target']['future_public_target_if_restored']
    command = ['bash', str(SOURCE / 'tools/seed_guard.sh'), str(binary), 'heartoutcomegen', '1',
               str(args.seed), str(run / 'states.jsonl'), 'on']
    record = {'seed': args.seed, 'source_sha': plan['source_sha'], 'binary_sha256': sha(binary),
              'runtime_identity': 'RESEARCH_PATCHED_NOT_HISTORICAL', 'reviewed_sha':args.reviewed_sha, 'patch_sha256':build['patch_sha256'], 'command': command, 'cwd': str(run),
              'environment': {k: v for k, v in env.items() if k.startswith(('STS_', 'OMP_'))},
              'host_environment': {k: env.get(k) for k in ['HOME', 'PATH']},
              'models': lead['models'], 'frozen_prefix': frozen, 'wall_limit_seconds': 900,
              'oracle_executed': False, 'capture_quarantined': True,
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write(run / 'started.json', record)
    started = time.monotonic()
    usage_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    state_matches = trace_matches = 0
    header_match = False
    mismatch = None
    status = 'RUNNING'
    with (run / 'stdout.log').open('wb') as stdout, (run / 'stderr.log').open('wb') as stderr:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        record['pid'] = process.pid
        write(run / 'started.json', record)
        try:
            while True:
                rows = complete_rows(run / 'states.jsonl')
                if rows and not header_match:
                    mismatch = difference(expected['header'], rows[0], '/header')
                    header_match = mismatch is None
                states = [r for r in rows if r.get('type') == 'state']
                traces = complete_rows(run / 'trace.jsonl')
                # Order public events by state -> decision trace -> next state.
                for i in range(max(len(states), len(traces))):
                    if mismatch:
                        break
                    if i < len(states) and i < len(expected['states']) and i >= state_matches:
                        mismatch = difference(expected['states'][i], states[i], f'/states/{i}')
                        if not mismatch:
                            state_matches += 1
                    if not mismatch and i < len(traces) and i < len(expected['trace']) and i >= trace_matches:
                        mismatch = difference(expected['trace'][i], traces[i], f'/trace/{i}')
                        if not mismatch:
                            trace_matches += 1
                progress = {'header_match': header_match, 'state_matches': state_matches,
                            'trace_matches': trace_matches, 'wall_seconds': time.monotonic() - started}
                write(run / 'progress.json', progress)
                if mismatch:
                    status = 'DIVERGED'
                    break
                if header_match and state_matches == len(expected['states']) and trace_matches == len(expected['trace']):
                    status = 'CHECKPOINT_IDENTICAL'
                    break
                if process.poll() is not None:
                    status = 'PROCESS_ENDED_BEFORE_PREFIX'
                    break
                if time.monotonic() - started > 900:
                    status = 'WALL_LIMIT'
                    break
                time.sleep(0.25)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    usage_end = resource.getrusage(resource.RUSAGE_CHILDREN)
    record.update({'status': status, 'first_difference': mismatch, 'header_match': header_match,
                   'state_matches': state_matches, 'trace_matches': trace_matches,
                   'wall_seconds': time.monotonic() - started, 'returncode': process.returncode,
                   'child_user_seconds': usage_end.ru_utime - usage_start.ru_utime,
                   'child_system_seconds': usage_end.ru_stime - usage_start.ru_stime,
                   'intentional_prefix_stop': status == 'CHECKPOINT_IDENTICAL',
                   'capture_quarantined': status != 'CHECKPOINT_IDENTICAL',
                   'files': {p.name: sha(p) for p in run.iterdir() if p.is_file() and not p.is_symlink()},
                   'finished_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    write(run / 'receipt.json', record)
    record['qualification_result'] = 'FLAG_OFF_PARITY_PASS' if status == 'CHECKPOINT_IDENTICAL' else 'MASK_SEARCH_RUNTIME_PARITY_FAILED'
    write(HERE / 'parity.json', record)
    print(json.dumps({k: record[k] for k in ['seed', 'status', 'state_matches', 'trace_matches', 'first_difference', 'wall_seconds']}, indent=2))
    return 0 if status == 'CHECKPOINT_IDENTICAL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
