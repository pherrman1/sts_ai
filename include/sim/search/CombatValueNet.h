//
// Learned combat value function V_combat(state) -> expected fight end HP.
// Native C++ inference of the GPU-trained XGBoost model, for use as an MCTS leaf
// value (replacing random rollouts). Single source of truth for the combat
// feature layout so training data (combatgen) and inference stay identical.
//
#ifndef STS_LIGHTSPEED_COMBATVALUENET_H
#define STS_LIGHTSPEED_COMBATVALUENET_H

#include <string>
#include <vector>
#include <functional>
#include <cstdint>
#include <unordered_map>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    struct Action;   // forward decl (full def in Action.h)

    // The entity model has separate heads for survival and conditional end-HP.
    // Keep those available to callers that need a cheap combat transition,
    // rather than exposing only the leaf-search scalar utility.
    struct CombatOutcomePrediction {
        double winProbability = 0.0;
        double endHpFractionIfWin = 0.0;
    };

    // Canonical combat-feature layout (base scalars + active-power features), in the
    // exact order the CSV/header use. combatExtractFeatures fills out[] with
    // combatFeatureCount() values in this order.
    const std::vector<std::string>& combatFeatureNames();
    int  combatFeatureCount();
    void combatExtractFeatures(const BattleContext &bc, float *out);

    // POLICY feature layout = the combat state features above ++ per-ACTION features
    // (a comparator net scores each candidate action; softmax over a node's legal
    // edges = the MCTS prior). Single source of truth so the policy datagen and the
    // native PUCT inference use identical extraction. combatExtractPolicyFeatures
    // fills the state block then the action block for one (state, action) pair.
    const std::vector<std::string>& combatPolicyFeatureNames();
    int  combatPolicyFeatureCount();
    void combatExtractPolicyFeatures(const BattleContext &bc, const Action &action, float *out);
    // Fill only the per-action feature block (out points at the action sub-vector).
    // Lets a caller extract the shared state block once and refill this per edge.
    void combatFillActionFeatures(const BattleContext &bc, const Action &action, float *actionOut);

    // Compact XGBoost regression-tree ensemble (loaded from export_combat_model.py).
    struct CombatValueNet {
        struct Node {           // split: featIdx>=0, go yes if feat < thresh; leaf: featIdx=-1
            int   featIdx;
            float thresh;       // (leaf value stored here when featIdx == -1)
            int   yes;
            int   no;
        };
        std::vector<std::vector<Node>> trees;
        std::vector<int> sel;   // model-feature i -> index into the canonical feature vector
        // §132 target experiment: quantile regression over the terminal utility
        // R = 0 | 50+endHp (combat_quantile_v1 format). quantileTrees[q] is a
        // tree set (same layout as `trees`); predict()/predictVec() return the
        // mean over quantiles (EV), which is on the leaf's terminal scale.
        // Mutually exclusive with the single-set `trees` path.
        std::vector<std::vector<std::vector<Node>>> quantileTrees;
        std::vector<float> quantileBase;
        int nQuantiles = 0;
        // Compact distilled MLP alternative.  Weights are output-major so each
        // neuron's dot product is contiguous and easy for -O3 to vectorize.
        bool isMlp = false;
        bool isSparseMlp = false;
        bool isEntity = false;
        bool isEntityPolicy = false;
        bool isDeepSets = false;
        int h1 = 0, h2 = 0;
        std::vector<float> xMean, xInvStd;
        std::vector<float> w1, b1, w2, b2, w3;
        float b3 = 0.f, yMean = 0.f, yScale = 1.f;
        // Entity-aware multi-head model (combat_entity_v1).
        float entityWinBonus = 0.f;
        std::vector<int> entityScalarSel;
        std::vector<float> entityScalarMean, entityScalarInv, entityMonMean, entityMonInv;
        std::vector<float> entityCard, entityRelic, entityPotion, entityEncounter;
        std::vector<float> entityMonsterId, entityIntent, entityMonsterW, entityMonsterB;
        std::vector<float> entityTrunk1W, entityTrunk1B, entityTrunk2W, entityTrunk2B;
        std::vector<float> entityWinW, entityHpW;
        float entityWinB = 0.f, entityHpB = 0.f;
        // Shared-state entity policy (combat_policy_entity_v1). The state encoder
        // runs once per expanded node; the small action encoder runs per legal edge.
        std::vector<int> policyScalarSel, policyActionScalarSel;
        std::vector<float> policyScalarMean, policyScalarInv, policyMonMean, policyMonInv;
        std::vector<float> policyActionMean, policyActionInv;
        std::vector<float> policyCard, policyRelic, policyPotion, policyEncounter;
        std::vector<float> policyMonsterId, policyIntent, policyMonsterW, policyMonsterB;
        std::vector<float> policyStateW, policyStateB, policyActionCard;
        std::vector<float> policyActionW, policyActionB, policyActionBiasW;
        float policyActionBiasB = 0.f;
        // DeepSets fields (combat_deepsets_v1).
        int d_card = 0, d_relic = 0, d_pot = 0, d_mon = 0, d_enc = 0, d_scalar = 0;
        int encIdx = 1, nEncounter = 128;
        std::vector<float> dsScalarMean, dsScalarInv, dsScalarW, dsScalarB;
        std::vector<int> dsScalarSel;
        std::vector<float> dsCardE, dsRelicE, dsPotionE, dsEncE;
        std::vector<float> dsMonW1, dsMonB1, dsMonW2, dsMonB2;
        float baseScore = 0.f;
        bool  isLoaded = false;
        bool  isPolicy = false; // map model features against the POLICY layout, not the value one

        bool load(const std::string &path);
        // Per-encounter specialization: encounterModels maps a MonsterEncounter
        // enum int -> specialized model used by predict(bc) whenever
        // hasEncounterModels is set. Encounters without an entry fall through to
        // this object's own base weights/trees. Populated either by
        // loadEncounterModels(dir) (compact-tree per-encounter files) or by the
        // combat_mlp_meta_v1 per-encounter delta table inside load() itself.
        std::unordered_map<int, CombatValueNet> encounterModels;
        bool hasEncounterModels = false;
        // Load <dir>/<ENUM_NAME>.txt per-encounter compact-tree files (names from
        // monsterEncounterEnumNames[]); <dir>/_pooled.txt, when present, replaces
        // this object's base weights as the non-specialized fallback. All files
        // are validated before any state is replaced; a load failure leaves this
        // object untouched and per-encounter dispatch off.
        bool loadEncounterModels(const std::string &dir);
        [[nodiscard]] bool loaded() const { return isLoaded; }
        [[nodiscard]] bool hasOutcomeHeads() const { return isEntity; }
        [[nodiscard]] std::string description() const;
        [[nodiscard]] float winBonus() const { return isEntity ? entityWinBonus : 0.f; }
        void setWinBonus(float value) { if (isEntity) entityWinBonus = value; }
        [[nodiscard]] double predict(const BattleContext &bc) const;
        [[nodiscard]] double predictVec(const float *canonFeatures) const;  // canonical vector
        // Quantile model (combat_quantile_v1): EV = mean over quantiles of R.
        [[nodiscard]] double predictQuantileEV(const float *canonFeatures) const;
        [[nodiscard]] CombatOutcomePrediction predictOutcome(const BattleContext &bc) const;
        [[nodiscard]] CombatOutcomePrediction predictOutcomeVec(const float *canonFeatures) const;
        // Comparator score for one candidate action (policy net; isPolicy must be set).
        [[nodiscard]] double predictAction(const BattleContext &bc, const Action &action) const;
        // Fast shared-state path for combat_policy_entity_v1. `state64` has 64 floats.
        void encodePolicyStateVec(const float *canonFeatures, float *state64) const;
        [[nodiscard]] double predictPolicyActionVec(const float *canonFeatures,
                                                    const float *state64) const;
    };

    extern CombatValueNet g_combatVNet;   // loaded value model (if any)
    extern bool g_useVNet;                // use V_combat as the MCTS leaf value

    // Zero-mean ranking correction model (experimental, STS_VNET_RANK_CORR,
    // standalone diagnostic arm — never a default). A small compact-tree model
    // trained on group-centered leafref - endHp_pred residuals; when loaded it
    // is ADDED on top of the primary vnet/PVNet leaf value inside
    // evaluateLeaf()/evaluateLeafState() to improve within-group action
    // ranking without shifting the HP scale. Same CombatValueNet format and
    // predict() interface, reusing all existing load/inference code.
    extern CombatValueNet g_combatVNetRankCorr;
    extern bool g_useVNetRankCorr;

    // Residual VNet correction (STS_VNET_RESIDUAL=<path>, STS_VNET_RESIDUAL_BETA=<b>):
    // loaded model is ADDED with weight beta on top of the primary VNet prediction.
    // At beta=0, behavior is unchanged.  Same CombatValueNet format as primary.
    extern CombatValueNet g_combatVNetResidual;
    extern double g_vnetResidualBeta;
    extern bool g_useVNetResidual;

    extern CombatValueNet g_policyNet;    // loaded policy comparator (if any)
    extern bool   g_usePolicyNet;         // use PUCT with the policy prior in selection
    extern double g_cPuct;                // PUCT exploration constant
    extern bool   g_richCombatFeatures;   // fill the wide relic/card-location block (else narrow fast path)

    // Hook fired inside CombatValueNet::predict() after every
    // VNet inference. The BattleContext pointer is valid only for the duration
    // of the callback; the callback must not mutate it. prediction is the raw
    // model output (not alpha-blended). nullptr by default — when unset,
    // predict() is byte-identical to pre-hook behavior.
    // NOT thread_local: set once from main() and read by all worker threads.
    // The handler must be thread-safe (the one_combat.cpp handler uses
    // per-thread buffers with a shared mutex for file writes).
    extern std::function<void(const BattleContext &, double)> g_onVNetQuery;

    // Thread-local context set by search code before calling predict().
    // Read by g_onVNetQuery handlers to group siblings by parent obsHash.
    extern thread_local std::uint64_t g_vnetTraceParent;
    extern thread_local int g_vnetTraceDepth;

}

#endif //STS_LIGHTSPEED_COMBATVALUENET_H
