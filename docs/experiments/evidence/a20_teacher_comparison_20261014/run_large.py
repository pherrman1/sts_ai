#!/usr/bin/env python3
"""Prepare and execute PROTOCOL-LARGE.md once; no retries, replacements or extensions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import importlib.util
import json
from pathlib import Path
import subprocess

PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[3]
spec = importlib.util.spec_from_file_location('large_analysis', REPO / 'tools/analyze_a20_teachers_large.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
spec = importlib.util.spec_from_file_location('pilot_prepare', PACKET / 'run_pilot.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.CANARY, base.COHORT = analysis.CANARY, analysis.COHORT
base.CPU_LIMIT, base.WALL_LIMIT = 1200, 1800
base.CTM_HASHES = analysis.core.CTM_HASHES


def prepare(out, prior, ctm_dir, source):
    base.prepare(out, prior, ctm_dir, 6, analysis.PRIOR_HASH, source)
    original = out / 'freeze.json'
    freeze = analysis.core.read_json(original)
    original.rename(out / 'preparation-base.json')
    env = freeze['environment'] | {'STS_CTMSILVER_ARMSET': 'teacher_a20_large', 'STS_CTMSILVER_LARGE_ANCHOR': '0'}
    # Re-export under the actual study environment, without any game seed.
    policy = out / 'large-policy.json'
    with (out / 'large-policy.log').open('x') as log:
        subprocess.run([freeze['binary'], 'vwinrefreshpolicyspec', str(policy)], cwd=REPO, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    teacher = analysis.core.read_json(freeze['teacher'])
    teacher.update(teacher_id='a20-teacher-large-plain10k-' + freeze['producerGitSha'][:12],
                   environment=env, ooc_policy=analysis.core.read_json(policy))
    teacher_path = out / 'large-teacher.json'
    anchor_path = out / 'anchor-teacher.json'
    anchor_env = env | {'STS_CTMSILVER_LARGE_ANCHOR': '1'}
    base.write_new(teacher_path, teacher)
    base.write_new(anchor_path, teacher | {'teacher_id': teacher['teacher_id'] + '-anchor', 'environment': anchor_env})
    freeze.update(schemaVersion=analysis.core.FREEZE_SCHEMA, teacher=str(teacher_path), environment=env,
                  resourceLimits=analysis.LIMITS, arms=analysis.arms(), anchorSeeds=analysis.ANCHORS,
                  anchorTeacher=str(anchor_path), anchorEnvironment=anchor_env, anchorArms=analysis.arms(True),
                  bootstrap=analysis.BOOTSTRAP, coverageMinimum=analysis.COVERAGE)
    for path in (Path(__file__).resolve(), REPO / 'tools/analyze_a20_teachers_large.py', PACKET / 'PROTOCOL-LARGE.md',
                 teacher_path, anchor_path, policy, out / 'large-policy.log', out / 'preparation-base.json'):
        freeze['artifactFiles'][str(path)] = base.sha(path)
    base.write_new(original, freeze)
    analysis.validate_freeze(freeze)


def verify(out):
    freeze = analysis.core.read_json(out / 'freeze.json')
    analysis.validate_freeze(freeze)
    return freeze


def execute(out, phase):
    freeze = verify(out)
    digest = base.sha(out / 'freeze.json')
    if phase == 'cohort':
        canary = analysis.core.read_json(out / 'canary-report.json')
        base.require(canary['verdict'] == 'CANARY_VALID' and canary['freezeSha256'] == digest, 'canary failed')
    base.write_new(out / f'phase-{phase}.started.json', {'freezeSha256': digest})
    seeds = [analysis.CANARY] if phase == 'canary' else analysis.COHORT
    # The base source launcher is reused with a seed-dependent frozen view; no mutable globals in workers.
    def run(seed):
        view = dict(freeze)
        if seed == analysis.CANARY or seed in analysis.ANCHORS:
            view.update(teacher=freeze['anchorTeacher'], environment=freeze['anchorEnvironment'])
        return run_source(out, seed, view, digest)
    pending_seeds = iter(seeds)
    failed = False
    teachers = analysis.validate_freeze(freeze)
    with ThreadPoolExecutor(max_workers=4) as pool:
        active = {pool.submit(run, s): s for s in [next(pending_seeds, None) for _ in range(min(4, len(seeds)))]}
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                seed = active.pop(future)
                try:
                    receipt = future.result()
                    failed |= receipt['returncode'] != 0 or receipt['timedOut'] or receipt['cpuSeconds'] is None
                    if receipt['returncode'] == 0 and not receipt['timedOut']:
                        analysis.job(freeze, seed, digest, teachers)
                except Exception as exc:
                    failed = True
                    print(json.dumps({'seed': seed, 'dispatchStopped': str(exc)}), flush=True)
            # A process failure drains already-running jobs and stops further dispatch.
            if not failed:
                for _ in done:
                    seed = next(pending_seeds, None)
                    if seed is not None:
                        active[pool.submit(run, seed)] = seed
    cmd = ['python3', str(REPO / 'tools/analyze_a20_teachers_large.py'), str(out / f'{phase}-report.json'),
           str(out / 'freeze.json'), *[freeze['outputs'][str(s)] for s in seeds]]
    if phase == 'canary':
        cmd.append('--canary')
    subprocess.run(cmd, cwd=REPO, check=True)


def run_source(out, seed, freeze, digest):
    import os
    import signal
    import time
    prefix = Path(freeze['outputs'][str(seed)])
    base.require(not list(out.glob(prefix.name + '.*')), 'existing source output')
    argv = ['bash', str(REPO / 'tools/seed_guard.sh'), freeze['binary'], 'ctmsilvergen', '1', '20',
            str(prefix), str(seed), freeze['teacher'], '16']
    base.write_new(str(prefix) + '.started.json', {'argv': argv, 'freezeSha256': digest})
    command = ['/usr/bin/time', '-f', '%U %S', '-o', str(prefix) + '.time', 'prlimit', '--cpu=1200:1200', '--', *argv]
    start = time.monotonic()
    with open(str(prefix) + '.log', 'x') as log:
        process = subprocess.Popen(command, cwd=REPO, env=freeze['environment'], stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    cpu = None
    try:
        fields = Path(str(prefix) + '.time').read_text().splitlines()[-1].split()
        cpu = sum(map(float, fields)) if len(fields) == 2 else None
    except (OSError, ValueError, IndexError):
        pass
    receipt = dict(returncode=code, cpuSeconds=cpu, wallSeconds=time.monotonic() - start, timedOut=timed_out,
                   argv=argv, seed=seed, binarySha256=freeze['binarySha256'], freezeSha256=digest)
    base.write_new(str(prefix) + '.receipt.json', receipt)
    print(json.dumps(receipt), flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'canary', 'cohort'))
    parser.add_argument('out', type=Path)
    parser.add_argument('--prior', type=Path)
    parser.add_argument('--ctm-dir', type=Path)
    parser.add_argument('--prior-source')
    args = parser.parse_args()
    if args.phase == 'prepare':
        base.require(args.prior and args.ctm_dir and args.prior_source, 'missing model identity')
        prepare(args.out.resolve(), args.prior.resolve(), args.ctm_dir.resolve(), args.prior_source)
    else:
        execute(args.out.resolve(), args.phase)


if __name__ == '__main__':
    main()
