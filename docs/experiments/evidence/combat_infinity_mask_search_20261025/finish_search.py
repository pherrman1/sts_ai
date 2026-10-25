#!/usr/bin/env python3
"""Regenerate the exhaustive decision only from sealed receipts and raw prefixes."""
import gzip
import json
from pathlib import Path
from build_runtime import HERE,sha,write
from qualify import difference
from search_logic import assess,locate_stop,control_result,rank,gate


def rows(path):return [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]
def main():
    freeze=json.loads((HERE/'FREEZE.json').read_text());build=json.loads((HERE/'build-result.json').read_text());parity=json.loads((HERE/'parity.json').read_text())
    assert parity['qualification_result']=='FLAG_OFF_PARITY_PASS'
    expected=json.loads(gzip.decompress((HERE.parent/'combat_infinity_reconstruction_20261024/expected-111101032.json.gz').read_bytes()))
    states=rows(HERE/'parity.states.jsonl.gz');trace=rows(HERE/'parity.trace.jsonl.gz')
    assert difference(expected['header'],states[0]) is None
    assert difference(expected['states'],[r for r in states if r.get('type')=='state'][:68]) is None
    assert difference(expected['trace'],trace[:67]) is None
    all_results=[];receipts=[]
    for mask in range(32):
        bits=f'{mask:05b}';manifest_path=HERE/'manifests'/f'{bits}.json';assert sha(manifest_path)==freeze['all_masks_sha256'][bits]
        manifest=json.loads(manifest_path.read_text());result=json.loads((HERE/'results'/f'{bits}.json').read_text());receipt_path=HERE/'runs'/f'{bits}.receipt.json';receipt=json.loads(receipt_path.read_text())
        assert result['status']==receipt['status']=='VALID'
        assert result['receipt_sha256']==sha(receipt_path)
        assert receipt['reviewed_sha']==parity['reviewed_sha'] and receipt['binary_sha256']==build['binary_sha256']
        assert receipt['models']==parity['models']
        if mask==0:
            assert receipt['qualification_reused'] and receipt['manifest_unset']
            regenerated=control_result(manifest,trace)
        else:
            assert receipt['manifest_sha256']==sha(manifest_path)
            raw=rows(HERE/'runs'/f'{bits}.trace.jsonl.gz');raw_states=rows(HERE/'runs'/f'{bits}.states.jsonl.gz')
            for name in ['trace.jsonl','states.jsonl','stdout.log','stderr.log']:
                assert __import__('hashlib').sha256(gzip.decompress((HERE/'runs'/f'{bits}.{name}.gz').read_bytes())).hexdigest()==receipt['files'][name]
            assert difference(expected['header'],raw_states[0]) is None
            endpoint=locate_stop(raw);assert endpoint==receipt['stop_endpoint']
            assert all(r['integrity_so_far'] for r in raw[:endpoint['row']+1] if r.get('kind')=='infinity_mask_boundary')
            if endpoint['kind']=='DEAD':
                footer=[r for r in raw_states if r.get('type')=='outcome'];assert len(footer)==1 and footer[0]['complete'] and footer[0]['integrityPassed']
            regenerated=assess(mask,manifest,raw,endpoint)
            if mask==1:assert receipt['canary_prefix_pass']
        assert difference(result['measurement'],regenerated) is None,(bits,difference(result['measurement'],regenerated))
        all_results.append(regenerated);receipts.append(receipt)
    ordered=sorted(all_results,key=rank);best=ordered[0];feasible=[r['mask'] for r in ordered if gate(r)]
    selection={'reviewed_sha':parity['reviewed_sha'],'all_32_valid':True,'best_mask':best['mask'],'best_result_sha256':sha(HERE/'results'/f"{best['mask']}.json"),'ranking_key':list(rank(best)),'ranking':[r['mask'] for r in ordered],'gate_pass':bool(gate(best)),'feasible_masks':feasible,'ranking_feasibility_discrepancy':bool(feasible and not gate(best)),'engine_complete_count':sum(r['engine_complete'] for r in all_results),'alive_target_count':sum(r['target_alive'] for r in all_results),'total_search_child_cpu_seconds':sum(r['child_user_seconds']+r['child_system_seconds'] for r in receipts),'search_contains_one_parity_control_plus_31_treatments':True,'oracle_used_for_ranking':False,'decision':'SINGLE_SELECTED_CAPTURE_AUTHORIZED' if gate(best) else 'STATIC_SKIP_SEARCH_NO_ENGINE_PRESERVING_COMPRESSION'}
    write(HERE/'SELECTED_MASK.json',selection)
    header=['# Exhaustive five-skip matrix','',f"All32 valid; engine complete {selection['engine_complete_count']}/32; alive first post-engine entry {selection['alive_target_count']}/32. Best **{best['mask']}**, gate **{selection['gate_pass']}**.",'','Masks MSB-left: bit0 Clothesline/f4, bit1 Armaments/f5, bit2 TwinStrike/f10, bit3 Immolate/f12, bit4 Reaper/f16. E=enabled, M=matched, N=not seen. Permanent sizes are not combat active pools. CPU includes parity work for mask00000. Every measurement clips at the frozen stop; later outcomes are excluded.','', '| Mask | E/M/N | Stop/floor | Alive | Pandora obtained / pair produced | Dropkick/Bash/Pommel | Engine | Deck at completion | First target | Entry deck/HP | CPU s |','|---|---|---|---|---|---|---|---|---|---|---|']
    for row,receipt in zip(all_results,receipts):
        t=row['target'];p=row['pandora_choice'];target=f"a{t['act']}/f{t['floor']}/fight{t['fight']} {t['encounter']}" if t else '—'
        header.append(f"|{row['mask']}|{row['enabled_skip_count']}/{row['matched']}/{row['not_seen']}|{row['stop']} f{row['highest_floor']}|{row['alive']}|{row['pandora_obtained']} / {p['dropkicks_produced'] if p else 0}|{row['dropkicks']}/{int(row['bash_present'])}/{int(row['pommel_present'])}|{row['engine_complete']}|{row['permanent_deck_at_engine_completion']}|{target}|{row['target_deck_size']}/{row['target_hp']}|{receipt['child_user_seconds']+receipt['child_system_seconds']:.3f}|")
    header+=['',f"Frozen rank: {', '.join(selection['ranking'])}.",'',f"Total child CPU: {selection['total_search_child_cpu_seconds']:.3f}s. Correlated variants of one seed; existence/search only."]
    (HERE/'MATRIX.md').write_text('\n'.join(header)+'\n')
    write(HERE/'regenerated-checks.json',{'all_32_measurements_match_raw':True,'all_32_receipts_and_manifests_verified':True,'raw_archive_hashes_match_receipts':True,'parity_header_states68_traces67_exact':True,'prefix_health_valid':True,'production_oracle_execution_during_search':False,'selected_mask_sha256':sha(HERE/'SELECTED_MASK.json'),'matrix_sha256':sha(HERE/'MATRIX.md')})
    print(json.dumps(selection,indent=2))
if __name__=='__main__':main()
