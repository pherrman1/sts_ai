#!/usr/bin/env python3
import csv, gzip, hashlib, json, math, random, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
RAW=HERE/'raw'
PLAN=json.load(open(HERE/'plan.json'))
EXPECTED=set(range(PLAN['seed_start'],PLAN['seed_start']+PLAN['seed_count_per_arm']))

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()

def wilson(w,n,z=1.959963984540054):
 p=w/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return [c-r,c+r]

def paired_bootstrap(a,b,draws=200000,seed=20260915):
 keys=sorted(a); delta=[a[k]-b[k] for k in keys]; rng=random.Random(seed)
 vals=sorted(sum(delta[rng.randrange(len(delta))] for _ in delta)/len(delta) for _ in range(draws))
 return [vals[int(.025*draws)],vals[int(.975*draws)]]

def require(cond,msg):
 if not cond: raise RuntimeError(msg)

def main():
 require(len(PLAN['arms'])==17 and PLAN['total_local_games']==544,'plan size')
 require(PLAN['source_sha']=='b7b26548a8800899318e5b78ca135c52e0117ed5','source receipt')
 require(sha(ROOT/'selfplay/models/ooc_strategic_tok_final.native')==PLAN['strategic_model_sha256'],'current strategic hash')
 results=[]; outcomes={}; raw_files=[]
 for arm in PLAN['arms']:
  name=arm['id']; profile=arm['profile']
  paths={kind:RAW/f'{name}{suffix}' for kind,suffix in {
   'csv':'.csv','meta':'.csv.meta.json','trace':'.mcts.csv','support':'.mcts.csv.support.jsonl',
   'receipt':'.receipt.json','score':'.score.json','log':'.log'}.items()}
  if not paths['log'].is_file(): paths['log']=RAW/f'{name}.log.gz'
  for kind,path in paths.items(): require(path.is_file(),f'{name}: missing {kind}')
  rows=list(csv.DictReader(open(paths['csv']))); require(len(rows)==32,f'{name}: result rows')
  byseed={int(r['seed']):r for r in rows}; require(set(byseed)==EXPECTED,f'{name}: result seeds')
  trace=list(csv.DictReader(open(paths['trace']))); require(len(trace)==32,f'{name}: trace rows')
  require({int(r['seed']) for r in trace}==EXPECTED,f'{name}: trace seeds')
  support=[json.loads(x) for x in open(paths['support']) if x.strip()]
  meta=json.load(open(paths['meta'])); receipt=json.load(open(paths['receipt'])); stored=json.load(open(paths['score']))
  require(meta['seedBlock']=={'lo':min(EXPECTED),'hi':max(EXPECTED)} and meta['nSeeds']==32,'meta cohort')
  require(meta['asc']==0 and meta['sims']==10000 and meta['threads']==12,'meta gameplay config')
  cfg=meta['config']; require(cfg['fairPlay'] and cfg['nativeOoc'] and cfg['effectiveCombatBackend']=='silver','meta backend')
  require(cfg['executableGitSha']==PLAN['source_sha'] and cfg['silverExactRootBudgets'],'meta source/budget')
  require(not cfg['collectKeys'] and not cfg['searcher3'] and not cfg['silverAdaptiveEnabled'],'meta exclusions')
  require(receipt['source']==PLAN['source_sha'] and receipt['binary_sha256']==PLAN['binary_sha256'],'receipt source/binary')
  require(receipt['combat_model_sha256']==PLAN['combat_model_sha256'] and receipt['seeds']==[min(EXPECTED),max(EXPECTED)],'receipt model/cohort')
  for key,value in profile.items(): require(receipt['env'].get(key)==value,f'{name}: profile {key}')
  require(receipt['env'].get('OMP_NUM_THREADS')=='12' and receipt['env'].get('STS_FAIR')=='1','receipt common env')
  log=(gzip.open(paths['log'],'rt',errors='replace').read() if paths['log'].suffix=='.gz' else paths['log'].read_text(errors='replace'))
  config_lines=re.findall(r'^\[ooc-mcts-config\] (\{.*\})$',log,re.MULTILINE)
  require(len(config_lines)==1,f'{name}: startup config count')
  actual=json.loads(config_lines[0]); expected={'prior':profile['STS_OOC_MCTS_PRIOR'],'temperature':float(profile['STS_OOC_MCTS_TEMPERATURE']),'cPuct':float(profile['STS_OOC_MCTS_CPUCT']),'wideningK':float(profile['STS_OOC_MCTS_WIDEN_K']),'wideningAlpha':float(profile['STS_OOC_MCTS_WIDEN_ALPHA']),'maxDepth':int(profile['STS_OOC_MCTS_MAX_DEPTH']),'rootSelection':profile['STS_OOC_MCTS_ROOT_SELECTION'],'earlyStop':True,'leafValue':profile['STS_OOC_MCTS_LEAF_VALUE'],'leafCombats':int(profile['STS_OOC_MCTS_LEAF_COMBATS']),'leafPolicy':profile['STS_OOC_MCTS_LEAF_POLICY'],'simulations':int(profile['STS_OOC_MCTS_SIMS'])}
  require(actual==expected,f'{name}: applied startup config')
  require('[fair-play / determinized MCTS ON]' in log and '[native OOC floor/win GBMs ON' in log and '[policy PUCT ON:' in log and '[ooc-strat-tok-net] loaded ' in log,f'{name}: startup markers')
  require('effectiveCombatBackend":"silver"' in paths['meta'].read_text(),'silver marker')
  wins=sum(int(r['won']) for r in rows); floors=[int(r['floor']) for r in rows]; secs=[float(r['sec']) for r in rows]
  calc={'wins':wins,'games':32,'win_rate':wins/32,'mean_floor':sum(floors)/32,'mean_seconds':sum(secs)/32}
  for key,value in calc.items(): require(abs(stored[key]-value)<1e-9,f'{name}: stored score {key}')
  telemetry={key:sum(int(r[key]) for r in trace) for key in ('oocDecisions','mctsOwned','mctsFallback','simulations','combatSurrogateSamples','mctsSupportAborts','continuationLimitAborts','earlyStopLockedRoot','savedSimulations')}
  require(telemetry['oocDecisions']==telemetry['mctsOwned']+telemetry['mctsFallback'],f'{name}: ownership accounting')
  require(all(int(r['mctsSupportAborts'])==int(r['unsupportedCombats'])+int(r['continuationLimitAborts']) for r in trace),f'{name}: abort accounting')
  require(all(int(r['simulationAttempts'])==int(r['simulations'])+int(r['mctsSupportAborts']) for r in trace),f'{name}: simulation accounting')
  budget=int(profile['STS_OOC_MCTS_SIMS'])
  require(all(int(r['simulations'])+int(r['savedSimulations'])==budget*int(r['mctsOwned'])+int(r['discardedSimulations']) for r in trace),f'{name}: full budget accounting')
  require(all(int(r['imaginedCombats'])==int(r['combatSurrogateSamples'])+int(r['unsupportedCombats']) and int(r['battleLeaves'])==0 for r in trace),f'{name}: imagined combat accounting')
  support_by_seed={int(r['seed']):r for r in support}; require(set(support_by_seed)==EXPECTED,f'{name}: support seeds')
  for seed,r in support_by_seed.items():
   t=next(x for x in trace if int(x['seed'])==seed)
   require(sum(r['reasons'].values())==int(t['unsupportedCombats']),f'{name}: support reasons')
   require(r['continuation_limit_aborts']==int(t['continuationLimitAborts']) and sum(r['continuation_reasons'].values())==int(t['continuationLimitAborts']),f'{name}: continuation reasons')
  outcomes[name]={s:int(r['won']) for s,r in byseed.items()}
  results.append({'id':name,'family':arm['family'],**calc,'win_rate_wilson95':wilson(wins,32),'wall_seconds':stored['wall_seconds'],'telemetry':telemetry,'support_reason_records':len(support),'profile':profile})
  raw_files.extend(paths.values())
 ref=outcomes['00_ref']
 for row in results:
  cur=outcomes[row['id']]; row['paired_win_delta_vs_reference']=sum(cur[s]-ref[s] for s in EXPECTED)/32
  row['paired_bootstrap95_vs_reference']=paired_bootstrap(cur,ref)
 ranked=sorted(results,key=lambda r:(-r['wins'],-r['mean_floor'],r['mean_seconds'],r['id']))
 summary={'schema_version':1,'source_sha':PLAN['source_sha'],'current_main_at_evidence_packaging':'608bb810c44173fb8c0036df6e89c71da4d778e3','binary_sha256':PLAN['binary_sha256'],'combat_model_sha256':PLAN['combat_model_sha256'],'strategic_model_provenance':{'plan_and_packaging_sha256':PLAN['strategic_model_sha256'],'per_arm_path_and_load_marker':True,'execution_time_byte_binding':False},'cohort':[min(EXPECTED),max(EXPECTED)],'arms':17,'games':544,'common_seeds':True,'selection_biased':True,'qualification':False,'rank_rule':['wins desc','mean_floor desc','mean_seconds asc','id asc'],'ranking':[r['id'] for r in ranked],'results':results,'interpretation':{'screening_leader':ranked[0]['id'],'leader_wins':ranked[0]['wins'],'leader_win_rate':ranked[0]['win_rate'],'limits':['The user explicitly overrode the repository aggregate local 128-seed policy.','The same 32 seeds were reused across all arms; comparisons are paired but this is a screening cohort.','The winning profile was selected on these outcomes, so its interval and lead are selection-biased.','No V4 control or fresh holdout was run in this 17x32 sweep.','The strategic model path and load marker are retained per arm; its plan-time hash matches packaging time, but the runner did not bind its bytes at execution.','Source b7b26548 predates current main Silver memory/cap changes; results do not qualify current main or a default change.']}}
 (HERE/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 labels={'00_ref':'reference: policy T1, c1.5, k2/a.5, depth32, native leaf, visits, 2048 sims','01_uniform15':'uniform prior, c1.5','02_uniform3':'uniform prior, c3','03_sharp':'policy T.5, c.5','04_flat':'policy T2, c3','05_greedy':'c0','06_narrow':'chance widening k1/a.25','07_broad':'chance widening k4/a.75','08_depth8':'depth8','09_depth16':'depth16','10_no_value':'constant .5 checkpoint leaf','11_rollout1':'one additional CTM combat','12_rollout3':'three additional CTM combats','13_uniform_leaf':'one CTM combat, uniform continuation','14_root_q':'root selection by mean Q','15_budget512':'512 simulations','16_budget10000':'10,000 simulations'}
 lines=['# Local 17 x 32 OOC MCTS parameter screen','',f"Tested source: `{summary['source_sha']}`. Packaging base: `{summary['current_main_at_evidence_packaging']}`.",'', 'All 17 profiles completed on common seeds `12002000..12002031`: Ironclad A0, fair RNG, exact-root-budget 10,000-simulation Silver combat, keys off, Act 3 stop, 12 OpenMP threads. Every arm has 32 result rows and 32 MCTS telemetry rows; source, binary, CTM, profile/environment, startup, ownership, simulation, support and abort-accounting receipts pass `analyze.py`. The strategic-model path and successful load marker are retained per arm; its plan-time hash matches packaging time, but the runner did not re-hash its bytes at execution.','', '| Rank | Profile | Change from reference | Wins | Win rate | Mean floor | Mean sec/game | Paired delta vs ref |','|---:|---|---|---:|---:|---:|---:|---:|']
 for i,r in enumerate(ranked,1): lines.append(f"| {i} | `{r['id']}` | {labels[r['id']]} | {r['wins']}/32 | {100*r['win_rate']:.1f}% | {r['mean_floor']:.3f} | {r['mean_seconds']:.1f} | {100*r['paired_win_delta_vs_reference']:+.1f} pp |")
 fastest=min(results,key=lambda r:r['mean_seconds'])
 leader=ranked[0]; lo,hi=leader['paired_bootstrap95_vs_reference']
 lines += ['',f"The descriptive screening leader is `{leader['id']}` with {leader['wins']}/32 wins ({100*leader['win_rate']:.1f}%) and mean floor {leader['mean_floor']:.1f}. It uses three additional CTM-resolved combats before native leaf scoring. Its mean elapsed time was {leader['mean_seconds']:.1f}s/game: {leader['mean_seconds']/results[0]['mean_seconds']:.1f}x the reference and {leader['mean_seconds']/fastest['mean_seconds']:.1f}x the fastest profile (`{fastest['id']}`). Ranking uses wins, floor, then time rather than treating speed as equivalent to win rate.",'',f"The rollout3 telemetry records {leader['telemetry']['combatSurrogateSamples']:,} successful CTM surrogate samples versus {results[0]['telemetry']['combatSurrogateSamples']:,} for reference ({leader['telemetry']['combatSurrogateSamples']/results[0]['telemetry']['combatSurrogateSamples']:.1f}x). Together with the {leader['mean_seconds']/results[0]['mean_seconds']:.1f}x elapsed-time ratio, this identifies the added CTM workload; it is not a component-level profiler and does not exclude V4, value-model or other overhead.",'',f"Against the reference on these paired seeds, the leader's observed delta is {100*leader['paired_win_delta_vs_reference']:+.1f} percentage points; the deterministic 200,000-resample paired percentile interval is [{100*lo:+.1f}, {100*hi:+.1f}] points and includes zero. Its unpaired Wilson 95% win-rate interval is [{100*leader['win_rate_wilson95'][0]:.1f}%, {100*leader['win_rate_wilson95'][1]:.1f}%]. These are descriptive uncertainty summaries, not selection-adjusted inference.",'','This is discovery evidence. The leader and its uncertainty were selected on the same cohort, there is no V4 control or untouched holdout, and the tested source predates current-main Silver memory/cap changes. It does not qualify a default or current-main gameplay improvement.','', 'Raw CSV, metadata, MCTS telemetry, support reasons, environment receipts, scores and deterministic compressed logs are retained under `raw/`. `file-index.json` binds every other tracked packet file.','', 'Knowledge impact: experiment evidence only. No maintained architecture, behavior, model, support, RNG, or deployment fact changes.']
 (HERE/'README.md').write_text('\n'.join(lines)+'\n')
 # Deterministically compress verbose stdout logs after every semantic check.
 for path in sorted(RAW.glob('*.log')):
  target=Path(str(path)+'.gz')
  with open(path,'rb') as src, open(target,'wb') as dst:
   with gzip.GzipFile(filename='',mode='wb',fileobj=dst,mtime=0) as gz: gz.write(src.read())
  path.unlink()
 files=[]
 for path in sorted(HERE.rglob('*')):
  if path.is_file() and '__pycache__' not in path.parts and path.name!='file-index.json': files.append({'path':str(path.relative_to(HERE)),'bytes':path.stat().st_size,'sha256':sha(path)})
 (HERE/'file-index.json').write_text(json.dumps({'schema_version':1,'files':files},indent=2,sort_keys=True)+'\n')
 print(json.dumps({'validated_arms':17,'validated_games':544,'leader':ranked[0]['id'],'wins':ranked[0]['wins'],'files':len(files)},sort_keys=True))

if __name__=='__main__': main()
