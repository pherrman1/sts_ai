#ifndef STS_AI_ONE_COMBAT_VNET_QUERY_LOG_H
#define STS_AI_ONE_COMBAT_VNET_QUERY_LOG_H

#include <cstdint>

namespace one_combat {

void configureVNetQueryLogFromEnvironment();
bool vnetQueryLogConfigured();
void beginVNetQueryLogFight(std::uint64_t seed, int fightIdx);
void flushVNetQueryLog();

} // namespace one_combat

#endif // STS_AI_ONE_COMBAT_VNET_QUERY_LOG_H
