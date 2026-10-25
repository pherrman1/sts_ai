#!/usr/bin/env python3
"""Regenerate custody/fidelity and K=4 reporting from retained bytes only."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDS = [111101032, 111101326, 111101512]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name):
    return json.loads((HERE / name).read_text())


def raw(seed, name):
    body = gzip.decompress((HERE / f'capture-{seed}.{name}.gz').read_bytes())
    assert sha(body) == load(f'replay-{seed}.json')['files'][name]
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    build = load('build-result.json')
    assert build['binary_sha256'] == build['expected_sha256'] == '0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52'
    assert build['source_sha'] == 'd8fd2a105a8d2a481b7639e26c683f75e382e3d4'
    assert not build['source_patched']
    caps = {'depth': 24, 'cycle_length': 24, 'nodes': 2000, 'candidates': 16,
            'repetitions': 128, 'actions_per_replay': 1024, 'total_replay_actions': 4096}
    rows, runs, witnesses = [], [], []
    for seed in SEEDS:
        replay = load(f'replay-{seed}.json')
        selection_bytes = (HERE / f'selection-{seed}.json').read_bytes()
        selection = json.loads(selection_bytes)
        assert replay['status'] == 'CHECKPOINT_IDENTICAL' and replay['header_match']
        expected_path = HERE / replay['frozen_prefix']['expected_file']
        assert sha(expected_path.read_bytes()) == replay['frozen_prefix']['expected_sha256']
        expected = json.loads(gzip.decompress(expected_path.read_bytes()))
        states = [json.loads(x) for x in raw(seed, 'states.jsonl').splitlines()]
        trace = [json.loads(x) for x in raw(seed, 'trace.jsonl').splitlines()]
        public = [json.loads(x) for x in raw(seed, 'public.jsonl').splitlines()]
        assert states[0] == expected['header']
        actual_states = [r for r in states if r.get('type') == 'state']
        assert actual_states[:len(expected['states'])] == expected['states']
        assert trace[:len(expected['trace'])] == expected['trace']
        assert replay['state_matches'] == len(expected['states'])
        assert replay['trace_matches'] == len(expected['trace'])
        assert selection['receipt_sha256'] == sha((HERE / f'replay-{seed}.json').read_bytes())
        assert selection['public_roots_captured'] == len(public)
        assert selection['no_prismatic_shard_proven'] and 'PRISMATIC_SHARD' not in selection['full_run_relics']
        target = trace[replay['frozen_prefix']['last_trace_index']]
        assert target['pre']['relics'] == selection['full_run_relics']
        assert target['pre']['deck'] == selection['run_deck_before_fight']
        inputs_bytes = (HERE / f'inputs-{seed}.jsonl').read_bytes()
        inputs = [json.loads(x) for x in inputs_bytes.splitlines()]
        assert sha(inputs_bytes) == selection['inputs_sha256']
        receipt = load(f'oracle-{seed}.receipt.json')
        assert receipt['selection_sha256'] == sha(selection_bytes)
        output = (HERE / f'oracle-{seed}.jsonl').read_bytes()
        assert receipt['output_sha256'] == sha(output) and receipt['returncode'] == 0
        assert receipt['stderr_sha256'] == sha((HERE / f'oracle-{seed}.stderr.txt').read_bytes())
        assert not (HERE / f'oracle-{seed}.stderr.txt').read_bytes()
        result = [json.loads(x) for x in output.splitlines()]
        assert len(result) == len(inputs) + 1 and len(inputs) <= 4
        assert result[-1]['roots'] == len(inputs) and result[-1]['root_cap'] == 4
        for index, (item, selected, sidecar) in enumerate(zip(inputs, selection['selected'], result[:-1])):
            assert sha(json.dumps(item, sort_keys=True).encode()) == selected['input_sha256']
            source = next(r for r in public if r['decision'] == selected['decision'])
            wire = json.loads(json.dumps(source['public_wire']))
            wire['state']['isolatedSearchSeed'] = 0
            wire['state']['observedGeneration'] = 0
            assert item == {'public_wire': wire, 'oracle_no_prismatic_shard': True}
            s = wire['state']
            assert not s['fullDrawOrderObserved'] and not s['drawPile']['fullOrderObserved']
            assert sidecar['K'] == 4 and sidecar['root_index'] == index
            worlds = sidecar['worlds']
            assert len(worlds) == 4
            for k, world in enumerate(worlds):
                digest = sha(f"combat-infinity-public-world-v1:{sidecar['public_root_sha256']}:{k}".encode())
                assert world['sample_seed'] == str(int(digest[:16], 16)) and world['k'] == k
                physical = sorted((c['id'], c['uniqueId']) for z in ('knownTop', 'unknown', 'knownBottom') for c in s['drawPile'][z])
                assert sorted((c['id'], c['physical_id']) for c in world['sampled_draw_bottom_first']) == physical
                assert world['oracle']['caps'] == caps
                oracle = world['oracle']
                assert oracle['nodes'] <= 2000 and oracle['max_depth'] <= 24
                assert len(oracle['candidates']) <= 16 and oracle['replay_actions'] <= 4096
            search = [w['oracle'] for w in worlds]
            candidates = [c for o in search for c in o['candidates'] if c['classification'] != 'STALL_LOOP']
            supported = sum(o['supported'] for o in search)
            certified = sum(o['classification'] == 'CERTIFIED_KILL' for o in search)
            candidate_worlds = sum(any(c['classification'] != 'STALL_LOOP' for c in o['candidates']) for o in search)
            assert sidecar['supported_worlds'] == supported
            if sidecar['status'] == 'ANNOTATED':
                assert supported == 4 and sidecar['certified_fraction'] == certified / 4
                assert sidecar['candidate_fraction'] == candidate_worlds / 4
            else:
                assert sidecar['certified_fraction'] is None and sidecar['candidate_fraction'] is None
            row = {'seed': seed, 'fight': selection['fight']['fight'], 'encounter': selection['fight']['encounter'],
                   'decision': selected['decision'], 'turn': selected['turn'], 'tier': selected['tier'],
                   'active_cards': selected['screen']['active_card_count'],
                   'ingredient_class': selected['screen']['reasons'], 'status': sidecar['status'],
                   'supported_samples': supported, 'candidate_samples': candidate_worlds, 'certified_samples': certified,
                   'candidate_fraction': sidecar['candidate_fraction'], 'certified_fraction': sidecar['certified_fraction'],
                   'minimum_reach_depth': sidecar['minimum_reach_depth'],
                   'classifications': dict(Counter(o['classification'] for o in search)),
                   'node_cap_worlds': sum(o['node_cap_hit'] for o in search),
                   'depth_cap_worlds': sum(o['depth_cap_hit'] for o in search),
                   'nodes_min': min(o['nodes'] for o in search), 'nodes_max': max(o['nodes'] for o in search),
                   'nodes_total': sum(o['nodes'] for o in search), 'max_depth': max(o['max_depth'] for o in search),
                   'cpu_ms': round(sum(o['cpu_ms'] for o in search), 3),
                   'replay_actions': sum(o['replay_actions'] for o in search),
                   'interpretation': 'INCONCLUSIVE_NODE_CAP' if any(o['node_cap_hit'] for o in search) else 'NO_CANDIDATE_IN_BOUNDED_SEARCH_NOT_PROVEN_ABSENCE',
                   'distinct_draw_orders': len({json.dumps(w['sampled_draw_bottom_first'], sort_keys=True) for w in worlds}),
                   'representative_witness': next(iter(candidates), None),
                   'input_sha256': selected['input_sha256'], 'public_root_sha256': sidecar['public_root_sha256']}
            rows.append(row)
            witnesses.extend({'seed': seed, 'decision': selected['decision'], 'candidate': c} for c in candidates)
        runs.append({'seed': seed, 'runtime': replay['runtime_identity'], 'fidelity': replay['status'],
                     'states_matched': replay['state_matches'], 'traces_matched': replay['trace_matches'],
                     'first_divergence': replay['first_difference'], 'target': selection['fight'],
                     'public_roots': len(public), 'ordinary_roots': selection['ordinary_public_roots'],
                     'tier1_roots': selection['tier1_roots'], 'tier2_roots': selection['tier2_roots'],
                     'active_min': min((r['screen']['active_card_count'] for r in selection['all_roots'] if 'screen' in r), default=None),
                     'active_max': max((r['screen']['active_card_count'] for r in selection['all_roots'] if 'screen' in r), default=None),
                     'selected_roots': len(inputs), 'replay_wall_seconds': replay['wall_seconds'],
                     'replay_cpu_seconds': replay['child_user_seconds'] + replay['child_system_seconds']})
    summary = {'runtime_conclusion': 'EXACT_RUNTIME_RECOVERED', 'runs_attempted': len(runs),
               'ingredient_fights_reproduced': len(runs), 'public_roots_captured': sum(r['public_roots'] for r in runs),
               'ordinary_roots': sum(r['ordinary_roots'] for r in runs),
               'tier1_roots': sum(r['tier1_roots'] for r in runs), 'tier2_roots': sum(r['tier2_roots'] for r in runs),
               'selected_roots': len(rows), 'eligible_annotated_roots': sum(r['status'] == 'ANNOTATED' for r in rows),
               'annotated_worlds': sum(r['supported_samples'] for r in rows),
               'candidate_worlds': sum(r['candidate_samples'] for r in rows),
               'certified_worlds': sum(r['certified_samples'] for r in rows),
               'node_cap_worlds': sum(r['node_cap_worlds'] for r in rows),
               'depth_cap_worlds': sum(r['depth_cap_worlds'] for r in rows),
               'nodes_total': sum(r['nodes_total'] for r in rows), 'cpu_ms': round(sum(r['cpu_ms'] for r in rows), 3),
               'runs': runs}
    summary['node_cap_rate'] = summary['node_cap_worlds'] / summary['annotated_worlds'] if summary['annotated_worlds'] else None
    # This packet's observed stopping decision, not a general negative-label rule.
    assert not witnesses and summary['tier1_roots'] == 0 and all(r['active_min'] > 8 for r in runs)
    summary['scientific_conclusion'] = 'NO_NEAR_INFINITY_STATE_OBSERVED'
    summary['classification_disagreement_roots'] = sum(len(r['classifications']) > 1 for r in rows)
    summary['draw_order_disagreement_roots'] = sum(r['distinct_draw_orders'] > 1 for r in rows)
    lines = ['# Frozen Heart targeted annotation matrix', '',
             'K=4. NONE is a bounded result, never a proven absence; caps remain inconclusive.', '',
             '| Seed | Fight | Decision | Turn | Tier | Active | Supported | Certified / candidate | Nodes/world | Depth | Node / depth caps | CPU ms | Reach / witness |',
             '|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---:|---|']
    for r in rows:
        lines.append(f"| {r['seed']} | {r['encounter']} | {r['decision']} | {r['turn']} | {r['tier']} | {r['active_cards']} | {r['supported_samples']}/4 | {r['certified_fraction']} / {r['candidate_fraction']} | {r['nodes_min']}–{r['nodes_max']} | {r['max_depth']} | {r['node_cap_worlds']} / {r['depth_cap_worlds']} | {r['cpu_ms']:.3f} | {r['minimum_reach_depth']} / {'none' if r['representative_witness'] is None else 'see sidecar'} |")
    outputs = {'RESULT.json': json.dumps(summary, indent=2) + '\n',
               'expanded-sidecars.json': json.dumps(rows, indent=2) + '\n',
               'witnesses.json': json.dumps(witnesses, indent=2) + '\n', 'MATRIX.md': '\n'.join(lines) + '\n'}
    for name, body in outputs.items():
        if args.check:
            assert (HERE / name).read_text() == body, name
        else:
            (HERE / name).write_text(body)
    print('PASS exact runtime, full frozen-prefix fidelity, same-run no-Shard custody, public sampling, K=4 bounds and regenerated matrix; no seed/world execution')


if __name__ == '__main__':
    main()
