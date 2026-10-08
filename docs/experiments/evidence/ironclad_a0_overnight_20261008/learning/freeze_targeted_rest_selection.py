#!/usr/bin/env python3
"""Validate all 64 selection siblings, then exclusively freeze the chosen action."""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import time
ROOT=Path(__file__).resolve().parents[5]
E=ROOT/'docs/experiments/evidence/ironclad_a0_overnight_20261008'
PREFIX=ROOT/'build/overnight_20261008/targeted_rest_631f/selection'
PROTOCOL_SHA='8c703eeaca9bd35d1c69b2cd4bad4096732e0ad6fd86f883dcc42fc83c1ddcf7'
TARGET_SHA='a7de83029458bd7cf4a4a482c9cdd61751b3bd6814a0b4c550d2a14bccee2072'
BASELINE='ooc:v1:effect=17:source=1:none'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,why):
    if not ok: raise ValueError(why)
def load(suffix): return json.loads(Path(str(PREFIX)+'.'+suffix).read_text())
def table(suffix):
    with Path(str(PREFIX)+'.'+suffix).open() as f: return list(csv.DictReader(f))
def key(row): return (int(row['optionIdx']),int(row['k']))

def validate():
    pp=E/'strategy/targeted_rest_631f/protocol.json'; p=json.loads(pp.read_text())
    require(sha(pp)==PROTOCOL_SHA,'protocol changed')
    require(sha(p['binary'])==p['binary_sha256'] and sha(p['teacher'])==p['teacher_sha256'],'producer/teacher changed')
    teacher=json.loads(Path(p['teacher']).read_text())
    for model in teacher['model_artifacts']: require(sha(ROOT/model['path'])==model['sha256'],'model changed')
    target_path=E/'learning/targeted_rest_631f_selection_target.json'; target=json.loads(target_path.read_text())
    require(sha(target_path)==TARGET_SHA,'bound target changed')
    preflight_path=Path(target['preflightReceiptPath']); preflight=json.loads(preflight_path.read_text())
    require(sha(preflight_path)==target['preflightReceiptSha256'],'preflight changed')
    invocation=load('receipt.json'); inputs=[]
    require(invocation['status']=='completed' and invocation['exit_code']==0,'selection invocation failed/incomplete')
    require(invocation['mode']=='SELECTION' and invocation['positive_futures']==16,'wrong stage/futures')
    require(invocation['protocol_sha256']==PROTOCOL_SHA and invocation['target_sha256']==TARGET_SHA,'invocation binding')
    require(invocation['source_sha']==p['source_sha'] and invocation['binary_sha256']==p['binary_sha256'],'invocation producer')
    require(invocation['environment']==p['environment'],'invocation environment')
    command=list(p['preflight_command']); command[5]=str(PREFIX); command[8]='16'; command[13]=str(target_path)
    require(invocation['command']==command,'invocation command')
    output_keys={'labels.csv','options.csv','sources.csv','map.csv','manifest.json','target.json','log'}
    require(set(invocation['outputs'])==output_keys,'unexpected/missing outputs')
    for suffix,r in invocation['outputs'].items():
        path=Path(str(PREFIX)+'.'+suffix)
        require(Path(r['path'])==path and path.stat().st_size==r['bytes'] and sha(path)==r['sha256'],'output changed: '+suffix)
        inputs.append({'path':str(path),'sha256':r['sha256']})
    manifest=load('manifest.json'); captured=load('target.json')
    require(manifest['schemaVersion']=='ooc_cf_pilot_v2','GEN2 schema')
    require(manifest['producerGitSha']==p['source_sha'] and manifest['producerExecutableSha256']==p['binary_sha256'],'manifest producer')
    require(manifest['teacherManifestSha256']==p['teacher_sha256'] and manifest['combatTeacher']==teacher,'manifest teacher')
    require(manifest['policy']==teacher['ooc_policy'],'manifest policy')
    require(manifest['seedSpec']=={'start':610081015,'count':1,'ascension':0},'source seed spec')
    require(manifest['statesPerSeed']==1 and manifest['selection']['types']==['REST'],'source screen scope')
    require(manifest['futures']['count']==16 and manifest['futures']['start']==0,'selection k range')
    require(manifest['target']['specification']==target and manifest['target']['sha256']==TARGET_SHA,'manifest target')
    integrity=manifest['integrity']
    require(integrity['selectedStates']==1 and integrity['labelRows']==integrity['validLabelRows']==64,'64 valid branches required')
    for k in ('quarantinedSeeds','fatalFailures','simulatorHealthFailures'):
        if k in integrity: require(integrity[k]==0,'nonzero '+k)
    for suffix,digest in manifest['outputs'].items(): require(sha(Path(str(PREFIX)+'.'+suffix))==digest,'producer hash: '+suffix)
    require(captured['preflightOnly'] is False and captured['futureStart']==0 and captured['futureCount']==16,'target stage')
    require(captured['binding']==preflight['binding'] and captured['identity']==preflight['identity'],'source target replay identity')
    require(captured['publicState']==preflight['publicState'],'full public source state parity')
    expected_keys=set(target['optionKeys'])|{BASELINE}
    require(set(captured['retainedOptionKeys'])==expected_keys and len(captured['retainedOptionKeys'])==4,'retained alternatives')
    sources=table('sources.csv'); options=table('options.csv'); labels=table('labels.csv'); maps=table('map.csv')
    require(len(sources)==1 and sources[0]['trajectoryValid']=='1','source trajectory invalid')
    require(int(sources[0]['sourceSeed'])==610081015 and int(sources[0]['decisionIdx'])==93 and sources[0]['type']=='REST','source state identity')
    require(sources[0]['options']=='4' and len(options)==4 and len(labels)==len(maps)==64,'table cardinality')
    option_by_idx={int(r['optionIdx']):r for r in options}
    require(len(option_by_idx)==4 and {r['optionKey'] for r in options}==expected_keys,'option completeness')
    require(sum(int(r['chosen']) for r in options)==1,'baseline retention')
    for r in options: require((r['chosen']=='1')==(r['optionKey']==BASELINE),'actual source choice binding')
    labels_by_key={key(r):r for r in labels}; maps_by_key={key(r):r for r in maps}
    grid={(i,k) for i in option_by_idx for k in range(16)}
    require(len(labels_by_key)==len(maps_by_key)==64 and set(labels_by_key)==set(maps_by_key)==grid,'complete action x selection k x MAP joins')
    wins=Counter(); branch_cpu=0.0; fights=0
    for k,r in labels_by_key.items():
        option=option_by_idx[k[0]]; maprow=maps_by_key[k]
        require(r['valid']=='1' and not r['error'] and r['finalWon'] in ('0','1'),'invalid branch label')
        require(int(r['sourceSeed'])==610081015 and int(r['decisionIdx'])==93 and r['type']=='REST','label source identity')
        require(r['optionKey']==option['optionKey'] and r['chosen']==option['chosen'],'label action identity')
        require(maprow['optionKey']==r['optionKey'] and maprow['chosen']==r['chosen'],'MAP action identity')
        require(maprow['sourceSeed']==r['sourceSeed'] and maprow['decisionIdx']==r['decisionIdx'] and maprow['type']==r['type'],'MAP source identity')
        require(maprow['mapAct']==r['mapAct'] and maprow['mapFloor']==r['mapFloor'],'MAP boundary identity')
        future=int(hashlib.sha256(f'ooc-cf-pilot-v2-future:610081015:93:{k[1]}'.encode()).hexdigest()[:16],16)
        require(int(r['futureSeed'])==future,'coupled future seed mismatch')
        cpu=float(r['cpuSeconds']); require(math.isfinite(cpu) and cpu>=0,'invalid branch CPU')
        branch_cpu+=cpu; fights+=int(r['fights']); wins[r['optionKey']]+=int(r['finalWon'])
    source_cpu=float(sources[0]['sourceCpuSeconds']); require(math.isfinite(source_cpu) and source_cpu>=0,'invalid source CPU')
    selected=min(expected_keys,key=lambda x:(-wins[x],0 if x==BASELINE else 1,x))
    scores=[{'option_key':k,'wins':wins[k],'n':16,'mean_final_won':wins[k]/16} for k in sorted(expected_keys)]
    for path in (pp,target_path,preflight_path,Path(str(PREFIX)+'.receipt.json')): inputs.append({'path':str(path),'sha256':sha(path)})
    return {'status':'SELECTION_INTEGRITY_PASS','source_sha':p['source_sha'],'binary_sha256':p['binary_sha256'],
      'protocol_sha256':PROTOCOL_SHA,'target_sha256':TARGET_SHA,'source_seed':610081015,'decision_idx':93,
      'public_state_sha256':target['publicStateSha256'],'baseline_option_key':BASELINE,'selected_option_key':selected,
      'selection_k':list(range(16)),'selection_scores':scores,'selection_rule':p['selection_rule'],
      'branches':64,'source_trajectory_valid':True,'invalid_branches':0,'map_rows':64,
      'source_cpu_seconds':source_cpu,'branch_cpu_seconds':branch_cpu,'branch_fights':fights,
      'process_wall_seconds':invocation['wall_seconds'],'inputs':inputs,
      'evaluation_started':False,'evaluation_outcomes_opened':False,
      'inference_limit':'Single selected source; selection outcomes are optimistic. Independent evaluation remains unopened. Teacher retains optional Recall defect.'}

def main():
    out=E/'learning/targeted_rest_631f_selection_integrity.json'
    choice=E/'learning/targeted_rest_631f_selection_choice.json'
    require(not out.exists() and not choice.exists(),'refusing previous analysis/selection artifacts')
    try:
        result=validate()
        chosen={k:result[k] for k in ('source_sha','binary_sha256','protocol_sha256','target_sha256','source_seed',
          'decision_idx','public_state_sha256','baseline_option_key','selected_option_key','selection_k','selection_scores','selection_rule','inputs')}
        chosen.update(schema='overnight_targeted_rest_choice_v1',frozen_epoch=time.time(),analysis_script_sha256=sha(__file__),evaluation_outcomes_opened=False)
        # Freeze first. Only a later, separately authorized invocation may inspect evaluation k.
        with choice.open('x') as f: json.dump(chosen,f,indent=2); f.write('\n')
        result.update(choice_path=str(choice),choice_sha256=sha(choice),choice_frozen_epoch=chosen['frozen_epoch'])
    except Exception as error:
        result={'status':'INVALID_STOP_LANE','error':repr(error),'evaluation_started':False,'choice_frozen':False}
    result['analysis_script_sha256']=sha(__file__)
    with out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='inputs'},indent=2))
    return 0 if result['status']=='SELECTION_INTEGRITY_PASS' else 1

if __name__=='__main__': raise SystemExit(main())
