cmake_minimum_required(VERSION 3.19)
project(
        sts_lightspeed
        VERSION 0.1
        DESCRIPTION "High Performance, rng accurate implementation of Slay the Spire with tools for tree search and ml."
        LANGUAGES CXX)

find_package(OpenSSL REQUIRED COMPONENTS Crypto)

enable_testing()

file (GLOB_RECURSE sts_lightspeed_SOURCES CONFIGURE_DEPENDS "src/*.cpp")
list(REMOVE_ITEM sts_lightspeed_SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/src/sim/search/SilverPriorNet.cpp")

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
add_library(silver_prior_runtime STATIC src/sim/search/SilverPriorNet.cpp)
set_target_properties(silver_prior_runtime PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver_prior_runtime PRIVATE include json/include)
target_link_libraries(silver_prior_runtime PUBLIC silver_combat_search_bridge)

add_library(silver_live_backend STATIC third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp)
set_target_properties(silver_live_backend PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(silver_live_backend PRIVATE include json/include)
target_link_libraries(silver_live_backend PUBLIC silver_combat_search_bridge silver_prior_runtime)

add_executable(silver-native-test apps/silver_native_test.cpp)
set_target_properties(silver-native-test PROPERTIES OUTPUT_NAME silver_native_test)
target_include_directories(silver-native-test PRIVATE include)
target_link_libraries(silver-native-test PRIVATE silver_combat_search_bridge)
target_link_options(silver-native-test PRIVATE -Wl,--gc-sections)

add_executable(silver-prior-native-parity apps/silver_prior_native_parity.cpp)
set_target_properties(silver-prior-native-parity PROPERTIES OUTPUT_NAME silver_prior_native_parity)
target_include_directories(silver-prior-native-parity PRIVATE include json/include)
target_link_libraries(silver-prior-native-parity PRIVATE silver_prior_runtime silver_combat_search_bridge)
target_link_options(silver-prior-native-parity PRIVATE -Wl,--gc-sections)

add_executable(silver-terminal-value-test apps/silver_terminal_value_test.cpp)
set_target_properties(silver-terminal-value-test PROPERTIES
    OUTPUT_NAME silver_terminal_value_test
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON)
target_include_directories(silver-terminal-value-test PRIVATE third_party/silver_lightspeed/include include)
target_compile_definitions(silver-terminal-value-test PRIVATE
    sts=sts_silver
    java=sts_silver_java
    fixed_list=silver_fixed_list
    rollWeightedIdx=silver_rollWeightedIdx
    simulationIdx=silver_simulationIdx
    initMaps=silver_initMaps
    agentMtRunner=silver_agentMtRunner)
target_link_libraries(silver-terminal-value-test PRIVATE silver_combat_model)
target_link_options(silver-terminal-value-test PRIVATE -Wl,--gc-sections)

add_executable(silver-leaf-relabel apps/silver_leaf_relabel.cpp)
set_target_properties(silver-leaf-relabel PROPERTIES OUTPUT_NAME silver_leaf_relabel)
target_include_directories(silver-leaf-relabel PRIVATE include json/include)
target_link_libraries(silver-leaf-relabel PRIVATE silver_combat_search_bridge)
target_link_options(silver-leaf-relabel PRIVATE -Wl,--gc-sections)

add_executable(silver-rollout-variance-diagnostic apps/silver_rollout_variance_diagnostic.cpp)
set_target_properties(silver-rollout-variance-diagnostic PROPERTIES
    OUTPUT_NAME silver_rollout_variance_diagnostic)
target_include_directories(silver-rollout-variance-diagnostic PRIVATE include json/include)
target_link_libraries(silver-rollout-variance-diagnostic PRIVATE silver_combat_search_bridge)
target_link_options(silver-rollout-variance-diagnostic PRIVATE -Wl,--gc-sections)

add_executable(silver-first-action-selector apps/silver_first_action_selector.cpp)
set_target_properties(silver-first-action-selector PROPERTIES
    OUTPUT_NAME silver_first_action_selector)
target_include_directories(silver-first-action-selector PRIVATE include json/include)
target_link_libraries(silver-first-action-selector PRIVATE silver_combat_search_bridge)
target_link_options(silver-first-action-selector PRIVATE -Wl,--gc-sections)

add_executable(silver-tactical-prefix-oracle apps/silver_tactical_prefix_oracle.cpp)
set_target_properties(silver-tactical-prefix-oracle PROPERTIES
    OUTPUT_NAME silver_tactical_prefix_oracle)
target_include_directories(silver-tactical-prefix-oracle PRIVATE include json/include)
target_link_libraries(silver-tactical-prefix-oracle PRIVATE silver_combat_search_bridge)
target_link_options(silver-tactical-prefix-oracle PRIVATE -Wl,--gc-sections)

add_executable(silver-root-mechanism apps/silver_root_mechanism.cpp)
set_target_properties(silver-root-mechanism PROPERTIES OUTPUT_NAME silver_root_mechanism)
target_include_directories(silver-root-mechanism PRIVATE include json/include)
target_link_libraries(silver-root-mechanism PRIVATE silver_combat_search_bridge)
target_link_options(silver-root-mechanism PRIVATE -Wl,--gc-sections)

add_executable(silver-prior-root-replay apps/silver_prior_root_replay.cpp)
set_target_properties(silver-prior-root-replay PROPERTIES OUTPUT_NAME silver_prior_root_replay)
target_include_directories(silver-prior-root-replay PRIVATE include json/include)
target_link_libraries(silver-prior-root-replay PRIVATE silver_combat_search_bridge)
target_link_options(silver-prior-root-replay PRIVATE -Wl,--gc-sections)

add_executable(silver-forced-action-audit apps/silver_forced_action_audit.cpp)
set_target_properties(silver-forced-action-audit PROPERTIES
    OUTPUT_NAME silver_forced_action_audit)
target_include_directories(silver-forced-action-audit PRIVATE include json/include)
target_link_libraries(silver-forced-action-audit PRIVATE silver_combat_search_bridge)
target_link_options(silver-forced-action-audit PRIVATE -Wl,--gc-sections)

execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE STS_PRIOR_BUILD_SHA OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
add_executable(silver-prior-label apps/silver_prior_label.cpp)
set_target_properties(silver-prior-label PROPERTIES OUTPUT_NAME silver_prior_label)
target_include_directories(silver-prior-label PRIVATE include json/include)
target_compile_definitions(silver-prior-label PRIVATE STS_PRIOR_BUILD_SHA="${STS_PRIOR_BUILD_SHA}")
target_link_libraries(silver-prior-label PRIVATE silver_combat_search_bridge)
target_link_options(silver-prior-label PRIVATE -Wl,--gc-sections)

add_executable(silver-hard-combat-fixture apps/silver_hard_combat_fixture.cpp)
set_target_properties(silver-hard-combat-fixture PROPERTIES OUTPUT_NAME silver_hard_combat_fixture)
target_include_directories(silver-hard-combat-fixture PRIVATE include json/include)
target_link_libraries(silver-hard-combat-fixture PRIVATE silver_combat_search_bridge)
target_link_options(silver-hard-combat-fixture PRIVATE -Wl,--gc-sections)

add_executable(silver-hard-combat-replay apps/silver_hard_combat_replay.cpp)
set_target_properties(silver-hard-combat-replay PROPERTIES OUTPUT_NAME silver_hard_combat_replay)
target_include_directories(silver-hard-combat-replay PRIVATE include json/include)
target_link_libraries(silver-hard-combat-replay PRIVATE silver_combat_search_bridge)
target_link_options(silver-hard-combat-replay PRIVATE -Wl,--gc-sections)

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

add_executable(silver-policy-value-phase-a apps/silver_policy_value_phase_a.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-policy-value-phase-a PROPERTIES
    OUTPUT_NAME silver_policy_value_phase_a)
target_include_directories(silver-policy-value-phase-a PRIVATE include json/include)
target_link_libraries(silver-policy-value-phase-a PRIVATE silver_live_backend)
target_link_options(silver-policy-value-phase-a PRIVATE -Wl,--gc-sections)

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
    apps/one_combat/ooc_checkpoint_policy.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat PUBLIC include)
target_include_directories(one_combat PUBLIC json/include)
target_link_libraries(one_combat PRIVATE silver_live_backend OpenSSL::Crypto)
# The isolated model objects contain upstream full-game methods adjacent to
# the combat methods used by Silver rollout. Their sections are compiled with
# -ffunction-sections; discard the unreachable OOC closure instead of vendoring
# it into the integration executable.
target_link_options(one_combat PRIVATE -Wl,--gc-sections)

# Read-only newline-delimited JSON endpoint for the private live-model
# inspector.  Keep it separate from the simulator driver until a proven
# Java-game importer can construct the native observation contracts.
add_executable(one_combat_advisor
    apps/one_combat/advisor_stdio.cpp
    apps/one_combat/advisor_protocol.cpp
    apps/one_combat/live_silver_importer.cpp
    apps/one_combat/live_silver_mapping.cpp)
target_include_directories(one_combat_advisor PUBLIC json/include)
target_sources(one_combat_advisor PRIVATE
    apps/one_combat/live_ooc_state.cpp
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
target_link_libraries(one_combat_advisor PRIVATE sts_core_objects silver_live_backend OpenSSL::Crypto)
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
target_link_libraries(test_live_ooc_policy PRIVATE OpenSSL::Crypto)
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
target_link_libraries(live_ooc_parity_test PRIVATE OpenSSL::Crypto)
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
set_tests_properties(live_game_driver PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")

add_executable(live_ctm_importer_test apps/live_ctm_importer_test.cpp
    apps/one_combat/live_ooc_importer.cpp
    apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(live_ctm_importer_test PRIVATE include json/include)
target_link_libraries(live_ctm_importer_test PRIVATE OpenSSL::Crypto)
add_test(NAME live_ctm_importer
    COMMAND $<TARGET_FILE:live_ctm_importer_test>
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_near_full_except_smoke_v2.native)
set_tests_properties(live_ctm_importer PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")

add_executable(live_silver_importer_test apps/live_silver_importer_test.cpp
    apps/one_combat/live_silver_importer.cpp apps/one_combat/live_silver_mapping.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(live_silver_importer_test PRIVATE include json/include apps)
target_link_libraries(live_silver_importer_test PRIVATE silver_live_backend)
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
target_link_libraries(unit-test PRIVATE silver_combat_bridge)
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
add_test(NAME paired_analysis_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/paired_analysis.py --self-test)
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
add_test(NAME simulator_correctness_pr9_19 COMMAND $<TARGET_FILE:unit-test> simulator_correctness_pr9_19)
set_tests_properties(simulator_correctness_pr9_19 PROPERTIES LABELS "core")
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
add_test(NAME ooc_policy_parity
    COMMAND $<TARGET_FILE:one_combat> oocpolicyparity 4000598 100 0)
set_tests_properties(ooc_policy_parity PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME teacher_schema_cap_override COMMAND ${CMAKE_COMMAND} -E env
    STS_SILVER_REUSE_CAP=131072 $<TARGET_FILE:one_combat> teacher_schema_compat)
set_tests_properties(teacher_schema_cap_override PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME teacher_schema_compat COMMAND $<TARGET_FILE:one_combat> teacher_schema_compat)
set_tests_properties(teacher_schema_compat PROPERTIES
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
add_test(NAME silver_random_bridge COMMAND $<TARGET_FILE:unit-test> silver_random_bridge)
add_test(NAME silver_semantic_action COMMAND $<TARGET_FILE:unit-test> silver_semantic_action)
add_test(NAME silver_searcher_link_closure COMMAND $<TARGET_FILE:silver-native-test>)
add_test(NAME silver_terminal_value COMMAND $<TARGET_FILE:silver-terminal-value-test>)
add_test(NAME silver_player_status COMMAND $<TARGET_FILE:silver-player-status-test>)
add_test(NAME silver_search_optimization COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:silver-search-optimization-test>)
set_tests_properties(silver_search_optimization PROPERTIES LABELS "integration")
add_test(NAME silver_repeated_reroot_canary COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:silver-search-optimization-test> --repeated-reroot-canary)
set_tests_properties(silver_repeated_reroot_canary PROPERTIES LABELS "integration")
add_test(NAME silver_experimental_cap_integration COMMAND ${CMAKE_COMMAND} -E env
    STS_SILVER_REUSE_CAP=131072 bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:silver-integration-test>)
set_tests_properties(silver_experimental_cap_integration PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME silver_integration_default COMMAND ${CMAKE_COMMAND} -E env
    --unset=STS_SILVER_ADAPTIVE --unset=STS_SILVER_ADAPTIVE_RETAINED_ONLY
    --unset=STS_SILVER_ADAPTIVE_TOP_GAP --unset=STS_SILVER_EXACT_VISIT_LOCK
    --unset=STS_SILVER_RHO_RACING $<TARGET_FILE:silver-integration-test>)
set_tests_properties(silver_integration_default PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")
add_test(NAME silver_integration_adaptive_optout COMMAND ${CMAKE_COMMAND} -E env
    STS_SILVER_ADAPTIVE=0 --unset=STS_SILVER_ADAPTIVE_RETAINED_ONLY
    $<TARGET_FILE:silver-integration-test>)
set_tests_properties(silver_integration_adaptive_optout PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")
add_test(NAME silver_integration_adaptive_override COMMAND ${CMAKE_COMMAND} -E env
    STS_SILVER_ADAPTIVE=1 STS_SILVER_ADAPTIVE_RETAINED_ONLY=1
    STS_SILVER_ADAPTIVE_TOP_GAP=0.2932885906040268
    $<TARGET_FILE:silver-integration-test>)
set_tests_properties(silver_integration_adaptive_override PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")
add_test(NAME silver_bridge_boundary COMMAND $<TARGET_FILE:silver-bridge-test>)
add_test(NAME silver_root_mechanism_fixture COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/silver_root_mechanism_fixture.py
    $<TARGET_FILE:silver-bridge-test> $<TARGET_FILE:silver-leaf-relabel>
    $<TARGET_FILE:silver-root-mechanism>)
set_tests_properties(silver_root_mechanism_fixture PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME silver_forced_action_fixture COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/silver_forced_action_fixture.py
    $<TARGET_FILE:silver-bridge-test> $<TARGET_FILE:silver-forced-action-audit>
    ${CMAKE_SOURCE_DIR}/tools/analyze_silver_forced_action_audit.py)
add_test(NAME silver_prior_dataset_fixture COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/silver_prior_dataset_fixture.py
    $<TARGET_FILE:silver-bridge-test> $<TARGET_FILE:silver-prior-label>)
set_tests_properties(silver_prior_dataset_fixture PROPERTIES TIMEOUT 180 LABELS "integration;smoke")
add_test(NAME silver_prior_resume COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/silver_prior_resume_test.py)
set_tests_properties(silver_prior_resume PROPERTIES LABELS "tooling;smoke")
add_test(NAME silver_prior_training COMMAND python3 -m unittest
    tests.test_train_silver_prior -v)
set_tests_properties(silver_prior_training PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
add_test(NAME silver_prior_native_export COMMAND python3 -m unittest
    tests.test_export_silver_prior_native -v)
set_tests_properties(silver_prior_native_export PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
add_test(NAME silver_prior_online_screen_parser COMMAND python3 -m unittest
    tests.test_silver_prior_online_screen -v)
set_tests_properties(silver_prior_online_screen_parser PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
add_test(NAME silver_prior_root_screen COMMAND python3 -m unittest
    tests.test_silver_prior_root_screen -v)
set_tests_properties(silver_prior_root_screen PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
add_test(NAME silver_prior_locked_evaluator COMMAND python3 -m unittest
    tests.test_evaluate_silver_prior_locked -v)
set_tests_properties(silver_prior_locked_evaluator PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
set_tests_properties(silver_forced_action_fixture PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;research-repro" TIMEOUT 180)
add_test(NAME silver_hard_combat_fixture COMMAND $<TARGET_FILE:silver-hard-combat-fixture>)
set_tests_properties(silver_hard_combat_fixture PROPERTIES LABELS "integration")
# tests/agent is owned by the separate pre-build unittest discovery step in CI.
# Do not register its modules or separate compile-only checks here as well:
# importing those tools during unittest discovery already parses them.
add_test(NAME runic_dome_lifecycle COMMAND $<TARGET_FILE:runic-dome-lifecycle-test>)
add_test(NAME analyze_silver_reuse_scaling_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_reuse_scaling.py --self-test)
add_test(NAME analyze_silver_vnet_leaf_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_vnet_leaf.py --self-test)
add_test(NAME check_benchmark_canary_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/agent/check_benchmark_canary.py --self-test)
add_test(NAME analyze_silver_sticky_quality_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_sticky_quality.py --self-test)
add_test(NAME analyze_silver_root_diagnostic_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_root_diagnostic.py --self-test)
add_test(NAME analyze_combat_budget_diag_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_combat_budget_diag.py --self-test)
add_test(NAME analyze_combat_sequential_diag_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_combat_sequential_diag.py --self-test)
add_test(NAME analyze_silver_staged_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_staged.py --self-test)
add_test(NAME analyze_silver_adaptive_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_silver_adaptive.py --self-test)
add_test(NAME analyze_silver_tactical_prefix_oracle
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_silver_tactical_prefix_oracle.py -q)
add_test(NAME analyze_silver_bounded_variable_prefix
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_silver_bounded_variable_prefix.py -q)
add_test(NAME analyze_silver_learned_prefix_scorer
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_silver_learned_prefix_scorer.py -q)
add_test(NAME analyze_silver_prefix_learning_curve
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_silver_prefix_learning_curve.py -q)
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
add_test(NAME combat_transition_oracle COMMAND $<TARGET_FILE:unit-test> combat_transition_oracle)
add_test(NAME combat_predictor_input COMMAND $<TARGET_FILE:combat-predictor-input-test>)
add_test(NAME combat_predictor_input_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_predictor_input_contract.py -q)
add_test(NAME combat_transition_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_contract.py)
add_test(NAME combat_transition_model_experiment_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_combat_transition_model_experiment.py)
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
add_test(NAME combat_transition_fixture_contract
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/combat_transition_contract.py
        ${CMAKE_CURRENT_BINARY_DIR}/combat_transition_fixture.manifest.json)
set_tests_properties(combat_transition_native_fixture
    PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(combat_transition_fixture_contract
    PROPERTIES DEPENDS combat_transition_native_fixture)
set_tests_properties(paired_analysis_selftest py_compile_parity_test py_compile_analyze_ooc_factor check_replay_selftest silver_prior_root_screen vnettest_selftest winnettest_selftest battlecontext_roundtrip designer_in_spire cardqueue_overflow keys_collect issue_fixes thorns_retaliation awakened_one_stage2 darkling_victory poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality simhealth_selection_failure training_integrity e2c_observer_scope analyze_silver_root_diagnostic_selftest analyze_postcombat_raw_terminal_selftest export_win_model_selftest runwin_e2c_native_parity
    runwin_e2c_production_native_parity e2c_runwin_projection_parity PROPERTIES ENVIRONMENT "PYTHONPYCACHEPREFIX=${CMAKE_BINARY_DIR}/pycache")

# Labels provide fast, intention-revealing local tiers while the unfiltered
# linux-gcc-test preset remains the authoritative full CTest suite.
set_tests_properties(battlecontext_roundtrip designer_in_spire cardqueue_overflow keys_collect
    issue_fixes relic_reward_sapphire thorns_retaliation awakened_one_stage2 darkling_victory
    poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality
    simhealth_selection_failure
    training_integrity PROPERTIES LABELS "core")
set_tests_properties(vnettest_selftest winnettest_selftest
    e2c_observer_scope combat_knowledge silver_random_bridge silver_semantic_action
    silver_searcher_link_closure silver_bridge_boundary runic_dome_lifecycle
    runwin_e2c_native_parity runwin_e2c_production_native_parity
    e2c_runwin_projection_parity PROPERTIES LABELS "integration")
set_tests_properties(py_compile_parity_test py_compile_analyze_ooc_factor
    check_replay_selftest check_benchmark_canary_selftest export_win_model_selftest
    PROPERTIES LABELS "tooling")
set_tests_properties(analyze_silver_reuse_scaling_selftest analyze_silver_vnet_leaf_selftest
    analyze_silver_sticky_quality_selftest analyze_silver_root_diagnostic_selftest
    analyze_silver_adaptive_selftest analyze_silver_staged_selftest analyze_postcombat_raw_terminal_selftest
    PROPERTIES LABELS "research-repro")
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
target_link_libraries(combat_transition_runtime_probe PRIVATE OpenSSL::Crypto)
add_test(NAME combat_transition_native_contract COMMAND python3 -m unittest
    tests.test_combat_transition_native_contract -v)
set_tests_properties(combat_transition_native_contract PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME combat_transition_runtime_loader COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_combat_transition_runtime_loader.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(combat_transition_runtime_loader PROPERTIES
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
