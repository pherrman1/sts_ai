#!/usr/bin/env python3
import csv, hashlib, json, os, subprocess, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
RAW=OUT/'raw'; RAW.mkdir(exist_ok=True)
PLAN=json.loads((OUT/'plan.json').read_text())
BINARY=ROOT/'build/linux-gcc-release/one_combat'
COMBAT=ROOT/PLAN['combat_model']
POLICY=ROOT/'selfplay/models/ooc_strategic_tok_final.native'
START, END=PLAN['seeds']; COUNT=END-START+1

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def validate(path):
    rows=list(csv.DictReader(open(path)))
    if len(rows)!=COUNT or {int(r['seed']) for r in rows}!=set(range(START,END+1)):
        raise RuntimeError(f'invalid rows/seeds in {path}')
    return {'wins':sum(int(r['won']) for r in rows),'games':COUNT,
            'mean_floor':sum(int(r['floor']) for r in rows)/COUNT,
            'mean_hp':sum(int(r['hpEnd']) for r in rows)/COUNT,
            'mean_seconds':sum(float(r['sec']) for r in rows)/COUNT}

def main():
    observed={'binary_sha256':sha(BINARY),'combat_model_sha256':sha(COMBAT),'ooc_policy_sha256':sha(POLICY)}
    for key,value in observed.items():
        if value!=PLAN[key]: raise RuntimeError(f'{key} drift: {value}')
    common={
      'OMP_NUM_THREADS':'12','STS_FAIR':'1','STS_SEARCHER3':'0','STS_SILVER_SEARCH':'1',
      'STS_SILVER_EXACT_ROOT_BUDGETS':'1','STS_SILVER_REUSE_CAP_MODE':'allocated',
      'STS_SILVER_ADAPTIVE':'0','STS_SILVER_VNET_LEAF_DIRECT':'0','STS_SILVER_TELEMETRY':'1',
      'STS_NATIVE_OOC':'1','STS_OOC_STRATEGIC_TOK_NN':str(POLICY),
      'STS_OOC_STRATEGIC_REST':'1','STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1',
      'STS_OOC_STRATEGIC_TREASURE':'1','STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0',
      'STS_STOP_AFTER_ACT':'3','STS_COLLECT_KEYS':'0','STS_OOC_MCTS':'1','STS_OOC_MCTS_SIMS':'512',
      'STS_OOC_MCTS_COMBAT_MODEL':str(COMBAT),'STS_OOC_MCTS_PRIOR':'policy','STS_OOC_MCTS_TEMPERATURE':'1',
      'STS_OOC_MCTS_CPUCT':'1.5','STS_OOC_MCTS_WIDEN_K':'2','STS_OOC_MCTS_WIDEN_ALPHA':'0.5',
      'STS_OOC_MCTS_MAX_DEPTH':'32','STS_OOC_MCTS_ROOT_SELECTION':'visits','STS_OOC_MCTS_LEAF_COMBATS':'0',
      'STS_OOC_MCTS_LEAF_POLICY':'v4','STS_EXECUTABLE_GIT_SHA':PLAN['source_head']
    }
    for arm in ('native','boss'):
        result=RAW/f'{arm}.csv'; log=RAW/f'{arm}.log'; trace=RAW/f'{arm}.mcts.csv'
        if result.exists():
            print('COMPLETED_VALIDATED',arm,json.dumps(validate(result)),flush=True); continue
        if any(p.exists() for p in (log,trace,Path(str(trace)+'.support.jsonl'))):
            raise RuntimeError(f'partial arm exists: {arm}')
        env={**os.environ,**common,'STS_OOC_MCTS_LEAF_VALUE':arm,'STS_OOC_MCTS_TRACE':str(trace)}
        receipt={'arm':arm,**observed,'source_head':PLAN['source_head'],
                 'implementation_diff_sha256':PLAN['implementation_diff_sha256'],'seeds':[START,END],
                 'env':{k:env[k] for k in sorted(env) if k.startswith('STS_') or k=='OMP_NUM_THREADS'},
                 'argv':[str(BINARY),'bestbench','10000',str(COUNT),'0',str(START),str(result)]}
        (RAW/f'{arm}.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        command=['bash',str(ROOT/'tools/seed_guard.sh'),str(BINARY),'bestbench','10000',str(COUNT),'0',str(START),str(result)]
        print('START',arm,flush=True); begun=time.time()
        with open(log,'w') as out:
            subprocess.run(command,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
        score=validate(result); score['wall_seconds']=time.time()-begun
        (RAW/f'{arm}.score.json').write_text(json.dumps(score,indent=2)+'\n')
        print('COMPLETED_VALIDATED',arm,json.dumps(score),flush=True)
    print('PAIR_COMPLETE',flush=True)

if __name__=='__main__': main()
