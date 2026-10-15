#!/usr/bin/env python3
import csv, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent; RAW=HERE/'raw'
def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()
def load(arm,suffix):
    rows=list(csv.DictReader(open(RAW/f'initial8_{arm}{suffix}')))
    if len(rows)!=8 or {int(r['seed']) for r in rows}!=set(range(12003064,12003072)):
        raise RuntimeError(f'incomplete initial8_{arm}{suffix}')
    return {int(r['seed']):r for r in rows}

def main():
    arms={a:load(a,'.csv') for a in ('native','boss')}
    traces={a:load(a,'.mcts.csv') for a in ('native','boss')}
    seeds=sorted(arms['native'])
    state_fields=('won','floor','act','hpEnd','maxHp','fightsLost','deathCombat','deathEncounter')
    trace_fields=[k for k in next(iter(traces['native'].values())) if k not in ('mctsWallSec','mctsCpuSec')]
    out={'classification':'CORRECTED_MECHANISM_PASS_PAIRED_N8_SMOKE','seeds':[seeds[0],seeds[-1]],
      'mechanism':json.loads((HERE/'mechanism.json').read_text()),'arms':{},
      'paired':{'native_only':sum(int(arms['native'][s]['won'])>int(arms['boss'][s]['won']) for s in seeds),
        'boss_only':sum(int(arms['boss'][s]['won'])>int(arms['native'][s]['won']) for s in seeds),
        'boss_minus_native_win_rate':sum(int(arms['boss'][s]['won'])-int(arms['native'][s]['won']) for s in seeds)/8,
        'terminal_rows_different':sum(any(arms['native'][s][k]!=arms['boss'][s][k] for k in state_fields) for s in seeds),
        'nontiming_trace_rows_different':sum(any(traces['native'][s][k]!=traces['boss'][s][k] for k in trace_fields) for s in seeds)},
      'interrupted_extension':{'native_rows':8,'boss_rows':3,'included_in_result':False},'artifacts':{}}
    for arm in arms:
        a=arms[arm]; t=traces[arm]
        out['arms'][arm]={'wins':sum(int(r['won']) for r in a.values()),
          'mean_floor':sum(int(r['floor']) for r in a.values())/8,
          'mean_final_hp':sum(int(r['hpEnd']) for r in a.values())/8,
          'mean_seconds':sum(float(r['sec']) for r in a.values())/8,
          'ooc_decisions':sum(int(r['oocDecisions']) for r in t.values()),
          'leaf_evaluations':sum(int(r['leafEvaluations']) for r in t.values())}
        for suffix in ('.csv','.mcts.csv','.mcts.csv.support.jsonl','.receipt.json','.score.json'):
            p=RAW/f'initial8_{arm}{suffix}'; out['artifacts'][p.relative_to(HERE).as_posix()]=sha(p)
    (HERE/'results.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__': main()
