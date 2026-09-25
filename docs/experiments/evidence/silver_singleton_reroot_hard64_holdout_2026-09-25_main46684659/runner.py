from pathlib import Path
import json
import subprocess
import sys
import time

control_root = Path('/tmp/sts-singleton-main-control-46684659')
treatment_root = Path('/home/philippherrmann/.codex/worktrees/e796/sts_lightspeed')
input_path = control_root / 'docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-holdout-snapshots.jsonl'
out_root = Path('/tmp/sts-singleton-n64-main46684659')
lines = [line for line in input_path.read_text().splitlines() if line.strip()]
rows = [json.loads(line) for line in lines]
case_ids = [row['case_id'] for row in rows]
if len(rows) != 64 or len(set(case_ids)) != 64:
    raise SystemExit(f'expected 64 unique frozen rows, got rows={len(rows)} unique={len(set(case_ids))}')

chunk_paths = []
for block in range(8):
    chunk = out_root / f'input-block-{block + 1:02}.jsonl'
    chunk.write_text('\n'.join(lines[block * 8:(block + 1) * 8]) + '\n')
    chunk_paths.append(chunk)

order = []
arm_rows = {'control': [], 'treatment': []}
roots = {'control': control_root, 'treatment': treatment_root}
binaries = {
    'control': control_root / 'build/linux-gcc-release/silver_hard_combat_replay',
    'treatment': treatment_root / 'build/linux-gcc-release/silver_hard_combat_replay',
}
for block, chunk in enumerate(chunk_paths):
    first = 'control' if block % 2 == 0 else 'treatment'
    arms = [first, 'treatment' if first == 'control' else 'control']
    record = {
        'block': block + 1,
        'case_count': 8,
        'case_ids': case_ids[block * 8:(block + 1) * 8],
        'run_order': arms,
        'runs': [],
    }
    for arm in arms:
        root = roots[arm]
        cmd = [
            'env', 'OMP_NUM_THREADS=4', 'bash', str(root / 'tools/seed_guard.sh'),
            str(binaries[arm]), str(chunk), '10000',
        ]
        if arm == 'treatment':
            cmd.append('--skip-singleton-search')
        started = time.monotonic()
        print(f'START block={block + 1} arm={arm}', flush=True)
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        elapsed = time.monotonic() - started
        stdout_path = out_root / f'block-{block + 1:02}-{arm}.jsonl'
        stderr_path = out_root / f'block-{block + 1:02}-{arm}.stderr.txt'
        stdout_path.write_text(proc.stdout)
        stderr_path.write_text(proc.stderr)
        parsed = []
        for output_line in proc.stdout.splitlines():
            if output_line.strip():
                parsed.append(json.loads(output_line))
        arm_rows[arm].extend(parsed)
        failed = sum(row.get('status') != 'ok' for row in parsed)
        record['runs'].append({
            'arm': arm,
            'command': cmd,
            'cwd': str(root),
            'exit_code': proc.returncode,
            'elapsed_seconds': elapsed,
            'stdout_file': stdout_path.name,
            'stderr_file': stderr_path.name,
            'rows': len(parsed),
            'non_ok_rows': failed,
        })
        print(f'DONE block={block + 1} arm={arm} rc={proc.returncode} rows={len(parsed)} non_ok={failed} elapsed={elapsed:.3f}s', flush=True)
    order.append(record)
    (out_root / 'run-progress.json').write_text(json.dumps(order, indent=2) + '\n')

for arm, parsed in arm_rows.items():
    got = [row.get('case_id') for row in parsed]
    if len(got) != 64 or sorted(got) != sorted(case_ids):
        raise SystemExit(f'{arm}: expected one output for each of 64 cases; got {len(got)} rows')
    (out_root / f'{arm}.jsonl').write_text('\n'.join(json.dumps(row, sort_keys=True) for row in parsed) + '\n')

(out_root / 'run-order.json').write_text(json.dumps(order, indent=2) + '\n')
print('COMPLETE control_rows=64 treatment_rows=64', flush=True)
