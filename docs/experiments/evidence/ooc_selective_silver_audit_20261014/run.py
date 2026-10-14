#!/usr/bin/env python3
"""Exclusive prepare/canary/cohort execution for the frozen selective OOC audit."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

REPO = Path(__file__).resolve().parents[4]
PACKET = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('selective_analysis', REPO / 'tools/analyze_ooc_selective_silver.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def prepare(out):
    a.require(not git('status', '--porcelain'), 'freeze requires clean reviewed source')
    producer = git('rev-parse', 'HEAD'); out.mkdir(parents=True, exist_ok=False)
    models = out / 'models'; models.mkdir()
    prior = REPO / 'docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt'
    a.require(a.sha(prior) == a.PRIOR, 'wrong gen6 E')
    frozen_prior = models / 'gen6E.txt'; shutil.copy2(prior, frozen_prior)
    commands = [['cmake', '--preset', 'linux-gcc-release-ccache'],
                ['cmake', '--build', '--preset', 'linux-gcc-release-ccache-build', '--target', 'one_combat', '-j', '2']]
    with (out / 'build.log').open('x') as log:
        for cmd in commands:
            subprocess.run(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
    a.require(git('rev-parse', 'HEAD') == producer and not git('status', '--porcelain'), 'source changed during build')
    binary = out / 'one_combat'; shutil.copy2(REPO / 'build/linux-gcc-release-ccache/one_combat', binary)
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': os.environ['HOME'],
           'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE', 'STS_EXECUTABLE_GIT_SHA': producer,
           'STS_NATIVE_OOC': '1', 'STS_FAIR': '1', 'STS_SEARCHER3': '0',
           'STS_SILVER_SEARCH': '1', 'STS_SILVER_EXACT_ROOT_BUDGETS': '1', 'STS_SILVER_REUSE_CAP_MODE': 'allocated',
           'STS_SILVER_ADAPTIVE': '0', 'STS_SILVER_LEARNED_STOP': '0', 'STS_SILVER_LOOP_GUARD': '0',
           'STS_SILVER_VNET_LEAF_DIRECT': '0', 'STS_SILVER_ROOT_PRIOR_WEIGHT': '400',
           'STS_SILVER_ROOT_PRIOR_SCOPE': 'override', 'STS_SILVER_ROOT_PRIOR': str(frozen_prior),
           'STS_COLLECT_KEYS': '0', 'STS_STOP_AFTER_ACT': '3', 'STS_OOC_MCTS': '1',
           'STS_OOC_MCTS_SIMS': '4096', 'STS_OOC_MCTS_LEAF_VALUE': 'native', 'STS_OOC_MCTS_LEAF_COMBATS': '3',
           'STS_OOC_MCTS_PRIOR': 'policy', 'STS_OOC_MCTS_LEAF_POLICY': 'v4', 'STS_OOC_MCTS_WIDEN_K': '4',
           'STS_OOC_MCTS_WIDEN_ALPHA': '0.75', 'STS_OOC_MCTS_ROOT_SELECTION': 'visits',
           'STS_OOC_MCTS_EARLY_STOP': '0', 'STS_OOC_MCTS_GAP_STOP_20': '0', 'STS_OOC_MCTS_TREE_RULES': '1',
           'STS_OOC_MCTS_MERGE_OUTCOMES': '1', 'STS_OOC_MCTS_ROLLOUT_SHOP': 'greedy', 'STS_OOC_PUBLIC_FUTURES': '8',
           'STS_OOC_STRATEGIC_TOK_NN': 'selfplay/models/ooc_strategic_tok_final.native',
           'STS_OOC_STRATEGIC_REST': '1', 'STS_OOC_STRATEGIC_EVENT': '1', 'STS_OOC_STRATEGIC_SHOP': '1',
           'STS_OOC_STRATEGIC_TREASURE': '1', 'STS_OOC_STRATEGIC_BOSS_RELIC': '1',
           'STS_OOC_STRATEGIC_MARGIN': '1.0', 'STS_REST_WIN': '0'}
    exported = subprocess.run([str(binary), 'oocselectivesilverspec'], cwd=REPO, env=env,
                              capture_output=True, text=True, check=True)
    (out / 'spec.log').write_text(exported.stdout + exported.stderr)
    identity = a.decode(exported.stdout.splitlines()[-1]); write(out / 'spec.json', identity)
    # Exact embedded identity, including the calibrated boss shift, is checked independently.
    manifest = REPO / 'build/a20-teacher-comparison/calibrated-ctm/manifest.json'
    a.require(a.sha(manifest) == a.CTM and identity['ctmLoadedIdentity'] == a.read(manifest), 'calibrated loaded identity mismatch')
    plan = out / 'plan.json'
    write(plan, {'schemaVersion': 'ooc_selective_silver_plan_v1', 'canarySeed': a.CANARY,
                 'streams': a.streams(), 'ctmLoadedIdentity': identity['ctmLoadedIdentity']})
    files = [binary, frozen_prior, plan, out / 'spec.json', out / 'spec.log', out / 'build.log',
             Path(__file__).resolve(), REPO / 'tools/analyze_ooc_selective_silver.py', REPO / 'tools/seed_guard.sh', PACKET / 'PROTOCOL.md', manifest]
    for artifact in identity['sourcePolicy']['model_artifacts']:
        files.append((REPO / artifact['path']).resolve())
    for name, expected in [('combat_transition_deepsets_pathb_a20_lizard.native', 'ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b'),
                           ('combat_transition_near_full_escape_pathb_a20.native', 'e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d')]:
        path = REPO / 'selfplay/models' / name; a.require(a.sha(path) == expected, 'CTM native hash'); files.append(path)
    freeze = {'schemaVersion': 'ooc_selective_silver_freeze_v1', 'producerGitSha': producer,
              'repository': str(REPO), 'binary': str(binary), 'binarySha256': a.sha(binary), 'environment': env,
              'spec': identity, 'plan': str(plan), 'ctmManifest': str(manifest), 'ctmManifestSha256': a.CTM, 'limits': a.LIMITS,
              'canarySeed': a.CANARY, 'cohortSeeds': a.COHORT,
              'mapScreenEnum': identity['mapScreenEnum'],
              'outputs': {str(s): str(out / ('canary' if s == a.CANARY else f's{s}')) for s in (a.CANARY, *a.COHORT)},
              'buildCommands': commands, 'artifactFiles': {str(p): a.sha(p) for p in files}}
    write(out / 'freeze.json', freeze); a.validate_freeze(out / 'freeze.json')


def source(out, f, seed, digest):
    prefix = f['outputs'][str(seed)]
    a.require(not list(out.glob(Path(prefix).name + '.*')), 'existing source outputs')
    argv = ['bash', str(REPO / 'tools/seed_guard.sh'), f['binary'], 'oocselectivesilvergen', '1', str(seed), f['plan'], prefix + '.jsonl']
    write(prefix + '.started.json', {'argv': argv, 'freezeSha256': digest})
    start = time.monotonic()
    with open(prefix + '.log', 'x') as log:
        process = subprocess.Popen(['/usr/bin/time', '-f', '%U %S %e', '-o', prefix + '.time',
                                    'prlimit', '--cpu=200:200', '--', *argv], cwd=REPO, env=f['environment'],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            code = process.wait()
        if code != 0:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
    cpu = elapsed = None
    try:
        fields = Path(prefix + '.time').read_text().splitlines()[-1].split(); cpu = sum(map(float, fields[:2])) if len(fields) == 3 else None; elapsed = float(fields[2]) if len(fields) == 3 else None
    except (ValueError, IndexError, OSError):
        pass
    receipt = {'argv': argv, 'seed': seed, 'freezeSha256': digest, 'returncode': code,
               'timedOut': timed_out, 'cpuSeconds': cpu, 'gnuWallSeconds': elapsed, 'wallSeconds': time.monotonic() - start}
    write(prefix + '.receipt.json', receipt); print(json.dumps(receipt), flush=True); return receipt


def execute(out, phase):
    f = a.validate_freeze(out / 'freeze.json'); digest = a.sha(out / 'freeze.json')
    if phase == 'cohort':
        canary = a.read(out / 'canary-report.json')
        a.require(canary['verdict'] == 'CANARY_VALID' and canary['freezeSha256'] == digest, 'canary prerequisite')
    write(out / f'phase-{phase}.started.json', {'freezeSha256': digest})
    seeds = iter([a.CANARY] if phase == 'canary' else a.COHORT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = {}
        for _ in range(1 if phase == 'canary' else 2):
            seed = next(seeds); active[pool.submit(source, out, f, seed, digest)] = seed
        failed = False
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                seed = active.pop(future)
                try:
                    receipt = future.result()
                    a.require(receipt['returncode'] == 0 and not receipt['timedOut'], 'process failed')
                    a.job(f, seed, digest)
                except Exception as exc:
                    failed = True; print(json.dumps({'dispatchStopped': str(exc), 'seed': seed}), flush=True)
            if not failed:
                for _ in done:
                    seed = next(seeds, None)
                    if seed is not None: active[pool.submit(source, out, f, seed, digest)] = seed
    cmd = ['python3', str(REPO / 'tools/analyze_ooc_selective_silver.py'), str(out / 'freeze.json'), str(out / f'{phase}-report.json')]
    if phase == 'canary': cmd.append('--canary')
    subprocess.run(cmd, cwd=REPO, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('phase', choices=('prepare', 'canary', 'cohort')); parser.add_argument('out', type=Path); args = parser.parse_args()
    prepare(args.out.resolve()) if args.phase == 'prepare' else execute(args.out.resolve(), args.phase)
