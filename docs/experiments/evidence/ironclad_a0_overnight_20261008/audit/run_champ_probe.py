#!/usr/bin/env python3
"""One frozen public Champ invocation; no scheduling, retry or adaptation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[5]
AUDIT = Path(__file__).resolve().parent
RAW = ROOT / 'build/overnight_20261008/champ_d13'
SPEC_SHA = '8d562f08f61bec9ce12f1a303a33376f532fab7cafd32ac75d6245aefd90fbb5'
ROW_SHA = '4ddbdefc045d4e7467fa448bcec48c235ae6c10716796df10a99b695bd7e6e93'
CAPTURE_SHA = '0a679ddf01a75eae8186a7c68eda9d6b808decb42c6c2c0457b4c2fc980a4f83'
CAPTURE_SOURCE = '3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0'
HELPER_SHA = 'e78ac9e5d229f48f2e28429855eafaa9e158589b359ad50369d3c10536ffda9a'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def git_blob(source, path):
    require(len(source) == 40 and all(c in '0123456789abcdef' for c in source), 'invalid source SHA')
    return subprocess.run(['git', 'show', source + ':' + path], cwd=ROOT,
                          check=True, capture_output=True).stdout


def custody(freeze_path, freeze_sha, tools_path, tools_sha):
    require(sha(freeze_path) == freeze_sha, 'build freeze changed')
    require(sha(tools_path) == tools_sha, 'tool freeze changed')
    f, t = load(freeze_path), load(tools_path)
    require(t['schema'] == 'champ_d13_tools_freeze_v1' and t['build_freeze_sha256'] == freeze_sha,
            'tool/build freeze mismatch')
    require(f['build_gate'] == 'PASS' and f['threads'] == f['max_workers'] == 1,
            'build/one-worker contract')
    require(f['timeout_seconds_per_pair'] == 600 and f['evaluation_allocation'] == list(range(2, 64)),
            'budget/allocation changed')
    require(f['helper_source_sha256'] == HELPER_SHA and sha(f['binary']) == f['binary_sha256'],
            'helper/binary changed')
    require(hashlib.sha256(git_blob(f['source_sha'], 'apps/silver_public_pair_probe.cpp')).hexdigest() == HELPER_SHA,
            'producer commit does not contain reviewed helper')
    require(hashlib.sha256(git_blob(f['source_sha'], 'CMakeLists.txt')).hexdigest() == t['cmake_sha256'],
            'producer CMake differs from frozen target')
    for name, digest in f['build_logs'].items():
        require(sha(name) == digest, 'build log changed')
    for name, digest in t['artifacts'].items():
        require(sha(ROOT / name) == digest, 'reviewed tooling changed: ' + name)
    expected_tools = {str(Path(__file__).resolve().relative_to(ROOT)),
        str((AUDIT / 'analyze_champ_probe.py').relative_to(ROOT)), 'tools/seed_guard.sh', 'paired_analysis.py'}
    require(set(t['artifacts']) == expected_tools, 'incomplete tooling custody')
    require(f['specification_sha256'] == SPEC_SHA and sha(f['specification']) == SPEC_SHA,
            'specification changed')
    s = load(f['specification'])
    require(s['public_row_sha256'] == ROW_SHA and sha(s['public_row_path']) == ROW_SHA,
            'extracted root changed')
    require(s['capture_sha256'] == CAPTURE_SHA and sha(s['capture_path']) == CAPTURE_SHA
            and s['capture_source_sha'] == CAPTURE_SOURCE, 'source capture custody')
    matches = [r for r in (json.loads(line) for line in Path(s['capture_path']).read_text().splitlines())
               if r['decision'] == 13 and r['floor'] == 33 and r['seed'] == '610081002']
    require(len(matches) == 1 and matches[0] == load(s['public_row_path']), 'root is not exact capture extraction')
    require(s['canary_k'] == [0, 1] and s['evaluation_k'] == list(range(2, 64))
            and s['continuation_simulations'] == 10000 and s['maximum_decisions'] == 1000,
            'specification scope changed')
    return f, t, s


def environment(f):
    return {'HOME': '/home/philippherrmann', 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE', 'OPENBLAS_NUM_THREADS': '1',
            'MKL_NUM_THREADS': '1', 'STS_EXECUTABLE_GIT_SHA': f['source_sha']}


def prefix(stage, k):
    require(stage in ('check', 'canary', 'evaluation'), 'unknown stage')
    require((stage == 'check' and k is None) or (stage == 'canary' and k in (0, 1))
            or (stage == 'evaluation' and k in range(2, 64)), 'unallocated stage/future')
    return RAW / ('check' if stage == 'check' else f'{stage}-{k:02d}')


def command(f, stage, k):
    cmd = ['bash', 'tools/seed_guard.sh', f['binary'], f['specification'], stage]
    return cmd if stage == 'check' else cmd + [str(k)]


def authorization(path, digest, freeze_sha, tools_sha):
    require(path is not None and digest is not None and sha(path) == digest, 'missing/changed affordability authorization')
    a = load(path)
    require(a['schema'] == 'champ_d13_evaluation_authorization_v1'
        and a['build_freeze_sha256'] == freeze_sha and a['tools_freeze_sha256'] == tools_sha,
        'authorization custody mismatch')
    require(a['canary_contract_pass'] is True and a['cost_fits_reserve'] is True
        and a['criterion'] == 'contract_and_cost_only' and a['evaluation_k'] == list(range(2, 64)),
        'authorization requires exact contract/cost decision')
    require(sha(a['canary_report']) == a['canary_report_sha256'], 'canary report changed')
    report = load(a['canary_report'])
    require(report['status'] == 'CANARY_CONTRACT_PASS' and report['build_freeze_sha256'] == freeze_sha
        and report['tools_freeze_sha256'] == tools_sha and report['pairs'] == 2, 'canary report not eligible')
    require(a['approved_epoch'] >= report['latest_invocation_finished_epoch'], 'cost approval predates canaries')
    for item in report['inputs']:
        require(sha(item['path']) == item['sha256'], 'canary evidence changed')
    return a


def main():
    ap = argparse.ArgumentParser()
    for field in ('freeze', 'tools'):
        ap.add_argument('--' + field, required=True, type=Path)
        ap.add_argument('--' + field + '-sha256', required=True)
    ap.add_argument('--stage', choices=('check', 'canary', 'evaluation'), required=True)
    ap.add_argument('--k', type=int)
    ap.add_argument('--authorization', type=Path)
    ap.add_argument('--authorization-sha256')
    args = ap.parse_args()
    f, _, _ = custody(args.freeze, args.freeze_sha256, args.tools, args.tools_sha256)
    p = prefix(args.stage, args.k)
    if args.stage == 'evaluation':
        authorization(args.authorization, args.authorization_sha256, args.freeze_sha256, args.tools_sha256)
    else:
        require(args.authorization is None and args.authorization_sha256 is None, 'unexpected authorization')
    if args.stage != 'check':
        # Reuse the exact output validator; this import cannot launch a process.
        from analyze_champ_probe import invocation
        invocation(f, args.freeze_sha256, args.tools_sha256, 'check', None)
    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / '.lane.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list(RAW.glob(p.name + '.*')), 'refusing prior output/allocation')
        paths = {suffix: Path(str(p) + '.' + suffix) for suffix in ('receipt.json', 'jsonl', 'stderr.log')}
        receipt = {'schema': 'champ_d13_invocation_v1', 'stage': args.stage, 'k': args.k,
            'freeze': str(args.freeze.resolve()), 'freeze_sha256': args.freeze_sha256,
            'tools': str(args.tools.resolve()), 'tools_sha256': args.tools_sha256,
            'source_sha': f['source_sha'], 'binary_sha256': f['binary_sha256'], 'script_sha256': sha(__file__),
            'command': command(f, args.stage, args.k), 'environment': environment(f),
            'authorization': str(args.authorization.resolve()) if args.authorization else None,
            'authorization_sha256': args.authorization_sha256,
            'started_epoch': time.time(), 'status': 'running'}
        with paths['receipt.json'].open('x') as stream:
            json.dump(receipt, stream, indent=2)
        start = time.monotonic()
        try:
            with paths['jsonl'].open('x') as out, paths['stderr.log'].open('x') as error:
                done = subprocess.run(receipt['command'], cwd=ROOT, env=receipt['environment'], stdout=out,
                    stderr=error, timeout=60 if args.stage == 'check' else f['timeout_seconds_per_pair'])
            receipt.update(exit_code=done.returncode, status='completed' if done.returncode == 0 else 'failed')
        except subprocess.TimeoutExpired:
            receipt.update(exit_code=124, status='timeout')
        except Exception as error:
            receipt.update(exit_code=125, status='launcher_error', error=repr(error))
        receipt.update(wall_seconds=time.monotonic() - start, finished_epoch=time.time())
        receipt['outputs'] = {suffix: {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
            for suffix, path in paths.items() if suffix != 'receipt.json' and path.exists()}
        paths['receipt.json'].write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ('stage', 'k', 'status', 'exit_code', 'wall_seconds')}))
    return receipt['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
