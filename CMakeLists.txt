cmake_minimum_required(VERSION 3.19)
project(
        sts_lightspeed
        VERSION 0.1
        DESCRIPTION "High Performance, rng accurate implementation of Slay the Spire with tools for tree search and ml."
        LANGUAGES CXX)

find_package(OpenSSL QUIET COMPONENTS Crypto)
if(NOT OpenSSL_FOUND)
    message(STATUS "OpenSSL Crypto not found; non-CTM targets remain available, CTM runtime targets require OpenSSL")
endif()
function(link_ctm_crypto target)
    if(OpenSSL_FOUND)
        target_link_libraries(${target} PRIVATE OpenSSL::Crypto)
    endif()
endfunction()

enable_testing()

file (GLOB_RECURSE sts_lightspeed_SOURCES CONFIGURE_DEPENDS "src/*.cpp")

set(CMAKE_CXX_STANDARD 20)
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

# Real live Runic-Dome lifecycle coverage: the observer is configured before
# battle init and exercises monster turns, chained rerolls, and intent query.
add_executable(runic-dome-lifecycle-test apps/runic_dome_lifecycle_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(runic-dome-lifecycle-test PROPERTIES OUTPUT_NAME runic_dome_lifecycle_test)
target_include_directories(runic-dome-lifecycle-test PRIVATE include json/include)
target_link_options(runic-dome-lifecycle-test PRIVATE -Wl,--gc-sections)

add_executable(silver-useless-replay apps/silver_useless_replay.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-useless-replay PROPERTIES OUTPUT_NAME silver_useless_replay)
target_include_directories(silver-useless-replay PRIVATE include json/include)

# Default-off observer neutrality: live combat core only.
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
    apps/one_combat/screen_leaf_snapshot.cpp
    apps/one_combat/screen_leaf_continuations.cpp
    apps/one_combat/screen_leaf_s0.cpp
    apps/one_combat/screen_leaf_probes.cpp
    apps/one_combat/screen_leaf_net.cpp
    apps/one_combat/screen_leaf_gbm.cpp
    apps/one_combat/run_features.cpp apps/one_combat/compact_tree.cpp
    apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp
    apps/one_combat/e2c_capture.cpp
    apps/one_combat/ooc_mcts_adapter.cpp
    apps/one_combat/ooc_native_fallback.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    apps/one_combat/ooc_policy.cpp
    apps/one_combat/ooc_v4_encoding.cpp
    apps/one_combat/run_driver.cpp
    apps/one_combat/differential_state.cpp
    apps/one_combat/differential_replay_native.cpp
    apps/one_combat/run_trace.cpp
    apps/one_combat/semantic_pilot.cpp
    apps/one_combat/combat_datasets.cpp
    apps/one_combat/ctm_offline_score.cpp
    apps/one_combat/ooc_factor_eval.cpp
    apps/one_combat/strategic_gen.cpp
    apps/one_combat/counterfactual_gen.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat PUBLIC include)
target_include_directories(one_combat PUBLIC json/include)
target_include_directories(one_combat PRIVATE apps)
link_ctm_crypto(one_combat)
target_link_options(one_combat PRIVATE -Wl,--gc-sections)

# Offline full-state transport for frozen #379 replay; no generated game seeds.
add_executable(screen_leaf_snapshot_test
    apps/one_combat/screen_leaf_snapshot.cpp
    apps/one_combat/screen_leaf_snapshot_test.cpp)
target_include_directories(screen_leaf_snapshot_test PRIVATE include json/include apps/one_combat)
add_test(NAME screen_leaf_snapshot COMMAND screen_leaf_snapshot_test)
add_executable(screen_leaf_continuations_test
    apps/one_combat/screen_leaf_snapshot.cpp
    apps/one_combat/screen_leaf_continuations.cpp
    apps/one_combat/screen_leaf_continuations_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(screen_leaf_continuations_test PRIVATE include json/include apps/one_combat)
add_test(NAME screen_leaf_continuations
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh $<TARGET_FILE:screen_leaf_continuations_test>)

# Read-only newline-delimited JSON endpoint for the private live-model
# inspector.  Keep it separate from the simulator driver until a proven
# Java-game importer can construct the native observation contracts.
add_executable(one_combat_advisor
    apps/one_combat/advisor_stdio.cpp
    apps/one_combat/advisor_protocol.cpp
    apps/one_combat/live_silver_importer.cpp
    apps/one_combat/live_silver_mapping.cpp
    apps/one_combat/native_silver_advisor.cpp)
target_include_directories(one_combat_advisor PUBLIC json/include)
target_sources(one_combat_advisor PRIVATE
    apps/one_combat/live_ooc_state.cpp
    apps/one_combat/differential_state.cpp
    apps/one_combat/live_ooc_policy.cpp
    apps/one_combat/ooc_v4_encoding.cpp
    apps/one_combat/run_features.cpp
    apps/one_combat/live_ooc_importer.cpp
    apps/one_combat/ooc_mcts_adapter.cpp
    apps/one_combat/ooc_native_fallback.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    apps/one_combat/compact_tree.cpp
    apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp)
target_link_libraries(one_combat_advisor PRIVATE sts_core_objects)
link_ctm_crypto(one_combat_advisor)
target_link_options(one_combat_advisor PRIVATE -Wl,--gc-sections)
target_compile_definitions(one_combat_advisor PRIVATE STS_LIVE_ADVISOR=1)
add_test(NAME live_advisor_protocol COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/live_advisor_protocol.py $<TARGET_FILE:one_combat_advisor>
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_near_full_except_smoke_v2.native)
set_tests_properties(live_advisor_protocol PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")
add_test(NAME live_game_runtime COMMAND python3 -m unittest tests.test_live_game_runtime)
set_tests_properties(live_game_runtime PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
add_test(NAME render_ooc_mcts COMMAND python3 -m unittest tests.test_render_ooc_mcts)
set_tests_properties(render_ooc_mcts PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
find_program(STS_NODE_EXECUTABLE node)
if(STS_NODE_EXECUTABLE)
    add_test(NAME ooc_graph_logic COMMAND ${STS_NODE_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/test_ooc_graph_logic.js)
    set_tests_properties(ooc_graph_logic PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
endif()

add_executable(test_live_ooc_policy apps/test_live_ooc_policy.cpp
    apps/one_combat/live_ooc_policy.cpp apps/one_combat/ooc_v4_encoding.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    apps/one_combat/run_features.cpp apps/one_combat/ooc_mcts_adapter.cpp
    apps/one_combat/ooc_native_fallback.cpp
    apps/one_combat/compact_tree.cpp apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp apps/one_combat/combat_transition_native_contract.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(test_live_ooc_policy PRIVATE include json/include apps)
link_ctm_crypto(test_live_ooc_policy)
target_compile_definitions(test_live_ooc_policy PRIVATE STS_LIVE_ADVISOR=1)
add_test(NAME live_ooc_policy COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:test_live_ooc_policy> ${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native)
set_tests_properties(live_ooc_policy PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(live_ooc_parity_test apps/live_ooc_parity_test.cpp
    apps/one_combat/live_ooc_state.cpp apps/one_combat/live_ooc_policy.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    apps/one_combat/ooc_v4_encoding.cpp apps/one_combat/run_features.cpp
    apps/one_combat/ooc_mcts_adapter.cpp apps/one_combat/compact_tree.cpp
    apps/one_combat/ooc_native_fallback.cpp
    apps/one_combat/combat_predictor_input.cpp apps/one_combat/combat_transition.cpp
    apps/one_combat/combat_transition_near_full.cpp apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(live_ooc_parity_test PRIVATE include json/include apps)
link_ctm_crypto(live_ooc_parity_test)
target_compile_definitions(live_ooc_parity_test PRIVATE STS_LIVE_ADVISOR=1)
add_test(NAME live_ooc_parity COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:live_ooc_parity_test>
    ${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native)
set_tests_properties(live_ooc_parity PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_test(NAME live_ooc_protocol COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/live_ooc_protocol.py
    $<TARGET_FILE:one_combat_advisor> $<TARGET_FILE:live_ooc_parity_test>
    ${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_near_full_except_smoke_v2.native
    ${CMAKE_SOURCE_DIR}/models/v_win_trees.txt)
set_tests_properties(live_ooc_protocol PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")
add_test(NAME live_game_driver COMMAND python3 -m unittest tests.test_live_game_driver)
add_test(NAME differential_trace COMMAND python3 -m unittest tests.test_differential_trace)
add_test(NAME native_differential_replay COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/native_differential_replay.py $<TARGET_FILE:one_combat>)
set_tests_properties(live_game_driver PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
set_tests_properties(differential_trace PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
set_tests_properties(native_differential_replay PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(live_ctm_importer_test apps/live_ctm_importer_test.cpp
    apps/one_combat/live_ooc_importer.cpp
    apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(live_ctm_importer_test PRIVATE include json/include)
link_ctm_crypto(live_ctm_importer_test)
add_test(NAME live_ctm_importer
    COMMAND $<TARGET_FILE:live_ctm_importer_test>
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_near_full_except_smoke_v2.native)
set_tests_properties(live_ctm_importer PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")

add_executable(live_silver_importer_test apps/live_silver_importer_test.cpp
    apps/one_combat/live_silver_importer.cpp apps/one_combat/live_silver_mapping.cpp
    apps/one_combat/native_silver_advisor.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(live_silver_importer_test PRIVATE include json/include apps)
target_link_options(live_silver_importer_test PRIVATE -Wl,--gc-sections)
add_test(NAME live_silver_importer COMMAND $<TARGET_FILE:live_silver_importer_test>)

add_executable(one_combat_feature_test apps/one_combat_feature_test.cpp
    apps/one_combat/run_features.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat_feature_test PUBLIC include)
target_include_directories(one_combat_feature_test PUBLIC json/include)

add_executable(one_combat_tree_test apps/one_combat_tree_test.cpp
    apps/one_combat/compact_tree.cpp apps/one_combat/run_features.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat_tree_test PUBLIC include json/include)
add_test(NAME one_combat_tree_parity COMMAND $<TARGET_FILE:one_combat_tree_test>
    ${CMAKE_SOURCE_DIR}/models/v_win_trees.txt ${CMAKE_SOURCE_DIR}/models/v_rich_trees.txt
    ${CMAKE_SOURCE_DIR}/models/v_runwin_e2c_v2.txt)

add_executable(parity_test apps/parity_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(parity_test PUBLIC include)
target_include_directories(parity_test PUBLIC json/include)

# "test" is reserved by CTest, so the manual dispatcher target is unit-test
# with OUTPUT_NAME "test" to keep the build/test binary path stable.
add_executable(unit-test apps/test.cpp
    apps/test_ooc_reward_continuation.cpp apps/test_ooc_semantic.cpp
    apps/test_ooc_semantic_pipeline.cpp
    apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(unit-test PROPERTIES OUTPUT_NAME test)
target_include_directories(unit-test PUBLIC include)
target_link_directories(unit-test PUBLIC json::nlohmann_json)
target_include_directories(unit-test PUBLIC json/include)

add_executable(small-test apps/small-test.cpp bindings/bindings-util.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_link_directories(small-test PRIVATE json::nlohmann_json)
target_include_directories(small-test PUBLIC include)
target_include_directories(small-test PUBLIC json/include)
target_include_directories(small-test PUBLIC bindings)

add_executable(combat-predictor-input-test
    apps/combat_predictor_input_test.cpp
    apps/one_combat/combat_predictor_input.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat-predictor-input-test PUBLIC include json/include)

# Offline generic planner test: no simulator or production policy dependency.
add_executable(ooc-mcts-test apps/ooc_mcts_test.cpp src/sim/search/OocMctsPlanner.cpp)
target_include_directories(ooc-mcts-test PRIVATE include)
add_test(NAME ooc_mcts COMMAND $<TARGET_FILE:ooc-mcts-test>)
set_tests_properties(ooc_mcts PROPERTIES LABELS "core")

# CTest entries below cover checks that do not depend on apps/test.cpp
# subcommands (apps/test.cpp is a manual command dispatcher; its subcommands
# receive CTest entries separately). bash -n only parses, never executes.
add_test(NAME silver_useless_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/tests/test_silver_useless.py)
add_test(NAME run_profile_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/tests/test_run_profile.py)
add_test(NAME paired_analysis_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/paired_analysis.py --self-test)
add_test(NAME silver_tree_profile_analysis COMMAND python3
    ${CMAKE_SOURCE_DIR}/tools/tests/test_silver_tree_profile.py)
add_test(NAME py_compile_parity_test COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/parity_test.py)
add_test(NAME semantic_confirmation_analysis COMMAND python3 -m unittest
    tests.test_ooc_semantic_confirmation tests.test_semantic_confirmation_runner
    tools.test_semantic_combat_coverage -q)
set_tests_properties(semantic_confirmation_analysis PROPERTIES
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS "research-repro;tooling")
add_test(NAME py_compile_analyze_ooc_factor COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/analyze_ooc_factor.py)
add_test(NAME check_replay_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/check_replay.py --self-test)
add_test(NAME vnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/vnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME winnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/winnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME one_combat_feature_regression COMMAND $<TARGET_FILE:one_combat_feature_test>)
add_test(NAME battlecontext_roundtrip COMMAND $<TARGET_FILE:unit-test> battlecontext_roundtrip)
add_test(NAME designer_in_spire COMMAND $<TARGET_FILE:unit-test> designer_in_spire)
add_test(NAME cardqueue_overflow COMMAND $<TARGET_FILE:unit-test> cardqueue_overflow)
add_test(NAME keys_collect COMMAND $<TARGET_FILE:unit-test> keys_collect)
add_test(NAME issue_fixes COMMAND $<TARGET_FILE:unit-test> issue_fixes)
add_test(NAME first_strong_exclusions COMMAND $<TARGET_FILE:unit-test> first_strong_exclusions)
set_tests_properties(first_strong_exclusions PROPERTIES LABELS "core")
add_test(NAME simulator_correctness_pr9_19 COMMAND $<TARGET_FILE:unit-test> simulator_correctness_pr9_19)
add_test(NAME simulator_relic_fidelity COMMAND $<TARGET_FILE:unit-test> simulator_relic_fidelity)
set_tests_properties(simulator_correctness_pr9_19 PROPERTIES LABELS "core")
set_tests_properties(simulator_relic_fidelity PROPERTIES LABELS "core")
add_test(NAME monster_ai_java_parity COMMAND $<TARGET_FILE:unit-test> monster_ai_java_parity)
set_tests_properties(monster_ai_java_parity PROPERTIES LABELS "core")
add_test(NAME ironclad_card_java_parity COMMAND $<TARGET_FILE:unit-test> ironclad_card_java_parity)
set_tests_properties(ironclad_card_java_parity PROPERTIES LABELS "core")
add_test(NAME match_and_keep COMMAND $<TARGET_FILE:unit-test> match_and_keep)
set_tests_properties(match_and_keep PROPERTIES LABELS "core")
add_test(NAME silver_escape_penalty COMMAND $<TARGET_FILE:unit-test> silver_escape_penalty)
set_tests_properties(silver_escape_penalty PROPERTIES LABELS "core")
add_test(NAME ooc_reward_continuation COMMAND $<TARGET_FILE:unit-test> ooc_reward_continuation)
add_test(NAME ooc_semantic COMMAND $<TARGET_FILE:unit-test> ooc_semantic)
add_test(NAME ironclad_card_coverage COMMAND $<TARGET_FILE:unit-test> ironclad_card_coverage)
add_test(NAME ooc_semantic_pipeline COMMAND $<TARGET_FILE:unit-test> ooc_semantic_pipeline)
add_test(NAME ooc_semantic_producer COMMAND $<TARGET_FILE:one_combat> oocsemanticselftest)
add_test(NAME combat_evaluator_semantic_branch_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_evaluator_semantic_branch.py)
set_tests_properties(combat_evaluator_semantic_branch_contract PROPERTIES LABELS "core;integration")
add_test(NAME battle_start_runout_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_battle_start_runout_contract.py)
set_tests_properties(battle_start_runout_contract PROPERTIES LABELS "core;research-repro")
add_test(NAME vwin_refresh_policy_export
    COMMAND $<TARGET_FILE:one_combat> vwinrefreshpolicyspec ${CMAKE_CURRENT_BINARY_DIR}/vwin_policy_export.json)
set_tests_properties(vwin_refresh_policy_export PROPERTIES
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PASS_REGULAR_EXPRESSION "vwin policy export: PASS")
add_test(NAME vwin_refresh_producer_contract COMMAND $<TARGET_FILE:one_combat> vwinrefreshselftest)
set_tests_properties(vwin_refresh_producer_contract PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_compound_decision_contract
    COMMAND $<TARGET_FILE:one_combat> vwinrefreshcompoundselftest)
set_tests_properties(vwin_refresh_compound_decision_contract PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_decision_sink_contract
    COMMAND $<TARGET_FILE:one_combat> vwinrefreshdecisionsinkselftest)
set_tests_properties(vwin_refresh_decision_sink_contract PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_match_and_keep_isolation
    COMMAND $<TARGET_FILE:one_combat> vwinrefreshmatchkeepselftest)
set_tests_properties(vwin_refresh_match_and_keep_isolation PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_reward_continuation
    COMMAND $<TARGET_FILE:one_combat> vwinrefreshcontinuationselftest)
set_tests_properties(vwin_refresh_reward_continuation PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_card_reward_classification
    COMMAND $<TARGET_FILE:one_combat> vwinrefreshrewardselftest)
set_tests_properties(vwin_refresh_card_reward_classification PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_fatal_runout_fight_count
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
        $<TARGET_FILE:one_combat> vwinrefreshfatalcountselftest 13000000 100)
set_tests_properties(vwin_refresh_fatal_runout_fight_count PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_rejects_vpath_override
    COMMAND ${CMAKE_COMMAND} -E env STS_VPATH=1
        $<TARGET_FILE:one_combat> vwinvpathguardselftest)
set_tests_properties(vwin_refresh_rejects_vpath_override PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_branch_parity
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
        $<TARGET_FILE:one_combat> vwinrefreshbranchselftest 4000598 100 0)
set_tests_properties(vwin_refresh_branch_parity PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_validator_selftest
    COMMAND python3 -m unittest tools.test_vwin_refresh_contract -q)
set_tests_properties(vwin_refresh_validator_selftest PROPERTIES
    LABELS "research-repro;tooling" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_refresh_corpus_selftest
    COMMAND python3 -m unittest tools.test_vwin_refresh_corpus -q)
set_tests_properties(vwin_refresh_corpus_selftest PROPERTIES
    LABELS "core;tooling" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_e1_focal_selftest
    COMMAND python3 -m unittest tools.test_vwin_e1_focal -q)
set_tests_properties(vwin_e1_focal_selftest PROPERTIES
    LABELS "core;tooling" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME boss_headroom_347_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_boss_headroom_347.py --self-test)
set_tests_properties(boss_headroom_347_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME silver_param_screen_400_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_param_screen_400.py --self-test)
set_tests_properties(silver_param_screen_400_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME vwin_public_info_397_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_vwin_public_info_397.py --self-test)
set_tests_properties(vwin_public_info_397_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME rich_domain_397_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_rich_domain_397.py --self-test)
set_tests_properties(rich_domain_397_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME vwin_history_397_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_vwin_history_397.py --self-test)
set_tests_properties(vwin_history_397_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME vwin_derived_397_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_vwin_derived_397.py --self-test)
set_tests_properties(vwin_derived_397_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME vwin_derived_rooms_397_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_vwin_derived_rooms_397.py --self-test)
set_tests_properties(vwin_derived_rooms_397_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME vwin_mlp_397_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_vwin_mlp_397.py --self-test)
set_tests_properties(vwin_mlp_397_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME silver_learned_stop_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/silver_learned_stop.py selftest)
set_tests_properties(silver_learned_stop_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME silver_stop_replay_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_stop_replay.py --self-test)
set_tests_properties(silver_stop_replay_analysis_selftest PROPERTIES
    LABELS "research-repro;tooling")
add_test(NAME silver_param_screen_400_seed_guard_rejects_zero
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh guard-only
        $<TARGET_FILE:one_combat> silverparams400gen 0 10000 0 /tmp/sp400 40000000 teacher.json)
set_tests_properties(silver_param_screen_400_seed_guard_rejects_zero PROPERTIES WILL_FAIL TRUE)
add_test(NAME silver_param_screen_400_rejects_non_exact_budget
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
        $<TARGET_FILE:one_combat> silverparams400gen 1 1000 0 /tmp/sp400-invalid 40000000 teacher.json)
set_tests_properties(silver_param_screen_400_rejects_non_exact_budget PROPERTIES WILL_FAIL TRUE)
add_test(NAME silver_stop_replay_seed_guard_rejects_zero
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh guard-only
        $<TARGET_FILE:one_combat> silverstopreplaygen 0 10000 0 /tmp/ssr 42000000 teacher.json)
set_tests_properties(silver_stop_replay_seed_guard_rejects_zero PROPERTIES WILL_FAIL TRUE)
add_test(NAME silver_stop_replay_rejects_non_exact_budget
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
        $<TARGET_FILE:one_combat> silverstopreplaygen 1 1000 0 /tmp/ssr-invalid 42000000 teacher.json)
set_tests_properties(silver_stop_replay_rejects_non_exact_budget PROPERTIES WILL_FAIL TRUE)
# The invalid option aborts the process before any seed runs; `!` turns that
# into a pass (WILL_FAIL does not accept an abort).
add_test(NAME silver_learned_stop_rejects_small_boss_max
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 0 46009000 /tmp/sls-invalid.csv")
set_tests_properties(silver_learned_stop_rejects_small_boss_max PROPERTIES
    ENVIRONMENT "STS_SILVER_ADAPTIVE=0;STS_SILVER_LEARNED_STOP=1;STS_SILVER_LEARNED_STOP_BOSS_MAX=5000"
    PASS_REGULAR_EXPRESSION "STS_SILVER_LEARNED_STOP_BOSS_MAX must be 0 or above 10000")
add_test(NAME silver_learned_stop_rejects_boss_fallback_without_learned_stop
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 0 46009000 /tmp/sls-invalid.csv")
set_tests_properties(silver_learned_stop_rejects_boss_fallback_without_learned_stop PROPERTIES
    ENVIRONMENT "STS_SILVER_ADAPTIVE=0;STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=1"
    PASS_REGULAR_EXPRESSION "STS_SILVER_LEARNED_STOP_BOSS_FALLBACK requires STS_SILVER_LEARNED_STOP=1")
add_test(NAME vwin_refresh_seed_guard_accepts_positive
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh guard-only
        $<TARGET_FILE:one_combat> vwinrefreshgen 128 10000 0 /tmp/vwin 13000000 teacher.json 1)
add_test(NAME vwin_refresh_seed_guard_rejects_zero
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh guard-only
        $<TARGET_FILE:one_combat> vwinrefreshgen 0 10000 0 /tmp/vwin 13000000 teacher.json 1)
set_tests_properties(vwin_refresh_seed_guard_rejects_zero PROPERTIES WILL_FAIL TRUE)
add_test(NAME vwin_refresh_rejects_negative_seed_start
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
        $<TARGET_FILE:one_combat> vwinrefreshgen 1 10000 0 /tmp/vwin-invalid-offset -1 teacher.json 1)
set_tests_properties(vwin_refresh_rejects_negative_seed_start PROPERTIES WILL_FAIL TRUE)
add_test(NAME ooc_policy_parity
    COMMAND $<TARGET_FILE:one_combat> oocpolicyparity 4000598 100 0)
set_tests_properties(ooc_policy_parity PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME teacher_schema_compat COMMAND $<TARGET_FILE:one_combat> teacher_schema_compat)
set_tests_properties(teacher_schema_compat PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME learned_stop_teacher_contract COMMAND $<TARGET_FILE:one_combat> learnedstopteacherselftest)
set_tests_properties(learned_stop_teacher_contract PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_offline_score_rows COMMAND $<TARGET_FILE:one_combat> ctmscoreselftest)
set_tests_properties(ctm_offline_score_rows PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(ooc_semantic_producer PROPERTIES WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
add_test(NAME ooc_semantic_smith COMMAND $<TARGET_FILE:unit-test> ooc_semantic_smith)
set_tests_properties(ooc_semantic ooc_semantic_pipeline ooc_semantic_producer ooc_semantic_smith ooc_reward_continuation
    PROPERTIES LABELS "core;integration")
add_test(NAME relic_reward_sapphire COMMAND $<TARGET_FILE:unit-test> relic_reward_sapphire)
add_test(NAME thorns_retaliation COMMAND $<TARGET_FILE:unit-test> thorns_retaliation)
add_test(NAME awakened_one_stage2 COMMAND $<TARGET_FILE:unit-test> awakened_one_stage2)
add_test(NAME darkling_victory COMMAND $<TARGET_FILE:unit-test> darkling_victory)
add_test(NAME poison_lose_hp COMMAND $<TARGET_FILE:unit-test> poison_lose_hp)
add_test(NAME time_eater_exhaust COMMAND $<TARGET_FILE:unit-test> time_eater_exhaust)
add_test(NAME simhealth_gamble_empty_hand COMMAND $<TARGET_FILE:unit-test> simhealth_gamble_empty_hand)
add_test(NAME gamblers_brew_legality COMMAND $<TARGET_FILE:unit-test> gamblers_brew_legality)
add_test(NAME simhealth_selection_failure COMMAND $<TARGET_FILE:unit-test> simhealth_selection_failure)
add_test(NAME training_integrity COMMAND $<TARGET_FILE:unit-test> training_integrity)
add_test(NAME e2c_observer_scope COMMAND $<TARGET_FILE:unit-test> e2c_observer_scope)
add_test(NAME combat_knowledge COMMAND $<TARGET_FILE:unit-test> combat_knowledge)
add_test(NAME persistent_latent_damage COMMAND $<TARGET_FILE:unit-test> persistent_latent_damage)
add_test(NAME battle_equality COMMAND $<TARGET_FILE:unit-test> battle_equality)
add_test(NAME card_pile COMMAND $<TARGET_FILE:unit-test> card_pile)
add_test(NAME card_pile_engine COMMAND $<TARGET_FILE:unit-test> card_pile_engine)
add_test(NAME violence_large_draw_pile COMMAND $<TARGET_FILE:unit-test> violence_large_draw_pile)
add_test(NAME stasis_large_pile COMMAND $<TARGET_FILE:unit-test> stasis_large_pile)
add_test(NAME silver_searcher COMMAND $<TARGET_FILE:unit-test> silver_searcher)
add_test(NAME silver_wire_state COMMAND $<TARGET_FILE:unit-test> silver_wire_state)
add_test(NAME silver_semantic_action COMMAND $<TARGET_FILE:unit-test> silver_semantic_action)
# tests/agent is owned by the separate pre-build unittest discovery step in CI.
# Do not register its modules or separate compile-only checks here as well:
# importing those tools during unittest discovery already parses them.
add_test(NAME runic_dome_lifecycle COMMAND $<TARGET_FILE:runic-dome-lifecycle-test>)
add_test(NAME check_benchmark_canary_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/agent/check_benchmark_canary.py --self-test)
add_test(NAME analyze_postcombat_raw_terminal_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_postcombat_raw_terminal_selftest.py)
add_test(NAME vwin_terminal_pricing_audit_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analysis/vwin_terminal_pricing_audit.py --self-test)
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
add_test(NAME combat_transition_oracle COMMAND $<TARGET_FILE:unit-test> combat_transition_oracle)
add_test(NAME combat_predictor_input COMMAND $<TARGET_FILE:combat-predictor-input-test>)
add_test(NAME combat_predictor_input_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_predictor_input_contract.py -q)
add_test(NAME combat_transition_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_contract.py)
add_test(NAME strategic_tok_state_cache_order_selftest
    COMMAND python3 -m unittest tools.test_strategic_tok_state_cache)
set_tests_properties(strategic_tok_state_cache_order_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_model_experiment_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_model_experiment.py)
add_test(NAME ctm_corpus_adapter_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_ctm_corpus_adapter.py)
add_test(NAME ctm_survival_compare_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_ctm_survival_compare.py)
add_test(NAME ctm_pins_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_ctm_pins.py)
add_test(NAME ctm_near_full_inputs_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_ctm_near_full_inputs.py)
add_test(NAME combat_transition_attention_hpo_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_attention_hpo.py)
add_test(NAME combat_transition_attention_hpo_promote_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_attention_hpo_promote.py)
add_test(NAME combat_transition_rng_audit_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_rng_audit.py)
add_test(NAME combat_transition_surrogate_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_surrogate.py)
add_test(NAME combat_transition_attention_ablation_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_attention_ablation.py)
add_test(NAME combat_transition_frozen_composition_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_frozen_composition.py)
add_test(NAME combat_transition_potion_decoder_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_potion_decoder.py)
add_test(NAME combat_transition_stochastic_hp_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_stochastic_hp.py)
add_test(NAME combat_transition_shared_hp_encoder_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_shared_hp_encoder)
set_tests_properties(combat_transition_shared_hp_encoder_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_shared_maxhp_encoder_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_shared_maxhp_encoder)
set_tests_properties(combat_transition_shared_maxhp_encoder_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_shared_encoder_distill_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_shared_encoder_distill)
set_tests_properties(combat_transition_shared_encoder_distill_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_shared_encoder_potion_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_shared_encoder_potion)
set_tests_properties(combat_transition_shared_encoder_potion_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_deepset_train_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_deepset_train)
set_tests_properties(combat_transition_survival_deepset_train_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_deepset_sweep_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_deepset_sweep)
set_tests_properties(combat_transition_survival_deepset_sweep_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_platt_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_platt)
set_tests_properties(combat_transition_survival_platt_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_mlp_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_mlp)
set_tests_properties(combat_transition_survival_mlp_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_mlp_head_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_mlp_head)
set_tests_properties(combat_transition_survival_mlp_head_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_deepset_aux_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_deepset_aux)
set_tests_properties(combat_transition_survival_deepset_aux_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_survival_wide96_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_survival_wide96)
set_tests_properties(combat_transition_survival_wide96_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_wide96_pretrain_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_wide96_pretrain)
set_tests_properties(combat_transition_wide96_pretrain_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_relic_trajectory_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_relic_trajectory.py)
add_test(NAME combat_transition_composed_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_composed.py)
add_test(NAME ooc_mcts_parameter_search_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_ooc_mcts_parameter_search.py)
add_test(NAME ooc_mcts_gameplay_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_analyze_ooc_mcts_gameplay.py)
add_test(NAME ooc_root_checkpoint_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_analyze_ooc_root_checkpoints.py)
add_test(NAME combat_transition_expanded_support_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_expanded_support.py)
add_test(NAME combat_transition_remaining_census_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_remaining_census.py)
add_test(NAME combat_transition_gold_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_gold.py)
add_test(NAME combat_transition_sparse_events_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_sparse_events)
add_test(NAME combat_transition_brew_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_brew)
add_test(NAME combat_transition_potion_trajectory_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_potion_trajectory)
add_test(NAME combat_transition_near_full_downstream_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_near_full_downstream)
add_test(NAME combat_transition_shared_hp_downstream_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_shared_hp_downstream)
add_test(NAME combat_transition_near_full_sampler_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_near_full_sampler)
add_test(NAME combat_transition_near_full_relic_ancestral_selftest
    COMMAND python3 -m unittest tools.test_combat_transition_near_full_relic_ancestral)
set_tests_properties(combat_transition_sparse_events_selftest combat_transition_brew_selftest combat_transition_potion_trajectory_selftest combat_transition_near_full_downstream_selftest combat_transition_shared_hp_downstream_selftest combat_transition_near_full_sampler_selftest combat_transition_near_full_relic_ancestral_selftest
    PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "research-repro")
add_test(NAME combat_transition_native_fixture
    COMMAND $<TARGET_FILE:one_combat> combattransitionselftest
        ${CMAKE_CURRENT_BINARY_DIR}/combat_transition_fixture.jsonl
        ${CMAKE_CURRENT_BINARY_DIR}/combat_transition_fixture.manifest.json)
add_test(NAME combat_transition_active_lizard_fixture
    COMMAND $<TARGET_FILE:one_combat> combattransitionlizardselftest)
set_tests_properties(combat_transition_active_lizard_fixture PROPERTIES
    ENVIRONMENT "STS_NATIVE_OOC=0")
add_test(NAME collect_lizard_stage_c_shards_selftest
    COMMAND python3 -m unittest tools.test_collect_lizard_stage_c_shards)
set_tests_properties(collect_lizard_stage_c_shards_selftest PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "research-repro")
add_test(NAME combat_transition_fixture_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/combat_transition_contract.py
        ${CMAKE_CURRENT_BINARY_DIR}/combat_transition_fixture.manifest.json)
set_tests_properties(combat_transition_native_fixture
    PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(combat_transition_fixture_contract
    PROPERTIES DEPENDS combat_transition_native_fixture)
set_tests_properties(paired_analysis_selftest py_compile_parity_test py_compile_analyze_ooc_factor check_replay_selftest vnettest_selftest winnettest_selftest battlecontext_roundtrip designer_in_spire cardqueue_overflow keys_collect issue_fixes thorns_retaliation awakened_one_stage2 darkling_victory poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality simhealth_selection_failure training_integrity e2c_observer_scope analyze_postcombat_raw_terminal_selftest export_win_model_selftest runwin_e2c_native_parity
    runwin_e2c_production_native_parity e2c_runwin_projection_parity PROPERTIES ENVIRONMENT "PYTHONPYCACHEPREFIX=${CMAKE_BINARY_DIR}/pycache")

# Labels provide fast, intention-revealing local tiers while the unfiltered
# linux-gcc-test preset remains the authoritative full CTest suite.
set_tests_properties(battlecontext_roundtrip designer_in_spire cardqueue_overflow keys_collect
    issue_fixes relic_reward_sapphire thorns_retaliation awakened_one_stage2 darkling_victory
    poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality
    simhealth_selection_failure battle_equality card_pile card_pile_engine violence_large_draw_pile
    stasis_large_pile
    silver_searcher silver_wire_state
    training_integrity PROPERTIES LABELS "core")
set_tests_properties(vnettest_selftest winnettest_selftest
    e2c_observer_scope combat_knowledge silver_semantic_action runic_dome_lifecycle
    runwin_e2c_native_parity runwin_e2c_production_native_parity
    e2c_runwin_projection_parity PROPERTIES LABELS "integration")
set_tests_properties(py_compile_parity_test py_compile_analyze_ooc_factor
    check_replay_selftest check_benchmark_canary_selftest export_win_model_selftest
    PROPERTIES LABELS "tooling")
set_tests_properties(analyze_postcombat_raw_terminal_selftest vwin_terminal_pricing_audit_selftest PROPERTIES LABELS "research-repro")
set_property(TEST paired_analysis_selftest check_replay_selftest
    battlecontext_roundtrip issue_fixes APPEND PROPERTY LABELS "smoke")

add_test(NAME ooc_mcts_adapter COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:one_combat> oocmctsselftest)
set_tests_properties(ooc_mcts_adapter PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration" ENVIRONMENT "STS_NATIVE_OOC=1;STS_OOC_STRATEGIC_TOK_NN=${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native")

# Captured-state probability probe; no gameplay or default integration.
add_executable(combat_transition_runtime_probe tests/combat_transition_runtime_probe.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    apps/one_combat/combat_predictor_input.cpp apps/one_combat/combat_transition.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat_transition_runtime_probe PRIVATE include json/include)
link_ctm_crypto(combat_transition_runtime_probe)
add_test(NAME combat_transition_native_contract COMMAND python3 -m unittest
    tests.test_combat_transition_native_contract -v)
set_tests_properties(combat_transition_native_contract PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME combat_transition_runtime_loader COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_combat_transition_runtime_loader.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(combat_transition_runtime_loader PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")

add_test(NAME vwin_override COMMAND python3
    ${CMAKE_SOURCE_DIR}/tools/test_vwin_override.py $<TARGET_FILE:one_combat>)
set_tests_properties(vwin_override PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")

add_test(NAME ooc_mcts_live_startup COMMAND python3
    ${CMAKE_SOURCE_DIR}/tools/verify/ooc_mcts_live_startup.py $<TARGET_FILE:one_combat>
    --artifact ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_near_full_except_smoke_v2.native)
set_tests_properties(ooc_mcts_live_startup PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")

add_test(NAME combat_transition_final_support_selftest COMMAND python3 -m unittest tools.test_combat_transition_final_support)
set_tests_properties(combat_transition_final_support_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME combat_transition_near_full_artifact COMMAND python3 -m unittest tests.test_combat_transition_near_full_artifact)
set_tests_properties(combat_transition_near_full_artifact PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    ENVIRONMENT "STS_COMBAT_TRANSITION_PROBE=$<TARGET_FILE:combat_transition_runtime_probe>" LABELS "integration")
