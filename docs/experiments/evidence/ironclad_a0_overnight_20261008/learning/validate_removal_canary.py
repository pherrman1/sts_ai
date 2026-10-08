#!/usr/bin/env python3
"""Read-only custody, default parity and public action-exposure gate for four removal runs."""
from collections import Counter
import csv, hashlib, json, math, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
E=ROOT/'docs/experiments/evidence/ironclad_a0_overnight_20261008'
RAW=ROOT/'build/overnight_20261008/removal_canary'
M=E/'protocols/removal_canary.json'
MSHA='80d32b02f2cabd089b0c0ad638ff425011154b750a91b18698a58daafccf58f7'
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
    data=rows(str(prefix)+'.csv');require(data,'empty invocation')
    seeds=[int(x['seed']) for x in data];seed=min(seeds);require(len(seeds)==len(set(seeds)) and set(seeds)==set(range(seed,seed+len(seeds))),'source block')
    require(set(seeds)<=set(manifest['allowed_seeds']),'unreserved source')
    require(r['command']==['bash','tools/seed_guard.sh',manifest['binary'],'bestbench','10000',str(len(data)),'0',str(seed),str(prefix)+'.csv'],'guarded command')
    require(all(x['won'] in ('0','1') and math.isfinite(float(x['sec'])) and float(x['sec'])>=0 for x in data),'invalid endpoint/time')
    require(math.isfinite(r['wall_seconds']) and r['wall_seconds']>=0,'invalid process time')
    meta=js(str(prefix)+'.csv.meta.json');c=meta['config']
    require(meta['nSeeds']==len(data) and meta['seedBlock']=={'lo':seed,'hi':max(seeds)} and meta['asc']==0 and meta['sims']==10000 and meta['threads']==1,'effective run allocation')
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
    require(len(public)==len(data) and {int(x[0]) for x in public}==set(seeds) and all(int(x[1])==8 and int(x[2])>0 for x in public),'public scorer source/use')
    removal_banner='[native OOC fallback REMOVE ranks low acquisition weight first; Bonfire unchanged]'
    require((removal_banner in log)==(env.get('STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT','0')=='1'),'removal flag/banner mismatch')
    tree=jl(str(prefix)+'.tree.jsonl');profile=jl(str(prefix)+'.profile.jsonl');trace=jl(str(prefix)+'.trace.jsonl')
    require(tree and profile and trace,'missing emitted profiles/trace')
    for row in tree:
        require(int(row['seed']) in seeds and not row['error'] and not row['adaptive'],'tree error/source/budget')
        require(0<=row['completed_simulations']<=row['configured_simulations'],'tree simulation bounds')
    for row in profile:
        require(int(row['seed']) in seeds and not row['error'],'profile error/source')
        for key,value in row.items():
            if key.endswith('_seconds'):require(math.isfinite(value) and value>=0,'profile time '+key)
    require(all(int(row['seed']) in seeds for row in trace),'trace source')
    return {'arm':r['arm'],'seeds':seeds,'receipt_sha256':sha(receipt_path),'public_scorer_calls':sum(int(x[2]) for x in public),'tree_rows':len(tree),'profile_rows':len(profile),'trace_rows':len(trace),'cpu_seconds':sum(x['thread_cpu_seconds'] for x in profile),'wall_seconds':r['wall_seconds']},inputs

def parity(old,new,seed):
    select=lambda values:[r for r in values if int(r['seed'])==seed]
    csv_norm=lambda values:[{k:v for k,v in r.items() if k!='sec'} for r in select(values)]
    require(csv_norm(rows(str(old)+'.csv'))==csv_norm(rows(str(new)+'.csv')),'default-off gameplay divergence')
    a=select(jl(str(old)+'.trace.jsonl'));b=select(jl(str(new)+'.trace.jsonl'))
    require(a==b,'default-off trace divergence')
    excluded={'combat_id','wall_seconds','cpu_seconds','thread_cpu_seconds'}
    norm=lambda values:[{k:v for k,v in r.items() if k not in excluded} for r in select(values)]
    ta=select(jl(str(old)+'.tree.jsonl'));tb=select(jl(str(new)+'.tree.jsonl'))
    require(norm(ta)==norm(tb),'default-off tree divergence')
    profile=lambda values:[{k:v for k,v in r.items() if not k.endswith('_seconds')} for r in select(values)]
    require(profile(jl(str(old)+'.profile.jsonl'))==profile(jl(str(new)+'.profile.jsonl')),'default-off floor profile divergence')
    require(select(rows(str(old)+'.strategic.jsonl'))==select(rows(str(new)+'.strategic.jsonl')),'default-off strategic trace divergence')
    return {'seed':seed,'old_prefix':str(old),'new_prefix':str(new),'gameplay_equal':True,'complete_trace_equal':True,'tree_equal':True,'floor_profile_counts_equal':True,'strategic_trace_equal':True,'trace_rows':len(a),'tree_rows':len(ta),'excluded_csv_fields':['sec'],'excluded_tree_fields_actually_present':sorted(excluded & set(ta[0])),'excluded_profile_fields':'only keys ending _seconds'}

def validate():
    require(sha(M)==MSHA,'frozen manifest changed');manifest=js(M)
    require(manifest['source_sha']=='d35b42b1d5dc9819ec0f157027c68912bb82b8b7' and manifest['binary_sha256']=='1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5','frozen producer')
    inputs=[{'path':str(M),'sha256':MSHA}];records={}
    expected={f'{arm}_{i}':(arm,seed) for i,(arm,seed) in enumerate(manifest['runs'])}
    require({p.name.removesuffix('.receipt.json') for p in RAW.glob('*.receipt.json')}==set(expected),'extra/missing attempted invocation')
    for stem,(arm,seed) in expected.items():
        record,part=custody(RAW/stem,M,MSHA);require(record['arm']==arm and record['seeds']==[seed],'run roster mismatch')
        receipt=js(RAW/(stem+'.receipt.json'));require(receipt['started_epoch']>=manifest['frozen_epoch'],'launch before freeze')
        records[stem]=record;inputs+=part
    parities=[]
    for old,new,seed,m,h in [
        (ROOT/'build/overnight_20261008/fullhp_canary/Fprod_0',RAW/'Fprod_0',610080001,E/'protocols/fullhp_canary.json','0c3ec718578f5f3fb20027bbbdd52e507324f9c0b5eedf46fed3909e56f35653'),
        (ROOT/'build/overnight_20261008/wave2/Fprod_2',RAW/'Fprod_2',610082010,E/'protocols/wave2.json','397247867ef2097865c9dc008ee84de3e1aa4ab9af865012ff520c1e4ff773b3')]:
        require(sha(m)==h,'comparator manifest custody');_,part=custody(old,m,h);inputs+=part+[{'path':str(m),'sha256':h}]
        parities.append(parity(old,new,seed))
    # A smoke with only native-shop REMOVE must be wholly unchanged by the flag.
    smoke=parity(RAW/'Fprod_0',RAW/'RemoveLow_1',610080001)
    a=jl(RAW/'Fprod_2.trace.jsonl');b=jl(RAW/'RemoveLow_3.trace.jsonl')
    different=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y];require(different,'candidate never changed action')
    i=different[0];x,y=a[i],b[i]
    require(a[:i]==b[:i] and x['pre']==y['pre'] and x['offer']==y['offer'],'intervention public prefix/state mismatch')
    require(x['kind']==y['kind']=='ooc' and x['pre']['screen']=='CARD_SELECT' and x['offer']=={'selectType':4,'toSelect':1},'not one-card REMOVE')
    require(x['pre']['act']==1 and x['pre']['floor']==2 and a[i-1]['pre']['event']=='Living Wall' and a[i-1]['post']==x['pre'],'Living Wall source chain mismatch')
    removals=[]
    for row in [x,y]:
        removed=Counter(row['pre']['deck'])-Counter(row['post']['deck']);added=Counter(row['post']['deck'])-Counter(row['pre']['deck'])
        require(sum(removed.values())==1 and not added and row['post']['screen']=='MAP','expected single removal transition')
        removals.append(dict(removed))
    require(removals==[{'Shrug It Off':1},{'Strike':1}],'unexpected actual removal targets')
    require({k:v for k,v in x['post'].items() if k!='deck'}=={k:v for k,v in y['post'].items() if k!='deck'},'immediate non-deck changes')
    static=E/'audit/removal-static-checks.json';require(sha(static)=='6b1cd56edfefd0201188982821b637b7b2e7b59da974a393d288fb56eadace90' and js(static)['status']=='PASS','static gate changed')
    analyzer=E/'analyze_wave_removal.py';require(sha(analyzer)==manifest['analyzer_sha256'],'reviewed analyzer changed')
    inputs += [{'path':str(p),'sha256':sha(p)} for p in [static,analyzer]]
    return {'schema':'removal_runtime_canary_validation_v1','status':'RUNTIME_GATE_PASS','manifest_sha256':MSHA,'source_sha':manifest['source_sha'],'binary_sha256':manifest['binary_sha256'],'runs':records,'default_off_parity':parities,'native_shop_smoke_flag_on_parity':smoke,'same_state_exposure':{'seed':610082010,'act':1,'floor':2,'event':'Living Wall','trace_line':i+1,'trace_idx':x['idx'],'preceding_complete_trace_rows_equal':i,'public_pre_exact':True,'public_pre':x['pre'],'offer':x['offer'],'baseline_removed':removals[0],'candidate_removed':removals[1],'baseline_row':x,'candidate_row':y,'baseline_locator':str(RAW/'Fprod_2.trace.jsonl')+':'+str(i+1),'candidate_locator':str(RAW/'RemoveLow_3.trace.jsonl')+':'+str(i+1)},'quality_inference':False,'scope':'Reused diagnostic sources establish runtime custody, default-off parity and public same-state action exposure only. No population strength claim. Bonfire isolation is covered by frozen static fixtures, not inferred from later diverged trajectories.','inputs':inputs,'validator_sha256':sha(__file__)}

def main():
    out=E/'learning/removal_canary_validation.json';require(not out.exists(),'refusing existing report')
    try:result=validate()
    except Exception as error:result={'status':'INVALID_STOP_RUNTIME_GATE','error':repr(error),'validator_sha256':sha(__file__)}
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','same_state_exposure')},indent=2));print('report_sha256',sha(out))
    return 0 if result['status']=='RUNTIME_GATE_PASS' else 1
if __name__=='__main__':raise SystemExit(main())
