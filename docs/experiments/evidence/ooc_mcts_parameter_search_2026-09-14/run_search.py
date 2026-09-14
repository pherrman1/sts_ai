"""Sequential frozen search orchestration; all game invocations use native guard."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
REPO=Path(__file__).resolve().parents[4];sys.path.insert(0,str(REPO))
from tools import ooc_mcts_parameter_search as search
from tools.agent import gcp_benchmark as gcp
PACKET=Path(__file__).resolve().parent
WORK=REPO/'build/ooc-mcts-parameter-search';REMOTE='/home/philippherrmann/sts_sweep'
def command(args):
 r=subprocess.run(args,cwd=REPO,text=True,capture_output=True,check=True)
 return r.stdout

def save(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+'\n')
def snapshot():
 text=command(['python3','tools/agent/gcp_benchmark.py','run','--foreground','--allow-parallel','--','python3','runs/mcts-search-monitor.py'])
 r=json.loads(text.splitlines()[-1])
 with (WORK/'progress.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
 return r

def execute(template,row,phase,start,count):
 m=search.manifest(template,[row],phase,start,count);path=WORK/'manifests'/(phase+'-'+row['id']+'.json');save(path,m)
 arm=m['arms'][0];name=row['id'];folder=WORK/phase;folder.mkdir(exist_ok=True)
 # A completed local arm can be reused only after all manifest-bound checks.
 expected={**m['common_env'],**arm['env']}
 if (folder/(name+'.csv')).exists() and (folder/(name+'-validation.json')).exists() and (folder/(name+'.native-check.txt')).exists():
  score=search.validate(folder,name,start,count,m['frozen_sha'],row['profile'],expected,on=name!='control');print('VERIFIED_EXISTING_ARM',phase,name,flush=True);return score
 receipt=command(['python3',str(PACKET/'launch_arm.py'),str(path),name]);(folder/(name+'.launch.txt')).write_text(receipt)
 while True:
  r=snapshot();state=r['arms'].get(arm['results'],{});print(json.dumps({'phase':phase,'arm':name,'completed':state.get('rows',0),'process':r['process'],'combats':state.get('combats',0),'time':r['time']}),flush=True)
  if r['hostname']!='sts-test' or r['cpus']!=24:raise RuntimeError('wrong actual research host/resources')
  if state.get('bridge_failures'):raise RuntimeError('bridge failures observed; preserve live process/artifacts and report, do not accept or rerun')
  if not r['process']:
   if state.get('rows')!=count:raise RuntimeError('arm stopped without exact completed cohort')
   break
  time.sleep(45)
 for remote,suffix in [(arm['results'],'.csv'),(arm['results']+'.meta.json','.csv.meta.json'),(arm['results']+'.mcts.csv','.csv.mcts.csv'),(arm['results']+'.mcts.csv.support.jsonl','.csv.mcts.csv.support.jsonl'),(arm['log'],'.log')]:
  command(['python3','tools/agent/gcp_benchmark.py','copy-from',remote,str(folder/(name+suffix))])
 save(folder/(name+'.config.json'),{'env':expected,'manifest':str(path)})
 score=search.validate(folder,name,start,count,m['frozen_sha'],row['profile'],expected,on=name!='control')
 # Native checker provides exact per-combat failure-field checks and binary hash.
 argv=['python3','tools/agent/check_benchmark_canary.py','--results',str(folder/(name+'.csv')),'--meta',str(folder/(name+'.csv.meta.json')),'--log',str(folder/(name+'.log')),'--expect-backend','silver','--expect-seeds',str(count),'--expect-sims','10000','--expect-seed-lo',str(start),'--expect-asc','0','--expect-threads','24','--expect-fair','--no-expect-searcher3','--expect-executable-sha',m['frozen_sha'],'--binary',str(WORK/'one_combat'),'--expect-binary-sha256',m['binary']['sha256'],'--expect-silver-reuse-cap-mode','allocated']
 (folder/(name+'.native-check.txt')).write_text(command(argv));save(folder/(name+'-validation.json'),score);print('COMPLETED_VALIDATED',phase,name,json.dumps(score),flush=True)
 return score

def main():
 parser=argparse.ArgumentParser();parser.add_argument('template',type=Path);parser.add_argument('--holdout-only',action='store_true');a=parser.parse_args();template=gcp.load_run_manifest(a.template)
 frozen=json.loads((PACKET/'search-plan.json').read_text());plan=frozen['screen']
 if plan!=search.screen_plan():raise RuntimeError('frozen plan differs from implementation')
 ctrl=dict(id='control',profile=search.profile(),family='control')
 scores=[]
 if not a.holdout_only:
  for row in [ctrl,*plan]:
   execute(template,row,'canary',11999999,1)
   score=execute(template,row,'discovery',12000000,32)
   if row['id']!='control':scores.append(score)
  composition=search.compose(plan,scores);save(WORK/'composition.json',composition)
  evaluated=list(plan)
  for row in composition['arms']:
   if row['reuse']:
    print('COMPOSITION_REUSE',row['id'],row['reuse'],flush=True);continue
   execute(template,row,'canary',11999999,1);score=execute(template,row,'discovery',12000000,32);scores.append(score);evaluated.append(row)
  scores.sort(key=search.rank_key);selected=next(r for r in evaluated if r['id']==scores[0]['id']);save(WORK/'selection.json',{'ranked':scores,'selected':selected,'composition':composition})
  for row in evaluated:
   result=search.analyze(WORK/'discovery/control.csv',WORK/('discovery/'+row['id']+'.csv'),combat_sims=10000,mcts_sims=int(row['profile']['STS_OOC_MCTS_SIMS']),seed_start=12000000,seed_count=32)
   save(WORK/('discovery/'+row['id']+'-analysis.json'),result)
  print('DISCOVERY_COMPLETE_AWAITING_INDEPENDENT_SELECTION_REVIEW',json.dumps(selected),flush=True)
  # A review boundary: selected policy is fixed; final holdout requires separate
  # invocation after independent reproduction of ranking/composition.
  return
 selected=json.loads((WORK/'selection.json').read_text())['selected']
 for row in [ctrl,selected]:
  execute(template,row,'confirmation-canary',12001999,1);execute(template,row,'confirmation',12001000,32)
 result=search.analyze(WORK/'confirmation/control.csv',WORK/('confirmation/'+selected['id']+'.csv'),combat_sims=10000,mcts_sims=int(selected['profile']['STS_OOC_MCTS_SIMS']),seed_start=12001000,seed_count=32)
 save(WORK/'confirmation-result.json',result);print('HOLDOUT_COMPLETE',json.dumps({k:result[k] for k in ['classification','control_wins','treatment_wins','win_difference_pp','win_difference_95_ci_pp']}),flush=True)
if __name__=='__main__':main()
