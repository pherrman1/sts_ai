"""Preparation-only native session coordinator/shard adapter. Never launches games.

Independent review, producer/canary qualification and durable export are still
required before implementing dispatch. No fit or TEST reader is provided.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

SOURCE = '9d83adbbbcc0fabf2c8bcd8c6a87f9782d0acbc3'
RUNNER = 'tools/run_heart_distill_pilot.py'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def scientific_environment(repo):
    """Read the literal environment from the exact reviewed runner, without import.

    Resolve only its three dynamic host/source fields and frozen Arm C policy.
    Refuse any future source change instead of silently adopting another teacher.
    """
    original = subprocess.check_output(['git', 'show', f'{SOURCE}:{RUNNER}'], cwd=repo)
    if (repo / RUNNER).read_bytes() != original:
        raise ValueError('reviewed runner differs from pinned source')
    tree = ast.parse(original)
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    expr = next(n.value for n in run.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'env' for t in n.targets))
    env = {}
    for key, value in zip(expr.keys, expr.values):
        name = ast.literal_eval(key)
        if name in ('HOME', 'PATH'):
            continue  # explicitly supplied by the eventual worker, never copied as secrets
        if name == 'STS_EXECUTABLE_GIT_SHA':
            env[name] = SOURCE
        elif name == 'STS_OOC_MCTS_LEAF_POLICY':
            assert ast.unparse(value) == "study['leafPolicy']"
            env[name] = 'heart1'
        else:
            env[name] = ast.literal_eval(value)
    return env


def assignment(repo, workers):
    if type(workers) is not int or not 1 <= workers <= 64:
        raise ValueError('workers must be 1..64; this is assignment, not capacity')
    return {
        'schema': 'arm-c-native-plan-v1', 'state': 'PREPARED_NOT_AUTHORIZED_TO_DISPATCH',
        'sourceSha': SOURCE, 'runnerSha256': sha(repo / RUNNER),
        'environment': scientific_environment(repo),
        'workerHostEnvironmentRequired': ['HOME', 'PATH'],
        'sourceTimeoutSeconds': 3600, 'globalCollectionSeconds': 21600,
        'deadlineRule': 'one coordinator persists start/deadline once at collection launch; never reset',
        'canaries': [{'seed': 110163994, 'capture': False},
                     {'seed': 110163994, 'capture': True},
                     {'seed': 110163995, 'capture': True}],
        'sources': [{'seed': seed, 'worker': i % workers,
                     'split': 'train' if i < 40 else 'validation' if i < 48 else 'test'}
                    for i, seed in enumerate(range(110164000, 110164064))],
        'requiredBeforeDispatch': ['independent adapter review', 'frozen producer/model/runtime/protocol',
                                  'completion-anchored independent canary review',
                                  'verified durable native artifact export'],
        'testCustody': 'separate sealed archive; hash/receipt transport only; no content inspection',
    }


def shard_spec(plan, seed, bundle, output, remaining_seconds):
    """Return a reviewable invocation, without opening any source output."""
    if type(seed) is not int:
        raise ValueError('source seed must be an integer')
    matches = [s for s in plan['sources'] if s['seed'] == seed]
    if len(matches) != 1:
        raise ValueError('source is not uniquely assigned')
    if not 0 < remaining_seconds <= 21600:
        raise ValueError('remaining deadline must be positive and at most six hours')
    base = Path(output).resolve() / f'seed-{seed}'
    env = dict(plan['environment'])
    env.update(STS_OOC_MCTS_TRACE=str(base.with_suffix('.mcts.csv')),
               STS_OOC_DECISION_TRACE=str(base.with_suffix('.trace.jsonl')),
               STS_OOC_SIBLING_CAPTURE=str(base.with_suffix('.sib.jsonl')),
               STS_OOC_SIBLING_EVERY='4', STS_OOC_SIBLING_REPEATS='64',
               STS_OOC_SIBLING_LONG='0', STS_OOC_SIBLING_MAX_DEPTH='1',
               STS_OOC_SIBLING_MAX_LEAVES='64')
    bundle = Path(bundle).resolve()
    return {'assignment': matches[0], 'environment': env, 'cwd': str(bundle),
            'command': ['bash', str(bundle / 'seed_guard.sh'), str(bundle / 'one_combat'),
                        'bestbench', '10000', '1', '20', str(seed), str(base.with_suffix('.csv'))],
            'timeoutSeconds': min(3600, remaining_seconds),
            'state': 'SPECIFICATION_ONLY_NO_EXECUTION'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--workers', type=int, default=1)
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    plan = assignment(repo, args.workers)
    with args.output.open('x') as f:
        json.dump(plan, f, indent=2, sort_keys=True)
        f.write('\n')


if __name__ == '__main__':
    main()
