#!/usr/bin/env python3
"""Read only completed, named discovery seed610081023; never simulate a game."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EV = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008'
RAW = ROOT / 'build/overnight_20261008'
SEED = 610081023
OUT = Path(__file__).with_name('SHARED_RESCUE_610081023.json')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
objsha = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_seed(path):
    return [(line, row) for line, text in enumerate(path.open(), 1)
            if int((row := json.loads(text))['seed']) == SEED]


def delta(a, b):
    out = {k: [a[k], b[k]] for k in ('hp', 'maxHp', 'gold', 'screen') if a[k] != b[k]}
    for k in ('deck', 'relics', 'potions'):
        if a[k] != b[k]:
            out[k] = {'added': dict(Counter(b[k])-Counter(a[k])),
                      'removed': dict(Counter(a[k])-Counter(b[k]))}
    return out


def compact(path, line, row):
    return {'locator': f'{path}:{line}', 'kind': row['kind'], 'idx': row.get('idx'),
            'act': row['pre']['act'], 'floor': row['pre']['floor'],
            'screen': row['pre']['screen'], 'event': row['pre']['event'],
            'encounter': row.get('encounter'), 'won': row.get('won'),
            'hp_before': row['pre']['hp'], 'hp_after': row['post']['hp'],
            'delta': delta(row['pre'], row['post'])}


def build():
    allruns, inputs = {}, []
    for wave, arm in [('wave3','Fprod'), ('wave3','FullHp'),
                      ('wave4_removal','Fprod'), ('wave4_removal','RemoveLow')]:
        prefix = RAW / wave / f'{arm}_5'
        rp = Path(str(prefix)+'.receipt.json')
        rec = json.loads(rp.read_text())
        assert rec['status']=='completed' and rec['exit_code']==0
        mp = Path(rec['manifest']); manifest = json.loads(mp.read_text())
        assert sha(mp)==rec['manifest_sha256']
        assert rec['source_sha']==manifest['source_sha'] and rec['binary_sha256']==manifest['binary_sha256']
        assert sha(manifest['binary'])==manifest['binary_sha256']
        for file, digest in manifest['artifacts'].items():
            assert sha(ROOT/file)==digest
        for key, output in rec['outputs'].items():
            assert sha(output['path'])==output['sha256'], (wave,arm,key)
            inputs.append({'run':wave+'/'+arm,'kind':key,'path':output['path'],'sha256':output['sha256']})
        inputs.extend([{'run':wave+'/'+arm,'kind':'receipt','path':str(rp),'sha256':sha(rp)},
                       {'run':wave+'/'+arm,'kind':'manifest','path':str(mp),'sha256':sha(mp)}])
        tp=Path(rec['outputs']['trace']['path']); rows=read_seed(tp)
        treep=Path(rec['outputs']['tree']['path']); tree=read_seed(treep)
        stp=Path(rec['outputs']['strategic']['path'])
        st=[(i,{k:v for k,v in x.items() if k not in ('won','finalFloor','finalHp')})
            for i,x in enumerate(csv.DictReader(stp.open()),2) if int(x['seed'])==SEED]
        ep=next(x for x in csv.DictReader(Path(rec['outputs']['csv']['path']).open()) if int(x['seed'])==SEED)
        assert all(not x['error'] and not x['descent_aborts'] for _,x in tree)
        assert all(all(x['endpoints'][k]['count']==0 for k in ('engine_stop','nonterminal','turn_limit')) for _,x in tree)
        assert all(sum(v['count'] for v in x['endpoints'].values())==x['completed_simulations'] for _,x in tree)
        allruns[wave+'/'+arm]={'receipt':rec,'rows':rows,'tree':tree,'strategic':st,
            'trace_path':str(tp),'tree_path':str(treep),'strategic_path':str(stp),'endpoint':ep}
    base=allruns['wave3/Fprod']; base4=allruns['wave4_removal/Fprod']
    norm=lambda t:[{k:v for k,v in x.items() if k!='combat_id'} for _,x in t]
    assert [x for _,x in base['rows']]==[x for _,x in base4['rows']]
    assert norm(base['tree'])==norm(base4['tree'])
    assert [x for _,x in base['strategic']]==[x for _,x in base4['strategic']]
    assert {k:v for k,v in base['endpoint'].items()if k!='sec'}=={k:v for k,v in base4['endpoint'].items()if k!='sec'}
    diagnostic={'STS_OOC_DECISION_TRACE','STS_OOC_STRATEGIC_TRACE','STS_RUN_PROFILE','STS_SILVER_TREE_PROFILE','STS_SILVER_USELESS_TRACE'}
    cases={}
    for wave,arm,flag in [('wave3','FullHp','STS_OOC_SKIP_FULL_HP_REST'),('wave4_removal','RemoveLow','STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT')]:
        a=allruns[wave+'/Fprod'];b=allruns[wave+'/'+arm]
        ea=a['receipt']['environment'];eb=b['receipt']['environment']
        ed={k:[ea.get(k),eb.get(k)]for k in ea.keys()|eb.keys()if k not in diagnostic and ea.get(k)!=eb.get(k)}
        assert ed=={flag:['0','1']}
        n=next(i for i,(x,y)in enumerate(zip(a['rows'],b['rows']))if x[1]!=y[1])
        la,ra=a['rows'][n];lb,rb=b['rows'][n]
        assert ra['pre']==rb['pre'] and ra['offer']==rb['offer']
        assert [k for k in ra if ra[k]!=rb.get(k)]==['post']
        floor=ra['pre']['floor'];beforea=[x for x in a['tree'] if x[1]['floor']<floor];beforeb=[x for x in b['tree'] if x[1]['floor']<floor];assert norm(beforea)==norm(beforeb)
        cases[arm]={'wave':wave,'sole_environment_difference':ed,'identical_trace_prefix_rows':n,
            'identical_trace_prefix_sha256':objsha([x for _,x in a['rows'][:n]]),
            'identical_prior_combat_profile_rows':len(beforea),'profile_exclusion':['combat_id diagnostic counter'],
            'first_difference':{'baseline_locator':f"{a['trace_path']}:{la}",'candidate_locator':f"{b['trace_path']}:{lb}",
                'serialized_public_pre_sha256':objsha(ra['pre']),'baseline':ra,'candidate':rb},
            'target_gate_records':{name:[{'locator':f"{run['strategic_path']}:{i}",'row':x}for i,x in run['strategic'] if int(x['floor']) in (5,6,47,49)]for name,run in [('Fprod',a),(arm,b)]}}
    named={}
    for key in ('wave3/Fprod','wave3/FullHp','wave4_removal/RemoveLow'):
        run=allruns[key]; bi,boss=next((i,x)for i,x in run['rows']if x['kind']=='battle'and x['pre']['floor']==50)
        bossroots=[(i,x)for i,x in run['tree']if x['floor']==50]
        named[key]={'source_sha':run['receipt']['source_sha'],'binary_sha256':run['receipt']['binary_sha256'],
            'endpoint':run['endpoint'],'trace_rows':len(run['rows']),
            'chronology':[compact(run['trace_path'],i,x)for i,x in run['rows']],
            'boss_trace_locator':f"{run['trace_path']}:{bi}",'boss_public_pre':boss['pre'],'boss_public_post':boss['post'],
            'tree_health':{'roots':len(run['tree']),'simulations':sum(x['completed_simulations']for _,x in run['tree']),
                'errors':0,'descent_aborts':0,'nonterminal_engine_stop_turn_limit_endpoints':0},
            'boss_first_root':{'locator':f"{run['tree_path']}:{bossroots[0][0]}",'row':bossroots[0][1]},
            'boss_last_root':{'locator':f"{run['tree_path']}:{bossroots[-1][0]}",'row':bossroots[-1][1]}}
    f=allruns['wave3/FullHp'];bpre=norm([x for x in base['tree']if x[1]['floor']<50]);fpre=norm([x for x in f['tree']if x[1]['floor']<50]);assert bpre==fpre
    ba=named['wave3/Fprod']['boss_public_pre'];fh=named['wave3/FullHp']['boss_public_pre'];assert [k for k in ba if ba[k]!=fh[k]]==['relics'];assert Counter(fh['relics'])-Counter(ba['relics'])==Counter({'TOXIC_EGG':1,'ANCHOR':1})
    return {'schema':'shared_rescue_worked_case_v1','seed':SEED,'selection':'Outcome-informed sole shared rescue from completed adaptive discovery; no causal effect estimate or combination authorization.',
        'script_sha256':sha(__file__),'inputs':inputs,'baseline_reproducibility':{'complete_trace_equal':True,'normalized_tree_equal':True,'strategic_equal':True,'endpoint_equal_except_sec':True},
        'cases':cases,'runs':named,'fullhp_prefinal_combat_profile_rows_equal':len(bpre),
        'fullhp_boss_serialized_state_difference_only':['TOXIC_EGG','ANCHOR'],
        'limits':['Public equality is limited to serialized fields, not full GC/RNG/relic-counter snapshots.',
            'REST bits from strategic trace distinguish REST0, SMITH1, DIG5; REMOVE card identity comes from inventory deltas plus source dispatcher.',
            'Battle summaries do not expose hands/block/card targets; no missing winning line or unique relic effect is reconstructed.',
            'Potion disappearance alone does not prove a chosen legal potion action; endpoint search counts are not actual win-probability estimates.',
            'All numerical reads are restricted to this named completed discovery source; no partial development, GEN2 or holdout was read.'],
        'source_games_run':0}


if __name__=='__main__':
    report=build()
    with OUT.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({'path':str(OUT),'sha256':sha(OUT),'bytes':OUT.stat().st_size,
        'prefixes':{k:v['identical_trace_prefix_rows']for k,v in report['cases'].items()},
        'fullhp_prefinal_equal_roots':report['fullhp_prefinal_combat_profile_rows_equal']}))
