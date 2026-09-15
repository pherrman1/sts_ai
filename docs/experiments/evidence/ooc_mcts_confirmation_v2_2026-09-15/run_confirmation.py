#!/usr/bin/env python3
import csv, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PLAN=json.loads((HERE/'plan.json').read_text())
RAW=HERE/'raw'; RAW.mkdir(exist_ok=True)

COMMON={
 'STS_FAIR':'1','STS_SEARCHER3':'0','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1',
 'STS_SILVER_REUSE_CAP_MODE':'allocated','STS_SILVER_ADAPTIVE':'0','STS_SILVER_VNET_LEAF_DIRECT':'0',
 'STS_SILVER_TELEMETRY':'1','STS_NATIVE_OOC':'1','STS_OOC_STRATEGIC_TOK_NN':str(ROOT/'selfplay/models/ooc_strategic_tok_final.native'),
 'STS_OOC_STRATEGIC_REST':'1','STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1',
 'STS_OOC_STRATEGIC_TREASURE':'1','STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0',
 'STS_STOP_AFTER_ACT':'3','STS_COLLECT_KEYS':'0','OMP_NUM_THREADS':str(PLAN['omp_threads']),
 'STS_EXECUTABLE_GIT_SHA':PLAN['source_sha'],
 'STS_OOC_MCTS_COMBAT_MODEL':str(ROOT/PLAN['models']['combat_transition'][0])}

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def frozen_hashes():
 got={'binary':sha(ROOT/PLAN['binary'])}
 for name,(path,expected) in PLAN['models'].items(): got[name]=sha(ROOT/path)
 expected={'binary':PLAN['binary_sha256'],**{k:v[1] for k,v in PLAN['models'].items()}}
 if got!=expected: raise RuntimeError(f'artifact drift: got={got} expected={expected}')
 return got

def rows(path,count,start):
 data=list(csv.DictReader(open(path)))
 if len(data)!=count or {int(r['seed']) for r in data}!=set(range(start,start+count)):
  raise RuntimeError(f'wrong rows/seeds: {path}')
 return data

def validate_run(arm,prefix,count,start):
 result=RAW/f'{prefix}.csv'; meta=Path(str(result)+'.meta.json'); log=RAW/f'{prefix}.log'
 data=rows(result,count,start); m=json.loads(meta.read_text()); text=log.read_text(errors='replace')
 cfg=m['config']
 silver_lines=[x for x in text.splitlines() if x.startswith('[silver-combat]')]
 bridge_zero=bool(silver_lines) and all(all(re.search(rf'\b{k}=0\b',x) for k in ('conversion_failures','semantic_resolution_failures','transaction_failures','knowledge_failures')) for x in silver_lines)
 checks=[m['seedBlock']=={'lo':start,'hi':start+count-1},m['nSeeds']==count,m['asc']==0,m['sims']==10000,m['threads']==PLAN['omp_threads'],cfg['fairPlay'],cfg['effectiveCombatBackend']=='silver',cfg['silverReuseCapMode']=='allocated',cfg['silverReuseCap']==32768,cfg['silverExactRootBudgets'],not cfg['silverAdaptiveEnabled'],not cfg['collectKeys'],not cfg['searcher3'],cfg['executableGitSha']==PLAN['source_sha'],'[isolated Silver combat backend ON:' in text,'cap=32768]' in text,'[fair-play / determinized MCTS ON]' in text,bridge_zero]
 if arm['id']=='v4': checks += ['[live OOC MCTS ON' not in text]
 else:
  config=re.findall(r'^\[ooc-mcts-config\] (\{.*\})$',text,re.MULTILINE)
  checks += ['[live OOC MCTS ON' in text,str(ROOT/PLAN['models']['combat_transition'][0]) in text,len(config)==1]
  if len(config)==1:
   actual=json.loads(config[0]); p=arm['profile']
   checks += [actual=={'prior':p['STS_OOC_MCTS_PRIOR'],'temperature':float(p['STS_OOC_MCTS_TEMPERATURE']),'cPuct':float(p['STS_OOC_MCTS_CPUCT']),'wideningK':float(p['STS_OOC_MCTS_WIDEN_K']),'wideningAlpha':float(p['STS_OOC_MCTS_WIDEN_ALPHA']),'maxDepth':int(p['STS_OOC_MCTS_MAX_DEPTH']),'rootSelection':p['STS_OOC_MCTS_ROOT_SELECTION'],'earlyStop':True,'leafValue':p['STS_OOC_MCTS_LEAF_VALUE'],'leafCombats':int(p['STS_OOC_MCTS_LEAF_COMBATS']),'leafPolicy':p['STS_OOC_MCTS_LEAF_POLICY'],'simulations':int(p['STS_OOC_MCTS_SIMS'])}]
  trace=RAW/f'{prefix}.mcts.csv'; support=Path(str(trace)+'.support.jsonl')
  checks += [trace.is_file(),support.is_file(),len(list(csv.DictReader(open(trace))))==count,len([x for x in support.read_text().splitlines() if x])==count]
 if not all(checks): raise RuntimeError(f'canary/run validation failed for {prefix}: {checks}')
 return {'wins':sum(int(r['won']) for r in data),'mean_floor':sum(int(r['floor']) for r in data)/count,'mean_hp':sum(int(r['hpEnd']) for r in data)/count,'mean_sec':sum(float(r['sec']) for r in data)/count}

def execute(arm,prefix,count,start):
 paths=[RAW/f'{prefix}.csv',RAW/f'{prefix}.csv.meta.json',RAW/f'{prefix}.log',RAW/f'{prefix}.receipt.json']
 if arm['id']!='v4': paths += [RAW/f'{prefix}.mcts.csv',RAW/f'{prefix}.mcts.csv.support.jsonl']
 if any(p.exists() for p in paths): raise RuntimeError(f'reused/partial output for {prefix}')
 hashes=frozen_hashes(); env={**os.environ,**COMMON,**arm['profile']}
 if arm['id']!='v4': env['STS_OOC_MCTS_TRACE']=str(RAW/f'{prefix}.mcts.csv')
 argv=[str(ROOT/PLAN['binary']),'bestbench','10000',str(count),'0',str(start),str(RAW/f'{prefix}.csv')]
 receipt={'arm':arm['id'],'phase':'canary' if count==1 else 'official','source_sha':PLAN['source_sha'],'seed_range':[start,start+count-1],'artifact_hashes':hashes,'env':{k:env[k] for k in sorted(env) if k.startswith('STS_') or k=='OMP_NUM_THREADS'},'argv':argv}
 (RAW/f'{prefix}.receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 begun=time.time()
 with open(RAW/f'{prefix}.log','w') as out: subprocess.run(['bash',str(ROOT/'tools/seed_guard.sh'),*argv],cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
 result=validate_run(arm,prefix,count,start); result['wall_seconds']=time.time()-begun
 (RAW/f'{prefix}.score.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print('VALIDATED',prefix,json.dumps(result,sort_keys=True),flush=True)

def main():
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=PLAN['source_sha']: raise RuntimeError('source drift')
 if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
  allowed=('docs/experiments/evidence/ooc_mcts_confirmation_v2_2026-09-15/',)
  bad=[x for x in subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).splitlines() if not any(a in x for a in allowed)]
  if bad: raise RuntimeError(f'unrelated worktree changes: {bad}')
 frozen_hashes()
 for arm in PLAN['arms']: execute(arm,'canary_'+arm['id'],1,PLAN['canary_seeds'][arm['id']])
 (HERE/'canaries-passed.json').write_text(json.dumps({'all_passed':True,'source_sha':PLAN['source_sha'],'arms':[a['id'] for a in PLAN['arms']]},indent=2)+'\n')
 for arm in PLAN['arms']: execute(arm,'official_'+arm['id'],PLAN['official_seed_count'],PLAN['official_seed_start'])
 print('CONFIRMATION_RUN_COMPLETE',flush=True)

if __name__=='__main__': main()
