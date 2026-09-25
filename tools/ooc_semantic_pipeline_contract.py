#!/usr/bin/env python3
"""Fail-closed semantic OOC pilot contract, separate from primitive schema v1."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

try:
    from tools.ooc_pipeline_contract import sha256, validate_teacher
except ModuleNotFoundError:
    from ooc_pipeline_contract import sha256, validate_teacher

SCHEMA_VERSION = 'ooc_semantic_manifest_v1'
ROW_SCHEMA_VERSION = 'ooc_semantic_action_v1'
SOURCE_FIELDS = ('sourceSeed', 'decisionIdx', 'act', 'floor', 'screen', 'semanticSchemaVersion')
ACTION_FIELDS = ('semanticActionIdx', 'semanticKey', 'semanticEffect', 'semanticSource', 'semanticPayload')
REQUIRED_COLUMNS = SOURCE_FIELDS + ACTION_FIELDS + (
    'siblingCount', 'futureIdentity', 'continuationSeed', 'hiddenSeed', 'H', 'budgetSchedule', 'executedPrimitiveBits',
    'survivedPrefix', 'continuationValue', 'qProduct', 'silverSimulations',
    'combatDecisions', 'transactionSubdecisions', 'transactionDecisions', 'cpuMs', 'wallMs', 'teacherId', 'valid', 'quarantineReason', 'richRow')


# Versioned adapter over run_features.cpp::richStateHeader; order is wire schema.
RICH_NAMES = (
    'ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor,'
    'blueKey,greenKey,redKey,potionCount,potionCapacity,bossId,nextEliteId,nextFight0,'
    'nextFight1,nextFight2,remElites,remFights,monOffset,eliteOffset,pvShop,pvRest,'
    'pvEvent,pvElite,pvMonster,pvTreasure,bottledAtkId,bottledSkillId,bottledPowId'
).split(',') + [f'{prefix}{i}' for prefix, count in [('d',372),('u',372),('r',181),('pot',48)] for i in range(count)] + (
    'fmDElite,fmDRest,fmDShop,fmDBoss,fmCElite,fmCRest,fmCShop,fmCEvent,fmCMonster,fmCTreasure,curMapX,curMapY'
).split(',')
MASKED_RICH_NAMES = ('nextEliteId', 'nextFight0', 'nextFight1', 'nextFight2')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    require(not isinstance(value, bool), 'boolean where integer required')
    require(re.fullmatch(r'-?\d+', str(value)) is not None, 'malformed integer')
    return int(value)


def payload(value):
    if isinstance(value, str):
        def unique(pairs):
            result = {}
            for key, item in pairs:
                require(key not in result, 'duplicate payload JSON key')
                result[key] = item
            return result
        value = json.loads(value, object_pairs_hook=unique)
    require(isinstance(value, dict) and bool(value), 'semanticPayload must be a typed JSON object')
    # Round-trip disallows NaN/Infinity, including nested values.
    json.dumps(value, allow_nan=False)
    return value


def canonical_payload_suffix(p):
    """Mirror the public v1 wire key, rejecting untyped or lossy JSON payloads."""
    def fields(obj, names):
        require(isinstance(obj, dict) and set(obj) == set(names.split()), 'unexpected/missing typed payload fields')
    def num(obj, name):
        require(type(obj[name]) is int, 'payload numeric fields must be JSON integers')
        return obj[name]
    def boolean(obj, name):
        require(type(obj[name]) is bool, 'payload flags must be JSON booleans')
        return int(obj[name])
    def card(c):
        fields(c, 'id misc upgraded')
        return f"{num(c,'id')},{num(c,'misc')},{boolean(c,'upgraded')}"
    def deck(c):
        fields(c, 'id misc upgraded bottle occurrence')
        require(-1 <= num(c, 'bottle') <= 2 and num(c, 'occurrence') >= 0, 'invalid deck target')
        return f":card={num(c,'id')}:misc={num(c,'misc')}:upgraded={boolean(c,'upgraded')}:bottle={num(c,'bottle')}:occurrence={num(c,'occurrence')}"
    def entity(e):
        kind = e.get('type')
        if kind == 'none':
            fields(e, 'type')
            return 'none'
        fields(e, 'type value')
        require(kind in ('card', 'relic', 'potion', 'gold', 'key'), 'unknown entity type')
        return kind + ',' + (card(e['value']) if kind == 'card' else str(num(e, 'value')))
    kind = p.get('type')
    if kind == 'none':
        fields(p, 'type')
        return ':none'
    if kind == 'deck_card':
        fields(p, 'type card')
        return deck(p['card'])
    if kind == 'transaction':
        fields(p, 'type card event option expectedGoldCost')
        return f":transaction:event={num(p,'event')}:option={num(p,'option')}:cost={num(p,'expectedGoldCost')}" + deck(p['card'])
    if kind == 'selector':
        fields(p, 'type selectorType requiredPicks completedPicks target')
        required, completed = num(p, 'requiredPicks'), num(p, 'completedPicks')
        require(0 <= completed < required, 'invalid sequential selector pick')
        t = p['target']
        if t.get('type') == 'deck_card':
            suffix = canonical_payload_suffix(t)
        else:
            fields(t, 'type card occurrence')
            require(t['type'] == 'candidate', 'unknown selector target type')
            suffix = ':candidate=' + card(t['card']) + f":occurrence={num(t,'occurrence')}"
        return f":selector={num(p,'selectorType')}:required={required}:completed={completed}" + suffix
    if kind == 'reward':
        fields(p, 'type entity cardGroup groupOccurrence occurrence sapphirePaired')
        require(isinstance(p['cardGroup'], list), 'cardGroup must be an array')
        group = ''.join(card(c) + ';' for c in p['cardGroup'])
        return ':reward=' + entity(p['entity']) + f":group=[{group}]:groupOccurrence={num(p,'groupOccurrence')}:occurrence={num(p,'occurrence')}:sapphirePaired={boolean(p,'sapphirePaired')}"
    if kind == 'shop':
        fields(p, 'type entity expectedPrice occurrence')
        return ':shop=' + entity(p['entity']) + f":price={num(p,'expectedPrice')}:occurrence={num(p,'occurrence')}"
    if kind == 'event':
        fields(p, 'type event option')
        return f":event={num(p,'event')}:option={num(p,'option')}"
    if kind == 'relic':
        fields(p, 'type relic occurrence')
        return f":relic={num(p,'relic')}:occurrence={num(p,'occurrence')}"
    raise ValueError('unknown semantic payload type')


def action_identity(action):
    effect, source = integer(action['semanticEffect']), integer(action['semanticSource'])
    require(0 <= effect <= 28 and 0 <= source <= 9, 'unknown semantic effect/source')
    key = action['semanticKey']
    require(isinstance(key, str) and re.fullmatch(
        rf'ooc:v1:effect={effect}:source={source}:(?:none|card=.+|transaction:event=.+|selector=.+|reward=.+|shop=.+|event=-?\d+:option=-?\d+|relic=-?\d+:occurrence=\d+)', key) is not None,
        'malformed semanticKey or effect/source mismatch')
    typed = payload(action['semanticPayload'])
    require(key == f'ooc:v1:effect={effect}:source={source}' + canonical_payload_suffix(typed), 'semantic key and typed payload disagree')
    return integer(action['semanticActionIdx']), key, effect, source, typed


def validate_manifest(manifest, verify_csv=True):
    require(manifest.get('schema_version') == SCHEMA_VERSION, 'wrong semantic manifest schema')
    require(manifest.get('row_schema_version') == ROW_SCHEMA_VERSION, 'wrong semantic row schema')
    for field, length in [('producer_git_sha', 40), ('producer_executable_sha256', 64)]:
        require(re.fullmatch(rf'[0-9a-f]{{{length}}}', str(manifest.get(field, ''))) is not None,
                f'missing or malformed {field}')
        require(manifest[field] != '0' * length, f'placeholder {field}')
    validate_teacher(manifest['combat_teacher'])
    teacher = manifest['combat_teacher']
    require(teacher['git_sha'] == manifest['producer_git_sha'] and
            teacher['executable_sha256'] == manifest['producer_executable_sha256'],
            'producer and frozen teacher identity mismatch')
    require(teacher['combat_backend'] == 'native_silver' and teacher['rng_regime'] == 'project_fair',
            'semantic pilot requires frozen project-fair Silver teacher')
    runtime = manifest.get('runtime')
    require(isinstance(runtime, dict), 'missing frozen runtime binding')
    environment = runtime.get('environment')
    require(isinstance(environment, dict) and
            all(isinstance(k, str) and (v is None or isinstance(v, str)) for k, v in environment.items()),
            'runtime.environment must bind names to strings or null')
    require(environment.get('STS_NATIVE_OOC') == '1' and
            all(environment.get(k) == v for k, v in teacher['environment'].items()),
            'runtime environment disagrees with frozen teacher/native OOC contract')
    models = runtime.get('oocModels')
    require(isinstance(models, list) and len(models) == 2 and
            all(isinstance(m, dict) for m in models) and
            {m.get('role') for m in models} == {'floor', 'win'}, 'missing floor/win runtime model identities')
    for model in models:
        require(isinstance(model.get('path'), str) and bool(model['path']) and
                re.fullmatch(r'[0-9a-f]{64}', str(model.get('sha256', ''))) is not None and
                model['sha256'] != '0' * 64, 'missing or placeholder runtime model path/hash')
    sampling = manifest['sampling']
    require(sampling.get('rule') == 'policy_independent_reservoir_eligible_semantic_decisions' and
            type(sampling.get('version')) is int and sampling['version'] == 1 and
            type(sampling.get('maxDecisionsPerSeed')) is int and sampling['maxDecisionsPerSeed'] == 1 and
            sampling.get('excludeNeow') is True, 'wrong frozen sampling rule/version')
    seeds = sampling['sourceSeeds']
    require(isinstance(seeds, list) and 1 <= len(seeds) <= 16 and
            all(type(seed) is int and seed >= 0 for seed in seeds) and len(set(seeds)) == len(seeds), 'invalid pilot source seed list')
    state_features = manifest['stateFeatures']
    require(state_features == {'schema':'rich_state_masked_hidden_v1', 'header':','.join(RICH_NAMES),
                               'maskedColumns':list(MASKED_RICH_NAMES)}, 'wrong rich state adapter contract')
    evaluation = manifest['evaluation']
    require(type(evaluation['H']) is int, 'H must be a JSON integer')
    h = integer(evaluation['H'])
    budgets = evaluation['budgetSchedule']
    futures = evaluation['futureIdentities']
    require(h == 1 and isinstance(budgets, list) and len(budgets) == h and
            all(type(b) is int and b == 10000 for b in budgets), 'invalid H/frozen teacher budget schedule')
    require(isinstance(futures, list) and futures == [0] and type(futures[0]) is int and
            len(set(map(str, futures))) == len(futures) and all(integer(f) >= 0 for f in futures),
            'invalid future identity coverage')
    require(evaluation['rngRegime'] == teacher['rng_regime'], 'continuation RNG regime mismatch')
    seen = set()
    require(isinstance(manifest['decisions'], list), 'decisions must be a list')
    for decision in manifest['decisions']:
        require(decision.get('supported') is True and decision.get('complete') is True,
                'unsupported/incomplete source decision')
        seed = integer(decision['sourceSeed'])
        require(seed in seeds, 'decision seed outside frozen source seeds')
        require(seed >= 0 and integer(decision['floor']) >= 1 and integer(decision['decisionIdx']) >= 0 and
                integer(decision['screen']) in (1, 2, 3, 4, 6, 7, 8), 'terminal/unsupported source metadata')
        require(seed not in seen, 'multiple decisions per source seed')
        seen.add(seed)
        for field in SOURCE_FIELDS:
            integer(decision[field])
        require(integer(decision['semanticSchemaVersion']) == 1, 'wrong semantic action schema')
        actions = decision['actions']
        require(isinstance(actions, list) and len(actions) >= 2, 'source decision requires complete siblings')
        identities = [action_identity(a) for a in actions]
        require([a[0] for a in identities] == list(range(len(actions))), 'non-contiguous canonical action indices')
        keys = [a[1] for a in identities]
        require(keys == sorted(set(keys)), 'semantic keys must be unique and canonically sorted')
        if 'siblingCount' in decision:
            require(integer(decision['siblingCount']) == len(actions), 'frozen siblingCount mismatch')
    if verify_csv:
        frozen = manifest['frozen_manifest']
        frozen_path = Path(frozen['path'])
        require(frozen_path.is_file() and sha256(frozen_path) == frozen['sha256'], 'frozen capture manifest/hash mismatch')
        captured = json.loads(frozen_path.read_text())
        for key in ('schema_version', 'row_schema_version', 'producer_git_sha', 'producer_executable_sha256',
                    'combat_teacher', 'sampling', 'stateFeatures', 'evaluation', 'decisions', 'runtime'):
            require(captured.get(key) == manifest.get(key), 'evaluated contract differs from frozen capture manifest')
        info = manifest['csv']
        require(re.fullmatch(r'[0-9a-f]{64}', str(info.get('sha256', ''))) is not None, 'missing CSV SHA256')
        path = Path(info['path'])
        require(path.is_file() and sha256(path) == info['sha256'], 'CSV/hash mismatch')


def validate_corpus(manifest):
    validate_manifest(manifest)
    with Path(manifest['csv']['path']).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        require(len(header) == len(set(header)) and set(REQUIRED_COLUMNS) <= set(header), 'missing/duplicate semantic CSV columns')
        require(set(header) <= set(REQUIRED_COLUMNS) | {'denseReferenceValue', 'terminalWon'}, 'unexpected semantic CSV columns')
        rows = list(reader)
    decisions = {(str(d['sourceSeed']), str(d['decisionIdx'])): d for d in manifest['decisions']}
    evaluation = manifest['evaluation']
    futures = set(map(str, evaluation['futureIdentities']))
    seen = set()
    equal_futures = {}
    # validate_manifest binds this header exactly to the versioned RICH_NAMES.
    state_names = manifest['stateFeatures']['header'].split(',')
    for row in rows:
        state = row['richRow'].split(',')
        require(len(state) == len(state_names) and all(math.isfinite(float(v)) for v in state), 'invalid canonical rich state')
        require(all(float(state[state_names.index(k)]) == -1 for k in MASKED_RICH_NAMES), 'hidden future feature leakage')
        require(None not in row and all(v is not None for v in row.values()), 'malformed CSV row')
        decision_key = row['sourceSeed'], row['decisionIdx']
        require(decision_key in decisions, 'unexpected source decision')
        decision = decisions[decision_key]
        require(all(integer(row[k]) == integer(decision[k]) for k in SOURCE_FIELDS), 'source metadata mismatch')
        action = action_identity(row)
        require(0 <= action[0] < len(decision['actions']) and
                action == action_identity(decision['actions'][action[0]]), 'action identity/payload differs from frozen manifest')
        require(integer(row['siblingCount']) == len(decision['actions']), 'inconsistent siblingCount')
        require(row['futureIdentity'] in futures, 'unexpected future identity')
        require(integer(row['H']) == evaluation['H'] and json.loads(row['budgetSchedule']) == evaluation['budgetSchedule'],
                'mixed H/budget schedule')
        future_key = decision_key + (row['futureIdentity'],)
        seeds = (integer(row['continuationSeed']), integer(row['hiddenSeed']))
        require(equal_futures.setdefault(future_key, seeds) == seeds, 'unequal sibling hidden/continuation futures')
        key = decision_key + (row['semanticKey'], row['futureIdentity'], row['H'])
        require(key not in seen, 'duplicate semantic row identity')
        seen.add(key)
        require(row['teacherId'] == manifest['combat_teacher']['teacher_id'], 'mixed teacher IDs')
        valid = integer(row['valid'])
        require(valid in (0, 1), 'invalid validity flag')
        require((valid == 1 and row['quarantineReason'] == '') or (valid == 0 and row['quarantineReason'] != ''),
                'invalid/quarantined row presented as valid')
        trace = json.loads(row['executedPrimitiveBits'])
        require(isinstance(trace, list) and len(trace) > 0 and all(0 <= integer(v) <= 2**32-1 for v in trace), 'invalid primitive trace')
        for field in ('silverSimulations', 'combatDecisions', 'transactionSubdecisions', 'transactionDecisions'):
            require(integer(row[field]) >= 0, f'invalid {field}')
        for field in ('cpuMs', 'wallMs'):
            require(math.isfinite(float(row[field])) and float(row[field]) >= 0, f'invalid {field}')
        if valid:
            require(integer(row['transactionDecisions']) <= min(integer(row['combatDecisions']), integer(row['transactionSubdecisions'])), 'invalid transaction overlap accounting')
            roots = integer(row['combatDecisions']) + integer(row['transactionSubdecisions']) - integer(row['transactionDecisions'])
            require(roots >= 0 and integer(row['silverSimulations']) == roots * 10000, 'Silver simulation/root accounting mismatch')
            survived = integer(row['survivedPrefix'])
            value, product = float(row['continuationValue']), float(row['qProduct'])
            require(survived in (0, 1) and math.isfinite(value) and 0 <= value <= 1 and
                    math.isfinite(product) and math.isclose(product, survived * value, rel_tol=1e-6, abs_tol=1e-8),
                    'inconsistent continuation target accounting')
            for field in ('denseReferenceValue', 'terminalWon'):
                if row.get(field, '') not in ('', '-1'):
                    number = float(row[field])
                    require(math.isfinite(number) and (field != 'terminalWon' or number in (0, 1)), f'invalid {field}')
    expected = {(str(d['sourceSeed']), str(d['decisionIdx']), a['semanticKey'], str(f), str(evaluation['H']))
                for d in manifest['decisions'] for a in d['actions'] for f in evaluation['futureIdentities']}
    require(seen == expected, 'missing siblings or incomplete future coverage')
    require(integer(manifest['integrity']['rows']) == len(rows), 'manifest row count mismatch')
    return {'rows': len(rows), 'decisions': len(decisions), 'valid': sum(integer(r['valid']) for r in rows),
            'quarantined': sum(1 - integer(r['valid']) for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'validate-corpus'])
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if args.command == 'check':
        validate_manifest(manifest, verify_csv=False)
        print('semantic frozen manifest: OK')
    else:
        print(json.dumps(validate_corpus(manifest), sort_keys=True))


if __name__ == '__main__':
    main()
