#!/usr/bin/env python3
"""Synthetic contract/statistical tests. Never opens campaign collection rows."""
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('k_precision',HERE/'analyze_k_precision.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
    seed=m.SEEDS[0];state=(seed,7,'BOSS_RELIC')
    options={state:{key:{'sourceSeed':str(seed),'decisionIdx':'7','type':'BOSS_RELIC',
                        'optionKey':key,'optionIdx':str(i),'chosen':str(int(key=='baseline'))}
                    for i,key in enumerate(('baseline','a','b'))}}
    sources={state:{'sourceSeed':str(seed),'decisionIdx':'7','type':'BOSS_RELIC','act':'1','floor':'17'}}
    labels=[]
    for option,opt in options[state].items():
        for k in range(32):
            # K4 chooses a; K16 chooses b. Evaluation favors a, so no reselect
            # during evaluation and subtraction direction are both observable.
            won=(option=='a' and (k<4 or k>=16)) or (option=='b' and 4<=k<16)
            future=int(hashlib.sha256(f'ooc-cf-pilot-v2-future:{seed}:7:{k}'.encode()).hexdigest()[:16],16)
            labels.append(opt|{'k':str(k),'futureSeed':str(future),'valid':'1','error':'',
                               'finalWon':str(int(won)),'mapAct':'2','mapFloor':'18'})
    return state,options,sources,labels


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def source_rows(options,sources):
    result=[]
    for seed in m.SEEDS:
        matching=[key for key in sources if key[0]==seed]
        if matching:
            key=matching[0];result.append(sources[key]|{'trajectoryValid':'1','options':str(len(options[key]))})
        else:
            result.append({'sourceSeed':str(seed),'decisionIdx':'-1','type':'','act':'0','floor':'0','trajectoryValid':'1','options':'0'})
    return result


class PrecisionTests(unittest.TestCase):
    def test_allocation_and_stage_disjointness(self):
        self.assertEqual(m.SEEDS,list(range(610084200,610084232)))
        self.assertTrue(set(m.RULES['K4'])<set(m.RULES['K16']))
        self.assertFalse(set(m.RULES['K16'])&set(m.EVAL_K))
        self.assertEqual(sorted(m.RULES['K16']+m.EVAL_K),list(range(32)))
        self.assertFalse(set(m.SEEDS)&set(range(610083000,610083512)))

    def test_ties_actual_baseline_then_semantic_key(self):
        self.assertEqual(m.choose({'z':1.,'b':1.,'a':1.},'z'),'z')
        self.assertEqual(m.choose({'z':0.,'b':1.,'a':1.},'z'),'a')
        with self.assertRaises(ValueError):m.choose({'baseline':float('nan')},'baseline')

    def test_nested_selection_and_evaluation_no_reselection(self):
        state,options,sources,rows=fixture()
        select_labels={(state,r['optionKey'],int(r['k'])):r for r in rows if int(r['k'])<16}
        selected=m.selection_states(options,sources,select_labels)
        self.assertEqual(selected[0]['choices'],{'K4':'a','K16':'b'})
        eval_labels={(state,r['optionKey'],int(r['k'])):r for r in rows if int(r['k'])>=16}
        states,summary=m.evaluate_states({'states':selected},options,sources,eval_labels)
        self.assertEqual(states[0]['choices'],{'K4':'a','K16':'b'})
        self.assertEqual(states[0]['comparisons']['K16-K4']['right_only'],16)
        self.assertEqual(states[0]['comparisons']['K16-K4']['left_only'],0)
        self.assertEqual(summary['K16-K4']['equal_source_mean_paired_gain'],-1/32)
        self.assertEqual(summary['K16-K4']['allocated_source_clusters'],32)
        self.assertEqual(summary['K16-K4']['observed_source_clusters'],1)

    def test_stage_barrier_ignores_poisoned_other_stage_outcomes(self):
        _,options,_,rows=fixture()
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            paths={'labels.csv':[Path(td)/'labels.csv'],'map.csv':[Path(td)/'map.csv']}
            for stage,ks in [('select',range(16)),('eval',range(16,32))]:
                poison=copy.deepcopy(rows)
                for row in poison:
                    if int(row['k']) not in ks:
                        row.update(finalWon='MUST_NOT_PARSE',valid='POISON',error='POISON',futureSeed='POISON')
                for name in paths:write_csv(paths[name][0],poison)
                labels=m.stage_labels(paths,options,list(ks))
                self.assertEqual(len(labels),3*16,stage)

    def test_complete_unique_valid_future_and_map_joins(self):
        _,options,_,rows=fixture()
        mutations={
            'missing_label':lambda ls,ms:ls.pop(),
            'duplicate_label':lambda ls,ms:ls.append(copy.deepcopy(ls[-1])),
            'invalid':lambda ls,ms:ls[-1].update(valid='0'),
            'error':lambda ls,ms:ls[-1].update(error='engine error'),
            'wrong_future':lambda ls,ms:ls[-1].update(futureSeed='1'),
            'wrong_action':lambda ls,ms:ls[-1].update(chosen='1'),
            'missing_map':lambda ls,ms:ms.pop(),
            'duplicate_map':lambda ls,ms:ms.append(copy.deepcopy(ms[-1])),
            'map_join':lambda ls,ms:ms[-1].update(mapFloor='999'),
            'bad_outcome':lambda ls,ms:ls[-1].update(finalWon='nan'),
        }
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            paths={'labels.csv':[Path(td)/'labels.csv'],'map.csv':[Path(td)/'map.csv']}
            for name,mutate in mutations.items():
                with self.subTest(name=name):
                    ls=copy.deepcopy(rows);ms=copy.deepcopy(rows);mutate(ls,ms)
                    write_csv(paths['labels.csv'][0],ls);write_csv(paths['map.csv'][0],ms)
                    with self.assertRaises(ValueError):m.stage_labels(paths,options,m.EVAL_K)

    def test_source_validity_and_canonical_no_state(self):
        _,options,sources,_=fixture();optrows=[r for opts in options.values() for r in opts.values()]
        src=source_rows(options,sources)
        actual,actual_sources=m.build_states(optrows,src)
        self.assertEqual(actual,options);self.assertEqual(actual_sources,sources)
        for name,alter in {
            'missing':lambda x:x.pop(), 'duplicate':lambda x:x.append(copy.deepcopy(x[-1])),
            'invalid_source':lambda x:x[-1].update(trajectoryValid='0'),
            'negative_noncanonical':lambda x:x[-1].update(decisionIdx='-2'),
            'no_state_options':lambda x:x[-1].update(options='1'),
            'no_state_type':lambda x:x[-1].update(type='BOSS_RELIC')}.items():
            with self.subTest(name=name):
                bad=copy.deepcopy(src);alter(bad)
                with self.assertRaises(ValueError):m.build_states(optrows,bad)

    def test_missing_baseline_or_duplicate_option_rejected(self):
        _,options,sources,_=fixture();src=source_rows(options,sources)
        opts=[r for values in options.values() for r in values.values()]
        for bad in [opts+[copy.deepcopy(opts[0])],[r|{'chosen':'0'} for r in opts]]:
            with self.assertRaises(ValueError):m.build_states(bad,src)

    def test_whole_source_bootstrap_includes_no_state_zeros(self):
        gains={m.SEEDS[0]:[1.],m.SEEDS[1]:[-.5]};summary=m.cluster_summary(gains)
        values=np.array([1.,-.5]+[0.]*30);rng=np.random.default_rng(20261008)
        draws=values[rng.integers(0,32,size=(10000,32))].mean(axis=1)
        self.assertEqual(summary['equal_source_mean_paired_gain'],.5/32)
        np.testing.assert_allclose(summary['source_cluster_bootstrap_ci95'],np.percentile(draws,[2.5,97.5]),atol=0,rtol=0)
        self.assertEqual(summary,m.cluster_summary(gains))
        for bad in [{m.SEEDS[0]:[0.,1.]},{m.SEEDS[0]:[float('nan')]},{1:[0.]}]:
            with self.assertRaises(ValueError):m.cluster_summary(bad)

    def test_no_state_everywhere_is_valid_zero_and_inconclusive(self):
        options,sources=m.build_states([],source_rows({},{}))
        states,summary=m.evaluate_states({'states':[]},options,sources,{})
        self.assertEqual(states,[])
        self.assertEqual(summary['K16-K4']['source_cluster_bootstrap_ci95'],[0.,0.])
        self.assertEqual(m.classify([0.,0.]),'LOCAL_CONDITIONAL_INCONCLUSIVE')

    def test_strict_sign_rule_without_population_threshold(self):
        self.assertEqual(m.classify([.001,.002]),'LOCAL_K16_SELECTION_GAIN_SUPPORTED')
        self.assertEqual(m.classify([-.002,-.001]),'LOCAL_K16_SELECTION_HARM_SUPPORTED')
        for ci in [[0.,.1],[-.1,0.],[-.1,.1]]:
            self.assertEqual(m.classify(ci),'LOCAL_CONDITIONAL_INCONCLUSIVE')

    def test_choice_hash_failure_precedes_any_efficacy_reader(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            path=Path(td)/'choice.json';path.write_text('{}')
            with patch.object(m,'stage_labels',side_effect=AssertionError('efficacy opened')) as reader:
                with self.assertRaisesRegex(ValueError,'changed input'):
                    m.evaluate(SimpleNamespace(choices=path,choices_sha='0'*64))
                reader.assert_not_called()

    def test_bound_input_tamper_precedes_any_efficacy_reader(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            dep=Path(td)/'input';dep.write_text('changed')
            choice={'status':'CHOICES_FROZEN','analysis_script_sha256':m.sha(m.__file__),
                    'source_seeds':m.SEEDS,'selection_k_by_rule':m.RULES,'evaluation_k':m.EVAL_K,
                    'evaluation_outcomes_opened':False,'frozen_epoch':0.,'analysis_runtime':m.runtime_identity(),
                    'inputs':[{'path':str(dep),'sha256':'0'*64}]}
            path=Path(td)/'choice.json';path.write_text(json.dumps(choice))
            with patch.object(m,'stage_labels',side_effect=AssertionError('efficacy opened')) as reader:
                with self.assertRaisesRegex(ValueError,'changed input'):
                    m.evaluate(SimpleNamespace(choices=path,choices_sha=m.sha(path)))
                reader.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
