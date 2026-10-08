#!/usr/bin/env python3
"""Read-only custody, default parity and public action-exposure gate for five runs."""
from collections import Counter
import csv, hashlib, json, math, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
E=ROOT/'docs/experiments/evidence/ironclad_a0_overnight_20261008'
RAW=ROOT/'build/overnight_20261008/fullhp_canary'
M=E/'protocols/fullhp_canary.json'
MSHA='0c3ec718578f5f3fb20027bbbdd52e507324f9c0b5eedf46fed3909e56f35653'
SUFFIX={'csv':'.csv','meta':'.csv.meta.json','log':'.log','trace':'.trace.jsonl','tree':'.tree.jsonl','profile':'.profile.jsonl','strategic':'.strategic.jsonl'}
TRACE_ENV={'STS_OOC_DECISION_TRACE':'trace','STS_OOC_STRATEGIC_TRACE':'strategic','STS_RUN_PROFILE':'profile','STS_SILVER_TREE_PROFILE':'tree'}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def js(path):return json.loads(Path(path).read_text())
def rows(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))
def jl(path):
    with Path(path).open() as f:return [json.loads(line) for line in f if line.strip()]
def custody(prefix,manifest_path,manifest_hash):
    manifest=js(manifest_path);receipt_path=Path(str(prefix)+'.receipt.json');r=js(receipt_path)
    require(r['status']=='completed' and r['exit_code']==0,'incomplete/failed '+str(prefix))
    require(r['manifest_sha256']==manifest_hash and Path(r['manifest'])==manifest_path,'manifest binding')
    require(r['source_sha']==manifest['source_sha'] and r['binary_sha256']==manifest['binary_sha256'],'producer binding')
    require(sha(manifest['binary'])==manifest['binary_sha256'],'binary custody')
    for p,h in manifest['artifacts'].items():require(sha(ROOT/p)==h,'artifact custody')
    require(set(r['outputs'])==set(SUFFIX),'output role coverage')
    inputs=[{'path':str(receipt_path),'sha256':sha(receipt_path)}]
    for key,suffix in SUFFIX.items():
        path=Path(str(prefix)+suffix);record=r['outputs'][key]
        require(Path(record['path'])==path and path.stat().st_size==record['bytes'] and sha(path)==record['sha256'],'output custody '+key)
        inputs.append({'path':str(path),'sha256':record['sha256']})
    env=dict(manifest['profiles']['common'],**manifest['profiles']['arms'][r['arm']]);env['STS_EXECUTABLE_GIT_SHA']=manifest['source_sha']
    env.update({key:str(prefix)+SUFFIX[k] for key,k in TRACE_ENV.items()})
    require(r['environment']==env,'undeclared environment')
    data=rows(str(prefix)+'.csv');require(len(data)==1,'one source per canary invocation')
    seed=int(data[0]['seed']);require(seed in manifest['allowed_seeds'],'unreserved source')
    require(r['command']==['bash','tools/seed_guard.sh',manifest['binary'],'bestbench','10000','1','0',str(seed),str(prefix)+'.csv'],'guarded command')
    require(data[0]['won'] in ('0','1') and math.isfinite(float(data[0]['sec'])) and float(data[0]['sec'])>=0,'invalid endpoint/time')
    require(math.isfinite(r['wall_seconds']) and r['wall_seconds']>=0,'invalid process time')
    meta=js(str(prefix)+'.csv.meta.json');c=meta['config']
    require(meta['nSeeds']==1 and meta['seedBlock']=={'lo':seed,'hi':seed} and meta['asc']==0 and meta['sims']==10000 and meta['threads']==1,'effective run allocation')
    require(c['executableGitSha']==manifest['source_sha'] and c['effectiveCombatBackend']=='native_silver' and c['fairPlay'] and not c['collectKeys'],'effective fair/source/backend')
    require(c['nativeOoc'] and not c['silverExactRootBudgets'] and bool(c['silverLearnedStopModel']) and not c['silverAdaptiveEnabled'],'effective budget/native OOC')
    require(c['silverReuseCapMode']=='allocated' and c['silverReuseCap']==32768 and not c['silverLearnedStopBossFallback'] and c['silverLearnedStopBossMax']==0,'effective reuse/boss budget')
    require(meta['models']['floor']=='models/v_rich_trees.txt' and meta['models']['win']=='models/v_win_trees.txt','loaded model paths')
    log=Path(str(prefix)+'.log').read_text()
    for banner in ['[native OOC public encounter mixture: 8 futures]','[benchmark stops after Act 3 boss]','[native OOC optional Ruby Recall excluded when keys off and another action is legal]','learned stop; one-action roots unsearched','[ooc-strat-tok-net] loaded selfplay/models/ooc_strategic_tok_final.native','[CompactTreeNet: 1060 trees, 448 feats from models/v_win_trees.txt]','[CompactTreeNet: 1256 trees, 448 feats from models/v_rich_trees.txt]']:
        require(banner in log,'missing runtime banner '+banner)
    full_banner='[native OOC full-HP REST excluded when Smith is legal and Dream Catcher is absent]'
    require((full_banner in log)==(env.get('STS_OOC_SKIP_FULL_HP_REST','0')=='1'),'full-health flag/banner mismatch')
    require(('[OOC one-ply: shop Q gate ON]' in log)==(env.get('STS_OOC_STRATEGIC_SHOP')=='1'),'shop gate/banner mismatch')
    public=re.findall(r'\[public OOC receipt seed=(\d+) futures=(\d+) scorers=(\d+)\]',log)
    require(len(public)==1 and tuple(map(int,public[0][:2]))==(seed,8) and int(public[0][2])>0,'public scorer source/use')
    tree=jl(str(prefix)+'.tree.jsonl');profile=jl(str(prefix)+'.profile.jsonl');trace=jl(str(prefix)+'.trace.jsonl')
    require(tree and profile and trace,'missing emitted profiles/trace')
    for row in tree:
        require(int(row['seed'])==seed and not row['error'] and not row['adaptive'],'tree error/source/budget')
        require(0<=row['completed_simulations']<=row['configured_simulations'],'tree simulation bounds')
    for row in profile:
        require(int(row['seed'])==seed and not row['error'],'profile error/source')
        for key,value in row.items():
            if key.endswith('_seconds'):require(math.isfinite(value) and value>=0,'profile time '+key)
    require(all(int(row['seed'])==seed for row in trace),'trace source')
    return {'arm':r['arm'],'seed':seed,'receipt_sha256':sha(receipt_path),'public_scorer_calls':int(public[0][2]),'tree_rows':len(tree),'profile_rows':len(profile),'trace_rows':len(trace),'cpu_seconds':sum(x['thread_cpu_seconds'] for x in profile),'wall_seconds':r['wall_seconds']},inputs

def rest_case(stem,act,floor):
    path=RAW/(stem+'.trace.jsonl');trace=jl(path)
    matches=[(i,r) for i,r in enumerate(trace) if r['kind']=='ooc' and r['pre']['screen']=='REST' and r['pre']['act']==act and r['pre']['floor']==floor]
    require(len(matches)==1,'REST target count '+stem);i,row=matches[0];end=row['post'];chain=[]
    for j,nxt in enumerate(trace[i+1:],i+1):
        if nxt['kind']!='ooc' or nxt['pre']['floor']!=floor or nxt['pre']['screen']!='CARD_SELECT':break
        chain.append(j+1);end=nxt['post']
        if end['screen']!='CARD_SELECT':break
    before=Counter(row['pre']['deck']);after=Counter(end['deck']);added=after-before;removed=before-after
    upgrades={name:min(n,added[name+'+']) for name,n in removed.items() if added[name+'+']}
    strat_path=RAW/(stem+'.strategic.jsonl');strategic=rows(strat_path)
    q=[(j+2,s) for j,s in enumerate(strategic) if int(s['act'])==act and int(s['floor'])==floor and s['screen']=='7']
    require(len(q)==1,'strategic REST binding '+stem);line,s=q[0]
    actions=[int(x) for x in s['actionBits'].split('|')];take=int(s['takeIdx']);owned=s['owned']=='1'
    actual=actions[take] if owned and 0<=take<len(actions) else None
    return {'stem':stem,'trace_locator':str(path)+':'+str(i+1),'strategic_locator':str(strat_path)+':'+str(line),'trace_idx':row['idx'],'public_pre':row['pre'],'public_post':row['post'],'selector_lines':chain,'upgrades_observed':upgrades,'strategic_available_action_bits':actions,'strategic_owned':owned,'strategic_chosen_action_bit':actual,'action_evidence':'Owned strategic choice binds action index0=REST,1=SMITH; selector deck deltas bind completed upgrade. If unowned, transition alone is inference.'}

def validate():
    require(sha(M)==MSHA,'frozen manifest changed');manifest=js(M);records={};inputs=[{'path':str(M),'sha256':MSHA}]
    expected={f'{arm}_{i}':(arm,seed) for i,(arm,seed) in enumerate(manifest['runs'])}
    require({p.name.removesuffix('.receipt.json') for p in RAW.glob('*.receipt.json')}==set(expected),'extra/missing invocation receipt')
    for stem,(arm,seed) in expected.items():
        r,part=custody(RAW/stem,M,MSHA);require((r['arm'],r['seed'])==(arm,seed),'run roster mismatch');records[stem]=r;inputs+=part
    old=ROOT/'build/overnight_20261008/corrected_canary/Fprod_0';old_manifest=E/'protocols/corrected_canary.json';old_hash='41e163b3b26602e51fc597032a6c7617a40810c4b311baac71945253387cdb7d'
    require(sha(old_manifest)==old_hash,'old frozen comparator manifest');_,part=custody(old,old_manifest,old_hash);inputs+=part
    new=RAW/'Fprod_0';a=rows(str(old)+'.csv');b=rows(str(new)+'.csv')
    gameplay=lambda values:[{k:v for k,v in r.items() if k!='sec'} for r in values]
    require(gameplay(a)==gameplay(b),'default-off CSV gameplay divergence')
    old_trace=jl(str(old)+'.trace.jsonl');new_trace=jl(str(new)+'.trace.jsonl');require(old_trace==new_trace,'default-off OOC/battle trace divergence')
    excluded={'combat_id','wall_seconds','cpu_seconds','thread_cpu_seconds'}
    norm=lambda values:[{k:v for k,v in r.items() if k not in excluded} for r in values]
    ta=jl(str(old)+'.tree.jsonl');tb=jl(str(new)+'.tree.jsonl');require(norm(ta)==norm(tb),'default-off tree divergence')
    pp=lambda values:[{k:v for k,v in r.items() if not k.endswith('_seconds')} for r in values]
    require(pp(jl(str(old)+'.profile.jsonl'))==pp(jl(str(new)+'.profile.jsonl')),'default-off floor-profile count divergence')
    smoke_old=rest_case('Fprod_0',1,15);smoke_new=rest_case('FullHp_1',1,15)
    require(smoke_old['public_pre']==smoke_new['public_pre'],'smoke interventions not at same public state')
    require(smoke_old['public_pre']['hp']==smoke_old['public_pre']['maxHp'] and 'DREAM_CATCHER' not in smoke_old['public_pre']['relics'],'smoke full health/relic eligibility')
    require(smoke_old['strategic_available_action_bits']==[0,1] and smoke_old['strategic_chosen_action_bit']==0,'baseline actual REST/Smith availability')
    require(smoke_new['strategic_available_action_bits']==[1] and smoke_new['strategic_chosen_action_bit']==1 and smoke_new['upgrades_observed'],'actual filtered Smith upgrade missing')
    named_old=rest_case('Fprod_3',3,44);named_new=rest_case('FullHp_4',3,44)
    packetpath=E/'strategy/fair_rest_610081015_a3f44.public.json';packet=js(packetpath)
    packet_equal=named_old['public_pre']==packet['publicState']
    require(named_old['strategic_chosen_action_bit']==0 and named_new['strategic_chosen_action_bit']==1 and named_new['upgrades_observed'],'namedcase action exposure')
    inputs.append({'path':str(packetpath),'sha256':sha(packetpath)})
    return {'schema':'fullhp_runtime_canary_validation_v1','status':'RUNTIME_GATE_PASS','manifest_sha256':MSHA,'source_sha':manifest['source_sha'],'binary_sha256':manifest['binary_sha256'],'receipts':records,'default_off_parity':{'gameplay_equal':True,'trace_equal':True,'tree_equal_except_declared_fields':True,'floor_profile_counts_equal':True,'gameplay_rows':len(a),'trace_rows':len(old_trace),'tree_rows':len(ta),'excluded_csv_fields':['sec'],'excluded_tree_fields_actually_present':sorted(excluded & set(ta[0])),'excluded_floor_profile_fields':'only keys ending _seconds'},'smoke_exposure':{'baseline':smoke_old,'candidate':smoke_new,'exact_public_prestate_equal':True},'named_case':{'baseline':named_old,'candidate':named_new,'baseline_matches_original_public_packet':packet_equal,'candidate_same_public_prestate':named_old['public_pre']==named_new['public_pre'],'scope':'FullHp changes earlier campfires, so later named-case behavior is runtime exposure, not an isolated same-state causal contrast.'},'quality_inference':False,'inputs':inputs,'validator_sha256':sha(__file__)}

def main():
    out=E/'learning/fullhp_canary_validation.json';require(not out.exists(),'refusing existing report')
    try:result=validate()
    except Exception as error:result={'status':'INVALID_STOP_RUNTIME_GATE','error':repr(error),'validator_sha256':sha(__file__)}
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','smoke_exposure','named_case')},indent=2));print('report_sha256',sha(out))
    return 0 if result['status']=='RUNTIME_GATE_PASS' else 1
if __name__=='__main__':raise SystemExit(main())
