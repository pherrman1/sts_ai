cmake_minimum_required(VERSION 3.19)
project(
        sts_lightspeed
        VERSION 0.1
        DESCRIPTION "High Performance, rng accurate implementation of Slay the Spire with tools for tree search and ml."
        LANGUAGES CXX)

enable_testing()

file (GLOB_RECURSE sts_lightspeed_SOURCES CONFIGURE_DEPENDS "src/*.cpp")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS  "-Wno-shift-count-overflow -O3 -fopenmp -flto")

add_subdirectory(json)

add_library(sts_core_objects OBJECT ${sts_lightspeed_SOURCES})
target_include_directories(sts_core_objects PUBLIC include)
target_include_directories(sts_core_objects PUBLIC json/include)

# The pybind11 module needs CPython development headers (python3-dev). Core
# targets (main, one_combat, test, small-test) must not depend on them, so the
# module is skipped with a warning when headers are absent.
find_package(Python COMPONENTS Interpreter Development.Module QUIET)
if(Python_Development.Module_FOUND)
    add_subdirectory(pybind11)
    pybind11_add_module(slaythespire bindings/slaythespire.cpp bindings/bindings-util.cpp ${sts_lightspeed_SOURCES})
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

add_executable(one_combat apps/one_combat.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat PUBLIC include)
target_include_directories(one_combat PUBLIC json/include)

add_executable(parity_test apps/parity_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(parity_test PUBLIC include)
target_include_directories(parity_test PUBLIC json/include)

# "test" is reserved by CTest, so the manual dispatcher target is unit-test
# with OUTPUT_NAME "test" to keep the build/test binary path stable.
add_executable(unit-test apps/test.cpp apps/test_belief.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(unit-test PROPERTIES OUTPUT_NAME test)
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
add_test(NAME py_compile_paired_analysis COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/paired_analysis.py)
add_test(NAME paired_analysis_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/paired_analysis.py --self-test)
add_test(NAME py_compile_parity_test COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/parity_test.py)
add_test(NAME py_compile_check_replay COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/verify/check_replay.py)
add_test(NAME py_compile_vnettest_selftest COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/verify/vnettest_selftest.py)
add_test(NAME py_compile_winnettest_selftest COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/verify/winnettest_selftest.py)
add_test(NAME check_replay_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/check_replay.py --self-test)
add_test(NAME vnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/vnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME winnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/winnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME battlecontext_roundtrip COMMAND $<TARGET_FILE:unit-test> battlecontext_roundtrip)
add_test(NAME designer_in_spire COMMAND $<TARGET_FILE:unit-test> designer_in_spire)
add_test(NAME scum_nonfair_empty_edges COMMAND $<TARGET_FILE:unit-test> scum_nonfair_empty_edges)
add_test(NAME scum_convroot_stale_outcome COMMAND $<TARGET_FILE:unit-test> scum_convroot_stale_outcome)
add_test(NAME cardqueue_overflow COMMAND $<TARGET_FILE:unit-test> cardqueue_overflow)
add_test(NAME keys_collect COMMAND $<TARGET_FILE:unit-test> keys_collect)
add_test(NAME issue_fixes COMMAND $<TARGET_FILE:unit-test> issue_fixes)
add_test(NAME semantic_card_edges COMMAND $<TARGET_FILE:unit-test> semantic_card_edges)
add_test(NAME s3_drawpile_reuse_boundary COMMAND $<TARGET_FILE:unit-test> s3_drawpile_reuse_boundary)
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
set_tests_properties(py_compile_paired_analysis paired_analysis_selftest py_compile_parity_test py_compile_check_replay py_compile_vnettest_selftest py_compile_winnettest_selftest check_replay_selftest vnettest_selftest winnettest_selftest battlecontext_roundtrip designer_in_spire scum_nonfair_empty_edges scum_convroot_stale_outcome cardqueue_overflow keys_collect issue_fixes semantic_card_edges thorns_retaliation awakened_one_stage2 darkling_victory poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality simhealth_nonfair_s2_empty simhealth_selection_failure simhealth_nonfair_s2_selection_failed training_integrity
    PROPERTIES ENVIRONMENT "PYTHONPYCACHEPREFIX=${CMAKE_BINARY_DIR}/pycache")
