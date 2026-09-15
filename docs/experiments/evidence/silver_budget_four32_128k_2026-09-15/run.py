import os,json,hashlib,subprocess,time
from pathlib import Path
root=Path.cwd(); out=root/'build/silver-budget-four32-20260915';binary=root/'build/linux-gcc-release-ccache/one_combat'
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert sha=='53a3ba36cb58876f192167162587eacae7c89556'
assert hashlib.sha256(binary.read_bytes()).hexdigest()==json.loads((root/'build/silver-cap-pair-20260915/provenance.json').read_text())['binary_sha256']
assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
common={ 'OMP_NUM_THREADS':'4','STS_FAIR':'1','STS_SEARCHER3':'0','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1','STS_SILVER_REUSE_CAP_MODE':'allocated','STS_SILVER_ADAPTIVE':'0','STS_SILVER_VNET_LEAF_DIRECT':'0','STS_SILVER_TELEMETRY':'1','STS_NATIVE_OOC':'1','STS_COLLECT_KEYS':'0','STS_OOC_MCTS':'0','STS_SILVER_REUSE_CAP':'131072','STS_SIM_ADAPT':'0'}
env={k:v for k,v in os.environ.items() if not k.startswith(('STS_','STRATEGIC_','OMP_'))}
packet={'handoff_sha':sha,'measured_code_sha':'2b29e9723a00b9dc6fcea45507e4dcf86c968cde','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'common_environment':common,'seeds':list(range(16,48)),'inventory':'Prior N16 cap comparison uses seeds0-15 and only exact10k; prior flat1k parity uses different cap/code. Neither qualifies for this matched four-arm N32 budget experiment.','decision_rule':'Exploratory fixed four-arm N32 matched outcome/compute/cap/resource comparison. No additional arms/seeds or tuning after results; report all pairwise comparisons and multiplicity/uncertainty.','arms':{},'models_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'models/v_win_trees.txt',root/'models/v_rich_trees.txt',root/'models/policy_trees_c.txt']}}
for label,normal,elite,boss in [('flat1k',1000,1000,1000),('tier1_2_5k',1000,2000,5000),('flat10k',10000,10000,10000),('tier10_20_50k',10000,20000,50000)]:
    result=out/f'{label}.csv';log=out/f'{label}.log';diag=out/f'{label}-decisions.csv';memory=out/f'{label}-time.txt'
    assert not any(p.exists() for p in (result,log,diag,memory))
    options=common|{'STS_SIMS_NORMAL':str(normal),'STS_SIMS_ELITE':str(elite),'STS_SIMS_BOSS':str(boss),'STS_SILVER_SCALING_DIAG_FILE':str(diag)}
    command=['/usr/bin/time','-v','-o',str(memory),'bash',str(root/'tools/seed_guard.sh'),str(binary),'bestbench',str(normal),'32','0','16',str(result)]
    record={'budgets':{'normal':normal,'elite':elite,'boss':boss},'environment':options,'command':command,'started_unix':time.time()};packet['arms'][label]=record
    (out/'provenance.json').write_text(json.dumps(packet,indent=2)+'\n')
    print('START',label,flush=True)
    with log.open('w') as f: record['exit_code']=subprocess.call(command,env=env|options,stdout=f,stderr=subprocess.STDOUT,cwd=root)
    record['completed_unix']=time.time();(out/'provenance.json').write_text(json.dumps(packet,indent=2)+'\n')
    print('COMPLETE',label,'exit',record['exit_code'],flush=True)
    if record['exit_code']:raise SystemExit(record['exit_code'])
