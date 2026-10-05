#!/usr/bin/env python3
"""Tag callbacks only in exact archived #334 producer sources, never a checkout.

Original lambda bodies/captures remain intact. Metadata is added by an observer
wrapper; frozen binary/model artifacts are never overwritten. The importer in
current-main separately reconstructs current callback semantics. Full source
SHA identities and exact lambda text/counts fail closed before any file write.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

CATALOG = {'src/game/GameContext.cpp': {'25f4fde876945f7b300698d0e6c383ec05b6ef886e33179d9741ca116640443a': [{'lambda': '[](auto '
                                                                                                              '&gs) '
                                                                                                              '{\n'
                                                                                                              '    '
                                                                                                              'gs.screenState '
                                                                                                              '= '
                                                                                                              'ScreenState::MAP_SCREEN;\n'
                                                                                                              '    '
                                                                                                              'gs.regainControlAction '
                                                                                                              '= '
                                                                                                              'nullptr;\n'
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"return_to_map"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '        '
                                                                                                              'gc.afterBattle();\n'
                                                                                                              '    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"after_battle"}}'},
                                                                                                   {'lambda': '[](auto '
                                                                                                              '&gs) '
                                                                                                              '{\n'
                                                                                                              '        '
                                                                                                              'gs.screenState '
                                                                                                              '= '
                                                                                                              'ScreenState::MAP_SCREEN;\n'
                                                                                                              '    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"set_map"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                '
                                                                                                              'gc.afterBattle();\n'
                                                                                                              '            '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"after_battle"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                '
                                                                                                              'gc.afterBattle();\n'
                                                                                                              '            '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"after_battle"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                '
                                                                                                              'gc.afterBattle();\n'
                                                                                                              '            '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"after_battle"}}'},
                                                                                                   {'lambda': '[a=act](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '        '
                                                                                                              'gc.transitionToAct(a+1);\n'
                                                                                                              '    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"next_captured_act"}, '
                                                                                                                      '{"act", '
                                                                                                                      'act}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                    '
                                                                                                              'gc.enterBossTreasureRoom();\n'
                                                                                                              '                '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"boss_treasure"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                        '
                                                                                                              'gc.afterBattle();\n'
                                                                                                              '                    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"after_battle"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{ '
                                                                                                              'gc.transitionToAct(gc.act '
                                                                                                              '+ '
                                                                                                              '1); '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"next_current_act"}}'},
                                                                                                   {'lambda': '[](auto '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '            '
                                                                                                              'int '
                                                                                                              'roll '
                                                                                                              '= '
                                                                                                              'gc.cardRng.random(static_cast<int>(9));\n'
                                                                                                              '            '
                                                                                                              'gc.deck.obtain(gc, '
                                                                                                              'curseCardPool[roll]);\n'
                                                                                                              '            '
                                                                                                              'gc.screenState '
                                                                                                              '= '
                                                                                                              'ScreenState::MAP_SCREEN;\n'
                                                                                                              '            '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '        '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"neow_curse"}}'},
                                                                                                   {'lambda': '[](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                    '
                                                                                                              'gc.screenState '
                                                                                                              '= '
                                                                                                              'ScreenState::EVENT_SCREEN;\n'
                                                                                                              '                    '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '                '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"colosseum_first"}}'},
                                                                                                   {'lambda': '[=](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                    '
                                                                                                              'Rewards '
                                                                                                              'reward;\n'
                                                                                                              '                    '
                                                                                                              'reward.addGold(goldAmt);\n'
                                                                                                              '                    '
                                                                                                              'reward.addRelic(rareRelic);\n'
                                                                                                              '                    '
                                                                                                              'reward.addRelic(uncommonRelic);\n'
                                                                                                              '                    '
                                                                                                              'gc.addPotionRewards(reward);\n'
                                                                                                              '                    '
                                                                                                              'reward.addCardReward(gc.createCardReward(Room::EVENT));\n'
                                                                                                              '                    '
                                                                                                              'gc.openCombatRewardScreen(reward);\n'
                                                                                                              '                    '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '                '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"colosseum_rewards"}, '
                                                                                                                      '{"gold", '
                                                                                                                      'goldAmt}, '
                                                                                                                      '{"rare", '
                                                                                                                      'static_cast<int>(rareRelic)}, '
                                                                                                                      '{"uncommon", '
                                                                                                                      'static_cast<int>(uncommonRelic)}}'},
                                                                                                   {'lambda': '[=](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                        '
                                                                                                              'Rewards '
                                                                                                              'reward;\n'
                                                                                                              '                        '
                                                                                                              'reward.addGold(goldAmt);\n'
                                                                                                              '                        '
                                                                                                              'if '
                                                                                                              '(addRelic) '
                                                                                                              '{\n'
                                                                                                              '                            '
                                                                                                              'reward.addRelic(combatRewardRelic);\n'
                                                                                                              '                        '
                                                                                                              '}\n'
                                                                                                              '                        '
                                                                                                              '// '
                                                                                                              'eliteTrigger: '
                                                                                                              'Black '
                                                                                                              'Star '
                                                                                                              'applies '
                                                                                                              'to '
                                                                                                              'this '
                                                                                                              'fight.\n'
                                                                                                              '                        '
                                                                                                              'if '
                                                                                                              '(gc.hasRelic(RelicId::BLACK_STAR)) '
                                                                                                              '{\n'
                                                                                                              '                            '
                                                                                                              'reward.addRelic(gc.returnNonCampfireRelic(returnRandomRelicTierElite(gc.relicRng)));\n'
                                                                                                              '                        '
                                                                                                              '}\n'
                                                                                                              '                        '
                                                                                                              'reward.addCardReward(gc.createCardReward(Room::EVENT));\n'
                                                                                                              '                        '
                                                                                                              'gc.addPotionRewards(reward);\n'
                                                                                                              '                        '
                                                                                                              'gc.openCombatRewardScreen(reward);\n'
                                                                                                              '                        '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '                    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"dead_adventurer_rewards"}, '
                                                                                                                      '{"gold", '
                                                                                                                      'goldAmt}, '
                                                                                                                      '{"addRelic", '
                                                                                                                      'addRelic}, '
                                                                                                                      '{"relic", '
                                                                                                                      'static_cast<int>(addRelic ? combatRewardRelic : RelicId::INVALID)}}'},
                                                                                                   {'lambda': '[=](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                        '
                                                                                                              'gc.deck.upgradeRandomCards(gc.miscRng, '
                                                                                                              '1);\n'
                                                                                                              '                        '
                                                                                                              'returnToMapAction(gc);\n'
                                                                                                              '                    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"designer_upgrade"}}'},
                                                                                                   {'lambda': '[goldAmt](auto '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                    '
                                                                                                              'Rewards '
                                                                                                              'reward;\n'
                                                                                                              '                    '
                                                                                                              'reward.addGold(goldAmt);\n'
                                                                                                              '                    '
                                                                                                              'reward.addRelic(RelicId::RED_MASK);\n'
                                                                                                              '                    '
                                                                                                              'reward.addCardReward(gc.createCardReward(Room::EVENT));\n'
                                                                                                              '                    '
                                                                                                              'gc.openCombatRewardScreen(reward);\n'
                                                                                                              '                    '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '                '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"masked_bandits_rewards"}, '
                                                                                                                      '{"gold", '
                                                                                                                      'goldAmt}}'},
                                                                                                   {'lambda': '[=](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                        '
                                                                                                              'Rewards '
                                                                                                              'reward;\n'
                                                                                                              '                        '
                                                                                                              'reward.addGold(goldAmt);\n'
                                                                                                              '                        '
                                                                                                              'reward.addRelic(rareRelic);\n'
                                                                                                              '                        '
                                                                                                              'gc.addPotionRewards(reward);\n'
                                                                                                              '                        '
                                                                                                              'reward.addCardReward(gc.createCardReward(Room::EVENT));\n'
                                                                                                              '                        '
                                                                                                              'gc.openCombatRewardScreen(reward);\n'
                                                                                                              '                        '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '                    '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"mind_bloom_rewards"}, '
                                                                                                                      '{"gold", '
                                                                                                                      'goldAmt}, '
                                                                                                                      '{"rare", '
                                                                                                                      'static_cast<int>(rareRelic)}}'},
                                                                                                   {'lambda': '[=](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                    '
                                                                                                              'Rewards '
                                                                                                              'reward;\n'
                                                                                                              '                    '
                                                                                                              'reward.addGold(goldAmt);\n'
                                                                                                              '                    '
                                                                                                              'reward.addRelic(RelicId::ODD_MUSHROOM);\n'
                                                                                                              '                    '
                                                                                                              'gc.addPotionRewards(reward);\n'
                                                                                                              '                    '
                                                                                                              'reward.addCardReward(gc.createCardReward(Room::EVENT));\n'
                                                                                                              '                    '
                                                                                                              'gc.openCombatRewardScreen(reward);\n'
                                                                                                              '                    '
                                                                                                              'gc.regainControlAction '
                                                                                                              '= '
                                                                                                              'returnToMapAction;\n'
                                                                                                              '                '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"mushroom_rewards"}, '
                                                                                                                      '{"gold", '
                                                                                                                      'goldAmt}}'},
                                                                                                   {'lambda': '[=](GameContext '
                                                                                                              '&gc) '
                                                                                                              '{\n'
                                                                                                              '                    '
                                                                                                              'gc.afterBattle();\n'
                                                                                                              '                '
                                                                                                              '}',
                                                                                                    'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                      '"after_battle"}}'}]},
 'src/game/Shop.cpp': {'1025862b24e3dd7f33dd70e9128324b0f28bfc746d01bdfdb44aa7a52b87f036': [{'lambda': '[](GameContext '
                                                                                                       '&gc) '
                                                                                                       '{\r\n'
                                                                                                       '            '
                                                                                                       'gc.screenState '
                                                                                                       '= '
                                                                                                       'ScreenState::SHOP_ROOM;\r\n'
                                                                                                       '            '
                                                                                                       'gc.regainControlAction '
                                                                                                       '= '
                                                                                                       '[] '
                                                                                                       '(auto '
                                                                                                       '&gc) '
                                                                                                       '{\r\n'
                                                                                                       '                '
                                                                                                       'gc.screenState '
                                                                                                       '= '
                                                                                                       'ScreenState::MAP_SCREEN;\r\n'
                                                                                                       '            '
                                                                                                       '};\r\n'
                                                                                                       '        '
                                                                                                       '}',
                                                                                             'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                               '"shop_relic_return"}}'},
                                                                                            {'lambda': '[] '
                                                                                                       '(auto '
                                                                                                       '&gc) '
                                                                                                       '{\r\n'
                                                                                                       '                '
                                                                                                       'gc.screenState '
                                                                                                       '= '
                                                                                                       'ScreenState::MAP_SCREEN;\r\n'
                                                                                                       '            '
                                                                                                       '}',
                                                                                             'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                               '"set_map"}}'},
                                                                                            {'lambda': '[=](GameContext '
                                                                                                       '&g) '
                                                                                                       '{\r\n'
                                                                                                       '        '
                                                                                                       'g.screenState '
                                                                                                       '= '
                                                                                                       'ScreenState::SHOP_ROOM;\r\n'
                                                                                                       '        '
                                                                                                       'g.regainControlAction '
                                                                                                       '= '
                                                                                                       'gc.regainControlAction;\r\n'
                                                                                                       '    '
                                                                                                       '}',
                                                                                             'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                               '"shop_remove_return"}, '
                                                                                                               '{"previous", '
                                                                                                               '::one_combat::screen_leaf::continuationDescriptor(gc.regainControlAction)}}'}]},
 'src/sim/search/GameAction.cpp': {'a43807c264d39a0b60b132384f287e13460de573b5786e6eac62eaf694482d18': [{'lambda': '[remainingRewards, '
                                                                                                                   'previousContinuation](GameContext '
                                                                                                                   '&next) '
                                                                                                                   '{\n'
                                                                                                                   '                    '
                                                                                                                   'const '
                                                                                                                   'auto '
                                                                                                                   'continuation '
                                                                                                                   '= '
                                                                                                                   'previousContinuation;\n'
                                                                                                                   '                    '
                                                                                                                   'next.openCombatRewardScreen(remainingRewards);\n'
                                                                                                                   '                    '
                                                                                                                   'next.regainControlAction '
                                                                                                                   '= '
                                                                                                                   'continuation;\n'
                                                                                                                   '                '
                                                                                                                   '}',
                                                                                                         'descriptor_cpp': '::one_combat::screen_leaf::Json{{"kind", '
                                                                                                                           '"remaining_rewards"}, '
                                                                                                                           '{"rewards", '
                                                                                                                           '::one_combat::screen_leaf::rewardsJson(remainingRewards)}, '
                                                                                                                           '{"previous", '
                                                                                                                           '::one_combat::screen_leaf::continuationDescriptor(previousContinuation)}}'}]}}


def apply(root):
    root = root.resolve()
    if (root / '.git').exists():
        raise ValueError('refusing callback patches in a Git checkout; use a frozen source archive')
    for name in ('screen_leaf_continuations.h', 'screen_leaf_snapshot.h'):
        if not (root / 'apps/one_combat' / name).is_file():
            raise ValueError('copy offline bridge headers into archived source first: ' + name)
    edits = []
    receipts = []
    pattern = r'(?:regainControlAction|returnToMapAction)\s*=\s*(\[[^\]]*\]\s*\([^)]*\)\s*\{)'
    for relative, identities in CATALOG.items():
        path = root / relative
        raw = path.read_bytes()
        before_sha = hashlib.sha256(raw).hexdigest()
        if before_sha not in identities:
            raise ValueError('unrecognized/already-patched frozen source: ' + relative)
        text = raw.decode('utf-8')
        inventory = identities[before_sha]
        spans = []
        for match in re.finditer(pattern, text):
            prefix = text[text.rfind('\n', 0, match.start()) + 1:match.start()]
            if prefix.lstrip().startswith('//'):
                continue
            pos, depth = match.end(), 1
            while depth:
                if pos == len(text):
                    raise ValueError('unterminated lambda')
                depth += (text[pos] == '{') - (text[pos] == '}')
                pos += 1
            spans.append((match.start(1), pos))
        if len(spans) != len(inventory):
            raise ValueError('callback count mismatch: ' + relative)
        inserts = []
        for (start, end), item in zip(spans, inventory):
            if text[start:end] != item['lambda']:
                raise ValueError('callback text mismatch: ' + relative)
            inserts.append((start, '::one_combat::screen_leaf::tagContinuation(' + item['descriptor_cpp'] + ', '))
            inserts.append((end, ')'))
        for pos, value in sorted(inserts, reverse=True):
            text = text[:pos] + value + text[pos:]
        relative_include = '../../' if relative.startswith('src/game/') else '../../../'
        includes = ''.join('#include "' + relative_include + 'apps/one_combat/' + name + '"\n'
                           for name in ('screen_leaf_continuations.h', 'screen_leaf_snapshot.h'))
        result = (includes + text).encode('utf-8')
        edits.append((path, result))
        receipts.append({'path': relative, 'before_sha256': before_sha,
                         'after_sha256': hashlib.sha256(result).hexdigest(),
                         'tagged_lambdas': len(spans)})
    # All source identities and callback bodies are verified before any write.
    for path, result in edits:
        path.write_bytes(result)
    return {'schema': 'screen_leaf_frozen_callback_patch_v1', 'files': receipts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
