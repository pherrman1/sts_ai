#!/usr/bin/env python3
import csv, hashlib, json, os, subprocess, sys, time
from pathlib import Path

PLAN_PATH=Path('/tmp/sts-old-new-v2-pair64-plan.json')
OUT=Path('/tmp/sts-old-new-v2-pair64-20260915')

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def rows(path,start,count):
    data=list(csv.DictReader(open(path)))
    expected=set(range(start,start+count))
    if len(data)!=count or {int(row['seed']) for row in data}!=expected:
        raise RuntimeError(f'invalid paired rows or seeds in {path}')
    return data

def validate_record(record,arm,plan,lo,n,path):
        config=record['config']; models=record['models']
        checks={
          'objective':record['objective']=='bestbench','seedBlock':record['seedBlock']=={'lo':lo,'hi':lo+n-1},
          'nSeeds':record['nSeeds']==n,'asc':record['asc']==0,'sims':record['sims']==plan['combatSimulations'],
          'threads':record['threads']==plan['ompThreads'],'fairPlay':config['fairPlay'] is True,
          'backend':config['effectiveCombatBackend']=='silver','silver':config['silverSearchEnabled'] is True,
          'exact':config['silverExactRootBudgets'] is True,'capMode':config['silverReuseCapMode']=='allocated',
          'cap':config['silverReuseCap']==32768,'source':config['executableGitSha']==arm['sourceSha'],
          'nativeOoc':config['nativeOoc'] is True,'keys':config['collectKeys'] is False,
          'searcher':config['searcher3'] is False,'policy':models['policyNet']=='ON',
          'floor':models['floor']=='models/v_rich_trees.txt','win':models['win']=='models/v_win_trees.txt'}
        failed=[name for name,passed in checks.items() if not passed]
        if failed: raise RuntimeError(f'metadata mismatch {path}: {failed}')

def validate_meta(path,arm,plan,expected_records=2):
    records=[json.loads(line) for line in open(path) if line.strip()]
    if len(records)!=expected_records: raise RuntimeError(f'expected {expected_records} metadata records in {path}')
    expected=[(plan['seedStart'],1),(plan['seedStart']+1,plan['seedCount']-1)]
    for record,(lo,n) in zip(records,expected): validate_record(record,arm,plan,lo,n,path)

def validate_canary_log(log,strategic,model,arm,plan):
    content=log.read_text()
    markers=(f'[ooc-strat-tok-net] loaded {strategic}',
      f'live OOC MCTS ON sims=2048 combat_model={model} prior=policy temperature=1 cpuct=1.5 widen_k=2 widen_alpha=0.5 max_depth=32 root_selection=visits early_stop=1 leaf_value=native leaf_combats=0 leaf_policy=v4',
      'isolated Silver combat backend ON: local Silver RNG/chance search; Searcher3 particles bypassed; reuse-cap=allocated cap=32768')
    for marker in markers:
        if marker not in content: raise RuntimeError(f"missing {marker} for {arm['id']}")

def main():
    plan=json.load(open(PLAN_PATH)); start=plan['seedStart']; count=plan['seedCount']
    if OUT.exists():
        if json.load(open(OUT/'plan.json'))!=plan: raise RuntimeError('existing output plan differs')
    else:
        OUT.mkdir(); (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    common={
      'STS_FAIR':'1','STS_SEARCHER3':'0','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1',
      'STS_SILVER_REUSE_CAP_MODE':'allocated','STS_SILVER_ADAPTIVE':'0','STS_SILVER_VNET_LEAF_DIRECT':'0',
      'STS_SILVER_TELEMETRY':'1','STS_NATIVE_OOC':'1','STS_OOC_STRATEGIC_REST':'1',
      'STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1','STS_OOC_STRATEGIC_TREASURE':'1',
      'STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0','STS_STOP_AFTER_ACT':'3',
      'STS_COLLECT_KEYS':'0','OMP_NUM_THREADS':str(plan['ompThreads']),'STS_OOC_MCTS':'1',
      **plan['oocMctsProfile'],**plan['explicitControls']}
    for phase,offset,n in [('canary',0,1),('remainder',1,count-1)]:
      for arm in plan['arms']:
        root=Path(arm['root']); binary=Path(arm['binary']); model=Path(arm['combatModel'])
        strategic=root/'selfplay/models/ooc_strategic_tok_final.native'
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=arm['sourceSha']:
            raise RuntimeError(f"source drift {arm['id']}")
        if sha(binary)!=arm['binarySha256'] or sha(model)!=arm['combatModelSha256']:
            raise RuntimeError(f"binary/model drift {arm['id']}")
        if sha(strategic)!=plan['strategicModelSha256']:
            raise RuntimeError(f"strategic model drift {arm['id']}")
        for relative,expected_hash in plan['treeModelSha256'].items():
            if sha(root/relative)!=expected_hash: raise RuntimeError(f"tree model drift {arm['id']} {relative}")
        result=OUT/f"{arm['id']}.csv"; log=OUT/f"{arm['id']}.{phase}.log"; trace=OUT/f"{arm['id']}.mcts.csv"
        expected=offset+n
        if result.exists() and len(list(csv.DictReader(open(result))))==expected:
            rows(result,start,expected)
            validate_meta(Path(str(result)+'.meta.json'),arm,plan,1 if phase=='canary' else 2)
            if phase=='canary': validate_canary_log(log,strategic,model,arm,plan)
            print('RESUME_VALIDATED',phase,arm['id'],'rows',expected,flush=True)
            continue
        clean_ambient={key:value for key,value in os.environ.items() if not key.startswith('STS_')}
        env={**clean_ambient,**common,'STS_EXECUTABLE_GIT_SHA':arm['sourceSha'],
             'STS_OOC_MCTS_COMBAT_MODEL':str(model),'STS_OOC_STRATEGIC_TOK_NN':str(strategic),
             'STS_OOC_MCTS_TRACE':str(trace)}
        argv=[str(binary),'bestbench',str(plan['combatSimulations']),str(n),'0',str(start+offset),str(result)]
        receipt={'phase':phase,'arm':arm['id'],'sourceSha':arm['sourceSha'],'binarySha256':sha(binary),
          'combatModelSha256':sha(model),'strategicModelSha256':sha(strategic),'argv':argv,
          'env':{key:env[key] for key in sorted(env) if key.startswith('STS_') or key=='OMP_NUM_THREADS'}}
        (OUT/f"{arm['id']}.{phase}.receipt.json").write_text(json.dumps(receipt,indent=2)+'\n')
        print('START',phase,arm['id'],flush=True); begun=time.time()
        with open(log,'x') as output:
            subprocess.run(['bash',str(root/'tools/seed_guard.sh'),*argv],cwd=root,env=env,
                           stdout=output,stderr=subprocess.STDOUT,check=True)
        rows(result,start,expected)
        validate_meta(Path(str(result)+'.meta.json'),arm,plan,1 if phase=='canary' else 2)
        print('COMPLETE',phase,arm['id'],'rows',expected,'wall',time.time()-begun,flush=True)
        if phase=='canary':
            validate_canary_log(log,strategic,model,arm,plan)
    for arm in plan['arms']:
        result=OUT/f"{arm['id']}.csv"; rows(result,start,count)
        validate_meta(Path(str(result)+'.meta.json'),arm,plan)
    print('PAIR64_COMPLETE',flush=True)

if __name__=='__main__': main()
