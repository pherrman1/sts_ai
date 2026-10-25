#!/usr/bin/env python3
"""Seed-free checks of stop/ranking/accounting using retained and constructed data."""
import gzip
import json
from copy import deepcopy
from build_runtime import HERE
from search_logic import engine,locate_stop,control_result,rank,gate

def main():
    prior=HERE.parent/'combat_infinity_reconstruction_20261024'
    historical=json.loads(gzip.decompress((prior/'expected-111101032.json.gz').read_bytes()))
    control=control_result(json.loads((HERE/'manifests/00000.json').read_text()),historical['trace'])
    assert control['engine_complete'] and control['target_alive'] and control['target_deck_size']==18 and control['dropkicks']==2
    assert control['pandora_selected_naturally'] and control['pandora_choice']['dropkicks_produced']==2
    assert control['pandora_choice']['floor']==17 and not gate(control)
    # Make a higher-HP future outcome after the first target. It cannot change rank.
    changed=deepcopy(historical['trace']);changed[-1]['post']['hp']=999
    assert control_result(json.loads((HERE/'manifests/00000.json').read_text()),changed)==control
    state={'deck':['Bash','Pommel Strike+','Dropkick','Dropkick'],'hp':30,'floor':18,'act':2,'screen':'BATTLE'}
    boundary={'kind':'infinity_mask_boundary','pre':state,'index':0,'fight':1,'encounter':'TEST'}
    stop=locate_stop([boundary]);assert stop['kind']=='TARGET_REACHED'
    incomplete=deepcopy(boundary);incomplete['pre']['deck']=['Bash'];incomplete['pre']['floor']=19
    assert locate_stop([incomplete])['kind']=='REGION_PASSED_WITHOUT_ENGINE'
    dead={'kind':'battle','pre':{'deck':['Bash']},'post':{'deck':['Bash'],'hp':0}}
    assert locate_stop([dead])['kind']=='DEAD'
    best=dict(control,target_deck_size=14);assert gate(best)
    rows=[dict(best,numeric_mask=4,enabled_skip_count=1),dict(best,numeric_mask=2,enabled_skip_count=1),dict(best,numeric_mask=3,enabled_skip_count=2)]
    assert sorted(rows,key=rank)[0]['numeric_mask']==2
    assert rank(best)<rank(dict(best,engine_complete=False,target_alive=False,target_deck_size=None,target_hp=None))
    for m in range(32):
        manifest=json.loads((HERE/'manifests'/f'{m:05b}.json').read_text());assert manifest['mask']==m
        assert all(e['enabled']==bool(m&(1<<i)) for i,e in enumerate(manifest['interventions']))
    print('PASS retained18-card/two-Dropkick/Pandora control; no future-outcome ranking; target/horizon/death stops; frozen lexicographic tie-break; all32 masks. No seeds/worlds executed.')
if __name__=='__main__':main()
