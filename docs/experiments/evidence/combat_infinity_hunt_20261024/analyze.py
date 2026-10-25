#!/usr/bin/env python3
"""Validate frozen census/selection and reuse identical already-committed worlds."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

E=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
def sha(b):return hashlib.sha256(b).hexdigest()
def emit(name,value):
 text=value if isinstance(value,str) else json.dumps(value,indent=2)+'\n'
 if args.check:assert (E/name).read_bytes()==text.encode(),name+' differs'
 else:(E/name).write_text(text)
c=json.loads((E/'census.json').read_text());s=json.loads((E/'SELECTION.json').read_text())
assert sha((E/'census.json').read_bytes())==s['census_sha256']
assert sha((E/'selected-inputs.jsonl').read_bytes())==s['selected_input_sha256']
assert (E/'selected-inputs.jsonl').read_bytes()==(E/s['prior_input']).read_bytes()
assert s['novel_selected_roots']==0 and s['current_A20_selected_roots']==0
assert sha((E/s['prior_output']).read_bytes())==s['prior_output_sha256']
raw=[json.loads(x) for x in (E/s['prior_output']).read_text().splitlines()]
assert len(raw)==5 and raw[-1]['roots']==4
assert len(s['roots'])<=32 and s['roots']==c['selected_roots']
counts=Counter((r['source'],r['run'],str(r['identity']['fight'])) for r in s['roots']);assert max(counts.values())<=4
rows=[]
for i,(root,record) in enumerate(zip(s['roots'],raw[:-1])):
 assert root['identity']['decision']==[1,2,3,5][i] and root['identity']['fight']==13
 assert root['enrichment']['reasons']==['K4_headbutt_draw']
 assert record['root_index']==i and record['K']==4 and record['supported_worlds']==4 and record['status']=='ANNOTATED'
 worlds=[w['oracle'] for w in record['worlds']]
 assert len(worlds)==4
 for o in worlds:
  assert o['caps']=={'actions_per_replay':1024,'candidates':16,'cycle_length':24,'depth':24,'nodes':2000,'repetitions':128,'total_replay_actions':4096}
  assert o['supported'] and o['nodes']<=2000 and o['max_depth']<=24
 cert=sum(o['classification']=='CERTIFIED_KILL' for o in worlds)
 cand=sum(any(x['classification']!='STALL_LOOP' for x in o['candidates']) for o in worlds)
 assert record['certified_fraction']==cert/4 and record['candidate_fraction']==cand/4
 candidates=[candidate for o in worlds for candidate in o['candidates'] if candidate['classification']!='STALL_LOOP']
 rows.append({'source':root['source'],'run':root['run'],'fight':root['identity']['fight'],'decision':root['identity']['decision'],
              'public_sha256':root['public_sha256'],**root['enrichment'],'supported_worlds':4,
              'evidence_status':'REUSED_PRIOR_OUTPUT_NOT_A_NEW_EXPERIMENT',
              'certified_fraction':record['certified_fraction'],'candidate_fraction':record['candidate_fraction'],
              'minimum_reach_depth':record['minimum_reach_depth'],
              'node_cap_worlds':sum(o['node_cap_hit'] for o in worlds),
              'depth_cap_worlds':sum(o['depth_cap_hit'] for o in worlds),
              'candidate_cap_worlds':sum(len(o['candidates'])>=16 for o in worlds),
              'nodes':sum(o['nodes'] for o in worlds),'max_depth':max(o['max_depth'] for o in worlds),
              'prior_oracle_cpu_ms':round(sum(o['cpu_ms'] for o in worlds),3),
              'representative_witness':next(iter(candidates),None),
              'interpretation':'INCONCLUSIVE_NODE_CAP' if any(o['node_cap_hit'] for o in worlds) else 'NO_CANDIDATE_IN_BOUNDED_SUPPORTED_SEARCH'})
groups=c['groups'];ooc={k:g for k,g in groups.items() if g['kind']=='OOC_PUBLIC_RECORD'}
source_runs={seed for g in ooc.values() for seed in g['runs']}
reasons={r:len({run for g in ooc.values() for run in g['reason_runs'].get(r,[])}) for r in sorted({r for g in ooc.values() for r in g['reason_runs']})}
summary={'schema':'infinity_targeted_hunt_v1','starting_sha':c['starting_sha'],'main_readonly_sha':c['main_readonly_sha'],
         'current_policy_natural_positive_signal':'BLOCKED_BY_DATA',
         'ooc_run_ids_screened':len(source_runs),'ooc_records_screened':sum(g['states'] for g in ooc.values()),
         'ooc_known_engine_run_ids':len({seed for g in ooc.values() for seed in g['known_runs']}),
         'ooc_known_engine_states':sum(g['known_engine_states'] for g in ooc.values()),
         'ooc_run_counts_per_subclass_overlapping':reasons,
         'generic_compression_assessable_for_ooc':False,
         'public_combat_roots_screened':c['public_roots_screened'],
         'public_declared_run_ids':len({seed for g in groups.values() if g['kind']=='PUBLIC_COMBAT_ROOT' for seed in g['runs']}),
         'enriched_public_roots':c['enriched_public_roots'],
         'generic_near_cycle_public_roots':sum(g['generic_states'] for g in groups.values() if g['kind']=='PUBLIC_COMBAT_ROOT'),
         'provenance_complete_public_roots':c['provenance_complete_public_roots'],
         'selected_roots':len(rows),'selected_current_A20_roots':0,'novel_selected_roots':0,
         'new_oracle_worlds':0,'new_oracle_cpu_ms':0,'reused_prior_world_records':16,
         'certified_worlds_in_reused_selection':sum(int(r['certified_fraction']*4) for r in rows),
         'candidate_worlds_in_reused_selection':sum(int(r['candidate_fraction']*4) for r in rows),
         'node_cap_worlds_in_reused_selection':sum(r['node_cap_worlds'] for r in rows),
         'node_cap_fraction_in_reused_selection':sum(r['node_cap_worlds'] for r in rows)/16,
         'node_cap_rate_for_current_policy':None,
         'prior_oracle_cpu_ms_reused':round(sum(r['prior_oracle_cpu_ms'] for r in rows),3),
         'read_only_census_wall_seconds':json.loads((E/'census-receipt.json').read_text())['wall_seconds'],
         'capture_patch_implemented':False,'new_collection':False,
         'missing_current_combat_field':'complete owned run relic inventory / authoritative no-Shard proof bound to each public root',
         'missing_ooc_field':'public in-combat BattleStateWire at an actual player boundary'}
emit('RESULT.json',summary);emit('matrix.json',rows)
lines=['# Targeted screen: K=4 evidence matrix','',
       '**All four rows reuse the prior committed pilot; no new oracle execution. Current-policy selected roots/worlds: 0/0.**','',
       '| Run / fight / decision | Class | Active cards | Relevant cards | Relevant relics | Supported | Certified / candidate | Reach | Node/depth/candidate caps | Nodes | Depth | Prior CPU ms | Witness / interpretation |',
       '|---|---|---:|---|---|---:|---|---|---|---:|---:|---:|---|']
for r in rows:
 cards=', '.join(f'{k} x{v}' for k,v in r['relevant_cards'].items())
 lines.append(f"| {r['run']} / {r['fight']} / {r['decision']} | K4 | {r['active_card_count']} | {cards} | none of screened relics | 4/4 | {r['certified_fraction']} / {r['candidate_fraction']} | null | {r['node_cap_worlds']}/{r['depth_cap_worlds']}/{r['candidate_cap_worlds']} | {r['nodes']} | {r['max_depth']} | {r['prior_oracle_cpu_ms']:.3f} | none; {r['interpretation']} |")
emit('MATRIX.md','\n'.join(lines)+'\n')
print(json.dumps(summary,sort_keys=True));print('PASS census arithmetic, frozen selection, exact prior-input/output hashes and unchanged per-world bounds; no oracle execution')
