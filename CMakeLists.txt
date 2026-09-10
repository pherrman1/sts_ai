cmake_minimum_required(VERSION 3.19)
project(
        sts_lightspeed
        VERSION 0.1
        DESCRIPTION "High Performance, rng accurate implementation of Slay the Spire with tools for tree search and ml."
        LANGUAGES CXX)

enable_testing()

file (GLOB_RECURSE sts_lightspeed_SOURCES CONFIGURE_DEPENDS "src/*.cpp")

set(CMAKE_CXX_STANDARD 17)
add_compile_options(
    -Wno-shift-count-overflow
    -fopenmp
    $<$<CONFIG:Release>:-O3>
    $<$<CONFIG:Release>:-flto>)
add_link_options(
    -fopenmp
    $<$<CONFIG:Release>:-flto>)

include(cmake/GccPgo.cmake)

add_subdirectory(json)

add_library(sts_core_objects OBJECT ${sts_lightspeed_SOURCES})
target_include_directories(sts_core_objects PUBLIC include)
target_include_directories(sts_core_objects PUBLIC json/include)

# Exact MIT-licensed Silver combat/search implementation, compiled under a
# private namespace. This target deliberately has no dependency on live
# sts_ai objects: it is the isolated combat model behind the future bridge.
# The source list is the audited combat/search closure only; it excludes the
# reference repository's apps, bindings, Python/OOC integration, training,
# deployment, and console controllers.
set(SILVER_MODEL_SOURCES
    third_party/silver_lightspeed/src/combat/Actions.cpp
    third_party/silver_lightspeed/src/combat/BattleContext.cpp
    third_party/silver_lightspeed/src/combat/CardInstance.cpp
    third_party/silver_lightspeed/src/combat/CardManager.cpp
    third_party/silver_lightspeed/src/combat/CardQueue.cpp
    third_party/silver_lightspeed/src/combat/Monster.cpp
    third_party/silver_lightspeed/src/combat/MonsterGroup.cpp
    third_party/silver_lightspeed/src/combat/MonsterMoveDamage.cpp
    third_party/silver_lightspeed/src/combat/MonsterSpecific.cpp
    third_party/silver_lightspeed/src/combat/Player.cpp
    third_party/silver_lightspeed/src/game/Card.cpp
    # Exact upstream RelicContainer helper block required by Silver combat
    # evaluation/action resolution; excludes the full-game controller.
    third_party/silver_lightspeed/bridge/SilverRelicContainer.cpp
    third_party/silver_lightspeed/bridge/SilverCombatRandomHelpers.cpp
    third_party/silver_lightspeed/src/sim/search/Action.cpp
    third_party/silver_lightspeed/src/sim/search/BattleSearcher.cpp
    third_party/silver_lightspeed/src/sim/search/ExpertKnowledge.cpp
    third_party/silver_lightspeed/src/sim/search/SimpleAgent.cpp)
add_library(silver_combat_model STATIC ${SILVER_MODEL_SOURCES})
set_target_properties(silver_combat_model PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver_combat_model PRIVATE third_party/silver_lightspeed/include include)
# The macro isolation is target-private. No live sts_ai translation unit sees
# either renamed namespace or any Silver simulator definition.
target_compile_definitions(silver_combat_model PRIVATE
    sts=sts_silver
    java=sts_silver_java
    fixed_list=silver_fixed_list
    rollWeightedIdx=silver_rollWeightedIdx
    simulationIdx=silver_simulationIdx
    initMaps=silver_initMaps
    agentMtRunner=silver_agentMtRunner)
target_compile_options(silver_combat_model PRIVATE -ffunction-sections -fdata-sections)

add_library(silver_combat_bridge STATIC third_party/silver_lightspeed/bridge/SilverBridge.cpp)
set_target_properties(silver_combat_bridge PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver_combat_bridge PRIVATE third_party/silver_lightspeed/include include)
target_compile_definitions(silver_combat_bridge PRIVATE
    sts=sts_silver
    java=sts_silver_java
    fixed_list=silver_fixed_list
    rollWeightedIdx=silver_rollWeightedIdx
    simulationIdx=silver_simulationIdx
    initMaps=silver_initMaps
    agentMtRunner=silver_agentMtRunner)
target_compile_options(silver_combat_bridge PRIVATE -ffunction-sections -fdata-sections)

add_library(silver_combat_search_bridge STATIC
    third_party/silver_lightspeed/bridge/SilverSearcherBridge.cpp
    third_party/silver_lightspeed/bridge/SilverStateBridge.cpp)
set_target_properties(silver_combat_search_bridge PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver_combat_search_bridge PRIVATE third_party/silver_lightspeed/include include)
target_compile_definitions(silver_combat_search_bridge PRIVATE
    sts=sts_silver
    java=sts_silver_java
    fixed_list=silver_fixed_list
    rollWeightedIdx=silver_rollWeightedIdx
    simulationIdx=silver_simulationIdx
    initMaps=silver_initMaps
    agentMtRunner=silver_agentMtRunner)
target_compile_options(silver_combat_search_bridge PRIVATE -ffunction-sections -fdata-sections)
target_link_libraries(silver_combat_search_bridge PRIVATE silver_combat_model)

# Normal-namespace live boundary. It is linked only by one_combat, while the
# core agent reaches it through a default-null callback; this keeps ordinary
# core/unit-test targets free of the full isolated Silver model.
add_library(silver_live_backend STATIC third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp)
set_target_properties(silver_live_backend PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver_live_backend PRIVATE include json/include)
target_link_libraries(silver_live_backend PUBLIC silver_combat_search_bridge)

add_executable(silver-native-test apps/silver_native_test.cpp)
set_target_properties(silver-native-test PROPERTIES OUTPUT_NAME silver_native_test)
target_include_directories(silver-native-test PRIVATE include)
target_link_libraries(silver-native-test PRIVATE silver_combat_search_bridge)
target_link_options(silver-native-test PRIVATE -Wl,--gc-sections)

add_executable(silver-leaf-relabel apps/silver_leaf_relabel.cpp)
set_target_properties(silver-leaf-relabel PROPERTIES OUTPUT_NAME silver_leaf_relabel)
target_include_directories(silver-leaf-relabel PRIVATE include json/include)
target_link_libraries(silver-leaf-relabel PRIVATE silver_combat_search_bridge)
target_link_options(silver-leaf-relabel PRIVATE -Wl,--gc-sections)

add_executable(silver-leaf-features apps/silver_leaf_features.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-leaf-features PROPERTIES OUTPUT_NAME silver_leaf_features)
target_include_directories(silver-leaf-features PRIVATE include json/include)
target_link_libraries(silver-leaf-features PRIVATE silver_live_backend)
target_link_options(silver-leaf-features PRIVATE -Wl,--gc-sections)

add_executable(silver-parent-policy-features
    apps/silver_parent_policy_features.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-parent-policy-features PROPERTIES
    OUTPUT_NAME silver_parent_policy_features)
target_include_directories(silver-parent-policy-features PRIVATE include json/include)
target_link_libraries(silver-parent-policy-features PRIVATE silver_live_backend)
target_link_options(silver-parent-policy-features PRIVATE -Wl,--gc-sections)

add_executable(silver-native-parity-runner third_party/silver_lightspeed/bridge/SilverNativeFixtureRunner.cpp)
set_target_properties(silver-native-parity-runner PROPERTIES OUTPUT_NAME silver_native_parity_runner)
set_target_properties(silver-native-parity-runner PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver-native-parity-runner PRIVATE third_party/silver_lightspeed/include include)
target_compile_definitions(silver-native-parity-runner PRIVATE
    sts=sts_silver java=sts_silver_java fixed_list=silver_fixed_list
    rollWeightedIdx=silver_rollWeightedIdx simulationIdx=silver_simulationIdx
    initMaps=silver_initMaps agentMtRunner=silver_agentMtRunner)
target_link_libraries(silver-native-parity-runner PRIVATE silver_combat_model silver_combat_search_bridge)
target_link_options(silver-native-parity-runner PRIVATE -Wl,--gc-sections)

add_executable(silver-player-status-test apps/silver_player_status_test.cpp)
set_target_properties(silver-player-status-test PROPERTIES
    OUTPUT_NAME silver_player_status_test CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver-player-status-test PRIVATE third_party/silver_lightspeed/include)

add_executable(silver-search-optimization-test apps/silver_search_optimization_test.cpp)
set_target_properties(silver-search-optimization-test PROPERTIES
    OUTPUT_NAME silver_search_optimization_test CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver-search-optimization-test PRIVATE
    third_party/silver_lightspeed/include include)
target_compile_definitions(silver-search-optimization-test PRIVATE
    sts=sts_silver java=sts_silver_java fixed_list=silver_fixed_list
    rollWeightedIdx=silver_rollWeightedIdx simulationIdx=silver_simulationIdx
    initMaps=silver_initMaps agentMtRunner=silver_agentMtRunner)
target_link_libraries(silver-search-optimization-test PRIVATE silver_combat_model silver_combat_search_bridge)
target_link_options(silver-search-optimization-test PRIVATE -Wl,--gc-sections)

# Full boundary test has its own executable: it needs both live fixture
# construction and the isolated model, but must not bloat normal unit-test.
add_executable(silver-bridge-test apps/silver_bridge_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-bridge-test PROPERTIES OUTPUT_NAME silver_bridge_test)
target_include_directories(silver-bridge-test PRIVATE include json/include)
target_link_libraries(silver-bridge-test PRIVATE silver_live_backend)
target_link_options(silver-bridge-test PRIVATE -Wl,--gc-sections)

# Real live Runic-Dome lifecycle coverage: the observer is configured before
# battle init and exercises monster turns, chained rerolls, and intent query.
add_executable(runic-dome-lifecycle-test apps/runic_dome_lifecycle_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(runic-dome-lifecycle-test PROPERTIES OUTPUT_NAME runic_dome_lifecycle_test)
target_include_directories(runic-dome-lifecycle-test PRIVATE include json/include)
target_link_libraries(runic-dome-lifecycle-test PRIVATE silver_combat_search_bridge)
target_link_options(runic-dome-lifecycle-test PRIVATE -Wl,--gc-sections)

# One controlled real-combat bridge smoke. It deliberately runs no campaign
# seeds and verifies only conversion -> Silver decision -> semantic lowering
# -> ordinary live action execution.
add_executable(silver-integration-test apps/silver_integration_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-integration-test PROPERTIES OUTPUT_NAME silver_integration_test)
target_include_directories(silver-integration-test PRIVATE include json/include)
target_link_libraries(silver-integration-test PRIVATE silver_live_backend)
target_link_options(silver-integration-test PRIVATE -Wl,--gc-sections)

# Default-off observer neutrality: live combat core only, deliberately no
# isolated Silver model linkage.
add_executable(combat-knowledge-neutrality-test apps/combat_knowledge_neutrality_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(combat-knowledge-neutrality-test PROPERTIES OUTPUT_NAME combat_knowledge_neutrality_test)
target_include_directories(combat-knowledge-neutrality-test PRIVATE include json/include)
target_link_options(combat-knowledge-neutrality-test PRIVATE -Wl,--gc-sections)

# The pybind11 module needs CPython development headers (python3-dev). Core
# targets (main, one_combat, test, small-test) must not depend on them, so the
# module is skipped with a warning when headers are absent.
find_package(Python COMPONENTS Interpreter Development.Module QUIET)
if(Python_Development.Module_FOUND)
    add_subdirectory(pybind11)
    # Keep native executables on non-PIC objects: Release throughput is
    # materially slower when their LTO inputs are compiled with -fPIC. The
    # shared Python module gets a dedicated hidden/PIC object collection.
    add_library(sts_core_pic_objects OBJECT ${sts_lightspeed_SOURCES})
    set_target_properties(sts_core_pic_objects PROPERTIES
        POSITION_INDEPENDENT_CODE ON
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN ON)
    target_include_directories(sts_core_pic_objects PUBLIC include)
    target_include_directories(sts_core_pic_objects PUBLIC json/include)
    pybind11_add_module(slaythespire
        bindings/slaythespire.cpp
        bindings/bindings-util.cpp
        $<TARGET_OBJECTS:sts_core_pic_objects>)
    target_include_directories(slaythespire PUBLIC include)
    target_include_directories(slaythespire PUBLIC json/single_include)
    target_include_directories(slaythespire PUBLIC bindings)
else()
    message(WARNING "Python development headers not found; skipping the slaythespire pybind11 module")
endif()


add_executable(main apps/main.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_link_directories(main PRIVATE json::nlohmann_json)
target_include_directories(main PUBLIC include)
target_include_directories(main PUBLIC json/include)

add_executable(one_combat apps/one_combat.cpp apps/combat_model_diagnostics.cpp
    apps/one_combat/run_features.cpp apps/one_combat/compact_tree.cpp
    apps/one_combat/e2c_capture.cpp
    apps/one_combat/ooc_policy.cpp
    apps/one_combat/run_driver.cpp
    apps/one_combat/fight_replay.cpp
    apps/one_combat/search_diagnostics.cpp
    apps/one_combat/vnet_query_log.cpp
    apps/one_combat/particle_diagnostics.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat PUBLIC include)
target_include_directories(one_combat PUBLIC json/include)
target_link_libraries(one_combat PRIVATE silver_live_backend)
# The isolated model objects contain upstream full-game methods adjacent to
# the combat methods used by Silver rollout. Their sections are compiled with
# -ffunction-sections; discard the unreachable OOC closure instead of vendoring
# it into the integration executable.
target_link_options(one_combat PRIVATE -Wl,--gc-sections)

add_executable(one_combat_feature_test apps/one_combat_feature_test.cpp
    apps/one_combat/run_features.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat_feature_test PUBLIC include)
target_include_directories(one_combat_feature_test PUBLIC json/include)

add_executable(parity_test apps/parity_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(parity_test PUBLIC include)
target_include_directories(parity_test PUBLIC json/include)

# "test" is reserved by CTest, so the manual dispatcher target is unit-test
# with OUTPUT_NAME "test" to keep the build/test binary path stable.
add_executable(unit-test apps/test.cpp apps/test_belief.cpp
    apps/test_ooc_reward_continuation.cpp apps/test_ooc_semantic.cpp
    apps/test_ooc_semantic_pipeline.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(unit-test PROPERTIES OUTPUT_NAME test)
target_link_libraries(unit-test PRIVATE silver_combat_bridge)
target_include_directories(unit-test PUBLIC include)
target_link_directories(unit-test PUBLIC json::nlohmann_json)
target_include_directories(unit-test PUBLIC json/include)

add_executable(small-test apps/small-test.cpp bindings/bindings-util.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_link_directories(small-test PRIVATE json::nlohmann_json)
target_include_directories(small-test PUBLIC include)
target_include_directories(small-test PUBLIC json/include)
target_include_directories(small-test PUBLIC bindings)

# CTest entries below cover checks that do not depend on apps/test.cpp
# subcommands (apps/test.cpp is a manual command dispatcher; its subcommands
# receive CTest entries separately). bash -n only parses, never executes.
add_test(NAME selfplay_syntax COMMAND bash -n
    ${CMAKE_SOURCE_DIR}/selfplay/loop.sh
    ${CMAKE_SOURCE_DIR}/selfplay/status.sh
    ${CMAKE_SOURCE_DIR}/selfplay/run_card_reliability_overnight.sh
    ${CMAKE_SOURCE_DIR}/selfplay/run_future_fight_collection.sh
    ${CMAKE_SOURCE_DIR}/selfplay/run_card_cf_collection.sh)
add_test(NAME paired_analysis_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/paired_analysis.py --self-test)
add_test(NAME py_compile_parity_test COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/parity_test.py)
add_test(NAME particle_leaf_probe_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/train_particle_leaf_probe.py --self-test)
add_test(NAME semantic_confirmation_analysis COMMAND python3 -m unittest
    tests.test_ooc_semantic_confirmation tests.test_semantic_confirmation_runner
    tools.test_semantic_combat_coverage -q)
set_tests_properties(semantic_confirmation_analysis PROPERTIES
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS "research-repro;tooling")
add_test(NAME py_compile_analyze_ooc_factor COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/analyze_ooc_factor.py)
add_test(NAME particle_posterior_probe_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_particle_posterior_probe.py --self-test)
add_test(NAME check_replay_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/check_replay.py --self-test)
add_test(NAME vnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/vnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME winnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/winnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME one_combat_feature_regression COMMAND $<TARGET_FILE:one_combat_feature_test>)
add_test(NAME battlecontext_roundtrip COMMAND $<TARGET_FILE:unit-test> battlecontext_roundtrip)
add_test(NAME designer_in_spire COMMAND $<TARGET_FILE:unit-test> designer_in_spire)
add_test(NAME scum_nonfair_empty_edges COMMAND $<TARGET_FILE:unit-test> scum_nonfair_empty_edges)
add_test(NAME scum_convroot_stale_outcome COMMAND $<TARGET_FILE:unit-test> scum_convroot_stale_outcome)
add_test(NAME cardqueue_overflow COMMAND $<TARGET_FILE:unit-test> cardqueue_overflow)
add_test(NAME keys_collect COMMAND $<TARGET_FILE:unit-test> keys_collect)
add_test(NAME issue_fixes COMMAND $<TARGET_FILE:unit-test> issue_fixes)
add_test(NAME ooc_reward_continuation COMMAND $<TARGET_FILE:unit-test> ooc_reward_continuation)
add_test(NAME ooc_semantic COMMAND $<TARGET_FILE:unit-test> ooc_semantic)
add_test(NAME ooc_semantic_pipeline COMMAND $<TARGET_FILE:unit-test> ooc_semantic_pipeline)
add_test(NAME ooc_semantic_producer COMMAND $<TARGET_FILE:one_combat> oocsemanticselftest)
add_test(NAME combat_evaluator_semantic_branch_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_evaluator_semantic_branch.py)
set_tests_properties(combat_evaluator_semantic_branch_contract PROPERTIES LABELS "core;integration")
set_tests_properties(ooc_semantic_producer PROPERTIES WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
add_test(NAME ooc_semantic_smith COMMAND $<TARGET_FILE:unit-test> ooc_semantic_smith)
set_tests_properties(ooc_semantic ooc_semantic_pipeline ooc_semantic_producer ooc_semantic_smith ooc_reward_continuation
    PROPERTIES LABELS "core;integration")
add_test(NAME relic_reward_sapphire COMMAND $<TARGET_FILE:unit-test> relic_reward_sapphire)
add_test(NAME semantic_card_edges COMMAND $<TARGET_FILE:unit-test> semantic_card_edges)
add_test(NAME s3_drawpile_reuse_boundary COMMAND $<TARGET_FILE:unit-test> s3_drawpile_reuse_boundary)
add_test(NAME s3_strategy_fusion_diag COMMAND $<TARGET_FILE:unit-test> s3_strategy_fusion_diag 12345)
add_test(NAME s3_persistent_endturn_chance COMMAND $<TARGET_FILE:unit-test> s3_persistent_endturn_chance 12345)
add_test(NAME thorns_retaliation COMMAND $<TARGET_FILE:unit-test> thorns_retaliation)
add_test(NAME awakened_one_stage2 COMMAND $<TARGET_FILE:unit-test> awakened_one_stage2)
add_test(NAME darkling_victory COMMAND $<TARGET_FILE:unit-test> darkling_victory)
add_test(NAME poison_lose_hp COMMAND $<TARGET_FILE:unit-test> poison_lose_hp)
add_test(NAME time_eater_exhaust COMMAND $<TARGET_FILE:unit-test> time_eater_exhaust)
add_test(NAME simhealth_gamble_empty_hand COMMAND $<TARGET_FILE:unit-test> simhealth_gamble_empty_hand)
add_test(NAME gamblers_brew_legality COMMAND $<TARGET_FILE:unit-test> gamblers_brew_legality)
add_test(NAME simhealth_nonfair_s2_empty COMMAND $<TARGET_FILE:unit-test> simhealth_nonfair_s2_empty)
add_test(NAME simhealth_selection_failure COMMAND $<TARGET_FILE:unit-test> simhealth_selection_failure)
add_test(NAME simhealth_nonfair_s2_selection_failed COMMAND $<TARGET_FILE:unit-test> simhealth_nonfair_s2_selection_failed)
add_test(NAME training_integrity COMMAND $<TARGET_FILE:unit-test> training_integrity)
add_test(NAME rng_state_propagation COMMAND $<TARGET_FILE:unit-test> rng_state_propagation 12345)
add_test(NAME s3_rand64_prior_sampler COMMAND $<TARGET_FILE:unit-test> s3_rand64_prior_sampler)
add_test(NAME rejuv_conditional_blocks COMMAND $<TARGET_FILE:unit-test> rejuv_conditional_blocks)
add_test(NAME live_rejuv_attempt_gate COMMAND $<TARGET_FILE:unit-test> live_rejuv_attempt_gate)
add_test(NAME e2c_observer_scope COMMAND $<TARGET_FILE:unit-test> e2c_observer_scope)
add_test(NAME combat_knowledge COMMAND $<TARGET_FILE:unit-test> combat_knowledge)
add_test(NAME silver_random_bridge COMMAND $<TARGET_FILE:unit-test> silver_random_bridge)
add_test(NAME silver_semantic_action COMMAND $<TARGET_FILE:unit-test> silver_semantic_action)
add_test(NAME silver_searcher_link_closure COMMAND $<TARGET_FILE:silver-native-test>)
add_test(NAME silver_player_status COMMAND $<TARGET_FILE:silver-player-status-test>)
add_test(NAME silver_search_optimization COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:silver-search-optimization-test>)
set_tests_properties(silver_search_optimization PROPERTIES LABELS "integration")
add_test(NAME silver_bridge_boundary COMMAND $<TARGET_FILE:silver-bridge-test>)
# tests/agent is owned by the separate pre-build unittest discovery step in CI.
# Do not register its modules or separate compile-only checks here as well:
# importing those tools during unittest discovery already parses them.
add_test(NAME runic_dome_lifecycle COMMAND $<TARGET_FILE:runic-dome-lifecycle-test>)
add_test(NAME analyze_silver_reuse_scaling_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_reuse_scaling.py --self-test)
add_test(NAME analyze_silver_vnet_leaf_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_vnet_leaf.py --self-test)
add_test(NAME check_benchmark_canary_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/agent/check_benchmark_canary.py --self-test)
add_test(NAME analyze_silver_sticky_quality_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_sticky_quality.py --self-test)
add_test(NAME analyze_silver_root_diagnostic_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_root_diagnostic.py --self-test)
add_test(NAME analyze_silver_adaptive_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_adaptive.py --self-test)
add_test(NAME analyze_postcombat_raw_terminal_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_postcombat_raw_terminal_selftest.py)
add_test(NAME export_win_model_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_export_win_model_selftest.py)
add_test(NAME runwin_e2c_native_parity COMMAND ${CMAKE_COMMAND} -E env
    STS_NATIVE_OOC=0
    STS_RUNWIN_SHADOW_MODEL=${CMAKE_SOURCE_DIR}/tools/runwin_e2c_synthetic.txt
    $<TARGET_FILE:one_combat> runwinparity ${CMAKE_SOURCE_DIR}/tools/runwin_e2c_synthetic_parity.csv)
add_test(NAME runwin_e2c_production_native_parity COMMAND ${CMAKE_COMMAND} -E env
    STS_NATIVE_OOC=0
    STS_RUNWIN_SHADOW_MODEL=${CMAKE_SOURCE_DIR}/models/v_runwin_e2c_v2.txt
    $<TARGET_FILE:one_combat> runwinparity ${CMAKE_SOURCE_DIR}/tests/data/v_runwin_e2c_v2_parity.csv)
add_test(NAME e2c_runwin_projection_parity COMMAND ${CMAKE_COMMAND} -E env
    STS_NATIVE_OOC=0
    $<TARGET_FILE:one_combat> e2cprojectiontest)
set_tests_properties(paired_analysis_selftest py_compile_parity_test py_compile_analyze_ooc_factor check_replay_selftest vnettest_selftest winnettest_selftest battlecontext_roundtrip designer_in_spire scum_nonfair_empty_edges scum_convroot_stale_outcome cardqueue_overflow keys_collect issue_fixes semantic_card_edges thorns_retaliation awakened_one_stage2 darkling_victory poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality simhealth_nonfair_s2_empty simhealth_selection_failure simhealth_nonfair_s2_selection_failed training_integrity e2c_observer_scope analyze_silver_root_diagnostic_selftest analyze_postcombat_raw_terminal_selftest export_win_model_selftest runwin_e2c_native_parity
    runwin_e2c_production_native_parity e2c_runwin_projection_parity PROPERTIES ENVIRONMENT "PYTHONPYCACHEPREFIX=${CMAKE_BINARY_DIR}/pycache")

# Labels provide fast, intention-revealing local tiers while the unfiltered
# linux-gcc-test preset remains the authoritative full CTest suite.
set_tests_properties(battlecontext_roundtrip designer_in_spire cardqueue_overflow keys_collect
    issue_fixes relic_reward_sapphire semantic_card_edges thorns_retaliation awakened_one_stage2 darkling_victory
    poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality
    simhealth_nonfair_s2_empty simhealth_selection_failure simhealth_nonfair_s2_selection_failed
    training_integrity PROPERTIES LABELS "core")
set_tests_properties(vnettest_selftest winnettest_selftest
    scum_nonfair_empty_edges scum_convroot_stale_outcome s3_drawpile_reuse_boundary
    s3_strategy_fusion_diag s3_persistent_endturn_chance rng_state_propagation
    s3_rand64_prior_sampler rejuv_conditional_blocks live_rejuv_attempt_gate
    e2c_observer_scope combat_knowledge silver_random_bridge silver_semantic_action
    silver_searcher_link_closure silver_bridge_boundary runic_dome_lifecycle
    runwin_e2c_native_parity runwin_e2c_production_native_parity
    e2c_runwin_projection_parity PROPERTIES LABELS "integration")
set_tests_properties(selfplay_syntax py_compile_parity_test py_compile_analyze_ooc_factor
    check_replay_selftest check_benchmark_canary_selftest export_win_model_selftest
    PROPERTIES LABELS "tooling")
set_tests_properties(particle_leaf_probe_selftest particle_posterior_probe_selftest
    analyze_silver_reuse_scaling_selftest analyze_silver_vnet_leaf_selftest
    analyze_silver_sticky_quality_selftest analyze_silver_root_diagnostic_selftest
    analyze_silver_adaptive_selftest analyze_postcombat_raw_terminal_selftest
    PROPERTIES LABELS "research-repro")
set_property(TEST selfplay_syntax paired_analysis_selftest check_replay_selftest
    battlecontext_roundtrip issue_fixes APPEND PROPERTY LABELS "smoke")
