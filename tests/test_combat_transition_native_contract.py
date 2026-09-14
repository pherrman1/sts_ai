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
int main() {
 using namespace one_combat; using nlohmann::json;
 for(std::string line;std::getline(std::cin,line);) {try {auto j=json::parse(line);
 if(j["kind"]=="rng") {auto p=j["pre"];auto s=replayNativeComposedMisc({p["counter"],p["seed0"],p["seed1"]},j["encounter"]);std::cout<<json{{"counter",s.counter},{"seed0",s.seed0},{"seed1",s.seed1}}<<'\n';}
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
        subprocess.run(['g++','-std=c++17','-Iinclude','-Iextern','-Iapps',str(source),
                        'apps/one_combat/combat_transition_native_contract.cpp','-o',str(cls.exe)],cwd=ROOT,check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def probe(self, rows):
        result = subprocess.run([str(self.exe)],input=''.join(json.dumps(r)+'\n' for r in rows),text=True,capture_output=True,check=True)
        return [json.loads(r) for r in result.stdout.splitlines()]

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
