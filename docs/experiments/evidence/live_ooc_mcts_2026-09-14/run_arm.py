import os, subprocess, sys, json
from pathlib import Path
root=Path.cwd()
base={k:v for k,v in os.environ.items() if not k.startswith(('STS_', 'STRATEGIC_', 'OMP_'))}
base.update(STS_FAIR='1',STS_SEARCHER3='0',STS_SILVER_SEARCH='1',STS_SILVER_EXACT_ROOT_BUDGETS='1',STS_SILVER_REUSE_CAP_MODE='allocated',STS_SILVER_ADAPTIVE='0',STS_SILVER_VNET_LEAF_DIRECT='0',STS_SILVER_TELEMETRY='1',STS_NATIVE_OOC='1',STS_OOC_STRATEGIC_TOK_NN='selfplay/models/ooc_strategic_tok_final.native',STS_OOC_STRATEGIC_REST='1',STS_OOC_STRATEGIC_EVENT='1',STS_OOC_STRATEGIC_SHOP='1',STS_OOC_STRATEGIC_TREASURE='1',STS_OOC_STRATEGIC_BOSS_RELIC='1',STS_OOC_STRATEGIC_MARGIN='1.0',STS_STOP_AFTER_ACT='3',STS_COLLECT_KEYS='0',OMP_NUM_THREADS='4')
arm,binary,count,offset=sys.argv[1:]
freeze=root/'build/ooc-mcts-gate/freeze.json'
if '/baseline/' in str(Path(binary).resolve()):
 base['STS_EXECUTABLE_GIT_SHA']='3057ea79f8a678ba13f9f2ea2b4834850fa2dd87'
elif freeze.exists():
 base['STS_EXECUTABLE_GIT_SHA']=json.loads(freeze.read_text())['sha']
out=root/'build/ooc-mcts-gate'/f'{arm}.csv'
on=arm.endswith('on') or arm=='treatment'
base['STS_OOC_MCTS']='1' if on else '0'
if arm in ('control','treatment'):
 base['STS_OOC_MCTS_TRACE']=str(out)+'.mcts.csv'
if on:
 base.update(STS_OOC_MCTS_SIMS='128',STS_OOC_MCTS_COMBAT_MODEL='/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-native-20260914/combat_transition_v1.native',STS_OOC_MCTS_TRACE=str(out)+'.mcts.csv')
cmd=['bash','tools/seed_guard.sh',binary,'bestbench','1000',count,'0',offset,str(out)]
(out.parent/f'{arm}.config.json').write_text(json.dumps({'env':{k:v for k,v in base.items() if k.startswith(('STS_','OMP_'))},'command':cmd},indent=2))
with (out.parent/f'{arm}.log').open('w') as log:
 subprocess.run(cmd,env=base,stdout=log,stderr=subprocess.STDOUT,check=True)
