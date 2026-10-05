#!/usr/bin/env python3
"""TRAIN/VALIDATION-only frozen replay canary, with exact output parity.

Does not run S0, fit models, open TEST, or reuse/overwrite an output directory.
Derived source/binary and teacher identities are recorded before seed execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from audit_screen_leaf_379 import EXPECTED, digest, source_split_function


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
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'], 'OMP_NUM_THREADS': '1',
           **teacher['environment'], 'STS_VWIN_DECISION_SINK': '1',
           'STS_SCREEN_LEAF_SNAPSHOT_OUT': str(output / 'snapshots.jsonl'),
           'STS_NATIVE_OOC': '1', 'STS_COLLECT_KEYS': '0',
           'STS_OOC_STRATEGIC_TOK_NN': 'selfplay/models/ooc_strategic_tok_final.native',
           'STS_OOC_STRATEGIC_SHOP': '1', 'STS_OOC_STRATEGIC_EVENT': '1',
           'STS_OOC_STRATEGIC_REST': '1', 'STS_OOC_STRATEGIC_TREASURE': '1',
           'STS_OOC_STRATEGIC_BOSS_RELIC': '1', 'STS_OOC_STRATEGIC_MARGIN': '1.0'}
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
            summary['status'] = 'PASS'
            summary['snapshots_sha256'] = digest(output / 'snapshots.jsonl')
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
