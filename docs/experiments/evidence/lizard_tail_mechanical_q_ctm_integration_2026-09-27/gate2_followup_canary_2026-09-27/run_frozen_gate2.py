#!/usr/bin/env python3
import csv, hashlib, json, pathlib, subprocess, sys, time

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

manifest_path = pathlib.Path(sys.argv[1])
expected_manifest_sha = sys.argv[2]
manifest = json.loads(manifest_path.read_text())
if sha(manifest_path) != expected_manifest_sha:
    raise SystemExit('manifest SHA mismatch')
root = pathlib.Path(manifest['source']['working_directory'])
files = manifest['files']
for name, item in files.items():
    p = pathlib.Path(item['path'])
    actual = sha(p)
    if actual != item['sha256']:
        raise SystemExit(f'input SHA mismatch for {name}: {actual}')
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() != manifest['source']['commit']:
    raise SystemExit('HEAD changed after freeze')
if subprocess.check_output(['git', 'status', '--porcelain=v1'], cwd=root, text=True).strip():
    raise SystemExit('worktree is not clean')
out = manifest['output']
preflight = json.loads(pathlib.Path(out['preflight_guard_only_results_path']).read_text())
if preflight.get('manifest_sha256') != expected_manifest_sha or preflight.get('status') != 'PASS_NO_GAMEPLAY_STARTED' or len(preflight.get('checks', [])) != 16 or any(x.get('returncode') != 0 for x in preflight['checks']):
    raise SystemExit('frozen manifest preflight guard record missing or invalid')
for key in ('status_path','guard_only_results_path','guard_only_stdout_path'):
    if pathlib.Path(out[key]).exists():
        raise SystemExit(f'runner output collision: {out[key]}')
runs = manifest['runs']
seeds = list(range(991008, 991016))
if len(runs) != 16 or [r['seed'] for r in runs] != [s for s in seeds for _ in range(2)]:
    raise SystemExit('run list does not match frozen eight-pair cohort')
for i in range(0, len(runs), 2):
    control, treatment = runs[i:i+2]
    if control['arm'] != 'control' or treatment['arm'] != 'treatment' or control['seed'] != treatment['seed']:
        raise SystemExit('run pair order mismatch')
    ce, te = dict(control['environment']), dict(treatment['environment'])
    if ce.pop('STS_OOC_MCTS_ACTIVE_LIZARD') != '0' or te.pop('STS_OOC_MCTS_ACTIVE_LIZARD') != '1':
        raise SystemExit('arm switch mismatch')
    # Trace paths and source marker are the only per-run differences beyond the arm switch.
    ctrace, ttrace = ce.pop('STS_OOC_MCTS_TRACE'), te.pop('STS_OOC_MCTS_TRACE')
    if ce != te or ctrace == ttrace:
        raise SystemExit('pair environments diverge outside arm/trace')
    for r in (control, treatment):
        for key in ('result_path', 'sidecar_path', 'trace_path', 'actions_trace_path', 'support_trace_path', 'process_log_path'):
            if pathlib.Path(r[key]).exists():
                raise SystemExit(f'output collision: {r[key]}')
        if r['environment']['STS_EXECUTABLE_GIT_SHA'] != manifest['source']['commit']:
            raise SystemExit('per-run source marker mismatch')
        if r['argv'][-2] != str(r['seed']) or r['argv'][0:5] != ['bash', 'tools/seed_guard.sh', 'build/linux-gcc-release/one_combat', 'bestbench', '10000']:
            raise SystemExit('actual argv mismatch')
        if r['argv'][-1] != r['result_path']:
            raise SystemExit('result path mismatch')

def validate_output_contents(run, manifest):
    errors = []
    try:
        with open(run['result_path'], newline='') as f:
            rows = list(csv.DictReader(f))
        required_columns = {'seed','won','floor','act','hpEnd','maxHp','fightsLost','deathCombat','deathEncounter','sec'}
        if len(rows) != 1:
            errors.append(f'result CSV must contain exactly one data row; got {len(rows)}')
        elif not required_columns.issubset(rows[0]) or any(not rows[0].get(k) for k in required_columns):
            errors.append('result CSV row is missing required fields')
        elif int(rows[0]['seed']) != run['seed']:
            errors.append(f"result CSV seed mismatch: {rows[0]['seed']}")
    except Exception as e:
        errors.append(f'result CSV parse failed: {type(e).__name__}: {e}')
    try:
        sidecar = json.loads(pathlib.Path(run['sidecar_path']).read_text())
        cfg = sidecar.get('config', {})
        expected_argv = ['bestbench','10000','1','0',str(run['seed']),run['result_path']]
        expected_fields = {
            'objective': 'bestbench', 'nSeeds': 1, 'asc': 0, 'sims': 10000,
            'argv': expected_argv,
        }
        for key, value in expected_fields.items():
            if sidecar.get(key) != value:
                errors.append(f'sidecar {key} mismatch')
        if sidecar.get('seedBlock') != {'lo':run['seed'],'hi':run['seed']}:
            errors.append('sidecar seedBlock mismatch')
        for key, value in {
            'fairPlay': True, 'effectiveCombatBackend':'native_silver',
            'stsSilverSearchEffective':True, 'silverSearchEnabled':True,
            'silverReuseCapMode':'allocated',
            'executableGitSha':manifest['source']['commit'],
        }.items():
            if cfg.get(key) != value:
                errors.append(f'sidecar config {key} mismatch')
    except Exception as e:
        errors.append(f'sidecar parse/validation failed: {type(e).__name__}: {e}')
    try:
        log = pathlib.Path(run['process_log_path']).read_text(errors='replace')
        expected_active = run['active_lizard']
        expected_live = (
            f"[live OOC MCTS ON sims=2048 combat_model={manifest['files']['integration_candidate']['path']} "
            f"brew_fallback_model={manifest['files']['brew_fallback']['path']}"
        )
        if expected_live not in log or f'active_lizard_correction={expected_active}' not in log:
            errors.append('process log effective OOC model/arm configuration mismatch')
        telemetry_lines = [line.split('] ',1)[1] for line in log.splitlines() if line.startswith('[ooc-combat-transition] ')]
        if len(telemetry_lines) != 1:
            errors.append(f'expected one OOC telemetry record; got {len(telemetry_lines)}')
        else:
            telemetry = json.loads(telemetry_lines[0])
            if telemetry.get('seed') != run['seed'] or telemetry.get('activeLizardEnabled') != (expected_active == '1'):
                errors.append('OOC telemetry seed/arm mismatch')
    except Exception as e:
        errors.append(f'process log validation failed: {type(e).__name__}: {e}')
    return errors

launcher = files['env_launcher']['path']
run_root = pathlib.Path(manifest['output']['directory'])
guard_records = []
with open(manifest['output']['guard_only_stdout_path'], 'xb') as out:
    for r in runs:
        env = [f'{k}={v}' for k, v in sorted(r['environment'].items())]
        argv = [launcher, '-i', *env, 'bash', 'tools/seed_guard.sh', 'guard-only', *r['argv'][2:]]
        cp = subprocess.run(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT)
        guard_records.append({'seed': r['seed'], 'arm': r['arm'], 'argv': argv, 'returncode': cp.returncode})
if any(x['returncode'] != 0 for x in guard_records):
    raise SystemExit('a guard-only preflight failed; no gameplay seeds were started')
with open(manifest['output']['guard_only_results_path'], 'x') as f:
    json.dump({'manifest_sha256': expected_manifest_sha, 'status': 'PASS_NO_GAMEPLAY_STARTED', 'checks': guard_records}, f, indent=2)
    f.write('\n')
status_file = pathlib.Path(manifest['output']['status_path'])
for index, r in enumerate(runs, start=1):
    env = [f'{k}={v}' for k, v in sorted(r['environment'].items())]
    argv = [launcher, '-i', *env, *r['argv']]
    print(f"START {index}/16 seed={r['seed']} arm={r['arm']}", flush=True)
    started = time.time()
    with open(r['process_log_path'], 'wb') as out:
        cp = subprocess.run(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    ended = time.time()
    required = [r['result_path'], r['sidecar_path'], r['trace_path'], r['actions_trace_path'], r['support_trace_path'], r['process_log_path']]
    missing = [p for p in required if not pathlib.Path(p).is_file() or pathlib.Path(p).stat().st_size == 0]
    content_errors = validate_output_contents(r, manifest) if cp.returncode == 0 and not missing else []
    record = {
        'index': index, 'seed': r['seed'], 'arm': r['arm'], 'argv': argv,
        'returncode': cp.returncode, 'started_unix': started, 'ended_unix': ended,
        'elapsed_seconds': round(ended - started, 3), 'missing_or_empty_required_outputs': missing, 'content_validation_errors': content_errors,
        'result_sha256': sha(r['result_path']) if pathlib.Path(r['result_path']).is_file() else None,
        'sidecar_sha256': sha(r['sidecar_path']) if pathlib.Path(r['sidecar_path']).is_file() else None,
        'trace_sha256': sha(r['trace_path']) if pathlib.Path(r['trace_path']).is_file() else None,
        'process_log_sha256': sha(r['process_log_path']) if pathlib.Path(r['process_log_path']).is_file() else None,
    }
    with open(status_file, 'a') as f:
        f.write(json.dumps(record, sort_keys=True) + '\n')
        f.flush()
    print(f"DONE {index}/16 seed={r['seed']} arm={r['arm']} rc={cp.returncode} elapsed={record['elapsed_seconds']}s missing={len(missing)}", flush=True)
    if cp.returncode != 0 or missing or content_errors:
        print('STOP: incomplete process/output; no further seeds or replacements will run', flush=True)
        raise SystemExit(1)
print('COHORT_PROCESSES_COMPLETE=16', flush=True)
