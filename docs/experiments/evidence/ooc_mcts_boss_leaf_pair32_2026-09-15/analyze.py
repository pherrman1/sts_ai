#!/usr/bin/env python3
import csv, hashlib, json, random
from pathlib import Path

HERE=Path(__file__).resolve().parent
RAW=HERE/'raw'; PLAN=json.loads((HERE/'plan.json').read_text())

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def rows(name,suffix='.csv'):
    result=list(csv.DictReader(open(RAW/f'{name}{suffix}')))
    expected=set(range(PLAN['seeds'][0],PLAN['seeds'][1]+1))
    if len(result)!=32 or {int(r['seed']) for r in result}!=expected:
        raise RuntimeError(f'incomplete {name}{suffix}')
    return {int(r['seed']):r for r in result}

def main():
    arms={name:rows(name) for name in ('native','boss')}
    traces={name:rows(name,'.mcts.csv') for name in ('native','boss')}
    seeds=sorted(arms['native'])
    deltas=[int(arms['boss'][s]['won'])-int(arms['native'][s]['won']) for s in seeds]
    rng=random.Random(20260915)
    boot=sorted(sum(deltas[rng.randrange(32)] for _ in range(32))/32 for _ in range(200000))
    state_fields=('won','floor','act','hpEnd','maxHp','fightsLost','deathCombat','deathEncounter')
    trace_fields=[k for k in next(iter(traces['native'].values())) if k not in ('mctsWallSec','mctsCpuSec')]
    summary={
      'classification':'BOSS_LEAF_NO_OBSERVED_BEHAVIORAL_EFFECT',
      'seeds':PLAN['seeds'],
      'arms':{},
      'paired':{
        'both_win':sum(int(arms['native'][s]['won']) and int(arms['boss'][s]['won']) for s in seeds),
        'both_lose':sum(not int(arms['native'][s]['won']) and not int(arms['boss'][s]['won']) for s in seeds),
        'native_only':sum(d<0 for d in deltas),'boss_only':sum(d>0 for d in deltas),
        'boss_minus_native_win_rate':sum(deltas)/32,
        'bootstrap_200k_percentile95':[boot[5000],boot[194999]],
        'identical_terminal_state_rows':sum(all(arms['native'][s][k]==arms['boss'][s][k] for k in state_fields) for s in seeds),
        'identical_nontiming_trace_rows':sum(all(traces['native'][s][k]==traces['boss'][s][k] for k in trace_fields) for s in seeds)
      },
      'artifacts':{}
    }
    for name in ('native','boss'):
        a=arms[name]; t=traces[name]
        summary['arms'][name]={
          'wins':sum(int(r['won']) for r in a.values()),
          'mean_floor':sum(int(r['floor']) for r in a.values())/32,
          'mean_final_hp':sum(int(r['hpEnd']) for r in a.values())/32,
          'mean_seconds':sum(float(r['sec']) for r in a.values())/32,
          'ooc_decisions':sum(int(r['oocDecisions']) for r in t.values()),
          'mcts_owned':sum(int(r['mctsOwned']) for r in t.values()),
          'mcts_fallback':sum(int(r['mctsFallback']) for r in t.values()),
          'completed_simulations':sum(int(r['simulations']) for r in t.values()),
          'leaf_evaluations':sum(int(r['leafEvaluations']) for r in t.values()),
          'support_aborts':sum(int(r['mctsSupportAborts']) for r in t.values()),
          'discarded_simulations':sum(int(r['discardedSimulations']) for r in t.values())
        }
        for suffix in ('.csv','.mcts.csv','.mcts.csv.support.jsonl','.receipt.json','.score.json'):
            path=RAW/f'{name}{suffix}'; summary['artifacts'][path.relative_to(HERE).as_posix()]=sha(path)
    (HERE/'results.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,indent=2,sort_keys=True))

if __name__=='__main__': main()
