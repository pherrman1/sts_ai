"""Seed-free native parity against the frozen Python RNG/relic contracts."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools import combat_transition_rng_audit as rng
from tools import combat_transition_relic_legality as relic
from tools import combat_transition_surrogate as base

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "one_combat/combat_transition_native_contract.h"
#include <iostream>
#include "constants/CardPools.h"
int main() {
 using namespace one_combat; using nlohmann::json;
 for(std::string line;std::getline(std::cin,line);) {try {auto j=json::parse(line);
 if(j["kind"]=="pools") {int hits=0;
 for(int cc=0;cc<4;++cc) {auto c=static_cast<sts::CharacterClass>(cc);
 for(int i=0;i<sts::CombatCardPool::getPoolSize(c);++i)hits+=sts::CombatCardPool::getCardAt(c,i)==sts::CardId::ALCHEMIZE;
 for(int t=0;t<3;++t){auto type=static_cast<sts::CardType>(t);for(int i=0;i<sts::CombatTypeCardPool::getPoolSize(c,type);++i)hits+=sts::CombatTypeCardPool::getCardAt(c,type,i)==sts::CardId::ALCHEMIZE;}}
 for(int i=0;i<sts::CombatColorlessCardPool::getPoolSize();++i)hits+=sts::CombatColorlessCardPool::getCardAt(i)==sts::CardId::ALCHEMIZE;
 std::cout<<json(hits)<<'\n';}
 else if(j["kind"]=="support") {CombatPredictorInputV1 pi;CombatTransitionPersistentState pre;NativeComposedDomain d;
 auto &g=pi.globals;auto v=j["pi"]["globals"];
#define G(name) g.name=v.at(#name).get<decltype(g.name)>()
 G(characterClass);G(curHp);G(maxHp);G(encounter);G(roomClass);G(lastRoom);G(potionCapacity);G(potionCount);G(potionKeepValue);
#undef G
 for(auto c:j["pi"]["cards"])pi.cards.push_back({c["cardId"],c["upgraded"],c["misc"],c["bottleBinding"]});
 for(auto r:j["pi"]["relics"])pi.relics.push_back({r["relicId"],r["data"],r["orderIndex"]});
 for(auto p:j["pi"]["potions"])pi.potions.push_back({p["slot"],p["potionId"]});
 auto p=j["pre"];
#define P(name) pre.name=p.at(#name).get<decltype(pre.name)>()
 P(curHp);P(maxHp);P(potionCapacity);P(potionCount);P(potions);P(smokeBombUsed);P(stolenGold);
#undef P
 for(auto r:p["relics"])pre.relics.push_back({r["id"],r["data"]});
 for(int i=0;i<6;++i){auto r=p["combatRng"][i];pre.combatRng[i]={r["counter"],r["seed0"],r["seed1"]};}
 d.ready=true;d.preCurHpRange={1,161};d.preMaxHpRange={24,172};for(int i=-160;i<144;++i)d.hpClasses.push_back(i);
 d.maxHpClasses={0,3};d.maxHpDeltaValues={0,3};d.trainedGroups={"turns","attacks","cards","shuffles"};
 std::cout<<json(nativeComposedSupportReasons(pi,pre,d))<<'\n';}
 else if(j["kind"]=="rng") {auto p=j["pre"];auto s=replayNativeComposedMisc({p["counter"],p["seed0"],p["seed1"]},j["encounter"]);std::cout<<json{{"counter",s.counter},{"seed0",s.seed0},{"seed1",s.seed1}}<<'\n';}
 else {std::vector<CombatTransitionRelicState> rs;for(auto r:j["pre"])rs.push_back({r["id"],r["data"]});auto out=reconstructNativeComposedRelics(rs,j["residues"].get<std::map<std::string,int>>(),j["encounter"]);json result=json::array();for(auto r:out)result.push_back({{"id",r.id},{"data",r.data}});std::cout<<result<<'\n';}
 }catch(const std::exception&e){std::cout<<json{{"error",e.what()}}<<'\n';}}
}
'''

class NativeContractParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        source = Path(cls.tmp.name) / 'probe.cpp'
        source.write_text(HARNESS)
        cls.exe = Path(cls.tmp.name) / 'probe'
        subprocess.run(['g++','-std=c++20','-Iinclude','-Iextern','-Iapps',str(source),
                        'apps/one_combat/combat_transition_native_contract.cpp','-o',str(cls.exe)],cwd=ROOT,check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def probe(self, rows):
        result = subprocess.run([str(self.exe)],input=''.join(json.dumps(r)+'\n' for r in rows),text=True,capture_output=True,check=True)
        return [json.loads(r) for r in result.stdout.splitlines()]

    def test_combat_pools_cannot_generate_alchemize(self):
        self.assertEqual(self.probe([dict(kind='pools')]), [0])

    def test_potion_generation_support_parity(self):
        import copy
        from tools.test_combat_transition_composed import ComposedTest, FakeModels
        from tools import combat_transition_composed as composed
        ComposedTest.setUpClass()
        fixture = ComposedTest()
        pre,pi = fixture.state()
        rows,expected = [],[]
        for name in ('BANE','FOREIGN_INFLUENCE','DISCOVERY','DISTRACTION','CHRYSALIS',
                     'METAMORPHOSIS','CREATIVE_AI','MAGNETISM','ALCHEMIZE'):
            candidate=copy.deepcopy(pi);candidate['cards'][0]['cardId']=base._CARD_IDS[name]
            reasons=composed.full_support_reasons(pre,candidate,FakeModels())
            self.assertEqual('potion_not_certified' in reasons,name=='ALCHEMIZE')
            rows.append(dict(kind='support',pre=pre,pi=candidate));expected.append(reasons)
        for name in ('DEAD_BRANCH','NILRYS_CODEX'):
            candidate=copy.deepcopy(pi);state=copy.deepcopy(pre)
            candidate['relics']=[dict(relicId=base._RELIC_IDS[name],data=0,orderIndex=0)]
            state['relics']=[dict(id=base._RELIC_IDS[name],data=0)]
            rows.append(dict(kind='support',pre=state,pi=candidate))
            expected.append(composed.full_support_reasons(state,candidate,FakeModels()))
            self.assertEqual(expected[-1],[])
        candidate=copy.deepcopy(pi);state=copy.deepcopy(pre)
        candidate['potions'][0]['potionId']=base.ENTROPIC_BREW_ID
        state['potions'][0]=base.ENTROPIC_BREW_ID
        rows.append(dict(kind='support',pre=state,pi=candidate))
        expected.append(composed.full_support_reasons(state,candidate,FakeModels()))
        self.assertIn('potion_not_certified',expected[-1])
        self.assertEqual(self.probe(rows),expected)

    def test_every_encounter_exact_rng(self):
        rows, expected = [], []
        for i, name in enumerate(rng.encounter_names()[1:],1):
            for seed0,seed1 in [(1,2),(2**64-1,2**63+17),(12345678,87654321)]:
                pre=dict(seed0=seed0,seed1=seed1,counter=42)
                rows.append(dict(kind='rng',pre=pre,encounter=i))
                expected.append(rng.replay_misc(pre,name))
        self.assertEqual(self.probe(rows),expected)

    def test_bounded_rejection_advances_seed_but_counts_one_call(self):
        # nextLong returns UINT64_MAX, forcing rejection for random(2).
        pre=dict(seed0=567594222891294720,seed1=0,counter=1)
        encounter=base._ENCOUNTER_IDS['SPHERE_AND_TWO_SHAPES']
        exact=rng.replay_misc(pre,'SPHERE_AND_TWO_SHAPES')
        self.assertNotEqual(exact,rng.set_counter(pre,3))
        self.assertEqual(self.probe([dict(kind='rng',pre=pre,encounter=encounter)]),[exact])

    def test_common_relic_residues_and_copy_through(self):
        rows,expected=[],[]
        encounter=base._ENCOUNTER_IDS['TWO_LOUSE']
        for turns in range(6):
            for attacks in range(10):
                residues=dict(turns=turns,attacks=attacks,cards=attacks,shuffles=turns%3)
                pre=[dict(id=rid,data=(relic.CYCLIC[name]-1 if name in relic.CYCLIC else 0)) for rid,name in relic.NAMES.items() if name!='INSERTER']
                pre.extend([dict(id=base._RELIC_IDS['AKABEKO'],data=31)])
                rows.append(dict(kind='relic',pre=pre,residues=residues,encounter=encounter))
                expected.append(relic.reconstruct(pre,residues,encounter))
        self.assertEqual(self.probe(rows),expected)

    def test_inserter_and_active_lizard_fail_closed(self):
        rows=[dict(kind='relic',pre=[dict(id=base._RELIC_IDS[name],data=data)],residues=dict(turns=0),encounter=1) for name,data in [('INSERTER',0),('LIZARD_TAIL',1),('HAPPY_FLOWER',3)]]
        self.assertTrue(all('error' in r for r in self.probe(rows)))

if __name__=='__main__':
    unittest.main()
