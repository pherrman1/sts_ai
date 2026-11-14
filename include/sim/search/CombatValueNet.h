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
    struct CardInstance;
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
    // The same values as combatExtractFeatures, for a buffer that only this
    // function writes: `touched` lists the entries of the wide relic / card /
    // monster / potion block the previous call on this buffer set, so only those
    // are reset instead of the whole block (start with an all-zero buffer and an
    // empty list, or with a buffer combatExtractFeatures filled and every index of
    // that block in the list).
    void combatExtractFeaturesReuse(const BattleContext &bc, float *out, std::vector<std::uint16_t> &touched);

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
    // Action block of playing card `c` (in hand or not) at monster `targetIdx` (-1 = none);
    // equals combatFillActionFeatures for a hand card's CARD action.
    void combatFillCardPlayFeatures(const BattleContext &bc, const CardInstance &c, int targetIdx, float *actionOut);
    // Monster slot an action targets: the card's target index when the action
    // block marks it as targeting a living enemy (aTargetsEnemy = 1), else -1.
    int  combatActionTargetSlot(const BattleContext &bc, const Action &action);
    // Per-monster slot block of the state layout: slot s's kCombatMonsterSlotFeatures
    // values (Id, Hp, Block, Str, Intent, Atk, Vuln, Weak, Poison) start at
    // combatMonsterSlotOffset() + s * kCombatMonsterSlotFeatures.
    constexpr int kCombatMonsterSlotFeatures = 9;
    constexpr int kCombatMonsterSlots = 5;
    int  combatMonsterSlotOffset();

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
        std::string path;

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
        [[nodiscard]] double predict(const BattleContext &bc, bool emitTrace = true) const;
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
        // Policy tree ensembles (combat_policy_trees_v1): score n candidate
        // actions of one state at once. `canonFeatures` holds the state block
        // (its action block is ignored); `actionBlocks` holds n consecutive
        // action blocks. out[i] equals predictVec on the state block followed by
        // action block i, bit for bit: each tree's state-only prefix is walked
        // once and the per-action sums keep predictVec's tree order.
        void predictPolicyActions(const float *canonFeatures, const float *actionBlocks,
                                  int n, double *out) const;

        // Factorized MLP policy prior (combat_policy_mlp_v1, research; Silver
        // tree prior). Per node: base = b1 + sum over nonzero state features of
        // x_i * pmStateW row i (computed once). Per edge: h1 = relu(base +
        // action block * pmActionW + pmCard row (aCardId + 1) + target slot
        // features * pmTargetW), h2 = relu(pmW2 h1 + pmB2), logit = pmW3.h2 + pmB3.
        // Input scaling and the card embedding's projection are folded into the
        // exported weights. Callers normalize logits with a softmax over edges.
        bool isPolicyMlp = false;
        int pmH1 = 0, pmH2 = 0;
        std::vector<float> pmStateW, pmActionW, pmCard, pmTargetW, pmB1, pmW2, pmB2, pmW3;
        std::vector<float> pmW2T;   // pmW2 transposed (h1 x h2), built by load
        // combat_policy_mlp_v2 per-node embedding tables (kPolicyMlpEmbRows x h1,
        // empty when absent): encounter id, and per occupied monster slot its
        // id + 1 and its incoming damage.
        std::vector<float> pmEnc, pmMonId, pmMonDmg;
        float pmB3 = 0.f;
        // Logits of n edges of one state. `stateFeatures` is the state block
        // (combatFeatureCount values), `actionBlocks` n consecutive action
        // blocks, `targetSlots[i]` combatActionTargetSlot of edge i (or -1).
        void predictPolicyMlp(const float *stateFeatures, const float *actionBlocks,
                              const int *targetSlots, int n, double *out) const;
        // The node's base (pmH1 values, before any edge's terms and the relu):
        // b1, the v2 embedding rows and the state layer. predictPolicyMlp builds
        // its edges on it; relu(base) is the state embedding a value head on
        // the frozen trunk reads (research, exact_combat_solver --leaf-heads).
        void policyMlpBase(const float *stateFeatures, std::vector<float> &base) const;

        // Compact copy of `trees` for predictPolicyActions, built by load for
        // policy tree ensembles whose children follow their parents (empty
        // otherwise, which keeps predictPolicyActions on predictVec). Each tree
        // starts at flatRoots[t]; a split's children sit at left (yes) and
        // left + 1 (no), relative to that start.
        struct FlatNode {
            float         thresh;   // leaf value when feat == -1
            std::int16_t  feat;     // canonical feature index, -1 = leaf
            std::uint16_t left;
        };
        std::vector<FlatNode> flatNodes;
        std::vector<int> flatRoots;
    };

    extern CombatValueNet g_combatVNet;   // loaded value model (if any)
    extern bool   g_richCombatFeatures;   // fill the wide relic/card-location block (else narrow fast path)

}

#endif //STS_LIGHTSPEED_COMBATVALUENET_H
