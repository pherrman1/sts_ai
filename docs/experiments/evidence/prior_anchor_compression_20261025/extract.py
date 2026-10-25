import subprocess,gzip,json,hashlib,pathlib
out=pathlib.Path('docs/experiments/evidence/prior_anchor_compression_20261025')
sha='1322e0d97721d9ffe9e2e41dbc69d8a5acc07a01'
cases={'032/11111':('combat_infinity_mask_search_20261025/runs/11111',111101032),'326/13-skip':('combat_infinity_counterfactual_20261024/treatment',111101326),'326/R1':('combat_infinity_r1_20261025/treatment',111101326)}
inputs=[];sources=[]
for case,(prefix,seed) in cases.items():
 loaded={}
 for typ in ['states','trace']:
  path='docs/experiments/evidence/'+prefix+'.'+typ+'.jsonl.gz';b=subprocess.check_output(['git','show',sha+':'+path]);sources.append({'case':case,'path':path,'sha256':hashlib.sha256(b).hexdigest()});loaded[typ]=[json.loads(l) for l in gzip.decompress(b).splitlines()]
 states={r['index']:r for r in loaded['states'] if r.get('type')=='state'}
 for r in loaded['trace']:
  if r.get('by')!='infinity_skip':continue
  matches=[s for s in states.values() if (s['floor'],s['act'])==(r['pre']['floor'],r['pre']['act']) and s['record']['cards_offered.cards']]
  assert len(matches)==1; s=matches[0]
  assert len(s['record']['obs.deck.cards'])==len(r['pre']['deck'])
  assert s['record']['obs.fixed_observation'][:4]==[r['pre']['hp'],r['pre']['maxHp'],r['pre']['gold'],r['pre']['floor']]
  record=s['record'].copy();assert 'obs.act' not in record;record['obs.act']=s['act']
  # All retained decks are free of misc-bearing cards. Fail rather than impute trained inputs.
  record['obs.deck.misc']=[0]*len(record['obs.deck.cards'])
  row={'case':case,'seed':seed,'decision':r['idx'],'state_index':s['index'],'act':s['act'],'floor':s['floor'],'record':record,'trace':r,'historical_record':s['record'],'expected_skip_key':'ooc:v1:effect=12:source=7:reward=none:group=['+''.join(f'{c},0,{u};' for c,u in sorted(zip(record['cards_offered.cards'],record['cards_offered.upgrades'])))+']:groupOccurrence=0:occurrence=0:sapphirePaired=0'};inputs.append(row)
(out/'inputs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in inputs))
(out/'sources.json').write_text(json.dumps({'historical_sha':sha,'sources':sources,'counts':{c:sum(r['case']==c for r in inputs) for c in cases}},indent=2)+'\n')
print('rows',len(inputs),json.loads((out/'sources.json').read_text())['counts'])
