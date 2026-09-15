#!/usr/bin/env python3
import csv,gzip,hashlib,json,math,random,re
from pathlib import Path
H=Path(__file__).resolve().parent; R=H/'raw'; ROOT=H.parents[3]; P=json.loads((H/'plan.json').read_text()); AP=json.loads((H/'additional-plan.json').read_text()) if (H/'additional-plan.json').is_file() else {'arms':[]}; ARMS=P['arms']+AP['arms']; SEEDS=set(range(P['official_seed_start'],P['official_seed_start']+P['official_seed_count']))
def req(x,m):
 if not x: raise RuntimeError(m)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def boot(a,b):
 d=[a[s]-b[s] for s in sorted(SEEDS)]; q=[]; rng=random.Random(P['bootstrap_seed']); n=P['bootstrap_resamples']
 for _ in range(n): q.append(sum(d[rng.randrange(32)] for _ in d)/32)
 q.sort(); return [q[int(.025*n)],q[int(.975*n)]]
def exact(a,b):
 pos=sum(a[s]>b[s] for s in SEEDS); neg=sum(a[s]<b[s] for s in SEEDS); n=pos+neg
 p=min(1,2*sum(math.comb(n,k) for k in range(min(pos,neg)+1))/2**n) if n else 1
 return {'candidate_only_wins':pos,'control_only_wins':neg,'discordant':n,'exact_p_two_sided':p}
def main():
 req(sha(ROOT/P['binary'])==P['binary_sha256'],'binary drift')
 for _,(path,h) in P['models'].items(): req(sha(ROOT/path)==h,f'model drift {path}')
 out={}; outcomes={}; files=[]
 for arm in ARMS:
  n=arm['id']; base=R/f'official_{n}'; csvp=Path(str(base)+'.csv'); meta=Path(str(csvp)+'.meta.json'); log=Path(str(base)+'.log'); receipt=Path(str(base)+'.receipt.json'); score=Path(str(base)+'.score.json')
  if not log.is_file(): log=Path(str(log)+'.gz')
  for p in (csvp,meta,log,receipt,score): req(p.is_file(),f'missing {p}')
  rows=list(csv.DictReader(open(csvp))); req(len(rows)==32,'row count'); by={int(x['seed']):x for x in rows}; req(set(by)==SEEDS,'seed set/duplicates')
  m=json.loads(meta.read_text()); rc=json.loads(receipt.read_text()); req(m['seedBlock']=={'lo':min(SEEDS),'hi':max(SEEDS)} and m['nSeeds']==32 and m['sims']==10000 and m['asc']==0 and m['threads']==P['omp_threads'],'meta contract')
  c=m['config']; req(c['effectiveCombatBackend']=='silver' and c['silverReuseCap']==32768 and c['silverExactRootBudgets'] and not c['silverAdaptiveEnabled'] and c['fairPlay'] and not c['searcher3'] and not c['collectKeys'],'gameplay contract')
  req(rc['source_sha']==P['source_sha'] and rc['artifact_hashes']=={'binary':P['binary_sha256'],**{k:v[1] for k,v in P['models'].items()}},'receipt provenance')
  text=(gzip.open(log,'rt',errors='replace').read() if log.suffix=='.gz' else log.read_text(errors='replace')); sl=[x for x in text.splitlines() if x.startswith('[silver-combat]')]; req(sl and all(all(re.search(rf'\b{k}=0\b',x) for k in ('conversion_failures','semantic_resolution_failures','transaction_failures','knowledge_failures')) for x in sl),'bridge failures')
  wins=sum(int(x['won']) for x in rows); result={'wins':wins,'games':32,'win_rate':wins/32,'mean_floor':sum(int(x['floor']) for x in rows)/32,'mean_hp':sum(int(x['hpEnd']) for x in rows)/32,'mean_sec_game':sum(float(x['sec']) for x in rows)/32,'wall_seconds':json.loads(score.read_text())['wall_seconds']}
  outcomes[n]={s:int(x['won']) for s,x in by.items()}
  if n!='v4':
   tp=Path(str(base)+'.mcts.csv'); sp=Path(str(tp)+'.support.jsonl'); req(tp.is_file() and sp.is_file(),'mcts evidence'); tr=list(csv.DictReader(open(tp))); req(len(tr)==32 and {int(x['seed']) for x in tr}==SEEDS,'trace seeds')
   sup={int(x['seed']):x for x in map(json.loads,sp.read_text().splitlines())}; req(set(sup)==SEEDS,'support seeds')
   for x in tr:
    req(int(x['oocDecisions'])==int(x['mctsOwned'])+int(x['mctsFallback']),'ownership'); req(int(x['mctsSupportAborts'])==int(x['unsupportedCombats'])+int(x['continuationLimitAborts']),'abort'); req(int(x['simulationAttempts'])==int(x['simulations'])+int(x['mctsSupportAborts']),'attempts'); req(int(x['imaginedCombats'])==int(x['combatSurrogateSamples'])+int(x['unsupportedCombats']) and int(x['battleLeaves'])==0,'combat accounting'); req(int(x['simulations'])+int(x['savedSimulations'])==int(arm['profile']['STS_OOC_MCTS_SIMS'])*int(x['mctsOwned'])+int(x['discardedSimulations']),'budget')
    s=sup[int(x['seed'])]; req(sum(s['reasons'].values())==int(x['unsupportedCombats']) and s['continuation_limit_aborts']==int(x['continuationLimitAborts']),'support reasons')
   keys=['oocDecisions','mctsOwned','mctsFallback','mctsSupportAborts','simulations','savedSimulations','simulationAttempts','combatSurrogateSamples','unsupportedCombats','continuationLimitAborts','mctsWallSec','maxDepth']
   tel={k:(max(int(x[k]) for x in tr) if k=='maxDepth' else sum(float(x[k]) if k=='mctsWallSec' else int(x[k]) for x in tr)) for k in keys}; tel['fallback_rate']=tel['mctsFallback']/tel['oocDecisions']; tel['ctm_samples_per_game']=tel['combatSurrogateSamples']/32; result['telemetry']=tel
  out[n]=result
 for a,b in [('mcts512','v4'),('mcts2048_rollout0','v4'),('mcts2048_rollout1','v4'),('rollout3','v4'),('mcts2048_rollout0','mcts512'),('mcts2048_rollout1','mcts2048_rollout0'),('rollout3','mcts2048_rollout0'),('rollout3','mcts2048_rollout1'),('rollout3','mcts512')]:
  delta=sum(outcomes[a][s]-outcomes[b][s] for s in SEEDS)/32; ci=boot(outcomes[a],outcomes[b]); cmp={'delta':delta,'bootstrap95':ci,**exact(outcomes[a],outcomes[b])}; cmp['classification']='CONFIRMED_POSITIVE' if delta>0 and ci[0]>0 else ('PROMISING_INCONCLUSIVE' if delta>0 else 'NO_CONFIRMATION'); out[f'{a}_vs_{b}']=cmp
 summary={'schema_version':2,'source_sha':P['source_sha'],'binary_sha256':P['binary_sha256'],'seed_block':[min(SEEDS),max(SEEDS)],'bootstrap_seed':P['bootstrap_seed'],'bootstrap_resamples':P['bootstrap_resamples'],'results':out,'runtime_ratios':{'mcts2048_rollout0_vs_v4':out['mcts2048_rollout0']['mean_sec_game']/out['v4']['mean_sec_game'],'mcts2048_rollout1_vs_v4':out['mcts2048_rollout1']['mean_sec_game']/out['v4']['mean_sec_game'],'rollout3_vs_v4':out['rollout3']['mean_sec_game']/out['v4']['mean_sec_game'],'rollout3_vs_mcts512':out['rollout3']['mean_sec_game']/out['mcts512']['mean_sec_game']}}
 (H/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 for p in sorted(R.glob('*.log')):
  with open(p,'rb') as src,open(str(p)+'.gz','wb') as dst:
   with gzip.GzipFile(filename='',mode='wb',fileobj=dst,mtime=0) as z:z.write(src.read())
  p.unlink()
 index=[]
 for p in sorted(H.rglob('*')):
  if p.is_file() and p.name!='sha256-index.json' and '__pycache__' not in p.parts:index.append({'path':str(p.relative_to(H)),'bytes':p.stat().st_size,'sha256':sha(p)})
 (H/'sha256-index.json').write_text(json.dumps({'files':index},indent=2,sort_keys=True)+'\n'); print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=='__main__':main()
