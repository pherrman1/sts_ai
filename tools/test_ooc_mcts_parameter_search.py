#!/usr/bin/env python3
import csv
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from tools.ooc_mcts_parameter_search import screen_plan,compose,canonical,profile,rank_key,applied,validate
ROOT=Path(__file__).resolve().parent.parent
class SearchTests(unittest.TestCase):
 def test_groups_and_composition(self):
  plan=screen_plan();self.assertEqual(len(plan),17);self.assertEqual(len({canonical(p['profile']) for p in plan}),17)
  scores=[dict(id=r['id'],wins=10,mean_floor=40,mean_seconds=100) for r in plan]
  # Distinct family winners must change only their own fields.
  for i in ['02_uniform3','06_narrow','09_depth16','14_root_q']:
   next(r for r in scores if r['id']==i)['wins']=20
  c=compose(plan,scores);self.assertEqual(c['family_winners'],dict(prior='02_uniform3',widening='06_narrow',leaf='09_depth16',root='14_root_q'))
  p=c['arms'][1]['profile'];self.assertEqual((p['STS_OOC_MCTS_CPUCT'],p['STS_OOC_MCTS_WIDEN_K'],p['STS_OOC_MCTS_MAX_DEPTH'],p['STS_OOC_MCTS_ROOT_SELECTION']),('3','1','16','q'))
  self.assertTrue(all(r['reuse'] is None for r in c['arms']))
  for r in scores:r['wins']=10
  for r in compose(plan,scores)['arms']:self.assertIsNotNone(r['reuse'])
  with self.assertRaises(ValueError):compose(plan,scores+[scores[0]])
  with self.assertRaises(ValueError):rank_key(dict(id='x',wins=1,mean_floor=math.nan,mean_seconds=1))
 def test_raw_receipt_guards(self):
  with tempfile.TemporaryDirectory() as d:
   b=Path(d);source=ROOT/'docs/experiments/evidence/live_ooc_mcts_fresh64_10000_2026-09-14/canary'
   for f in source.glob('treatment*'):
    if f.name.endswith('.gz'):
     import gzip
     (b/f.name[:-3]).write_bytes(gzip.decompress(f.read_bytes()))
    else:shutil.copyfile(f,b/f.name)
   trace=b/'treatment.csv.mcts.csv'
   with trace.open() as f:tr=list(csv.DictReader(f))
   tr[0]['continuationLimitAborts']='0'
   def write_trace():
    with trace.open('w') as f:w=csv.DictWriter(f,fieldnames=list(tr[0]));w.writeheader();w.writerows(tr)
   write_trace()
   p=profile(SIMS='10000');config=b/'treatment.config.json';r=json.loads(config.read_text());r['env'].update(p);config.write_text(json.dumps(r));expected=r['env']
   log=b/'treatment.log';log.write_text(log.read_text()+'\n[ooc-mcts-config] '+json.dumps(applied(p))+'\n');sha='54f2820f426c45540b02eb075cf73102b00de8f0'
   def check():return validate(b,'treatment',979999,1,sha,p,expected)
   self.assertEqual(check()['wins'],1)
   # A noncombat bound abort changes root attempts, never combat census.
   tr[0]['continuationLimitAborts']='1'
   for k in ['mctsSupportAborts','simulationAttempts','mctsFallback','oocDecisions']:tr[0][k]=str(int(tr[0][k])+1)
   write_trace();reasons=b/'treatment.csv.mcts.csv.support.jsonl';original_reasons=reasons.read_text();q=json.loads(original_reasons);q.update(continuation_limit_aborts=1,continuation_reasons={'continuation_step_limit_256':1});reasons.write_text(json.dumps(q)+'\n')
   self.assertEqual(check()['support_aborts'],106)
   q['continuation_reasons']={};reasons.write_text(json.dumps(q)+'\n')
   with self.assertRaises(ValueError):check()
   reasons.write_text(original_reasons);tr[0]['continuationLimitAborts']='0'
   for k in ['mctsSupportAborts','simulationAttempts','mctsFallback','oocDecisions']:tr[0][k]=str(int(tr[0][k])-1)
   write_trace()
   for key,value in [('STS_NATIVE_OOC','0'),('STS_STOP_AFTER_ACT','2'),('STS_COLLECT_KEYS','1')]:
    bad=json.loads(config.read_text());bad['env'][key]=value;config.write_text(json.dumps(bad))
    with self.assertRaises(ValueError):check()
    config.write_text(json.dumps(r))
   original=log.read_text();log.write_text(original.replace('"cPuct": 1.5','"cPuct": 3'))
   with self.assertRaises(ValueError):check()
   log.write_text(original)
   results=b/'treatment.csv';original=results.read_text()
   for value in ['nan','inf']:
    rows=list(csv.DictReader(original.splitlines()));rows[0]['sec']=value
    with results.open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with self.assertRaises(ValueError):check()
   results.write_text(original)
   with self.assertRaises(ValueError):validate(b,'treatment',979998,1,sha,p,expected)
if __name__=='__main__':unittest.main()
