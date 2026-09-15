#!/usr/bin/env python3
"""Frozen source-grouped Stage 2 native target inventory."""
import argparse
from collections import Counter
import json
from pathlib import Path
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_sparse_events as native


def audit(output):
    if output.exists():raise ValueError('refusing overwrite')
    hashes=e.verify_data();arrays,_=c.base._load_prepared(e.PREPARED)
    tables={k:{s:Counter() for s in ('train','validation','test')} for k in ('writhing','ritual','brew','smoke')}
    problems=[]; examples=[]; records=[]
    for index,row in enumerate(c.base.iter_rows(e.CORPUS)):
        if (row['sourceSeed'],row['fightIdx']) != (int(arrays['sourceSeed'][index]),int(arrays['fightIdx'][index])):raise ValueError('row binding differs')
        pre,post,pi=row['transition']['pre'],row['transition']['post'],row['predictorInput']
        split=('train','validation','test')[int(arrays['split_id'][index])]; win=row['transition']['combatOutcome']==c.base.WIN
        writh=pi['globals']['encounter']==c.base.WRITHING_MASS_ID
        ritual=any(card['cardId']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in pi['cards'])
        brew=c.base._POTION_IDS['ENTROPIC_BREW'] in pre['potions']
        smoke=c.base._POTION_IDS['SMOKE_BOMB'] in pre['potions'] or pre['smokeBombUsed']
        for name,active in (('writhing',writh),('ritual',ritual),('brew',brew),('smoke',smoke)):
            if active:
                t=tables[name][split];t['rows']+=1;t['victories' if win else 'deaths']+=1
        if not win or not (writh or ritual):continue
        rec=dict(index=index,source=row['sourceSeed'],fight=row['fightIdx'],split=split,writhing=writh,ritual=ritual)
        if writh:
            try:
                event=native.writhing_target(pre,post);rec['writhingEvent']=event;tables['writhing'][split]['event:'+str(event)]+=1
            except ValueError as ex:
                problems.append(dict(**rec,mechanism='writhing',error=str(ex)))
        if ritual:
            try:
                changes=native.ritual_changes(pre,post) if not writh else native.ritual_changes(native.writhing_posts(pre)[rec.get('writhingEvent',0)],post)
                rec['ritualChanges']=changes
                t=tables['ritual'][split];t['copies:'+str(len(changes))]+=1
                for card in changes:t['delta:'+str(card['delta'])+':up:'+str(card['upgraded'])]+=1
                if any(card['delta']<0 for card in changes):examples.append(dict(**rec,pre=pre,post=post))
            except ValueError as ex:problems.append(dict(**rec,mechanism='ritual',error=str(ex)))
        records.append(rec)
        if index%50000==0:print('sparse audit',index,flush=True)
    result=dict(schema='sparse_native_audit_v1',baseline=e.snapshot(),hashes=hashes,tables=tables,
                nativeTargetProblems=problems,negativeRitualDeltaExamples=examples,training=False,gameplay=False)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    with output.with_suffix('.rows.jsonl').open('w') as f:
        for rec in records:f.write(json.dumps(rec)+'\n')
    print(json.dumps(dict(tables=tables,nativeTargetProblems=len(problems),negativeRitualDeltas=len(examples))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);audit(p.parse_args().output)
