#!/usr/bin/env python3
"""Offline public-only root freeze for the single gate-qualified best mask."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from build_runtime import HERE,REPO,sha
from search_logic import sha_value

spec=importlib.util.spec_from_file_location('original_freeze',HERE.parent/'combat_infinity_reconstruction_20261024/freeze_roots.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)

def load_rows(path):return [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
def generate():
    selected=json.loads((HERE/'SELECTED_MASK.json').read_text());assert selected['all_32_valid'] and selected['gate_pass']
    bits=selected['best_mask'];receipt_path=HERE/'capture'/f'{bits}.receipt.json';receipt=json.loads(receipt_path.read_text())
    search=json.loads((HERE/'results'/f'{bits}.json').read_text())
    assert sha(HERE/'results'/f'{bits}.json')==selected['best_result_sha256']
    assert receipt['status']=='CAPTURED' and receipt['first_difference'] is None
    assert receipt['binary_sha256']==json.loads((HERE/'build-result.json').read_text())['binary_sha256']
    for name in ['public.jsonl','trace.jsonl','states.jsonl']:
        assert hashlib.sha256(gzip.decompress((HERE/'capture'/f'{bits}.{name}.gz').read_bytes())).hexdigest()==receipt['files'][name]
    target=search['measurement']['target'];battle=receipt['capture_battle']
    assert battle['kind']=='battle' and battle['fight']==target['fight'] and sha_value(battle['pre'])==target['pre_sha256']
    assert sha_value(battle['pre'])==sha_value(target['state'])
    relics=battle['pre']['relics'];assert 'PRISMATIC_SHARD' not in relics
    cards=original.table('include/constants/Cards.h','cardEnumStrings');powers=original.table('include/constants/PlayerStatusEffects.h','playerStatusEnumStrings')
    raw=load_rows(HERE/'capture'/f'{bits}.public.jsonl.gz');summaries=[];eligible=[];seen=set()
    for line,row in enumerate(raw,1):
        assert int(row['seed'])==111101032 and row['act']==target['act'] and row['floor']==target['floor'] and row['encounter']==target['encounter']
        summary={'line_1based':line,'decision':row['decision'],'turn':row['turn'],'capture_valid':row['capture_valid']};summaries.append(summary)
        if not row['capture_valid']:summary['capture_error']=row.get('capture_error');continue
        wire=json.loads(json.dumps(row['public_wire']));state=wire['state'];summary['ordinary_player_decision']=state['inputState']==1
        if state['inputState']!=1:continue
        assert not state['intentsHidden'] and state['player']['characterClass']==0
        assert not state['fullDrawOrderObserved'] and not state['drawPile']['fullOrderObserved']
        active=[c for z in ['hand','drawPile','discardPile'] for c in original.zone(state[z]) if c['id']!=0];names=[cards[c['id']] for c in active]
        owned_powers=[name for i,name in enumerate(powers) if int(state['player'].get('statusBits'+str(i//64),0))&(1<<(i%64))]
        screen=original.screen_module.screen(names,relics,combat=True,costs=[c['costForTurn'] for c in active],powers=owned_powers,vulnerable=any(m['curHp']>0 and m.get('vulnerable',0)>0 for m in state['monsters']))
        state['isolatedSearchSeed']=0;state['observedGeneration']=0
        item={'public_wire':wire,'oracle_no_prismatic_shard':True};key=sha_value(item)
        summary.update({'screen':screen,'tier1':screen['generic_near_cycle'],'active_cards':dict(sorted(Counter(names).items())),'input_sha256':key,'duplicate_public_root':key in seen})
        if key not in seen:eligible.append((summary,item))
        seen.add(key)
    assert [r['decision'] for r in raw]==sorted(set(r['decision'] for r in raw))
    eligible.sort(key=lambda item:(item[0]['screen']['active_card_count'],item[0]['decision']));chosen=eligible[:4];assert chosen
    binary=REPO/'build/linux-gcc-release-ccache/combat_infinity_oracle'
    assert sha(binary)=='28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9'
    body=''.join(json.dumps(item,sort_keys=True)+'\n' for _,item in chosen)
    result={'rule':'smallest active pool then earliest decision; no Tier gate','mask':bits,'target':target,'selected_mask_sha256':sha(HERE/'SELECTED_MASK.json'),'capture_receipt_sha256':sha(receipt_path),'capture_sha256':receipt['files']['public.jsonl'],'trace_sha256':receipt['files']['trace.jsonl'],'full_run_relics':relics,'no_prismatic_shard_proven':True,'run_deck_before_fight':battle['pre']['deck'],'public_roots_captured':len(raw),'ordinary_public_roots':sum(r.get('ordinary_player_decision',False) for r in summaries),'tier1_roots':sum(r.get('tier1',False) for r in summaries),'minimum_active':min(r['screen']['active_card_count'] for r in summaries if 'screen' in r),'maximum_active':max(r['screen']['active_card_count'] for r in summaries if 'screen' in r),'active_at_most8_roots':sum(r['screen']['active_card_count']<=8 for r in summaries if 'screen' in r),'historical_minimum_active':16,'selected':[s for s,_ in chosen],'all_roots':summaries,'inputs_sha256':hashlib.sha256(body.encode()).hexdigest(),'oracle_binary_sha256':sha(binary),'oracle_K':4,'oracle_caps':{'depth':24,'nodes':2000,'candidates':16,'periods':128,'actions_per_candidate':1024,'total_replay_actions':4096}}
    return {'selection.json':json.dumps(result,indent=2)+'\n','inputs.jsonl':body}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    for name,body in generate().items():
        if args.check:assert (HERE/name).read_text()==body,name
        else:
            with (HERE/name).open('x') as f:f.write(body)
    print('PASS selected fight identity, receipt-bound no-Shard, public-only root selection and unchanged adapter custody; no oracle execution')
