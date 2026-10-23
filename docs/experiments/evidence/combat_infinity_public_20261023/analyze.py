#!/usr/bin/env python3
"""Verify retained pilot coverage and K=4 sidecar denominators."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
E=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check',action='store_true',help='validate generated reporting without rewriting it')
args=parser.parse_args()
def emit(name,content):
 if args.check:
  assert (E/name).read_bytes()==content.encode(),name+': generated reporting differs'
 else:
  (E/name).write_text(content)
controls=list(map(json.loads,(E/'public-controls.jsonl').read_text().splitlines()))
expected={'public_static_exhaust_dropkick':(1,1,4),'public_energy_positive':(1,1,4),'public_broken_dropkick':(0,0,None),'public_phase_guard':(0,1,4)}
rows=controls[:-1]
assert {r['fixture'] for r in rows}==set(expected)
assert controls[-1]['public_contract_assertions']=='PASS'
assert len(controls[-1]['known_boundary_samples'])==4
for sample in controls[-1]['known_boundary_samples']:
 ids=sample['draw_bottom_first'];assert ids[0]==5 and ids[-1]==1 and sorted(ids)==[1,2,3,4,5]
caps={'depth':24,'cycle_length':24,'nodes':2000,'candidates':16,'repetitions':128,'actions_per_replay':1024,'total_replay_actions':4096}
for r in rows:
 assert r['K']==4 and r['status']=='ANNOTATED' and r['supported_worlds']==4
 assert len(r['worlds'])==4 and {w['k'] for w in r['worlds']}==set(range(4))
 assert len({w['sample_seed'] for w in r['worlds']})==4
 assert (r['certified_fraction'],r['candidate_fraction'],r['minimum_reach_depth'])==expected[r['fixture']]
 assert all(w['oracle']['supported'] and w['oracle']['caps']==caps for w in r['worlds'])
 cert=sum(w['oracle']['classification']=='CERTIFIED_KILL' for w in r['worlds'])
 cand=sum(any(c['classification']!='STALL_LOOP' for c in w['oracle']['candidates']) for w in r['worlds'])
 assert r['certified_fraction']==cert/4 and r['candidate_fraction']==cand/4
natural=list(map(json.loads,(E/'public-sidecars.jsonl').read_text().splitlines()))
assert natural[-1]=={'schema':'combat_infinity_public_pilot_summary_v1','roots':4,'annotated_roots':0,'unsupported_roots':4,'K':4,'root_cap':4}
for i,r in enumerate(natural[:-1]):
 assert r['root_index']==i and r['K']==4 and r['status']=='UNSUPPORTED'
 assert r['reason']=='missing_proven_no_prismatic_shard' and r['supported_worlds']==0 and not r['worlds']
 assert all(r[k] is None for k in ('certified_fraction','candidate_fraction','minimum_reach_depth'))
manifest=json.loads((E/'root-inventory.json').read_text())
assert hashlib.sha256((E/'public-roots.jsonl').read_bytes()).hexdigest()==manifest['public_input_sha256']
all_worlds=[w['oracle'] for r in rows for w in r['worlds']]
summary={'adapter_contract':'PASS','natural_annotation':'BLOCKED_MISSING_NO_SHARD_PROVENANCE','K':4,'control_roots':4,'control_worlds':16,'natural_roots':4,'annotated_natural_roots':0,'unsupported_natural_roots':4,'max_nodes_per_control_world':max(w['nodes'] for w in all_worlds),'max_cpu_ms_per_control_world':max(w['cpu_ms'] for w in all_worlds),'total_control_cpu_ms':sum(w['cpu_ms'] for w in all_worlds)}
expanded=[]
for source,records in [('public-controls.jsonl',rows),('public-sidecars.jsonl',natural[:-1])]:
 for r in records:
  worlds=r['worlds']
  damaging=[(w,c) for w in worlds for c in w['oracle']['candidates'] if c['classification']!='STALL_LOOP']
  certified=sum(w['oracle']['classification']=='CERTIFIED_KILL' for w in worlds)
  candidate_samples=len({w['k'] for w,c in damaging})
  chosen=next(((w,c) for w,c in damaging if c['classification']=='CERTIFIED_KILL'),damaging[0] if damaging else None)
  witness=None
  if chosen:
   w,c=chosen
   witness={'world_index':w['k'],'sample_seed':w['sample_seed'],**copy.deepcopy(c)}
  searched=[w['oracle'] for w in worlds if w['oracle']['supported']]
  cap_counts={'searched_samples':len(searched),
   'node_cap_samples':sum(o['node_cap_hit'] for o in searched) if searched else None,
   'depth_cap_samples':sum(o['depth_cap_hit'] for o in searched) if searched else None,
   'candidate_cap_samples':sum(len(o['candidates'])>=o['caps']['candidates'] for o in searched) if searched else None,
   'replay_period_cap_rejections':sum(c.get('replay',{}).get('reason')=='repetition_cap' for o in searched for c in o['candidates']) if searched else None,
   'replay_action_cap_rejections':sum(c.get('replay',{}).get('reason')=='action_cap' for o in searched for c in o['candidates']) if searched else None,
   'total_replay_cap_samples':sum(o['replay_actions']>=o['caps']['total_replay_actions'] for o in searched) if searched else None}
  report={'schema':'combat_infinity_public_reporting_v1','source_file':source,
   'fixture':r.get('fixture'),'root_index':r.get('root_index'),'public_root_sha256':r['public_root_sha256'],
   'status':r['status'],'reason':r['reason'],'K':r['K'],
   'supported_samples':r['supported_worlds'],'certified_kill_samples':certified,'candidate_samples':candidate_samples,
   'certified_fraction':r['certified_fraction'],'candidate_fraction':r['candidate_fraction'],
   'minimum_reach_depth':r['minimum_reach_depth'],'search_cap_hits':cap_counts,'representative_witness':witness}
  if r['status']=='ANNOTATED':
   assert report['supported_samples']==4 and report['certified_fraction']==certified/4 and report['candidate_fraction']==candidate_samples/4
  else:
   assert report['supported_samples']==0 and not worlds and report['certified_fraction'] is None and report['candidate_fraction'] is None and witness is None
  expanded.append(report)
summary['eligible_natural_roots']=sum(r['status']=='ANNOTATED' for r in natural[:-1])
summary['annotated_natural_worlds']=sum(len(r['worlds']) for r in natural[:-1] if r['status']=='ANNOTATED')
assert summary['eligible_natural_roots']==0 and summary['annotated_natural_worlds']==0
emit('expanded-sidecars.json',json.dumps(expanded,indent=2)+'\n')
emit('RESULT.json',json.dumps(summary,indent=2)+'\n')
lines=['# K=4 public-root pilot matrix','','| Root | Supported samples | Certified samples | Candidate samples | Certified fraction | Candidate fraction | Minimum reach |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for r in expanded:
 name=r['fixture'] or f"archived root {r['root_index']}"
 fmt=lambda key:'null' if r[key] is None else str(r[key])
 lines.append(f"| {name} | {r['supported_samples']}/4 | {r['certified_kill_samples']} | {r['candidate_samples']} | {fmt('certified_fraction')} | {fmt('candidate_fraction')} | {fmt('minimum_reach_depth')} |")
lines+=['','Candidate fraction includes certified and rejected damaging candidates. Unsupported roots are not negatives: zero observed sample counts reflect zero searches, while fractions remain null. Eligible natural roots: **0**; annotated natural worlds: **0**. The original provenance-blocked verdict is unchanged.','','| Root | Searched samples | Node cap | Depth cap | Candidate cap | Replay period/action caps | Representative witness |','| --- | ---: | ---: | ---: | ---: | --- | --- |']
for r in expanded:
 name=r['fixture'] or f"archived root {r['root_index']}"; c=r['search_cap_hits']; w=r['representative_witness']
 fmt=lambda key:'not searched' if c[key] is None else str(c[key])
 witness=f"world {w['world_index']}, reach {w['reach_depth']}, cycle {w['cycle_length']}, {w['classification']}" if w else 'none'
 lines.append(f"| {name} | {c['searched_samples']} | {fmt('node_cap_samples')} | {fmt('depth_cap_samples')} | {fmt('candidate_cap_samples')} | {fmt('replay_period_cap_rejections')}/{fmt('replay_action_cap_rejections')} | {witness} |")
lines+=['','Expanded counts, all cap categories and exact representative reach/cycle/replay records are in expanded-sidecars.json. They are derived offline from the unchanged raw sidecars; no world sampling or gameplay was rerun. All 16 control worlds retain unchanged oracle caps.','']
emit('MATRIX.md','\n'.join(lines))
print(json.dumps(summary,sort_keys=True))
if args.check: print('PASS generated result, matrix and expanded sidecars match committed raw evidence')
