#!/usr/bin/env python3
"""Regenerate matrices and decisions from custody-checked frozen raw rows."""
import argparse
from collections import Counter
import json
from pathlib import Path
from stage_a import HERE, CAPS, BINARY_HASH, sha, dump, check


def generate(folder):
    freeze_bytes = (folder / 'FREEZE.json').read_bytes()
    f = json.loads(freeze_bytes)
    lines = (folder / 'inputs.jsonl').read_text().splitlines(keepends=True)
    assert sha(''.join(lines).encode()) == f['inputs_sha256']
    roots, worlds, unannotated = [], [], []
    for meta, line in zip(f['roots'], lines):
        prefix = folder / 'oracle' / f"{meta['decision']:02}"
        if not prefix.with_suffix('.receipt.json').exists():
            unannotated.append(meta['decision'])
            continue
        receipt = json.loads(prefix.with_suffix('.receipt.json').read_text())
        assert receipt['returncode'] == 0 and receipt['binary_sha256'] == BINARY_HASH
        assert receipt['freeze_sha256'] == sha(freeze_bytes) and receipt['input_sha256'] == sha(line.encode()) == meta['input_sha256']
        assert receipt['output_sha256'] == sha(prefix.with_suffix('.jsonl').read_bytes())
        assert receipt['stderr_sha256'] == sha(prefix.with_suffix('.stderr.txt').read_bytes())
        row, summary = [json.loads(v) for v in prefix.with_suffix('.jsonl').read_text().splitlines()]
        assert summary['roots'] == 1 and row['K'] == 4
        os = [w['oracle'] for w in row['worlds']]
        assert all(o['caps'] == CAPS for o in os)
        supported = [o for o in os if o['supported']]
        candidate = sum(any(c['classification'] != 'STALL_LOOP' for c in o['candidates']) for o in supported)
        certified = sum(o['classification'] == 'CERTIFIED_KILL' for o in supported)
        if len(supported) == 4:
            assert row['candidate_fraction'] == candidate/4 and row['certified_fraction'] == certified/4
        caps = [o['node_cap_hit'] or o['depth_cap_hit'] or len(o['candidates']) >= 16 or o['replay_actions'] >= 4096
                or any(c.get('replay', {}).get('reason') in ('action_cap', 'repetition_cap') for c in o['candidates']) for o in os]
        witnesses = [dict(k=w['k'], sample_seed=w['sample_seed'], candidate_index=i,
                          witness_sha256=sha(json.dumps(c, sort_keys=True).encode()), witness=c)
                     for w in row['worlds'] for i,c in enumerate(w['oracle']['candidates']) if c['classification'] != 'STALL_LOOP']
        roots.append(dict(**meta, supported_worlds=len(supported), candidate_fraction=row['candidate_fraction'],
                          certified_fraction=row['certified_fraction'], candidate_worlds=candidate, certified_worlds=certified,
                          minimum_reach_depth=row['minimum_reach_depth'], classifications=dict(Counter(o['classification'] for o in os)),
                          nodes=[o['nodes'] for o in os], max_depth=[o['max_depth'] for o in os],
                          cap_worlds=sum(caps), unsupported_worlds=4-len(supported), witnesses=witnesses,
                          public_root_sha256=row['public_root_sha256']))
        worlds.extend(os)
    nc = sum(r['candidate_worlds'] > 0 for r in roots)
    nk = sum(r['certified_worlds'] > 0 for r in roots)
    caps = sum(r['cap_worlds'] for r in roots)
    unsupported = sum(r['unsupported_worlds'] for r in roots)
    label = ('NATURAL_POSITIVE_ESTABLISHED' if nk else 'NATURAL_NEAR_INFINITY_ESTABLISHED' if nc else
             'TARGET_COMBAT_INCONCLUSIVE' if caps or unsupported or unannotated else 'TARGET_COMBAT_EXHAUSTED_NO_SIGNAL')
    counts = dict(ordinary_roots=len(f['roots']), annotated_roots=len(roots), supported_worlds=sum(r['supported_worlds'] for r in roots),
                  vulnerable_roots=sum(any(v>0 for v in r['enemy_vulnerable']) for r in f['roots']),
                  **{name.lower()+'_in_hand_roots':sum(any(c['name']==name for c in r['zones']['hand']) for r in f['roots'])
                     for name in ('DROPKICK','BASH','POMMEL_STRIKE')},
                  candidate_roots=nc, certified_roots=nk, candidate_worlds=sum(r['candidate_worlds'] for r in roots),
                  certified_worlds=sum(r['certified_worlds'] for r in roots), cap_worlds=caps, unsupported_worlds=unsupported,
                  cap_roots=sum(r['cap_worlds']>0 for r in roots), unsupported_roots=sum(r['unsupported_worlds']>0 for r in roots),
                  total_nodes=sum(o['nodes'] for o in worlds), maximum_depth=max((o['max_depth'] for o in worlds),default=None),
                  minimum_active_pool=min(r['active_pool'] for r in f['roots']))
    result = dict(label=label, counts=counts, permanent_deck_size=f['permanent_deck_size'], cycle_burden=f['cycle_burden'],
                  roots=roots, unannotated_roots=unannotated, freeze_sha256=sha(freeze_bytes))
    md = ['# Exhaustive ordinary-root matrix', '',
          'All identities and ingredient locations (including physical IDs) are in RESULT.json and FREEZE.json. Draw bags are unordered. Turn uses the captured zero-based counter.', '',
          '|Decision|Turn|Player HP|Enemy HP|Vuln|Active|Hand|Draw bag|Dropkick / Bash / Pommel locations|Supported|Nodes|Depth|Candidate / certified|Reach|Caps / unsupported|Witness|',
          '|---:|---:|---:|---|---|---:|---|---|---|---:|---|---|---|---|---|---|']
    for r in roots:
        names = lambda z: ', '.join(c['name']+('#'+str(c['physical_id']))+('+' if c['upgraded'] else '') for c in r['zones'][z]) or 'empty'
        loc = lambda n: ','.join(z+':'+str(len(cs)) for z,cs in r['ingredient_locations'][n].items() if cs) or 'absent'
        md.append('|'+ '|'.join(map(str,[r['decision'],r['turn'],r['player_hp'],r['enemy_hp'],r['enemy_vulnerable'],r['active_pool'],names('hand'),names('drawPile'),
                      ' / '.join(loc(n) for n in ('DROPKICK','BASH','POMMEL_STRIKE')),r['supported_worlds'],r['nodes'],r['max_depth'],
                      f"{r['candidate_fraction']} / {r['certified_fraction']}",r['minimum_reach_depth'],f"{r['cap_worlds']} / {r['unsupported_worlds']}",
                      ','.join(w['witness_sha256'] for w in r['witnesses']) or 'none']))+'|')
    md += ['', '**'+label+'**', '', '```json', dump(counts).strip(), '```', '',
           'NONE is a bounded observation, never a training negative. Unsupported/capped worlds are not negatives.']
    return {'RESULT.json':dump(result), 'MATRIX.md':'\n'.join(md)+'\n'}


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--folder', type=Path, default=HERE); p.add_argument('--check', action='store_true'); a=p.parse_args()
    check()
    for name,body in generate(a.folder).items():
        if a.check:
            assert (a.folder/name).read_text()==body
        else:
            (a.folder/name).write_text(body)
    print((a.folder/'RESULT.json').read_text()[:2100])
