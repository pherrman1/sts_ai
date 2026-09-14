#!/usr/bin/env python3
"""Frozen grouped OOC search design and strict seed-free artifact analysis."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import math
try:
 from tools.analyze_ooc_mcts_gameplay import analyze,read_rows
except ModuleNotFoundError:
 from analyze_ooc_mcts_gameplay import analyze,read_rows

PREFIX='STS_OOC_MCTS_'
DEFAULT={'SIMS':'2048','PRIOR':'policy','TEMPERATURE':'1','CPUCT':'1.5','WIDEN_K':'2','WIDEN_ALPHA':'0.5','MAX_DEPTH':'32','ROOT_SELECTION':'visits','LEAF_VALUE':'native','LEAF_COMBATS':'0','LEAF_POLICY':'v4'}
FAMILIES={'prior':('PRIOR','TEMPERATURE','CPUCT'),'widening':('WIDEN_K','WIDEN_ALPHA'),'leaf':('MAX_DEPTH','LEAF_VALUE','LEAF_COMBATS','LEAF_POLICY'),'root':('ROOT_SELECTION',)}

def profile(**changes):return {PREFIX+k:v for k,v in {**DEFAULT,**changes}.items()}
def screen_plan():
 definitions=[('00_ref',{},'all'),('01_uniform15',dict(PRIOR='uniform'),'prior'),('02_uniform3',dict(PRIOR='uniform',CPUCT='3'),'prior'),('03_sharp',dict(TEMPERATURE='0.5',CPUCT='0.5'),'prior'),('04_flat',dict(TEMPERATURE='2',CPUCT='3'),'prior'),('05_greedy',dict(CPUCT='0'),'prior'),('06_narrow',dict(WIDEN_K='1',WIDEN_ALPHA='0.25'),'widening'),('07_broad',dict(WIDEN_K='4',WIDEN_ALPHA='0.75'),'widening'),('08_depth8',dict(MAX_DEPTH='8'),'leaf'),('09_depth16',dict(MAX_DEPTH='16'),'leaf'),('10_no_value',dict(LEAF_VALUE='constant'),'leaf'),('11_rollout1',dict(LEAF_COMBATS='1'),'leaf'),('12_rollout3',dict(LEAF_COMBATS='3'),'leaf'),('13_uniform_leaf',dict(LEAF_COMBATS='1',LEAF_POLICY='uniform'),'leaf'),('14_root_q',dict(ROOT_SELECTION='q'),'root'),('15_budget512',dict(SIMS='512'),'budget'),('16_budget10000',dict(SIMS='10000'),'budget')]
 return [{'id':i,'profile':profile(**p),'family':f} for i,p,f in definitions]
def rank_key(row):
 if any(not math.isfinite(float(row[k])) for k in ['wins','mean_floor','mean_seconds']):raise ValueError('nonfinite score')
 return (-row['wins'],-row['mean_floor'],row['mean_seconds'],row['id'])
def canonical(p):return tuple(sorted(p.items()))
def compose(plan,scores):
 if len(scores)!=len(plan) or len({r['id'] for r in scores})!=len(scores) or {r['id'] for r in scores}!={r['id'] for r in plan}:raise ValueError('composition requires complete screening scores')
 by_id={r['id']:r for r in scores};chosen={};p=profile()
 for family,keys in FAMILIES.items():
  winner=min((r for r in plan if r['family'] in ('all',family)),key=lambda r:rank_key(by_id[r['id']]))
  chosen[family]=winner['id']
  for key in keys:p[PREFIX+key]=winner['profile'][PREFIX+key]
 seen={canonical(r['profile']):r['id'] for r in plan};arms=[]
 for sims in ['512','2048','10000']:
  q={**p,PREFIX+'SIMS':sims};old=seen.get(canonical(q));i='combo'+sims
  arms.append(dict(id=i,profile=q,family='composed',reuse=old))
 return {'family_winners':chosen,'arms':arms}
def applied(p):
 mapping={'prior':'PRIOR','temperature':'TEMPERATURE','cPuct':'CPUCT','wideningK':'WIDEN_K','wideningAlpha':'WIDEN_ALPHA','maxDepth':'MAX_DEPTH','rootSelection':'ROOT_SELECTION','leafValue':'LEAF_VALUE','leafCombats':'LEAF_COMBATS','leafPolicy':'LEAF_POLICY','simulations':'SIMS'}
 numeric={'temperature','cPuct','wideningK','wideningAlpha','maxDepth','leafCombats','simulations'}
 return {k:float(p[PREFIX+v]) if k in numeric else p[PREFIX+v] for k,v in mapping.items()}
def validate(folder,name,start,count,sha,p,expected_env,on=True):
 path=folder/(name+'.csv');rows=read_rows(path);trace=read_rows(Path(str(path)+'.mcts.csv'));seeds=set(range(start,start+count))
 if set(rows)!=seeds or set(trace)!=seeds:raise ValueError('exact membership mismatch')
 meta=json.loads(Path(str(path)+'.meta.json').read_text());c=meta['config'];env=json.loads(path.with_suffix('.config.json').read_text())['env']
 if meta['nSeeds']!=count or meta['seedBlock']!={'lo':start,'hi':start+count-1} or meta['threads']!=24 or meta['sims']!=10000 or meta['asc']!=0 or c['executableGitSha']!=sha or c['effectiveCombatBackend']!='silver' or not c['fairPlay'] or not c['silverExactRootBudgets'] or c['searcher3']:raise ValueError('frozen metadata mismatch')
 if env!=expected_env or meta['argv']!=['bestbench','10000',str(count),'0',str(start),expected_env['STS_OOC_MCTS_TRACE'].removesuffix('.mcts.csv')] or not c['nativeOoc'] or c['collectKeys'] or c['silverAdaptiveEnabled'] or not c['silverSearchEnabled'] or env.get('STS_STOP_AFTER_ACT')!='3':raise ValueError('full frozen environment/argv mismatch')
 if any(env.get(k)!=v for k,v in p.items()) or env.get('STS_OOC_MCTS')!=str(int(on)):raise ValueError('profile receipt mismatch')
 reasons=[json.loads(l) for l in Path(str(path)+'.mcts.csv.support.jsonl').read_text().splitlines()]
 if len(reasons)!=count or {r['seed'] for r in reasons}!=seeds:raise ValueError('support seed membership mismatch')
 for r in reasons:
  limits=int(trace[r['seed']].get('continuationLimitAborts',0))
  if any(v<0 for v in r.get('continuation_reasons',{}).values()) or r.get('continuation_limit_aborts',0)!=limits or sum(r.get('continuation_reasons',{}).values())!=limits:raise ValueError('continuation reason mismatch')
  if any(v<0 for v in r['reasons'].values()) or sum(r['reasons'].values())!=int(trace[r['seed']]['unsupportedCombats']):raise ValueError('support reasons mismatch')
 budget=int(p[PREFIX+'SIMS'])
 for r in trace.values():
  n={k:int(r[k]) for k in ['oocDecisions','mctsOwned','mctsFallback','simulations','discardedSimulations','simulationAttempts','mctsSupportAborts','unsupportedCombats','imaginedCombats','combatSurrogateSamples','battleLeaves','maxDepth','realCombats']}
  if n['battleLeaves'] or n['realCombats']<=0 or not 0<=n['maxDepth']<=int(p[PREFIX+'MAX_DEPTH']):raise ValueError('invalid boundary/depth')
  if on and n['oocDecisions']!=n['mctsOwned']+n['mctsFallback']:raise ValueError('ownership mismatch')
  if not on and any(n[k] for k in ['mctsOwned','mctsFallback','simulations','imaginedCombats','simulationAttempts']):raise ValueError('OFF searches')
  if 'continuationLimitAborts' not in r:raise ValueError('new runtime continuation telemetry missing')
  limits=int(r['continuationLimitAborts'])
  if not on and limits:raise ValueError('OFF continuation aborts')
  if limits<0:raise ValueError('negative continuation limit count')
  if n['simulations']!=budget*n['mctsOwned']+n['discardedSimulations'] or n['simulationAttempts']!=n['simulations']+n['mctsSupportAborts'] or n['unsupportedCombats']+limits!=n['mctsSupportAborts'] or not 0<=n['mctsSupportAborts']<=n['mctsFallback'] or not 0<=n['discardedSimulations']<=(budget-1)*n['mctsSupportAborts'] or n['imaginedCombats']!=n['combatSurrogateSamples']+n['unsupportedCombats']:raise ValueError('search attempt accounting mismatch')
 log=(folder/(name+'.log')).read_text();silver=[l for l in log.splitlines() if l.startswith('[silver-combat] ')]
 if len(silver)!=sum(int(r['realCombats']) for r in trace.values()):raise ValueError('actual combat log mismatch')
 for line in silver:
  fields=dict(re.findall(r'(\w+)=(-?\d+)',line))
  if any(fields.get(k)!='0' for k in ['conversion_failures','semantic_resolution_failures','transaction_failures','knowledge_failures']):raise ValueError('bridge failure')
 if on:
  receipts=[json.loads(l.removeprefix('[ooc-mcts-config] ')) for l in log.splitlines() if l.startswith('[ooc-mcts-config] ')]
  if receipts!=[applied(p)]:raise ValueError('actual applied knobs mismatch')
 for marker in ['[ooc-strat-tok-net] loaded ','448 feats from models/v_win_trees.txt','448 feats from models/v_rich_trees.txt','[policy PUCT ON: models/policy_trees_c.txt, 100 trees]','[benchmark stops after Act 3 boss]']:
  if marker not in log:raise ValueError('model activation missing')
 if any(r['won'] not in ('0','1') or any(not math.isfinite(float(r[k])) for k in ['floor','sec']) or float(r['sec'])<=0 or float(r['floor'])<0 for r in rows.values()):raise ValueError('invalid ranking outcome')
 return {'id':name,'wins':sum(int(r['won']) for r in rows.values()),'mean_floor':sum(float(r['floor']) for r in rows.values())/count,'mean_seconds':sum(float(r['sec']) for r in rows.values())/count,'owned':sum(int(r['mctsOwned']) for r in trace.values()),'support_aborts':sum(int(r['mctsSupportAborts']) for r in trace.values()),'surrogate_samples':sum(int(r['combatSurrogateSamples']) for r in trace.values()),'validated':True}
def manifest(template,configs,phase,start,count):
 m=json.loads(json.dumps(template));m['experiment_id']='mcts-parameter-search-'+phase
 m['command']=[m['binary']['remote_path'],'bestbench','10000',str(count),'0',str(start),'{results}'];m['arms']=[]
 root='/home/philippherrmann/sts_sweep'
 for row in configs:
  i=row['id'];out='results/mcts-search-20260914-'+phase+'-'+i+'.csv'
  e={'STS_OOC_MCTS':'0' if i=='control' else '1',**row['profile'],'STS_OOC_MCTS_TRACE':root+'/'+out+'.mcts.csv'}
  if i!='control':e['STS_OOC_MCTS_COMBAT_MODEL']=root+'/'+next(v['remote_path'] for v in m['artifacts'] if v['remote_path'].endswith('mcts64-combat-transition-v1.native'))
  m['arms'].append({'name':i,'results':out,'log':'logs/mcts-search-20260914-'+phase+'-'+i+'.log','env':e})
 return m

def main():
 a=argparse.ArgumentParser();a.add_argument('--plan',type=Path,required=True);x=a.parse_args();x.plan.write_text(json.dumps({'schema_version':1,'baseline':'f8279e4dfc075e83ca6f167f41b7103635c7dd4f','screen':screen_plan(),'composition_fields':FAMILIES,'discovery':[12000000,12000031],'confirmation':[12001000,12001031],'rank':['wins desc','mean_floor desc','mean_seconds asc','id asc'],'maximum_search_configs':20,'maximum_official_games':736},indent=2)+'\n')
if __name__=='__main__':main()
