#!/usr/bin/env python3
"""Freeze every ordinary root of one completed subsequent combat, no oracle."""
import argparse
import gzip
import json
from pathlib import Path
import re
import subprocess
from stage_a import HERE, REPO, PIN, BINARY_HASH, CAPS, sha, dump, zone, git
from stage_b import SNAPSHOT, custody


def freeze(fight):
    phase=f'capture{fight}'
    receipt_path=HERE/(phase+'.receipt.json')
    receipt=json.loads(receipt_path.read_text())
    assert receipt['prefix_checked'] and receipt['target_fight']==fight
    assert receipt['status'] in ('NEXT_COMBAT_ENTRY','THREE_COMBAT_HORIZON','DEATH','END_OF_ACT_2','DROPKICK_LOSS')
    streams={}
    for name in ('public.jsonl','trace.jsonl','states.jsonl'):
        packed=(HERE/(phase+'.'+name+'.gz')).read_bytes()
        raw=gzip.decompress(packed)
        assert sha(raw)==receipt['files'][name]['sha256'] and sha(packed)==receipt['files'][name]['compressed_sha256']
        assert raw.endswith(b'\n'), 'partial capture cannot be silently accepted'
        streams[name]=[json.loads(v) for v in raw.splitlines()]
    battle=next(r for r in streams['trace.jsonl'] if r.get('kind')=='battle' and r['fight']==fight)
    entry=battle['pre']; assert entry['act']==2 and entry['floor']==receipt['target_floor']
    assert 'PRISMATIC_SHARD' not in entry['relics']
    assert sum(c.rstrip('+')=='Dropkick' for c in entry['deck'])>=2
    header=(SNAPSHOT/'include/constants/Cards.h').read_text()
    def table(symbol):
        start=header.index(symbol)
        return re.findall(r'"([^"]*)"',header[start:header.index('};',start)])
    names=table('cardEnumStrings'); human_names=table('cardNames')
    roots, inputs, excluded=[],[],[]
    for line,row in enumerate(streams['public.jsonl'],1):
        assert int(row['seed'])==111101032 and row['act']==2 and row['floor']==entry['floor'] and row['encounter']==battle['encounter']
        assert row['capture_valid'], row.get('capture_error')
        wire=row['public_wire']; state=wire['state']
        if state['inputState']!=1:
            excluded.append(dict(line=line,decision=row['decision'],inputState=state['inputState'])); continue
        assert not state['intentsHidden'] and not state['fullDrawOrderObserved'] and not state['drawPile']['fullOrderObserved']
        assert state['player']['characterClass']==0
        state['isolatedSearchSeed']=0;state['observedGeneration']=0
        inputs.append(json.dumps(dict(public_wire=wire,oracle_no_prismatic_shard=True),sort_keys=True)+'\n')
        zones={z:[dict(name=names[c['id']],physical_id=c['uniqueId'],upgraded=c['upgraded']) for c in zone(state[z]) if c['id']]
               for z in ('hand','drawPile','discardPile','exhaustPile','limbo')}
        locations={n:{z:[c for c in cs if c['name']==n] for z,cs in zones.items()} for n in ('DROPKICK','BASH','POMMEL_STRIKE')}
        monsters=[m for m in state['monsters'] if m['curHp']>0]
        roots.append(dict(decision=row['decision'],line_1based=line,turn=row['turn'],player_hp=state['player']['curHp'],
                          enemy_hp=[m['curHp'] for m in monsters],enemy_vulnerable=[m['vulnerable'] for m in monsters],
                          active_pool=sum(len(zones[z]) for z in ('hand','drawPile','discardPile')),zones=zones,
                          ingredient_locations=locations,input_sha256=sha(inputs[-1].encode())))
    assert roots and [r['decision'] for r in roots]==sorted(set(r['decision'] for r in roots))
    # Compile a seed-free reader against the retained headers; no simulator build/input change.
    helper=REPO/'build/natural-infinity-20261026/burden'
    command=['g++','-std=c++17','-I'+str(SNAPSHOT/'include'),str(HERE/'burden.cpp'),'-o',str(helper)]
    subprocess.run(command,check=True)
    ids=[]
    for name in entry['deck']:
        base=name.rstrip('+'); matches=[i for i,n in enumerate(human_names) if n==base]
        assert len(matches)==1,(name,matches)
        ids.append((matches[0],int(name.endswith('+'))))
    values=list(map(int,subprocess.check_output([str(helper)],input=''.join(f'{i} {u}\n' for i,u in ids).encode()).splitlines()))
    assert len(values)==len(ids)
    burden=sum(values)+2*('MARK_OF_PAIN' in entry['relics'])
    body=''.join(inputs)
    result=dict(pinned_source=PIN,receipt_sha256=sha(receipt_path.read_bytes()),capture_receipt=receipt,
                runtime_custody=custody(),K=4,caps=CAPS,oracle_binary_sha256=BINARY_HASH,
                rule='every ordinary captured root in capture order, no selection or deduplication',
                roots=roots,excluded_nonordinary=excluded,inputs_sha256=sha(body.encode()),
                combat_entry=entry,combat_exit=battle['post'],permanent_deck_size=len(entry['deck']),cycle_burden=burden,
                burden_cards=[dict(card=n,burden=v) for n,v in zip(entry['deck'],values)],
                burden_helper=dict(command=command,source_sha256=sha((HERE/'burden.cpp').read_bytes()),binary_sha256=sha(helper.read_bytes()),
                                   header_sha256=sha((SNAPSHOT/'include/constants/Cards.h').read_bytes())))
    return {'FREEZE.json':dump(result),'inputs.jsonl':body}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('fight',type=int,choices=[12,13]);p.add_argument('--check',action='store_true');a=p.parse_args()
    folder=HERE/f'combat{a.fight}'
    if not a.check:
        folder.mkdir()
    for name,body in freeze(a.fight).items():
        if a.check:
            assert (folder/name).read_text()==body
        else:
            (folder/name).write_text(body)
    print('PASS exhaustive freeze:',a.fight)
