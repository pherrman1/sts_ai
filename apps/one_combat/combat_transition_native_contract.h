#ifndef STS_COMBAT_TRANSITION_NATIVE_CONTRACT_H
#define STS_COMBAT_TRANSITION_NATIVE_CONTRACT_H
#include "combat_transition.h"
#include <map>
#include <set>
namespace one_combat {
// A verified loader owns readiness; support never inspects inferred outcomes.
struct NativeComposedDomain {
    bool ready = false;
    bool nearFull = false;
    bool escape = false; // escape-capable artifact: an initial Smoke Bomb is supported
    bool writhingRitual = false; // Writhing Mass with Ritual Dagger is supported
    std::array<int,2> preCurHpRange{};
    std::array<int,2> preMaxHpRange{};
    std::vector<int> hpClasses;
    std::vector<int> maxHpClasses;
    std::vector<int> maxHpDeltaValues;
    std::set<std::string> trainedGroups;
};
std::vector<std::string> nativeComposedSupportReasons(const CombatPredictorInputV1 &input,
    const CombatTransitionPersistentState &pre, const NativeComposedDomain &domain);
std::vector<std::string> nativeComposedForecastSupportReasons(
    const CombatPredictorInputV1 &input, const NativeComposedDomain &domain);
CombatTransitionRandomState replayNativeComposedMisc(CombatTransitionRandomState pre, int encounter);
std::vector<CombatTransitionRelicState> reconstructNativeComposedRelics(
    const std::vector<CombatTransitionRelicState> &pre,
    const std::map<std::string,int> &residues, int encounter);
}
#endif
