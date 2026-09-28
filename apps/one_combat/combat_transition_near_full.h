#pragma once
#include "combat_transition_runtime.h"
namespace one_combat {
CombatRuntimeSample sampleNearFull(const CombatTransitionRuntime &,const NativeComposedDomain &,
    const CombatTransitionPersistentState &,const CombatPredictorInputV1 &,std::mt19937_64 &,
    float survival,const std::vector<float>& maximum,const std::vector<float>& hpEncoding,
    const std::vector<float>& potionEncoding,bool survivalAlreadyWon=false);
nlohmann::json nearFullDiagnostics(const CombatTransitionRuntime &,const CombatTransitionPersistentState &,const CombatPredictorInputV1 &,int delta,int ending,int maximum,int mask,const std::vector<int>& consumed,bool escaped,const std::vector<int>& dagger);
}
