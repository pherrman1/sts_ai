#!/usr/bin/env python3
"""Offline, pre-oracle root freeze. No Tier requirement; active count then decision."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
from build_runtime import HERE, REPO, RUNTIME, sha
from measure import digest

spec=importlib.util.spec_from_file_location('original_freeze',HERE.parent/'combat_infinity_reconstruction_20261024/freeze_roots.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)

def generate():
    receipt=json.loads((HERE/'capture.json').read_text())
    freeze=json.loads((HERE/'target.json').read_text())
    assert receipt['status']=='COMPLETED' and receipt['first_difference'] is None
    assert freeze['treatment_receipt_sha256']==sha(HERE/'treatment.json')
    run=RUNTIME/'capture'
    assert all(sha(run/name)==receipt['files'][name] for name in ['public.jsonl','trace.jsonl','states.jsonl'])
    trace=[json.loads(line) for line in (run/'trace.jsonl').read_text().splitlines()]
    target=freeze['target'];battle=trace[target['trace_index']]
    assert battle['kind']=='battle' and battle['fight']==target['fight'] and digest(battle['pre'])==target['pre_sha256']
    relics=battle['pre']['relics'];assert 'PRISMATIC_SHARD' not in relics
    cards=original.table('include/constants/Cards.h','cardEnumStrings')
    powers=original.table('include/constants/PlayerStatusEffects.h','playerStatusEnumStrings')
    raw=[json.loads(line) for line in (run/'public.jsonl').read_text().splitlines()]
    summaries=[];eligible=[];seen=set()
    for line,row in enumerate(raw,1):
        # A fixed-floor capture must be unambiguously the frozen first combat.
        assert int(row['seed'])==111101326 and row['act']==target['act'] and row['floor']==target['floor'] and row['encounter']==target['encounter']
        summary={'line_1based':line,'decision':row['decision'],'turn':row['turn'],'capture_valid':row['capture_valid']}
        summaries.append(summary)
        if not row['capture_valid']:summary['capture_error']=row.get('capture_error');continue
        wire=json.loads(json.dumps(row['public_wire']));state=wire['state']
        summary['ordinary_player_decision']=state['inputState']==1
        if state['inputState']!=1:continue
        assert not state['intentsHidden'] and state['player']['characterClass']==0
        assert not state['fullDrawOrderObserved'] and not state['drawPile']['fullOrderObserved']
        active=[c for z in ['hand','drawPile','discardPile'] for c in original.zone(state[z]) if c['id']!=0]
        names=[cards[c['id']] for c in active]
        owned_powers=[name for i,name in enumerate(powers) if int(state['player'].get('statusBits'+str(i//64),0)) & (1<<(i%64))]
        screen=original.screen_module.screen(names,relics,combat=True,costs=[c['costForTurn'] for c in active],powers=owned_powers,vulnerable=any(m['curHp']>0 and m.get('vulnerable',0)>0 for m in state['monsters']))
        state['isolatedSearchSeed']=0;state['observedGeneration']=0
        item={'public_wire':wire,'oracle_no_prismatic_shard':True};key=digest(item)
        summary.update({'screen':screen,'tier1':screen['generic_near_cycle'],'active_cards':dict(sorted(Counter(names).items())),'input_sha256':key,'duplicate_public_root':key in seen})
        if key not in seen:eligible.append((summary,item))
        seen.add(key)
    assert [r['decision'] for r in raw]==sorted(set(r['decision'] for r in raw))
    eligible.sort(key=lambda item:(item[0]['screen']['active_card_count'],item[0]['decision']))
    selected=eligible[:4];assert selected
    binary=REPO/'build/linux-gcc-release-ccache/combat_infinity_oracle'
    assert sha(binary)=='28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9'
    body=''.join(json.dumps(item,sort_keys=True)+'\n' for _,item in selected)
    import hashlib
    result={'rule':'lowest active pool, then earliest decision; no Tier requirement','target':target,'capture_receipt_sha256':sha(HERE/'capture.json'),'capture_sha256':receipt['files']['public.jsonl'],'trace_sha256':receipt['files']['trace.jsonl'],'full_run_relics':relics,'no_prismatic_shard_proven':True,'run_deck_before_fight':battle['pre']['deck'],'public_roots_captured':len(raw),'ordinary_public_roots':sum(r.get('ordinary_player_decision',False) for r in summaries),'tier1_roots':sum(r.get('tier1',False) for r in summaries),'minimum_active':min(r['screen']['active_card_count'] for r in summaries if 'screen' in r),'maximum_active':max(r['screen']['active_card_count'] for r in summaries if 'screen' in r),'historical_minimum_active':30,'selected':[s for s,_ in selected],'all_roots':summaries,'inputs_sha256':hashlib.sha256(body.encode()).hexdigest(),'oracle_binary_sha256':sha(binary),'oracle_K':4,'oracle_caps':{'depth':24,'nodes':2000,'candidates':16,'periods':128,'actions_per_candidate':1024,'total_replay_actions':4096}}
    return {'selection.json':json.dumps(result,indent=2)+'\n','inputs.jsonl':body}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for name,body in generate().items():
        if args.check:assert (HERE/name).read_text()==body,name
        else:
            with (HERE/name).open('x') as f:f.write(body)
    print('PASS fixed first-combat identity, same-run no-Shard, public-only selection and frozen adapter custody; no oracle execution')
