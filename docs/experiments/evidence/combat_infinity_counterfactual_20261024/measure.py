#!/usr/bin/env python3
"""Summarize retained treatment, freeze first engine-complete combat; no simulator."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path
from build_runtime import HERE, REPO, sha, write

CORE={'Corruption':1,'Dark Embrace':1,'Flash of Steel':2}
def engine(state):
    counts=Counter(c.rstrip('+') for c in state['deck'])
    return {c:counts[c] for c in CORE}
def complete(state):
    return all(engine(state)[c]>=n for c,n in CORE.items())
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    receipt=json.loads((HERE/'treatment.json').read_text())
    assert receipt['status']=='COMPLETED'
    raw={name:gzip.decompress((HERE/f'treatment.{name}.gz').read_bytes()) for name in ['trace.jsonl','states.jsonl']}
    assert all(hashlib.sha256(body).hexdigest()==receipt['files'][name] for name,body in raw.items())
    trace=[json.loads(line) for line in raw['trace.jsonl'].splitlines()]
    states=[json.loads(line) for line in raw['states.jsonl'].splitlines()]
    actions=[(i,r) for i,r in enumerate(trace) if r.get('kind') in ['ooc','battle']]
    fired=[];acquisitions=[];offers=[];completion=None;target=None
    for index,row in actions:
        pre,post=row['pre'],row['post']
        if row.get('by')=='infinity_skip':
            fired.append({'trace_index':index,'decision':row['idx'],'act':pre['act'],'floor':pre['floor'],'pre_deck_size':len(pre['deck']),'post_deck_size':len(post['deck']),'hp':post['hp'],'gold':post['gold'],'engine':engine(post),'pre_sha256':digest(pre),'offer':row['offer']})
        for card in CORE:
            before,after=engine(pre)[card],engine(post)[card]
            if after!=before:acquisitions.append({'trace_index':index,'decision':row.get('idx'),'act':post['act'],'floor':post['floor'],'by':row.get('by'),'card':card,'before':before,'after':after,'pre':pre,'offer':row.get('offer'),'post':post})
        groups=row.get('offer',{}).get('cards',[])
        if pre['screen']=='SHOP':
            assert all(len(g)==2 and isinstance(g[0],str) and isinstance(g[1],int) for g in groups)
            offered_cards=[g[0] for g in groups]
        else:
            assert all(isinstance(c,str) for group in groups for c in group)
            offered_cards=[c for group in groups for c in group]
        if any(c.rstrip('+') in CORE for c in offered_cards):
            offers.append({'trace_index':index,'decision':row.get('idx'),'by':row.get('by'),'pre':pre,'offer':row.get('offer'),'post':post})
        if completion is None and complete(post):
            completion={'trace_index':index,'decision':row.get('idx'),'act':post['act'],'floor':post['floor'],'permanent_deck_size':len(post['deck']),'engine':engine(post),'state':post}
        if target is None and completion is not None and index>completion['trace_index'] and row['kind']=='battle':
            target={'seed':111101326,'act':pre['act'],'floor':pre['floor'],'fight':row['fight'],'encounter':row['encounter'],'trace_index':index,'pre_sha256':digest(pre),'permanent_deck_size':len(pre['deck']),'engine':engine(pre),'pre':pre}
    # Full-run counts and final state independent of the target-search prefix.
    final=actions[-1][1]['post'];highest=max(max(r['pre']['floor'],r['post']['floor']) for _,r in actions)
    seen={c:max(engine(s)[c] for _,r in actions for s in [r['pre'],r['post']]) for c in CORE}
    constants=subprocess.check_output(['git','show','d8fd2a105a8d2a481b7639e26c683f75e382e3d4:include/constants/Cards.h'],cwd=REPO,text=True)
    start=constants.index('cardEnumStrings')
    names=re.findall(r'"([A-Z_0-9]+)"',constants[start:constants.index('};',start)])
    ids={card:names.index(card.upper().replace(' ','_')) for card in CORE}
    offer_occurrences={card:[{'state_index':row['index'],'act':row['act'],'floor':row['floor'],'screen':row['screen']} for row in states if row.get('type')=='state' and ids[card] in row.get('record',{}).get('cards_offered.cards',[])] for card in CORE}
    missing=[]
    for entry in receipt['summary'][0]['entries']:
        if entry['status']!='NOT_SEEN':continue
        observed=[row for _,row in actions if row['pre']['act']==entry['act'] and row['pre']['floor']==entry['floor']]
        missing.append({'act':entry['act'],'floor':entry['floor'],'historical_decision_audit':entry['original_ooc_decision'],'historical_card':entry['historical_acquisition'],'observed_screens':sorted({row['pre']['screen'] for row in observed}),'observed_reward_groups':[row['offer']['cards'] for row in observed if row.get('offer',{}).get('cards') and row['pre']['screen']=='REWARDS'],'reason':'floor not reached' if not observed else 'exact frozen reward group never appeared'})
    historical=json.loads(gzip.decompress((HERE.parent/'combat_infinity_reconstruction_20261024/expected-111101326.json.gz').read_bytes()))['trace']
    historical_map=next(row for row in historical if row.get('pre',{}).get('screen')=='MAP')
    actual_map=next(row for _,row in actions if row['pre']['screen']=='MAP')
    route={'historical_decision':historical_map['idx'],'treatment_decision':actual_map['idx'],'historical_post':{k:historical_map['post'][k] for k in ['act','floor','x','y','room']},'treatment_post':{k:actual_map['post'][k] for k in ['act','floor','x','y','room']}}
    last_battle=next(row for _,row in reversed(actions) if row['kind']=='battle')
    result={'seed':111101326,'treatment_receipt_sha256':sha(HERE/'treatment.json'),'frozen_triggers':receipt['summary'][0]['entries'],'actual_skips':receipt['summary'][0]['matched'],'not_seen':receipt['summary'][0]['not_seen'],'post_skip_measurements':fired,'highest_floor':highest,'outcomes':receipt['outcomes'],'final_public_state':final,'maximum_owned_engine':seen,'engine_completion':completion,'first_subsequent_combat':target,'engine_acquisitions':acquisitions,'engine_offers':offers,'historical_control':{'permanent_deck':31,'minimum_active_pool':30,'act':3,'floor':37,'fight':19,'encounter':'THREE_DARKLINGS'},'oracle_executed':False,'engine_public_offer_occurrences':offer_occurrences,'not_seen_diagnostics':missing,'first_map_choice':route,'last_battle':last_battle}
    if args.check:assert json.loads((HERE/'measurements.json').read_text())==result
    else:write(HERE/'measurements.json',result)
    if target:
        frozen={'treatment_receipt_sha256':sha(HERE/'treatment.json'),'selection_rule':'FIRST subsequent combat after naturally owning all four engine cards','target':target}
        path=HERE/'target.json'
        if path.exists():assert json.loads(path.read_text())==frozen
        else:
            assert not args.check, 'missing frozen target'
            write(path,frozen)
    print(json.dumps({k:result[k] for k in ['actual_skips','not_seen','highest_floor','outcomes','maximum_owned_engine','engine_completion','first_subsequent_combat']},indent=2))

if __name__=='__main__':main()
