#!/usr/bin/env python3
"""Verify retained pilot coverage and K=4 sidecar denominators."""
import hashlib
import json
from pathlib import Path
E=Path(__file__).resolve().parent
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
(E/'RESULT.json').write_text(json.dumps(summary,indent=2)+'\n')
lines=['# K=4 public-root pilot matrix','','| Root | Supported worlds | Certified fraction | Candidate fraction | Minimum reach |','| --- | ---: | ---: | ---: | ---: |']
for r in rows:
 lines.append(f"| {r['fixture']} | 4/4 | {r['certified_fraction']} | {r['candidate_fraction']} | {r['minimum_reach_depth'] if r['minimum_reach_depth'] is not None else 'null'} |")
for i,r in enumerate(natural[:-1]):
 lines.append(f"| archived root {i} | unsupported | null | null | null |")
lines+=['','Candidate fraction includes certified and rejected damaging candidates. Unsupported roots are not negatives. The four natural roots were not sampled because no-Shard provenance was absent. All 16 control worlds retain unchanged oracle caps.','']
(E/'MATRIX.md').write_text('\n'.join(lines))
print(json.dumps(summary,sort_keys=True))
