#!/usr/bin/env python3
"""Synthetic-only checks; no current collection file is opened."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('blocked_accounting',HERE/'account_blocked_collection.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def tables(seed):
    source={'sourceSeed':str(seed),'decisionIdx':'4','type':'BOSS_RELIC','trajectoryValid':'1','options':'1','sourceCpuSeconds':'12.5'}
    option={k:source[k] for k in ('sourceSeed','decisionIdx','type')}|{'optionIdx':'0'}
    labels=[option|{'k':str(k),'valid':'1','error':'','cpuSeconds':'2.5'} for k in range(32)]
    return {'sources.csv':[source],'options.csv':[option],'labels.csv':labels,
            'map.csv':[{k:r[k] for k in m.FIELDS['map.csv']} for r in labels]}


def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


class AccountingTests(unittest.TestCase):
    def test_outcome_poison_never_retained_or_interpreted(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            path=Path(td)/'labels.csv';rows=[r|{'finalWon':'POISON_NOT_A_NUMBER','finalFloor':'SECRET'} for r in tables(m.SEEDS[0])['labels.csv']]
            write(path,rows);projected,issues=m.project_csv(path,m.FIELDS['labels.csv'])
            self.assertFalse(issues);self.assertEqual(len(projected),32)
            self.assertNotIn('POISON',json.dumps(projected));self.assertNotIn('SECRET',json.dumps(projected))
            self.assertEqual(m.cpu_summary(projected,'cpuSeconds')['observed_seconds'],80.)

    def test_source_cpu_deduplicates_and_flags_conflict(self):
        rows=[{'sourceSeed':'1','sourceCpuSeconds':'5'},{'sourceSeed':'1','sourceCpuSeconds':'5'},
              {'sourceSeed':'1','sourceCpuSeconds':'6'},{'sourceSeed':'2','sourceCpuSeconds':'nan'}]
        result=m.cpu_summary(rows,'sourceCpuSeconds',True)
        self.assertEqual(result['observed_seconds'],5.);self.assertEqual(result['invalid_cost_records'],2)

    def test_missing_cpu_is_unavailable_not_zero(self):
        self.assertIsNone(m.cpu_summary([],'cpuSeconds')['observed_seconds'])
        for value in ['nan','inf','-1','bad',None]:self.assertIsNone(m.number(value))

    def test_incomplete_table_preserves_completed_metadata_rows(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            path=Path(td)/'labels.csv';write(path,[r|{'finalWon':'unread'} for r in tables(m.SEEDS[0])['labels.csv'][:2]])
            with path.open('a') as f:f.write('incomplete,last,row\n')
            rows,issues=m.project_csv(path,m.FIELDS['labels.csv'])
            self.assertEqual(len(rows),2);self.assertEqual(len(issues),1)
            self.assertEqual(m.cpu_summary(rows,'cpuSeconds')['observed_seconds'],5.)

    def test_full_width_unterminated_numeric_tail_excluded(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            for role,field in [('sources.csv','sourceCpuSeconds'),('labels.csv','cpuSeconds')]:
                with self.subTest(role=role):
                    path=Path(td)/role;row=tables(m.SEEDS[0])[role][0]
                    write(path,[row,row|{field:'2.'}])
                    data=path.read_bytes();path.write_bytes(data.rstrip(b'\r\n'))
                    rows,issues=m.project_csv(path,m.FIELDS[role])
                    self.assertEqual(len(rows),1);self.assertIn('unterminated',issues[-1])
                    self.assertEqual(m.cpu_summary(rows,field)['observed_seconds'],float(row[field]))
                    path.write_bytes(data)
                    complete,errors=m.project_csv(path,m.FIELDS[role])
                    self.assertEqual(len(complete),2);self.assertFalse(errors)

    def test_live_process_closeout_blocks_collection_reads(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            dispatch={'schema':'k_precision_dispatch_completion_v1','status':'DISPATCH_FAILED_NO_RETRY','exit_code':123}
            closeout={'dispatcher_completed':True,'active_game_processes':1,'dispatcher_completion_sha256':'d'}
            args=['account','--dispatcher-completion','dispatch','--dispatcher-completion-sha','d',
                  '--process-closeout','close','--process-closeout-sha','c','--output',str(Path(td)/'out.json')]
            with patch('sys.argv',args),patch.object(m,'load_bound',side_effect=[(dispatch,{'sha256':'d'}),(closeout,{})]),patch.object(m,'source_inventory') as reader:
                with self.assertRaisesRegex(ValueError,'no active game process'):m.main()
                reader.assert_not_called()

    def test_missing_branches_maps_and_duplicates_are_metadata(self):
        seed=m.SEEDS[0];t=tables(seed);t['labels.csv'].pop();t['map.csv'].pop();t['labels.csv'].append(t['labels.csv'][0])
        r=m.summarize_tables(t,seed)
        self.assertEqual(r['missing_branch_identities'],1);self.assertEqual(r['missing_map_identities'],1)
        self.assertEqual(r['duplicate_branch_identity_rows'],1)
        self.assertEqual(r['retained_states'],1)

    def test_partial_timeout_receipt_and_all_files_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            raw=Path(td);seed=m.SEEDS[17];prefix=raw/f'seed-{seed}'
            t=tables(seed);write(Path(str(prefix)+'.sources.csv'),t['sources.csv'])
            source=Path(str(prefix)+'.sources.csv');record=m.bind(source)
            receipt={'source_seed':seed,'freeze_sha256':m.FREEZE_SHA,'status':'timeout','exit_code':124,
                     'started_epoch':100.,'finished_epoch':1900.,'wall_seconds':1800.,'outputs':{'sources.csv':record}}
            Path(str(prefix)+'.receipt.json').write_text(json.dumps(receipt))
            r=m.source_inventory(raw,seed,m.FREEZE_SHA)
            self.assertEqual(r['status'],'timeout');self.assertFalse(r['completed_game_invocation'])
            self.assertIn('labels.csv',r['missing_outputs']);self.assertIsNone(r['metadata']['branch_cpu']['observed_seconds'])
            self.assertEqual(r['metadata']['source_cpu']['observed_seconds'],12.5)
            self.assertFalse(r['accounting_issues'])

    def test_changed_output_custody_is_reported(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            raw=Path(td);seed=m.SEEDS[0];prefix=raw/f'seed-{seed}'
            path=Path(str(prefix)+'.log');path.write_text('new bytes')
            receipt={'source_seed':seed,'freeze_sha256':m.FREEZE_SHA,'status':'timeout','exit_code':124,
                     'outputs':{'log':{'path':str(path),'sha256':'0'*64,'bytes':path.stat().st_size}}}
            Path(str(prefix)+'.receipt.json').write_text(json.dumps(receipt))
            r=m.source_inventory(raw,seed,m.FREEZE_SHA)
            self.assertIn('receipt output custody mismatch: log',r['accounting_issues'])

    def test_fixed32_includes_timeout_and_separates_elapsed_from_sumwall(self):
        records=[]
        for i,seed in enumerate(m.SEEDS):
            records.append({'source_seed':seed,'status':'timeout' if i==17 else 'completed',
                'completed_game_invocation':i!=17,'missing_outputs':['labels.csv'] if i==17 else [],
                'timing':{'started_epoch':100.+i,'finished_epoch':200.+i,'wall_seconds':100.},
                'metadata':m.summarize_tables(tables(seed),seed)})
        summary=m.aggregate(records,{'started_epoch':90.,'finished_epoch':250.,'exit_code':123})
        self.assertEqual(summary['allocated_sources'],32);self.assertEqual(summary['completed_game_invocations'],31)
        self.assertEqual(summary['incomplete_or_failed_source_seeds'],[m.SEEDS[17]])
        self.assertEqual(summary['invocation_wall_seconds_sum'],3200.)
        self.assertEqual(summary['receipt_span_elapsed_seconds'],131.)
        self.assertEqual(summary['dispatcher_elapsed_seconds'],160.)
        with self.assertRaises(ValueError):m.aggregate(records[:-1],{})


if __name__=='__main__':unittest.main(verbosity=2)
