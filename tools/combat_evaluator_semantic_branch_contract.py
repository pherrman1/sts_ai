#!/usr/bin/env python3
"""Validate observational semantic-branch combat labels and their provenance."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

try:
    from tools.combat_evaluator_contract import EPSILON, LABELS, sha256, validate_label_row
    from tools.ooc_semantic_pipeline_contract import RICH_NAMES, integer, require, validate_corpus as validate_semantic_corpus
except ModuleNotFoundError:
    from combat_evaluator_contract import EPSILON, LABELS, sha256, validate_label_row
    from ooc_semantic_pipeline_contract import RICH_NAMES, integer, require, validate_corpus as validate_semantic_corpus

SCHEMA_VERSION = 'combat_evaluator_semantic_branch_v1'
PREFIX = ['sourceSeed', 'decisionIdx', 'semanticActionIdx', 'semanticKey', 'futureIdentity',
          'branchFightIdx', 'continuationSeed', 'hiddenSeed', 'semanticSource',
          'act', 'floor', 'roomClass', 'encounter', 'teacherId']
HEADER = PREFIX + RICH_NAMES + LABELS


def encounter_names():
    """Use the same public encounter strings as the C++ producer."""
    source = (Path(__file__).resolve().parents[1] / 'include/constants/MonsterEncounters.h').read_text()
    block = source.split('monsterEncounterStrings[] = {', 1)[1].split('};', 1)[0]
    return set(re.findall(r'"([^"\n]+)"', block)) - {'INVALID'}


def _hash(value, length, name):
    require(isinstance(value, str) and re.fullmatch(rf'[0-9a-f]{{{length}}}', value) is not None
            and value != '0' * length, 'invalid ' + name)


def _bound_file(info, name):
    require(isinstance(info, dict) and isinstance(info.get('path'), str) and bool(info['path']),
            'missing ' + name + ' path')
    _hash(info.get('sha256'), 64, name + ' hash')
    path = Path(info['path'])
    require(path.is_file() and sha256(path) == info['sha256'], name + ' hash mismatch')
    return path


def _number(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid ' + name) from exc
    require(math.isfinite(number), 'non-finite ' + name)
    return number


def _branch(row):
    return (integer(row['sourceSeed']), integer(row['decisionIdx']),
            row['semanticKey'], integer(row['futureIdentity']))


def _read_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.reader(stream)
        require(next(reader, []) == HEADER, 'canonical metadata/feature/label order mismatch')
        rows = []
        for line, cells in enumerate(reader, 2):
            require(len(cells) == len(HEADER), f'raw CSV width mismatch at line {line}')
            # Validate the raw cells before making dictionaries: act and floor
            # intentionally appear in both metadata and the state feature block.
            feature_cells = cells[len(PREFIX):-len(LABELS)]
            values = [_number(v, name) for name, v in zip(RICH_NAMES, feature_cells)]
            row = dict(zip(PREFIX, cells[:len(PREFIX)]))
            row.update(zip(LABELS, cells[-len(LABELS):]))
            for name in ('act', 'floor'):
                require(_number(row[name], name) == values[RICH_NAMES.index(name)],
                        'metadata/state ' + name + ' mismatch')
            rows.append(row)
    return rows


def validate_csv(path):
    """Check row shape/targets; use validate_manifest for provenance binding."""
    rows = _read_csv(path)
    encounters = encounter_names()
    keys, seeds, quarantined, teachers = set(), set(), set(), set()
    counts = dict(valid=0, invalid=0, wins=0, deaths=0, ambiguous=0)
    for row in rows:
        for name in PREFIX:
            if name not in ('semanticKey', 'roomClass', 'encounter', 'teacherId'):
                require(integer(row[name]) >= 0, 'negative ' + name)
        require(integer(row['act']) in range(1, 5) and integer(row['floor']) >= 1,
                'invalid combat act/floor')
        require(integer(row['semanticSource']) <= 9, 'invalid semantic source')
        require(integer(row['futureIdentity']) == 0 and integer(row['branchFightIdx']) == 0,
                'H=1 requires futureIdentity=0 and branchFightIdx=0')
        require(row['roomClass'] in ('NORMAL', 'ELITE', 'BOSS', 'OTHER'), 'invalid room class')
        require(row['encounter'] in encounters, 'invalid encounter')
        require(bool(row['teacherId']), 'missing teacher ID')
        require(re.fullmatch(r'ooc:v1:effect=\d+:source=\d+:.+', row['semanticKey']) is not None,
                'invalid semantic key')
        key = _branch(row) + (integer(row['branchFightIdx']),)
        require(key not in keys, 'duplicate semantic branch fight identity')
        keys.add(key)
        seeds.add(key[0])
        teachers.add(row['teacherId'])
        bits = validate_label_row(row)
        require(not (bits['turnCapLoss'] and bits['labelValid']), 'turn-cap row is label-valid')
        require(bits['progressAmbiguous'] == int(bool(bits['trueDeath']) and row['encounter'] == 'Awakened One'),
                'ambiguous progress mask mismatch')
        # These independently computed ratios detect mutually consistent but
        # incorrect fraction/signed-target edits. Preserve V1 epsilon clamps.
        hp, max_hp = float(row['terminalCombatHp']), float(row['terminalCombatMaxHp'])
        require(hp >= 0 and max_hp >= 0, 'negative terminal player HP')
        cur, maximum = float(row['terminalNonMinionCurHp']), float(row['terminalNonMinionMaxHp'])
        win = max(EPSILON, min(1.0, hp / max_hp if max_hp > 0 else EPSILON))
        loss = max(EPSILON, min(1.0, cur / maximum if cur != 0 and maximum != 0 else 0.0))
        require(abs(float(row['winHpFrac']) - win) <= 1e-6, 'win HP ratio mismatch')
        require(abs(float(row['lossRemainingFrac']) - loss) <= 1e-6, 'enemy remaining HP ratio mismatch')
        require(not bits['trueDeath'] or hp == 0, 'true death has positive terminal HP')
        require(not bits['labelValid'] or row['quarantineReason'] == '', 'valid row has quarantine reason')
        valid = bits['labelValid']
        counts['valid'] += valid
        counts['invalid'] += 1 - valid
        counts['wins'] += bits['won'] * valid
        counts['deaths'] += bits['trueDeath'] * valid
        counts['ambiguous'] += bits['progressAmbiguous']
        if not valid:
            quarantined.add(key[0])
    require(len(teachers) <= 1, 'mixed teacher IDs')
    return dict(rows=len(rows), source_seeds=len(seeds), quarantined_source_seeds=len(quarantined),
                counts=counts, feature_count=len(RICH_NAMES), features=RICH_NAMES,
                csv_sha256=sha256(path))


def validate_manifest(manifest):
    require(manifest.get('schema_version') == SCHEMA_VERSION, 'unsupported schema version')
    for key, length in [('producer_git_sha', 40), ('producer_executable_sha256', 64)]:
        _hash(manifest.get(key), length, key)
    csv_path = _bound_file(manifest.get('csv'), 'combat CSV')
    frozen_path = _bound_file(manifest.get('frozen_manifest'), 'frozen manifest')
    semantic_path = _bound_file(manifest.get('semantic_manifest'), 'semantic manifest')
    semantic = json.loads(semantic_path.read_text())
    validate_semantic_corpus(semantic)
    require(Path(semantic['frozen_manifest']['path']).resolve() == frozen_path.resolve()
            and semantic['frozen_manifest']['sha256'] == manifest['frozen_manifest']['sha256'],
            'semantic frozen capture binding mismatch')
    for key in ('producer_git_sha', 'producer_executable_sha256'):
        require(manifest[key] == semantic[key], 'semantic/combat producer mismatch')
    teacher = manifest.get('teacher')
    require(teacher == semantic['combat_teacher'], 'semantic/combat teacher mismatch')
    for artifact in teacher['model_artifacts']:
        _hash(artifact.get('sha256'), 64, 'teacher artifact hash')
    fc = manifest.get('feature_contract')
    require(isinstance(fc, dict) and type(fc.get('count')) is int and fc['count'] == 1017
            and fc.get('state_names') == RICH_NAMES, 'canonical feature contract mismatch')
    require(manifest.get('seed_spec') == {'sourceSeeds': semantic['sampling']['sourceSeeds']},
            'source seed specification mismatch')
    result = validate_csv(csv_path)
    with Path(semantic['csv']['path']).open(newline='', encoding='utf-8') as stream:
        branches = {_branch(r): r for r in csv.DictReader(stream)}
    captured = set()
    for row in _read_csv(csv_path):
        key = _branch(row)
        captured.add(key)
        require(key in branches, 'combat row absent from semantic corpus')
        source = branches[key]
        for name in ('semanticActionIdx', 'continuationSeed', 'hiddenSeed', 'semanticSource'):
            require(integer(row[name]) == integer(source[name]), 'semantic/combat ' + name + ' mismatch')
        require(row['teacherId'] == teacher['teacher_id'], 'combat teacher ID mismatch')
    # H=1 simulation cost accrues only inside an actual playoutBattle call.
    # A zero-cost invalid capture may still be useful for auditing a missing
    # decision hook, so require completeness only in the positive-cost direction.
    require(all(integer(row['silverSimulations']) == 0 or key in captured
                for key, row in branches.items()), 'semantic fight simulations lack a combat row')
    integrity = manifest.get('integrity', {})
    for name, expected in {**result['counts'], **{k: result[k] for k in
                          ('rows', 'source_seeds', 'quarantined_source_seeds')}}.items():
        require(type(integrity.get(name)) is int and integrity[name] == expected,
                'manifest count mismatch: ' + name)
    result['semantic_branches_without_combat'] = len(branches) - result['rows']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_manifest(json.loads(args.manifest.read_text())), sort_keys=True))


if __name__ == '__main__':
    main()
