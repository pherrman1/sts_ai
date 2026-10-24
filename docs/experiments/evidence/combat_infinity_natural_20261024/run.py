#!/usr/bin/env python3
"""Execute each frozen batch once, with the seed guard and a 30-second timeout."""
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time
from prepare import E, ROOT, generate

for name, content in generate().items():
    assert (E / name).read_bytes() == content.encode(), name
for batch in range(4):
    for suffix in ('jsonl', 'stderr.txt', 'receipt.json'):
        assert not (E / f'output-{batch}.{suffix}').exists(), 'pilot already started; no automatic retry'
for batch in range(4):
    command = ['timeout', '30s', 'bash', 'tools/seed_guard.sh',
               'build/linux-gcc-release-ccache/combat_infinity_oracle', '--public-roots',
               str((E / f'inputs-{batch}.jsonl').relative_to(ROOT))]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    with (E / f'output-{batch}.jsonl').open('xb') as out, (E / f'output-{batch}.stderr.txt').open('xb') as err:
        completed = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err)
    elapsed = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt = {'command': command, 'returncode': completed.returncode, 'wall_seconds': elapsed,
               'child_user_seconds': after.ru_utime - before.ru_utime,
               'child_system_seconds': after.ru_stime - before.ru_stime,
               'output_sha256': hashlib.sha256((E / f'output-{batch}.jsonl').read_bytes()).hexdigest(),
               'stderr_sha256': hashlib.sha256((E / f'output-{batch}.stderr.txt').read_bytes()).hexdigest(),
               'frozen_protocol_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    (E / f'output-{batch}.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'batch': batch, 'returncode': completed.returncode, 'wall_seconds': elapsed}), flush=True)
    if completed.returncode != 0:
        raise SystemExit('stopped at failed batch; preserve evidence, no retry')
