#!/usr/bin/env python3
"""Compare the zero-future receipt with the previously frozen public case."""
import csv
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[5]
E=ROOT/'docs/experiments/evidence/ironclad_a0_overnight_20261008'
P=ROOT/'build/overnight_20261008/targeted_rest_631f/preflight'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read_array(path,name):
    text=path.read_text(); match=re.search(r'\b'+re.escape(name)+r'\[\][^{]*\{(.*?)\};',text,re.S)
    if not match: raise ValueError('cannot read native name table '+name)
    return [json.loads(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',match.group(1))]

def main():
    protocol_path=E/'strategy/targeted_rest_631f/protocol.json'
    protocol=json.loads(protocol_path.read_text())
    assert sha(protocol_path)=='8c703eeaca9bd35d1c69b2cd4bad4096732e0ad6fd86f883dcc42fc83c1ddcf7'
    invocation_path=Path(str(P)+'.receipt.json'); invocation=json.loads(invocation_path.read_text())
    assert invocation['status']=='completed' and invocation['exit_code']==0 and invocation['positive_futures']==0
    assert invocation['command']==protocol['preflight_command'] and invocation['environment']==protocol['environment']
    assert invocation['protocol_sha256']==sha(protocol_path)
    for suffix,record in invocation['outputs'].items():
        path=Path(str(P)+'.'+suffix)
        assert Path(record['path'])==path and path.stat().st_size==record['bytes'] and sha(path)==record['sha256']
    receipt_path=Path(str(P)+'.target.json'); receipt=json.loads(receipt_path.read_text())
    assert receipt['schemaVersion']=='ooc_cf_target_receipt_v1' and receipt['preflightOnly'] is True
    assert receipt['futureCount']==receipt['futureStart']==0
    binding=receipt['binding']; identity=receipt['identity']; state=receipt['publicState']
    assert binding['producerGitSha']==protocol['source_sha'] and binding['producerExecutableSha256']==protocol['binary_sha256']
    assert binding['teacherManifestSha256']==protocol['teacher_sha256'] and binding['sourceSeed']==protocol['source_seed']
    teacher=json.loads(Path(protocol['teacher']).read_text())
    assert binding['combatTeacher']==teacher and binding['policy']==teacher['ooc_policy']
    assert identity['act']==3 and identity['floor']==44 and identity['screen']=='REST'
    manifest=json.loads(Path(str(P)+'.manifest.json').read_text())
    assert manifest['integrity']['selectedStates']==1 and manifest['integrity']['labelRows']==0
    for suffix,digest in manifest['outputs'].items(): assert sha(Path(str(P)+'.'+suffix))==digest
    with Path(str(P)+'.sources.csv').open() as f: sources=list(csv.DictReader(f))
    assert len(sources)==1 and sources[0]['trajectoryValid']=='1' and int(sources[0]['decisionIdx'])==identity['decisionIdx']
    for suffix in ('labels.csv','options.csv','map.csv'):
        with Path(str(P)+'.'+suffix).open() as f: assert not list(csv.DictReader(f))
    packet_path=E/'strategy/fair_rest_610081015_a3f44.public.json'
    packet=json.loads(packet_path.read_text()); expected=packet['publicState']
    assert sha(packet['source']['tracePath'])==packet['source']['traceSha256']
    assert sha(packet['source']['receiptPath'])==packet['source']['receiptSha256']
    names=state['richHeader'].split(','); values=dict(zip(names,state['richValues']))
    assert len(names)==len(state['richValues'])==1017
    hidden=['nextEliteId','nextFight0','nextFight1','nextFight2','remElites','remFights','monOffset','eliteOffset']
    assert all(values[key]==-1 for key in hidden)
    card_file=ROOT/'include/constants/Cards.h'; relic_file=ROOT/'include/constants/Relics.h'; potion_file=ROOT/'include/constants/Potions.h'
    cards=read_array(card_file,'cardNames'); relics=read_array(relic_file,'relicEnumNames'); potions=read_array(potion_file,'potionEnumNames')
    actual={key:int(values[name]) for key,name in {'act':'act','floor':'floor','gold':'gold','hp':'curHp','maxHp':'maxHp','potionCapacity':'potionCapacity','x':'curMapX','y':'curMapY'}.items()}
    actual['deck']=[cards[d['card']['id']]+('+' if d['card']['upgraded'] else '') for d in state['deck']]
    actual['relics']=[relics[r['id']] for r in state['relics']]
    actual['potions']=[potions[p] for p in state['potionSlots'] if potions[p]!='EMPTY_POTION_SLOT']
    actual['screen']=state['screenContents']['screen'].upper()
    matches={key:actual[key]==expected[key] for key in actual}
    assert all(matches.values()),matches
    chosen=identity['chosenKey']; assert chosen=='ooc:v1:effect=17:source=1:none'
    alternatives={}
    for name in ('Offering','Disarm','Immolate'):
        cardid=cards.index(name)
        key=f'ooc:v1:effect=0:source=0:card={cardid}:misc=0:upgraded=0:bottle=-1:occurrence=0'
        assert key in receipt['legalOptionKeys']; alternatives[name]=key
    result={'schema':'overnight_target_preflight_parity_v1','status':'PUBLIC_CASE_PROJECTION_MATCH',
      'source_sha':protocol['source_sha'],'binary_sha256':protocol['binary_sha256'],
      'protocol_sha256':sha(protocol_path),'invocation':str(invocation_path),'invocation_sha256':sha(invocation_path),
      'target_receipt':str(receipt_path),'target_receipt_sha256':sha(receipt_path),
      'public_packet':str(packet_path),'public_packet_sha256':sha(packet_path),'identity':identity,
      'matched_fields':matches,'public_projection':actual,'legal_option_count':len(receipt['legalOptionKeys']),
      'baseline_action':'REST','baseline_semantic_key':chosen,'requested_legal_alternatives':alternatives,
      'source_trajectory_valid':True,'positive_futures':0,'label_rows':0,'wall_seconds':invocation['wall_seconds'],
      'command':invocation['command'],'script_sha256':sha(__file__),
      'name_table_hashes':{str(path):sha(path) for path in (card_file,relic_file,potion_file)},
      'limits':['Packet does not contain rich features, relic counters, bottled flags, path or entire visible map; parity claim covers its comparable projection only.',
       'Room/event are not separate fields in the new receipt. REST screen and exact act/floor/map coordinates identify the targeted campfire.',
       'No continuation outcomes generated. Teacher retains optional Recall defect for this local exact-source diagnostic only.',
       'Positive futures require coordinator target-gate approval.']}
    out=E/'learning/targeted_rest_preflight_631f_parity.json'
    with out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['public_projection','name_table_hashes']},indent=2))

if __name__=='__main__': main()
