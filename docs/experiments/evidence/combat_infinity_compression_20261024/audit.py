#!/usr/bin/env python3
"""Offline public provenance/accounting only; never launches the simulator."""
import argparse
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher
import gzip
import hashlib
import json
from pathlib import Path
import re

E=Path(__file__).resolve().parent
OLD=E.parent/'combat_infinity_reconstruction_20261024'
ROOT=E.parents[3]
SOURCE=ROOT/'build/infinity-heart-runtime-20261024/source'
SEEDS=[111101032,111101326,111101512]
CORE={111101032:{'Dropkick','Bash','Pommel Strike'},111101326:{'Flash of Steel','Corruption','Dark Embrace'},111101512:{'Pommel Strike','Shrug It Off'}}

def sha(b):return hashlib.sha256(b).hexdigest()
def base(c):return c.rstrip('+')
def table(path,symbol):
 s=(SOURCE/path).read_text();i=s.index(symbol);return re.findall(r'"([A-Z_0-9]+)"',s[i:s.index('};',i)])
CARDS=table('include/constants/Cards.h','cardEnumStrings')
RELICS=table('include/constants/Relics.h','relicEnumNames')

def describe(key):
 effect=int(re.search(r':effect=(\d+)',key)[1]); cost=re.search(r':(?:cost|price)=(\d+)',key)
 result={'key':key,'effect':effect,'gold_cost':int(cost[1]) if cost else 0,'same_map_path_structurally':True,'adds':[],'removes':[],'engine_threat':False}
 card=re.search(r':card=(\d+)',key) or re.search(r'(?:reward|shop)=card,(\d+)',key)
 name=CARDS[int(card[1])] if card else None
 if effect in [0,1,2,3,4]:
  result['label']={0:'upgrade',1:'remove',2:'transform',3:'transform+upgrade',4:'duplicate'}[effect]+' '+str(name)
  result['removes']=[name] if effect in [1,2,3] else []
  result['adds']=['unobserved transformed card'] if effect in [2,3] else [name] if effect==4 else []
 elif effect in [5,22]:result['label']=('pick ' if effect==5 else 'buy ')+str(name);result['adds']=[name]
 elif effect==12:result['label']='SKIP this card-reward group'
 elif effect in [23,27]:
  relic=re.search(r'(?:relic=|shop=relic,)(\d+)',key);result['label']=('buy ' if effect==23 else 'take boss relic ')+RELICS[int(relic[1])]
  result['deck_effect']='see source-backed coupled-choice table; unobserved random products not invented'
 elif effect==24:result['label']='buy potion (no permanent card change)'
 elif effect==25:result['label']='leave shop'
 elif effect==28:result['label']='SKIP boss relic'
 elif effect==26:
  event=re.search(r':event=(\d+):option=(\d+)',key);result['label']=f"event {event[1]} option {event[2]}";result['deck_effect']='public event option; details in opportunity notes'
 else:result['label']='semantic effect '+str(effect)
 return result

def generate():
 sources=json.loads((E/'sources.json').read_text());results=[];provenance_lines=['# Complete target-card provenance','', 'Every target slot is listed. Duplicate names are ordered trace slots, not claimed persistent physical UIDs.','', '| Run | Target slot | Card | Origin | Floor / trace / OOC decision | Upgrade history | Engine |','|---|---:|---|---|---|---|---|']
 opportunities_lines=['# Historical-route OOC compression opportunities','','All siblings in opportunities.json are receipt-bound legal semantic keys, without Q/outcome data. Shop rows are repeated observations of one inventory, not independent removals. At most one removal per shop; later removal prices rise by25. Normal map alternatives are excluded. Card upgrade decisions are retained only as provenance, not counted as removals.','','| Run | Trace / decision / floor | Screen / event | Historical action | SKIP? | Gold | Legal siblings / composition effect |','|---|---|---|---|---|---:|---|']
 all_opportunities=[]
 for seed in SEEDS:
  prefix=json.loads(gzip.decompress((OLD/f'expected-{seed}.json.gz').read_bytes()))
  legal_bytes=(E/f'legal-{seed}.json.gz').read_bytes();source=next(x for x in sources['sources'] if x['seed']==seed);assert sha(legal_bytes)==source['legal_extract_sha256']
  replay=json.loads((OLD/f'replay-{seed}.json').read_text());assert sha((OLD/f'replay-{seed}.json').read_bytes())==source['executed_receipt_sha256'];assert replay['files']['roots.jsonl']==source['raw_roots_sha256']
  assert sha((OLD/replay['frozen_prefix']['expected_file']).read_bytes())==replay['frozen_prefix']['expected_sha256']
  legal=json.loads(gzip.decompress(legal_bytes));by_dec={r['decisionIndex']:r for r in legal};trace=prefix['trace']
  tokens=[];serial=0;acquisitions=[];relics=[]
  for idx,c in enumerate(trace[0]['pre']['deck']):
   tokens.append({'token':f'start-{idx+1}','card':c,'source':'starting deck' if c!="Ascender's Bane" else 'starting ascension curse','trace':None,'decision':None,'floor':0,'history':[]})
  for ti,r in enumerate(trace[:-1]):
   assert [x['card'] for x in tokens]==r['pre']['deck'],(seed,ti,'prefix deck discontinuity')
   before=deepcopy(tokens);post=r['post']['deck'];out=[]
   for tag,a,b,c,d in SequenceMatcher(None,[base(x['card']) for x in before],[base(x) for x in post],autojunk=False).get_opcodes():
    if tag=='equal':
     for token,newname in zip(before[a:b],post[c:d]):
      if token['card']!=newname:token['history'].append({'trace':ti,'decision':r.get('idx'),'floor':r['pre']['floor'],'from':token['card'],'to':newname})
      token['card']=newname;out.append(token)
    elif tag in ['insert','replace']:
     screen=r['pre']['screen'];event=r['pre']['event']
     source_name='Pandora batch (9 starters ->9 products)' if screen=='BOSS_RELIC' else 'event transform' if event=='Transmorgrifier' else 'shop purchase' if screen=='SHOP' else 'Neow card reward' if screen=='REWARDS' and r['pre']['floor']==0 else 'Sensory Stone card reward' if screen=='REWARDS' and seed==111101326 and r['pre']['floor']==36 else 'ordinary card reward' if screen=='REWARDS' else 'other acquisition'
     for newname in post[c:d]:
      serial+=1;token={'token':f'acq-{serial}','card':newname,'source':source_name,'trace':ti,'decision':r.get('idx'),'floor':r['pre']['floor'],'history':[],'parents':[x['token'] for x in (before if 'Pandora' in source_name else before[a:b]) if ('Pandora' not in source_name or base(x['card']) in ['Strike','Defend'])]};out.append(token);acquisitions.append(deepcopy(token))
   tokens=out;assert [t['card'] for t in tokens]==post,(seed,ti,'accounting mismatch')
   for relic in r['post']['relics']:
    if relic not in r['pre']['relics']:relics.append({'relic':relic,'trace':ti,'decision':r.get('idx'),'floor':r['pre']['floor'],'screen':r['pre']['screen'],'event':r['pre']['event']})
   if r['kind']!='ooc' or r.get('idx') not in by_dec:continue
   root=by_dec[r['idx']];assert root['floor']==r['pre']['floor']
   if root['screen'] not in [1,2,3,8]:continue
   siblings=[describe(k) for k in root['legal_keys']]
   for sibling in siblings:
    card=re.search(r':card=(\d+)',sibling['key']);sibling['engine_threat']=bool(card and CARDS[int(card[1])] in {CARDS[i] for i in range(len(CARDS)) if CARDS[i].replace('_','').lower() in {x.replace(' ','').lower() for x in CORE[seed]}} and sibling['effect'] in [1,2,3])
   op={'seed':seed,'trace':ti,'decision':r['idx'],'floor':r['pre']['floor'],'act':r['pre']['act'],'screen':r['pre']['screen'],'event':r['pre']['event'],'historical_key':root['selectedKey'],'historical_action':describe(root['selectedKey']),'gold':r['pre']['gold'],'deck_before':r['pre']['deck'],'cards_added':list((Counter(r['post']['deck'])-Counter(r['pre']['deck'])).elements()),'cards_removed':list((Counter(r['pre']['deck'])-Counter(r['post']['deck'])).elements()),'skip_exists':any(s['effect'] in [12,28] for s in siblings),'siblings':siblings,'offer':r.get('offer',{}),'same_map_path_structurally':True}
   if 'neow_offers' in root:op['neow_offers']=root['neow_offers']
   bonuses=['choose three cards','random rare card','remove one','upgrade one','transform one','colorless reward','three potions','random common relic','max HP','Neow Lament','100 gold','rare colorless reward','remove two','rare relic','three rare cards','250 gold','transform two','max HP','boss relic swap']
   for sib in siblings:
    if sib['effect']==26:
     option=int(re.search(r':option=(\d+)',sib['key'])[1]);event=r['pre']['event']
     if event=='NEOW':
      n=root['neow_offers'][option];drawbacks=['invalid','none','10% max HP loss','lose all gold','one random curse','HP becomes floor(HP/10)*7','lose starter relic'];sib['label']=bonuses[n['r']]+' (drawback: '+drawbacks[n['d']]+')';sib['deck_effect']='reward/selector or coupled random relic outcome; not an observed independent card deletion'
      if n['r']==2:sib['deck_effect']='remove one legal selected card, -1 permanent; if starter selected before Pandora the future batch changes'
      if n['r'] in [0,11]:sib['deck_effect']='one optional card-reward group; pick adds one card, SKIP adds none'
      if n['r'] in [10,15]:sib['gold_gain']=100 if n['r']==10 else 250
      if n['d']==4:sib['adds']=['one unobserved random curse'];sib['deck_effect']+='; curse drawback adds one permanent card'
     elif event=='The Cleric':sib['label']={0:'heal35g (excludes removal)',2:'leave'}[option];sib['gold_cost']=35 if option==0 else 0;sib['deck_effect']='no permanent deck change'
     elif event=='Sensory Stone':sib['label']=f'{option+1} colorless reward group(s), {5*option} HP';sib['deck_effect']='0 immediate cards; each group subsequently permits pick or SKIP; earlier group generation prefix unchanged'
     elif event=='Shining Light':sib['label']='upgrade two random cards, HP cost' if option==0 else 'leave';sib['deck_effect']='upgrades only, permanent cardinality unchanged'
     elif event=='Golden Idol':sib['label']='take idol, opens curse/HP/maxHP choice' if option==0 else 'leave';sib['deck_effect']='0 immediate cards; a later Injury option can add one curse, HP alternatives need not'
     elif event=='Transmorgrifier':sib['label']='leave';sib['deck_effect']='0 cards; would forego historical Fire Breathing output'
     elif event=='WeMeetAgain':sib['label']={0:'give offered potion for relic',1:'give offered gold121 for relic',2:'give offered Headbutt for relic',3:'leave'}[option];sib['deck_effect']='only offered Headbutt can be removed; it is already absent under reward-skip accounting' if option==2 else 'no permanent card change'
    if sib['effect']==1:sib['deck_effect']='remove exactly the named owned non-bottled removable card; Ascenders Bane absent from legal removal siblings'
    if sib['effect'] in [23,27]:
     name=sib['label'].split()[-1]
     sib['deck_effect']={'PANDORAS_BOX':'replace all starter Strikes/Defends, count unchanged; all historical products form one batch','ASTROLABE':'transform+upgrade three owned cards, no permanent count reduction; outputs unobserved','MARK_OF_PAIN':'0 permanent cards; +1 energy/turn and2 temporary Wounds every combat','CURSED_KEY':'0 immediate cards; future opened nonboss chests may add a curse','TINY_HOUSE':'one optional card reward plus gold/HP/potion/random upgrade; skip may avoid addition'}.get(name,'no immediate permanent-card count change')
   protected_decisions={111101032:{22},111101326:{22,90,114,115},111101512:{35,40}}[seed]
   for sib in siblings:
    if r['idx'] in protected_decisions and sib['effect'] in [5,12] and sib['key']!=root['selectedKey']:
     sib['engine_threat']=True;sib['engine_note']='foregoes a frozen engine acquisition in this reward group'
    if seed==111101032 and r['pre']['screen']=='BOSS_RELIC' and sib['key']!=root['selectedKey']:
     sib['engine_threat']=True;sib['engine_note']='foregoes the only observed two-Dropkick batch; alternate random products unverified'
    if seed==111101032 and r['pre']['event']=='NEOW' and 'remove one' in sib['label']:
     sib['engine_note']='changes pre-Pandora starter count if a starter is selected; coupled, not independently counted'
    if seed==111101326 and r['pre']['event']=='Sensory Stone' and ':option=0' in sib['key']:
     sib['engine_threat']=True;sib['engine_note']='only one reward group, so the second frozen Flash group is not generated'
   op['future_policy_engine_retention']='unverified under any altered trajectory; accounting holds historical offers/products only'
   op['historical_action']=next((sib for sib in siblings if sib['key']==root['selectedKey']),op['historical_action'])
   all_opportunities.append(op)
   labels='; '.join(s['label']+(f" ({s['gold_cost']}g)" if s['gold_cost'] else '') for s in siblings)
   opportunities_lines.append(f"| {seed} | {ti} / {r['idx']} / {r['pre']['floor']} | {r['pre']['screen']} {r['pre']['event']} | {op['historical_action']['label']} | {'yes' if op['skip_exists'] else 'no'} | {op['gold']} | {labels} |")
  target=trace[-1];assert target['kind']=='battle' and [t['card'] for t in tokens]==target['pre']['deck']
  origin_by_token={t['token']:t for t in acquisitions}
  for i,t in enumerate(tokens):
   t['parent_origins']=[origin_by_token[parent] for parent in t.get('parents',[]) if parent in origin_by_token]
   t['target_slot']=i+1;t['engine']=base(t['card']) in CORE[seed]
   upgrades='; '.join(f"{h['from']} -> {h['to']} f{h['floor']} d{h['decision']}" for h in t['history']) or 'none'
   provenance_lines.append(f"| {seed} | {i+1} | {t['card']} | {t['source'] + (' of ' + ', '.join(x['card'] + ' (f' + str(x['floor']) + ' d' + str(x['decision']) + ')' for x in t['parent_origins']) if t['parent_origins'] else '')} | {t['floor']} / {t['trace']} / {t['decision']} | {upgrades} | {'yes' if t['engine'] else 'no'} |")
  # Independent reward picks only. Protect the transformed Flame Barrier lineage
  # in032: the historical transform target disappears if that acquisition is skipped.
  skip=[t for t in tokens if 'card reward' in t['source'] and not t['engine']]
  cleanA=[t for t in tokens if t not in skip]
  protected=[]
  if seed==111101032:
   protected=[a for a in acquisitions if a['card']=='Flame Barrier'];assert len(protected)==1
  # Fixed, resource-feasible optimistic B plans. Card-purchase displacement is
  # explicit, never silently treated as a free removal.
  B=deepcopy(cleanA);removed=[];forgone=[]
  def remove_one(predicate,reason):
   token=next(t for t in B if predicate(t));assert not token['engine'];B.remove(token);removed.append({'card':token['card'],'token':token['token'],'reason':reason})
  if seed==111101032:
   remove_one(lambda t:t['source']=='event transform','Cleric f8,75g instead of35g heal; preserve nine Pandora inputs')
   plan=[{'floor':8,'historical_entry_gold':177,'available_gold':177,'cost':75,'replaces':'35g heal','removed':removed[-1]['card'],'balance_after':102,'gold_delta_after':-40}]
  elif seed==111101326:
   for t in list(B):
    if t['source']=='shop purchase' and t['floor'] in [2,25]:
     B.remove(t);forgone.append({'card':t['card'],'token':t['token'],'reason':'shop removal funding displaces this non-engine card purchase; see running cash plan'})
   for f in [2,25,31]:remove_one(lambda t:t['card']=='Strike',f'shop f{f}; escalating removal cost')
   plan=[{'floor':2,'historical_entry_gold':110,'available_gold':110,'cost':75,'forgone':['Dramatic Entrance72g','Anger38g'],'other_spend':0,'balance_after':35,'gold_delta_after':35},
         {'floor':25,'historical_entry_gold':251,'available_gold':286,'cost':100,'forgone':['Feel No Pain56g','Power Potion38g'],'other_spend':118,'retained':['Sling of Courage118g'],'balance_after':68,'gold_delta_after':29},
         {'floor':31,'historical_entry_gold':99,'available_gold':128,'cost':125,'forgone':['Blessing of the Forge42g','Colorless Potion41g'],'other_spend':0,'balance_after':3,'gold_delta_after':-13}]
  else:
   for t in list(B):
    if t['source']=='shop purchase':
     B.remove(t);forgone.append({'card':t['card'],'token':t['token'],'reason':'f7 removal funding displaces Uppercut64g and potion41g, preserving Orichalcum117g'})
   remove_one(lambda t:t['card']=='Strike','Cleric f4,75g instead of35g heal')
   remove_one(lambda t:t['card']=='Strike','shop f7,75g; event removal does not increment shopRemoveCount')
   plan=[{'floor':4,'historical_entry_gold':247,'available_gold':247,'cost':75,'replaces':'35g heal','balance_after':172,'gold_delta_after':-40},
         {'floor':7,'historical_entry_gold':232,'available_gold':192,'cost':75,'forgone':['Uppercut64g','Colorless Potion41g'],'other_spend':117,'retained':['Orichalcum117g'],'balance_after':0,'gold_delta_after':-10}]
  for v in plan:assert v['available_gold']>=v['cost']+v.get('other_spend',0) and v['balance_after']==v['available_gold']-v['cost']-v.get('other_spend',0)
  # Assert that all advertised removal places had a legal removal sibling.
  for v in plan:
   assert any(o['seed']==seed and o['floor']==v['floor'] and any(s['effect']==1 for s in o['siblings']) for o in all_opportunities)
  result={'seed':seed,'permanent_deck_size':len(tokens),'historical_min_active':{111101032:16,111101326:30,111101512:19}[seed],
          'target_cards':tokens,'relic_acquisitions':relics,'all_acquisitions':acquisitions,'engine_core':sorted(CORE[seed]),'engine_relics':['SUNDIAL'] if seed==111101512 else [],
          'reward_skip_bound':{'deck_size':len(cleanA),'deck':[t['card'] for t in cleanA],'skips':skip,'dependent_acquisition_not_independently_deleted':protected,'scope':'clean independent skips; Flame Barrier transform dependency separately disclosed'},
          'skip_remove_bound':{'deck_size':len(B),'deck':[t['card'] for t in B],'removed':removed,'forgone_shop_cards':forgone,'resource_plan':plan,'scope':'optimistic fixed-route accounting; explicitly replaces purchases to fund removals; not replayed'},
          'gate_A':len(cleanA)<=10 or len(tokens)-len(cleanA)>=6,'gate_B':len(B)<=10 or len(tokens)-len(B)>=6}
  results.append(result)
 for r in results:
  assert Counter(base(t['card']) for t in r['target_cards'] if t['engine']) <= Counter(base(c) for c in r['reward_skip_bound']['deck'])
  assert Counter(base(t['card']) for t in r['target_cards'] if t['engine']) <= Counter(base(c) for c in r['skip_remove_bound']['deck'])
 bound_lines=['# Nested offline compression bounds','', 'A uses independent non-engine reward skips, preserving the032 transform input. B additionally funds actual route removals and explicitly displaces purchases. Neither predicts active combat pool or survival.','', '| Run | Permanent | Historical min active | A size / reduction | B size / reduction | Gate A / B |','|---|---:|---:|---|---|---|']
 for result in results:
  a=result['reward_skip_bound'];b=result['skip_remove_bound'];n=result['permanent_deck_size']
  bound_lines.append(f"| {result['seed']} | {n} | {result['historical_min_active']} | {a['deck_size']} / {n-a['deck_size']} | {b['deck_size']} / {n-b['deck_size']} | {result['gate_A']} / {result['gate_B']} |")
 for result in results:
  a=result['reward_skip_bound'];b=result['skip_remove_bound']
  bound_lines += ['',f"## {result['seed']}",'',f"A ({a['deck_size']}): "+', '.join(a['deck'])+'.','',f"B ({b['deck_size']}): "+', '.join(b['deck'])+'.','', 'Reward skips: '+'; '.join(f"f{t['floor']}/d{t['decision']} {t['card']}" for t in a['skips'])+'.','', 'B removed: '+'; '.join(t['card']+' — '+t['reason'] for t in b['removed'])+'.','', 'B displaced shop cards: '+(', '.join(t['card'] for t in b['forgone_shop_cards']) or 'none')+'.','', '| Floor | Historical gold | Accounting gold | Removal | Other spend | Forgone | Balance |','|---|---:|---:|---:|---:|---|---:|']
  for step in b['resource_plan']:
   bound_lines.append(f"| {step['floor']} | {step['historical_entry_gold']} | {step['available_gold']} | {step['cost']} | {step.get('other_spend',0)} | {', '.join(step.get('forgone',[step.get('replaces','')]))} | {step['balance_after']} |")
 outputs={'BOUNDS.md':'\n'.join(bound_lines)+'\n','AUDIT.json':json.dumps(results,indent=2)+'\n','opportunities.json':json.dumps(all_opportunities,indent=2)+'\n','PROVENANCE.md':'\n'.join(provenance_lines)+'\n','OPPORTUNITIES.md':'\n'.join(opportunities_lines)+'\n'}
 return outputs

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
 for name,body in generate().items():
  if args.check:assert (E/name).read_text()==body,name
  else:(E/name).write_text(body)
 print('PASS full prefix card lineage, legal siblings, nested independent-skip/resource-removal bounds; no simulator or oracle execution')
