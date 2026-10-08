#!/usr/bin/env python3
"""Independent, read-only audit of the already completed fixed final trial."""
import collections
import csv
import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import numpy as np

R = Path(__file__).resolve().parents[5]
E = R / 'docs/experiments/evidence/ironclad_a0_overnight_20261008'
A = E / 'audit'
D = R / 'build/overnight_20261008/final_confirmation'
SOURCE = 'd35b42b1d5dc9819ec0f157027c68912bb82b8b7'
control_inputs = {}

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def bind(p, expected=None):
    p = Path(p).resolve()
    h = sha(p)
    assert expected is None or h == expected, ('hash mismatch', str(p), expected, h)
    control_inputs[str(p)] = h
    return h

def read(p, expected=None):
    bind(p, expected)
    return json.loads(Path(p).read_text())

report_path = E / 'final_confirmation_report.json'
report = read(report_path, '56af59f69b2e2040f0f4673c245e962634e34f2f828f4351892f01c3139c8ce9')
manifest_path = E / 'protocols/final_confirmation.json'
m = read(manifest_path, report['manifest_sha256'])
freeze = read(E / 'champion_freeze.json')
latch = read(E / 'holdout_opened.json', 'eadbf3663ad340925e7c3cc2d0ba53846e64251a108a7e014de44e291126674e')
completion = read(A / 'final_execution_completion.json', '720fe902253296cae4a50991947f3d72e32739d1acf07f72012d9b2341a8c83a')
dispatch = read(E / 'protocols/final_confirmation_dispatch.json')
health = read(A / 'final_confirmation_health.json', '29b11028411eb0f07eb22df0a66ddaf93f20f5284e75b278e02201b24942b2c0')
health_invocation = read(A / 'final_confirmation_health_invocation.json')
for p, h in latch['bound_inputs'].items():
    bind(p, h)
for p, h in m['artifacts'].items():
    bind(R / p, h)
for role in ('source_review', 'runtime_receipt', 'static_receipt'):
    bind(E / m['gates'][role], m['gates'][role + '_sha256'])
for name, h in freeze['development_reports'].items():
    bind(E / name, h)
bind(m['binary'], m['binary_sha256'])
bind(m['runtime']['python_executable'], m['runtime']['python_executable_sha256'])
assert Path(sys.executable).resolve() == Path(m['runtime']['python_executable']).resolve()
assert sys.version == m['runtime']['python'] and np.__version__ == m['runtime']['numpy']
assert subprocess.check_output(['git', 'rev-parse', SOURCE+'^{commit}'], cwd=R, text=True).strip() == SOURCE
assert m['source_sha'] == report['source_sha'] == freeze['source_sha'] == latch['source_sha'] == SOURCE
assert m['binary_sha256'] == report['binary_sha256'] == freeze['binary_sha256'] == latch['binary_sha256']
assert m['allowed_seeds'] == m['analysis_seeds'] == list(range(610083000, 610083512))
assert m['analysis_arms'] == ['Fprod', 'RemoveLow'] and m['comparisons'] == [['RemoveLow', 'Fprod']]
profiles = {a: dict(m['profiles']['common'], **m['profiles']['arms'][a]) for a in m['analysis_arms']}
difference = {k:[profiles['Fprod'].get(k), profiles['RemoveLow'].get(k)] for k in set(profiles['Fprod'])|set(profiles['RemoveLow']) if profiles['Fprod'].get(k) != profiles['RemoveLow'].get(k)}
assert difference == freeze['profile_difference'] == {'STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT':['0','1']}
assert freeze['unopened_check']['source_overlap'] is False and freeze['unopened_check']['confirmation_output_directory_absent'] is True
assert latch['prelaunch_existing_output_count'] == 0 and not latch['prelaunch_owned_workers']
assert completion['dispatcher_exit_code'] == 0 and completion['completed_shards'] == completion['expected_shards'] == 256
assert completion['failed_shards'] == completion['timed_out_shards'] == 0 and not completion['owned_game_processes']
assert completion['manifest_sha256'] == dispatch['manifest_sha256'] == sha(manifest_path)
assert completion['latch_sha256'] == dispatch['latch_sha256'] == sha(E/'holdout_opened.json')
assert dispatch['workers'] == latch['worker_limit'] == m['max_workers'] == 6
assert dispatch['shard_timeout_seconds'] == latch['shard_timeout_seconds'] == m['timeout_seconds_per_shard'] == 900
assert freeze['frozen_epoch'] < latch['opened_epoch'] < completion['started_epoch'] <= completion['finished_epoch'] <= completion['recorded_epoch']
assert completion['recorded_epoch'] < report_path.stat().st_mtime <= health_invocation['started_epoch']
assert health_invocation['exit_code'] == 0 and health_invocation['output_sha256'] == sha(A/'final_confirmation_health.json')
assert health_invocation['report_sha256'] == sha(report_path)
assert health_invocation['auditor_sha256'] == sha(A/'audit_fullrun_health.py') == m['health_auditor_sha256']
bind(A/'final_confirmation_health.log', health_invocation['log_sha256'])
# Frozen validator function re-execution creates no report and calls no simulator.
spec = importlib.util.spec_from_file_location('frozen_final_analysis', E/'analyze_wave_removal.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
validated = module.analyze(manifest_path, D)
assert validated == report, 'frozen analyzer did not reproduce the original report exactly'
# Every fixed job has one receipt and exactly the expected seven output files.
jobs_path = Path(m['jobs']['path']); bind(jobs_path, m['jobs']['sha256'])
jobs = [shlex.split(line) for line in jobs_path.read_text().splitlines()]
assert len(jobs) == 256 and len({tuple(x) for x in jobs}) == 256
receipts = {Path(x['path']):json.loads(Path(x['path']).read_text()) for x in completion['receipts']}
assert len(receipts) == 256 and set(receipts) == set(D.glob('*.receipt.json'))
expected_files = set(receipts)
for i, x in enumerate(jobs):
    assert len(x) == 5
    mp, arm, low, count, prefix = x
    block = i // 2
    expected_order = ['Fprod','RemoveLow'] if block % 2 == 0 else ['RemoveLow','Fprod']
    assert arm == expected_order[i % 2] and int(low) == 610083000 + 4*block and int(count) == 4
    assert Path(mp).resolve() == manifest_path and Path(prefix) == D / f'{arm}_{block}'
    rp = Path(prefix+'.receipt.json'); q=receipts[rp]
    assert q['status'] == 'completed' and q['exit_code'] == 0
    assert q['command'] == ['bash','tools/seed_guard.sh',m['binary'],'bestbench','10000','4','0',low,prefix+'.csv']
    assert latch['opened_epoch'] < q['started_epoch'] < q['finished_epoch'] <= completion['finished_epoch']
    assert q['wall_seconds'] < 900
    assert set(q['outputs']) == {'csv','meta','log','trace','tree','profile','strategic'}
    expected_files.update(Path(v['path']) for v in q['outputs'].values())
for item in completion['receipts']:
    assert sha(item['path']) == item['sha256']
assert expected_files == set(p for p in D.iterdir() if p.is_file()), 'extra/missing attempt/output file'
assert min(q['started_epoch'] for q in receipts.values()) == completion['started_epoch']
assert max(q['finished_epoch'] for q in receipts.values()) == completion['finished_epoch']
events = sorted([(q['started_epoch'],1) for q in receipts.values()]+[(q['finished_epoch'],-1) for q in receipts.values()])
active=peak=0
for _, delta in events:
    active+=delta;peak=max(peak,active)
assert active == 0 and peak <= 6
dispatch_log=R/'build/overnight_20261008/final_confirmation_dispatch.log';bind(dispatch_log)
dispatch_rows=[json.loads(line) for line in dispatch_log.read_text().splitlines()]
assert len(dispatch_rows)==256 and all(x['status']=='completed' and x['exit_code']==0 for x in dispatch_rows)
assert collections.Counter((q['arm'],q['wall_seconds']) for q in receipts.values()) == collections.Counter((q['arm'],q['wall_seconds']) for q in dispatch_rows)
# Independent CSV parser and arithmetic; do not call paired_analysis.bootstrap_ci.
wins={a:{} for a in profiles}
for q in receipts.values():
    with Path(q['outputs']['csv']['path']).open(newline='') as f:
        part=list(csv.DictReader(f))
    assert len(part)==4
    for row in part:
        s=int(row['seed']); w=int(row['won'])
        assert s not in wins[q['arm']] and w in (0,1)
        wins[q['arm']][s]=w
assert all(set(v)==set(m['analysis_seeds']) for v in wins.values())
delta=np.array([wins['RemoveLow'][s]-wins['Fprod'][s] for s in sorted(wins['Fprod'])],dtype=np.float64)
rng=np.random.default_rng(20261008)
# Same draws/order as the frozen per-replicate loop, independently vectorized.
means=delta[rng.integers(0,512,size=(10000,512))].mean(axis=1)
ci=np.percentile(means,[(1-.95)/2*100,(1+.95)/2*100]).tolist()
counts={'pairs':512,'gain':float(delta.mean()),'ci95':ci,'candidate_only':int((delta>0).sum()),'control_only':int((delta<0).sum()),'both_win':sum(wins['Fprod'][s]==wins['RemoveLow'][s]==1 for s in wins['Fprod'])}
counts['decision']='CONFIRMED_IMPROVEMENT' if counts['gain']>=.02 and ci[0]>0 else 'NO_CONFIRMED_IMPROVEMENT'
assert counts == report['comparisons']['RemoveLow-Fprod']
assert {a:sum(v.values()) for a,v in wins.items()} == {a:x['wins'] for a,x in report['arms'].items()}
# Independent complete tree census and conservation, without calling the health auditor.
health_counts={a:{'roots':0,'completed_simulations':0,'singleton_skips':0,'error_strings':{},'descent_aborts':0,'cycle_rollouts':0,'rollout_calls':0,'nonterminal_rollout_starts':0,'endpoints':{k:0 for k in ['victory','death','turn_limit','engine_stop','nonterminal']}} for a in profiles}
per_seed={a:collections.Counter() for a in profiles}; limit_roots=collections.Counter()
for q in receipts.values():
    arm=q['arm']; out=health_counts[arm]; seen=set()
    expected=set(range(int(q['command'][7]),int(q['command'][7])+4))
    with Path(q['outputs']['tree']['path']).open() as f:
        for line in f:
            x=json.loads(line);s=int(x['seed']);assert s in expected
            ident=(s,x['combat_id'],x['decision']);assert ident not in seen;seen.add(ident)
            assert x['schema']==1 and not x['adaptive'] and x['configured_simulations']==10000
            assert not x['error'] and x['descent_aborts']==0
            n=x['completed_simulations'];assert n>=0
            if x['singleton_skip']:assert x['root_actions']==1 and n==0
            else:assert n in {250,500,1000,2000,4000,8000,10000}
            assert x['heuristic_evaluations']==n and x['neural_evaluations']==0
            assert 0<=x['nonterminal_rollout_starts']<=x['rollout_calls']<=n
            assert 0<=x['cycle_rollouts']<=x['rollout_calls']
            assert set(x['endpoints'])==set(out['endpoints'])
            assert sum(v['count'] for v in x['endpoints'].values())==n
            for k,v in x['endpoints'].items():
                assert v['count']>=0
                assert all(type(count)is int and count>=0 for field in ['tree_depth','total_depth'] for count in v[field].values())
                assert sum(v['tree_depth'].values())==sum(v['total_depth'].values())==v['count']
                assert sum(int(k)*c for k,c in v['total_depth'].items())>=sum(int(k)*c for k,c in v['tree_depth'].items())
                out['endpoints'][k]+=v['count']
            assert x['endpoints']['nonterminal']['count']==0
            if x['endpoints']['turn_limit']['count'] or x['endpoints']['engine_stop']['count']:limit_roots[arm]+=1
            out['roots']+=1;per_seed[arm][s]+=1;out['singleton_skips']+=int(x['singleton_skip'])
            for k in ['completed_simulations','descent_aborts','cycle_rollouts','rollout_calls','nonterminal_rollout_starts']:out[k]+=x[k]
assert health_counts==health['arms']
assert not health['fatal_contract_findings'] and health['status']=='PASS_WITH_DIAGNOSTIC_LIMITS'
for arm in profiles:
    assert set(per_seed[arm])==set(m['analysis_seeds'])
    assert dict(per_seed[arm])=={int(s):v['roots'] for s,v in health['per_arm_seed'][arm].items()}
assert sum(limit_roots.values())==len(health['diagnostic_safety_limits'])
# The audit produces a new receipt only, refusing replacement.
bind(__file__)
output={
 'schema':'final_confirmation_independent_review_v1',
 'status':'PASS_EXECUTION_VALIDITY_AND_REPRODUCED_PRIMARY_RESULT',
 'reviewed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'original_raw_verdict':report['comparisons']['RemoveLow-Fprod']['decision'],
 'primary_recomputed':dict(counts,neither_win=512-counts['both_win']-counts['candidate_only']-counts['control_only']),
 'arm_wins':{a:sum(v.values()) for a,v in wins.items()},
 'checks':{'frozen_analyzer_report_exactly_reproduced':True,'independent_raw_csv_arithmetic_and_bootstrap':True,'all_2048_report_inputs_rehashed':True,'all256_receipts_rehashed':True,'source_binary_models_runner_analyzer_runtime_bound':True,'only_profile_difference':difference,'fixed_job_order_and_allocation_exact':True,'no_missing_duplicate_extra_or_retry_outputs':True,'dispatcher_log_matches_all_receipts':True,'all_shards_under900s':True,'max_concurrent_receipt_intervals':peak,'latch_precedes_every_invocation':True,'completion_precedes_report_filesystem_mtime':True,'independent_all_tree_health_census':True,'source_seed_coverage_per_arm':512},
 'execution':{'runs':1024,'shards':256,'start_epoch':completion['started_epoch'],'finish_epoch':completion['finished_epoch'],'elapsed_seconds':completion['finished_epoch']-completion['started_epoch'],'freeze_epoch':freeze['frozen_epoch'],'opened_epoch':latch['opened_epoch'],'producer_source':SOURCE,'binary_sha256':m['binary_sha256'],'python':sys.version,'numpy':np.__version__},
 'health':{'status':health['status'],'arms':health_counts,'diagnostic_limit_roots':dict(limit_roots),'fatal_findings':[]},
 'scope':['One preregistered final contrast on512 fresh paired IroncladA0 Act3 seeds under the public8/Recall1/nativeSilver learned-stop profile.','Observed2.734375pp gain meets the2pp point-estimate floor and paired95% lower bound is positive; the confidence interval does not establish a true gain of at least2pp.','No claim against legacy hidden-queue Bprod, other ascensions, keys-on/Act4, exact-budget combat, currentmain CTM changes, or the live game.','Existing engine-stop and turn-limit search endpoints were retained under the frozen health interpretation; no outcome-dependent exclusions or new health threshold.','No retries are evidenced by the unique frozen job/output inventory, refuse-existing-output runner and one completed dispatcher receipt per job; historical absence of out-of-band deleted runs relies on the prelaunch custody checks, not an unforgeable external audit.','No games, source edits, selection changes, extra contrasts, extensions, default changes or merge were performed by this review.'],
 'inputs':[{'path':p,'sha256':h}for p,h in sorted(control_inputs.items())],
 'raw_input_inventory_sha256':hashlib.sha256(json.dumps(report['inputs'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
 'raw_input_inventory_count':len(report['inputs'])}
with (A/'FINAL_CONFIRMATION_REVIEW.json').open('x')as f:json.dump(output,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in output.items() if k not in ['inputs','scope']},indent=2))
