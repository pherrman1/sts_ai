#!/usr/bin/env python3
"""Independent checks on retained traces and declared accounting; no gameplay."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

E=Path(__file__).resolve().parent
OLD=E.parent/'combat_infinity_reconstruction_20261024'
ROOT=E.parents[3]
subprocess.run(['python3',str(E/'audit.py'),'--check'],check=True)
rows=json.loads((E/'AUDIT.json').read_text())
assert [r['permanent_deck_size'] for r in rows]==[18,31,19]
assert [r['reward_skip_bound']['deck_size'] for r in rows]==[13,18,14]
assert [r['skip_remove_bound']['deck_size'] for r in rows]==[12,12,11]
assert sum(len(r['target_cards']) for r in rows)==68
for r in rows:
 seed=r['seed'];prefix=json.loads(gzip.decompress((OLD/f'expected-{seed}.json.gz').read_bytes()));trace=prefix['trace']
 A=r['reward_skip_bound'];B=r['skip_remove_bound']
 assert Counter(trace[-1]['pre']['deck'])-Counter(t['card'] for t in A['skips'])==Counter(A['deck'])
 assert Counter(A['deck'])-Counter(x['card'] for x in B['removed'])-Counter(x['card'] for x in B['forgone_shop_cards'])==Counter(B['deck'])
 for t in A['skips']:
  x=trace[t['trace']];delta=Counter(x['post']['deck'])-Counter(x['pre']['deck']);assert sum(delta.values())==1
  assert next(iter(delta)).rstrip('+')==t['card'].rstrip('+')
  assert t['card'].rstrip('+') not in r['engine_core']
 # Price/cash propagation independently uses the actual historical shop exit,
 # not a sum of per-row balances that could double-count one shop inventory.
 carry=0;shop_removals=0
 for step in B['resource_plan']:
  floor=step['floor'];relevant=[x for x in trace if x['kind']=='ooc' and x['pre']['floor']==floor]
  shop=[x for x in relevant if x['pre']['screen']=='SHOP']
  if shop:
   assert step['historical_entry_gold']==shop[0]['pre']['gold']
   assert step['cost']==75+25*shop_removals;shop_removals+=1
   old_spend=shop[0]['pre']['gold']-shop[-1]['post']['gold']
  else:
   cleric=next(x for x in relevant if x['pre']['event']=='The Cleric')
   assert step['historical_entry_gold']==cleric['pre']['gold']
   old_spend=cleric['pre']['gold']-cleric['post']['gold'];assert old_spend==35 and step['cost']==75
  assert step['available_gold']==step['historical_entry_gold']+carry
  new_spend=step['cost']+step.get('other_spend',0)
  carry+=old_spend-new_spend
  assert carry==step['gold_delta_after'] and new_spend<=step['available_gold']
 print(f"PASS {seed}: provenance{len(r['target_cards'])}; independent reward skips{len(A['skips'])}; A{A['deck_size']}; B{B['deck_size']}; final accounted cash delta{carry}; gateA={r['gate_A']} gateB={r['gate_B']}")
core032=[t for t in rows[0]['target_cards'] if t['card']=='Dropkick'];assert len(core032)==2 and all('Pandora' in t['source'] and len(t['parents'])==9 for t in core032)
transformed=next(t for t in rows[0]['target_cards'] if t['source']=='event transform');assert transformed['parent_origins'][0]['card']=='Flame Barrier'
assert len(rows[0]['reward_skip_bound']['dependent_acquisition_not_independently_deleted'])==1
m=json.loads((E/'INTERVENTIONS.json').read_text());assert m['new_runs']==m['new_worlds']==0
assert len(m['interventions'])==13 and {x['original_ooc_decision'] for x in m['interventions']}=={1,4,11,32,40,50,60,68,73,87,93,105,113}
legal=json.loads(gzip.decompress((E/'legal-111101326.json.gz').read_bytes()));by={x['decisionIndex']:x for x in legal}
for x in m['interventions']:
 r=by[x['original_ooc_decision']];assert x['historical_take_key']==r['selectedKey'] and x['forced_skip_key'] in r['legal_keys']
 assert ':effect=12:' in x['forced_skip_key'] and ':group='+x['public_reward_group']+':groupOccurrence=' in x['forced_skip_key']
assert not ({22,90,114,115}&{x['original_ooc_decision'] for x in m['interventions']})
print('PASS frozen13 exact public SKIP keys; protected four engine acquisition groups; transform/Pandora dependency retained')
# Retained combat-only inflation; no new sampling or annotation.
src=Path(json.loads((OLD/'source-build-plan.json').read_text())['source_snapshot']);text=(src/'include/constants/Cards.h').read_text();i=text.index('cardEnumStrings');cards=re.findall(r'"([A-Z_0-9]+)"',text[i:text.index('};',i)])
raw=gzip.decompress((OLD/'capture-111101326.public.jsonl.gz').read_bytes());public=[json.loads(x) for x in raw.splitlines()]
def zone(v):return v if isinstance(v,list) else [c for k in ['knownTop','unknown','knownBottom'] for c in v[k]]
counts=[]
for r in public:
 s=r['public_wire']['state'];all_cards=[c for z in ['hand','drawPile','discardPile','exhaustPile'] for c in zone(s[z]) if c['id']]
 counts.append(Counter(cards[c['id']] for c in all_cards))
assert all(c['WOUND']==2 for c in counts) and counts[0]['ANGER']==3 and max(c['ANGER'] for c in counts)==5
print('PASS Mark of Pain2 temporary Wounds; Anger3->5 combat copies; permanent31 is separately audited')
plan=json.loads((OLD/'source-build-plan.json').read_text())
assert all(hashlib.sha256((src/p).read_bytes()).hexdigest()==h for p,h in plan['tracked_files_sha256'].items())
build=json.loads((OLD/'build-result.json').read_text());assert hashlib.sha256(Path(build['binary_path']).read_bytes()).hexdigest()==m['historical_binary_sha256']==build['expected_sha256']
assert all(hashlib.sha256(Path(model['path']).read_bytes()).hexdigest()==model['expected_sha256'] for model in m['models'])
print('PASS exact historical source/executable/eight model identities unchanged; zero new game/world execution')
