"""Synthetic contracts only: hashes/teacher below are never live pilot evidence."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.ooc_semantic_pipeline_contract import (
    REQUIRED_COLUMNS, ROW_SCHEMA_VERSION, SCHEMA_VERSION, RICH_NAMES, MASKED_RICH_NAMES, sha256,
    validate_manifest, validate_corpus, canonical_payload_suffix, action_identity,
)


class TestSemanticPipeline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.csv'
        search = dict(simulation_budgets=[10000], exploration_parameter=25.0,
                      exploration_parameter_chance=25.0, chance_widening_c=3.7028,
                      chance_widening_alpha=0.52389, end_turn_widening_c=3.7028,
                      end_turn_widening_alpha=0.52389, reuse_cap_mode='allocated',
                      reuse_cap=32768, sequential_halving=False, pruning=False,
                      learned_visit_puct=False, direct_learned_leaf=False, adaptive=False)
        environment = dict(STS_FAIR='1', STS_SEARCHER3='0', STS_SILVER_SEARCH='1',
                           STS_SILVER_EXACT_ROOT_BUDGETS='1', STS_SILVER_REUSE_CAP_MODE='allocated',
                           STS_SILVER_ADAPTIVE='0', STS_SILVER_VNET_LEAF_DIRECT='0')
        teacher = dict(teacher_id='synthetic-only', git_sha='a'*40, executable_sha256='b'*64,
                       combat_backend='native_silver', rng_regime='project_fair', search_configuration=search,
                       environment=environment, model_artifacts=[dict(role='floor', path='synthetic', sha256='c'*64)])
        actions = [dict(semanticActionIdx=i, semanticKey=f'ooc:v1:effect=26:source=5:event=17:option={i}',
                        semanticEffect=26, semanticSource=5, semanticPayload={'type':'event','event':17,'option':i}) for i in range(2)]
        decision = dict(sourceSeed=10, decisionIdx=2, act=1, floor=7, screen=3,
                        semanticSchemaVersion=1, supported=True, complete=True, actions=actions)
        self.manifest = dict(schema_version=SCHEMA_VERSION, row_schema_version=ROW_SCHEMA_VERSION,
                             producer_git_sha='a'*40, producer_executable_sha256='b'*64, combat_teacher=teacher,
                             runtime={'environment':dict(environment, STS_NATIVE_OOC='1'),
                                      'oocModels':[dict(role=role,path='synthetic-'+role,sha256='d'*64) for role in ('floor','win')]},
                             sampling={'rule':'policy_independent_reservoir_eligible_semantic_decisions','version':1,'sourceSeeds':[10],'maxDecisionsPerSeed':1,'excludeNeow':True},
                             stateFeatures={'schema':'rich_state_masked_hidden_v1','header':','.join(RICH_NAMES),'maskedColumns':list(MASKED_RICH_NAMES)},
                             evaluation={'H':1,'budgetSchedule':[10000],'futureIdentities':[0], 'rngRegime':'project_fair'},
                             decisions=[decision], integrity={'rows':2})
        self.rows = []
        for action in actions:
            row = {k:decision[k] for k in ('sourceSeed','decisionIdx','act','floor','screen','semanticSchemaVersion')}
            row.update(action)
            row['semanticPayload'] = json.dumps(action['semanticPayload'])
            row.update(siblingCount=2, futureIdentity=0, continuationSeed=20, hiddenSeed=30, H=1,
                       budgetSchedule='[10000]', executedPrimitiveBits='[123]', survivedPrefix=1,
                       continuationValue=.4, qProduct=.4, silverSimulations=10000, combatDecisions=1,
                       transactionSubdecisions=0, transactionDecisions=0, cpuMs=10, wallMs=11, teacherId='synthetic-only', valid=1, quarantineReason='')
            row.update(richRow=','.join('-1' if n in MASKED_RICH_NAMES else '0' for n in RICH_NAMES))
            self.rows.append(row)

    def write(self):
        with self.path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        frozen = Path(self.temp.name) / 'capture.json'
        frozen.write_text(json.dumps({k:v for k,v in self.manifest.items() if k not in ('csv','integrity','frozen_manifest')}))
        self.manifest['frozen_manifest'] = {'path':str(frozen),'sha256':sha256(frozen)}
        self.manifest['csv'] = {'path':str(self.path), 'sha256':sha256(self.path)}

    def test_round_trip_and_clean_complete_corpus(self):
        self.write()
        with self.path.open(newline='') as stream:
            self.assertNotIn('richStateHeader', next(csv.reader(stream)))
        restored = json.loads(json.dumps(self.manifest))
        validate_manifest(restored)
        self.assertEqual(validate_corpus(restored), {'rows':2,'decisions':1,'valid':2,'quarantined':0})

    def test_manifest_negative_contracts(self):
        self.write()
        changes = [lambda m:m.update(schema_version='ooc_pipeline_v1'),
                   lambda m:m.update(row_schema_version='old'),
                   lambda m:m.pop('producer_git_sha'),
                   lambda m:m.pop('producer_executable_sha256'),
                   lambda m:m['decisions'][0].update(supported=False),
                   lambda m:m['decisions'][0].update(complete=False),
                   lambda m:m['decisions'][0].update(semanticSchemaVersion=2),
                   lambda m:m['decisions'][0]['actions'][0].update(semanticKey='primitive:123'),
                   lambda m:m['decisions'][0]['actions'][0].update(semanticActionIdx=7),
                   lambda m:m['decisions'][0]['actions'].reverse(),
                   lambda m:m['decisions'][0]['actions'].append(m['decisions'][0]['actions'][0]),
                   lambda m:m['decisions'].append(copy.deepcopy(m['decisions'][0])),
                   lambda m:m['combat_teacher']['search_configuration'].update(simulation_budgets=[100]),
                   lambda m:m['evaluation'].update(rngRegime='known_rng'),
                   lambda m:m.pop('runtime'),
                   lambda m:m['runtime'].pop('environment'),
                   lambda m:m['runtime']['environment'].update(STS_NATIVE_OOC='0'),
                   lambda m:m['runtime']['environment'].pop('STS_SILVER_ADAPTIVE'),
                   lambda m:m['runtime']['oocModels'].pop(),
                   lambda m:m['runtime']['oocModels'][0].update(sha256='0'*64),
                   lambda m:m.update(producer_git_sha='0'*40),
                   lambda m:m.update(producer_executable_sha256='0'*64),
                   lambda m:m['evaluation'].update(futureIdentities=[1]),
                   lambda m:m['evaluation'].update(futureIdentities=[False]),
                   lambda m:m['evaluation'].update(H=True),
                   lambda m:m['sampling'].update(version=True),
                   lambda m:m['stateFeatures'].update(header=','.join(reversed(RICH_NAMES))),
                   lambda m:m['stateFeatures'].update(header=','.join(RICH_NAMES[:-1]))]
        for change in changes:
            with self.subTest(change=change):
                broken = copy.deepcopy(self.manifest)
                change(broken)
                with self.assertRaises((ValueError, KeyError)):
                    validate_manifest(broken)

    def test_csv_negative_contracts(self):
        changes = [lambda rows:rows.pop(), lambda rows:rows.append(copy.deepcopy(rows[0])),
                   lambda rows:rows[0].update(siblingCount=3),
                   lambda rows:rows[0].update(semanticActionIdx=1),
                   lambda rows:rows[0].update(semanticSchemaVersion=2),
                   lambda rows:rows[0].update(semanticPayload='{"event":17,"option":8}'),
                   lambda rows:rows[0].update(semanticPayload='{"event":17,"event":17}'),
                   lambda rows:rows[0].update(teacherId='another'),
                   lambda rows:rows[0].update(H=2),
                   lambda rows:rows[0].update(budgetSchedule='[100]'),
                   lambda rows:rows[0].update(futureIdentity=1),
                   lambda rows:rows[0].update(hiddenSeed=31),
                   lambda rows:rows[0].update(continuationSeed=21),
                   lambda rows:rows[0].update(quarantineReason='health failure'),
                   lambda rows:rows[0].update(valid=0),
                   lambda rows:rows[0].update(qProduct=.7),
                   lambda rows:rows[0].update(executedPrimitiveBits='[]'),
                   lambda rows:rows[0].update(cpuMs='nan'),
                   lambda rows:rows[0].update(transactionDecisions=1),
                   lambda rows:rows[0].update(silverSimulations=9999),
                   lambda rows:rows[0].update(richRow='0'),
                   lambda rows:rows[0].update(richRow=rows[0]['richRow']+',0'),
                   lambda rows:rows[0].update(richRow=','.join('0' for _ in RICH_NAMES))]
        original = copy.deepcopy(self.rows)
        for change in changes:
            with self.subTest(change=change):
                self.rows = copy.deepcopy(original)
                change(self.rows)
                self.write()
                with self.assertRaises(ValueError):
                    validate_corpus(self.manifest)

    def test_lossless_typed_payload_variants(self):
        card = {'id':25, 'misc':0, 'upgraded':False}
        deck = dict(card, bottle=-1, occurrence=0)
        cases = [
            ({'type':'none'}, ':none'),
            ({'type':'deck_card', 'card':deck}, ':card=25:misc=0:upgraded=0:bottle=-1:occurrence=0'),
            ({'type':'transaction', 'card':deck, 'event':17, 'option':0, 'expectedGoldCost':75},
             ':transaction:event=17:option=0:cost=75:card=25:misc=0:upgraded=0:bottle=-1:occurrence=0'),
            ({'type':'selector', 'selectorType':3, 'requiredPicks':3, 'completedPicks':1,
              'target':{'type':'deck_card', 'card':deck}},
             ':selector=3:required=3:completed=1:card=25:misc=0:upgraded=0:bottle=-1:occurrence=0'),
            ({'type':'selector', 'selectorType':4, 'requiredPicks':1, 'completedPicks':0,
              'target':{'type':'candidate','card':card,'occurrence':0}},
             ':selector=4:required=1:completed=0:candidate=25,0,0:occurrence=0'),
            ({'type':'reward', 'entity':{'type':'card','value':card}, 'cardGroup':[card],
              'groupOccurrence':0, 'occurrence':0, 'sapphirePaired':False},
             ':reward=card,25,0,0:group=[25,0,0;]:groupOccurrence=0:occurrence=0:sapphirePaired=0'),
            ({'type':'shop','entity':{'type':'relic','value':25}, 'expectedPrice':50,'occurrence':0},
             ':shop=relic,25:price=50:occurrence=0'),
            ({'type':'relic','relic':25,'occurrence':0}, ':relic=25:occurrence=0'),
            ({'type':'event','event':17,'option':0}, ':event=17:option=0')]
        for typed, expected in cases:
            with self.subTest(type=typed['type']):
                self.assertEqual(canonical_payload_suffix(typed), expected)
                action = dict(semanticActionIdx=0, semanticEffect=0, semanticSource=0,
                              semanticKey='ooc:v1:effect=0:source=0'+expected, semanticPayload=typed)
                self.assertEqual(action_identity(action)[4], typed)
                action['semanticPayload'] = dict(typed, unexpectedPrimitiveIndex=0)
                with self.assertRaises(ValueError):
                    action_identity(action)
        malformed = {'type':'deck_card', 'card':dict(deck, upgraded=0)}
        with self.assertRaisesRegex(ValueError, 'boolean'):
            canonical_payload_suffix(malformed)

    def test_append_only_discard_potion_identity(self):
        typed = dict(type="reward",entity=dict(type="potion",value=7),cardGroup=[],
                     groupOccurrence=0,occurrence=1,sapphirePaired=False)
        action = dict(semanticActionIdx=0,semanticEffect=29,semanticSource=7,
                      semanticKey="ooc:v1:effect=29:source=7"+canonical_payload_suffix(typed),
                      semanticPayload=typed)
        self.assertEqual(action_identity(action)[2:4], (29,7))
        action["semanticEffect"] = 30
        with self.assertRaisesRegex(ValueError,"unknown semantic effect"):
            action_identity(action)

    def test_hash_binding(self):
        self.write()
        with self.path.open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'hash'):
            validate_corpus(self.manifest)

    def test_frozen_capture_hash_and_identity_binding(self):
        self.write()
        frozen = Path(self.manifest['frozen_manifest']['path'])
        frozen.write_text(frozen.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'capture manifest/hash'):
            validate_corpus(self.manifest)
        self.write()
        self.manifest['decisions'][0]['floor'] = 8
        with self.assertRaisesRegex(ValueError, 'differs from frozen'):
            validate_corpus(self.manifest)

    def test_missing_future_coverage(self):
        self.write()
        self.manifest['evaluation']['futureIdentities'] = [0, 1]
        with self.assertRaisesRegex(ValueError, 'coverage|future'):
            validate_corpus(self.manifest)

    def test_quarantine_is_explicit(self):
        self.rows[0].update(valid=0, quarantineReason='synthetic health failure')
        self.write()
        self.assertEqual(validate_corpus(self.manifest)['quarantined'], 1)


if __name__ == '__main__':
    unittest.main()
