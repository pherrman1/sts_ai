#!/usr/bin/env python3
"""Offline whole-study summary; never execute gameplay or an oracle."""
import argparse
from collections import Counter
import json
from stage_a import HERE, PIN, BASELINE, BINARY_HASH, dump, sha
from report import generate


def study():
    combat_rows=[]
    ambiguities=[]
    for fight,folder in ((11,HERE),(12,HERE/'combat12'),(13,HERE/'combat13')):
        if not (folder/'RESULT.json').exists():
            continue
        for name,body in generate(folder).items():
            assert (folder/name).read_text()==body
        r=json.loads((folder/'RESULT.json').read_text());f=json.loads((folder/'FREEZE.json').read_text())
        for root in r['roots']:
            if root['cap_worlds'] or root['unsupported_worlds']:
                ambiguities.append(dict(fight=fight,decision=root['decision'],turn=root['turn'],
                    active_pool=root['active_pool'],enemy_hp=root['enemy_hp'],enemy_vulnerable=root['enemy_vulnerable'],
                    nodes=root['nodes'],max_depth=root['max_depth'],cap_worlds=root['cap_worlds'],
                    unsupported_worlds=root['unsupported_worlds'],hand=root['zones']['hand'],
                    ingredient_locations=root['ingredient_locations']))
        entry=f['combat_entry']
        combat_rows.append(dict(fight=fight,encounter=('SHELL_PARASITE' if fight==11 else f['capture_receipt']['latest_boundary'].get('encounter','')),
            act=entry['act'],floor=entry['floor'],entry_hp=entry['hp'],exit_hp=f['combat_exit']['hp'],
            deck=entry['deck'],relics=entry['relics'],permanent_deck_size=r['permanent_deck_size'],cycle_burden=r['cycle_burden'],
            label=r['label'],counts=r['counts'],result_sha256=sha((folder/'RESULT.json').read_bytes())))
        if fight!=11:
            # The receipt may stop at the following fight; identify this fight from raw capture.
            import gzip
            trace=[json.loads(v) for v in gzip.decompress((HERE/f'capture{fight}.trace.jsonl.gz').read_bytes()).splitlines()]
            combat_rows[-1]['encounter']=next(v['encounter'] for v in trace if v.get('kind')=='battle' and v['fight']==fight)
    assert combat_rows
    labels=[c['label'] for c in combat_rows]
    if 'NATURAL_POSITIVE_ESTABLISHED' in labels:
        stop='NATURAL_POSITIVE_ESTABLISHED'
    elif 'NATURAL_NEAR_INFINITY_ESTABLISHED' in labels:
        stop='NATURAL_NEAR_INFINITY_ESTABLISHED'
    elif 'TARGET_COMBAT_INCONCLUSIVE' in labels:
        stop='TARGET_COMBAT_INCONCLUSIVE'
    elif len(combat_rows)==3:
        stop='COMPRESSION_WITHOUT_INFINITY_SIGNAL'
    else:
        stop='BOUNDED_STUDY_INCOMPLETE'
    changes=[]
    for a,b in zip(combat_rows,combat_rows[1:]):
        old,new=Counter(a['deck']),Counter(b['deck'])
        added,removed=new-old,old-new
        upgrades=[]
        for old_name,n in list(removed.items()):
            upgraded=old_name+'+'
            k=min(n,added[upgraded])
            if k:
                upgrades.append(dict(before=old_name,after=upgraded,count=k))
                removed[old_name]-=k;added[upgraded]-=k
        changes.append(dict(from_fight=a['fight'],to_fight=b['fight'],added_cards=dict(+added),removed_cards=dict(+removed),upgrades=upgrades,
            added_relics=sorted(set(b['relics'])-set(a['relics'])),removed_relics=sorted(set(a['relics'])-set(b['relics']))))
    result=dict(stopping_label=stop,baseline_sha=BASELINE,pinned_844_sha=PIN,oracle_binary_sha256=BINARY_HASH,
                combats=combat_rows,inventory_changes=changes,ambiguities=ambiguities,
                total_ordinary_roots=sum(c['counts']['ordinary_roots'] for c in combat_rows),
                total_supported_worlds=sum(c['counts']['supported_worlds'] for c in combat_rows),
                total_node_visits=sum(c['counts']['total_nodes'] for c in combat_rows),
                source_artifacts=json.loads((HERE/'FREEZE.json').read_text())['source_artifacts'],
                full_run_outcomes=None,current_policy_prevalence=None,training_negatives_created=False,
                knowledge_impact='experiment ledger and maintained current-research status; no production/default change')
    if (HERE/'capture13.trace.jsonl.gz').exists():
        import gzip
        raw_trace=[json.loads(v) for v in gzip.decompress((HERE/'capture13.trace.jsonl.gz').read_bytes()).splitlines()]
        at=next(i for i,v in enumerate(raw_trace) if v.get('kind')=='battle' and v['fight']==13)
        tail=raw_trace[at+1:]
        result['stop_monitor_tail']=dict(records=len(tail),ordinary_ooc_actions=sum(v.get('kind')=='ooc' for v in tail),
                                       additional_completed_combats=sum(v.get('kind')=='battle' for v in tail))
    md=['# Natural trajectory exhaustive infinity study', '', '**'+stop+'**', '',
        'Baseline: `'+BASELINE+'`. Historical #844 is read-only at `'+PIN+'`; #863 is unchanged. '
        'This is one deterministic counterfactual trajectory, not a prevalence or gameplay-quality study.', '',
        '|Combat|Act/floor|Entry HP|Permanent cards|Cycle burden|Min active|Ordinary roots|Vulnerable|Dropkick in hand|Bash in hand|Pommel in hand|Candidate / certified roots|Cap / unsupported worlds|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|']
    for c in combat_rows:
        n=c['counts']
        md.append('|'+ '|'.join(map(str,[f"{c['fight']} {c['encounter']}",f"{c['act']}/{c['floor']}",c['entry_hp'],c['permanent_deck_size'],c['cycle_burden'],
            n['minimum_active_pool'],n['ordinary_roots'],n['vulnerable_roots'],n['dropkick_in_hand_roots'],n['bash_in_hand_roots'],n['pommel_strike_in_hand_roots'],
            f"{n['candidate_roots']} / {n['certified_roots']}",f"{n['cap_worlds']} / {n['unsupported_worlds']}"]))+'|')
    md+=['', 'Stage A: all 21 ordinary Shell Parasite roots were frozen before oracle execution; 84 supported worlds, '
         '1,954 nodes, maximum depth 6, no candidates, certifications or caps. Its clean-NONE gate alone authorized Stage B.', '',
         'Unchanged oracle/adapter executable SHA256: `'+BINARY_HASH+'`. K4 / depth24 / nodes2000 / candidates16 / periods128 / '
         'actions1024 / total replay4096. All commands, sampled world seeds/orders, nodes, depths, cap flags, raw sidecars and '
         'custody receipts are retained. A NONE row is never a training negative.', '',
         'Pinned #844 adapter source (`apps/combat_infinity_oracle.cpp`) SHA256: `'+json.loads((HERE/'FREEZE.json').read_text())['oracle_source_sha256']+'`. '
         'The public adapter is retained from that historical branch; it is not silently substituted by the baseline main executable.', '',
         'Full matrices: [Shell Parasite](MATRIX.md), [Chosen](combat12/MATRIX.md), [third combat](combat13/MATRIX.md). '
         'RESULT.json in each folder includes hand/draw identities and physical IDs, Dropkick/Bash/Pommel locations, '
         'fractions, reach depth and witnesses. Freeze files retain every root before annotation.', '',
         'Inventory changes between combat entries:', '', '```json',dump(changes).strip(),'```', '',
         'Exact #844 source artifact identities (SHA256):', '', '|Artifact|Compressed|Decompressed|', '|---|---|---|']
    for name,a in result['source_artifacts'].items():
        md.append(f"|{name}|`{a['compressed_sha256']}`|`{a['decompressed_sha256']}`|")
    if stop=='TARGET_COMBAT_INCONCLUSIVE':
        md += ['', 'The exact decision-critical ambiguity is retained below. No candidate was observed, but a capped search '
               'cannot establish clean absence. Do not assign COMPRESSION_WITHOUT_INFINITY_SIGNAL, use these rows as training negatives, '
               'or increase bounds automatically.', '', '```json',dump(ambiguities).strip(),'```', '',
               'Slavers decision 11 has enemy Vulnerable, both Pommels and Shrug It Off in hand, one Dropkick in the draw bag '
               'and the other in discard. Seven Wounds are already in discard. Its 2,000-node cap in all four worlds can '
               'hide a relevant continuation; the shallow NONE explanation from the four original minimum-active roots '
               'does not discharge this ambiguity. Ingredient/reachability model work remains unauthorized by this result.']
    md+=['', 'The retained gameplay binary is `2b317b0533d0c834da268ddff03d087b271b9a950b26dde303437df7cc10cba9`, '
         'from historical d8fd2a105a8d2a481b7639e26c683f75e382e3d4 plus the previously qualified five-skip patch. '
         'It is byte-identical to #844\'s research runtime, with eight hash-matched historical models, including Student-C '
         '`eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`. '
         'No production/runtime rebuild was needed. Stage-B launch/receipt files bind source/model custody and complete replay-prefix equality.', '',
         'The binary accepts one capture floor per launch. A bounded discovery replay identifies the next entry; targeted '
         'replays recapture that unchanged trajectory. These passes are not independent experimental trajectories. '
         'The monitor terminates the exact process group at the observation boundary; a SIGTERM return is intentional. '
         'No fourth combat is part of the study.', '',
         'Stop-monitor deviation: before the polling wrapper terminated capture13, the simulator emitted two ordinary '
         'floor-24 reward-screen actions after the Slavers battle record (five trace records including boundaries). '
         'No fourth combat was entered or completed. Those reward actions are retained in raw evidence but do not '
         'affect combat-entry inventories, root selection, annotation, or interpretation.', '',
         'Reporting metadata: STAGE_A_GATE_AT_FIRST_LAUNCH.json retains the original hash-bound gate report. '
         'The later RESULT.json adds zero-valued cap-root and unsupported-root totals; labels/raw evidence did not change.', '',
         'Knowledge impact: experiment ledger and maintained current-research status. No training, beam, planner, model, '
         'threshold, oracle-bound or production-default change. Full-run outcomes and current-policy prevalence are unobserved.']
    if stop=='COMPRESSION_WITHOUT_INFINITY_SIGNAL':
        md += ['', 'The three-combat horizon has no candidate in any supported sampled world and no cap/unsupported ambiguity. '
               'The historical 18→14 / active16→9 compression is real, but it did not produce the desired loop in this bounded trajectory. '
               'Natural subsequent choices changed the deck; these data do not isolate compression alone as a causal treatment. '
               'Do not build generic compression beam search from this result. The next hypothesis is ingredient/reachability-aware '
               'infinity potential; no such model is implemented here. This is bounded absence at the fixed oracle settings, '
               'not exhaustive hidden-world absence or a general claim that compressed decks cannot loop.']
    return {'STUDY.json':dump(result),'REPORT.md':'\n'.join(md)+'\n'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    for name,body in study().items():
        if a.check:
            assert (HERE/name).read_text()==body
        else:
            (HERE/name).write_text(body)
    print(json.loads((HERE/'STUDY.json').read_text())['stopping_label'])
