import unittest
from pathlib import Path
from tools.ooc_pipeline_contract import parse_budgets, h_plan, validate_manifest, sha256, SCHEMA_VERSION

class TestOocPipeline(unittest.TestCase):
    def test_budget_prefixes_and_h_plan(self):
        self.assertEqual(parse_budgets("333,333,334"), [333,333,334])
        self.assertEqual(h_plan(12,[1,2,4]), [{"H":1,"distinct_state_actions":12,"expensive_branches":12},{"H":2,"distinct_state_actions":6,"expensive_branches":12},{"H":4,"distinct_state_actions":3,"expensive_branches":12}])
        with self.assertRaises(ValueError): parse_budgets("100,0")
    def test_manifest_fails_closed_and_checks_csv(self):
        csv=Path(__file__).resolve().parents[1]/"data"/"v_runwin_e2c_v2_parity.csv"
        teacher={"teacher_id":"t","git_sha":"1"*40,"combat_backend":"Searcher3","rng_regime":"fair","search_configuration":{"simulation_budgets":[1000]},"model_artifacts":[{"role":"value","sha256":"2"*64}]}
        m={"schema_version":SCHEMA_VERSION,"producer_git_sha":"3"*40,"combat_teacher":teacher,"seed_spec":{"list":[1]},"csv":{"path":str(csv),"sha256":sha256(csv)},"collection_timestamp":"2026-01-01T00:00:00Z","integrity":{"requested_runs":1,"completed_runs":1,"quarantined_runs":0,"rows":1}}
        validate_manifest(m)
        del teacher["rng_regime"]
        with self.assertRaisesRegex(ValueError,"rng_regime"): validate_manifest(m)

if __name__ == "__main__": unittest.main()
