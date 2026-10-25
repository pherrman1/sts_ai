#!/usr/bin/env python3
"""Freeze qualified public roots with the existing ingredient screen; no oracle."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RUNTIME = REPO / 'build/infinity-heart-runtime-20261024'
spec = importlib.util.spec_from_file_location('frozen_screen', HERE.parent / 'combat_infinity_hunt_20261024/screen_rules.py')
screen_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen_module)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def table(path, symbol):
    text = (RUNTIME / 'source' / path).read_text()
    start = text.index(symbol)
    return re.findall(r'"([A-Z_0-9]+)"', text[start:text.index('};', start)])


def zone(value):
    if isinstance(value, list):
        return value
    return [c for key in ('knownTop', 'unknown', 'knownBottom') for c in value.get(key, [])]


def generate(seed):
    run = RUNTIME / f'run-{seed}'
    receipt_bytes = (run / 'receipt.json').read_bytes()
    receipt = json.loads(receipt_bytes)
    assert receipt['status'] == 'CHECKPOINT_IDENTICAL' and not receipt['capture_quarantined']
    for name in ['public.jsonl', 'trace.jsonl', 'states.jsonl']:
        assert sha((run / name).read_bytes()) == receipt['files'][name]
    trace = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
    target = receipt['frozen_prefix']['target']
    battle = trace[receipt['frozen_prefix']['last_trace_index']]
    assert battle['kind'] == 'battle' and battle['fight'] == target['fight']
    relics = battle['pre']['relics']
    assert 'PRISMATIC_SHARD' not in relics
    cards = table('include/constants/Cards.h', 'cardEnumStrings')
    powers = table('include/constants/PlayerStatusEffects.h', 'playerStatusEnumStrings')
    rows = [json.loads(line) for line in (run / 'public.jsonl').read_text().splitlines()]
    summaries, eligible, seen = [], [], set()
    for index, row in enumerate(rows):
        assert int(row['seed']) == seed and row['floor'] == target['floor'] and row['encounter'] == target['encounter']
        summary = {'line_1based': index + 1, 'decision': row['decision'], 'turn': row['turn'],
                   'capture_valid': row['capture_valid']}
        summaries.append(summary)
        if not row['capture_valid']:
            summary['capture_error'] = row.get('capture_error')
            continue
        wire = json.loads(json.dumps(row['public_wire']))
        state = wire['state']
        summary['ordinary_player_decision'] = state['inputState'] == 1
        if state['inputState'] != 1:
            summary['selection_exclusion'] = 'not PLAYER_NORMAL; unchanged adapter domain'
            continue
        assert not state['intentsHidden']
        assert state['player']['characterClass'] == 0
        assert not state['fullDrawOrderObserved'] and not state['drawPile']['fullOrderObserved']
        active = [c for z in ('hand', 'drawPile', 'discardPile') for c in zone(state[z]) if c['id'] != 0]
        names = [cards[c['id']] for c in active]
        owned_powers = [name for j, name in enumerate(powers)
                        if int(state['player'].get('statusBits' + str(j // 64), 0)) & (1 << (j % 64))]
        screen = screen_module.screen(names, relics, combat=True,
                                      costs=[c['costForTurn'] for c in active], powers=owned_powers,
                                      vulnerable=any(m['curHp'] > 0 and m.get('vulnerable', 0) > 0 for m in state['monsters']))
        strong = [r for r in screen['reasons'] if r.startswith(('K1_', 'K2_', 'K3_', 'K5_'))]
        tier = 1 if screen['generic_near_cycle'] else 2 if strong else None
        # Public root boundary: historical run seed is join metadata only.
        state['isolatedSearchSeed'] = 0
        state['observedGeneration'] = 0
        item = {'public_wire': wire, 'oracle_no_prismatic_shard': True}
        digest = sha(json.dumps(item, sort_keys=True).encode())
        priority = min((int(r[1]) for r in strong), default=9)
        summary.update({'screen': screen, 'tier': tier, 'ingredient_priority': priority,
                        'active_cards': dict(sorted(Counter(names).items())),
                        'input_sha256': digest, 'duplicate_public_root': digest in seen})
        if tier and digest not in seen:
            eligible.append((summary, item))
        seen.add(digest)
    assert [r['decision'] for r in rows] == sorted(set(r['decision'] for r in rows)), 'not a single ordinary decision stream'
    # Tier 1 takes precedence. The published ordering is applied within each tier.
    eligible.sort(key=lambda x: (x[0]['tier'], x[0]['screen']['active_card_count'],
                                 x[0]['ingredient_priority'], x[0]['decision']))
    selected = eligible[:4]
    binary = REPO / 'build/linux-gcc-release-ccache/combat_infinity_oracle'
    assert sha(binary.read_bytes()) == '28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9'
    body = ''.join(json.dumps(item, sort_keys=True) + '\n' for _, item in selected)
    manifest = {'seed_for_join_only': seed, 'fight': target, 'receipt_sha256': sha(receipt_bytes),
                'capture_sha256': receipt['files']['public.jsonl'], 'trace_sha256': receipt['files']['trace.jsonl'],
                'full_run_relics': relics, 'no_prismatic_shard_proven': True,
                'run_deck_before_fight': battle['pre']['deck'], 'public_roots_captured': len(rows),
                'valid_roots': sum(r['capture_valid'] for r in summaries),
                'ordinary_public_roots': sum(r.get('ordinary_player_decision', False) for r in summaries),
                'tier1_roots': sum(r.get('tier') == 1 for r in summaries),
                'tier2_roots': sum(r.get('tier') == 2 for r in summaries),
                'selected': [s for s, _ in selected], 'all_roots': summaries,
                'inputs_sha256': sha(body.encode()), 'oracle_binary_sha256': sha(binary.read_bytes()),
                'oracle_K': 4, 'oracle_caps': {'depth': 24, 'nodes': 2000, 'candidates': 16,
                                             'periods': 128, 'actions_per_candidate': 1024, 'total_replay_actions': 4096}}
    return {f'selection-{seed}.json': json.dumps(manifest, indent=2) + '\n', f'inputs-{seed}.jsonl': body}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('seed', type=int, choices=[111101032, 111101326, 111101512])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for name, body in generate(args.seed).items():
        path = HERE / name
        if args.check:
            assert path.read_text() == body, name
        else:
            with path.open('x') as handle:
                handle.write(body)
    print('PASS qualified custody, frozen public-only selection, unchanged adapter identity; no oracle execution')
