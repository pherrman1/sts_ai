import json,csv,re,hashlib,math
from pathlib import Path
import numpy as np
root=Path('/home/philippherrmann/Documents/sts/sts_lightspeed');folder=root/'build/ooc-mcts-fresh64-10000/official';result=json.load(open(folder.parent/'result.json'));manifest=json.load(open(root/'docs/experiments/evidence/live_ooc_mcts_fresh64_10000_2026-09-14/official.manifest.json'));seeds=list(range(980000,980064));arms={};traces={};reviews={}
for arm in manifest['arms']:
 name=arm['name'];config=json.load(open(folder/(name+'.config.json')))['env'];assert config=={**manifest['common_env'],**arm['env']}
 for suffix,target in (('.csv',arms),('.csv.mcts.csv',traces)):
  with open(folder/(name+suffix)) as f:data=list(csv.DictReader(f))
  target[name]={int(r['seed']):r for r in data};assert len(data)==len(target[name])==64 and set(target[name])==set(seeds)
 meta=json.load(open(folder/(name+'.csv.meta.json')));assert meta['argv']==['bestbench','10000','64','0','980000','/home/philippherrmann/sts_sweep/'+arm['results']];assert meta['nSeeds']==64 and meta['threads']==24 and meta['sims']==10000 and meta['asc']==0 and meta['seedBlock']==dict(lo=980000,hi=980063)
 c=meta['config'];assert c['executableGitSha']==manifest['frozen_sha'] and c['fairPlay'] and c['silverSearchEnabled'] and c['silverExactRootBudgets'] and c['effectiveCombatBackend']=='silver' and not c['searcher3'] and not c['silverAdaptiveEnabled'] and not c['collectKeys']
 for r in traces[name].values():
  t={k:float(v) for k,v in r.items()};assert t['battleLeaves']==0 and t['realCombats']>0 and 0<=t['maxDepth']<=32
  if name=='control':assert all(t[k]==0 for k in ('mctsOwned','mctsFallback','simulations','simulationAttempts','combatSurrogateSamples','imaginedCombats','unsupportedCombats','mctsSupportAborts','discardedSimulations'))
  else:
   assert t['oocDecisions']==t['mctsOwned']+t['mctsFallback'];assert t['simulations']==10000*t['mctsOwned']+t['discardedSimulations'];assert t['simulationAttempts']==t['simulations']+t['mctsSupportAborts'];assert 0<=t['discardedSimulations']<=9999*t['mctsSupportAborts'] and t['unsupportedCombats']==t['mctsSupportAborts']<=t['mctsFallback'];assert t['imaginedCombats']==t['combatSurrogateSamples']+t['unsupportedCombats']
 reasons=list(map(json.loads,(folder/(name+'.csv.mcts.csv.support.jsonl')).read_text().splitlines()));assert len(reasons)==64 and {r['seed'] for r in reasons}==set(seeds)
 for r in reasons:assert sum(r['reasons'].values())==int(traces[name][r['seed']]['unsupportedCombats'])
 log=(folder/(name+'.log')).read_text();combats=sum(int(r['realCombats']) for r in traces[name].values());assert len(re.findall(r'\[silver-combat\]',log))==combats;assert not re.findall(r'(?:conversion_failures|semantic_resolution_failures|transaction_failures|knowledge_failures)=[1-9][0-9]*',log)
 for text in ('[ooc-strat-tok-net] loaded '+config['STS_OOC_STRATEGIC_TOK_NN'],'448 feats from models/v_win_trees.txt','448 feats from models/v_rich_trees.txt','[policy PUCT ON: models/policy_trees_c.txt, 100 trees]','[benchmark stops after Act 3 boss]','[fair-play / determinized MCTS ON]'):assert text in log,text
 if name=='treatment':assert '[live OOC MCTS ON sims=10000 combat_model='+config['STS_OOC_MCTS_COMBAT_MODEL']+']' in log
 reviews[name]=dict(wins=sum(int(r['won']) for r in arms[name].values()),realSilverCombats=combats,zeroBridgeFailures=True,owned=sum(int(r['mctsOwned']) for r in traces[name].values()),supportAborts=sum(int(r['mctsSupportAborts']) for r in traces[name].values()),surrogateSamples=sum(int(r['combatSurrogateSamples']) for r in traces[name].values()),maxDepth=max(int(r['maxDepth']) for r in traces[name].values()))
# Same 200000 paired PCG64 resamples independently constructed, all metrics computed from raw outcomes.
indices=np.random.Generator(np.random.PCG64(20260914)).integers(0,64,size=(200000,64));paired={}
for key in ('won','floor','hpEnd','fightsLost','deathCombat','sec'):
 a=np.array([float(arms['control'][s][key]) for s in seeds]);b=np.array([float(arms['treatment'][s][key]) for s in seeds]);delta=b-a;ci=np.quantile(delta[indices].mean(1),[.025,.975],method='linear');paired[key]=dict(control_mean=float(a.mean()),treatment_mean=float(b.mean()),treatment_minus_control=float(delta.mean()),paired_bootstrap_95_ci=ci.tolist());assert paired[key]==result['paired_outcomes'][key]
tonly=sum(int(arms['treatment'][s]['won'])==1 and int(arms['control'][s]['won'])==0 for s in seeds);conly=sum(int(arms['control'][s]['won'])==1 and int(arms['treatment'][s]['won'])==0 for s in seeds);n=tonly+conly;pvalue=min(1,2*sum(math.comb(n,k) for k in range(min(tonly,conly)+1))/2**n) if n else 1
assert result['treatment_only_wins']==tonly and result['control_only_wins']==conly and result['same_result_seeds']==64-tonly-conly and result['exact_two_sided_discordant_binomial_p']==pvalue
lo,hi=paired['won']['paired_bootstrap_95_ci'];classification='OOC_MCTS_WINRATE_UP' if lo>0 else 'OOC_MCTS_WINRATE_DOWN' if hi<0 else 'OOC_MCTS_WINRATE_INCONCLUSIVE'
if not reviews['treatment']['owned'] or not reviews['treatment']['surrogateSamples']:classification='OOC_MCTS_NO_SEARCH_COVERAGE'
assert classification==result['classification'];assert result['seeds']==seeds and result['control_wins']==reviews['control']['wins'] and result['treatment_wins']==reviews['treatment']['wins'];assert result['win_difference_pp']==100*paired['won']['treatment_minus_control'] and result['win_difference_95_ci_pp']==[100*lo,100*hi]
ratio=paired['sec']['treatment_mean']/paired['sec']['control_mean'];assert ratio==result['runtime_ratio_of_mean_per_run_seconds']
for key in traces['treatment'][seeds[0]]:
 if key not in ('seed','maxDepth'):assert sum(float(traces['treatment'][s][key]) for s in seeds)/64==result['diagnostics']['mean_'+key+'_per_run']
freeze=json.load(open(folder.parent/'remote-freeze-info.json'));assert freeze['sha']==manifest['frozen_sha'];assert list(freeze['hashes'].values())==[manifest['binary']['sha256']]+[r['sha256'] for r in manifest['artifacts']]
review=dict(passed=True,classification=classification,source=manifest['frozen_sha'],seeds=64,arms=reviews,discordance=dict(treatmentOnly=tonly,controlOnly=conly,sameOutcome=64-tonly-conly,exactTwoSidedBinomialP=pvalue),pairedOutcomes=paired,runtimeRatio=ratio,bootstrap=dict(replicates=200000,rng='PCG64',seed=20260914,paired=True),fullConfigModelHashBinding=True,reviewerGameplay=0,interpretation='Inconclusive fresh engineering policy comparison; point estimate favors V4, CI includes zero. Sequential same-host elapsed-time ratio descriptive; no causal comparison against historical budgets.')
path=Path('/tmp/ooc-mcts-fresh64-10000-independent-final-review.json');path.write_text(json.dumps(review,indent=2)+'\n');print(json.dumps(review))
