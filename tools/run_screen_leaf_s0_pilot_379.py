#!/usr/bin/env python3
"""Run the exact native S0 pilot on verified TRAIN/VALIDATION snapshots only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from audit_screen_leaf_379 import EXPECTED, digest, source_split_function

X2B = 'a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf'


def run(index, replays, output, count, replicates, wall_budget):
    if not 256 <= count <= 1024 or not 1 <= replicates <= 32 or wall_budget <= 0:
        raise ValueError('invalid frozen pilot size/resource budget')
    repo = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True).strip():
        raise ValueError('S0 checkout must be frozen and clean')
    if digest(index) != EXPECTED:
        raise ValueError('sealed corpus index mismatch')
    corpus = json.loads(index.read_text())
    manifest_hashes = {str((index.parent / c['manifest']).resolve()): c['sha256']
                       for c in corpus['components']}
    split, _ = source_split_function()
    sources = []
    # Verify all source split identities and receipts before parsing snapshots.
    for replay in replays:
        receipt = json.loads((replay / 'receipt.json').read_text())
        if split(receipt['seed']) != 'VALIDATION' or receipt['split'] != 'VALIDATION':
            raise ValueError('pilot permits frozen VALIDATION sources only')
        result = json.loads((replay / 'result.json').read_text())
        if result['status'] != 'PASS' or result['exit_code'] != 0:
            raise ValueError('reconstruction parity not qualified')
        snapshot = replay / 'snapshots.jsonl'
        if digest(snapshot) != result['snapshots_sha256']:
            raise ValueError('snapshot custody mismatch')
        manifest_path = Path(receipt['source_manifest'])
        expected_manifest = manifest_hashes.get(str(manifest_path.resolve()))
        if digest(manifest_path) != expected_manifest or expected_manifest != receipt['source_manifest_sha256']:
            raise ValueError('original source manifest changed')
        manifest = json.loads(manifest_path.read_text())
        if manifest['seedSpec'] != {'start': receipt['seed'], 'count': 1, 'ascension': 0}:
            raise ValueError('receipt source identity mismatch')
        if set(result['csv_parity']) != set(manifest['outputs']):
            raise ValueError('incomplete replay parity evidence')
        if any(v['expected'] != manifest['outputs'][k] for k, v in result['csv_parity'].items()):
            raise ValueError('replay parity not bound to original outputs')
        if any(not v['equal'] or v['actual'] != v['expected'] for v in result['csv_parity'].values()):
            raise ValueError('reconstruction output mismatch')
        sources.append((receipt['seed'], snapshot))
    model = repo / 'models/candidates/v_win_x2b_trees.txt'
    if digest(model) != X2B:
        raise ValueError('X2-B identity mismatch')
    candidates = defaultdict(list)
    seen = set()
    for seed, snapshot in sources:
        with snapshot.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['sourceSeed'] != seed:
                    raise ValueError('snapshot source does not match verified manifest')
                identity = f"{seed}:{row['branchId']}:{row['rowIdx']}"
                if identity in seen:
                    raise ValueError('duplicate snapshot identity')
                seen.add(identity)
                rank = hashlib.sha256(('screen-leaf-379-pilot-v1:' + identity).encode()).hexdigest()
                candidates[row['screenContents']['screen']].append((rank, line))
    for group in candidates.values():
        group.sort()
    # Balanced deterministic round robin by observed family; no label access.
    selected = []
    offset = 0
    while len(selected) < count:
        previous = len(selected)
        for screen in sorted(candidates):
            if offset < len(candidates[screen]) and len(selected) < count:
                selected.append(candidates[screen][offset][1])
        if len(selected) == previous:
            raise ValueError('not enough recovered states for pilot')
        offset += 1
    output.mkdir(parents=True, exist_ok=False)
    selected_path = output / 'selected.jsonl'
    selected_path.write_text(''.join(selected))
    by_screen = Counter(json.loads(s)['screenContents']['screen'] for s in selected)
    profile = json.loads((repo / 'docs/experiments/evidence/screen_leaf_379_preflight_20261005/current-default-receipt.json').read_text())
    for model_path, model_hash in profile['models'].items():
        if digest(repo / model_path) != model_hash:
            raise ValueError('auxiliary S0 model identity changed: ' + model_path)
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'], **profile['env']}
    env['STS_OOC_MCTS'] = '0'
    env.pop('STS_OOC_MCTS_TRACE', None)
    env['STS_EXECUTABLE_GIT_SHA'] = sha
    env['STS_WIN_NET'] = str(model)
    binary = repo / 'build/linux-gcc-release/one_combat'
    argv = ['bash', str(repo / 'tools/seed_guard.sh'), str(binary), 'screenleafs0',
            str(selected_path), str(output / 'predictions.jsonl'), str(count), str(replicates)]
    receipt = {'purpose': 'Exact current evaluateLeaf S0 CPU pilot, no model selection',
               'source_sha': sha, 'binary_sha256': digest(binary), 'x2b_sha256': X2B,
               'auxiliary_models': profile['models'], 'corpus_sha256': EXPECTED,
               'replays': [str(p) for p in replays], 'selected_sha256': digest(selected_path),
               'selected_by_screen': dict(by_screen), 'states': count, 'replicates': replicates,
               'threads': 1, 'wall_budget_seconds': wall_budget, 'env': env, 'argv': argv,
               'test_access': 'forbidden before any snapshot numerical parsing',
               'decision_rule': 'Stop on any custody, state/candidate parity, or evaluator failure; report cost separately from reconstruction'}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    start = time.monotonic()
    with (output / 'stdout').open('x') as stdout, (output / 'stderr').open('x') as stderr:
        result = subprocess.run(['timeout', '-k', '10', str(wall_budget), '/usr/bin/time', '-v', *argv],
                                cwd=repo, env=env, stdout=stdout, stderr=stderr)
    summary = {'exit_code': result.returncode, 'wall_seconds': time.monotonic() - start,
               'status': 'FAIL', 'completed_rows': 0}
    predictions = output / 'predictions.jsonl'
    if predictions.exists():
        rows = [json.loads(line) for line in predictions.open()]
        summary['completed_rows'] = len(rows)
        if result.returncode == 0 and len(rows) == count:
            stats = defaultdict(lambda: {'states': 0, 'leaf_cpu_seconds': 0, 'projection_steps': 0})
            for row in rows:
                st = stats[row['screen']]
                st['states'] += 1
                st['leaf_cpu_seconds'] += row['leafCpuSeconds']
                st['projection_steps'] += row['projectionSteps']
            summary.update(status='PASS', by_screen=dict(stats), predictions_sha256=digest(predictions))
    (output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if summary['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', type=Path, required=True)
    p.add_argument('--replay', action='append', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--count', type=int, default=512)
    p.add_argument('--replicates', type=int, default=1)
    p.add_argument('--wall-budget', type=int, default=600)
    a = p.parse_args()
    run(a.index.resolve(), [r.resolve() for r in a.replay], a.output.resolve(), a.count, a.replicates, a.wall_budget)
