"""Native cloud execution of the fresh Arm C cohort (§494, seeds 110164000..063).

Subcommands (receipts expose completion/custody only; capture JSONL is never parsed
here, so TEST stays opaque):
  bundle REPO BINARY STUDENTC OUT       assemble and hash the frozen producer bundle
  deadline PLAN SHARE CANARY_JSON       lead only, after canary review: the single 6 h deadline
  unit PLAN BUNDLE OUT SEED TAG [--no-capture]
                                        one canary unit (seed must be a frozen canary)
  canary PLAN BUNDLE OUT                lead: frozen canaries + parity/coverage gates
  worker PLAN PLAN_SHA256 BUNDLE LOCAL SHARE W
                                        run worker W's fixed sources concurrently, export

Interruption rule (Philipp, 2026-10-16 10:33Z): a source whose attempt ended without a
share receipt (process or container lost) is rerun whole exactly once, inside the same
deadline, after any orphaned producer of the earlier attempt is killed. Partial outputs
are kept only when the local disk survived (a lost container takes them with it). A
source with a share receipt (any return code, including timeout 124) is never rerun.
Each source's outputs reach the share as their own archive (sealed for TEST) BEFORE its
receipt, so a receipt on the share always means its data is there too.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
PRODUCER_SHA256 = '86a7569fe56cfdd2f635018147f005b16870598c53c7c164a5d1edd994ecbacf'
STUDENT_C_SHA256 = 'eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509'
GLOBAL_SECONDS = 21600
MAX_ATTEMPTS = 2


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan_mod = _load('heart_distill_native_plan', HERE / 'heart_distill_native_plan.py')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, value, exclusive=True):
    """Write via a temporary name and rename; exclusive refuses an existing target."""
    path = Path(path)
    if exclusive and path.exists():
        raise FileExistsError(str(path))
    tmp = path.with_name(path.name + '.partial')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(tmp, path)


def student_contract_fn(repo):
    """The reviewed runner's student_contract, compiled from its pinned bytes without import
    (the runner imports the torch trainer at module level)."""
    source = (repo / plan_mod.RUNNER).read_bytes()
    original = subprocess.check_output(['git', 'show', f'{plan_mod.SOURCE}:{plan_mod.RUNNER}'], cwd=repo)
    if source != original:
        raise ValueError('reviewed runner differs from pinned source')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'student_contract')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), plan_mod.RUNNER, 'exec'), namespace)
    return namespace['student_contract']


def host_identity():
    def read(p):
        try:
            return Path(p).read_text().strip()
        except OSError:
            return None
    model = next((l.split(':', 1)[1].strip() for l in (read('/proc/cpuinfo') or '').splitlines()
                  if l.startswith('model name')), None)
    mem = next((l for l in (read('/proc/meminfo') or '').splitlines() if l.startswith('MemTotal')), None)
    return {'hostname': socket.gethostname(), 'bootId': read('/proc/sys/kernel/random/boot_id'),
            'cpuModel': model, 'affinity': sorted(os.sched_getaffinity(0)), 'memTotal': mem,
            'platform': platform.platform(), 'python': sys.version}


# ---------------------------------------------------------------- bundle

def bundle(repo, binary, student_c, out):
    repo, out = Path(repo).resolve(), Path(out)
    if sha(binary) != PRODUCER_SHA256:
        raise ValueError('binary is not the frozen producer')
    if sha(student_c) != STUDENT_C_SHA256:
        raise ValueError('wrong Arm C native weights')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(binary, out / 'one_combat')
    shutil.copy2(student_c, out / 'studentc.bin')
    shutil.copy2(repo / 'tools/seed_guard.sh', out / 'seed_guard.sh')
    paths = subprocess.check_output(['git', 'ls-files', 'models', 'selfplay/models'],
                                    cwd=repo, text=True).splitlines()
    for rel in paths:
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / rel, dst)
    manifest = {'producerSha256': PRODUCER_SHA256, 'studentcSha256': STUDENT_C_SHA256,
                'files': {p: sha(out / p) for p in ['one_combat', 'studentc.bin', 'seed_guard.sh', *paths]}}
    write_json(out / 'bundle.json', manifest)
    return verify_bundle(out)


def verify_bundle(path):
    path = Path(path)
    manifest = json.loads((path / 'bundle.json').read_text())
    if (manifest['files'].get('one_combat') != PRODUCER_SHA256
            or manifest['files'].get('studentc.bin') != STUDENT_C_SHA256):
        raise ValueError('bundle manifest is not the frozen producer/model')
    for rel, digest in manifest['files'].items():
        if sha(path / rel) != digest:
            raise ValueError('bundle file changed: ' + rel)
    return sha(path / 'bundle.json')


# ---------------------------------------------------------------- deadline

def create_deadline(plan_path, share, canary_json):
    """Refuses unless the frozen canary gates passed; independent canary review is still
    required before the lead runs this."""
    if json.loads(Path(canary_json).read_text()).get('gatePass') is not True:
        raise ValueError('canary gates did not pass; no collection deadline')
    share = Path(share)
    share.mkdir(parents=True, exist_ok=True)
    start = time.time()
    value = {'planSha256': sha(plan_path), 'canarySha256': sha(canary_json), 'startEpoch': start, 'deadlineEpoch': start + GLOBAL_SECONDS,
             'startUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start)),
             'rule': 'created once by the lead; never reset or extended'}
    fd = os.open(share / 'deadline.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
    return value


def read_deadline(share, plan_sha):
    value = json.loads((Path(share) / 'deadline.json').read_text())
    if value['planSha256'] != plan_sha or value['deadlineEpoch'] - value['startEpoch'] != GLOBAL_SECONDS:
        raise ValueError('deadline is not bound to this plan')
    return value['deadlineEpoch']


# ---------------------------------------------------------------- one unit

def run_unit(plan, repo, bundle_dir, out, seed, deadline, capture=True, tag=None, attempt=1, on_start=None):
    """Run one guarded unit to a local receipt. Mirrors the reviewed runner's unit().

    on_start(pgid) is called once the producer's process group exists."""
    contract = student_contract_fn(repo)
    bundle_sha = verify_bundle(bundle_dir)
    remaining = deadline - time.time()
    if remaining <= 0:
        raise RuntimeError(f'global deadline passed before unit {seed}')
    spec = plan_mod.shard_spec(plan, seed, bundle_dir, out, min(GLOBAL_SECONDS, remaining), capture, tag)
    base = Path(spec['base'])
    env = dict(spec['environment'])
    for name in plan['workerHostEnvironmentRequired']:  # HOME, PATH, as the reviewed runner supplies
        env[name] = os.environ.get(name, '/usr/bin:/bin' if name == 'PATH' else '')
    receipt = base.with_suffix('.receipt.json')
    if receipt.exists() or list(base.parent.glob(base.name + '.*')):
        raise ValueError('unit output already exists: ' + str(base))
    start = time.time()
    result = {'seed': seed, 'capture': capture, 'tag': tag, 'attempt': attempt,
              'assignment': spec['assignment'], 'command': spec['command'],
              'environment': env, 'timeoutSeconds': spec['timeoutSeconds'],
              'deadlineEpoch': deadline, 'bundleSha256': bundle_sha, 'host': host_identity(),
              'started': start}
    with base.with_suffix('.log').open('x') as log:
        with subprocess.Popen(spec['command'], cwd=spec['cwd'], env=env, stdout=log,
                              stderr=subprocess.STDOUT, start_new_session=True) as child:
            if on_start:
                on_start(child.pid)
            try:
                rc = child.wait(timeout=spec['timeoutSeconds'])
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                rc = 124
    result.update(returncode=rc, seconds=time.time() - start)
    if rc == 0:
        try:
            with base.with_suffix('.mcts.csv.support.jsonl').open() as f:
                support = [json.loads(line) for line in f]
            if len(support) != 1:
                raise ValueError('one source support receipt required')
            result['studentPriorContract'] = contract(base.with_suffix('.log').read_text(), support[0],
                                                      seed, plan['environment']['STS_OOC_MCTS_LEAF_POLICY'])
        except (ValueError, KeyError, OSError) as error:
            result.update(contractError=str(error), processReturncode=rc, returncode=65)
    cap = base.with_suffix('.sib.jsonl')
    if capture and cap.exists():
        result['captureSha256'] = sha(cap)
    result['files'] = {p.name: sha(p) for p in sorted(base.parent.glob(base.name + '.*')) if p.is_file()}
    write_json(receipt, result)
    return result


# ---------------------------------------------------------------- canary

def canary(plan, repo, bundle_dir, out):
    """Frozen canaries: 994 OFF/ON parity, 995 ON; coverage via the reviewed validator."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    deadline = time.time() + 3600 + 60
    units = [(c['seed'], c['capture'], tag) for c, tag in
             zip(plan['canaries'], ('canary-control', 'canary-capture', 'canary-second'))]
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(lambda u: run_unit(plan, repo, bundle_dir, out, u[0], deadline, u[1], u[2]), units))
    summary = {'receipts': {u[2]: sha(out / (u[2] + '.receipt.json')) for u in units},
               'returncodes': [r['returncode'] for r in receipts], 'parity': {}, 'coverage': {}}
    for suffix in ('.trace.jsonl', '.mcts.csv.actions.jsonl'):
        a, b = out / ('canary-control' + suffix), out / ('canary-capture' + suffix)
        summary['parity'][suffix] = a.exists() and b.exists() and a.read_bytes() == b.read_bytes()
    if all(r['returncode'] == 0 for r in receipts):
        sys.path.insert(0, str(repo / 'tools'))
        from heart_rollout_distill import validate_rows
        for tag, seed in (('canary-capture', units[1][0]), ('canary-second', units[2][0])):
            try:
                with (out / (tag + '.sib.jsonl')).open() as f:
                    _, _, cover = validate_rows((json.loads(l) for l in f), seed, 'heart1')
            except (ValueError, KeyError, OSError) as error:
                cover = {'error': str(error)}
            summary['coverage'][tag] = cover
    summary['artifacts'] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    cov = summary['coverage'].values()
    summary['gatePass'] = (all(r['returncode'] == 0 for r in receipts) and all(summary['parity'].values())
                           and len(summary['coverage']) == 2
                           and all('error' not in c and c['groups'] and c['accepted'] >= .8 * c['raw'] for c in cov))
    write_json(out / 'canary.json', summary)
    return summary


# ---------------------------------------------------------------- worker

def claim_attempt(share, seed, w, boot_id):
    """Return the attempt number to run, or None if a receipt already exists.

    Attempt files are created with O_EXCL. On the rclone share that is exclusive only
    within a container; duplicates across containers are prevented by launching each
    worker number once.
    """
    receipts, claims = Path(share) / 'receipts', Path(share) / 'claims'
    receipts.mkdir(parents=True, exist_ok=True)
    claims.mkdir(parents=True, exist_ok=True)
    if (receipts / f'seed-{seed}.receipt.json').exists():
        return None
    previous = [n for n in range(1, MAX_ATTEMPTS + 1) if (claims / f'seed-{seed}.attempt{n}.json').exists()]
    if previous:
        last_path = claims / f'seed-{seed}.attempt{previous[-1]}.json'
        last = json.loads(last_path.read_text())
        if last['bootId'] == boot_id:
            if _alive(last['pid']):
                raise RuntimeError(f'source {seed} attempt {previous[-1]} still running here')
            started = claims / f'seed-{seed}.attempt{previous[-1]}.child.json'
            if started.exists():  # the worker died; its producer group may still be running
                _kill_group(json.loads(started.read_text())['pgid'])
    attempt = len(previous) + 1
    if attempt > MAX_ATTEMPTS:
        raise RuntimeError(f'source {seed} interrupted {MAX_ATTEMPTS} times; INCOMPLETE, no further rerun')
    fd = os.open(claims / f'seed-{seed}.attempt{attempt}.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, 'w') as f:
        json.dump({'seed': seed, 'worker': w, 'attempt': attempt, 'bootId': boot_id, 'pid': os.getpid(),
                   'time': time.time()}, f, sort_keys=True)
    return attempt


def _kill_group(pgid):
    """Terminate an orphaned producer group and wait until none of it remains."""
    for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 30)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        end = time.time() + wait
        while time.time() < end:
            if not _group_running(pgid):
                return
            time.sleep(0.2)
    raise RuntimeError(f'orphaned producer group {pgid} did not exit')


def _group_running(pgid):
    """True while any non-zombie process of the group exists (zombies hold no CPU or files)."""
    for stat in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = stat.read_text().rsplit(')', 1)[1].split()
        except OSError:
            continue
        if int(fields[2]) == pgid and fields[0] != 'Z':
            return True
    return False


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def export_file(src, dst):
    """Copy to the share via a temporary name, then verify the bytes read back."""
    dst = Path(dst)
    if dst.exists():
        raise FileExistsError(str(dst))
    tmp = dst.with_name(dst.name + '.partial')
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    digest = sha(src)
    if sha(dst) != digest:
        raise RuntimeError('share read-back mismatch: ' + dst.name)
    return digest


def worker(plan_path, plan_sha, repo, bundle_dir, local, share, w):
    if sha(plan_path) != plan_sha:
        raise ValueError('plan is not the frozen assignment')
    plan = json.loads(Path(plan_path).read_text())
    workers = len({s['worker'] for s in plan['sources']})
    if type(w) is not int or not 1 <= w <= workers:
        raise ValueError('worker number out of range')
    mine = [s for s in plan['sources'] if s['worker'] == w - 1]
    splits = {s['split'] for s in mine}
    if len(splits) != 1:
        raise ValueError('worker assignment is not split-pure; TEST could not be sealed separately')
    split = splits.pop()
    deadline = read_deadline(share, plan_sha)
    local, share = Path(local), Path(share)
    local.mkdir(parents=True, exist_ok=True)
    (share / 'sources').mkdir(parents=True, exist_ok=True)
    boot = host_identity()['bootId']

    def one(source):
        seed = source['seed']
        attempt = claim_attempt(share, seed, w, boot)
        if attempt is None:
            return {'seed': seed, 'state': 'already-receipted'}
        if attempt > 1:
            old = sorted(local.glob(f'seed-{seed}.*'))
            if old:
                keep = local / f'interrupted-attempt{attempt - 1}'
                keep.mkdir(exist_ok=True)
                for p in old:
                    os.replace(p, keep / p.name)
        child = share / 'claims' / f'seed-{seed}.attempt{attempt}.child.json'
        def started(pgid):
            write_json(child, {'pgid': pgid, 'bootId': boot, 'time': time.time()})
        try:
            receipt = run_unit(plan, repo, bundle_dir, local, seed, deadline, attempt=attempt, on_start=started)
        except Exception as error:  # no receipt: recorded as a failed attempt, not rerun here
            write_json(local / f'seed-{seed}.attempt{attempt}.error.json', {'error': str(error)}, exclusive=False)
            raise
        # Data first, receipt last: the share receipt is the completion marker.
        name = f'seed-{seed}.attempt{attempt}' + ('-SEALED' if split == 'test' else '')
        members = sorted(local.glob(f'seed-{seed}.*')) + sorted(local.glob(f'interrupted-attempt*/seed-{seed}.*'))
        archive = local.parent / (name + '.tar.gz')
        with tarfile.open(archive, 'x:gz') as tar:
            for p in members:
                tar.add(p, arcname=f'{name}/{p.relative_to(local)}')
        files = {str(p.relative_to(local)): sha(p) for p in members}
        archive_sha = export_file(archive, share / 'sources' / (name + '.tar.gz'))
        wrapper = local.parent / f'seed-{seed}.share-receipt.json'
        write_json(wrapper, {'seed': seed, 'split': split, 'worker': w, 'attempt': attempt,
                             'returncode': receipt['returncode'], 'receiptSha256': sha(local / f'seed-{seed}.receipt.json'),
                             'archive': 'sources/' + name + '.tar.gz', 'archiveSha256': archive_sha, 'files': files},
                   exclusive=False)
        export_file(wrapper, share / 'receipts' / f'seed-{seed}.receipt.json')
        return {'seed': seed, 'state': 'receipted', 'returncode': receipt['returncode'], 'attempt': attempt,
                'archive': 'sources/' + name + '.tar.gz', 'archiveSha256': archive_sha}

    with ThreadPoolExecutor(max_workers=len(mine)) as pool:
        futures = [pool.submit(one, s) for s in mine]
        outcomes = []
        for f in futures:
            try:
                outcomes.append(f.result())
            except Exception as error:
                outcomes.append({'state': 'error', 'error': str(error)})
    name = f'w{w:02d}-{split}'
    done = {'worker': w, 'split': split, 'seeds': [s['seed'] for s in mine], 'outcomes': outcomes,
            'planSha256': plan_sha, 'deadlineEpoch': deadline, 'finished': time.time(), 'host': host_identity(),
            'testCustody': 'sealed per-source archives; file names and hashes only' if split == 'test' else None}
    write_json(local.parent / (name + '.DONE.json'), done, exclusive=False)
    target = share / (name + '.DONE.json')
    if target.exists():  # a later invocation after an in-process rerun keeps the first record
        target = share / f'{name}.DONE.{int(time.time())}.json'
    export_file(local.parent / (name + '.DONE.json'), target)
    return done


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('bundle'); [b.add_argument(n, type=Path) for n in ('repo', 'binary', 'studentc', 'out')]
    d = sub.add_parser('deadline')
    for n in ('plan', 'share', 'canary_json'):
        d.add_argument(n, type=Path)
    u = sub.add_parser('unit')
    for n in ('plan', 'bundle', 'out'):
        u.add_argument(n, type=Path)
    u.add_argument('seed', type=int); u.add_argument('tag'); u.add_argument('--no-capture', action='store_true')
    c = sub.add_parser('canary'); [c.add_argument(n, type=Path) for n in ('plan', 'bundle', 'out')]
    k = sub.add_parser('worker')
    k.add_argument('plan', type=Path); k.add_argument('plan_sha')
    for n in ('bundle', 'local', 'share'):
        k.add_argument(n, type=Path)
    k.add_argument('w', type=int)
    a = p.parse_args()
    repo = HERE.parent
    if a.cmd == 'bundle':
        print('bundle ok', bundle(a.repo, a.binary, a.studentc, a.out))
    elif a.cmd == 'deadline':
        print(json.dumps(create_deadline(a.plan, a.share, a.canary_json)))
    elif a.cmd == 'unit':
        a.out.mkdir(parents=True, exist_ok=True)
        r = run_unit(json.loads(a.plan.read_text()), repo, a.bundle, a.out, a.seed, time.time() + 3660,
                     not a.no_capture, a.tag)
        print('unit rc', r['returncode'])
    elif a.cmd == 'canary':
        s = canary(json.loads(a.plan.read_text()), repo, a.bundle, a.out)
        print('canary gatePass', s['gatePass'])
    else:
        done = worker(a.plan, a.plan_sha, repo, a.bundle, a.local, a.share, a.w)
        print('worker done', f"w{done['worker']:02d}-{done['split']}",
              json.dumps([[o.get('seed'), o['state'], o.get('returncode')] for o in done['outcomes']]))


if __name__ == '__main__':
    main()
