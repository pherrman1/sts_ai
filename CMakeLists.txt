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

# The policy MLP (Silver prior playouts take its argmax) and its exactness test
# must not fuse a*b+c into an FMA, or play changes on a build with FMA enabled
# (e.g. -march=native); the presets already pass -mno-fma or have no FMA.
set_source_files_properties(src/sim/search/CombatValueNet.cpp tests/policy_mlp_exact_test.cpp
    PROPERTIES COMPILE_OPTIONS -ffp-contract=off)

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

# Bounded public-state research probe; never linked into the gameplay executables.
add_executable(silver-public-pair-probe apps/silver_public_pair_probe.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(silver-public-pair-probe PROPERTIES OUTPUT_NAME silver_public_pair_probe)
target_include_directories(silver-public-pair-probe PRIVATE include json/include)
link_ctm_crypto(silver-public-pair-probe)

# Same-turn infinity oracle: research executable, no production linkage.
add_executable(combat-infinity-oracle apps/combat_infinity_oracle.cpp $<TARGET_OBJECTS:sts_core_objects>)
set_target_properties(combat-infinity-oracle PROPERTIES OUTPUT_NAME combat_infinity_oracle)
target_include_directories(combat-infinity-oracle PRIVATE include json/include)
add_test(NAME combat_infinity_oracle COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:combat-infinity-oracle> --fixtures)
set_tests_properties(combat_infinity_oracle PROPERTIES LABELS "core;research-repro")

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
    # Stage 0 bench, part 3: the end-to-end producer for a Python / GPU net (tools/az_bench/e2e_bench.py).
    pybind11_add_module(az_bench_native
        apps/az_bench/az_bench_module.cpp
        apps/az_bench/az_driver.cpp
        apps/az_bench/az_run_driver.cpp
        $<TARGET_OBJECTS:sts_core_pic_objects>)
    target_include_directories(az_bench_native PRIVATE include json/include apps/az_bench)
else()
    message(WARNING "Python development headers not found; skipping the slaythespire pybind11 module")
endif()


add_executable(expert-seed-probe apps/expert_seed_probe.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(expert-seed-probe PUBLIC include)
target_include_directories(expert-seed-probe PUBLIC json/include)

add_executable(expert-replay-probe apps/expert_replay_probe.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(expert-replay-probe PUBLIC include)
target_include_directories(expert-replay-probe PUBLIC json/include)

add_executable(main apps/main.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_link_directories(main PRIVATE json::nlohmann_json)
target_include_directories(main PUBLIC include)
target_include_directories(main PUBLIC json/include)

add_executable(run_goal_test tests/run_goal_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(run_goal_test PRIVATE include json/include)
add_test(NAME run_goal COMMAND $<TARGET_FILE:run_goal_test>)
set_tests_properties(run_goal PROPERTIES LABELS "core;smoke")

# predictPolicyMlp stays bit-identical to the plain reference loops (Silver
# prior playouts take its argmax).
add_executable(policy_mlp_exact_test tests/policy_mlp_exact_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(policy_mlp_exact_test PRIVATE include json/include)
add_test(NAME policy_mlp_exact COMMAND $<TARGET_FILE:policy_mlp_exact_test>
         ${CMAKE_SOURCE_DIR}/models/combat_policy_mlp_g7f_E.txt)
set_tests_properties(policy_mlp_exact PROPERTIES LABELS "core;smoke")

# The exact prior-playout pick cache (#1051) returns the uncached prior's argmax on real playout states.
add_executable(prior_pick_cache_test tests/prior_pick_cache_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(prior_pick_cache_test PRIVATE include json/include)
add_test(NAME prior_pick_cache COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:prior_pick_cache_test> ${CMAKE_SOURCE_DIR}/models/combat_policy_mlp_g7f_E.txt)
set_tests_properties(prior_pick_cache PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

# Native combat net (combat plan stage 3): the encoder matches tools/combat_net's Python encoder and the forward pass
# matches PyTorch on a fixture (tools/combat_net/make_native_fixture.py).
add_executable(combat-tok-net-tool apps/combat_tok_net_tool.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat-tok-net-tool PRIVATE include json/include)
add_test(NAME combat_tok_net_parity COMMAND $<TARGET_FILE:combat-tok-net-tool> check
         ${CMAKE_SOURCE_DIR}/tests/data/combat_tok_net_tiny.ctn ${CMAKE_SOURCE_DIR}/tests/data/combat_tok_net_fixture.json)
set_tests_properties(combat_tok_net_parity PROPERTIES LABELS "core;smoke")
# The same with the per-edge Q head (value-net-as-leaf V1; make_native_fixture.py --q-head).
add_test(NAME combat_tok_net_q_parity COMMAND $<TARGET_FILE:combat-tok-net-tool> check
         ${CMAKE_SOURCE_DIR}/tests/data/combat_tok_net_tiny_q.ctn ${CMAKE_SOURCE_DIR}/tests/data/combat_tok_net_q_fixture.json)
set_tests_properties(combat_tok_net_q_parity PROPERTIES LABELS "core;smoke")

# Stage 0 throughput bench, part 2 (tools/az_bench/README.md): CPU positions per second of copy + step + enumerate +
# encode over threads. Smoke: one short run on the wire sample.
add_executable(az-bench-producer apps/az_bench_producer.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(az-bench-producer PRIVATE include json/include)
find_package(Threads REQUIRED)
target_link_libraries(az-bench-producer PRIVATE Threads::Threads)
add_test(NAME az_bench_producer_smoke COMMAND $<TARGET_FILE:az-bench-producer>
         ${CMAKE_SOURCE_DIR}/tests/data/combat_net_wire_sample.jsonl --threads 2 --seconds 0.3 --games 4)
set_tests_properties(az_bench_producer_smoke PROPERTIES LABELS "core;smoke")

# Stage 0 bench, part 3: end-to-end producer (worker threads, request queue, batching) with a fake net (C++ only).
add_executable(az-bench-driver apps/az_bench/az_bench_driver.cpp apps/az_bench/az_driver.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(az-bench-driver PRIVATE include json/include apps/az_bench)
target_link_libraries(az-bench-driver PRIVATE Threads::Threads)
add_test(NAME az_bench_driver_smoke COMMAND $<TARGET_FILE:az-bench-driver>
         ${CMAKE_SOURCE_DIR}/tests/data/combat_net_wire_sample.jsonl --workers 2 --games 8 --batch 16 --seconds 0.5)
set_tests_properties(az_bench_driver_smoke PROPERTIES LABELS "core;smoke")

# Stage 1 self-play: whole-run driver (combat + out-of-combat Gumbel search, training samples) with a fake net.
add_executable(az-run-driver apps/az_bench/az_run_driver_main.cpp apps/az_bench/az_run_driver.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(az-run-driver PRIVATE include json/include apps/az_bench)
target_link_libraries(az-run-driver PRIVATE Threads::Threads)
add_test(NAME az_run_driver_smoke COMMAND $<TARGET_FILE:az-run-driver> --workers 2 --games 3 --runs 6 --fast
         --seed-base 1 --seconds 300)
set_tests_properties(az_run_driver_smoke PROPERTIES LABELS "core;smoke")
add_test(NAME az_run_driver_explore COMMAND $<TARGET_FILE:az-run-driver> --workers 2 --games 3 --runs 24 --fast
         --seed-base 1 --seconds 300 --explore-c 0.5 --pick-target 0.2 --test-hp 300)
set_tests_properties(az_run_driver_explore PROPERTIES LABELS "core;smoke")
# Evaluation cache of the stage 1 driver is exact: same moves and samples with and without it (hash fake net).
add_executable(az-eval-cache-test apps/az_bench/az_eval_cache_test.cpp apps/az_bench/az_run_driver.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(az-eval-cache-test PRIVATE include json/include apps/az_bench)
target_link_libraries(az-eval-cache-test PRIVATE Threads::Threads)
add_test(NAME az_eval_cache COMMAND $<TARGET_FILE:az-eval-cache-test> --runs 3 --seed-base 1 --fast)
set_tests_properties(az_eval_cache PROPERTIES LABELS "core;smoke")
# Packed tokens (only live tokens to the GPU) carry the same rows as the [R][T] layout.
add_executable(az-pack-test apps/az_bench/az_pack_test.cpp)
target_include_directories(az-pack-test PRIVATE include apps/az_bench)
target_link_libraries(az-pack-test PRIVATE Threads::Threads)
add_test(NAME az_pack_packed_tokens COMMAND $<TARGET_FILE:az-pack-test>)
set_tests_properties(az_pack_packed_tokens PROPERTIES LABELS "core;smoke")
# Search flags (no Gumbel noise on fast moves, Gumbel MuZero completed-Q rescale): the transform's arithmetic, and
# full runs with both flags on give valid samples.
add_test(NAME az_run_driver_qtransform COMMAND $<TARGET_FILE:az-run-driver> --self-test-q)
set_tests_properties(az_run_driver_qtransform PROPERTIES LABELS "core;smoke")
add_test(NAME az_run_driver_search_flags COMMAND $<TARGET_FILE:az-run-driver> --workers 2 --games 3 --runs 6 --fast
         --seed-base 1 --seconds 300 --no-fast-noise --q-rescale --c-scale 0.1)
set_tests_properties(az_run_driver_search_flags PROPERTIES LABELS "core;smoke")
# Fair play of the stage 1 driver's combat view (ADR-0002): fights differing only in hidden draw order (and, under
# Runic Dome, rolled intents) give identical net inputs and identical search paths.
add_executable(az-fair-view-test apps/az_bench/az_fair_view_test.cpp apps/az_bench/az_run_driver.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(az-fair-view-test PRIVATE include json/include apps/az_bench)
target_link_libraries(az-fair-view-test PRIVATE Threads::Threads)
add_test(NAME az_fair_view COMMAND $<TARGET_FILE:az-fair-view-test> --fights 40)
set_tests_properties(az_fair_view PROPERTIES LABELS "core;smoke")

# Native Amber-token combat encoder (stage 0 of the self-play loop assessment): every wire-encoded field reaches the
# tokens, determinism, capacity cut counting and live action src / tgt, on the wire sample.
add_executable(amber_encoder_test tests/amber_encoder_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(amber_encoder_test PRIVATE include json/include)
add_test(NAME amber_encoder COMMAND $<TARGET_FILE:amber_encoder_test>
         ${CMAKE_SOURCE_DIR}/tests/data/combat_net_wire_sample.jsonl)
set_tests_properties(amber_encoder PROPERTIES LABELS "core;smoke")

# Out-of-combat Amber encoder (stage 1 self-play loop): random-legal whole A20 runs with battles skipped (fixed test
# seeds 1..200, no evaluation), every screen and action type, live src / tgt, distinct tuples, determinism, and
# byte-identical tokens after scrambling private state.
add_executable(amber_game_encoder_test tests/amber_game_encoder_test.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(amber_game_encoder_test PRIVATE include json/include)
add_test(NAME amber_game_encoder COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:amber_game_encoder_test> 200)
set_tests_properties(amber_game_encoder PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(rest_recall_filter_test tests/rest_recall_filter_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(rest_recall_filter_test PRIVATE include json/include)
add_test(NAME rest_recall_filter COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:rest_recall_filter_test>)
set_tests_properties(rest_recall_filter PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(neow_transform_curse_test tests/neow_transform_curse_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(neow_transform_curse_test PRIVATE include json/include)
add_test(NAME neow_transform_curse COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:neow_transform_curse_test>)
set_tests_properties(neow_transform_curse PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(engine_fidelity_fix_test tests/engine_fidelity_fix_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(engine_fidelity_fix_test PRIVATE include json/include)
add_test(NAME engine_fidelity_fix COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:engine_fidelity_fix_test>)
set_tests_properties(engine_fidelity_fix PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(dead_target_debuff_fix_test tests/dead_target_debuff_fix_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(dead_target_debuff_fix_test PRIVATE include json/include)
add_test(NAME dead_target_debuff_fix COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:dead_target_debuff_fix_test>)
set_tests_properties(dead_target_debuff_fix PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(curl_up_lethal_test tests/curl_up_lethal_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(curl_up_lethal_test PRIVATE include json/include)
add_test(NAME curl_up_lethal COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:curl_up_lethal_test>)
set_tests_properties(curl_up_lethal PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(combat_turn_cap_test tests/combat_turn_cap_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat_turn_cap_test PRIVATE include json/include)
add_test(NAME combat_turn_cap COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:combat_turn_cap_test>)
set_tests_properties(combat_turn_cap PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(exhaust_empty_hand_test tests/exhaust_empty_hand_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(exhaust_empty_hand_test PRIVATE include json/include)
add_test(NAME exhaust_empty_hand COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:exhaust_empty_hand_test>)
set_tests_properties(exhaust_empty_hand PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(blood_for_blood_copy_cost_test tests/blood_for_blood_copy_cost_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(blood_for_blood_copy_cost_test PRIVATE include json/include)
add_test(NAME blood_for_blood_copy_cost COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:blood_for_blood_copy_cost_test>)
set_tests_properties(blood_for_blood_copy_cost PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(true_grit_single_card_rng_test tests/true_grit_single_card_rng_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(true_grit_single_card_rng_test PRIVATE include json/include)
add_test(NAME true_grit_single_card_rng COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:true_grit_single_card_rng_test>)
set_tests_properties(true_grit_single_card_rng PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(anger_copy_cost_test tests/anger_copy_cost_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(anger_copy_cost_test PRIVATE include json/include)
add_test(NAME anger_copy_cost COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:anger_copy_cost_test>)
set_tests_properties(anger_copy_cost PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(corruption_hand_cost_test tests/corruption_hand_cost_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(corruption_hand_cost_test PRIVATE include json/include)
add_test(NAME corruption_hand_cost COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:corruption_hand_cost_test>)
set_tests_properties(corruption_hand_cost PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(upgrade_cost_delta_test tests/upgrade_cost_delta_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(upgrade_cost_delta_test PRIVATE include json/include)
add_test(NAME upgrade_cost_delta COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:upgrade_cost_delta_test>)
set_tests_properties(upgrade_cost_delta PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(byrd_grounded_flight_test tests/byrd_grounded_flight_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(byrd_grounded_flight_test PRIVATE include json/include)
add_test(NAME byrd_grounded_flight COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:byrd_grounded_flight_test>)
set_tests_properties(byrd_grounded_flight PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(half_dead_power_reset_test tests/half_dead_power_reset_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(half_dead_power_reset_test PRIVATE include json/include)
add_test(NAME half_dead_power_reset COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:half_dead_power_reset_test>)
set_tests_properties(half_dead_power_reset PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(strike_count_test tests/strike_count_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(strike_count_test PRIVATE include json/include)
add_test(NAME strike_count COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:strike_count_test>)
set_tests_properties(strike_count PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(pile_cost_reset_test tests/pile_cost_reset_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(pile_cost_reset_test PRIVATE include json/include)
add_test(NAME pile_cost_reset COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:pile_cost_reset_test>)
set_tests_properties(pile_cost_reset PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(panache_test tests/panache_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(panache_test PRIVATE include json/include)
add_test(NAME panache COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:panache_test>)
set_tests_properties(panache PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(dead_monster_block_test tests/dead_monster_block_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(dead_monster_block_test PRIVATE include json/include)
add_test(NAME dead_monster_block COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:dead_monster_block_test>)
set_tests_properties(dead_monster_block PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(mugger_death_rng_test tests/mugger_death_rng_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(mugger_death_rng_test PRIVATE include json/include)
add_test(NAME mugger_death_rng COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:mugger_death_rng_test>)
set_tests_properties(mugger_death_rng PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(slime_split_rng_test tests/slime_split_rng_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(slime_split_rng_test PRIVATE include json/include)
add_test(NAME slime_split_rng COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:slime_split_rng_test>)
set_tests_properties(slime_split_rng PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(dying_attacker_test tests/dying_attacker_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(dying_attacker_test PRIVATE include json/include)
add_test(NAME dying_attacker COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:dying_attacker_test>)
set_tests_properties(dying_attacker PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(blood_potion_heal_test tests/blood_potion_heal_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(blood_potion_heal_test PRIVATE include json/include)
add_test(NAME blood_potion_heal COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:blood_potion_heal_test>)
set_tests_properties(blood_potion_heal PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(post_victory_heal_test tests/post_victory_heal_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(post_victory_heal_test PRIVATE include json/include)
add_test(NAME post_victory_heal COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:post_victory_heal_test>)
set_tests_properties(post_victory_heal PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(empty_pile_loss_test tests/empty_pile_loss_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(empty_pile_loss_test PRIVATE include json/include)
add_test(NAME empty_pile_loss COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:empty_pile_loss_test>)
set_tests_properties(empty_pile_loss PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(thorns_blocked_hit_test tests/thorns_blocked_hit_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(thorns_blocked_hit_test PRIVATE include json/include)
add_test(NAME thorns_blocked_hit COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:thorns_blocked_hit_test>)
set_tests_properties(thorns_blocked_hit PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(hand_upgrade_all_test tests/hand_upgrade_all_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(hand_upgrade_all_test PRIVATE include json/include)
add_test(NAME hand_upgrade_all COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:hand_upgrade_all_test>)
set_tests_properties(hand_upgrade_all PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(mayhem_after_draw_test tests/mayhem_after_draw_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(mayhem_after_draw_test PRIVATE include json/include)
add_test(NAME mayhem_after_draw COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:mayhem_after_draw_test>)
set_tests_properties(mayhem_after_draw PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(slime_split_monster_count_test tests/slime_split_monster_count_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(slime_split_monster_count_test PRIVATE include json/include)
add_test(NAME slime_split_monster_count COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:slime_split_monster_count_test>)
set_tests_properties(slime_split_monster_count PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(curiosity_power_play_test tests/curiosity_power_play_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(curiosity_power_play_test PRIVATE include json/include)
add_test(NAME curiosity_power_play COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:curiosity_power_play_test>)
set_tests_properties(curiosity_power_play PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(unplayable_autoplay_test tests/unplayable_autoplay_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(unplayable_autoplay_test PRIVATE include json/include)
add_test(NAME unplayable_autoplay COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:unplayable_autoplay_test>)
set_tests_properties(unplayable_autoplay PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(purge_copy_can_use_test tests/purge_copy_can_use_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(purge_copy_can_use_test PRIVATE include json/include)
add_test(NAME purge_copy_can_use COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:purge_copy_can_use_test>)
set_tests_properties(purge_copy_can_use PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(lagavulin_wake_metallicize_test tests/lagavulin_wake_metallicize_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(lagavulin_wake_metallicize_test PRIVATE include json/include)
add_test(NAME lagavulin_wake_metallicize COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:lagavulin_wake_metallicize_test>)
set_tests_properties(lagavulin_wake_metallicize PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(magnetism_start_of_turn_test tests/magnetism_start_of_turn_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(magnetism_start_of_turn_test PRIVATE include json/include)
add_test(NAME magnetism_start_of_turn COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:magnetism_start_of_turn_test>)
set_tests_properties(magnetism_start_of_turn PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(active_power_features_test tests/active_power_features_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(active_power_features_test PRIVATE include json/include)
add_test(NAME active_power_features COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:active_power_features_test>)
set_tests_properties(active_power_features PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(potion_reward_swap_test tests/potion_reward_swap_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(potion_reward_swap_test PRIVATE include json/include)
add_test(NAME potion_reward_swap COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:potion_reward_swap_test>)
set_tests_properties(potion_reward_swap PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(shop_rules_fix_test tests/shop_rules_fix_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(shop_rules_fix_test PRIVATE include json/include)
add_test(NAME shop_rules_fix COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:shop_rules_fix_test>)
set_tests_properties(shop_rules_fix PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(full_hp_rest_filter_test tests/full_hp_rest_filter_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(full_hp_rest_filter_test PRIVATE include json/include)
add_test(NAME full_hp_rest_filter COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:full_hp_rest_filter_test>)
set_tests_properties(full_hp_rest_filter PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(deck_obtain_raw_test tests/deck_obtain_raw_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(deck_obtain_raw_test PRIVATE include json/include)
add_test(NAME deck_obtain_raw COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:deck_obtain_raw_test>)
set_tests_properties(deck_obtain_raw PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(matryoshka_counter_test tests/matryoshka_counter_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(matryoshka_counter_test PRIVATE include json/include)
add_test(NAME matryoshka_counter COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:matryoshka_counter_test>)
set_tests_properties(matryoshka_counter PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(old_coin_gold_test tests/old_coin_gold_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(old_coin_gold_test PRIVATE include json/include)
add_test(NAME old_coin_gold COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:old_coin_gold_test>)
set_tests_properties(old_coin_gold PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(vampires_strike_tag_test tests/vampires_strike_tag_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(vampires_strike_tag_test PRIVATE include json/include)
add_test(NAME vampires_strike_tag COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:vampires_strike_tag_test>)
set_tests_properties(vampires_strike_tag PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(screenless_relic_pool_test tests/screenless_relic_pool_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(screenless_relic_pool_test PRIVATE include json/include)
add_test(NAME screenless_relic_pool COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:screenless_relic_pool_test>)
set_tests_properties(screenless_relic_pool PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(gold_reward_idol_test tests/gold_reward_idol_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(gold_reward_idol_test PRIVATE include json/include)
add_test(NAME gold_reward_idol COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:gold_reward_idol_test>)
set_tests_properties(gold_reward_idol PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(ooc_relic_minor_fix_test tests/ooc_relic_minor_fix_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(ooc_relic_minor_fix_test PRIVATE include json/include)
add_test(NAME ooc_relic_minor_fix COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:ooc_relic_minor_fix_test>)
set_tests_properties(ooc_relic_minor_fix PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(remove_obtain_weight_test tests/remove_obtain_weight_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(remove_obtain_weight_test PRIVATE include json/include)
add_test(NAME remove_obtain_weight COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:remove_obtain_weight_test>)
set_tests_properties(remove_obtain_weight PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(native_ooc_card_win_rank_test tests/native_ooc_card_win_rank_test.cpp
    apps/one_combat/ooc_native_fallback.cpp apps/one_combat/run_features.cpp
    apps/one_combat/compact_tree.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(native_ooc_card_win_rank_test PRIVATE include json/include apps)
add_test(NAME native_ooc_card_win_rank COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:native_ooc_card_win_rank_test>)
set_tests_properties(native_ooc_card_win_rank PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(native_ooc_shop_features_test tests/native_ooc_shop_features_test.cpp
    apps/one_combat/ooc_native_fallback.cpp apps/one_combat/run_features.cpp
    apps/one_combat/compact_tree.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(native_ooc_shop_features_test PRIVATE include json/include apps)
add_test(NAME native_ooc_shop_features COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:native_ooc_shop_features_test>)
set_tests_properties(native_ooc_shop_features PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(test_ooc_public_futures apps/test_ooc_public_futures.cpp
    apps/one_combat/ooc_native_fallback.cpp apps/one_combat/run_features.cpp
    apps/one_combat/compact_tree.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(test_ooc_public_futures PRIVATE include json/include apps)
add_test(NAME ooc_public_futures COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:test_ooc_public_futures>)
set_tests_properties(ooc_public_futures PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration;smoke")

add_executable(one_combat apps/one_combat.cpp apps/combat_model_diagnostics.cpp
    apps/one_combat/ooc_leaf_capture.cpp
    apps/one_combat/ooc_leaf_capture_sink.cpp
    apps/one_combat/screen_leaf_snapshot.cpp
    apps/one_combat/screen_leaf_continuations.cpp
    apps/one_combat/screen_leaf_s0.cpp
    apps/one_combat/screen_leaf_probes.cpp
    apps/one_combat/screen_leaf_net.cpp
    apps/one_combat/screen_leaf_gbm.cpp
    apps/one_combat/heart_leaf.cpp apps/one_combat/heart_leaf_tail.cpp
    apps/one_combat/run_features.cpp apps/one_combat/compact_tree.cpp
    apps/one_combat/combat_predictor_input.cpp
    apps/one_combat/combat_transition.cpp
    apps/one_combat/e2c_capture.cpp
    apps/one_combat/ooc_mcts_adapter.cpp
    apps/one_combat/ooc_selective_silver_audit.cpp
    apps/one_combat/ooc_selective_silver_sampler.cpp
    apps/one_combat/ooc_native_fallback.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    apps/one_combat/ooc_policy.cpp
    apps/one_combat/ooc_v4_encoding.cpp
    apps/one_combat/run_driver.cpp
    apps/one_combat/a4_perturb.cpp
    apps/one_combat/ooc_tree_rules.cpp
    apps/one_combat/heart_outcome_capture.cpp
    apps/one_combat/expert_replay.cpp
    apps/one_combat/heart1_policy.cpp
    apps/one_combat/silver_price_table.cpp
    apps/one_combat/heart1_record_invariance.cpp
    apps/one_combat/rollout_student.cpp
    apps/one_combat/differential_state.cpp
    apps/one_combat/differential_replay_native.cpp
    apps/one_combat/run_trace.cpp
    apps/one_combat/semantic_pilot.cpp
    apps/one_combat/combat_datasets.cpp
    apps/one_combat/turn_dominance.cpp
    apps/one_combat/ritual_writhing_setup.cpp
    apps/one_combat/silver_synth_gen.cpp
    apps/one_combat/silver_synth_replay.cpp
    apps/one_combat/turn_plan.cpp
    apps/one_combat/ctm_offline_score.cpp
    apps/one_combat/fight_replay.cpp
    apps/one_combat/ooc_factor_eval.cpp
    apps/one_combat/potion_price_probe.cpp
    apps/one_combat/fight_end_pairs.cpp
    apps/one_combat/strategic_gen.cpp
    apps/one_combat/counterfactual_gen.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(one_combat PUBLIC include)
target_include_directories(one_combat PUBLIC json/include)
target_include_directories(one_combat PRIVATE apps)
link_ctm_crypto(one_combat)
target_link_options(one_combat PRIVATE -Wl,--gc-sections)

add_test(NAME heart_outcome_capture COMMAND one_combat heartoutcomeselftest)
add_test(NAME forced_boss_relic COMMAND one_combat forcebossrelicselftest)
add_test(NAME forced_decision COMMAND one_combat forcedecisionselftest)
add_test(NAME a4_perturb COMMAND one_combat a4perturbselftest)
add_test(NAME fight_end_pairs COMMAND one_combat fightendpairselftest)
set_tests_properties(fight_end_pairs PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")
add_test(NAME heart1_public_record_invariance COMMAND one_combat heart1recordselftest)
add_test(NAME heart1_ppo COMMAND one_combat heart1pposelftest)
add_test(NAME heart_outcome_collection_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_heart_outcome_collect.py)
add_test(NAME heart_outcome_import_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_heart_outcome_import.py)
set_tests_properties(heart_outcome_import_python PROPERTIES LABELS "core;smoke")
set_tests_properties(heart_outcome_collection_python PROPERTIES LABELS "core;smoke")
set_tests_properties(heart_outcome_capture PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")
set_tests_properties(heart1_public_record_invariance PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")
set_tests_properties(heart1_ppo PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")
add_test(NAME heart1_ppo_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_heart1_ppo.py)
set_tests_properties(heart1_ppo_python PROPERTIES LABELS "core;smoke")
add_test(NAME ppo_signals_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_ppo_signals.py)
set_tests_properties(ppo_signals_python PROPERTIES LABELS "core;smoke")
add_test(NAME ppo_decision_sources_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_ppo_decision_sources.py)
set_tests_properties(ppo_decision_sources_python PROPERTIES LABELS "core;smoke")
add_test(NAME critic_ceiling_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_critic_ceiling.py)
set_tests_properties(critic_ceiling_python PROPERTIES LABELS "core;smoke")
add_test(NAME combat_net_wire_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_combat_net_wire.py)
set_tests_properties(combat_net_wire_python PROPERTIES LABELS "core;smoke")
add_test(NAME combat_net_pack_python COMMAND python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/tests -p test_combat_net_pack.py)
set_tests_properties(combat_net_pack_python PROPERTIES LABELS "core;smoke")

# Offline full-state transport for frozen #379 replay; no generated game seeds.
add_executable(screen_leaf_snapshot_test
    apps/one_combat/screen_leaf_snapshot.cpp
    apps/one_combat/screen_leaf_snapshot_test.cpp)
target_include_directories(screen_leaf_snapshot_test PRIVATE include json/include apps/one_combat)
add_test(NAME screen_leaf_snapshot COMMAND screen_leaf_snapshot_test)
add_executable(screen_leaf_gbm_test
    apps/one_combat/screen_leaf_gbm.cpp
    apps/one_combat/screen_leaf_gbm_test.cpp
    apps/one_combat/compact_tree.cpp)
target_include_directories(screen_leaf_gbm_test PRIVATE include json/include apps/one_combat)
add_test(NAME screen_leaf_gbm_features COMMAND screen_leaf_gbm_test)
add_executable(silver_price_table_test tests/silver_price_table_test.cpp
    apps/one_combat/silver_price_table.cpp apps/one_combat/compact_tree.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(silver_price_table_test PRIVATE include json/include apps apps/one_combat)
add_test(NAME silver_price_table COMMAND silver_price_table_test WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(silver_price_table PROPERTIES LABELS "core")
# STS_SILVER_PRICE_TABLE_LEAF unset / =0 gives main's act4replay rows; =a746 runs.
add_test(NAME silver_price_table_off_identity
    COMMAND bash ${CMAKE_SOURCE_DIR}/tests/silver_price_table_off_identity.sh $<TARGET_FILE:one_combat>
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(silver_price_table_off_identity PROPERTIES LABELS "core")
add_test(NAME silver_stalemate_flags_log
    COMMAND bash ${CMAKE_SOURCE_DIR}/tests/silver_stalemate_flags_log.sh $<TARGET_FILE:one_combat>
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(silver_stalemate_flags_log PROPERTIES LABELS "core")
add_test(NAME silver_risk_veto_flag_log
    COMMAND bash ${CMAKE_SOURCE_DIR}/tests/silver_risk_veto_flag_log.sh $<TARGET_FILE:one_combat>
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
set_tests_properties(silver_risk_veto_flag_log PROPERTIES LABELS "core")
add_executable(heart_leaf_test tests/heart_leaf_test.cpp
    apps/one_combat/heart_leaf.cpp apps/one_combat/run_features.cpp apps/one_combat/compact_tree.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(heart_leaf_test PRIVATE include json/include apps)
link_ctm_crypto(heart_leaf_test)
add_test(NAME heart_leaf_features COMMAND heart_leaf_test)
add_executable(screen_leaf_continuations_test
    apps/one_combat/screen_leaf_snapshot.cpp
    apps/one_combat/screen_leaf_continuations.cpp
    apps/one_combat/screen_leaf_continuations_test.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(screen_leaf_continuations_test PRIVATE include json/include apps/one_combat)
add_test(NAME screen_leaf_continuations
    COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh $<TARGET_FILE:screen_leaf_continuations_test>)

# Offline exact one-step combat parity against recorded live game steps.
add_executable(combat_parity_probe apps/combat_parity_probe.cpp
    apps/one_combat/combat_parity.cpp
    apps/one_combat/live_silver_importer.cpp
    apps/one_combat/live_silver_mapping.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat_parity_probe PRIVATE include json/include apps)
target_link_options(combat_parity_probe PRIVATE -Wl,--gc-sections)
add_test(NAME combat_parity COMMAND python3 -m unittest tests.test_combat_parity)
set_tests_properties(combat_parity PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    ENVIRONMENT "COMBAT_PARITY_PROBE=$<TARGET_FILE:combat_parity_probe>" LABELS "core;smoke")
add_executable(combat_parity_projection_test tests/combat_parity_projection_test.cpp
    apps/one_combat/combat_parity.cpp
    apps/one_combat/live_silver_importer.cpp
    apps/one_combat/live_silver_mapping.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat_parity_projection_test PRIVATE include json/include apps)
target_link_options(combat_parity_projection_test PRIVATE -Wl,--gc-sections)
add_test(NAME combat_parity_projection COMMAND combat_parity_projection_test)
set_tests_properties(combat_parity_projection PROPERTIES LABELS "core;smoke")

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
    apps/one_combat/heart1_policy.cpp
    apps/one_combat/heart_leaf.cpp
    apps/one_combat/ooc_v4_encoding.cpp
    apps/one_combat/run_features.cpp
    apps/one_combat/live_ooc_importer.cpp
    apps/one_combat/ooc_mcts_adapter.cpp
    apps/one_combat/ooc_tree_rules.cpp
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
add_test(NAME workflow_tools COMMAND python3 -m unittest tests.test_workflow_tools)
set_tests_properties(workflow_tools PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
add_test(NAME heart1_capture_provenance COMMAND python3 -m unittest tests.test_heart1_capture_provenance)
set_tests_properties(heart1_capture_provenance PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
find_program(STS_NODE_EXECUTABLE node)
if(STS_NODE_EXECUTABLE)
    add_test(NAME ooc_graph_logic COMMAND ${STS_NODE_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/test_ooc_graph_logic.js)
    set_tests_properties(ooc_graph_logic PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "tooling;smoke")
endif()

add_executable(test_live_ooc_policy apps/test_live_ooc_policy.cpp
    apps/one_combat/heart1_policy.cpp apps/one_combat/heart_leaf.cpp
    apps/one_combat/live_ooc_policy.cpp apps/one_combat/ooc_v4_encoding.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    apps/one_combat/run_features.cpp apps/one_combat/ooc_mcts_adapter.cpp apps/one_combat/ooc_tree_rules.cpp
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
    apps/one_combat/heart1_policy.cpp apps/one_combat/heart_leaf.cpp
    apps/one_combat/live_ooc_state.cpp apps/one_combat/live_ooc_policy.cpp
    apps/one_combat/ooc_checkpoint_policy.cpp
    apps/one_combat/ooc_v4_encoding.cpp apps/one_combat/run_features.cpp
    apps/one_combat/ooc_mcts_adapter.cpp apps/one_combat/ooc_tree_rules.cpp apps/one_combat/compact_tree.cpp
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
    ${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native
    ${CMAKE_CURRENT_BINARY_DIR}/live_ooc_parity_fixtures.jsonl
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_act3_entry.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_act1_boss_card_reward.json)
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
    apps/one_combat/compact_tree.cpp
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
add_test(NAME live_silver_importer COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:live_silver_importer_test>
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_slime_boss_split.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_guardian_a20_phases.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_runic_dome_two_thieves_turn1.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_runic_dome_three_byrds_turn1.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_runic_dome_writhing_mass_headbutt_turn2.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_shield_spear_back_attack_turn1.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_runic_dome_byrd_headbutt_grounded.json
    ${CMAKE_SOURCE_DIR}/tests/fixtures/live_automaton_stasis_headbutt_return.json)

add_executable(ritual_dagger_persistence_test apps/ritual_dagger_persistence_test.cpp
    apps/one_combat/combat_transition.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(ritual_dagger_persistence_test PRIVATE include json/include apps)
add_test(NAME ritual_dagger_persistence COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:ritual_dagger_persistence_test>)
set_tests_properties(ritual_dagger_persistence PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(ritual_writhing_setup_test apps/test_ritual_writhing_setup.cpp
    apps/one_combat/ritual_writhing_setup.cpp apps/one_combat/combat_transition.cpp
    apps/one_combat/combat_predictor_input.cpp $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(ritual_writhing_setup_test PRIVATE include json/include apps)
add_test(NAME ritual_writhing_setup COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:ritual_writhing_setup_test>)
set_tests_properties(ritual_writhing_setup PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

add_executable(ritual_dagger_eligibility_test apps/test_ritual_dagger_eligibility.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(ritual_dagger_eligibility_test PRIVATE include json/include)
add_test(NAME ritual_dagger_eligibility COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:ritual_dagger_eligibility_test>)
set_tests_properties(ritual_dagger_eligibility PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")

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

add_executable(ooc_tok_net_fast_test apps/ooc_tok_net_fast_test.cpp)
target_include_directories(ooc_tok_net_fast_test PRIVATE apps)
add_test(NAME ooc_tok_net_fast COMMAND $<TARGET_FILE:ooc_tok_net_fast_test>
    ${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native)
set_tests_properties(ooc_tok_net_fast PROPERTIES LABELS "integration;smoke")

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
add_executable(ooc-particle-planner-test tests/ooc_particle_planner_test.cpp src/sim/search/OocParticlePlanner.cpp)
target_include_directories(ooc-particle-planner-test PRIVATE include)
add_test(NAME ooc_particle_planner COMMAND $<TARGET_FILE:ooc-particle-planner-test>)
set_tests_properties(ooc_particle_planner PROPERTIES LABELS "core")

# CTest entries below cover checks that do not depend on apps/test.cpp
# subcommands (apps/test.cpp is a manual command dispatcher; its subcommands
# receive CTest entries separately). bash -n only parses, never executes.
add_test(NAME silver_useless_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/tests/test_silver_useless.py)
add_test(NAME run_profile_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/tests/test_run_profile.py)
add_test(NAME paired_analysis_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/paired_analysis.py --self-test)
add_test(NAME sprt_gate_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/sprt_gate.py --self-test)
add_test(NAME silver_tree_profile_analysis COMMAND python3
    ${CMAKE_SOURCE_DIR}/tools/tests/test_silver_tree_profile.py)
add_test(NAME py_compile_parity_test COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/parity_test.py)
add_test(NAME semantic_confirmation_analysis COMMAND python3 -m unittest
    tests.test_ooc_semantic_confirmation tests.test_semantic_confirmation_runner
    tools.test_semantic_combat_coverage -q)
set_tests_properties(semantic_confirmation_analysis PROPERTIES
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS "research-repro;tooling")
add_test(NAME py_compile_analyze_ooc_factor COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/analyze_ooc_factor.py)
add_test(NAME py_compile_silver_az_mlp COMMAND python3 -m py_compile ${CMAKE_SOURCE_DIR}/tools/silver_az_mlp.py)
add_test(NAME check_replay_selftest COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/verify/check_replay.py --self-test)
add_test(NAME turn_plan_enum COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/turn_plan_enum_check.py $<TARGET_FILE:one_combat>)
set_tests_properties(turn_plan_enum PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")
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
add_test(NAME silver_rollout_zero_cost_loop COMMAND $<TARGET_FILE:unit-test> silver_rollout_zero_cost_loop)
set_tests_properties(silver_escape_penalty PROPERTIES LABELS "core")
add_test(NAME silver_potion_weights COMMAND $<TARGET_FILE:unit-test> silver_potion_weights)
set_tests_properties(silver_potion_weights PROPERTIES LABELS "core")
add_test(NAME silver_concave_hp_leaf COMMAND $<TARGET_FILE:unit-test> silver_concave_hp_leaf)
set_tests_properties(silver_concave_hp_leaf PROPERTIES LABELS "core")
add_test(NAME silver_victory_turn_penalty COMMAND $<TARGET_FILE:unit-test> silver_victory_turn_penalty)
set_tests_properties(silver_victory_turn_penalty PROPERTIES LABELS "core")
add_test(NAME silver_loss_ceiling COMMAND $<TARGET_FILE:unit-test> silver_loss_ceiling)
set_tests_properties(silver_loss_ceiling PROPERTIES LABELS "core")
add_test(NAME silver_risk_veto COMMAND $<TARGET_FILE:unit-test> silver_risk_veto)
set_tests_properties(silver_risk_veto PROPERTIES LABELS "core")
add_test(NAME silver_order_dominance COMMAND $<TARGET_FILE:unit-test> silver_order_dominance)
set_tests_properties(silver_order_dominance PROPERTIES LABELS "core")
add_test(NAME silver_gumbel_root COMMAND $<TARGET_FILE:unit-test> silver_gumbel_root)
set_tests_properties(silver_gumbel_root PROPERTIES LABELS "core")
add_test(NAME silver_gumbel_boundary_observer COMMAND $<TARGET_FILE:unit-test> silver_gumbel_boundary_observer)
set_tests_properties(silver_gumbel_boundary_observer PROPERTIES LABELS "core")
add_test(NAME silver_gumbel_learned_stop COMMAND $<TARGET_FILE:unit-test> silver_gumbel_learned_stop)
set_tests_properties(silver_gumbel_learned_stop PROPERTIES LABELS "core")
add_test(NAME silver_hidden_info_invariance COMMAND $<TARGET_FILE:unit-test> silver_hidden_info_invariance)
set_tests_properties(silver_hidden_info_invariance PROPERTIES LABELS "core")
add_test(NAME silver_incense_heart_phase COMMAND $<TARGET_FILE:unit-test> silver_incense_heart_phase)
set_tests_properties(silver_incense_heart_phase PROPERTIES LABELS "core")
set_tests_properties(silver_rollout_zero_cost_loop PROPERTIES LABELS "core")
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
add_test(NAME match_and_keep_boss_draft_oracle
    COMMAND $<TARGET_FILE:one_combat> matchandkeep_oracle_selftest)
set_tests_properties(match_and_keep_boss_draft_oracle PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME match_and_keep_curse_fix
    COMMAND $<TARGET_FILE:one_combat> matchandkeep_curse_selftest)
set_tests_properties(match_and_keep_curse_fix PROPERTIES
    LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME act_fight_probe_all_ooc_root_state
    COMMAND $<TARGET_FILE:one_combat> actfightprobeallooc_rootstate_selftest)
set_tests_properties(act_fight_probe_all_ooc_root_state PROPERTIES
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
add_test(NAME vwin_e3_cf_selftest
    COMMAND python3 -m unittest tools.test_vwin_e3_cf -q)
set_tests_properties(vwin_e3_cf_selftest PROPERTIES
    LABELS "core;tooling" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME vwin_outcome_curve_selftest
    COMMAND python3 -m unittest tools.test_vwin_outcome_curve -q)
set_tests_properties(vwin_outcome_curve_selftest PROPERTIES
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
add_test(NAME vwin_map_396_analysis_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/analyze_vwin_map_396.py --self-test)
set_tests_properties(vwin_map_396_analysis_selftest PROPERTIES
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
# ADR-0051: STS_SILVER_LEARNED_STOP_MODEL selects a compiled stop model by id; A20
# whole-run modes default to learned stopping even with a sims argument.
add_test(NAME silver_learned_stop_rejects_unknown_model
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 20 46009000 /tmp/sls-invalid.csv")
set_tests_properties(silver_learned_stop_rejects_unknown_model PROPERTIES
    ENVIRONMENT "STS_SILVER_LEARNED_STOP_MODEL=gbt-000000000000"
    PASS_REGULAR_EXPRESSION "\\[A20 default: Silver learned stopping.*STS_SILVER_LEARNED_STOP_MODEL must be gbt-0cac7cc64364 or gbt-770201c31f7b")
add_test(NAME silver_learned_stop_no_default_below_a20
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 0 46009000 /tmp/sls-invalid.csv")
set_tests_properties(silver_learned_stop_no_default_below_a20 PROPERTIES
    ENVIRONMENT "STS_SILVER_LEARNED_STOP=1;STS_SILVER_LEARNED_STOP_MODEL=gbt-000000000000"
    PASS_REGULAR_EXPRESSION "STS_SILVER_LEARNED_STOP_MODEL must be"
    FAIL_REGULAR_EXPRESSION "A20 default")
add_test(NAME silver_learned_stop_a20_zero_keeps_flat
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 20 46009000 /tmp/sls-invalid.csv")
set_tests_properties(silver_learned_stop_a20_zero_keeps_flat PROPERTIES
    ENVIRONMENT "STS_SILVER_LEARNED_STOP=0;STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=1"
    PASS_REGULAR_EXPRESSION "STS_SILVER_LEARNED_STOP_BOSS_FALLBACK"
    FAIL_REGULAR_EXPRESSION "A20 default")
add_test(NAME silver_learned_stop_rejects_boss_fallback_without_learned_stop
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 0 46009000 /tmp/sls-invalid.csv")
set_tests_properties(silver_learned_stop_rejects_boss_fallback_without_learned_stop PROPERTIES
    ENVIRONMENT "STS_SILVER_ADAPTIVE=0;STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=1"
    PASS_REGULAR_EXPRESSION "STS_SILVER_LEARNED_STOP_BOSS_FALLBACK requires STS_SILVER_LEARNED_STOP=1")
add_test(NAME silver_gold_weight_rejects_negative
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash -c "! bash tools/seed_guard.sh $<TARGET_FILE:one_combat> bestbench 10000 1 0 46009000 /tmp/sgw-invalid.csv")
set_tests_properties(silver_gold_weight_rejects_negative PROPERTIES
    ENVIRONMENT "STS_SILVER_ADAPTIVE=0;STS_SILVER_GOLD_WEIGHT=-1"
    PASS_REGULAR_EXPRESSION "STS_SILVER_GOLD_WEIGHT must be a number in \\[0, 100\\]")
# strategicgen2 aborts if a Tier-B label branch leaves t_curPath cleared before
# the main-trajectory policy step (the branch evaluator resets it on return).
add_test(NAME strategicgen2_policy_keeps_path
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash tools/seed_guard.sh $<TARGET_FILE:one_combat> strategicgen2 1 20 0
        ${CMAKE_BINARY_DIR}/strategicgen2_policy_keeps_path.csv 74000000)
set_tests_properties(strategicgen2_policy_keeps_path PROPERTIES
    ENVIRONMENT "OMP_NUM_THREADS=1;STRATEGIC_BRANCH_FIGHTS=1;STRATEGIC_BRANCH_SIMS=10"
    LABELS "integration;smoke")
# strategicmarggen aborts if Pass 2 replays the source policy without the
# snapshot's path (the Pass 2 source rerun and each branch clear t_curPath).
add_test(NAME strategicmarggen_replay_keeps_path
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash tools/seed_guard.sh $<TARGET_FILE:one_combat> strategicmarggen 1 20 1 2
        ${CMAKE_BINARY_DIR}/strategicmarggen_replay_keeps_path.csv 74000001)
set_tests_properties(strategicmarggen_replay_keeps_path PROPERTIES
    ENVIRONMENT "OMP_NUM_THREADS=1;STRATEGIC_BRANCH_FIGHTS=1;STRATEGIC_BRANCH_SIMS=10"
    LABELS "integration;smoke")
# strategicmarggen Pass 2 must reproduce Pass 1: each source replay reaches the
# source run's post-decision state (agent RNG restored per snapshot) and each
# stored state row matches its snapshot (row built before the snapshot move).
add_test(NAME strategicmarggen_replay_matches_source
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash tools/seed_guard.sh $<TARGET_FILE:one_combat> strategicmarggen 1 20 0 200
        ${CMAKE_BINARY_DIR}/strategicmarggen_replay_matches_source.csv 74000001)
set_tests_properties(strategicmarggen_replay_matches_source PROPERTIES
    ENVIRONMENT "OMP_NUM_THREADS=1"
    PASS_REGULAR_EXPRESSION "source replay checks [1-9][0-9]*, replay mismatches 0, stateRow mismatches 0"
    LABELS "integration;smoke")
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
add_test(NAME a20_teacher_runner COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/test_a20_teacher_runner.py)
set_tests_properties(a20_teacher_runner PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME a20_teacher_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/test_analyze_a20_teachers.py)
set_tests_properties(a20_teacher_analysis PROPERTIES
    LABELS "core;research-repro"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME a20_teacher_large_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/test_analyze_a20_teachers_large.py)
set_tests_properties(a20_teacher_large_analysis PROPERTIES
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
add_test(NAME ooc_learned_stop_parity COMMAND $<TARGET_FILE:one_combat> ooclearnedstoptest
    tests/fixtures/ooc_learned_stop_parity.jsonl models/candidates/ooc_learned_stop_trees.txt)
set_tests_properties(ooc_learned_stop_parity PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration" PASS_REGULAR_EXPRESSION "ooclearnedstoptest rows=256 mismatched=0 ")
add_test(NAME ctm_act4_survival_parity COMMAND $<TARGET_FILE:one_combat> ctmact4survivaltest
    tests/fixtures/ctm_act4_survival_parity.jsonl)
set_tests_properties(ctm_act4_survival_parity PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_ACT4_SURVIVAL_MODEL=models/candidates/ctm_act4_survival_trees.txt"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
# ADR-0048: unset, the pathb-a20 stack uses the bundled model; =0 restores the CTM head, so parity must fail. The
# ADR-0058 calibration is off here: the test checks the Act-4 model alone.
add_test(NAME ctm_act4_survival_default COMMAND $<TARGET_FILE:one_combat> ctmact4survivaltest
    tests/fixtures/ctm_act4_survival_parity.jsonl)
set_tests_properties(ctm_act4_survival_default PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT_MODIFICATION "STS_CTM_ACT4_SURVIVAL_MODEL=unset:;STS_CTM_CALIBRATION=set:0"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_act4_survival_off COMMAND $<TARGET_FILE:one_combat> ctmact4survivaltest
    tests/fixtures/ctm_act4_survival_parity.jsonl)
set_tests_properties(ctm_act4_survival_off PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_ACT4_SURVIVAL_MODEL=0"
    WILL_FAIL TRUE
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
# STS_CTM_CALIBRATION: parity with tools/ctm_calibration.py. Unset applies the built-in A20 stack's own table (also
# under a research manifest with the same content), but not with STS_CTM_ACT4_SURVIVAL_MODEL set; =0 keeps the CTM's
# scores. Each stack has its own fixture. These five check the §470 stack with the ADR-0058 table
# (STS_CTM_A20_HP_FINETUNE=0); the ctm_calibration_ft_hp_* ones below check the ADR-0059 default.
add_test(NAME ctm_calibration_parity COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_parity.jsonl on)
set_tests_properties(ctm_calibration_parity PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_CALIBRATION=models/candidates/ctm_calibration_pathb_a20_v1.json;STS_CTM_A20_HP_FINETUNE=0"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=on "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_default COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_parity.jsonl on)
set_tests_properties(ctm_calibration_default PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_A20_HP_FINETUNE=0"
    ENVIRONMENT_MODIFICATION "STS_CTM_CALIBRATION=unset:;STS_CTM_ACT4_SURVIVAL_MODEL=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=on "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_default_research_manifest COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_parity.jsonl on)
set_tests_properties(ctm_calibration_default_research_manifest PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_A20_HP_FINETUNE=0;STS_CTM_RESEARCH_CANDIDATE_MANIFEST=docs/experiments/evidence/ctm_a20_boss_calib_470_20261014/candidate-pathb-a20-lizard-boss470.json;STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=00bb4da6eb9b3117feb0579356436a96f7315ea28a8f3d1f29fd10b827c254ea"
    ENVIRONMENT_MODIFICATION "STS_CTM_CALIBRATION=unset:;STS_CTM_ACT4_SURVIVAL_MODEL=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=on "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_default_act4_set COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_parity.jsonl off)
set_tests_properties(ctm_calibration_default_act4_set PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_A20_HP_FINETUNE=0;STS_CTM_ACT4_SURVIVAL_MODEL=models/candidates/ctm_act4_survival_trees.txt"
    ENVIRONMENT_MODIFICATION "STS_CTM_CALIBRATION=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=off "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_off COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_parity.jsonl off)
set_tests_properties(ctm_calibration_off PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_CALIBRATION=0;STS_CTM_A20_HP_FINETUNE=0"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=off "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
# ADR-0059: unset (or 1), the built-in A20 stack is the §672 HP-head fine-tune with its own table.
add_test(NAME ctm_calibration_ft_hp_parity COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_ft_hp_parity.jsonl on)
set_tests_properties(ctm_calibration_ft_hp_parity PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_CALIBRATION=models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json;STS_CTM_A20_HP_FINETUNE=1"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=on "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_ft_hp_default COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_ft_hp_parity.jsonl on)
set_tests_properties(ctm_calibration_ft_hp_default PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT_MODIFICATION "STS_CTM_CALIBRATION=unset:;STS_CTM_ACT4_SURVIVAL_MODEL=unset:;STS_CTM_A20_HP_FINETUNE=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=on "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_ft_hp_default_research_manifest COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_ft_hp_parity.jsonl on)
set_tests_properties(ctm_calibration_ft_hp_default_research_manifest PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_RESEARCH_CANDIDATE_MANIFEST=models/candidates/ctm_finetune_hp_pathb_a20_v1.manifest.json;STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=31bb21f7ace7e3cd440136cf0799dbae1e0fbc2964d00bfa7bac8e21124e0a5c"
    ENVIRONMENT_MODIFICATION "STS_CTM_CALIBRATION=unset:;STS_CTM_ACT4_SURVIVAL_MODEL=unset:;STS_CTM_A20_HP_FINETUNE=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=on "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_ft_hp_default_act4_set COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_ft_hp_parity.jsonl off)
set_tests_properties(ctm_calibration_ft_hp_default_act4_set PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_ACT4_SURVIVAL_MODEL=models/candidates/ctm_act4_survival_trees.txt"
    ENVIRONMENT_MODIFICATION "STS_CTM_CALIBRATION=unset:;STS_CTM_A20_HP_FINETUNE=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=off "
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_calibration_ft_hp_off COMMAND $<TARGET_FILE:one_combat> ctmcalibrationtest
    tests/fixtures/ctm_calibration_ft_hp_parity.jsonl off)
set_tests_properties(ctm_calibration_ft_hp_off PROPERTIES
    LABELS "core;research-repro"
    ENVIRONMENT "STS_CTM_CALIBRATION=0"
    ENVIRONMENT_MODIFICATION "STS_CTM_A20_HP_FINETUNE=unset:"
    PASS_REGULAR_EXPRESSION "ctmcalibrationtest PASS mode=off "
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
add_test(NAME silver_rollout_limit COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:unit-test> silver_rollout_limit)
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
add_test(NAME ctm_retrain_pins_selftest COMMAND python3 -m unittest tools.test_ctm_retrain_pins)
set_tests_properties(ctm_retrain_pins_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME export_combat_transition_near_full_override_selftest
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tools/test_export_combat_transition_near_full.py)
add_test(NAME ctm_exposure_cohorts_selftest COMMAND python3 -m unittest tools.test_ctm_exposure_cohorts)
set_tests_properties(ctm_exposure_cohorts_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_support_census_check_selftest COMMAND python3 -m unittest tools.test_ctm_support_census_check)
set_tests_properties(ctm_support_census_check_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_qualify_fixtures_selftest COMMAND python3 -m unittest tools.test_ctm_qualify_fixtures)
set_tests_properties(ctm_qualify_fixtures_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_input_encoding_selftest COMMAND python3 -m unittest tools.test_ctm_input_encoding)
set_tests_properties(ctm_input_encoding_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_hp_domain_selftest COMMAND python3 -m unittest tools.test_ctm_hp_domain)
set_tests_properties(ctm_hp_domain_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_escape_selftest COMMAND python3 -m unittest tools.test_ctm_escape)
set_tests_properties(ctm_escape_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_capabilities_selftest COMMAND python3 -m unittest tools.test_ctm_capabilities)
set_tests_properties(ctm_capabilities_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ctm_lizard_selftest COMMAND python3 -m unittest tools.test_ctm_lizard)
set_tests_properties(ctm_lizard_selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
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
set_tests_properties(paired_analysis_selftest sprt_gate_selftest py_compile_parity_test py_compile_analyze_ooc_factor check_replay_selftest vnettest_selftest winnettest_selftest battlecontext_roundtrip designer_in_spire cardqueue_overflow keys_collect issue_fixes thorns_retaliation awakened_one_stage2 darkling_victory poison_lose_hp time_eater_exhaust simhealth_gamble_empty_hand gamblers_brew_legality simhealth_selection_failure training_integrity e2c_observer_scope analyze_postcombat_raw_terminal_selftest export_win_model_selftest runwin_e2c_native_parity
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
    check_replay_selftest check_benchmark_canary_selftest export_win_model_selftest sprt_gate_selftest
    PROPERTIES LABELS "tooling")
set_tests_properties(analyze_postcombat_raw_terminal_selftest vwin_terminal_pricing_audit_selftest PROPERTIES LABELS "research-repro")
set_property(TEST paired_analysis_selftest check_replay_selftest
    battlecontext_roundtrip issue_fixes APPEND PROPERTY LABELS "smoke")

add_test(NAME ooc_mcts_adapter COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:one_combat> oocmctsselftest)
# Run-level loss accounting of runFullRunOOC on one seed with substitute combat backends (UNDECIDED exit
# recorded as the death; a throwing backend becomes CombatAbort with the partial result).
add_test(NAME run_driver_loss_accounting COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:one_combat> rundriverlossselftest 1 0)
set_tests_properties(run_driver_loss_accounting PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
set_tests_properties(ooc_mcts_adapter PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration" ENVIRONMENT "STS_NATIVE_OOC=1;STS_OOC_STRATEGIC_TOK_NN=${CMAKE_SOURCE_DIR}/selfplay/models/ooc_strategic_tok_final.native")
add_test(NAME arm_c_rollout_analysis COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_arm_c_rollout_493.py -q)
set_tests_properties(arm_c_rollout_analysis PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "tooling")
add_test(NAME arm_c_rollout_startup COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_arm_c_rollout_startup.py $<TARGET_FILE:one_combat>)
set_tests_properties(arm_c_rollout_startup PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration")
add_test(NAME ooc_leaf_capture_startup COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_ooc_leaf_capture_startup.py $<TARGET_FILE:one_combat>)
set_tests_properties(ooc_leaf_capture_startup PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration")
add_test(NAME ooc_real_learned_stop_guard COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_ooc_real_learned_stop_guard.py $<TARGET_FILE:one_combat>)
set_tests_properties(ooc_real_learned_stop_guard PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration")
add_test(NAME ooc_leaf_calibration_default COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_ooc_leaf_calibration_default.py $<TARGET_FILE:one_combat>)
set_tests_properties(ooc_leaf_calibration_default PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration")
add_test(NAME ooc_leaf_replay COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:one_combat> oocleafreplayselftest)
set_tests_properties(ooc_leaf_replay PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration" ENVIRONMENT "STS_NATIVE_OOC=1;OMP_NUM_THREADS=1")
add_test(NAME ooc_leaf_replay_startup COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_ooc_leaf_replay_startup.py $<TARGET_FILE:one_combat>)
set_tests_properties(ooc_leaf_replay_startup PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration")
add_test(NAME ooc_leaf_stability COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh
    $<TARGET_FILE:one_combat> oocleafstabilityselftest)
set_tests_properties(ooc_leaf_stability PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration" ENVIRONMENT "STS_NATIVE_OOC=1;OMP_NUM_THREADS=1")
add_test(NAME ooc_leaf_stability_startup COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/test_ooc_leaf_stability_startup.py $<TARGET_FILE:one_combat>)
set_tests_properties(ooc_leaf_stability_startup PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    LABELS "integration")

# Captured-state probability probe; no gameplay or default integration.
add_executable(combat_transition_runtime_probe tests/combat_transition_runtime_probe.cpp
    apps/one_combat/combat_transition_near_full.cpp
    apps/one_combat/combat_transition_runtime.cpp
    apps/one_combat/combat_transition_native_contract.cpp
    apps/one_combat/combat_predictor_input.cpp apps/one_combat/combat_transition.cpp
    apps/one_combat/compact_tree.cpp
    $<TARGET_OBJECTS:sts_core_objects>)
target_include_directories(combat_transition_runtime_probe PRIVATE include json/include)
link_ctm_crypto(combat_transition_runtime_probe)
add_test(NAME ctm_ritual_kill_budget COMMAND $<TARGET_FILE:combat_transition_runtime_probe>
    --ritual-kill-budget-selftest
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_near_full_except_smoke_v2.native)
set_tests_properties(ctm_ritual_kill_budget PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "core;smoke")
add_test(NAME combat_transition_native_contract COMMAND python3 -m unittest
    tests.test_combat_transition_native_contract -v)
set_tests_properties(combat_transition_native_contract PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME combat_transition_runtime_loader COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_combat_transition_runtime_loader.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(combat_transition_runtime_loader PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_encoder_memo_parity COMMAND $<TARGET_FILE:combat_transition_runtime_probe> --encoder-memo-parity
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_deepsets_pathb_r2.native
    ${CMAKE_SOURCE_DIR}/selfplay/models/combat_transition_deepsets_lizard_t2.native
    ${CMAKE_SOURCE_DIR}/tests/fixtures/combat_transition_near_full.jsonl)
set_tests_properties(ctm_encoder_memo_parity PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_research_candidate_loader COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_ctm_research_candidate.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(ctm_research_candidate_loader PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_input_encoding COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_ctm_input_encoding.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(ctm_input_encoding PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_escape_runtime COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_ctm_escape_runtime.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(ctm_escape_runtime PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_writhing_ritual_runtime COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_ctm_writhing_ritual_runtime.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(ctm_writhing_ritual_runtime PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_candidate_tool COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_ctm_candidate.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(ctm_candidate_tool PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR} LABELS "integration")
add_test(NAME ctm_lizard_runtime COMMAND python3
    ${CMAKE_SOURCE_DIR}/tests/check_ctm_lizard_runtime.py
    $<TARGET_FILE:combat_transition_runtime_probe>)
set_tests_properties(ctm_lizard_runtime PROPERTIES
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

# The strategic generators play the deployed OOC policy step (§431): their main
# trajectory must end where bestbench ends on the same seed.
add_test(NAME generator_policy_parity
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMAND bash tools/check_generator_policy_parity.sh $<TARGET_FILE:one_combat> 74008999 20 0
        ${CMAKE_BINARY_DIR}/generator_policy_parity)
set_tests_properties(generator_policy_parity PROPERTIES
    PASS_REGULAR_EXPRESSION "GENERATOR_POLICY_PARITY: PASS" LABELS "integration;smoke")

add_test(NAME ooc_selective_silver_sampler COMMAND $<TARGET_FILE:one_combat> oocselectivesilverselftest)
set_tests_properties(ooc_selective_silver_sampler PROPERTIES LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ooc_selective_silver_analysis COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/test_ooc_selective_silver.py)
set_tests_properties(ooc_selective_silver_analysis PROPERTIES LABELS "core;research-repro" WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
add_test(NAME ooc_selective_seed_guard_rejects_zero COMMAND bash ${CMAKE_SOURCE_DIR}/tools/seed_guard.sh $<TARGET_FILE:one_combat> oocselectivesilvergen 0 97151001 /tmp/audit-unused-plan /tmp/audit-unused-output)
set_tests_properties(ooc_selective_seed_guard_rejects_zero PROPERTIES WILL_FAIL TRUE LABELS "core;research-repro")

# Tests that import torch, xgboost, scipy or sklearn. Cloud containers lack these packages, so run
# `ctest -LE needs-ml-python` there; a failure in the rest is then a real failure.
set(STS_ML_PYTHON_TESTS
    semantic_confirmation_analysis
    analyze_postcombat_raw_terminal_selftest
    export_win_model_selftest
    ctm_near_full_inputs_selftest
    ctm_retrain_pins_selftest
    export_combat_transition_near_full_override_selftest
    ctm_exposure_cohorts_selftest
    ctm_qualify_fixtures_selftest
    ctm_hp_domain_selftest
    ctm_escape_selftest
    combat_transition_attention_hpo_promote_selftest
    combat_transition_attention_ablation_selftest
    combat_transition_shared_hp_encoder_selftest
    combat_transition_shared_maxhp_encoder_selftest
    combat_transition_shared_encoder_distill_selftest
    combat_transition_shared_encoder_potion_selftest
    combat_transition_survival_deepset_train_selftest
    combat_transition_survival_deepset_sweep_selftest
    combat_transition_survival_platt_selftest
    combat_transition_survival_mlp_selftest
    combat_transition_survival_mlp_head_selftest
    combat_transition_survival_deepset_aux_selftest
    combat_transition_survival_wide96_selftest
    combat_transition_wide96_pretrain_selftest
    combat_transition_potion_trajectory_selftest
    combat_transition_near_full_downstream_selftest
    combat_transition_shared_hp_downstream_selftest
    combat_transition_near_full_sampler_selftest
    combat_transition_near_full_relic_ancestral_selftest
    ctm_research_candidate_loader
    ctm_escape_runtime
    ctm_writhing_ritual_runtime
)
foreach(t IN LISTS STS_ML_PYTHON_TESTS)
    if(TEST ${t})
        set_property(TEST ${t} APPEND PROPERTY LABELS needs-ml-python)
    endif()
endforeach()

# Research tooling: exact expectimax baseline for native Silver on small
# combats. Its own copy of the engine is compiled with STS_EXACT_CHANCE (exact
# chance enumeration hooks, include/game/ExactChance.h); no other target sees
# the define. Not built by default.
add_library(sts_core_exact_objects OBJECT EXCLUDE_FROM_ALL ${sts_lightspeed_SOURCES})
target_include_directories(sts_core_exact_objects PUBLIC include json/include)
target_compile_definitions(sts_core_exact_objects PUBLIC STS_EXACT_CHANCE)
add_executable(exact_combat_solver EXCLUDE_FROM_ALL apps/exact_combat_solver.cpp $<TARGET_OBJECTS:sts_core_exact_objects>)
target_include_directories(exact_combat_solver PRIVATE include json/include)
target_compile_definitions(exact_combat_solver PRIVATE STS_EXACT_CHANCE)
link_ctm_crypto(exact_combat_solver)
