#!/usr/bin/env python3
"""Synthetic custody/health/schema checks; no game executable is invoked."""
from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).with_name('verify_gen2_k32.py')
spec = importlib.util.spec_from_file_location('verify_k32', P)
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
ROOT = P.resolve().parents[5]


def profile(seed, count=250):
    endpoints = {k: {'count': 0, 'tree_depth': {}, 'total_depth': {}} for k in v.HEALTH.KINDS}
    endpoints['victory'] = {'count': count, 'tree_depth': {'0': count}, 'total_depth': {'1': count}}
    return dict(schema=1, seed=str(seed), combat_id=0, decision=0, error='', adaptive=False,
                singleton_skip=False, completed_simulations=count, configured_simulations=10000,
                heuristic_evaluations=count, neural_evaluations=0, rollout_calls=count,
                cycle_rollouts=0, nonterminal_rollout_starts=count, descent_aborts=0,
                root_actions=2, inherited_visits=40000, endpoints=endpoints)


def tables(no_state=False):
    seed=v.SOURCE_SEEDS[0]
    row=dict(sourceSeed=str(seed), outcome='PLAYER_LOSS', finalFloor='30', trajectoryValid='1',
             inScopeSamples='0' if no_state else '1', decisionIdx='-1' if no_state else '10',
             type='' if no_state else 'BOSS_RELIC', act='-1' if no_state else '1',
             floor='-1' if no_state else '17', options='0' if no_state else '2', sourceCpuSeconds='1')
    return {'sources.csv':[row], 'options.csv':[], 'labels.csv':[], 'map.csv':[]}


def write_csv(path, rows, fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


class GuardTests(unittest.TestCase):
    def test_allocation_and_modes(self):
        f=dict(source_seeds=v.SOURCE_SEEDS, futures=32, states_per_seed=1, types=['BOSS_RELIC'],
               future_start=0, timeout_seconds_per_source=1800, root=str(ROOT),
               artifacts={str(v.HEALTH_PATH.relative_to(ROOT)):v.HEALTH_SHA,v.RUNNER_REL:v.RUNNER_SHA})
        prefixes=[Path('/tmp/synthetic-k32-'+str(x)) for x in range(32)]
        v.validate_scope(f,prefixes)
        for key, val in [('futures',8),('states_per_seed',2),('types',['CARD_REWARD']),('future_start',1),
                         ('source_seeds',list(range(610083000,610083032)))]:
            changed=dict(f,**{key:val})
            with self.assertRaises(ValueError): v.validate_scope(changed,prefixes)
        with self.assertRaises(ValueError): v.validate_scope(f,prefixes[:-1]+prefixes[:1])

    def test_no_state_is_explicit_and_valid(self):
        local=tables(True); m={'integrity':{'selectedStates':0}}
        self.assertTrue(v.validate_source_rows(local,m,v.SOURCE_SEEDS[0]))
        for key,val in [('trajectoryValid','0'),('decisionIdx','-2'),('type','BOSS_RELIC'),('options','1'),('inScopeSamples','1')]:
            bad=deepcopy(local);bad['sources.csv'][0][key]=val
            with self.assertRaises(ValueError):v.validate_source_rows(bad,m,v.SOURCE_SEEDS[0])
        for key in ('labels.csv','map.csv','options.csv'):
            bad=deepcopy(local);bad[key]=[{}]
            with self.assertRaises(ValueError):v.validate_source_rows(bad,m,v.SOURCE_SEEDS[0])

    def test_one_boss_state_and_duplicate_rejection(self):
        local=tables();m={'integrity':{'selectedStates':1}}
        self.assertFalse(v.validate_source_rows(local,m,v.SOURCE_SEEDS[0]))
        local['sources.csv']*=2
        with self.assertRaises(ValueError):v.validate_source_rows(local,m,v.SOURCE_SEEDS[0])

    def test_checkpoints_and_inherited_visits(self):
        for n in sorted(v.HEALTH.CHECKPOINTS):
            self.assertEqual(sum(v.verify_profile_root(profile(1,n),{1}).values()),n)
        with self.assertRaises(ValueError):v.verify_profile_root(profile(1,251),{1})
        with self.assertRaises(ValueError):v.verify_profile_root(profile(1),{2})

    def test_singleton(self):
        p=profile(1,0);p.update(singleton_skip=True,root_actions=1)
        v.verify_profile_root(p,{1})
        p['root_actions']=2
        with self.assertRaises(ValueError):v.verify_profile_root(p,{1})

    def test_endpoint_and_evaluator_conservation(self):
        for field in ('completed_simulations','heuristic_evaluations'):
            p=profile(1);p[field]+=1
            with self.assertRaises(ValueError):v.verify_profile_root(p,{1})
        p=profile(1);p['endpoints']['victory']['tree_depth']={'0':249}
        with self.assertRaises(ValueError):v.verify_profile_root(p,{1})

    def test_error_abort_nonterminal_fatal(self):
        for field,value in [('error','oops'),('descent_aborts',1)]:
            p=profile(1);p[field]=value
            with self.assertRaises(ValueError):v.verify_profile_root(p,{1})
        p=profile(1);p['endpoints']['nonterminal'],p['endpoints']['victory']=p['endpoints']['victory'],p['endpoints']['nonterminal']
        with self.assertRaises(ValueError):v.verify_profile_root(p,{1})

    def test_diagnostic_limits_not_fatal(self):
        for kind in ('turn_limit','engine_stop'):
            p=profile(1);p['endpoints'][kind],p['endpoints']['victory']=p['endpoints']['victory'],p['endpoints'][kind]
            p['cycle_rollouts']=20
            self.assertEqual(v.verify_profile_root(p,{1})[kind],250)
        self.assertNotIn('victory',json.dumps(v.empty_health()))

    def test_malformed_containers_and_duplicate_json(self):
        for p in ([],dict(profile(1),endpoints=[]),dict(profile(1),endpoints={'victory':[]})):
            with self.assertRaises(ValueError):v.verify_profile_root(p,{1})
        with self.assertRaises(ValueError):v.HEALTH.parse('{"a":1,"a":2}')
        with self.assertRaises(ValueError):v.HEALTH.parse('{"a":NaN}')

    def test_standard_first_rng_vectors_unchanged(self):
        expected = {0: 2947667278772165694, 1: 2469588189546311528,
                    5489: 14514284786278117030, (1 << 64)-1: 478026398904862820}
        for seed, word in expected.items():
            self.assertEqual(v.mt19937_64_first(seed), word)

    def test_future_seed_membership_all32(self):
        rows=[dict(sourceSeed='610084200',decisionIdx='10')]
        allowed=v.expected_profile_seeds(610084200,rows,32)
        self.assertEqual(len(allowed),33)
        digest=hashlib.sha256(b'ooc-cf-pilot-v2-future:610084200:10:31').hexdigest()
        self.assertIn(v.mt19937_64_first(int(digest[:16],16)),allowed)
        self.assertEqual(v.expected_profile_seeds(610084200,[],32),{610084200})

    def test_full_synthetic_cohort_including_no_branch_combats(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);teacher_path=d/'teacher.json';binary=d/'not_an_executable'
            binary.write_text('synthetic identity only')
            env={k:'1' for k in ('STS_FAIR','STS_SILVER_LEARNED_STOP','STS_OOC_SKIP_OPTIONAL_RECALL','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}
            env.update(STS_OOC_PUBLIC_FUTURES='8',STS_STOP_AFTER_ACT='3',STS_COLLECT_KEYS='0',STS_OOC_MCTS='0',STS_SILVER_EXACT_ROOT_BUDGETS='0',STS_SILVER_ADAPTIVE='0')
            policy={'flags':{'native_ooc_public_futures':8,'skip_optional_recall':True},'parameters':{'stop_after_act':3}}
            teacher={'git_sha':'synthetic','executable_sha256':v.sha(binary),'environment':env,'ooc_policy':policy,'model_artifacts':[],'teacher_id':'synthetic'}
            teacher_path.write_text(json.dumps(teacher))
            f=dict(source_seeds=v.SOURCE_SEEDS,futures=32,states_per_seed=1,types=['BOSS_RELIC'],future_start=0,
                   root=str(ROOT),binary=str(binary),binary_sha256=v.sha(binary),source_sha='synthetic',
                   teacher=str(teacher_path),teacher_sha256=v.sha(teacher_path),environment=env,timeout_seconds_per_source=1800,
                   artifacts={str(v.HEALTH_PATH.relative_to(ROOT)):v.HEALTH_SHA,v.RUNNER_REL:v.RUNNER_SHA})
            fp=d/'freeze.json';fp.write_text(json.dumps(f));prefixes=[]
            for index,seed in enumerate(v.SOURCE_SEEDS):
                prefix=d/str(seed);prefixes.append(prefix);local=tables(index>0)
                for row in local['sources.csv']:row['sourceSeed']=str(seed)
                if index==0:
                    for option in range(2):
                        row=dict(sourceSeed=str(seed),decisionIdx='10',type='BOSS_RELIC',optionIdx=str(option),optionKey='option'+str(option),chosen=str(1-option))
                        local['options.csv'].append(row)
                        for k in range(32):
                            digest=hashlib.sha256(f'ooc-cf-pilot-v2-future:{seed}:10:{k}'.encode()).hexdigest()
                            label=dict(row,k=str(k),finalWon=str(k%2),valid='1',error='',cpuSeconds='1',futureSeed=str(int(digest[:16],16)),mapAct='2',mapFloor='18')
                            local['labels.csv'].append(label)
                            local['map.csv'].append({key:val for key,val in label.items() if key not in ('finalWon','valid','error','cpuSeconds','futureSeed')})
                fields={'sources.csv':list(local['sources.csv'][0]),'options.csv':['sourceSeed','decisionIdx','type','optionIdx','optionKey','chosen'],
                        'labels.csv':['sourceSeed','decisionIdx','type','optionIdx','optionKey','chosen','k','finalWon','valid','error','cpuSeconds','futureSeed','mapAct','mapFloor'],
                        'map.csv':['sourceSeed','decisionIdx','type','optionIdx','optionKey','chosen','k','mapAct','mapFloor']}
                for suffix,rows in local.items():write_csv(Path(str(prefix)+'.'+suffix),rows,fields[suffix])
                manifest=dict(schemaVersion='ooc_cf_pilot_v2',producerGitSha='synthetic',producerExecutableSha256=v.sha(binary),teacherManifestSha256=v.sha(teacher_path),
                              teacherId='synthetic',combatTeacher=teacher,policy=policy,seedSpec={'ascension':0,'start':seed,'count':1},futures={'count':32},statesPerSeed=1,
                              selection={'types':['BOSS_RELIC']},integrity={'selectedStates':int(index==0),'labelRows':len(local['labels.csv']),'validLabelRows':len(local['labels.csv'])},
                              outputs={suffix:v.sha(Path(str(prefix)+'.'+suffix)) for suffix in local})
                Path(str(prefix)+'.manifest.json').write_text(json.dumps(manifest))
                Path(str(prefix)+'.tree.jsonl').write_text(json.dumps(profile(seed))+'\n')
                Path(str(prefix)+'.log').write_text('[native OOC public encounter mixture: 8 futures]\n[native OOC optional Ruby Recall excluded when keys off and another action is legal]\n[benchmark stops after Act 3 boss]\nlearned stop; one-action roots unsearched\n')
                outputs={}
                for suffix in (*local,'manifest.json','tree.jsonl','log'):
                    path=Path(str(prefix)+'.'+suffix);outputs[suffix]={'path':str(path),'sha256':v.sha(path),'bytes':path.stat().st_size}
                receipt=dict(status='completed',exit_code=0,source_sha='synthetic',binary_sha256=v.sha(binary),freeze=str(fp),freeze_sha256=v.sha(fp),script_sha256=v.RUNNER_SHA,source_seed=seed,
                             command=['bash','tools/seed_guard.sh',str(binary),'ooccfpilotgen','1',str(prefix),str(seed),str(teacher_path),'32','1','1','2','BOSS_RELIC'],
                             environment=dict(env,STS_SILVER_TREE_PROFILE=str(prefix)+'.tree.jsonl'),wall_seconds=2,outputs=outputs)
                Path(str(prefix)+'.receipt.json').write_text(json.dumps(receipt))
            result=v.verify(f,prefixes,fp)
            self.assertEqual(result['status'],'CONTRACT_RECEIPT_PASS')
            self.assertEqual(result['label_rows'],64)
            self.assertEqual(result['no_state_sources'],v.SOURCE_SEEDS[1:])
            self.assertEqual(result['native_tree_health']['roots'],32)
            self.assertEqual(result['native_tree_health']['completed_simulations'],8000)
            self.assertEqual(len(result['inputs']),256)
            self.assertFalse(result['evaluation_outcomes_reported'])
            # Duplicate roots fail even when output custody is consistently rehashed.
            prefix=prefixes[0];tp=Path(str(prefix)+'.tree.jsonl');original=tp.read_text()
            rp=Path(str(prefix)+'.receipt.json');original_receipt=rp.read_text()
            tp.write_text(original+original);receipt=json.loads(original_receipt)
            receipt['outputs']['tree.jsonl'].update(sha256=v.sha(tp),bytes=tp.stat().st_size)
            rp.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'duplicate profiled real decision'):v.verify(f,prefixes,fp)
            tp.write_text(original);rp.write_text(original_receipt)
            # Entirely missing evaluation siblings fail even with rehashed file custody.
            prefix=prefixes[0];path=Path(str(prefix)+'.labels.csv')
            labels=v.table(path)[:-1];write_csv(path,labels,fields['labels.csv'])
            mp=Path(str(prefix)+'.manifest.json');manifest=json.loads(mp.read_text());manifest['outputs']['labels.csv']=v.sha(path)
            manifest['integrity'].update(labelRows=63,validLabelRows=63);mp.write_text(json.dumps(manifest))
            rp=Path(str(prefix)+'.receipt.json');receipt=json.loads(rp.read_text())
            for suffix in ('labels.csv','manifest.json'):
                out=Path(str(prefix)+'.'+suffix);receipt['outputs'][suffix].update(sha256=v.sha(out),bytes=out.stat().st_size)
            rp.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'missing/extra sibling futures'):v.verify(f,prefixes,fp)


if __name__=='__main__':unittest.main()
