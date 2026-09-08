#ifndef STS_AI_ONE_COMBAT_PARTICLE_DIAGNOSTICS_H
#define STS_AI_ONE_COMBAT_PARTICLE_DIAGNOSTICS_H

#include <cstdint>
#include <string>

namespace sts {
enum class MonsterEncounter : std::int8_t;
class BattleContext;
}

namespace one_combat {

void configureParticleDiagnosticsFromEnvironment();

bool particleDiagnosticsActive();
void beginParticleDiagnosticFight(std::uint64_t seed, int fightIdx, int floor,
                                  int act, sts::MonsterEncounter encounter);
int particleDiagnosticStratum(const sts::BattleContext &bc, int depth);
int particleDiagnosticStrataCount();

void startParticleLeafProbe(const std::string &outputFile);
void installParticleLeafProbeHooks(std::uint64_t seed);
std::string finishParticleLeafProbeSeed();
std::string particleLeafProbeHeader();
int particleLeafProbeK();
double particleLeafProbeRate();
int particleLeafProbeMaxGroups();

bool startParticlePosteriorProbe(const std::string &outputFile);
void installParticlePosteriorProbeHooks(std::uint64_t seed);
std::string finishParticlePosteriorProbeSeed();
std::string particlePosteriorProbeHeader();
std::string particlePosteriorActionFingerprint();
int particlePosteriorProbeK();
int particlePosteriorProbeMaxGroups();

void stopParticleDiagnostics();

} // namespace one_combat

#endif
