#pragma once

#include <cstdint>

int testBelief();
int testBeliefOrderInvariance();
int testBeliefImmutability();
int testRealBeliefFilter(std::uint64_t seed);
int testPersistentBeliefTransfer(std::uint64_t seed);
int testRngStatePropagation(std::uint64_t seed);
int testS3Rand64PriorSampler();
int testRejuvHistoryReplay(std::uint64_t seed);
int testRejuvSemanticSelect();
int testRejuvNoninterference(std::uint64_t seed);
int testRejuvConditionalBlocks();
