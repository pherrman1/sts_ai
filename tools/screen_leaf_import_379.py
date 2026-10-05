"""Issue379-only custody decoration of verified frozen VALIDATION snapshots.

Tags assert semantics; receipts and original byte hashes establish provenance.
Never rewrites frozen artifacts. No TEST/TRAIN source is admitted.
"""
import copy
import json
from pathlib import Path

from audit_screen_leaf_379 import EXPECTED, digest

PRODUCERS = {'1e93bd66cb5ef489028f1a06c22d5f12bd2ca935',
             '0665747164ca3914c229546ad13f4f26a3a4a23c'}
CURRENT = {'schema': 'screen-leaf-import-context-v1', 'domain': 'current-379'}
FORBIDDEN = {'snapshotSemantics', 'snapshotOrigin', 'snapshotImportHistory'}


def require(ok, message):
    if not ok: raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text())


def write_new(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def identity(row):
    return row['sourceSeed'], row['branchId'], row['rowIdx']


def decorate_replay(index, source, custody, output, kind='snapshots'):
    # Lazy import avoids coordinator/helper circular initialization. Source is
    # independently rejoined to the sealed VALIDATION index, never trusted input.
    from run_screen_leaf_validation_379 import frozen_sources, verify_replay
    require(kind in ('snapshots', 'temporal'), 'unsupported decoration kind')
    index, output = Path(index).resolve(), Path(output).resolve()
    require(digest(index) == EXPECTED, 'sealed corpus index differs')
    approved = {s['seed']: s for s in frozen_sources(index)}
    require(source.get('seed') in approved and source == approved[source['seed']],
            'decoration source is not exact frozen VALIDATION descriptor')
    require(source['producer_sha'] in PRODUCERS, 'unapproved producer')
    replay = Path(custody['directory'])
    require(verify_replay(replay, source) == custody, 'unverified replay decoration')
    original = replay / ('snapshots.jsonl' if kind == 'snapshots' else 'snapshots.jsonl.temporal.jsonl')
    original_sha = custody['snapshots_sha256'] if kind == 'snapshots' else custody['temporal']['temporal_sha256']
    require(digest(original) == original_sha, 'original artifact changed')
    context = {'schema': CURRENT['schema'], 'domain': 'frozen-334',
               'producerGitSha': source['producer_sha'], 'snapshotSchema': 'screen-leaf-full-state-v1',
               'sourceSeed': source['seed'], 'sourceManifestSha256': source['manifest_sha256'],
               'inputArtifactSha256': original_sha}
    rows = snapshots = 0
    seen = set()
    with original.open() as inp, output.open('x') as out:
        for line in inp:
            row = json.loads(line)
            require(row['sourceSeed'] == source['seed'], 'artifact source mismatch')
            require(not FORBIDDEN.intersection(row), 'original artifact already has import metadata')
            key = identity(row) if kind == 'snapshots' else (row['sourceSeed'], row['branchId'])
            require(key not in seen, 'duplicate original identity'); seen.add(key)
            if kind == 'temporal':
                require(row['schema'] == 'screen_leaf_temporal_v1', 'temporal schema differs')
                envelope = row['forcedPostAction']
                if envelope is not None:
                    require(envelope['branchId'] == row['branchId'], 'nested temporal branch mismatch')
                    require('sourceSeed' not in envelope or envelope['sourceSeed'] == source['seed'],
                            'nested temporal source mismatch')
            else:
                envelope = row
            if envelope is not None:
                require(not FORBIDDEN.intersection(envelope), 'original snapshot already tagged')
                require(envelope['snapshot']['schema'] == context['snapshotSchema'], 'snapshot transport differs')
                require(envelope['snapshot']['game']['seed'] == source['seed'], 'snapshot game seed differs')
                envelope['snapshotSemantics'] = context
                snapshots += 1
            out.write(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')
            rows += 1
    require(rows > 0 and (kind != 'snapshots' or rows == source['decision_rows']), 'decoration population differs')
    require(digest(original) == original_sha, 'original changed while decorating')
    receipt = {'schema': 'screen_leaf_379_import_decoration_v1', 'kind': kind,
               'corpus': str(index), 'corpus_sha256': EXPECTED, 'source': source, 'replay': custody,
               'original': str(original.resolve()), 'original_sha256': original_sha,
               'decorated': str(output), 'decorated_sha256': digest(output),
               'rows': rows, 'snapshot_count': snapshots,
               'helper': str(Path(__file__).resolve()), 'helper_sha256': digest(Path(__file__))}
    receipt_path = Path(str(output) + '.receipt.json')
    write_new(receipt_path, receipt)
    binding = {'receipt': str(receipt_path), 'receipt_sha256': digest(receipt_path)}
    verify_decoration(binding)
    return binding


def verify_decoration(binding):
    path = Path(binding['receipt'])
    require(digest(path) == binding['receipt_sha256'], 'decoration receipt changed')
    r = load(path)
    require(r['schema'] == 'screen_leaf_379_import_decoration_v1', 'decoration schema differs')
    require(r['helper_sha256'] == digest(Path(__file__)) and Path(r['helper']).resolve() == Path(__file__).resolve(),
            'decoration helper differs')
    require(r['source']['split'] == 'VALIDATION' and r['source']['producer_sha'] in PRODUCERS,
            'decoration source forbidden')
    for name, expected in [(r['corpus'], EXPECTED), (r['source']['manifest'], r['source']['manifest_sha256']),
                           (r['original'], r['original_sha256']), (r['decorated'], r['decorated_sha256'])]:
        require(digest(Path(name)) == expected, 'import custody changed: ' + str(name))
    replay = Path(r['replay']['directory'])
    for name, field in [('receipt.json', 'receipt_sha256'), ('result.json', 'result_sha256')]:
        require(digest(replay / name) == r['replay'][field], 'original replay receipt changed')
    return r


def post_input(trajectory):
    post = trajectory['forcedPostAction']
    return {'sourceSeed': trajectory['sourceSeed'], 'branchId': trajectory['branchId'], 'rowIdx': -1,
            'decisionIdx': post['sourceDecisionIdx'], 'features': post['features'],
            'snapshot': post['snapshot'], 'snapshotSemantics': post['snapshotSemantics']}


def bind_selection(path, decorations, temporal=False):
    """Bind a selected mixed-source input to exact decorated rows, no fake tags."""
    path = Path(path).resolve()
    selected = {}
    for line in path.open():
        row = json.loads(line); key = identity(row)
        require(key not in selected, 'duplicate selected import identity'); selected[key] = row
    require(selected, 'empty import selection')
    unmatched = set(selected)
    for binding in decorations:
        r = verify_decoration(binding)
        require(r['kind'] == ('temporal' if temporal else 'snapshots'), 'selection input kind differs')
        with Path(r['decorated']).open() as stream:
            for line in stream:
                row = json.loads(line)
                if temporal:
                    if row['forcedPostAction'] is None: continue
                    row = post_input(row)
                key = identity(row)
                if key in selected:
                    require(key in unmatched and row == selected[key], 'selected row not exact source decoration')
                    unmatched.remove(key)
    require(not unmatched, 'unbound selected snapshot')
    receipt = {'schema': 'screen_leaf_379_import_selection_v1', 'input': str(path),
               'input_sha256': digest(path), 'rows': len(selected), 'decorations': decorations,
               'temporal': temporal, 'helper_sha256': digest(Path(__file__))}
    receipt_path = Path(str(path) + '.receipt.json'); write_new(receipt_path, receipt)
    binding = {'receipt': str(receipt_path), 'receipt_sha256': digest(receipt_path)}
    verify_selection(binding)
    return binding


def verify_selection(binding):
    path = Path(binding['receipt'])
    require(digest(path) == binding['receipt_sha256'], 'selection receipt changed')
    r = load(path)
    require(r['schema'] == 'screen_leaf_379_import_selection_v1' and
            r['helper_sha256'] == digest(Path(__file__)), 'selection schema/helper differs')
    require(digest(Path(r['input'])) == r['input_sha256'], 'selected input changed')
    for decoration in r['decorations']: verify_decoration(decoration)
    return r


def verify_current(path, expected_sha):
    require(digest(Path(path)) == expected_sha, 'native current input changed')
    for line in Path(path).open():
        require(json.loads(line)['snapshotSemantics'] == CURRENT, 'native output lacks exact current tag')


def verify_projected(original, projected):
    """Independent exact phase-only migration oracle for poststate projection."""
    context = original['snapshotSemantics']
    require(context['domain'] == 'frozen-334' and context['producerGitSha'] in PRODUCERS,
            'projection original is not historical')
    require(projected['snapshotSemantics'] == CURRENT and projected.get('snapshotOrigin') == context,
            'projection import origin/current domain differs')
    expected = copy.deepcopy(original['snapshot'])
    game = expected['game']; history = []
    # Pinned enum values from constants/{Relics,Events}.h and GameContext.h.
    if game['screenState'] == 1 and game['curEvent'] == 23:
        relics = game['relics']
        held = bool(relics['relicBits2'] & (1 << (143 - 128)))
        require(held == any(r['id'] == 143 for r in relics['relics']), 'Golden Idol cache/list disagreement')
        phase = 1 if held else 0; options = [2, 3, 4] if held else [0, 1]
        if 'screenContents' in original:
            c = original['screenContents']
            require(c['screen'] == 'event' and c['eventId'] == 23 and c['optionIds'] == options,
                    'Golden Idol original public options differ')
        history = [{'rule': 'frozen334_golden_idol_relic_to_current_phase_v1', 'context': context,
                    'originalPhase': game['info']['phase'], 'adaptedPhase': phase,
                    'changed': game['info']['phase'] != phase, 'historicalOptionIds': options,
                    'originalPublicOptionsPresent': 'screenContents' in original}]
        game['info']['phase'] = phase
    # Stale Smoke Bomb flag left by an event-fight escape that skipped afterBattle().
    if game.get('smokeBombUsed'):
        require(game['screenState'] != 9, 'historical smokeBombUsed inside combat')
        history.append({'rule': 'frozen334_stale_smoke_bomb_flag_clear_v1', 'context': context,
                        'screenState': game['screenState'], 'curEvent': game['curEvent'],
                        'originalSmokeBombUsed': True, 'adaptedSmokeBombUsed': False, 'changed': True})
        game['smokeBombUsed'] = False
    require(projected['snapshot'] == expected, 'projection changed fields beyond exact approved migrations')
    require(projected.get('snapshotImportHistory', []) == history, 'projection migration audit differs')
    require(projected['features'] == original['features'], 'projection public features changed')
    for field in ('sourceSeed', 'branchId', 'rowIdx', 'decisionIdx'):
        require(projected[field] == original[field], 'projection identity changed')
