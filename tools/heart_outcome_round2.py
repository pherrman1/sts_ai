#!/usr/bin/env python3
"""Second observed Heart-outcome cohort: same fixed §497 teacher, plus a root trace.

Each captured source additionally writes `STS_OOC_MCTS_ROOT_TRACE`: one row per live
OOC MCTS root with complete candidate keys, priors, visits/visit shares and Q, the
public record and a replay-only native snapshot (hidden state, never a model input).
Splits are TRAIN/VALIDATION development data and a sealed CONFIRM cohort. The §497
tool stays unchanged (its assignments are pinned by the §497 importer).
No provider API, fit, CONFIRM opener or retry.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import time

import numpy as np

from heart_distill_native_plan import scientific_environment
from heart_outcome_collect import STUDENT_C, runtime_contract, sha, trajectory, write

SCHEMA = 'heart-outcome-round2-plan-v1'
FIRST = 111101000
CANARIES = {'local': [111100000, 111100001], 'cloud': [111100002, 111100003]}
SPLITS = ('train', 'validation', 'confirm')
SOURCE_SECONDS = 3600
CAMPAIGN_SECONDS = 21600
ROOT_TRACE_CAP = 256*1024**2


def assignments(workers, per_worker):
    """Contiguous seed blocks per split; within a split, sources go round-robin to workers."""
    out, seed = [], FIRST
    for split, count in zip(SPLITS, per_worker):
        for i in range(workers*count):
            out.append({'seed': seed, 'worker': i % workers, 'split': split})
            seed += 1
    return out


def sibling_env(every):
    """§494 sibling rollout labels (64 Arm C rollout3 repeats per root child) on every Nth searched root; 0 = off."""
    if not every:
        return {}
    return {'STS_OOC_SIBLING_EVERY': str(every), 'STS_OOC_SIBLING_REPEATS': '64', 'STS_OOC_SIBLING_LONG': '0',
            'STS_OOC_SIBLING_MAX_DEPTH': '1', 'STS_OOC_SIBLING_MAX_LEAVES': '64'}


def verify_bundle(bundle):
    manifest = json.loads((bundle/'bundle.json').read_text())
    if manifest.get('runtime') != {'python': platform.python_version(), 'numpy': np.__version__}:
        raise ValueError('bundle Python/NumPy runtime changed')
    if manifest['files'].get('studentc.bin') != STUDENT_C:
        raise ValueError('not exact Arm C')
    for name, digest in manifest['files'].items():
        if sha(bundle/name) != digest:
            raise ValueError('bundle changed: ' + name)
    return manifest


TOOLS = ('heart_outcome_round2.py', 'heart_outcome_collect.py', 'heart_distill_native_plan.py',
         'run_heart_distill_pilot.py', 'heart_record_encoder.py')


def prepare(repo, binary, student, out, workers, per_worker, sibling_every=0):
    if sha(student) != STUDENT_C:
        raise ValueError('wrong Arm C weights')
    if len(per_worker) != 3 or min(per_worker) < 1 or workers < 1 or sibling_every < 0:
        raise ValueError('need a positive train/validation/confirm count per worker')
    source = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip():
        raise ValueError('freeze requires clean reviewed source')
    out.mkdir(parents=True, exist_ok=False)
    bundle = out/'bundle'
    bundle.mkdir()
    shutil.copy2(binary, bundle/'one_combat')
    shutil.copy2(student, bundle/'studentc.bin')
    shutil.copy2(repo/'tools/seed_guard.sh', bundle/'seed_guard.sh')
    paths = subprocess.check_output(['git', '-C', str(repo), 'ls-files', 'models', 'selfplay/models'], text=True).splitlines()
    for rel in paths:
        target = bundle/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo/rel, target)
    for name in TOOLS:
        shutil.copy2(repo/'tools'/name, bundle/name)
    env = scientific_environment(repo)
    env['STS_EXECUTABLE_GIT_SHA'] = source
    write(bundle/'environment.json', env)
    files = ['one_combat', 'studentc.bin', 'seed_guard.sh', *TOOLS, 'environment.json', *paths]
    write(bundle/'bundle.json', {'sourceSha': source, 'runtime': {'python': platform.python_version(), 'numpy': np.__version__},
        'files': {p: sha(bundle/p) for p in files}})
    write(out/'plan.json', {'schema': SCHEMA, 'sourceSha': source,
        'state': 'PREPARED_NOT_DISPATCHED', 'bundleSha256': sha(bundle/'bundle.json'),
        'environment': env, 'workers': workers, 'perWorker': dict(zip(SPLITS, per_worker)),
        'sources': assignments(workers, per_worker), 'processesPerWorker': 4,
        'sourceSeconds': SOURCE_SECONDS, 'campaignSeconds': CAMPAIGN_SECONDS, 'canaries': CANARIES,
        'rootTrace': 'ooc-root-trace-v1: candidate keys, priors, visits, Q, public record, replay-only native snapshot',
        'sibling': sibling_env(sibling_every),
        'confirmCustody': 'sealed archive only, no inspection or fitting before candidate selection is frozen',
        'beforeDispatch': ['independent source review', 'completion-anchored independent canary review',
                           'durable export check from a different container', 'one global activation/deadline'],
        'noRetry': True, 'noNativeIntegration': True, 'noRlLoop': True})


def verify_plan(plan_path, bundle):
    plan = json.loads(plan_path.read_text())
    manifest = verify_bundle(bundle)
    per_worker = [plan['perWorker'][s] for s in SPLITS]
    if (plan.get('schema') != SCHEMA or plan['sources'] != assignments(plan['workers'], per_worker)
            or plan['bundleSha256'] != sha(bundle/'bundle.json') or plan['sourceSha'] != manifest['sourceSha']
            or plan['environment'] != json.loads((bundle/'environment.json').read_text())):
        raise ValueError('plan assignment/bundle binding changed')
    return plan


HYPOTHETICAL_INDEX = 1 << 12


def root_trace(path, actions_path, seed):
    """Every live root has one row aligned with the executed-action trace; returns coverage counts."""
    if path.stat().st_size > ROOT_TRACE_CAP:
        raise ValueError('root trace exceeds cap')
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    actions = [json.loads(line) for line in actions_path.read_text().splitlines()]
    if not rows or len(rows) != len(actions):
        raise ValueError('root trace not aligned with action trace')
    counts = {'roots': len(rows), 'searched': 0, 'snapshots': 0, 'records': 0, 'snapshotErrorsByScreen': {}}
    previous, base, seen = -1, -1, set()
    for row, action in zip(rows, actions):
        index = row.get('decisionIndex')
        # Match and Keep values each offered card with a hypothetical root indexed (real index << 12) ^ card bits
        # (run_driver.cpp matchAndKeepPolicyStep); real indices stay below 1 << 12 and increase strictly.
        hypothetical = type(index) is int and index >= HYPOTHETICAL_INDEX
        if (row.get('schema') != 'ooc-root-trace-v1' or row.get('seed') != seed
                or type(index) is not int or index in seen
                or (index >> 12 if hypothetical else index) <= previous
                or index != action['decisionIndex'] or row.get('selectedKey') != action['selectedKey']
                or row.get('executed') != action['executed'] or row.get('selectedId') != action['selectedId']):
            raise ValueError('root trace row does not match the live decision')
        seen.add(index)
        if hypothetical:
            counts['hypotheticalRoots'] = counts.get('hypotheticalRoots', 0)+1
            base = max(base, index >> 12)
        elif index <= base:
            raise ValueError('root trace row does not match the live decision')
        else:
            previous = index
        keys = [a['key'] for a in row['rootActions']]
        if len(set(keys)) != len(keys):
            raise ValueError('duplicate root candidate identity')
        if row['rootActions'] and not row['singletonBypass']:
            counts['searched'] += 1
            visits = sum(a['visits'] for a in row['rootActions'])
            if visits <= 0 or abs(sum(a['visitShare'] for a in row['rootActions'])-1) > 1e-9:
                raise ValueError('root visit distribution invalid')
            if row['executed'] and row['selectedKey'] not in keys:
                raise ValueError('selected action missing from root candidates')
        if isinstance(row.get('snapshot'), dict):
            counts['snapshots'] += 1
        elif not row.get('snapshotError'):
            raise ValueError('missing snapshot is not accounted')
        else:
            screen = str(row.get('screen'))
            counts['snapshotErrorsByScreen'][screen] = counts['snapshotErrorsByScreen'].get(screen, 0)+1
        if isinstance(row.get('record'), dict):
            if any(k in row['record'] for k in ('seed', 'rng', 'target', 'label', 'outcome')):
                raise ValueError('root public record leaks hidden data')
            counts['records'] += 1
        elif not row.get('recordError'):
            raise ValueError('missing root record is not accounted')
    return counts


def unit(plan, bundle, out, seed, tag, capture=True, seconds=SOURCE_SECONDS, expected_policy=None):
    base = out/tag
    write(base.with_suffix('.started.json'), {'seed': seed, 'capture': capture, 'sourceSha': plan['sourceSha']})
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ.get('PATH', '/usr/bin:/bin'), **plan['environment']}
    env.update(STS_OOC_DECISION_TRACE=str(base.with_suffix('.trace.jsonl')),
               STS_OOC_MCTS_TRACE=str(base.with_suffix('.mcts.csv')))
    if capture:
        env['STS_OOC_MCTS_ROOT_TRACE'] = str(base.with_suffix('.roots.jsonl'))
        if plan.get('sibling'):
            env.update(plan['sibling'], STS_OOC_SIBLING_CAPTURE=str(base.with_suffix('.sib.jsonl')))
    cmd = ['bash', str(bundle/'seed_guard.sh'), str(bundle/'one_combat'),
           'heartoutcomegen', '1', str(seed), str(base.with_suffix('.states.jsonl')), 'on' if capture else 'off']
    started = time.monotonic()
    with base.with_suffix('.log').open('x') as log:
        child = subprocess.Popen(cmd, cwd=bundle, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid, 15)
            except ProcessLookupError: pass
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid, 9)
                except ProcessLookupError: pass
                child.wait()
            rc = 124
    receipt = {'seed': seed, 'returncode': rc, 'processReturncode': rc, 'seconds': time.monotonic()-started,
               'sourceSha': plan['sourceSha'], 'binarySha256': sha(bundle/'one_combat'),
               'host': os.uname().nodename, 'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'command': cmd, 'environment': env}
    if rc == 0:
        try:
            header, footer, _ = trajectory(base.with_suffix('.states.jsonl'), seed, plan['sourceSha'], capture)
            if header.get('rootTrace') is not capture:
                raise ValueError('root trace setting differs from capture')
            if not isinstance(header.get('policy'), dict) or not header['policy']:
                raise ValueError('missing effective teacher policy')
            if expected_policy is not None and header['policy'] != expected_policy:
                raise ValueError('effective teacher policy changed')
            support = [json.loads(l) for l in base.with_suffix('.mcts.csv.support.jsonl').read_text().splitlines()]
            if len(support) != 1:
                raise ValueError('missing/cross-source model-use telemetry')
            contract = runtime_contract(bundle, base.with_suffix('.log').read_text(), support[0], seed)
            receipt.update(states=footer['states'], supportedStates=footer['supportedStates'],
                           policy=header['policy'], modelUse=contract)
            if capture:
                receipt['roots'] = root_trace(base.with_suffix('.roots.jsonl'),
                                              base.with_suffix('.mcts.csv.actions.jsonl'), seed)
        except (ValueError, KeyError, TypeError, OSError, StopIteration) as error:
            # A normally exited but invalid producer is censored, never labeled a death.
            receipt.update(returncode=65, contractError=str(error))
    receipt['files'] = {p.name: sha(p) for p in sorted(out.glob(tag+'.*')) if p.is_file()}
    write(base.with_suffix('.receipt.json'), receipt)
    return receipt


def canary(plan_path, bundle, out, role):
    plan = verify_plan(plan_path, bundle)
    out.mkdir(parents=True, exist_ok=False)
    first, second = plan['canaries'][role]
    receipts = []
    for seed, capture, tag in ((first, False, 'off'), (first, True, 'on'), (second, True, 'second')):
        r = unit(plan, bundle, out, seed, tag, capture,
                 expected_policy=receipts[0]['policy'] if receipts else None)
        receipts.append(r)
        if r['returncode']:
            raise ValueError('canary failed; no retry or cohort dispatch')
    # Root trace and snapshots are observation only: actual play must be byte-identical.
    for suffix in ('.trace.jsonl', '.mcts.csv.actions.jsonl'):
        if (out/('off'+suffix)).read_bytes() != (out/('on'+suffix)).read_bytes():
            raise ValueError('capture changed actual action/state trace')
    a = trajectory(out/'off.states.jsonl', first, plan['sourceSha'], False)[1]
    b = trajectory(out/'on.states.jsonl', first, plan['sourceSha'])[1]
    if any(a[k] != b[k] for k in ('label', 'heartKilled', 'finalFloor', 'finalAct', 'finalHp')):
        raise ValueError('capture changed run outcome')
    write(out/'canary.json', {'verdict': 'PASS', 'role': role, 'planSha256': sha(plan_path),
        'bundleSha256': sha(bundle/'bundle.json'), 'traceParity': True, 'actionParity': True,
        'outcomeParity': True, 'policy': receipts[0]['policy'],
        'roots': {'on': receipts[1]['roots'], 'second': receipts[2]['roots']},
        'seconds': {tag: r['seconds'] for tag, r in zip(('off', 'on', 'second'), receipts)},
        'files': {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}})


def qualification(plan_path, bundle, approval):
    plan = verify_plan(plan_path, bundle)
    review = json.loads(approval.read_text())
    canary_path = approval.parent/'canary.json'
    export_path = approval.parent/'export-check.json'
    qualified = json.loads(canary_path.read_text())
    export = json.loads(export_path.read_text())
    if (review.get('verdict') != 'PASS' or review.get('sourceSha') != plan['sourceSha']
            or review.get('planSha256') != sha(plan_path)
            or review.get('bundleSha256') != sha(bundle/'bundle.json')
            or review.get('canarySha256') != sha(canary_path)
            or review.get('exportCheckSha256') != sha(export_path)
            or qualified.get('verdict') != 'PASS' or qualified.get('role') != 'cloud'
            or qualified.get('planSha256') != sha(plan_path)
            or qualified.get('bundleSha256') != sha(bundle/'bundle.json')
            or not isinstance(qualified.get('policy'), dict) or not qualified['policy']
            or qualified.get('actionParity') is not True
            or export.get('bytes', 0) < 256*1024**2 or not export.get('writerBootId')
            or export.get('writerBootId') == export.get('readerBootId')
            or not export.get('writtenSha256') or export.get('writtenSha256') != export.get('readSha256')):
        raise ValueError('missing exact reviewed canary/export qualification')
    for name, digest in qualified['files'].items():
        if sha(approval.parent/name) != digest:
            raise ValueError('completion-anchored canary artifact changed')
    return qualified


def activate(plan_path, bundle, approval, out):
    qualified = qualification(plan_path, bundle, approval)
    approval_rel = str(approval.resolve().relative_to(plan_path.parent.resolve()))
    if out.resolve() != (plan_path.parent/'activation.json').resolve():
        raise ValueError('activation must use the one fixed coordinator path')
    started = time.time()
    write(plan_path.parent/'COHORT-STARTED.json', {'planSha256': sha(plan_path), 'startedUtc': started})
    write(out, {'planSha256': sha(plan_path), 'bundleSha256': sha(bundle/'bundle.json'),
        'approvalSha256': sha(approval), 'approvalRelativePath': approval_rel,
        'latchSha256': sha(plan_path.parent/'COHORT-STARTED.json'), 'policy': qualified['policy'],
        'startedUtc': started, 'deadlineUtc': started+CAMPAIGN_SECONDS})


def worker(plan_path, bundle, activation, out, worker_id, activation_sha, half=None):
    """Runs this worker's sources; `half` (0/1) runs only entries[half::2] for a lost-worker rerun."""
    plan = verify_plan(plan_path, bundle)
    if not activation_sha or sha(activation) != activation_sha:
        raise ValueError('activation differs from coordinator approved identity')
    act = json.loads(activation.read_text())
    if (act.get('planSha256') != sha(plan_path) or act.get('bundleSha256') != sha(bundle/'bundle.json')
            or act['deadlineUtc']-act['startedUtc'] != CAMPAIGN_SECONDS
            or not act['startedUtc'] <= time.time() < act['deadlineUtc']):
        raise ValueError('wrong/expired global activation')
    approval = activation.parent/act['approvalRelativePath']
    approval.resolve().relative_to(activation.parent.resolve())
    qualified = qualification(plan_path, bundle, approval)
    latch = activation.parent/'COHORT-STARTED.json'
    if (sha(approval) != act['approvalSha256'] or sha(latch) != act['latchSha256']
            or qualified['policy'] != act['policy']
            or json.loads(latch.read_text()) != {'planSha256': sha(plan_path), 'startedUtc': act['startedUtc']}):
        raise ValueError('activation qualification chain changed')
    if type(worker_id) is not int or not 0 <= worker_id < plan['workers'] or half not in (None, 0, 1):
        raise ValueError('worker id outside plan or bad half')
    quota = Path('/sys/fs/cgroup/cpu.max')
    quota_text = quota.read_text().strip() if quota.exists() else 'max 100000'
    q, period = quota_text.split()
    if len(os.sched_getaffinity(0)) < 4 or (q != 'max' and int(q)/int(period) < 4):
        raise ValueError('worker has fewer than four CPU-equivalents')
    out.mkdir(parents=True, exist_ok=False)
    write(out/'worker-started.json', {'worker': worker_id, 'half': half, 'planSha256': sha(plan_path),
        'activationSha256': sha(activation), 'cpuMax': quota_text, 'affinity': sorted(os.sched_getaffinity(0)),
        'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
    for split in SPLITS:
        (out/split).mkdir()

    def run(entry):
        seed = entry['seed']
        split_dir = out/entry['split']
        try:
            remaining = act['deadlineUtc']-time.time()
            if remaining <= 0:
                raise TimeoutError('global cohort deadline expired; source not launched')
            return unit(plan, bundle, split_dir, seed, 'seed-'+str(seed),
                        seconds=min(SOURCE_SECONDS, remaining), expected_policy=act['policy'])
        except Exception as error:
            failed = {'seed': seed, 'returncode': 70, 'collectionError': str(error)}
            write(split_dir/('seed-'+str(seed)+'.collection-failure.json'), failed)
            return failed
    entries = [s for s in plan['sources'] if s['worker'] == worker_id]
    if half is not None:
        entries = entries[half::2]
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(run, entries))
    # No outcomes or content summaries of CONFIRM leave its sealed archive.
    exports = {}
    for split in SPLITS:
        name = ('SEALED-' if split == 'confirm' else '') + split + '.tar.gz'
        with tarfile.open(out/name, 'x:gz') as tar:
            tar.add(out/split, arcname=split)
        exports[name] = sha(out/name)
    write(out/'worker-receipt.json', {'worker': worker_id, 'half': half, 'planSha256': sha(plan_path),
        'activationSha256': sha(activation), 'sources': [r['seed'] for r in receipts],
        'returncodes': [r['returncode'] for r in receipts], 'archives': exports,
        'complete': all(r['returncode'] == 0 for r in receipts)})


ROOT_TRACE_MISMATCH = 'root trace row does not match the live decision'


def requalify(receipt, roots, actions, seed):
    """True for a source censored only by the pre-4473ce6 root-trace order check (Match and Keep roots).

    root_trace is the last check in unit(), so states/policy/modelUse being recorded means every
    earlier contract check passed; the archived trace is re-validated with the corrected rule."""
    if (receipt.get('returncode') != 65 or receipt.get('processReturncode') != 0
            or receipt.get('contractError') != ROOT_TRACE_MISMATCH
            or not all(k in receipt for k in ('states', 'policy', 'modelUse'))):
        return False
    return root_trace(roots, actions, seed).get('hypotheticalRoots', 0) > 0


def index(plan_path, activation, deliveries, out):
    """Delivery index: receipt/archive hashes per worker; TRAIN/VALIDATION outcomes. Never opens SEALED archives."""
    import tempfile
    plan = json.loads(plan_path.read_text())
    act_sha = sha(activation)
    split_of = {s['seed']: s['split'] for s in plan['sources']}
    workers, sources = {}, {}
    for d in sorted(deliveries.iterdir()):
        receipt = d/'worker-receipt.json'
        if not receipt.exists():
            workers[d.name] = {'status': 'no-receipt', 'files': sorted(p.name for p in d.iterdir())}
            continue
        rec = json.loads(receipt.read_text())
        want = [s['seed'] for s in plan['sources'] if s['worker'] == rec['worker']]
        if rec.get('half') is not None:
            want = want[rec['half']::2]
        if (rec['sources'] != want or rec['activationSha256'] != act_sha or rec['planSha256'] != sha(plan_path)
                or any(sha(d/n) != h for n, h in rec['archives'].items())):
            raise ValueError(d.name+': receipt does not match plan, activation or archives')
        workers[d.name] = {'status': 'verified', 'receiptSha256': sha(receipt), 'archives': rec['archives']}
        codes = dict(zip(rec['sources'], rec['returncodes']))
        for seed, rc in codes.items():
            sources[seed] = {'split': split_of[seed], 'worker': rec['worker'], 'returncode': rc}
        for split in ('train', 'validation'):
            with tarfile.open(d/(split+'.tar.gz')) as tar, tempfile.TemporaryDirectory() as tmp:
                members = {m.name: m for m in tar.getmembers()}
                for seed in (s for s in rec['sources'] if split_of[s] == split):
                    base, row = f'{split}/seed-{seed}', sources[seed]
                    if base+'.receipt.json' not in members:
                        row['status'] = 'censored'
                        continue
                    unit_receipt = json.loads(tar.extractfile(members[base+'.receipt.json']).read())
                    usable = unit_receipt['returncode'] == 0
                    if not usable and unit_receipt['returncode'] == 65:
                        paths = []
                        for suffix in ('.roots.jsonl', '.mcts.csv.actions.jsonl'):
                            path = Path(tmp)/('x'+suffix)
                            path.write_bytes(tar.extractfile(members[base+suffix]).read())
                            paths.append(path)
                        usable = requalify(unit_receipt, *paths, seed)
                        row['requalified'] = usable
                    row['status'] = 'usable' if usable else 'censored'
                    if usable:
                        footer = json.loads(tar.extractfile(members[base+'.states.jsonl']).read().splitlines()[-1])
                        if footer.get('complete') is not True or footer.get('integrityPassed') is not True:
                            raise ValueError(f'{seed}: usable source without a complete footer')
                        row['label'] = footer['label']
        for seed in (s for s in rec['sources'] if split_of[s] == 'confirm'):
            sources[seed]['status'] = 'sealed'
    summary = {}
    for split in SPLITS:
        rows = [r for r in sources.values() if r['split'] == split]
        planned = sum(s['split'] == split for s in plan['sources'])
        entry = {'planned': planned, 'delivered': len(rows), 'returncode0': sum(r['returncode'] == 0 for r in rows),
                 'returncode65': sum(r['returncode'] == 65 for r in rows),
                 'otherNonzero': sum(r['returncode'] not in (0, 65) for r in rows)}
        if split != 'confirm':
            usable = [r for r in rows if r['status'] == 'usable']
            entry.update(usable=len(usable), requalified=sum(bool(r.get('requalified')) for r in rows),
                         heartWins=sum(r['label'] == 1 for r in usable))
        summary[split] = entry
    write(out, {'schema': 'heart-outcome-round2-delivery-index-v1', 'planSha256': sha(plan_path),
                'activationSha256': act_sha, 'requalifyTool': 'tools/heart_outcome_round2.py requalify (4473ce6+)',
                'summary': summary, 'workers': workers,
                'sources': {str(k): sources[k] for k in sorted(sources)}})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prepare', 'canary', 'activate', 'worker', 'index'))
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    for name in ('binary', 'student', 'plan', 'bundle', 'out', 'approval', 'activation'):
        p.add_argument('--'+name, type=Path)
    p.add_argument('--workers', type=int)
    p.add_argument('--per-worker', type=int, nargs=3, metavar=('TRAIN', 'VALIDATION', 'CONFIRM'))
    p.add_argument('--sibling-every', type=int, default=0)
    p.add_argument('--role', choices=('local', 'cloud'), default='local')
    p.add_argument('--worker', type=int)
    p.add_argument('--deliveries', type=Path)
    p.add_argument('--half', type=int, choices=(0, 1))
    p.add_argument('--activation-sha256')
    a = p.parse_args()
    required = {'prepare': ('binary', 'student', 'out', 'workers', 'per_worker'), 'canary': ('plan', 'bundle', 'out'),
                'activate': ('plan', 'bundle', 'approval', 'out'),
                'worker': ('plan', 'bundle', 'activation', 'out', 'worker', 'activation_sha256'),
                'index': ('plan', 'activation', 'deliveries', 'out')}
    for key in required[a.command]:
        if getattr(a, key) is None:
            p.error('--'+key.replace('_', '-')+' is required for '+a.command)
    if a.command == 'prepare': prepare(a.repo, a.binary, a.student, a.out, a.workers, a.per_worker, a.sibling_every)
    elif a.command == 'canary': canary(a.plan, a.bundle.resolve(), a.out.resolve(), a.role)
    elif a.command == 'activate': activate(a.plan, a.bundle, a.approval, a.out)
    elif a.command == 'index': print(json.dumps(index(a.plan, a.activation, a.deliveries, a.out), indent=1))
    else: worker(a.plan, a.bundle.resolve(), a.activation, a.out.resolve(), a.worker, a.activation_sha256, a.half)


if __name__ == '__main__':
    main()
