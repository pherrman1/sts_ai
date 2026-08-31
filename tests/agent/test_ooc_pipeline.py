import csv, json, unittest
from pathlib import Path
from tools.ooc_pipeline_contract import parse_budgets, h_plan, validate_corpus, validate_manifest, sha256, SCHEMA_VERSION
from tools.verify.vnettest_selftest import canonical_names
from tools.analyze_ooc_k_budget import self_test as k_budget_analysis_self_test

class TestOocPipeline(unittest.TestCase):
    def test_k_budget_evaluator_is_observational_and_fail_closed(self):
        source=Path("apps/one_combat.cpp").read_text(encoding="utf-8")
        begin=source.index("static void oocBudgetEvaluate")
        end=source.index("static void strategicGen",begin)
        evaluator=source[begin:end]
        self.assertIn('const std::string partialFile=outFile+".partial"',evaluator)
        self.assertIn("OocPrefixObserver observer",evaluator)
        self.assertIn("observational checkpoint equivalence failed",evaluator)
        self.assertIn("legal sibling set differs from manifest",evaluator)
        self.assertIn("invalid/non-finite prefix target",evaluator)
        self.assertIn('{"STS_NATIVE_OOC","1"}',evaluator)
        self.assertIn("modelPaths[\"floor\"]!=g_floorNet.path",evaluator)
        self.assertIn("modelPaths[\"win\"]!=g_winNet.path",evaluator)

    def test_k_budget_analyzer_self_test(self):
        k_budget_analysis_self_test()

    def test_counterfactual_audit_uses_external_combat_backend_overload(self):
        source=Path("apps/one_combat.cpp").read_text(encoding="utf-8")
        begin=source.index("runCounterfactualSurrogateAuditSeed")
        end=source.index("counterfactualSurrogateAuditGen",begin)
        audit=source[begin:end]
        self.assertIn("agent.playoutBattle(gc,bc)",audit)
        self.assertIn("fight.playoutBattle(branch,bc)",audit)
        self.assertNotIn("fight.playoutBattle(bc)",audit)

    def test_budget_prefixes_and_h_plan(self):
        self.assertEqual(parse_budgets("333,333,334"), [333,333,334])
        self.assertEqual(h_plan(12,[1,2,4]), [{"H":1,"distinct_state_actions":12,"expensive_branches":12},{"H":2,"distinct_state_actions":6,"expensive_branches":12},{"H":4,"distinct_state_actions":3,"expensive_branches":12}])
        with self.assertRaises(ValueError): parse_budgets("100,0")
    def test_manifest_fails_closed_and_checks_csv(self):
        csv=Path(__file__).resolve().parents[1]/"data"/"v_runwin_e2c_v2_parity.csv"
        search={"simulation_budgets":[10000],"exploration_parameter":25.0,"exploration_parameter_chance":25.0,"chance_widening_c":3.7028,"chance_widening_alpha":0.52389,"end_turn_widening_c":3.7028,"end_turn_widening_alpha":0.52389,"reuse_cap_mode":"allocated","reuse_cap":32768,"sequential_halving":False,"pruning":False,"learned_visit_puct":False,"direct_learned_leaf":False,"adaptive":False}
        env={"STS_FAIR":"1","STS_SEARCHER3":"0","STS_SILVER_SEARCH":"1","STS_SILVER_EXACT_ROOT_BUDGETS":"1","STS_SILVER_REUSE_CAP_MODE":"allocated","STS_SILVER_ADAPTIVE":"0","STS_SILVER_VNET_LEAF_DIRECT":"0","STS_SILVER_TELEMETRY":"1"}
        teacher={"teacher_id":"t","git_sha":"3"*40,"executable_sha256":"4"*64,"combat_backend":"silver_uct","rng_regime":"project_fair","search_configuration":search,"environment":env,"model_artifacts":[{"role":"value","path":str(csv),"sha256":"2"*64}]}
        m={"schema_version":SCHEMA_VERSION,"producer_git_sha":"3"*40,"producer_executable_sha256":"4"*64,"combat_teacher":teacher,"seed_spec":{"list":[1]},"csv":{"path":str(csv),"sha256":sha256(csv)},"collection_timestamp":"2026-01-01T00:00:00Z","integrity":{"requested_runs":1,"completed_runs":1,"quarantined_runs":0,"rows":1}}
        validate_manifest(m)
        del teacher["rng_regime"]
        with self.assertRaisesRegex(ValueError,"rng_regime"): validate_manifest(m)

    def test_corpus_rejects_unexpected_numeric_leakage_column(self):
        prefix=["sourceSeed","fightIdx","act","floor","encounter","roomClass","decisionIdx","teacherId"]
        suffix=["won","endHp","startHp","startMaxHp","endMaxHp","endHpFrac","startPotionIds","endPotionIds","startPotionCount","endPotionCount","goldDelta","smokeBombUsed","changedRelicCounters","ritualDaggerChanges","deckStructureChanged","parasiteAdded","persistentMutationSummary"]
        search={"simulation_budgets":[10000],"exploration_parameter":25.0,"exploration_parameter_chance":25.0,"chance_widening_c":3.7028,"chance_widening_alpha":0.52389,"end_turn_widening_c":3.7028,"end_turn_widening_alpha":0.52389,"reuse_cap_mode":"allocated","reuse_cap":32768,"sequential_halving":False,"pruning":False,"learned_visit_puct":False,"direct_learned_leaf":False,"adaptive":False}
        env={"STS_FAIR":"1","STS_SEARCHER3":"0","STS_SILVER_SEARCH":"1","STS_SILVER_EXACT_ROOT_BUDGETS":"1","STS_SILVER_REUSE_CAP_MODE":"allocated","STS_SILVER_ADAPTIVE":"0","STS_SILVER_VNET_LEAF_DIRECT":"0","STS_SILVER_TELEMETRY":"1"}
        teacher={"teacher_id":"t","git_sha":"3"*40,"executable_sha256":"4"*64,"combat_backend":"silver_uct","rng_regime":"project_fair","search_configuration":search,"environment":env,"model_artifacts":[{"role":"value","path":"unused","sha256":"2"*64}]}
        Path("build").mkdir(exist_ok=True)
        path=Path("build/ooc_pipeline_leaky_test.csv")
        header=prefix+canonical_names()+suffix+["future_win_probability"]
        row=[1,0,1,1,1,"NORMAL",0,"t"]+[0]*1766+[1,70,70,80,80,.875,"","",0,0,0,0,"","",0,0,""]+[1.0]
        with path.open("w",newline="",encoding="utf-8") as f:
            writer=csv.writer(f); writer.writerow(header); writer.writerow(row)
        manifest={"schema_version":SCHEMA_VERSION,"producer_git_sha":"3"*40,"producer_executable_sha256":"4"*64,"combat_teacher":teacher,"seed_spec":{"list":[1]},"csv":{"path":str(path),"sha256":sha256(path)},"collection_timestamp":"2026-01-01T00:00:00Z","integrity":{"requested_runs":1,"completed_runs":1,"quarantined_runs":0,"rows":1}}
        with self.assertRaisesRegex(ValueError,"unexpected columns"):
            validate_corpus(manifest)

if __name__ == "__main__": unittest.main()
