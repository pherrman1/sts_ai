"""One row per real fight of the bot (§683 MAP arm ctm rows; #865 source tars).

usage: python3 -I bot_fights.py <units_root> <repo_root> <out.jsonl> [ARM]

Per fight: seed, floor, act, room (ctm roomClass), encounter (game name), entry/exit HP and max HP (exit = after
end-of-combat heals such as Burning Blood, before rewards), died (combatOutcome 2), potions held at entry and exit
(potion slots that are not EMPTY_POTION_SLOT), potion capacity, deck size, upgraded cards, relic count.
uses_lb = max(0, held at entry - held at exit) is a lower bound on potions drunk: in-combat potion creation
(Alchemize, Entropic Brew) is not netted out.
"""
import gzip, json, sys, glob, os, re

units, repo, out = sys.argv[1:4]
arm = sys.argv[4] if len(sys.argv) > 4 else 'MAP'


def strings(path, name):
    t = open(path).read()
    m = re.search(r'monsterEncounterStrings\[\] = \{(.*?)\};', t, re.S)
    return re.findall(r'"([^"]*)"', m.group(1))


def enum_values(path, name):
    t = open(path).read()
    m = re.search(r'enum class ' + name + r'[^{]*\{(.*?)\};', t, re.S)
    vals, i = {}, 0
    for tok in re.sub(r'//[^\n]*', '', m.group(1)).split(','):
        tok = tok.strip()
        if not tok:
            continue
        if '=' in tok:
            k, v = tok.split('=')
            i = int(v.strip()); tok = k.strip()
        vals[i] = tok; i += 1
    return vals

ENC = enum_values(os.path.join(repo, 'include/constants/MonsterEncounters.h'), 'MonsterEncounter')
EMPTY = 1  # Potion::EMPTY_POTION_SLOT
n = 0
with open(out, 'w') as fo:
    for p in sorted(glob.glob(os.path.join(units, '**', arm + '-*.ctm.jsonl.gz'), recursive=True)):
        seed = int(os.path.basename(p).split('-')[1].split('.')[0])
        with gzip.open(p, 'rt') as f:
            for line in f:
                d = json.loads(line); t = d['transition']; a, b = t['pre'], t['post']; g = d['predictorInput']['globals']
                held = sum(1 for x in a['potions'][:a['potionCapacity']] if x != EMPTY)
                held_post = sum(1 for x in b['potions'][:b['potionCapacity']] if x != EMPTY)
                r = dict(seed=seed, floor=d['floor'], act=d['act'], room=d['roomClass'], enc=ENC.get(d['encounter']),
                         burning=bool(g.get('isBurningElite')), entry_hp=a['curHp'], entry_maxhp=a['maxHp'],
                         exit_hp=b['curHp'], died=t.get('combatOutcome') == 2, outcome=t.get('combatOutcome'),
                         inv_entry=held, inv_exit=held_post, cap=a['potionCapacity'], uses_lb=max(0, held - held_post),
                         gained=max(0, held_post - held), potions_entry=[x for x in a['potions'][:a['potionCapacity']] if x != EMPTY],
                         deck=len(a['deck']), upgrades=sum(1 for c in a['deck'] if c['upgraded']), relics=len(a['relics']),
                         valid=d.get('runValid'))
                fo.write(json.dumps(r) + '\n'); n += 1
print(n, 'fights')
