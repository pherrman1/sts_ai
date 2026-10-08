#!/usr/bin/env python3
"""Read-only chronological run summary; observed deltas are not action proofs."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path):
    with path.open() as stream:
        for line, raw in enumerate(stream, 1):
            if raw.strip():
                row = json.loads(raw)
                seed = int(row['seed'])
                if 610083000 <= seed <= 610083511:
                    raise ValueError('Final confirmation is not an audit source')
                yield line, row


def inventory_delta(before, after):
    a, b = Counter(before), Counter(after)
    return {'added': dict(b - a), 'removed': dict(a - b)}


def describe_delta(pre, post):
    return {'hp': post['hp'] - pre['hp'], 'max_hp': post['maxHp'] - pre['maxHp'],
            'gold': post['gold'] - pre['gold'],
            **{k: inventory_delta(pre.get(k, []), post.get(k, [])) for k in ('deck', 'relics', 'potions')}}


def upgraded_cards(delta):
    added, removed = Counter(delta['deck']['added']), Counter(delta['deck']['removed'])
    result = {}
    for card, count in removed.items():
        if added[card + '+']:
            result[card] = min(count, added[card + '+'])
    return result


def action_observation(row, delta):
    pre, post = row['pre'], row['post']
    if row['kind'] == 'battle':
        return 'battle_win' if row.get('won') else 'battle_loss'
    upgrades = upgraded_cards(delta)
    if upgrades:
        return 'upgrade_observed'
    screen = pre['screen']
    if screen == 'REST':
        if post['screen'] == 'CARD_SELECT':
            return 'rest_opens_selector'
        if post['screen'] == 'REWARDS' and 'DREAM_CATCHER' in pre.get('relics', []):
            return 'rest_opens_dream_catcher_reward'
        if delta['hp'] > 0:
            return 'rest_healing_observed'
        if delta['deck']['removed'] and not delta['deck']['added']:
            return 'rest_removal_observed'
        if (pre['hp'] == pre['maxHp'] and post['screen'] == 'MAP'
                and not any(delta[k]['added'] or delta[k]['removed'] for k in ('deck','relics','potions'))):
            return 'rest_no_visible_benefit_at_full_hp'
        return 'rest_other_transition'
    if screen == 'CARD_SELECT':
        if delta['deck']['removed'] and not delta['deck']['added']:
            return 'selector_removal_observed'
        return 'selector_other_transition'
    if screen == 'REWARDS' and delta['deck']['added']:
        return 'reward_card_added'
    if screen == 'REWARDS' and row.get('offer', {}).get('cards') and post['screen'] != 'REWARDS':
        return 'reward_exit_without_card_addition'
    if screen == 'BOSS_RELIC' and delta['relics']['added']:
        return 'boss_relic_added'
    if screen == 'SHOP':
        return 'shop_spend_observed' if delta['gold'] < 0 else 'shop_transition_without_spend'
    return screen.lower() + '_transition'


def summarize(paths, tree_paths=(), combat_paths=()):
    runs, inputs = {}, []
    for path in paths:
        filehash = sha(path)
        inputs.append({'kind': 'ooc_trace', 'path': str(path.resolve()), 'sha256': filehash})
        rows = list(read_jsonl(path))
        for position, (line, row) in enumerate(rows):
            seed = int(row['seed'])
            run = runs.setdefault(seed, {'seed': seed, 'chronology': [], 'suspicions': [],
                                        'tree_roots': [], 'combat_audit': []})
            pre, post = row['pre'], row['post']
            delta = describe_delta(pre, post)
            item = {'locator': f'{path.resolve()}:{line}', 'file_sha256': filehash,
                    'kind': row['kind'], 'idx': row.get('idx'), 'fight': row.get('fight'),
                    'act': pre['act'], 'floor': pre['floor'], 'screen': pre['screen'],
                    'by': row.get('by'), 'encounter': row.get('encounter'), 'won': row.get('won'),
                    'pre_hp': pre['hp'], 'post_hp': post['hp'], 'pre_max_hp': pre['maxHp'],
                    'gold_before': pre['gold'], 'gold_after': post['gold'],
                    'deck_size_before': len(pre.get('deck', [])), 'deck_size_after': len(post.get('deck', [])),
                    'delta': delta, 'upgrades_observed': upgraded_cards(delta),
                    'observation': action_observation(row, delta),
                    'action_identity_status': 'inferred_from_observed_transition; trace does not serialize exact OOC semantic action'}
            if pre['screen'] == 'REST' and post['screen'] == 'CARD_SELECT':
                chain = []
                end = post
                for nextline, nxt in rows[position+1:]:
                    if int(nxt['seed']) != seed or nxt['pre']['floor'] != pre['floor'] or nxt['pre']['screen'] != 'CARD_SELECT':
                        break
                    chain.append(f'{path.resolve()}:{nextline}')
                    end = nxt['post']
                    if end['screen'] != 'CARD_SELECT':
                        break
                item['following_selector_locators'] = chain
                item['rest_through_selector_delta'] = describe_delta(pre, end)
                item['rest_through_selector_upgrades'] = upgraded_cards(item['rest_through_selector_delta'])
            suspicion = None
            if item['observation'] == 'rest_no_visible_benefit_at_full_hp' and 'DREAM_CATCHER' not in pre.get('relics', []):
                suspicion = 'zero_healing_rest_candidate; check actual semantic action, legal alternatives, relic effects and counterfactuals'
            if row['kind'] == 'battle' and not row.get('won') and post.get('potions'):
                suspicion = 'loss_with_potions_retained; retained potion is not proof of a useful legal potion line'
            if suspicion:
                run['suspicions'].append({'locator': item['locator'], 'classification': 'SUSPICIOUS_UNTESTED', 'reason': suspicion})
            run['chronology'].append(item)
            run['last_public_state'] = post
    for path in tree_paths:
        filehash = sha(path)
        inputs.append({'kind': 'tree', 'path': str(path.resolve()), 'sha256': filehash})
        for line, row in read_jsonl(path):
            seed = int(row['seed'])
            if seed not in runs:
                continue
            fields = ('combat_id','act','floor','encounter','turn','decision','hp','max_hp','enemy_hp',
                      'configured_simulations','completed_simulations','inherited_visits','nodes',
                      'root_actions','singleton_skip','action','error','descent_aborts')
            runs[seed]['tree_roots'].append({'locator': f'{path.resolve()}:{line}',
                                           **{k: row.get(k) for k in fields}})
    for path in combat_paths:
        filehash = sha(path)
        inputs.append({'kind': 'combat_audit', 'path': str(path.resolve()), 'sha256': filehash})
        for line, row in read_jsonl(path):
            seed = int(row['seed'])
            if seed not in runs:
                continue
            # Preserve snapshot locator/hash only: the concrete proof state is
            # privileged forensic material, not a blinded public decision.
            fields = ('act','floor','encounter','turn','decision','chosen_action','provably_useless',
                      'reason','proof_scope','classification','q_difference','snapshot_fnv1a64')
            runs[seed]['combat_audit'].append({'locator': f'{path.resolve()}:{line}',
                                             **{k: row.get(k) for k in fields}})
    for run in runs.values():
        battles = [r for r in run['chronology'] if r['kind'] == 'battle']
        run['battle_count'] = len(battles)
        run['observations'] = dict(Counter(r['observation'] for r in run['chronology']))
        run['act3_boss_win_observed'] = any(r['won'] and r['act'] == 3
            and r['encounter'] in ('AWAKENED_ONE','TIME_EATER','DONU_AND_DECA') for r in battles)
        roots = run['tree_roots']
        run['tree_summary'] = {'roots': len(roots),
            'simulations': sum(r.get('completed_simulations') or 0 for r in roots),
            'singleton_skips': sum(bool(r.get('singleton_skip')) for r in roots),
            'errors': sum(bool(r.get('error')) for r in roots)}
    return {'schema': 'overnight_trace_summary_v1', 'inputs': inputs, 'runs': list(runs.values()),
            'limits': ['Inventory deltas use multiplicities; deck positions, relic counters, and precise OOC semantic actions are absent.',
                       'After-battle HP includes exit/healing effects; potion removals do not alone prove consumption.',
                       'Suspicion flags are hypothesis generators, not bugs or policy-quality verdicts.',
                       'Completion and effective policy must be joined to the frozen run receipts before population analysis.']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--trace', type=Path, action='append', required=True)
    p.add_argument('--tree', type=Path, action='append', default=[])
    p.add_argument('--combat', type=Path, action='append', default=[])
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = summarize(a.trace, a.tree, a.combat)
    with a.out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({'out': str(a.out.resolve()), 'sha256': sha(a.out), 'runs': len(result['runs']),
                      'observations': sum(len(r['chronology']) for r in result['runs']),
                      'suspicions': sum(len(r['suspicions']) for r in result['runs'])}))


if __name__ == '__main__':
    main()
