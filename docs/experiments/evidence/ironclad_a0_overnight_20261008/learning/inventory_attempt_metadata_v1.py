#!/usr/bin/env python3
"""Read only receipt/job metadata and named diagnostic artifacts; never read game rows."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[5]
EV = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008'
RAW = ROOT / 'build/overnight_20261008'


def now():
    return datetime.now(timezone.utc).isoformat()


def absolute(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def read_bound(path):
    p = absolute(path)
    before = p.stat()
    data = p.read_bytes()
    after = p.stat()
    stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return data, dict(path=str(p), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      stable_during_read=stable, observed_mtime_ns=after.st_mtime_ns)


def bound(path):
    return read_bound(path)[1]


def load(path):
    raw, identity = read_bound(path)
    return json.loads(raw), identity


def classify(d):
    if d.get('status') == 'completed' and d.get('exit_code') == 0:
        return 'completed_exit0'
    if d.get('status') == 'running' and d.get('exit_code') is None:
        return 'pending_running'
    if d.get('status') == 'timeout':
        return 'timeout'
    if d.get('status') == 'failed' or d.get('exit_code') not in (None, 0):
        return 'failed'
    return 'unresolved_status'


def receipt_record(path):
    d, identity = load(path)
    keys = ('schema', 'status', 'exit_code', 'stage', 'arm', 'source_seed', 'command',
            'started_epoch', 'finished_epoch', 'wall_seconds', 'source_sha',
            'binary_sha256', 'manifest', 'manifest_sha256', 'freeze', 'freeze_sha256')
    out = {**identity, **{k: d[k] for k in keys if k in d}}
    out['classification'] = classify(d) if identity['stable_during_read'] else 'unstable_read'
    cmd = d.get('command', [])
    if 'bestbench' in cmd:
        i = cmd.index('bestbench')
        out.update(kind='full_run_shard', requested_runs=int(cmd[i+2]), seed_lo=int(cmd[i+4]))
    elif 'ooccfpilotgen' in cmd:
        i = cmd.index('ooccfpilotgen')
        out.update(kind='source_with_conditional_branches', source_seed=int(cmd[i+3]),
                   allocated_futures_per_option=int(cmd[i+5]))
    elif any(Path(x).name == 'silver_public_pair_probe' for x in cmd):
        out['kind'] = 'public_combat_check' if d.get('stage') == 'check' else 'public_combat_pair'
    else:
        out['kind'] = 'unrecognized_command'
    return out


def joblists(receipts):
    result = []
    for path in sorted(RAW.glob('*jobs.txt')):
        data, identity = read_bound(path)
        jobs = []
        for line_no, line in enumerate(data.decode().splitlines(), 1):
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            tokens = shlex.split(line)
            item = dict(line=line_no)
            if path.name == 'champ_d13_jobs.txt' and len(tokens) == 1 and tokens[0].isdigit():
                target = RAW / f'champ_d13/evaluation-{int(tokens[0]):02}.receipt.json'
            elif '--prefix' in tokens:
                target = absolute(tokens[tokens.index('--prefix')+1] + '.receipt.json')
            elif len(tokens) == 5 and tokens[2].isdigit() and tokens[3].isdigit():
                target = absolute(tokens[4] + '.receipt.json')
                item.update(arm=tokens[1], seed_lo=int(tokens[2]), requested_runs=int(tokens[3]))
            else:
                jobs.append(dict(line=line_no, classification='unsupported_job_format'))
                continue
            if not target.is_relative_to(RAW):
                raise ValueError(f'job receipt outside campaign: {target}')
            item['receipt_path'] = str(target)
            item['classification'] = receipts.get(str(target), {}).get('classification', 'not_started_at_receipt_snapshot')
            jobs.append(item)
        result.append({**identity, 'counts':dict(Counter(j['classification'] for j in jobs)), 'jobs':jobs})
    return result


def named_events():
    # Curated from preserved campaign evidence. References are hashed, never modified.
    events = []
    def add(name, category, resolution, refs, **extra):
        events.append(dict(name=name, category=category, resolution=resolution,
                           evidence=[bound(p) for p in refs], **extra))
    add('shop feature regression fixture', 'expected_negative_fixture',
        'Pre-fix synthetic fixture failed; corrected focused fixture passed. No seed run.',
        ['build/overnight-shop-baseline-fail.log', 'build/overnight-shop-fixed-test.log'])
    add('optional Recall regression fixture', 'expected_negative_fixture',
        'Pre-fix synthetic fixture failed; corrected focused fixture passed. No seed run.',
        ['build/overnight-recall-baseline-fail.log', 'build/overnight-recall-fixed-test.log'])
    moved, moved_id = load(EV/'audit/recall_build_logs_manifest.json')
    for item in moved['files']:
        actual = bound(item['retained_raw_path'])
        if actual['sha256'] != item['sha256'] or actual['bytes'] != item['bytes']:
            raise ValueError('relocated compiler log custody mismatch')
    add('missing rest_recall_filter_test build target', 'build_orchestration_failure',
        'CMake target absent before reconfigure; preserved reconfigure and v2 build show repair. No game. Explicit exit code was not recorded in the text log.',
        [EV/'audit/recall_build_logs_manifest.json'] + [x['retained_raw_path'] for x in moved['files']],
        diagnostic="gmake: *** No rule to make target 'rest_recall_filter_test'.  Stop.",
        relocation_manifest=moved_id, prior_locations=[x['original_path'] for x in moved['files']])
    add('targeted REST wrong target hash', 'prelaunch_rejection',
        'Hash gate rejected before binary launch or output creation; corrected later invocation separately receipted.',
        [EV/'learning/targeted_rest_launcher_failure001.json'], source_runs=0, continuations=0)
    add('GEN2 source-only profiler seed verifier', 'postcollection_validator_defect',
        'Original INVALID preserved. Reviewed exact derived-seed membership repair passed v2 on unchanged collection; no recollection. This did not establish a failed game.',
        [EV/'learning/gen2_canary_3ed9/contract_receipt.json',
         EV/'learning/gen2_canary_3ed9/contract_receipt_v2.json',
         EV/'learning/gen2_canary_3ed9/profile_seed_fix_review.json',
         EV/'learning/verify_gen2_v1.py', EV/'learning/verify_gen2.py',
         EV/'learning/GEN2_PROFILE_SEED_DIAGNOSIS.md'])
    add('GEN2 seed verifier synthetic test identity mismatch', 'test_fixture_defect',
        'One fixture used decision36 with expected decision71 seed set. Fixture corrected; five focused tests and independent review passed. Historical pending-review status remains unchanged.',
        [EV/'learning/gen2_profile_seed_fix_checks.json',
         EV/'learning/gen2_canary_3ed9/profile_seed_fix_review.json'])
    add('old 736d GEN2 freeze', 'superseded_unlaunched_proposal',
        'Superseded before collection to include Recall correction; source seeds later consumed only by separately frozen corrected producer.',
        [EV/'learning/gen2_canary_736d/freeze.json', EV/'learning/gen2_canary_736d/superseded-unlaunched.json'], source_runs=0)
    return events


def startup_checks():
    checks = []
    for rel in ['audit/startup_rejections.json', 'audit/corrected_startup_rejections.json',
                'audit/fullhp-build-static-checks.json', 'audit/removal-static-checks.json',
                'audit/cardrank-static-checks.json']:
        d, identity = load(EV/rel)
        rows = d.get('checks', d.get('tests'))
        if rows is None:
            rows = [dict(name=k, **v) for k,v in d.items()]
        for x in rows:
            if x.get('exit_code', 0) == 0:
                continue
            row = dict(name=x['name'], exit_code=x['exit_code'], evidence=identity,
                       classification='expected_startup_rejection_no_game')
            if 'log' in x:
                row['log'] = bound(x['log'])
                if row['log']['sha256'] != x['log_sha256']:
                    raise ValueError('startup log custody mismatch')
            checks.append(row)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    outputs = [Path(str(args.output_prefix)+suffix).resolve() for suffix in ('.json', '.md')]
    if any(p.exists() for p in outputs):
        raise FileExistsError('Refusing to replace existing accounting; choose a new versioned prefix')
    if any(not p.is_relative_to(EV/'learning') for p in outputs):
        raise ValueError('accounting output must be under campaign learning directory')
    started = now()
    receipts = {}
    errors = []
    for path in sorted(RAW.rglob('*.receipt.json')):
        try:
            receipts[str(path)] = receipt_record(path)
        except (ValueError, KeyError, IndexError, OSError) as exc:
            errors.append(dict(path=str(path), classification='unreadable_receipt', error=str(exc)))
    groups = defaultdict(Counter)
    kinds = defaultdict(Counter)
    for row in receipts.values():
        group = str(Path(row['path']).parent.relative_to(RAW))
        groups[group][row['classification']] += 1
        kinds[row['kind']][row['classification']] += 1
    jobs = joblists(receipts)
    status = Counter(x['classification'] for x in receipts.values())
    pending_jobs = [j for f in jobs for j in f['jobs'] if j['classification'] != 'completed_exit0']
    data = dict(schema='overnight_attempt_metadata_snapshot_v1', started_utc=started,
                script=bound(__file__), scope='Receipt and job metadata, named diagnostic evidence only. No CSV/JSONL game outcomes, protected TEST or holdout numerical contents read.',
                limitations=['Snapshot is not an atomic view of the running campaign; each file has its own stable-read flag.',
                             'A completed exit0 receipt is invocation status, not independent runtime validity or policy strength.',
                             'Only preserved receipts and named diagnostic evidence are accounted; unsaved terminal-only attempts cannot be reconstructed.',
                             'Build logs without recorded process exit metadata are not assigned invented exit codes.',
                             'Synthetic rejection tests are not failed campaign games; queued jobs are not yet attempts.'],
                receipt_counts=dict(status), groups={k:dict(v) for k,v in sorted(groups.items())},
                kinds={k:dict(v) for k,v in sorted(kinds.items())},
                runtime_receipts=list(receipts.values()), unreadable_receipts=errors,
                joblists=jobs, pending_or_unresolved_jobs=pending_jobs,
                named_events=named_events(), expected_startup_rejections=startup_checks())
    data['finished_utc'] = now()
    data['snapshot_status'] = 'PENDING_OR_UNRESOLVED' if pending_jobs or errors or any(k != 'completed_exit0' for k in status) else 'ALL_INVENTORIED_INVOCATIONS_COMPLETE'
    with outputs[0].open('x') as f:
        json.dump(data,f,indent=2); f.write('\n')
    lines = ['# Campaign attempt accounting', '',
             f"Metadata snapshot {started} to {data['finished_utc']}. **{data['snapshot_status']}**.", '',
             f"Inventoried {len(receipts)} runtime receipts: " + ', '.join(f'{n} {k}' for k,n in sorted(status.items())) + '.', '',
             'This is invocation accounting, not a quality or validity verdict. No numerical game outcomes were read. Pending jobs are excluded from completion.', '',
             '| Receipt directory | Status counts |', '|---|---|']
    lines += [f"| `{g}` | " + ', '.join(f'{n} {s}' for s,n in counts.items()) + ' |' for g,counts in data['groups'].items()]
    lines += ['', f"Expected strict startup negatives: **{len(data['expected_startup_rejections'])}**; all occur before game execution. Negative signal exit codes are retained exactly.", '',
              '| Preserved event | Classification | Resolution |', '|---|---|---|']
    lines += [f"| {e['name']} | `{e['category']}` | {e['resolution']} |" for e in data['named_events']]
    lines += ['', 'The JSON records every runtime receipt path/hash, command, timestamps, status and source/binary identity; every joblist path/hash and expected receipt; and exact paths/hashes for the named events and startup rejections.', '',
              'Pending or unresolved scheduled jobs:', '']
    lines += [f"- `{j.get('receipt_path', 'unsupported job')}`: `{j['classification']}`." for j in pending_jobs] or ['None in this snapshot.']
    lines += ['', 'Limits:', ''] + ['- '+s for s in data['limitations']]
    lines += ['', f"JSON SHA256: `{bound(outputs[0])['sha256']}`.", '',
              'Refresh after dispatchers stop using a new output prefix; this script refuses overwrites:', '',
              '```sh', f'.venv/bin/python {Path(__file__).relative_to(ROOT)} --output-prefix {str(args.output_prefix)}_v2', '```', '',
              'Knowledge impact: experiment evidence accounting only; no new runtime or policy claim.']
    with outputs[1].open('x') as f:
        f.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(status=data['snapshot_status'], receipt_counts=data['receipt_counts'],
                          pending_jobs=len(pending_jobs), unreadable=len(errors),
                          expected_startup_rejections=len(data['expected_startup_rejections']),
                          outputs=[bound(p) for p in outputs]), indent=2))


if __name__ == '__main__':
    main()
