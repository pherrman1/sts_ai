#!/usr/bin/env python3
"""One bounded execution of the unchanged adapter on a frozen qualified fight."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    subprocess.run(['python3', str(HERE / 'freeze_roots.py'), '--check'], check=True)
    manifest_path = HERE / 'selection.json'
    manifest = json.loads(manifest_path.read_text())
    assert 0 < len(manifest['selected']) <= 4
    inputs = HERE / 'inputs.jsonl'
    assert sha(inputs) == manifest['inputs_sha256']
    binary = REPO / 'build/linux-gcc-release-ccache/combat_infinity_oracle'
    assert sha(binary) == manifest['oracle_binary_sha256']
    paths = {suffix: HERE / f'oracle.{suffix}' for suffix in ['jsonl', 'stderr.txt', 'receipt.json']}
    assert not any(p.exists() for p in paths.values()), 'never rerun a frozen batch'
    command = ['timeout', '30s', 'bash', 'tools/seed_guard.sh', str(binary), '--public-roots', str(inputs)]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    with paths['jsonl'].open('xb') as out, paths['stderr.txt'].open('xb') as err:
        result = subprocess.run(command, cwd=REPO, stdout=out, stderr=err)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt = {'seed': 111101032, 'command': command, 'returncode': result.returncode,
               'selection_sha256': sha(manifest_path), 'inputs_sha256': sha(inputs),
               'output_sha256': sha(paths['jsonl']), 'stderr_sha256': sha(paths['stderr.txt']),
               'adapter_binary_sha256': sha(binary), 'wall_seconds': time.monotonic() - start,
               'child_user_seconds': after.ru_utime - before.ru_utime,
               'child_system_seconds': after.ru_stime - before.ru_stime}
    paths['receipt.json'].write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
