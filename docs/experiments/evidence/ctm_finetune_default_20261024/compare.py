"""python3 -I compare.py GUARD NEW SEED...: the HP-head fine-tune default (ADR-TBD) on guard seeds.
GUARD holds the guard's units (out/units/ of the ../ctm_calibration_20261023 tars; arm C is main's default, the §470
stack with the ADR-0058 table). NEW holds this change's games, one ../ctm_calibration_default_20261023/run_exp.sh game
each with arm C's environment: zero-SEED/ with STS_CTM_A20_HP_FINETUNE=0 and ft-SEED/ with it unset (the default).
Requires a complete, integrity-passed outcome footer in every game, zero equal to the guard's C in every record after
the header and every CTM row, and in each game the banners and header CTM artifacts of its stack. Reports where the
default first plays differently."""
import gzip
import json
import sys
from pathlib import Path

guard, new = Path(sys.argv[1]), Path(sys.argv[2])
FT = {'path': 'models/candidates/ctm_finetune_hp_pathb_a20_v1.native',
      'sha256': 'bdbfafa6823adc52ff240dae5cbd2ba224aca145f2182bedf79fe0dc8cf6571b'}
TABLES = {'zero': 'table=models/candidates/ctm_calibration_pathb_a20_v1.json '
                  'sha256=359619f713677de60b86144e275ad37874718951c6964b63811f55c77181cb42 groups=34',
          'ft': 'table=models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json '
                'sha256=8c226f23d80ff1cd2d9d1f87a14af3b5098a710ef88c6428f3fe0e70b3283653 groups=34'}


def lines(p):
    if p.exists():
        return p.read_text().splitlines()
    return gzip.decompress(p.with_name(p.name + '.gz').read_bytes()).decode().splitlines()


def footer(rows):
    try:
        foot = json.loads(rows[-1])
    except (IndexError, ValueError):
        return None
    ok = foot.get('type') == 'outcome' and bool(foot.get('complete')) and bool(foot.get('integrityPassed'))
    return foot if ok else None


def artifacts(rows):
    return {a['role']: {'path': a['path'], 'sha256': a['sha256']} for a in json.loads(rows[0])['provenance']['ctmArtifacts']}


ok = True
for seed in sys.argv[3:]:
    base = guard / seed / f'C-{seed}'
    games = {'guard': base, 'zero': new / f'zero-{seed}' / f'C-{seed}', 'ft': new / f'ft-{seed}' / f'C-{seed}'}
    rows = {k: lines(p.with_name(p.name + '.jsonl')) for k, p in games.items()}
    ctm = {k: lines(p.with_name(p.name + '.ctm.jsonl')) for k, p in games.items()}
    for k in games:
        foot = footer(rows[k])
        ok &= foot is not None
        end = 'incomplete' if foot is None else ('Heart killed' if foot['heartKilled'] else 'died') + \
            f" (act {foot['finalAct']}, floor {foot['finalFloor']})"
        print(f'{seed} {k}: {len(rows[k])} records, {len(ctm[k])} CTM rows, {end}')
    for k in ('zero', 'ft'):
        text = '\n'.join(lines(games[k].with_name(games[k].name + '.log')) + lines(games[k].with_name(games[k].name + '.err')))
        stack = f"active_lizard_correction=1 hp_finetune={int(k == 'ft')}"
        banners = '[ctm-a20-stack] candidate_id=pathb-a20' in text and stack in text and f'[ctm-calibration] {TABLES[k]}' in text
        want = dict(artifacts(rows['guard']), **({'ctm_a20': FT} if k == 'ft' else {}))
        header = artifacts(rows[k]) == want
        print(f'{seed} {k}: banner "{stack}" and its table {banners}; header CTM artifacts as expected {header}')
        ok &= banners and header
    for left, right, must in (('zero', 'guard', True), ('ft', 'zero', False)):
        for kind, data, skip in (('records', rows, 1), ('CTM rows', ctm, 0)):  # the header holds paths and the git sha
            a, b = data[left][skip:], data[right][skip:]
            first = next((i + skip for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
            same = a == b
            print(f'{seed} {left} vs {right} {kind}: identical={same}'
                  + ('' if same else f' (first difference at line {first if first is not None else min(len(a), len(b)) + skip})'))
            if must:
                ok &= same
    # Records carry the search's statistics, so they differ before any move does. Rule decisions (tree, relic, chest
    # rules) name no key.
    moves = {k: [(d['by'], d.get('selectedKey')) for d in map(json.loads, rows[k]) if d.get('type') == 'decision']
             for k in ('zero', 'ft')}
    first = next((i for i, (x, y) in enumerate(zip(moves['zero'], moves['ft'])) if x != y), None)
    print(f"{seed} ft vs zero moves: {len(moves['ft'])} vs {len(moves['zero'])} decisions, "
          + ('the same move at every decision' if first is None and len(moves['ft']) == len(moves['zero'])
             else f'first different move at decision {first}'))
print('PASS' if ok else 'FAIL')
