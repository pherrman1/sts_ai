import csv, json, unittest
from pathlib import Path
from tools.ooc_pipeline_contract import parse_budgets, h_plan, validate_corpus, validate_manifest, sha256, SCHEMA_VERSION
from tools.verify.vnettest_selftest import canonical_names
from tools.analyze_ooc_k_budget import self_test as k_budget_analysis_self_test
from tools.analyze_ooc_h_futures import self_test as h_futures_analysis_self_test
from tools.audit_clean_ooc_pilot import audit as audit_clean_pilot, PREFIX as PILOT_PREFIX, SUFFIX as PILOT_SUFFIX

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
        self.assertIn('spec.at("execution").at("shardCount")',evaluator)
        self.assertIn('d.seed%(std::uint64_t)shardCount',evaluator)
        self.assertIn('spec.at("execution").at("recoveryWorkCount")',evaluator)
        self.assertIn('at("recoveryPartition")',evaluator)
        self.assertIn('workOrdinal%workCount!=workIndex',evaluator)
        self.assertIn('(shardIndex<0&&futures!=0)',evaluator)
        self.assertIn('output filename does not bind frozen shard assignment',evaluator)
        self.assertIn('std::filesystem::create_directory(claimDir)',evaluator)

    def test_k_budget_freezer_locks_process_sharding(self):
        source=Path("tools/freeze_ooc_k_budget_experiment.py").read_text(encoding="utf-8")
        self.assertIn('"mode":"source_seed_modulo_process_shards"',source)
        self.assertIn('"shardCount":24',source)
        self.assertIn('"recoveryWorkCount":12',source)
        self.assertIn('"mergeRequiresAllShards":True',source)

    def test_k_budget_recovery_partition_is_disjoint_and_complete(self):
        for action_count in (2, 5, 23):
            branches={(future,action) for future in range(4)
                      for action in range(action_count)}
            workers=[{(future,action) for future,action in branches
                      if (future*action_count+action)%12==worker}
                     for worker in range(12)]
            self.assertEqual(set().union(*workers),branches)
            self.assertEqual(sum(map(len,workers)),len(branches))

    def test_k_budget_analyzer_self_test(self):
        k_budget_analysis_self_test()

    def test_h_futures_analyzer_self_test(self):
        h_futures_analysis_self_test()

    def test_clean_pilot_is_atomic_complete_and_reuses_one_combat(self):
        source=Path("apps/one_combat.cpp").read_text(encoding="utf-8")
        begin=source.index("runCleanOocPilotSeed(std::uint64_t")
        end=source.index("static void cleanOocPilotGen",begin)
        producer=source[begin:end]
        self.assertIn("actions.size()>=2",producer)
        self.assertIn("actionBits.insert(a.bits).second",producer)
        self.assertIn("source action missing from legal siblings",producer)
        self.assertIn("resampleRemainingActEncounters(siblingBase,hiddenSeed)",producer)
        self.assertIn("combatFeatureRow(bc)",producer)
        self.assertIn("bc.exitBattle(branch)",producer)
        self.assertIn("qProduct=survived?conditional:0.0",producer)
        self.assertIn("combat semantic/conversion/transaction/knowledge health failure",producer)
        wrapper=source[end:source.index("// Play one full run",end)]
        self.assertIn('const std::string partial=outfile+".partial"',wrapper)
        self.assertIn('failurePartial=failurePath+".partial"',wrapper)
        self.assertIn("std::filesystem::rename(failurePartial,failurePath)",wrapper)
        self.assertIn("std::filesystem::rename(partial,outfile)",wrapper)

    def test_clean_pilot_schema_fails_closed(self):
        build=Path("build");build.mkdir(exist_ok=True)
        data=build/"clean_pilot_synthetic.csv";manifest_path=build/"clean_pilot_synthetic.manifest.json"
        header=PILOT_PREFIX+canonical_names()+PILOT_SUFFIX
        search={"simulation_budgets":[10000],"exploration_parameter":25.0,"exploration_parameter_chance":25.0,"chance_widening_c":3.7028,"chance_widening_alpha":0.52389,"end_turn_widening_c":3.7028,"end_turn_widening_alpha":0.52389,"reuse_cap_mode":"allocated","reuse_cap":32768,"sequential_halving":False,"pruning":False,"learned_visit_puct":False,"direct_learned_leaf":False,"adaptive":False}
        env={"STS_FAIR":"1","STS_SEARCHER3":"0","STS_SILVER_SEARCH":"1","STS_SILVER_EXACT_ROOT_BUDGETS":"1","STS_SILVER_REUSE_CAP_MODE":"allocated","STS_SILVER_ADAPTIVE":"0","STS_SILVER_VNET_LEAF_DIRECT":"0","STS_SILVER_TELEMETRY":"1"}
        teacher={"teacher_id":"clean-t","git_sha":"3"*40,"executable_sha256":"4"*64,"combat_backend":"silver_uct","rng_regime":"project_fair","search_configuration":search,"environment":env,"model_artifacts":[{"role":"floor","path":"floor","sha256":"5"*64},{"role":"win","path":"win","sha256":"6"*64}]}
        def row(action,chosen):
            prefix=[983000,0,1,1,1,action,[11,22][action],["a","b"][action],2,"11;22",chosen,0,1,7,8,"clean-t",1,.2,.2,2.0,10.0,10000,1,1.0,1.0,1,"",1,-1,1,2,3,"NORMAL"]
            suffix=[1,40,50,80,80,.5,"","",0,0,0,0,"","",0,0,"none"]
            return prefix+[0]*1766+suffix
        rows=[row(0,1),row(1,0)]
        def write(rows,producer="3"*40):
            with data.open("w",newline="",encoding="utf-8") as f:csv.writer(f).writerows([header,*rows])
            manifest={"schema":"ooc_clean_pilot_manifest_v1","producerGitSha":producer,"producerExecutableSha256":"4"*64,"csv":{"path":str(data),"sha256":sha256(data)},"seedSpec":{"start":983000,"count":1},"H":1,"futureIdentities":[0],"schedule":[10000],"combatTeacher":teacher,"perSource":[{"sourceSeed":983000,"decisions":1,"rows":len(rows)}],"integrity":{"requested":1,"completed":1,"quarantined":0,"failures":0,"rows":len(rows)}}
            manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
        write(rows);self.assertEqual(audit_clean_pilot(data,manifest_path)["rows"],2)
        terminal=row(1,0);terminal[PILOT_PREFIX.index("reachedCombat")]=0;terminal[PILOT_PREFIX.index("terminalOutcomeBeforeCombat")]=0;terminal[PILOT_PREFIX.index("survivedPrefix")]=0;terminal[PILOT_PREFIX.index("conditionalAliveValue")]=0;terminal[PILOT_PREFIX.index("qProduct")]=0;terminal[PILOT_PREFIX.index("silverSimulations")]=0;terminal[PILOT_PREFIX.index("combatDecisions")]=0;terminal[len(PILOT_PREFIX):len(PILOT_PREFIX)+1766]=[""]*1766;terminal[-17:]=[""]*16+["no_combat_terminal"]
        terminal[PILOT_PREFIX.index("battleEncounter")]=-1;terminal[PILOT_PREFIX.index("roomClass")]="OTHER"
        write([row(0,1),terminal]);summary=audit_clean_pilot(data,manifest_path);self.assertEqual(summary["combatSurrogateRows"],1);self.assertEqual(summary["terminalBeforeCombatRows"],1)
        victory=terminal.copy();victory[PILOT_PREFIX.index("terminalOutcomeBeforeCombat")]=2;victory[PILOT_PREFIX.index("survivedPrefix")]=1;victory[PILOT_PREFIX.index("conditionalAliveValue")]=1;victory[PILOT_PREFIX.index("qProduct")]=1
        write([row(0,1),victory]);self.assertEqual(audit_clean_pilot(data,manifest_path)["terminalBeforeCombatRows"],1)
        bad=terminal.copy();bad[PILOT_PREFIX.index("conditionalAliveValue")]=.2;write([row(0,1),bad])
        with self.assertRaisesRegex(ValueError,"exact absorbed"):audit_clean_pilot(data,manifest_path)
        bad=terminal.copy();bad[PILOT_PREFIX.index("silverSimulations")]=10000;write([row(0,1),bad])
        with self.assertRaisesRegex(ValueError,"combat search cost"):audit_clean_pilot(data,manifest_path)
        bad=terminal.copy();bad[len(PILOT_PREFIX)]=0;write([row(0,1),bad])
        with self.assertRaisesRegex(ValueError,"combat surrogate target"):audit_clean_pilot(data,manifest_path)
        bad=terminal.copy();bad[-11]="Potion::BLOOD_POTION";write([row(0,1),bad])
        with self.assertRaisesRegex(ValueError,"combat surrogate target"):audit_clean_pilot(data,manifest_path)
        write(rows[:1]);
        with self.assertRaisesRegex(ValueError,"incomplete sibling"):audit_clean_pilot(data,manifest_path)
        bad=[row(0,1),row(1,0)];bad[0][PILOT_PREFIX.index("qProduct")]=.3;write(bad)
        with self.assertRaisesRegex(ValueError,"qProduct"):audit_clean_pilot(data,manifest_path)
        write(rows,producer="7"*40)
        with self.assertRaisesRegex(ValueError,"provenance"):audit_clean_pilot(data,manifest_path)

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
