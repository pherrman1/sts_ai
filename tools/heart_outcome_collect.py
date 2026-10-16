#!/usr/bin/env python3
"""Heart-outcome corpus setup/qualification and fixed native Claude-worker execution.

No provider API, fit, TEST opener, or retry. Worker outputs remain split-separated.
Only complete integrity-checked real trajectories can supply value labels.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import time

from heart_distill_native_plan import scientific_environment

FIRST = 110180000
COUNT = 1800
WORKERS = 45
STUDENT_C = 'eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')


def assignments():
    return [{'seed': FIRST+i, 'worker': i % WORKERS,
             'split': 'train' if i < 1080 else 'validation' if i < 1440 else 'test'}
            for i in range(COUNT)]


def verify_bundle(bundle):
    manifest = json.loads((bundle / 'bundle.json').read_text())
    if manifest['files'].get('studentc.bin') != STUDENT_C:
        raise ValueError('not exact Arm C')
    for name, digest in manifest['files'].items():
        if sha(bundle / name) != digest:
            raise ValueError('bundle changed: ' + name)
    return manifest


def prepare(repo, binary, student, out):
    if sha(student) != STUDENT_C:
        raise ValueError('wrong Arm C weights')
    source = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip():
        raise ValueError('freeze requires clean reviewed source')
    out.mkdir(parents=True, exist_ok=False)
    bundle = out / 'bundle'
    bundle.mkdir()
    shutil.copy2(binary, bundle / 'one_combat')
    shutil.copy2(student, bundle / 'studentc.bin')
    shutil.copy2(repo / 'tools/seed_guard.sh', bundle / 'seed_guard.sh')
    paths = subprocess.check_output(['git', '-C', str(repo), 'ls-files', 'models', 'selfplay/models'], text=True).splitlines()
    for rel in paths:
        target = bundle / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / rel, target)
    for name in ('heart_outcome_collect.py', 'heart_distill_native_plan.py', 'run_heart_distill_pilot.py'):
        shutil.copy2(repo / 'tools' / name, bundle / name)
    env = scientific_environment(repo)
    env['STS_EXECUTABLE_GIT_SHA'] = source
    write(bundle/'environment.json', env)
    files = ['one_combat', 'studentc.bin', 'seed_guard.sh', 'heart_outcome_collect.py',
             'heart_distill_native_plan.py', 'run_heart_distill_pilot.py', 'environment.json', *paths]
    write(bundle / 'bundle.json', {'sourceSha': source, 'files': {p: sha(bundle / p) for p in files}})
    write(out / 'plan.json', {'schema': 'heart-outcome-plan-v1', 'sourceSha': source,
        'state': 'PREPARED_NOT_DISPATCHED', 'bundleSha256': sha(bundle / 'bundle.json'),
        'environment': env, 'sources': assignments(), 'workers': 45, 'processesPerWorker': 4,
        'sourceSeconds': 3600, 'campaignSeconds': 21600,
        'canaries': {'local': [110179994, 110179995], 'cloud': [110179996, 110179997]},
        'trainingGate': {'trainWins': 20, 'trainLosses': 20, 'validationWins': 5, 'validationLosses': 5},
        'testCustody': 'sealed archive only, no coordinator inspection or fitting',
        'beforeDispatch': ['independent source review', 'completion-anchored independent canary review',
                           'verified durable export roundtrip', 'one global activation/deadline'],
        'noRetry': True, 'noNativeIntegration': True, 'noRlLoop': True})


def verify_plan(plan_path, bundle):
    plan = json.loads(plan_path.read_text())
    manifest = verify_bundle(bundle)
    if (plan['sources'] != assignments() or plan['bundleSha256'] != sha(bundle / 'bundle.json')
            or plan['sourceSha'] != manifest['sourceSha']
            or plan['environment'] != json.loads((bundle/'environment.json').read_text())):
        raise ValueError('plan assignment/bundle binding changed')
    return plan


def trajectory(path, seed, source, capture=True):
    """No state receives a label until the final validated terminal footer exists."""
    if path.stat().st_size > 64*1024**2:
        raise ValueError('trajectory exceeds64MiB cap')
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if len(rows) < 2:
        raise ValueError('missing completed trajectory')
    header, footer = rows[0], rows[-1]
    if (header.get('schema') != 'heart-trajectory-v1' or header.get('type') != 'header'
            or header.get('seed') != seed or header.get('producerSha') != source
            or header.get('objective') != 'heart' or header.get('ascension') != 20
            or header.get('combatSimulations') != 10000 or header.get('collectKeys') is not True
            or header.get('stopAfterAct') != 0 or header.get('capture') is not capture
            or header.get('recordSchema') != 'heart1-public-record-v2'
            or header.get('recordPublicParityQualified') is not False):
        raise ValueError('wrong trajectory producer/objective/schema')
    if (footer.get('type') != 'outcome' or footer.get('complete') is not True
            or footer.get('integrityPassed') is not True or type(footer.get('label')) is not int
            or footer['label'] not in (0, 1) or type(footer.get('heartKilled')) is not bool
            or footer['heartKilled'] != bool(footer['label'])
            or (footer['label'] == 1 and footer.get('finalAct') != 4)):
        raise ValueError('not an integrity-checked full-run Heart outcome')
    supported = 0
    states = rows[1:-1]
    if len(states) > 2048:
        raise ValueError('too many observations')
    for i, state in enumerate(states):
        if (state.get('type') != 'state' or state.get('index') != i
                or state.get('origin') != 'real-run-driver' or type(state.get('supported')) is not bool):
            raise ValueError('non-trajectory/duplicate/counterfactual state')
        if state['supported']:
            record = state.get('record')
            if (not isinstance(record, dict) or record.get('screen_state') != state.get('screen')
                    or any(k in record for k in ('seed', 'rng', 'target', 'label', 'outcome'))):
                raise ValueError('invalid public record or label leakage')
            supported += 1
        elif not state.get('reason') or 'record' in state:
            raise ValueError('unsupported boundary is not accounted')
    if (footer.get('states') != len(states) or footer.get('supportedStates') != supported
            or (capture and (not states or supported / len(states) < .8))
            or (not capture and states)):
        raise ValueError('incomplete trajectory coverage/counts')
    return header, footer, states


def unit(plan, bundle, out, seed, tag, capture=True, seconds=3600):
    base = out / tag
    write(base.with_suffix('.started.json'), {'seed': seed, 'capture': capture, 'sourceSha': plan['sourceSha']})
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ.get('PATH', '/usr/bin:/bin'), **plan['environment']}
    env.update(STS_OOC_DECISION_TRACE=str(base.with_suffix('.trace.jsonl')),
               STS_OOC_MCTS_TRACE=str(base.with_suffix('.mcts.csv')))
    cmd = ['bash', str(bundle / 'seed_guard.sh'), str(bundle / 'one_combat'),
           'heartoutcomegen', '1', str(seed), str(base.with_suffix('.states.jsonl')), 'on' if capture else 'off']
    started = time.monotonic()
    with base.with_suffix('.log').open('x') as log:
        child = subprocess.Popen(cmd, cwd=bundle, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            # Only our live owned Popen session is signalled; no stale shared claims.
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait()
            rc = 124
    receipt = {'seed': seed, 'returncode': rc, 'seconds': time.monotonic()-started,
               'sourceSha': plan['sourceSha'], 'binarySha256': sha(bundle / 'one_combat'),
               'host': os.uname().nodename, 'command': cmd, 'environment': env}
    if rc == 0:
        header, footer, _ = trajectory(base.with_suffix('.states.jsonl'), seed, plan['sourceSha'], capture)
        support = [json.loads(l) for l in base.with_suffix('.mcts.csv.support.jsonl').read_text().splitlines()]
        if len(support) != 1 or support[0]['seed'] != seed:
            raise ValueError('missing/cross-source model-use telemetry')
        s = support[0]
        if (s['heart1_prior_nodes'] <= 0 or s['heart1_leaf_steps'] <= 0 or s['prior_leaf_steps'] != 0
                or s['heart1_leaf_steps'] / (s['heart1_leaf_steps']+s['heart1_leaf_fallbacks']) < .9):
            raise ValueError('Arm C prior/rollout scoring not qualified')
        receipt.update(states=footer['states'], supportedStates=footer['supportedStates'],
                       policy=header['policy'], modelUse=s)
    receipt['files'] = {p.name: sha(p) for p in sorted(out.glob(tag+'.*')) if p.is_file()}
    write(base.with_suffix('.receipt.json'), receipt)
    return receipt


def canary(plan_path, bundle, out, role):
    plan = verify_plan(plan_path, bundle)
    out.mkdir(parents=True, exist_ok=False)
    first, second = plan['canaries'][role]
    receipts = []
    for seed, capture, tag in ((first, False, 'off'), (first, True, 'on'), (second, True, 'second')):
        r = unit(plan, bundle, out, seed, tag, capture)
        receipts.append(r)
        if r['returncode']:
            raise ValueError('canary failed; no retry or cohort dispatch')
    if (out/'off.trace.jsonl').read_bytes() != (out/'on.trace.jsonl').read_bytes():
        raise ValueError('capture changed actual action/state trace')
    a = trajectory(out/'off.states.jsonl', first, plan['sourceSha'], False)[1]
    b = trajectory(out/'on.states.jsonl', first, plan['sourceSha'])[1]
    if any(a[k] != b[k] for k in ('label','heartKilled','finalFloor','finalAct','finalHp')):
        raise ValueError('capture changed run outcome')
    write(out/'canary.json', {'verdict': 'PASS', 'role': role, 'planSha256': sha(plan_path),
        'bundleSha256': sha(bundle/'bundle.json'), 'traceParity': True, 'outcomeParity': True,
        'files': {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}})


def activate(plan_path, bundle, approval, out):
    plan = verify_plan(plan_path, bundle)
    review = json.loads(approval.read_text())
    canary_path = approval.parent/'canary.json'
    export_path = approval.parent/'export-roundtrip.json'
    qualified = json.loads(canary_path.read_text())
    export = json.loads(export_path.read_text())
    if (review.get('verdict') != 'PASS' or review.get('sourceSha') != plan['sourceSha']
            or review.get('planSha256') != sha(plan_path)
            or review.get('bundleSha256') != sha(bundle/'bundle.json')
            or review.get('durableExportRoundtrip') is not True
            or review.get('canarySha256') != sha(canary_path)
            or review.get('exportReceiptSha256') != sha(export_path)
            or qualified.get('verdict') != 'PASS' or qualified.get('role') != 'cloud'
            or qualified.get('planSha256') != sha(plan_path)
            or qualified.get('bundleSha256') != sha(bundle/'bundle.json')
            or export.get('bytes', 0) < 256*1024**2 or export.get('sourceHost') == export.get('destinationHost')
            or not export.get('sourceSha256') or export.get('sourceSha256') != export.get('returnedSha256')):
        raise ValueError('missing exact reviewed canary/export qualification')
    for name, digest in qualified['files'].items():
        if sha(approval.parent/name) != digest:
            raise ValueError('completion-anchored canary artifact changed')
    if out.resolve() != (plan_path.parent/'activation.json').resolve():
        raise ValueError('activation must use the one fixed coordinator path')
    started = time.time()
    write(plan_path.parent/'COHORT-STARTED.json', {'planSha256': sha(plan_path), 'startedUtc': started})
    write(out, {'planSha256': sha(plan_path), 'bundleSha256': sha(bundle/'bundle.json'),
        'approvalSha256': sha(approval), 'startedUtc': started, 'deadlineUtc': started+21600})


def worker(plan_path, bundle, activation, out, worker_id):
    plan = verify_plan(plan_path, bundle)
    act = json.loads(activation.read_text())
    if (act.get('planSha256') != sha(plan_path) or act.get('bundleSha256') != sha(bundle/'bundle.json')
            or act['deadlineUtc']-act['startedUtc'] != 21600 or time.time() >= act['deadlineUtc']):
        raise ValueError('wrong/expired global activation')
    if type(worker_id) is not int or not 0 <= worker_id < 45:
        raise ValueError('worker id must be0..44')
    quota = Path('/sys/fs/cgroup/cpu.max')
    quota_text = quota.read_text().strip() if quota.exists() else 'max 100000'
    available = len(os.sched_getaffinity(0))
    q, period = quota_text.split()
    if available < 4 or (q != 'max' and int(q)/int(period) < 4):
        raise ValueError('worker has fewer than four CPU-equivalents')
    out.mkdir(parents=True, exist_ok=False)
    write(out/'worker-started.json', {'worker': worker_id, 'planSha256': sha(plan_path),
        'activationSha256': sha(activation), 'cpuMax': quota_text, 'affinity': sorted(os.sched_getaffinity(0))})
    def run(entry):
        remaining = act['deadlineUtc']-time.time()
        if remaining <= 0:
            raise TimeoutError('global cohort deadline expired')
        split_dir = out / entry['split']
        split_dir.mkdir(exist_ok=True)
        return unit(plan, bundle, split_dir, entry['seed'], 'seed-'+str(entry['seed']),
                    seconds=min(3600, remaining))
    entries = [s for s in plan['sources'] if s['worker'] == worker_id]
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(run, entries))
    # No outcomes or content summaries of TEST leave its sealed archive.
    exports = {}
    for split in ('train','validation','test'):
        name = ('SEALED-' if split == 'test' else '') + split + '.tar.gz'
        with tarfile.open(out/name, 'x:gz') as tar:
            tar.add(out/split, arcname=split)
        exports[name] = sha(out/name)
    write(out/'worker-receipt.json', {'worker': worker_id, 'planSha256': sha(plan_path),
        'activationSha256': sha(activation), 'sources': [r['seed'] for r in receipts],
        'returncodes': [r['returncode'] for r in receipts], 'archives': exports,
        'complete': all(r['returncode'] == 0 for r in receipts)})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prepare','canary','activate','worker'))
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    for name in ('binary','student','plan','bundle','out','approval','activation'):
        p.add_argument('--'+name, type=Path)
    p.add_argument('--role', choices=('local','cloud'), default='local')
    p.add_argument('--worker', type=int)
    a = p.parse_args()
    required = {'prepare': ('binary','student','out'), 'canary': ('plan','bundle','out'),
                'activate': ('plan','bundle','approval','out'),
                'worker': ('plan','bundle','activation','out','worker')}
    for key in required[a.command]:
        if getattr(a,key) is None:
            p.error('--'+key+' is required for '+a.command)
    if a.command == 'prepare': prepare(a.repo, a.binary, a.student, a.out)
    elif a.command == 'canary': canary(a.plan, a.bundle.resolve(), a.out.resolve(), a.role)
    elif a.command == 'activate': activate(a.plan, a.bundle, a.approval, a.out)
    else: worker(a.plan, a.bundle.resolve(), a.activation, a.out.resolve(), a.worker)


if __name__ == '__main__':
    main()
