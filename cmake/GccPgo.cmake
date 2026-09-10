# Opt-in experiment; ordinary Release retains its existing optimization flags.
set(STS_PGO_MODE "OFF" CACHE STRING "GCC profile-guided optimization: OFF, GENERATE, or USE")
set_property(CACHE STS_PGO_MODE PROPERTY STRINGS OFF GENERATE USE)
set(STS_PGO_PROFILE_DIR "" CACHE STRING "Absolute directory for GCC .gcda profiles")

if(NOT STS_PGO_MODE MATCHES "^(OFF|GENERATE|USE)$")
    message(FATAL_ERROR "STS_PGO_MODE must be OFF, GENERATE, or USE")
endif()
if(STS_PGO_MODE STREQUAL "OFF")
    return()
endif()
if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    message(FATAL_ERROR "STS_PGO_MODE requires the GNU C++ compiler")
endif()
if(CMAKE_CONFIGURATION_TYPES OR NOT CMAKE_BUILD_TYPE STREQUAL "Release")
    message(FATAL_ERROR "STS_PGO_MODE requires a single-config Release build")
endif()
if(NOT IS_ABSOLUTE "${STS_PGO_PROFILE_DIR}")
    message(FATAL_ERROR "STS_PGO_PROFILE_DIR must be an absolute path")
endif()

if(STS_PGO_MODE STREQUAL "GENERATE")
    file(MAKE_DIRECTORY "${STS_PGO_PROFILE_DIR}")
    # Collection can run OpenMP workers; do not race profiling counters.
    add_compile_options("-fprofile-generate=${STS_PGO_PROFILE_DIR}" -fprofile-update=atomic)
    add_link_options("-fprofile-generate=${STS_PGO_PROFILE_DIR}")
else()
    file(GLOB_RECURSE _sts_pgo_profiles "${STS_PGO_PROFILE_DIR}/*.gcda")
    if(NOT _sts_pgo_profiles)
        message(FATAL_ERROR "STS_PGO_MODE=USE requires collected .gcda profiles in STS_PGO_PROFILE_DIR")
    endif()
    # Never silently fall back to unprofiled code or accept stale coverage.
    add_compile_options("-fprofile-use=${STS_PGO_PROFILE_DIR}"
        -Werror=missing-profile -Werror=coverage-mismatch)
    add_link_options("-fprofile-use=${STS_PGO_PROFILE_DIR}"
        -Werror=missing-profile -Werror=coverage-mismatch)
endif()
message(STATUS "GCC PGO: ${STS_PGO_MODE}, profiles: ${STS_PGO_PROFILE_DIR}")
