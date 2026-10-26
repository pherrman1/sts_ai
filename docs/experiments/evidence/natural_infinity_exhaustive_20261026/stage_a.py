#!/usr/bin/env python3
"""Evidence-only exhaustive freeze, bounded invocation, and offline reporting."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PIN = '1322e0d97721d9ffe9e2e41dbc69d8a5acc07a01'
BASELINE = '8cce22b4d5d54733330e323b3065ca687fbcbfc5'
SOURCE = 'docs/experiments/evidence/combat_infinity_mask_search_20261025/'
BINARY = Path('/home/philippherrmann/.codex/worktrees/infinity-public-root-pilot/sts_lightspeed/build/linux-gcc-release-ccache/combat_infinity_oracle')
BINARY_HASH = '28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9'
CAPS = dict(depth=24, cycle_length=24, nodes=2000, candidates=16,
            repetitions=128, actions_per_replay=1024, total_replay_actions=4096)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(path):
    return subprocess.check_output(['git', 'show', PIN + ':' + path], cwd=REPO)


def dump(value):
    return json.dumps(value, indent=2, sort_keys=True) + '\n'


def zone(value):
    return value if isinstance(value, list) else [c for k in ('knownTop', 'unknown', 'knownBottom') for c in value.get(k, [])]


def freeze():
    receipt = json.loads(git(SOURCE + 'capture/11111.receipt.json'))
    assert receipt['status'] == 'CAPTURED' and receipt['first_difference'] is None
    artifacts = {}
    streams = {}
    for name in ('public.jsonl', 'states.jsonl', 'trace.jsonl'):
        packed = git(SOURCE + 'capture/11111.' + name + '.gz')
        raw = gzip.decompress(packed)
        assert sha(raw) == receipt['files'][name]
        artifacts[name] = dict(path=SOURCE + 'capture/11111.' + name + '.gz',
                               compressed_sha256=sha(packed), decompressed_sha256=sha(raw))
        streams[name] = [json.loads(line) for line in raw.splitlines()]
    battle = receipt['capture_battle']
    assert battle['pre']['relics'] == ['BURNING_BLOOD', 'MEAL_TICKET', 'STRIKE_DUMMY', 'KUNAI', 'PANDORAS_BOX']
    assert battle in streams['trace.jsonl']
    text = git('include/constants/Cards.h').decode()
    start = text.index('cardEnumStrings')
    names = re.findall(r'"([A-Z_0-9]+)"', text[start:text.index('};', start)])
    roots, inputs, excluded = [], [], []
    for line, row in enumerate(streams['public.jsonl'], 1):
        assert int(row['seed']) == 111101032 and row['act'] == 2 and row['floor'] == 18 and row['encounter'] == 'SHELL_PARASITE'
        assert row['capture_valid']
        wire = row['public_wire']
        state = wire['state']
        if state['inputState'] != 1:
            excluded.append(dict(line=line, decision=row['decision'], inputState=state['inputState']))
            continue
        assert not state['intentsHidden'] and not state['fullDrawOrderObserved'] and not state['drawPile']['fullOrderObserved']
        assert state['player']['characterClass'] == 0
        # Same public-only identity normalization as the existing #844 freeze.
        state['isolatedSearchSeed'] = 0
        state['observedGeneration'] = 0
        item = dict(public_wire=wire, oracle_no_prismatic_shard=True)
        inputs.append(json.dumps(item, sort_keys=True) + '\n')
        zones = {z: [dict(name=names[c['id']], physical_id=c['uniqueId'], upgraded=c['upgraded'])
                     for c in zone(state[z]) if c['id']] for z in ('hand', 'drawPile', 'discardPile', 'exhaustPile', 'limbo')}
        locations = {name: {z: [c for c in cards if c['name'] == name] for z, cards in zones.items()}
                     for name in ('DROPKICK', 'BASH', 'POMMEL_STRIKE')}
        monsters = [m for m in state['monsters'] if m['curHp'] > 0]
        roots.append(dict(decision=row['decision'], line_1based=line, turn=row['turn'],
                          player_hp=state['player']['curHp'], enemy_hp=[m['curHp'] for m in monsters],
                          enemy_vulnerable=[m['vulnerable'] for m in monsters],
                          active_pool=sum(len(zones[z]) for z in ('hand', 'drawPile', 'discardPile')),
                          zones=zones, ingredient_locations=locations, input_sha256=sha(inputs[-1].encode())))
    assert len(roots) == 21 and len(excluded) == 1
    assert [r['decision'] for r in roots] == sorted(set(r['decision'] for r in roots))
    assert sha(BINARY.read_bytes()) == BINARY_HASH
    oracle_source = git('apps/combat_infinity_oracle.cpp')
    assert oracle_source == (BINARY.parents[2] / 'apps/combat_infinity_oracle.cpp').read_bytes()
    body = ''.join(inputs)
    metadata = dict(baseline_sha=BASELINE, pinned_source=PIN, source_artifacts=artifacts,
                    capture_receipt_sha256=sha(git(SOURCE + 'capture/11111.receipt.json')),
                    oracle_binary=str(BINARY), oracle_binary_sha256=BINARY_HASH,
                    oracle_source_sha256=sha(oracle_source), K=4, caps=CAPS,
                    rule='all ordinary roots, capture order; no selection or deduplication',
                    roots=roots, excluded_nonordinary=excluded, inputs_sha256=sha(body.encode()),
                    combat_entry=battle['pre'], combat_exit=battle['post'],
                    permanent_deck_size=14, cycle_burden=8,
                    cycle_burden_definition_source='PR863 6e479697b7af2874e89bb850737b31656cbed8a9 apps/one_combat/compression_audit.cpp::burden',
                    cycle_burden_excluded=['Ascender\'s Bane', 'Fire Breathing x2', 'Berserk', 'Inflame', 'Barricade'])
    return {'FREEZE.json': dump(metadata), 'inputs.jsonl': body}


def check():
    for name, body in freeze().items():
        assert (HERE / name).read_text() == body, name


def run(folder=HERE):
    check()
    manifest = json.loads((folder / 'FREEZE.json').read_text())
    assert sha((folder / 'inputs.jsonl').read_bytes()) == manifest['inputs_sha256']
    assert sha(BINARY.read_bytes()) == BINARY_HASH
    lines = (folder / 'inputs.jsonl').read_text().splitlines(keepends=True)
    assert len(lines) == len(manifest['roots'])
    outdir = folder / 'oracle'
    outdir.mkdir(exist_ok=False)
    for root, line in zip(manifest['roots'], lines):
        prefix = outdir / str(root['decision']).zfill(2)
        input_path = prefix.with_suffix('.input.jsonl')
        input_path.write_text(line)
        command = ['timeout', '30s', 'bash', 'tools/seed_guard.sh', str(BINARY), '--public-roots', str(input_path)]
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.monotonic()
        result = subprocess.run(command, cwd=REPO, capture_output=True)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        prefix.with_suffix('.jsonl').write_bytes(result.stdout)
        prefix.with_suffix('.stderr.txt').write_bytes(result.stderr)
        prefix.with_suffix('.receipt.json').write_text(dump(dict(command=command, returncode=result.returncode,
            freeze_sha256=sha((folder / 'FREEZE.json').read_bytes()), input_sha256=sha(line.encode()),
            output_sha256=sha(result.stdout), stderr_sha256=sha(result.stderr), binary_sha256=sha(BINARY.read_bytes()),
            wall_seconds=time.monotonic()-start, child_user_seconds=after.ru_utime-before.ru_utime,
            child_system_seconds=after.ru_stime-before.ru_stime)))
        assert result.returncode == 0, result.stderr
        row, summary = [json.loads(v) for v in result.stdout.splitlines()]
        print(root['decision'], row['status'], row['candidate_fraction'], flush=True)
        if row['candidate_fraction'] and row['candidate_fraction'] > 0:
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['freeze', 'check', 'run'])
    args = parser.parse_args()
    if args.mode == 'freeze':
        for name, body in freeze().items():
            with (HERE / name).open('x') as stream:
                stream.write(body)
    elif args.mode == 'check':
        check()
    else:
        run()
