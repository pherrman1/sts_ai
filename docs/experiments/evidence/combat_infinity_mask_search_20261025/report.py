#!/usr/bin/env python3
"""Validate and summarize retained search/capture/sidecars, never run a world."""
from collections import Counter
import gzip
import hashlib
import json
from build_runtime import HERE,sha,write
from qualify import difference
from search_logic import assess,locate_stop

def rows(path):return [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
def generate():
    selected=json.loads((HERE/'SELECTED_MASK.json').read_text());assert selected['all_32_valid'] and selected['best_mask']=='11111' and selected['gate_pass']
    choice=json.loads((HERE/'results/11111.json').read_text())['measurement'];capture=json.loads((HERE/'capture/11111.receipt.json').read_text());selection=json.loads((HERE/'selection.json').read_text())
    assert capture['status']=='CAPTURED' and capture['first_difference'] is None
    assert selection['selected_mask_sha256']==sha(HERE/'SELECTED_MASK.json') and selection['capture_receipt_sha256']==sha(HERE/'capture/11111.receipt.json')
    for name in ['trace.jsonl','states.jsonl','stdout.log','stderr.log','public.jsonl']:
        assert hashlib.sha256(gzip.decompress((HERE/'capture'/f'11111.{name}.gz').read_bytes())).hexdigest()==capture['files'][name]
    search_rows=rows(HERE/'runs/11111.trace.jsonl.gz');capture_rows=rows(HERE/'capture/11111.trace.jsonl.gz');endpoint=locate_stop(capture_rows)
    assert difference(choice,assess(31,json.loads((HERE/'manifests/11111.json').read_text()),capture_rows,endpoint)) is None
    index=choice['target']['boundary_index']
    def prefix(path):return [r for r in rows(path) if r.get('type')=='header' or (r.get('type')=='state' and r['index']<=index)]
    a=prefix(HERE/'runs/11111.states.jsonl.gz');b=prefix(HERE/'capture/11111.states.jsonl.gz')
    assert difference(a,b) is None and [r['index'] for r in b if r.get('type')=='state']==list(range(index+1))
    assert capture['capture_battle']['post']['hp']==36
    assert next(r for r in capture_rows if r.get('kind')=='infinity_mask_boundary' and r['index']>index)['integrity_so_far']
    oracle_receipt=json.loads((HERE/'oracle.receipt.json').read_text());assert oracle_receipt['returncode']==0
    for name,key in [('selection.json','selection_sha256'),('inputs.jsonl','inputs_sha256'),('oracle.jsonl','output_sha256'),('oracle.stderr.txt','stderr_sha256')]:assert sha(HERE/name)==oracle_receipt[key]
    assert oracle_receipt['adapter_binary_sha256']==selection['oracle_binary_sha256']=='28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9'
    sidecars=[json.loads(line) for line in (HERE/'oracle.jsonl').read_text().splitlines()];assert len(sidecars)==5 and sidecars[-1]['annotated_roots']==4 and sidecars[-1]['unsupported_roots']==0
    stats=[];worlds=[]
    for i,(meta,row) in enumerate(zip(selection['selected'],sidecars[:-1])):
        assert row['root_index']==i and row['status']=='ANNOTATED' and row['K']==row['supported_worlds']==4
        assert row['sampling']=='Silver_CardPile_drawTop_public_conditioned_v1'
        oracles=[w['oracle'] for w in row['worlds']];assert [w['k'] for w in row['worlds']]==list(range(4));worlds+=oracles
        assert all(o['supported'] and o['prismatic_shard_absence_proven'] and o['caps']=={'actions_per_replay':1024,'candidates':16,'cycle_length':24,'depth':24,'nodes':2000,'repetitions':128,'total_replay_actions':4096} for o in oracles)
        assert row['candidate_fraction']==sum(bool(o['candidates']) for o in oracles)/4
        assert row['certified_fraction']==sum(o['classification']=='CERTIFIED_KILL' for o in oracles)/4
        stats.append({'decision':meta['decision'],'active':meta['screen']['active_card_count'],'input_sha256':meta['input_sha256'],'public_root_sha256':row['public_root_sha256'],'supported_worlds':4,'classifications':dict(Counter(o['classification'] for o in oracles)),'candidate_fraction':row['candidate_fraction'],'certified_fraction':row['certified_fraction'],'minimum_reach_depth':row['minimum_reach_depth'],'nodes_per_world':[o['nodes'] for o in oracles],'depth_per_world':[o['max_depth'] for o in oracles],'node_cap_worlds':sum(o['node_cap_hit'] for o in oracles),'depth_cap_worlds':sum(o['depth_cap_hit'] for o in oracles),'oracle_cpu_ms':sum(o['cpu_ms'] for o in oracles),'representative_witness':None if not any(o['candidates'] for o in oracles) else 'see oracle.jsonl'})
    assert len(worlds)==16 and all(o['classification']=='NONE' and not o['candidates'] and not o['node_cap_hit'] and not o['depth_cap_hit'] and o['replay_actions']==0 for o in worlds)
    inspection=json.loads((HERE/'manual-root-inspection.json').read_text());assert [r['decision'] for r in inspection]==[r['decision'] for r in selection['selected']]
    inputs=[json.loads(line) for line in (HERE/'inputs.jsonl').read_text().splitlines()]
    for inspected,item in zip(inspection,inputs):
        s=item['public_wire']['state'];assert inspected['player']['energy']==s['player']['energy']
        assert all(m.get('vulnerable',0)==0 for m in s['monsters'] if m['curHp']>0)
        assert 'BASH' in inspected['zones']['drawPile'] and 'POMMEL_STRIKE' in inspected['zones']['drawPile']
    result={'decision':'OOC_COMPRESSION_LEVER_ESTABLISHED','scope':'one historical seed, frozen five-skip space; existence only, not policy quality or prevalence','starting_sha':'13bed5e0060788f58a0138e563877f1e9c312696','runtime_reviewed_sha':selected['reviewed_sha'],'research_binary_sha256':capture['binary_sha256'],'parity':'header+68 states+67 traces EXACT','search_trajectories':32,'new_treatments':31,'single_capture_replay':1,'technical_failures':0,'engine_complete':32,'alive_target':32,'best_mask':'11111','gate_pass':True,'unique_feasible_mask':True,'matched_skips':5,'not_seen':0,'historical_permanent':18,'selected_permanent':14,'historical_minimum_active':16,'selected_minimum_active':selection['minimum_active'],'tier1_roots':selection['tier1_roots'],'public_records':selection['public_roots_captured'],'ordinary_public_roots':selection['ordinary_public_roots'],'selected_roots':4,'annotated_worlds':16,'supported_worlds':16,'candidate_worlds':0,'certified_worlds':0,'node_cap_worlds':0,'depth_cap_worlds':0,'node_cap_rate':0.0,'search_child_cpu_seconds':selected['total_search_child_cpu_seconds'],'capture_child_cpu_seconds':capture['child_user_seconds']+capture['child_system_seconds'],'oracle_child_cpu_seconds':oracle_receipt['child_user_seconds']+oracle_receipt['child_system_seconds'],'oracle_cpu_ms':sum(o['cpu_ms'] for o in worlds),'oracle_total_nodes':sum(o['nodes'] for o in worlds),'oracle_results':stats,'engine_at_entry':choice['target']['state'],'target_combat_exit_hp':36,'natural_near_infinity_established':False,'certified_positive_established':False,'current_policy_prevalence_measured':False,'qualification_not_original_binary':True,'unobserved_full_run_outcomes':None,'witnesses':[],'all_capture_public_state_and_trace_prefixes_exact':True}
    body=['# Selected-mask K=4 annotation','', '| Decision | Active | Worlds | Classification | Candidate / certified | Nodes per world | Max depth per world | Caps | Oracle CPU ms |','|---:|---:|---:|---|---|---|---|---|---:|']
    for r in stats:body.append(f"|{r['decision']}|{r['active']}|4 supported|NONE x4|{r['candidate_fraction']} / {r['certified_fraction']}|{r['nodes_per_world']}|{r['depth_per_world']}|0|{r['oracle_cpu_ms']:.3f}|")
    body+=['',f"Total {len(worlds)} supported worlds, {result['oracle_total_nodes']} nodes, {result['oracle_cpu_ms']:.3f}ms reported oracle CPU; process CPU {result['oracle_child_cpu_seconds']:.6f}s. No candidate, repeated control state, replay action or witness. Reach depths remain null. No budget change.",'','All four selected roots are turn2 with enemy Vulnerable0; Bash and Pommel Strike remain in the public unordered four-card draw pile, while the hand has no draw mechanism. Dropkicks cannot initiate their draw/refund loop in these roots. This is a public-state explanation for the small searched action trees, not a proven absence for the run, other roots or future turns.','', 'The 16 concrete sampled worlds and their draw orders/seeds are retained in oracle.jsonl. Those are independently public-conditioned samples, not the real hidden order.']
    return {'RESULT.json':json.dumps(result,indent=2)+'\n','ORACLE_MATRIX.md':'\n'.join(body)+'\n'}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    for name,body in generate().items():
        if a.check:assert (HERE/name).read_text()==body,name
        else:(HERE/name).write_text(body)
    print('PASS exact capture public-state/trace prefixes, archive/receipt custody,4 roots16 worlds/caps/fractions, report regeneration; no simulator execution')
