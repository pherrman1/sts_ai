import os, subprocess, sys, json
from pathlib import Path
root=Path.cwd()
base={k:v for k,v in os.environ.items() if not k.startswith(('STS_', 'STRATEGIC_', 'OMP_'))}
base.update(STS_FAIR='1',STS_SEARCHER3='0',STS_SILVER_SEARCH='1',STS_SILVER_EXACT_ROOT_BUDGETS='1',STS_SILVER_REUSE_CAP_MODE='allocated',STS_SILVER_ADAPTIVE='0',STS_SILVER_VNET_LEAF_DIRECT='0',STS_SILVER_TELEMETRY='1',STS_NATIVE_OOC='1',STS_OOC_STRATEGIC_TOK_NN='selfplay/models/ooc_strategic_tok_final.native',STS_OOC_STRATEGIC_REST='1',STS_OOC_STRATEGIC_EVENT='1',STS_OOC_STRATEGIC_SHOP='1',STS_OOC_STRATEGIC_TREASURE='1',STS_OOC_STRATEGIC_BOSS_RELIC='1',STS_OOC_STRATEGIC_MARGIN='1.0',STS_STOP_AFTER_ACT='3',STS_COLLECT_KEYS='0',OMP_NUM_THREADS='4')
arm,binary,count,offset=sys.argv[1:]
folder=root/'build/ooc-mcts-expanded-support'
freeze=folder/'freeze.json'
base['STS_EXECUTABLE_GIT_SHA']='916a3d35ff33bd3992de38f1540049838cb55d80' if '/baseline/' in str(Path(binary).resolve()) else json.loads(freeze.read_text())['sha'] if freeze.exists() else '0757c2db918b6395d8f22ca54f6d94c8e3ae0b10'
out=folder/f'{arm}.csv'
if out.exists(): raise RuntimeError(f'refusing to overwrite {out}')
on=arm.endswith('on') or arm=='treatment'
base['STS_OOC_MCTS']='1' if on else '0'
base['STS_OOC_MCTS_TRACE']=str(out)+'.mcts.csv'
if on:
 base.update(STS_OOC_MCTS_SIMS='512',STS_OOC_MCTS_COMBAT_MODEL='/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-native-20260914/combat_transition_v1.native')
cmd=['bash','tools/seed_guard.sh',binary,'bestbench','10000',count,'0',offset,str(out)]
(folder/f'{arm}.config.json').write_text(json.dumps({'env':{k:v for k,v in base.items() if k.startswith(('STS_','OMP_'))},'command':cmd},indent=2)+'\n')
with (folder/f'{arm}.log').open('w') as log:
 subprocess.run(cmd,env=base,stdout=log,stderr=subprocess.STDOUT,check=True)
