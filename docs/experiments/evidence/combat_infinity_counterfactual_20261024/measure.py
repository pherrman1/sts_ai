#!/usr/bin/env python3
"""Summarize retained treatment, freeze first engine-complete combat; no simulator."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from build_runtime import HERE, RUNTIME, sha, write

CORE={'Corruption':1,'Dark Embrace':1,'Flash of Steel':2}
def engine(state):
    counts=Counter(c.rstrip('+') for c in state['deck'])
    return {c:counts[c] for c in CORE}
def complete(state):
    return all(engine(state)[c]>=n for c,n in CORE.items())
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def main():
    receipt=json.loads((HERE/'treatment.json').read_text())
    assert receipt['status']=='COMPLETED'
    run=RUNTIME/'treatment'
    assert all(sha(run/name)==receipt['files'][name] for name in ['trace.jsonl','states.jsonl'])
    trace=[json.loads(line) for line in (run/'trace.jsonl').read_text().splitlines()]
    states=[json.loads(line) for line in (run/'states.jsonl').read_text().splitlines()]
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
        if any(c.rstrip('+') in CORE for group in groups for c in group):
            offers.append({'trace_index':index,'decision':row.get('idx'),'by':row.get('by'),'pre':pre,'offer':row.get('offer'),'post':post})
        if completion is None and complete(post):
            completion={'trace_index':index,'decision':row.get('idx'),'act':post['act'],'floor':post['floor'],'permanent_deck_size':len(post['deck']),'engine':engine(post),'state':post}
        if target is None and completion is not None and index>completion['trace_index'] and row['kind']=='battle':
            target={'seed':111101326,'act':pre['act'],'floor':pre['floor'],'fight':row['fight'],'encounter':row['encounter'],'trace_index':index,'pre_sha256':digest(pre),'permanent_deck_size':len(pre['deck']),'engine':engine(pre),'pre':pre}
    # Full-run counts and final state independent of the target-search prefix.
    final=actions[-1][1]['post'];highest=max(max(r['pre']['floor'],r['post']['floor']) for _,r in actions)
    seen={c:max(engine(s)[c] for _,r in actions for s in [r['pre'],r['post']]) for c in CORE}
    result={'seed':111101326,'treatment_receipt_sha256':sha(HERE/'treatment.json'),'frozen_triggers':receipt['summary'][0]['entries'],'actual_skips':receipt['summary'][0]['matched'],'not_seen':receipt['summary'][0]['not_seen'],'post_skip_measurements':fired,'highest_floor':highest,'outcomes':receipt['outcomes'],'final_public_state':final,'maximum_owned_engine':seen,'engine_completion':completion,'first_subsequent_combat':target,'engine_acquisitions':acquisitions,'engine_offers':offers,'historical_control':{'permanent_deck':31,'minimum_active_pool':30,'act':3,'floor':37,'fight':19,'encounter':'THREE_DARKLINGS'},'oracle_executed':False}
    write(HERE/'measurements.json',result)
    if target:
        frozen={'treatment_receipt_sha256':sha(HERE/'treatment.json'),'selection_rule':'FIRST subsequent combat after naturally owning all four engine cards','target':target}
        path=HERE/'target.json'
        if path.exists():assert json.loads(path.read_text())==frozen
        else:write(path,frozen)
    print(json.dumps({k:result[k] for k in ['actual_skips','not_seen','highest_floor','outcomes','maximum_owned_engine','engine_completion','first_subsequent_combat']},indent=2))

if __name__=='__main__':main()
