#!/usr/bin/env python3
"""Validate archived experiment evidence and regenerate tables; never launches seeds."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from build_runtime import HERE, REPO, sha

BASE=HERE.parent/'combat_infinity_reconstruction_20261024'
def load(path):return json.loads(path.read_text())
def raw(label,name):
    receipt=load(HERE/f'{label}.json')
    body=gzip.decompress((HERE/f'{label}.{name}.gz').read_bytes())
    assert hashlib.sha256(body).hexdigest()==receipt['files'][name]
    return [json.loads(x) for x in body.splitlines()] if name.endswith('.jsonl') else body

def generate():
    parity=load(HERE/'parity.json');expected=load_gzip(BASE/'expected-111101326.json.gz')
    assert parity['qualification_result']=='FLAG_OFF_PARITY_PASS' and parity['first_difference'] is None
    states=raw('parity','states.jsonl');trace=raw('parity','trace.jsonl')
    assert states[0]==expected['header']
    assert [r for r in states if r.get('type')=='state'][:137]==expected['states']
    assert trace[:136]==expected['trace'] and parity['state_matches']==137 and parity['trace_matches']==136
    treatment=load(HERE/'treatment.json');build=load(HERE/'build-result.json')
    assert treatment['status']=='COMPLETED' and treatment['returncode']==0
    assert treatment['binary_sha256']==parity['binary_sha256']==build['binary_sha256']
    assert treatment['reviewed_sha']==parity['reviewed_sha']=='06119a587009844c427339a1e5c93c60ca3998c8'
    manifest=load(HERE.parent/'combat_infinity_compression_20261024/INTERVENTIONS.json')
    assert treatment['manifest_sha256']==build['manifest_sha256']==sha(HERE.parent/'combat_infinity_compression_20261024/INTERVENTIONS.json')
    review=load(HERE/'independent-review.json')
    assert review['outcome']=='PASS'
    for p,h in review['files_sha256'].items():
        reviewed_bytes=subprocess.check_output(['git','show',review['reviewed_sha']+':'+str((HERE/p).relative_to(REPO))],cwd=REPO)
        assert hashlib.sha256(reviewed_bytes).hexdigest()==h
        if p!='measure.py':assert sha(HERE/p)==h
    # measure.py received an offline shop name/price parsing correction only.
    # The frozen executable/qualifier/treatment and all raw run bytes are unchanged.
    trace=raw('treatment','trace.jsonl');states=raw('treatment','states.jsonl')
    assert states[-1]['type']=='outcome' and states[-1]['complete'] and states[-1]['integrityPassed']
    assert [states[-1]]==treatment['outcomes']
    summary=[r for r in trace if r.get('kind')=='infinity_skip_summary']
    assert summary==treatment['summary'] and len(summary)==1;summary=summary[0]
    statuses=summary['entries'];assert len(statuses)==13 and summary['failed']==0
    assert [{k:v for k,v in r.items() if k not in ['status','error']} for r in statuses]==manifest['interventions']
    assert all(r['status'] in ['MATCHED_EXECUTED','NOT_SEEN'] for r in statuses)
    fired=[r for r in trace if r.get('by')=='infinity_skip']
    assert len(fired)==summary['matched']==sum(r['status']=='MATCHED_EXECUTED' for r in statuses)
    assert summary['matched']+summary['not_seen']==13
    measurements=load(HERE/'measurements.json')
    assert measurements['treatment_receipt_sha256']==sha(HERE/'treatment.json')
    assert len(measurements['post_skip_measurements'])==len(fired)
    for entry in statuses:
        matches=[r for r in fired if r['pre']['act']==entry['act'] and r['pre']['floor']==entry['floor']]
        assert len(matches)==(1 if entry['status']=='MATCHED_EXECUTED' else 0)
        for row in matches:
            assert row['pre']['deck']==row['post']['deck'],'skip must not add/remove permanent cards'
            historical=expected['trace'][entry['original_trace_index']]
            assert any(sorted(group)==sorted(histgroup) for group in row['offer']['cards'] for histgroup in historical['offer']['cards'])
    result={'starting_sha':'5adfd78bfb32580ac49eca4a4c8f52498be08653','reviewed_runtime_sha':parity['reviewed_sha'],'patched_binary_sha256':build['binary_sha256'],'patch_sha256':build['patch_sha256'],'flag_off_parity':{'status':parity['qualification_result'],'header_match':parity['header_match'],'states':137,'traces':136,'first_difference':None,'wall_seconds':parity['wall_seconds'],'cpu_seconds':parity['child_user_seconds']+parity['child_system_seconds']},'treatment':{'status':treatment['status'],'wall_seconds':treatment['wall_seconds'],'cpu_seconds':treatment['child_user_seconds']+treatment['child_system_seconds'],'outcomes':treatment['outcomes']},'triggers':statuses,'matched':summary['matched'],'not_seen':summary['not_seen'],'highest_floor':measurements['highest_floor'],'final_public_state':measurements['final_public_state'],'engine_maximum_owned':measurements['maximum_owned_engine'],'engine_completion':measurements['engine_completion'],'target':measurements['first_subsequent_combat'],'historical_permanent_deck':31,'historical_minimum_active':30,'counterfactual_minimum_active':None,'public_roots':0,'tier1_roots':None,'selected_roots':0,'annotated_worlds':0,'node_cap_worlds':0,'node_cap_rate':None,'oracle_rows':[],'witnesses':[],'candidate_fraction':None,'certified_fraction':None,'minimum_reach_depth':None}
    if result['engine_completion'] is None:
        assert not (HERE/'capture.json').exists() and not (HERE/'oracle.jsonl').exists()
        result['decision_labels']=['COMPRESSION_SURVIVAL_TRADEOFF']
        result['annotation_status']='NOT_REACHED_ENGINE_NEVER_COMPLETED; not an oracle-negative result'
    elif not (HERE/'oracle.jsonl').exists():
        raise AssertionError('engine completed: capture/selection/annotation path not finished')
    else:
        capture=load(HERE/'capture.json');assert capture['status']=='COMPLETED' and capture['first_difference'] is None
        assert raw('capture','states.jsonl')==states and raw('capture','trace.jsonl')==trace
        selection=load(HERE/'selection.json');inputs=(HERE/'inputs.jsonl').read_bytes()
        assert sha(HERE/'inputs.jsonl')==selection['inputs_sha256']
        receipt=load(HERE/'oracle.receipt.json');assert receipt['returncode']==0 and receipt['selection_sha256']==sha(HERE/'selection.json')
        assert receipt['output_sha256']==sha(HERE/'oracle.jsonl') and receipt['inputs_sha256']==selection['inputs_sha256']
        assert receipt['adapter_binary_sha256']==selection['oracle_binary_sha256']=='28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9'
        output=[json.loads(x) for x in (HERE/'oracle.jsonl').read_text().splitlines()]
        assert len(output)==len(selection['selected'])+1
        for chosen,sidecar in zip(selection['selected'],output[:-1]):
            assert sidecar['K']==4
            worlds=sidecar['worlds'];assert len(worlds)==4
            for world in worlds:
                oracle=world['oracle'];assert oracle['nodes']<=2000 and oracle['max_depth']<=24 and oracle['replay_actions']<=4096
                assert oracle['caps']=={'depth':24,'cycle_length':24,'nodes':2000,'candidates':16,'repetitions':128,'actions_per_replay':1024,'total_replay_actions':4096}
            candidates=[c for world in worlds for c in world['oracle']['candidates'] if c['classification']!='STALL_LOOP']
            row={'decision':chosen['decision'],'turn':chosen['turn'],'active_cards':chosen['screen']['active_card_count'],'tier1':chosen['tier1'],'input_sha256':chosen['input_sha256'],'public_root_sha256':sidecar['public_root_sha256'],'status':sidecar['status'],'supported_samples':sidecar['supported_worlds'],'candidate_fraction':sidecar['candidate_fraction'],'certified_fraction':sidecar['certified_fraction'],'minimum_reach_depth':sidecar['minimum_reach_depth'],'classifications':dict(Counter(w['oracle']['classification'] for w in worlds)),'node_cap_worlds':sum(w['oracle']['node_cap_hit'] for w in worlds),'nodes':[w['oracle']['nodes'] for w in worlds],'max_depth':[w['oracle']['max_depth'] for w in worlds],'cpu_ms':sum(w['oracle']['cpu_ms'] for w in worlds),'candidates':candidates}
            result['oracle_rows'].append(row);result['witnesses'].extend(candidates)
        result.update({'counterfactual_minimum_active':selection['minimum_active'],'public_roots':selection['public_roots_captured'],'tier1_roots':selection['tier1_roots'],'selected_roots':len(selection['selected']),'annotated_worlds':sum(r['supported_samples'] for r in result['oracle_rows']),'node_cap_worlds':sum(r['node_cap_worlds'] for r in result['oracle_rows']),'capture_wall_seconds':capture['wall_seconds'],'capture_cpu_seconds':capture['child_user_seconds']+capture['child_system_seconds']})
        result['node_cap_rate']=result['node_cap_worlds']/result['annotated_worlds'] if result['annotated_worlds'] else None
        labels=[];active=selection['minimum_active']
        if active<=12 or 30-active>=6:labels.append('OOC_COMPRESSION_LEVER_ESTABLISHED')
        if any((r['certified_fraction'] or 0)>0 for r in result['oracle_rows']):labels.append('NATURAL_POSITIVE_ESTABLISHED')
        elif result['witnesses']:labels.append('NATURAL_NEAR_INFINITY_ESTABLISHED')
        elif active<30:labels.append('COMPRESSION_IMPROVES_BUT_NOT_ENOUGH')
        else:labels.append('COUNTERFACTUAL_NO_EFFECT')
        result['decision_labels']=labels;result['annotation_status']='bounded diagnostic; NONE/cap hits are not negative labels'
    result['runs']={'flag_off_qualification':1,'treatment':1,'capture_only_replay':int((HERE/'capture.json').exists())}
    triggers=['| Act | Floor | Historical decision (audit only) | Historical card | Status |','|---:|---:|---:|---|---|']
    for row in statuses:triggers.append(f"| {row['act']} | {row['floor']} | {row['original_ooc_decision']} | {row['historical_acquisition']} | {row['status']} |")
    matrix=['| Decision | Active | Tier1 | Supported/K | Candidate fraction | Certified fraction | Reach | Node caps | Nodes | Max depths | CPU ms |','|---:|---:|---|---|---|---|---|---:|---|---|---:|']
    for r in result['oracle_rows']:matrix.append(f"| {r['decision']} | {r['active_cards']} | {r['tier1']} | {r['supported_samples']}/4 | {r['candidate_fraction']} | {r['certified_fraction']} | {r['minimum_reach_depth']} | {r['node_cap_worlds']} | {r['nodes']} | {r['max_depth']} | {r['cpu_ms']:.3f} |")
    if not result['oracle_rows']:matrix=['Oracle not executed: engine never completed. Zero captured/selected/annotated public combat roots/worlds. Fractions and active-pool comparison are unavailable, not negative labels.']
    return {'RESULT.json':json.dumps(result,indent=2)+'\n','TRIGGERS.md':'\n'.join(triggers)+'\n','MATRIX.md':'\n'.join(matrix)+'\n'}

def load_gzip(path):return json.loads(gzip.decompress(path.read_bytes()))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for name,body in generate().items():
        if args.check:assert (HERE/name).read_text()==body,name
        else:(HERE/name).write_text(body)
    print('PASS raw custody, complete exact flag-off prefix, frozen13 statuses/accounting, actual measurements and conditional oracle tables; no seed/world execution')
