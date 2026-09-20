#ifndef STS_ONE_COMBAT_OOC_V4_ENCODING_H
#define STS_ONE_COMBAT_OOC_V4_ENCODING_H
#include "run_features.h"
#include "sim/search/GameAction.h"

constexpr int TOK_NGLOB = 42;
struct TokState {
    float glob[TOK_NGLOB];
    int nDk, nRl, nPt;
    int dk[96][3];
    int rl[64][2];
    int pt[8][2];
};

// Exact shared V4 encoder without the integration driver's diagnostic hook.
TokState buildTokStatePure(const sts::GameContext &, const one_combat::PathHistory &);
namespace one_combat {
bool v4DecisionSupported(const sts::GameContext &);
std::vector<sts::search::GameAction> v4CandidateActions(const sts::GameContext &);
void strategicCands(const sts::GameContext &, const sts::search::GameAction &,
                    int &, int &, int &, int &, int &, int &, int &);
void tokEntity(const sts::GameContext &, const sts::search::GameAction &, int &, int &, float &);
}
#endif
