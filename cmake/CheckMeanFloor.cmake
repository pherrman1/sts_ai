# ctest helper (2026-11-20): run az-run-driver (DRIVER, ARGS as a ;-list) and fail unless its summary's mean_floor
# is >= MIN_FLOOR. Guards --utility amber2-root against the fight-boundary collapse seen with per-state amber2
# (fake net, A0, --cross-combat: amber 4.71, amber2 2.98, amber2-root 4.56 over 300 runs).
execute_process(COMMAND ${DRIVER} ${ARGS} OUTPUT_VARIABLE out ERROR_VARIABLE err RESULT_VARIABLE rc)
if(NOT rc EQUAL 0)
  message(FATAL_ERROR "az-run-driver failed (${rc}): ${err}")
endif()
string(REGEX MATCH "\"mean_floor\": ([0-9.]+)" m "${out}${err}")
if(NOT m)
  message(FATAL_ERROR "no mean_floor in output")
endif()
set(floor ${CMAKE_MATCH_1})
if(floor LESS MIN_FLOOR)
  message(FATAL_ERROR "mean_floor ${floor} < ${MIN_FLOOR}")
endif()
message(STATUS "mean_floor ${floor} >= ${MIN_FLOOR}")
