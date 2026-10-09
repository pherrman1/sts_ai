#!/usr/bin/env python3
"""Read-only complete-canary custody, trace neutrality and rank exposure checks."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import validate_removal_canary as prior

ROOT, E = prior.ROOT, prior.E
RAW = ROOT/'build/overnight_20261008/card_rank_canary'
M = E/'protocols/card_rank_canary.json'
MSHA = 'cc77397f2017986c9807153d0a35e90b5034ce0029838bdc555912fdb08dde4c'
PRIOR_SHA = '986b19e60bb9bf7db9e34a1ea9920af34b39a801e73cba9a554d58e89ee7ad54'
CARDS_SHA = 'bde2800c2f1184b7336b449bf2e1f331fe0739df05f1959478faa4be6b366e5c'
BANNER = '[native OOC card win ranking ON; public8 floor take/skip preserved]'
MARKER = '[card win rank] '
sha, require, js, jl = prior.sha, prior.require, prior.js, prior.jl


def finite(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def first_argmax(values):
    return max(range(len(values)), key=lambda i: values[i]) if values else 5


def validate_scores(path, floor_skip, names):
    output=[]
    for line_number,line in enumerate(path.read_text().splitlines(),1):
        if not line.startswith(MARKER):
            continue
        row=json.loads(line[len(MARKER):]);offers=row['offers'];n=len(offers)
        require(row['seed']==610080001 and row['public_futures']==8,'score source/public futures')
        require(type(row['reward_index']) is int and row['reward_index']>=0,'invalid reward index')
        require(type(row['win_evaluated']) is bool,'win evaluation marker')
        for offer in offers:
            require(set(offer)=={'card_id','upgraded'} and type(offer['card_id']) is int and 0<=offer['card_id']<len(names) and type(offer['upgraded']) is bool,'card semantic identity')
        require(finite(row['floor_base']) and len(row['floor_marginals'])==n and all(map(finite,row['floor_marginals'])),'invalid floor scores')
        floor_pick=first_argmax(row['floor_marginals'])
        if not n or max(row['floor_marginals'])<floor_skip:
            floor_pick=5
        require(row['baseline_pick']==floor_pick,'floor baseline rank/threshold mismatch')
        require(row['baseline_action']==('SKIP' if floor_pick==5 else offers[floor_pick]),'baseline semantic mismatch')
        if floor_pick==5:
            require(row['chosen_pick']==5 and row['chosen_action']=='SKIP' and not row['win_evaluated'] and row['win_base'] is None and row['win_marginals']==[],'floor skip not preserved/extra win evaluation')
        else:
            require(row['win_evaluated'] and finite(row['win_base']) and 0<=row['win_base']<=1,'win head not evaluated/probability')
            require(len(row['win_marginals'])==n and all(map(finite,row['win_marginals'])),'invalid win marginal scores')
            require(all(-1e-12<=row['win_base']+v<=1+1e-12 for v in row['win_marginals']),'post-card win probability bounds')
            chosen=first_argmax(row['win_marginals'])
            require(row['chosen_pick']==chosen and row['chosen_action']==offers[chosen],'win argmax/semantic mismatch')
            require(row['chosen_pick']!=5,'floor take not preserved')
        row['log_locator']=str(path)+':'+str(line_number)
        output.append(row)
    require(output,'missing score/use trace')
    return output


def card_name(action,names):
    return names[action['card_id']]+('+' if action['upgraded'] else '')


def validate():
    require(sha(M)==MSHA and sha(prior.__file__)==PRIOR_SHA,'manifest/prior-validator custody')
    cards=ROOT/'include/constants/Cards.h';require(sha(cards)==CARDS_SHA,'card name mapping custody')
    array=re.search(r'cardNames\[\]\s*=\s*\{(.*?)\};',cards.read_text(),re.S).group(1)
    names=json.loads('['+array.rstrip().rstrip(',')+']')
    m=js(M);require(m['source_sha']=='5add2413281c95a29e32846531d41353c804fd3c' and m['binary_sha256']=='85552690f7455c40e70d08a812dd631254313a287a511b939a06afed8587e907','frozen producer mismatch')
    expected={f'{arm}_{i}':(arm,seed) for i,(arm,seed) in enumerate(m['runs'])}
    require({p.name.removesuffix('.receipt.json') for p in RAW.glob('*.receipt.json')}==set(expected),'missing/extra attempt receipts')
    require(m['runs']==[['Fprod',610080001],['CardWinRank',610080001],['CardWinTrace',610080001]],'fixed roster changed')
    inputs=[{'path':str(p),'sha256':sha(p)} for p in [M,Path(prior.__file__),cards]];records={}
    for stem,(arm,seed) in expected.items():
        record,part=prior.custody(RAW/stem,M,MSHA)
        require(record['arm']==arm and record['seeds']==[seed],'allocation mismatch')
        receipt=js(RAW/(stem+'.receipt.json'));require(receipt['started_epoch']>=m['frozen_epoch'],'launch before freeze')
        env=receipt['environment'];log=(RAW/(stem+'.log')).read_text()
        require((BANNER in log)==(env['STS_OOC_CARD_WIN_RANK']=='1'),'rank enabled/banner mismatch')
        require((MARKER in log)==(env['STS_OOC_CARD_WIN_RANK_TRACE']=='1'),'trace flag/emission mismatch')
        records[stem]=record;inputs+=part
    old=ROOT/'build/overnight_20261008/removal_canary/Fprod_0';old_m=E/'protocols/removal_canary.json'
    old_h='80d32b02f2cabd089b0c0ad638ff425011154b750a91b18698a58daafccf58f7'
    require(sha(old_m)==old_h,'prior reference manifest changed');_,part=prior.custody(old,old_m,old_h);inputs+=part+[{'path':str(old_m),'sha256':old_h}]
    default_parity=prior.parity(old,RAW/'Fprod_0',610080001)
    trace_parity=prior.parity(RAW/'CardWinRank_1',RAW/'CardWinTrace_2',610080001)
    require(records['CardWinRank_1']['public_scorer_calls']==records['CardWinTrace_2']['public_scorer_calls'],'trace changed public model call count')
    score_rows=validate_scores(RAW/'CardWinTrace_2.log',float(m['profiles']['common']['STS_SKIP_THR']),names)
    base=jl(RAW/'Fprod_0.trace.jsonl');candidate=jl(RAW/'CardWinRank_1.trace.jsonl')
    differences=[i for i,(x,y) in enumerate(zip(base,candidate)) if x!=y]
    exposure={'observed':False,'reason':'No changed action at a matched public root observed.'}
    if differences:
        i=differences[0];a,b=base[i],candidate[i]
        require(base[:i]==candidate[:i] and a['pre']==b['pre'] and a['offer']==b['offer'],'first divergence does not share public prefix/root')
        require(a['kind']==b['kind']=='ooc' and a['pre']['screen']=='REWARDS','first divergence is not reward ranking')
        matches=[]
        for row in score_rows:
            pre=a['pre'];groups=a['offer'].get('cards',[]);idx=row['reward_index']
            if (row['act'],row['floor'],row['hp'],row['deck_size']) != (pre['act'],pre['floor'],pre['hp'],len(pre['deck'])) or idx>=len(groups):
                continue
            if [card_name(x,names) for x in row['offers']] != groups[idx]:
                continue
            if row['baseline_pick']==5 or row['chosen_pick']==5:
                continue
            old_added=Counter(a['post']['deck'])-Counter(a['pre']['deck']);new_added=Counter(b['post']['deck'])-Counter(b['pre']['deck'])
            if old_added==Counter({card_name(row['baseline_action'],names):1}) and new_added==Counter({card_name(row['chosen_action'],names):1}):
                matches.append(row)
        require(len(matches)==1,'changed first root cannot uniquely join semantic ranking trace and actual acquisition')
        require(not(Counter(a['pre']['deck'])-Counter(a['post']['deck'])) and not(Counter(b['pre']['deck'])-Counter(b['post']['deck'])),'unexpected removal at acquisition root')
        require({k:v for k,v in a['post'].items() if k!='deck'}=={k:v for k,v in b['post'].items() if k!='deck'},'unexpected immediate non-deck changes')
        exposure={'observed':True,'same_public_root':True,'preceding_complete_trace_rows_equal':i,'trace_idx':a['idx'],'baseline_locator':str(RAW/'Fprod_0.trace.jsonl')+':'+str(i+1),'candidate_locator':str(RAW/'CardWinRank_1.trace.jsonl')+':'+str(i+1),'public_pre':a['pre'],'offer':a['offer'],'baseline_acquired':card_name(matches[0]['baseline_action'],names),'candidate_acquired':card_name(matches[0]['chosen_action'],names),'score_trace':matches[0]}
    else:
        require(base==candidate,'trace-length divergence without matched change')
    analyzer=E/'analyze_wave_card_rank.py';require(sha(analyzer)==m['analyzer_sha256'],'analyzer custody')
    review=E/'strategy/CARD_WIN_RANK_REVIEW.md';require(sha(review)==m['source_review_sha256'],'source review custody')
    inputs += [{'path':str(p),'sha256':sha(p)} for p in [analyzer,review]]
    return {'schema':'card_rank_runtime_canary_validation_v1','status':'RUNTIME_GATE_PASS','manifest_sha256':MSHA,'source_sha':m['source_sha'],'binary_sha256':m['binary_sha256'],'runs':records,'default_off_parity':default_parity,'trace_on_off_parity':trace_parity,'score_invariants':{'rows':len(score_rows),'public_futures':8,'floor_take_rows':sum(x['baseline_pick']!=5 for x in score_rows),'floor_skip_rows':sum(x['baseline_pick']==5 for x in score_rows),'win_head_evaluated_rows':sum(x['win_evaluated'] for x in score_rows),'different_local_rank_rows':sum(x['baseline_pick']!=x['chosen_pick'] for x in score_rows),'all_floor_take_skip_choices_preserved':True,'all_finite_scores_and_first_argmax':True,'win_probability_bounds_pass':True,'scope':'Local floor-versus-win comparisons on candidate reached states. After first changed acquisition, later states are not same-state matches to the baseline run. If skip count is zero, skip-branch execution is not established by this canary.'},'first_same_state_exposure':exposure,'score_rows':score_rows,'quality_inference':False,'inputs':inputs,'validator_sha256':sha(__file__)}


def main():
    out=E/'learning/card_rank_canary_validation.json';require(not out.exists(),'refusing existing report')
    try:result=validate()
    except Exception as error:result={'status':'INVALID_STOP_RUNTIME_GATE','error':repr(error),'validator_sha256':sha(__file__)}
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','first_same_state_exposure','score_rows')},indent=2));print('report_sha256',sha(out))
    return 0 if result['status']=='RUNTIME_GATE_PASS' else 1


if __name__=='__main__':raise SystemExit(main())
