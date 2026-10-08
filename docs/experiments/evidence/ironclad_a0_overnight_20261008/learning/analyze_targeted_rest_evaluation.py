#!/usr/bin/env python3
"""Fixed Offering-vs-REST independent future evaluation at one captured decision."""
from collections import Counter
import csv,hashlib,json,math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from paired_analysis import bootstrap_ci
E=ROOT/'docs/experiments/evidence/ironclad_a0_overnight_20261008'
PREFIX=ROOT/'build/overnight_20261008/targeted_rest_631f/evaluation'
PROTOCOL_SHA='8c703eeaca9bd35d1c69b2cd4bad4096732e0ad6fd86f883dcc42fc83c1ddcf7'
TARGET_SHA='9c97ebca79bf6f6fba111f7ecebcb8f3365df16bf4256294a3c9a186da9044c3'
CHOICE_SHA='c4f8f74597ca5c9b423a4ae40920ab76ca70cf2559965916bd0784712ee000a8'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,why):
    if not ok: raise ValueError(why)
def load(suffix): return json.loads(Path(str(PREFIX)+'.'+suffix).read_text())
def table(suffix):
    with Path(str(PREFIX)+'.'+suffix).open() as f: return list(csv.DictReader(f))
def key(row): return (int(row['optionIdx']),int(row['k']))

def analyze():
    pp=E/'strategy/targeted_rest_631f/protocol.json'; p=json.loads(pp.read_text())
    require(sha(pp)==PROTOCOL_SHA,'protocol changed')
    require(sha(p['binary'])==p['binary_sha256'] and sha(p['teacher'])==p['teacher_sha256'],'producer/teacher changed')
    teacher=json.loads(Path(p['teacher']).read_text())
    for model in teacher['model_artifacts']: require(sha(ROOT/model['path'])==model['sha256'],'model changed')
    choicepath=E/'learning/targeted_rest_631f_selection_choice.json'; choice=json.loads(choicepath.read_text())
    require(sha(choicepath)==CHOICE_SHA,'frozen choice changed')
    require(choice['protocol_sha256']==PROTOCOL_SHA and choice['source_sha']==p['source_sha'] and choice['binary_sha256']==p['binary_sha256'],'choice producer/protocol')
    require(choice['selection_k']==list(range(16)) and choice['evaluation_outcomes_opened'] is False,'choice was not frozen before evaluation')
    for artifact in choice['inputs']: require(sha(artifact['path'])==artifact['sha256'],'frozen selection input changed')
    selected=choice['selected_option_key']; baseline=choice['baseline_option_key']; expected_keys={selected,baseline}
    require(len(expected_keys)==2 and 'card=234:' in selected and baseline=='ooc:v1:effect=17:source=1:none','frozen contrast changed')
    targetpath=E/'learning/targeted_rest_631f_evaluation_target.json'; target=json.loads(targetpath.read_text())
    require(sha(targetpath)==TARGET_SHA and target['optionKeys']==[selected],'evaluation target changed')
    require(target['decisionIdx']==93 and target['sourceSeed']==610081015 and target['publicStateSha256']==choice['public_state_sha256'],'target identity')
    preflightpath=Path(target['preflightReceiptPath']); preflight=json.loads(preflightpath.read_text())
    require(sha(preflightpath)==target['preflightReceiptSha256'],'preflight changed')
    invocation=load('receipt.json'); inputs=[]
    require(invocation['status']=='completed' and invocation['exit_code']==0,'evaluation invocation failed/incomplete')
    require(invocation['mode']=='EVALUATION' and invocation['positive_futures']==32,'wrong stage/futures')
    require(invocation['protocol_sha256']==PROTOCOL_SHA and invocation['target_sha256']==TARGET_SHA,'invocation binding')
    require(invocation['source_sha']==p['source_sha'] and invocation['binary_sha256']==p['binary_sha256'],'invocation producer')
    require(invocation['environment']==p['environment'],'invocation environment')
    require(invocation['target_binding']['frozen_choice']['sha256']==CHOICE_SHA and invocation['started_epoch']>choice['frozen_epoch'],'evaluation not after frozen selection')
    require(invocation['target_binding']['future_k']==list(range(16,48)),'invocation future block')
    command=list(p['preflight_command']); command[5]=str(PREFIX); command[8]='32'; command[13]=str(targetpath); command[14]='16'
    require(invocation['command']==command,'invocation command')
    outputkeys={'labels.csv','options.csv','sources.csv','map.csv','manifest.json','target.json','log'}
    require(set(invocation['outputs'])==outputkeys,'unexpected/missing outputs')
    for suffix,r in invocation['outputs'].items():
        path=Path(str(PREFIX)+'.'+suffix)
        require(Path(r['path'])==path and path.stat().st_size==r['bytes'] and sha(path)==r['sha256'],'output changed: '+suffix)
        inputs.append({'path':str(path),'sha256':r['sha256']})
    manifest=load('manifest.json'); captured=load('target.json'); integrity=manifest['integrity']
    require(manifest['schemaVersion']=='ooc_cf_pilot_v2','GEN2 schema')
    require(manifest['producerGitSha']==p['source_sha'] and manifest['producerExecutableSha256']==p['binary_sha256'],'manifest producer')
    require(manifest['teacherManifestSha256']==p['teacher_sha256'] and manifest['combatTeacher']==teacher and manifest['policy']==teacher['ooc_policy'],'manifest teacher/policy')
    require(manifest['seedSpec']=={'start':610081015,'count':1,'ascension':0},'source seed spec')
    require(manifest['statesPerSeed']==1 and manifest['selection']['types']==['REST'],'source scope')
    require(manifest['futures']['count']==32 and manifest['futures']['start']==16,'evaluation k range')
    require(manifest['target']['specification']==target and manifest['target']['sha256']==TARGET_SHA,'manifest target')
    require(integrity['selectedStates']==1 and integrity['labelRows']==integrity['validLabelRows']==64,'64 valid branches required')
    for k in ('quarantinedSeeds','fatalFailures','simulatorHealthFailures'):
        if k in integrity: require(integrity[k]==0,'nonzero '+k)
    for suffix,digest in manifest['outputs'].items(): require(sha(Path(str(PREFIX)+'.'+suffix))==digest,'producer hash: '+suffix)
    require(captured['preflightOnly'] is False and captured['futureStart']==16 and captured['futureCount']==32,'target stage')
    require(captured['binding']==preflight['binding'] and captured['identity']==preflight['identity'] and captured['publicState']==preflight['publicState'],'exact source target replay parity')
    require(set(captured['retainedOptionKeys'])==expected_keys and len(captured['retainedOptionKeys'])==2,'retained contrast')
    sources=table('sources.csv'); options=table('options.csv'); labels=table('labels.csv'); maps=table('map.csv')
    require(len(sources)==1 and sources[0]['trajectoryValid']=='1','source trajectory invalid')
    require(int(sources[0]['sourceSeed'])==610081015 and int(sources[0]['decisionIdx'])==93 and sources[0]['type']=='REST','source identity')
    require(sources[0]['options']=='2' and len(options)==2 and len(labels)==len(maps)==64,'table cardinality')
    option_by_idx={int(r['optionIdx']):r for r in options}
    require(len(option_by_idx)==2 and {r['optionKey'] for r in options}==expected_keys,'option completeness')
    require(sum(int(r['chosen']) for r in options)==1,'baseline retention')
    for r in options: require((r['chosen']=='1')==(r['optionKey']==baseline),'actual source choice binding')
    labels_by_key={key(r):r for r in labels}; maps_by_key={key(r):r for r in maps}; grid={(i,k) for i in option_by_idx for k in range(16,48)}
    require(len(labels_by_key)==len(maps_by_key)==64 and set(labels_by_key)==set(maps_by_key)==grid,'complete action x evaluation k x MAP joins')
    outcomes={option:set() for option in expected_keys}; wins=Counter(); branch_cpu=0.0; fights=0
    for k,r in labels_by_key.items():
        option=option_by_idx[k[0]]; mr=maps_by_key[k]
        require(r['valid']=='1' and not r['error'] and r['finalWon'] in ('0','1'),'invalid branch label')
        require(int(r['sourceSeed'])==610081015 and int(r['decisionIdx'])==93 and r['type']=='REST','label source identity')
        require(r['optionKey']==option['optionKey'] and r['chosen']==option['chosen'],'label action identity')
        require(all(mr[field]==r[field] for field in ('sourceSeed','decisionIdx','type','optionKey','chosen','mapAct','mapFloor')),'MAP identity/boundary')
        future=int(hashlib.sha256(f'ooc-cf-pilot-v2-future:610081015:93:{k[1]}'.encode()).hexdigest()[:16],16)
        require(int(r['futureSeed'])==future,'coupled future seed mismatch')
        cpu=float(r['cpuSeconds']); require(math.isfinite(cpu) and cpu>=0,'invalid branch CPU')
        branch_cpu+=cpu; fights+=int(r['fights']); wins[r['optionKey']]+=int(r['finalWon'])
        if r['finalWon']=='1': outcomes[r['optionKey']].add(k[1])
    delta=np.array([int(k in outcomes[selected])-int(k in outcomes[baseline]) for k in range(16,48)])
    mean,low,high=bootstrap_ci(delta,n_boot=10000,ci=.95,rng=np.random.default_rng(20261008))
    source_cpu=float(sources[0]['sourceCpuSeconds']); require(math.isfinite(source_cpu) and source_cpu>=0,'invalid source CPU')
    wall=invocation['wall_seconds']; require(math.isfinite(wall) and wall>=0,'invalid wall time')
    for path in (pp,targetpath,preflightpath,choicepath,Path(str(PREFIX)+'.receipt.json')): inputs.append({'path':str(path),'sha256':sha(path)})
    return {'schema':'overnight_targeted_rest_evaluation_v1','status':'EVALUATION_INTEGRITY_PASS',
      'source_sha':p['source_sha'],'binary_sha256':p['binary_sha256'],'protocol_sha256':PROTOCOL_SHA,'choice_sha256':CHOICE_SHA,
      'source_seed':610081015,'decision_idx':93,'public_state_sha256':choice['public_state_sha256'],
      'selected_action':'Upgrade Offering','baseline_action':'REST','selected_option_key':selected,'baseline_option_key':baseline,
      'evaluation_k':list(range(16,48)),'conditional_future_pairs':32,'independent_source_decisions':1,
      'selected_wins':wins[selected],'baseline_wins':wins[baseline],'paired_gain':mean,'paired_bootstrap_ci95':[low,high],
      'selected_only':int((delta>0).sum()),'baseline_only':int((delta<0).sum()),
      'both_win':len(outcomes[selected]&outcomes[baseline]),'both_lose':32-len(outcomes[selected]|outcomes[baseline]),
      'bootstrap_replicates':10000,'bootstrap_seed':20261008,
      'classification':'LOCAL_CONDITIONAL_POSITIVE_SIGNAL' if low>0 else 'LOCAL_CONDITIONAL_NEGATIVE_SIGNAL' if high<0 else 'LOCAL_CONDITIONAL_INCONCLUSIVE',
      'branches':64,'map_rows':64,'invalid_branches':0,'source_trajectory_valid':True,'source_cpu_seconds':source_cpu,
      'branch_cpu_seconds':branch_cpu,'branch_fights':fights,'process_wall_seconds':wall,'inputs':inputs,
      'limits':['One selected source decision under fixed public-conditioning sampler and old631f teacher; not32 independent full runs.',
       'Confidence interval resamples32 paired future draws conditional on this source; it does not include source-selection or teacher-distribution uncertainty.',
       'Optional Ruby Recall defect remains in this diagnostic teacher. No corrected-reference qualification, policy promotion, or training claim.',
       'Frozen selection used k0..15. Only k16..47 contribute to this evaluation; no reselection or sample extension.']}

def main():
    out=E/'learning/targeted_rest_631f_evaluation_result.json'
    require(not out.exists(),'refusing previous evaluation artifact')
    try: result=analyze()
    except Exception as error: result={'status':'INVALID_STOP_LANE','error':repr(error)}
    result['analysis_script_sha256']=sha(__file__)
    with out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='inputs'},indent=2))
    return 0 if result['status']=='EVALUATION_INTEGRITY_PASS' else 1

if __name__=='__main__': raise SystemExit(main())
