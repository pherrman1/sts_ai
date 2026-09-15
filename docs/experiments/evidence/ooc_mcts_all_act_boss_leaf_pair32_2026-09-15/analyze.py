#!/usr/bin/env python3
import csv,hashlib,json,random
from pathlib import Path
HERE=Path(__file__).resolve().parent;RAW=HERE/'raw';PLAN=json.loads((HERE/'plan.json').read_text())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def load(name,suffix='.csv'):
 x=list(csv.DictReader(open(RAW/f'{name}{suffix}')));expected=set(range(PLAN['seeds'][0],PLAN['seeds'][1]+1))
 if len(x)!=32 or {int(r['seed']) for r in x}!=expected:raise RuntimeError(f'incomplete {name}{suffix}')
 return {int(r['seed']):r for r in x}
def main():
 arms={n:load(n) for n in ('native','all_bosses')};traces={n:load(n,'.mcts.csv') for n in arms};seeds=sorted(arms['native'])
 d=[int(arms['all_bosses'][s]['won'])-int(arms['native'][s]['won']) for s in seeds];rng=random.Random(20260915);boot=sorted(sum(d[rng.randrange(32)] for _ in range(32))/32 for _ in range(200000))
 states=('won','floor','act','hpEnd','maxHp','fightsLost','deathCombat','deathEncounter');tracekeys=[k for k in next(iter(traces['native'].values())) if k not in ('mctsWallSec','mctsCpuSec')]
 out={'classification':'ALL_ACT_BOSS_LEAF_NO_OBSERVED_BEHAVIORAL_EFFECT','seeds':PLAN['seeds'],'arms':{},'paired':{'both_win':sum(int(arms['native'][s]['won']) and int(arms['all_bosses'][s]['won']) for s in seeds),'both_lose':sum(not int(arms['native'][s]['won']) and not int(arms['all_bosses'][s]['won']) for s in seeds),'native_only':sum(x<0 for x in d),'all_bosses_only':sum(x>0 for x in d),'all_bosses_minus_native_win_rate':sum(d)/32,'bootstrap_200k_percentile95':[boot[5000],boot[194999]],'identical_terminal_state_rows':sum(all(arms['native'][s][k]==arms['all_bosses'][s][k] for k in states) for s in seeds),'identical_nontiming_trace_rows':sum(all(traces['native'][s][k]==traces['all_bosses'][s][k] for k in tracekeys) for s in seeds)},'artifacts':{}}
 for n in arms:
  a=arms[n];t=traces[n];out['arms'][n]={'wins':sum(int(r['won']) for r in a.values()),'mean_floor':sum(int(r['floor']) for r in a.values())/32,'mean_final_hp':sum(int(r['hpEnd']) for r in a.values())/32,'mean_seconds':sum(float(r['sec']) for r in a.values())/32,**{k:sum(int(r[v]) for r in t.values()) for k,v in {'ooc_decisions':'oocDecisions','mcts_owned':'mctsOwned','mcts_fallback':'mctsFallback','completed_simulations':'simulations','leaf_evaluations':'leafEvaluations','support_aborts':'mctsSupportAborts','discarded_simulations':'discardedSimulations','continuation_limit_aborts':'continuationLimitAborts'}.items()}}
  for suffix in ('.csv','.mcts.csv','.mcts.csv.support.jsonl','.receipt.json','.score.json'):
   p=RAW/f'{n}{suffix}';out['artifacts'][p.relative_to(HERE).as_posix()]=sha(p)
 (HERE/'results.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()
