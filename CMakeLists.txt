cmake_minimum_required(VERSION 3.19)
project(
        sts_lightspeed
        VERSION 0.1
        DESCRIPTION "High Performance, rng accurate implementation of Slay the Spire with tools for tree search and ml."
        LANGUAGES CXX)

enable_testing()

file (GLOB_RECURSE sts_lightspeed_SOURCES CONFIGURE_DEPENDS "src/*.cpp")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS  "-Wno-shift-count-overflow -O3 -fopenmp")

add_subdirectory(json)

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


add_executable(main apps/main.cpp ${sts_lightspeed_SOURCES})
target_link_directories(main PRIVATE json::nlohmann_json)
target_include_directories(main PUBLIC include)
target_include_directories(main PUBLIC json/include)

add_executable(one_combat apps/one_combat.cpp ${sts_lightspeed_SOURCES})
target_include_directories(one_combat PUBLIC include)
target_include_directories(one_combat PUBLIC json/include)

add_executable(parity_test apps/parity_test.cpp ${sts_lightspeed_SOURCES})
target_include_directories(parity_test PUBLIC include)
target_include_directories(parity_test PUBLIC json/include)

# "test" is reserved by CTest, so the manual dispatcher target is unit-test
# with OUTPUT_NAME "test" to keep the build/test binary path stable.
add_executable(unit-test apps/test.cpp ${sts_lightspeed_SOURCES})
set_target_properties(unit-test PROPERTIES OUTPUT_NAME test)
target_include_directories(unit-test PUBLIC include)
target_link_directories(unit-test PUBLIC json::nlohmann_json)
target_include_directories(unit-test PUBLIC json/include)

add_executable(small-test apps/small-test.cpp bindings/bindings-util.cpp ${sts_lightspeed_SOURCES})
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
add_test(NAME py_compile_check_replay COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/check_replay.py)
add_test(NAME py_compile_vnettest_selftest COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/vnettest_selftest.py)
add_test(NAME check_replay_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/check_replay.py --self-test)
add_test(NAME vnettest_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/vnettest_selftest.py --self-test $<TARGET_FILE:one_combat>)
add_test(NAME battlecontext_roundtrip COMMAND $<TARGET_FILE:unit-test> battlecontext_roundtrip)
set_tests_properties(py_compile_paired_analysis paired_analysis_selftest py_compile_parity_test py_compile_check_replay py_compile_vnettest_selftest check_replay_selftest vnettest_selftest battlecontext_roundtrip
    PROPERTIES ENVIRONMENT "PYTHONPYCACHEPREFIX=${CMAKE_BINARY_DIR}/pycache")
