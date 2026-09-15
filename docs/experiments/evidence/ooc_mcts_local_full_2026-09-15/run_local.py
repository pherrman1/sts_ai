#!/usr/bin/env python3
import csv, hashlib, json, os, subprocess, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
RAW=OUT/'raw'; RAW.mkdir(exist_ok=True)
PLAN=json.load(open(OUT/'plan.json'))
BINARY=Path(PLAN['binary']); COMBAT=Path(PLAN['combat_model'])
SOURCE=PLAN['source_sha']; START=PLAN['seed_start']; COUNT=PLAN['seed_count_per_arm']
COMMON={'STS_FAIR':'1','STS_SEARCHER3':'0','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1',
 'STS_SILVER_REUSE_CAP_MODE':'allocated','STS_SILVER_ADAPTIVE':'0','STS_SILVER_VNET_LEAF_DIRECT':'0',
 'STS_SILVER_TELEMETRY':'1','STS_NATIVE_OOC':'1','STS_OOC_STRATEGIC_TOK_NN':str(ROOT/'selfplay/models/ooc_strategic_tok_final.native'),
 'STS_OOC_STRATEGIC_REST':'1','STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1',
 'STS_OOC_STRATEGIC_TREASURE':'1','STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0',
 'STS_STOP_AFTER_ACT':'3','STS_COLLECT_KEYS':'0','OMP_NUM_THREADS':str(PLAN['omp_threads']),
 'STS_EXECUTABLE_GIT_SHA':SOURCE,'STS_OOC_MCTS':'1','STS_OOC_MCTS_COMBAT_MODEL':str(COMBAT)}

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()

def validate(path):
 rows=list(csv.DictReader(open(path)))
 if len(rows)!=COUNT or {int(r['seed']) for r in rows}!=set(range(START,START+COUNT)):
  raise RuntimeError(f'invalid rows/seeds in {path}')
 wins=sum(int(r['won']) for r in rows)
 return {'wins':wins,'games':COUNT,'win_rate':wins/COUNT,
  'mean_floor':sum(int(r['floor']) for r in rows)/COUNT,
  'mean_seconds':sum(float(r['sec']) for r in rows)/COUNT}

def main():
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=SOURCE: raise RuntimeError('source drift')
 if sha(BINARY)!=PLAN['binary_sha256'] or sha(COMBAT)!=PLAN['combat_model_sha256']: raise RuntimeError('binary/model drift')
 for arm in PLAN['arms']:
  name=arm['id']; result=RAW/f'{name}.csv'; log=RAW/f'{name}.log'; trace=RAW/f'{name}.mcts.csv'
  if result.exists():
   score=validate(result); print('COMPLETED_VALIDATED',name,json.dumps(score),flush=True); continue
  if any(p.exists() for p in (log,trace,Path(str(trace)+'.support.jsonl'))): raise RuntimeError(f'partial arm exists: {name}')
  env={**os.environ,**COMMON,**arm['profile'],'STS_OOC_MCTS_TRACE':str(trace)}
  argv=[str(BINARY),'bestbench','10000',str(COUNT),'0',str(START),str(result)]
  receipt={'arm':name,'source':SOURCE,'binary_sha256':sha(BINARY),'combat_model_sha256':sha(COMBAT),
   'seeds':[START,START+COUNT-1],'env':{k:env[k] for k in sorted(env) if k.startswith('STS_') or k=='OMP_NUM_THREADS'},'argv':argv}
  (RAW/f'{name}.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  command=['bash',str(ROOT/'tools/seed_guard.sh'),*argv]
  print('START',name,flush=True); begun=time.time()
  with open(log,'w') as out: subprocess.run(command,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
  score=validate(result); score['wall_seconds']=time.time()-begun
  (RAW/f'{name}.score.json').write_text(json.dumps(score,indent=2)+'\n')
  print('COMPLETED_VALIDATED',name,json.dumps(score),flush=True)
 print('LOCAL_FULL_SWEEP_COMPLETE',flush=True)

if __name__=='__main__': main()
