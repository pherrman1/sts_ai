import os,json,hashlib,subprocess,time
from pathlib import Path
root=Path.cwd(); out=root/'build/silver-cap-pair-20260915';binary=root/'build/linux-gcc-release-ccache/one_combat'
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert sha=='2b29e9723a00b9dc6fcea45507e4dcf86c968cde'
assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
common={ 'OMP_NUM_THREADS':'4','STS_FAIR':'1','STS_SEARCHER3':'0','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1','STS_SILVER_REUSE_CAP_MODE':'allocated','STS_SILVER_ADAPTIVE':'0','STS_SILVER_VNET_LEAF_DIRECT':'0','STS_SILVER_TELEMETRY':'1','STS_NATIVE_OOC':'1','STS_COLLECT_KEYS':'0','STS_OOC_MCTS':'0'}
env={k:v for k,v in os.environ.items() if not k.startswith(('STS_','STRATEGIC_','OMP_'))}
packet={'measured_sha':sha,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'common_environment':common,'seeds':list(range(16)),'inventory':'Preserved flat1k parity and forced-end-turn stress are not matched exact10k whole-run cap-arm evidence. No qualifying prior comparison found.','decision_rule':'Exploratory paired outcome/diagnostic/resource comparison; no production promotion from N16.','arms':{},'models_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'models/v_win_trees.txt',root/'models/v_rich_trees.txt',root/'models/policy_trees_c.txt']}}
for cap in (32768,131072):
    label=str(cap);result=out/f'{label}.csv';log=out/f'{label}.log';diag=out/f'{label}-decisions.csv';memory=out/f'{label}-time.txt'
    assert not any(p.exists() for p in (result,log,diag,memory))
    options=common|{'STS_SILVER_REUSE_CAP':label,'STS_SILVER_SCALING_DIAG_FILE':str(diag)}
    command=['/usr/bin/time','-v','-o',str(memory),'bash',str(root/'tools/seed_guard.sh'),str(binary),'bestbench','10000','16','0','0',str(result)]
    record={'environment':options,'command':command,'started_unix':time.time()};packet['arms'][label]=record
    (out/'provenance.json').write_text(json.dumps(packet,indent=2)+'\n')
    print('START',label,flush=True)
    with log.open('w') as f: record['exit_code']=subprocess.call(command,env=env|options,stdout=f,stderr=subprocess.STDOUT,cwd=root)
    record['completed_unix']=time.time();(out/'provenance.json').write_text(json.dumps(packet,indent=2)+'\n')
    print('COMPLETE',label,'exit',record['exit_code'],flush=True)
    if record['exit_code']:raise SystemExit(record['exit_code'])
