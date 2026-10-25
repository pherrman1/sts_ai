#!/usr/bin/env python3
"""Read-only TRAIN/public census. Never executes the oracle or reads outcome fields."""
from collections import Counter
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tarfile
from screen_rules import screen

E=Path(__file__).resolve().parent
ROOT=E.parents[3]
BASE=Path('/home/philippherrmann/Documents/sts/sts_lightspeed/build')
AZ='43ad57f0e34e5bc34b7cb21c9fa8f8d5bb3039c1'
MAIN='413e85d69634b51419f3306e286f385f68c3a32c'

def sha(b):return hashlib.sha256(b).hexdigest()
def table(path,symbol):
 s=(ROOT/path).read_text();i=s.index(symbol);return re.findall(r'"([A-Z_0-9]+)"',s[i:s.index('};',i)])
CARDS=table('include/constants/Cards.h','cardEnumStrings')
RELICS=table('include/constants/Relics.h','relicEnumNames')
POWERS=table('include/constants/PlayerStatusEffects.h','playerStatusEnumStrings')
GROUPS={}
EXAMPLES=[]
SOURCES=[]
ROOTS=[]

def group(name,kind):
 if name not in GROUPS:GROUPS[name]={'kind':kind,'states':0,'runs':set(),'known_engine_states':0,'generic_states':0,'known_runs':set(),'generic_runs':set(),'no_shard_states':0,'reason_states':Counter(),'reason_runs':{},'producers':set()}
 return GROUPS[name]

def add(name,kind,run,result,no_shard,identity,public=None,eligible=False):
 g=group(name,kind);g['states']+=1;g['runs'].add(str(run));g['no_shard_states']+=bool(no_shard)
 for field,key,runkey in [('known_engine','known_engine_states','known_runs'),('generic_near_cycle','generic_states','generic_runs')]:
  if result[field]:g[key]+=1;g[runkey].add(str(run))
 for reason in result['reasons']:
  g['reason_states'][reason]+=1;g['reason_runs'].setdefault(reason,set()).add(str(run))
 for reason in result['reasons']:
  old=[x for x in EXAMPLES if x['source']==name and x['example_reason']==reason]
  if len(old)<2 and all(x['run']!=str(run) for x in old):
   EXAMPLES.append({'source':name,'run':str(run),'identity':identity,'example_reason':reason,'no_shard_in_record':no_shard,**result})
 if public is not None:
  ROOTS.append({'source':name,'run':str(run),'identity':identity,'no_shard_proven':no_shard,
               'eligible_public_input':eligible,'enrichment':result,
               'public_sha256':sha(json.dumps(public,sort_keys=True).encode()),'public_wire':public})

def record(name,seed,r,index):
 # Deliberately project only public deck/relic fields; never read z/outcome/actions.
 rec=r.get('record')
 if not rec:return
 deck=rec['obs.deck.cards'];relics=rec['obs.relics.relics']
 if name.startswith('AZ_'):assert rec['obs.fixed_observation'][6]==20
 cards=[CARDS[i] for i in deck if i!=0];owned=[RELICS[i] for i in relics]
 result=screen(cards,owned)
 add(name,'OOC_PUBLIC_RECORD',seed,result,'PRISMATIC_SHARD' not in owned,index)

def heart(name,path):
 index=json.loads((path/'DELIVERY-INDEX.json').read_text())
 if 'workers' in index:
  entries=[(folder,worker['archives']['train.tar.gz']) for folder,worker in index['workers'].items()]
 else:entries=[(d['folder'],d['archives']['train.tar.gz']['sha256']) for d in index['deliveries']]
 SOURCES.append({'source':name,'path':str(path),'index_sha256':sha((path/'DELIVERY-INDEX.json').read_bytes()),'partition':'TRAIN only','archives':len(entries)})
 for n,(folder,expected) in enumerate(sorted(entries)):
  p=path/'deliveries'/folder/'train.tar.gz';assert sha(p.read_bytes())==expected
  with tarfile.open(p,'r|gz') as tar:
   for m in tar:
    if not m.isfile() or not m.name.endswith('.states.jsonl'):continue
    f=tar.extractfile(m);header=json.loads(f.readline());assert header['type']=='header' and header['ascension']==20
    g=group(name,'OOC_PUBLIC_RECORD');g['producers'].add(header['producerSha']);seed=header['seed']
    for line in f:
     r=json.loads(line)
     if r.get('type')=='state' and r.get('supported'):record(name,seed,r,r['index'])
  if (n+1)%8==0:print(name,'TRAIN archives scanned',n+1,flush=True)

def az():
 lines=subprocess.check_output(['git','ls-tree','-r','--long',AZ],cwd=ROOT,text=True).splitlines()
 selected=[]
 for line in lines:
  meta,path=line.split('\t',1)
  if not (path.startswith('gen2/rows/') or path.startswith('gen3/rows_new/')):continue
  match=re.search(r'az-(\d+)\.capture.jsonl.gz$',path)
  if match and int(match[1])%8!=7:selected.append((path,meta.split()[2]))
 SOURCES.append({'source':'AZ_GEN2_GEN3_TRAIN','git_commit':AZ,'partitions':'seed%8!=7; no validation or sealed archives','files':len(selected),'tree_sha256':sha('\n'.join(lines).encode())})
 proc=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
 for n,(path,oid) in enumerate(sorted(selected)):
  proc.stdin.write((oid+'\n').encode());proc.stdin.flush();header=proc.stdout.readline().split();assert header[0].decode()==oid and header[1]==b'blob'
  body=proc.stdout.read(int(header[2]));assert proc.stdout.read(1)==b'\n'
  for i,line in enumerate(gzip.decompress(body).splitlines()):
   r=json.loads(line);assert int(r['seed'])%8!=7
   record('AZ_'+path.split('/')[0].upper(),r['seed'],r,{'file':path,'row':i})
  if (n+1)%1000==0:print('AZ TRAIN files scanned',n+1,flush=True)
 proc.stdin.close();assert proc.wait()==0

def zone(value):
 if isinstance(value,list):return value
 return [c for key in ('knownTop','unknown','knownBottom') for c in value.get(key,[])]

def public(name,path,complete_relics=None,proven=False,fight_override=None):
 op=gzip.open if path.suffix=='.gz' else open
 SOURCES.append({'source':name,'path':str(path),'sha256':sha(path.read_bytes()),'complete_relic_proof':proven})
 seen=set()
 with op(path,'rt') as f:
  for i,line in enumerate(f):
   r=json.loads(line);env=r.get('public_wire',r.get('state'));s=env['state']
   if not s.get('valid',False):continue
   cards=[c for z in ('hand','drawPile','discardPile') for c in zone(s[z]) if c['id']!=0]
   names=[CARDS[c['id']] for c in cards]
   owned=complete_relics
   if owned is None:
    bits=s['player'];owned=[name for j,name in enumerate(RELICS[:128]) if int(bits.get('relicBits'+str(j//64),0)) & (1<<(j%64))]
   powers=[power for j,power in enumerate(POWERS) if int(s['player'].get('statusBits'+str(j//64),0)) & (1<<(j%64))]
   result=screen(names,owned,combat=True,costs=[c['costForTurn'] for c in cards],vulnerable=any(m['curHp']>0 and m.get('vulnerable',0)>0 for m in s['monsters']),powers=powers)
   canonical=json.loads(json.dumps(env));canonical['state']['isolatedSearchSeed']=0;canonical['state']['observedGeneration']=0
   digest=sha(json.dumps(canonical,sort_keys=True).encode())
   if digest in seen:continue
   seen.add(digest)
   run=r.get('seed',r.get('source_seed','unknown'))
   eligible=(proven and s['player']['characterClass']==0 and s['inputState']==1
             and not s['intentsHidden'] and not s['fullDrawOrderObserved'] and not s['drawPile']['fullOrderObserved'])
   identity={'line':i+1,'decision':r.get('decision',r.get('case_id',r.get('root_id',i))),
             'act':r.get('act',s['act']),'floor':r.get('floor',s['floorNum']),
             'fight':fight_override if fight_override is not None else r.get('fight_index',r.get('combat_id','floor:'+str(s['floorNum'])))}
   add(name,'PUBLIC_COMBAT_ROOT',run,result,proven,identity,canonical,eligible)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
 heart('HEART_ROUND2_TRAIN',BASE/'heart-outcome-round2-data-a8f6542e/heart-outcome-round2')
 az()
 heart('HEART_ROUND1_TRAIN',BASE/'heart-outcome-import-20261016-v1/heart-outcome-collection')
 old=E.parent/'combat_infinity_public_20261023'
 spec=importlib.util.spec_from_file_location('audit',old/'inspect_provenance.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
 custody=a.audit(a.ARCHIVE);assert custody==json.loads((old/'provenance-inventory.json').read_text())
 public('A0_CHAMP_PAIRED',Path(custody['checked_artifacts']['public']['path']),custody['full_run_relics'],True,custody['fight'])
 for name,relative in [('NATIVE8_PUBLIC','silver_quiescent_queue_item_20260922/native8-captures.jsonl.gz'),('FORCED_ACTION_PUBLIC','silver_forced_action_target_2026-09-19/roots.jsonl'),('PRIOR_ROOT_PUBLIC','silver_prior_root_replay_20260923/prepared/roots.jsonl')]:
  public(name,E.parent/relative)
 selected=[];per_fight=Counter()
 for root in sorted(ROOTS,key=lambda x:(0 if x['source']=='A0_CHAMP_PAIRED' else 1,x['source'],x['run'],str(x['identity']['fight']),x['identity']['line'],x['public_sha256'])):
  if not root['eligible_public_input'] or not root['enrichment']['reasons']:continue
  fight=(root['source'],root['run'],str(root['identity']['fight']))
  if len(selected)>=32 or per_fight[fight]>=4:continue
  per_fight[fight]+=1;selected.append(root)
 for g in GROUPS.values():
  g['generic_assessable']=g['kind']=='PUBLIC_COMBAT_ROOT'
  g['top_cost_assessable']=g['kind']=='PUBLIC_COMBAT_ROOT'
  for key in ('runs','known_runs','generic_runs','producers'):g[key]=sorted(g[key])
  g['reason_runs']={k:sorted(v) for k,v in g['reason_runs'].items()}
 out={'schema':'infinity_enrichment_census_v1','starting_sha':'7249709a16a19b8cc6d265a5b42c8d93e5a24872','main_readonly_sha':MAIN,'sources':SOURCES,'groups':GROUPS,'ingredient_examples':EXAMPLES,
      'public_roots_screened':len(ROOTS),'provenance_complete_public_roots':sum(r['no_shard_proven'] for r in ROOTS),
      'enriched_public_roots':sum(bool(r['enrichment']['reasons']) for r in ROOTS),
      'selected_roots':[{k:v for k,v in r.items() if k!='public_wire'} for r in selected]}
 outputs={'census.json':json.dumps(out,indent=2)+'\n',
          'public-screen.jsonl':''.join(json.dumps({k:v for k,v in r.items() if k!='public_wire'},sort_keys=True)+'\n' for r in ROOTS),
          'selected-inputs.jsonl':''.join(json.dumps({'public_wire':r['public_wire'],'oracle_no_prismatic_shard':True},sort_keys=True)+'\n' for r in selected)}
 for name,content in outputs.items():
  if args.check:assert (E/name).read_bytes()==content.encode(),name+' differs'
  else:
   assert not (E/name).exists(),'preserve existing census: '+name
   (E/name).write_text(content)
 if args.check:print('PASS census regenerated from TRAIN/public sources; no oracle execution',flush=True)
 print('CENSUS COMPLETE',json.dumps({k:out[k] for k in ('public_roots_screened','provenance_complete_public_roots','enriched_public_roots')}),'selected',len(selected),flush=True)
