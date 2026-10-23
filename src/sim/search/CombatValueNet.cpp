//
// See CombatValueNet.h
//
#include "sim/search/CombatValueNet.h"

#include "combat/BattleContext.h"
#include "constants/MonsterEncounters.h"
#include "constants/PlayerStatusEffects.h"
#include "constants/MonsterStatusEffects.h"
#include "constants/Cards.h"
#include "constants/Relics.h"
#include "sim/search/Action.h"
#include "sim/search/ExpertKnowledge.h"

#include <cstdint>
#include <cstdlib>
#include <emmintrin.h>
#include <fstream>
#include <stdexcept>
#include <string>
#include <sstream>
#include <unordered_map>
#include <algorithm>
#include <cmath>

using namespace sts;

namespace {
    // Active-power features (must match apps/one_combat.cpp combatgen order/names).
    struct PowerFeat { const char *name; PlayerStatus status; };
    const PowerFeat kPowers[] = {
        {"pDemonForm",   PlayerStatus::DEMON_FORM},   {"pMetallicize",  PlayerStatus::METALLICIZE},
        {"pFeelNoPain",  PlayerStatus::FEEL_NO_PAIN}, {"pBarricade",    PlayerStatus::BARRICADE},
        {"pPlatedArmor", PlayerStatus::PLATED_ARMOR}, {"pRupture",      PlayerStatus::RUPTURE},
        {"pCombust",     PlayerStatus::COMBUST},      {"pDarkEmbrace",  PlayerStatus::DARK_EMBRACE},
        {"pBrutality",   PlayerStatus::BRUTALITY},    {"pFireBreath",   PlayerStatus::FIRE_BREATHING},
        {"pJuggernaut",  PlayerStatus::JUGGERNAUT},   {"pCorruption",   PlayerStatus::CORRUPTION},
        {"pVigor",       PlayerStatus::VIGOR},        {"pMayhem",       PlayerStatus::MAYHEM},
        {"pPanache",     PlayerStatus::PANACHE},      {"pNoxious",      PlayerStatus::NOXIOUS_FUMES},
        {"pFlameBarrier",PlayerStatus::FLAME_BARRIER},{"pThorns",       PlayerStatus::THORNS},
        {"pRegen",       PlayerStatus::REGEN},        {"pBuffer",       PlayerStatus::BUFFER},
        {"pIntangible",  PlayerStatus::INTANGIBLE},   {"pVulnerable",   PlayerStatus::VULNERABLE},
        {"pWeak",        PlayerStatus::WEAK},         {"pFrail",        PlayerStatus::FRAIL},
    };
    const char *kBaseNames[] = {
        "ascension","encounter","turn","curHp","maxHp","block","energy","strength","dexterity",
        "focus","artifact","monAlive","monSumHp","monMaxHp","monSumBlock","monSumStr","monSumArt",
        "hand","draw","discard","exhaust","nAtkAvail","nSklAvail","nPowAvail","nOtherAvail","potions",
    };
    constexpr int kNumBase = sizeof(kBaseNames) / sizeof(kBaseNames[0]);
    constexpr int kNumPow  = sizeof(kPowers) / sizeof(kPowers[0]);
    // Rich context (added 2026-07-15): relic presence + per-pile card-id counts, so
    // the value/policy nets see card IDENTITY and LOCATION, not just aggregates.
    constexpr int kNumCards  = 371;   // CardId members (0..370)
    constexpr int kNumRelics = 128;   // hasRelicRuntime is only valid for ids < 128
    // feature-block offsets within the state vector
    constexpr int kRelicOff = kNumBase + kNumPow;           // relics
    constexpr int kHandOff  = kRelicOff + kNumRelics;       // per-id count in hand
    constexpr int kDrawOff  = kHandOff  + kNumCards;        // ...draw pile
    constexpr int kDiscOff  = kDrawOff  + kNumCards;        // ...discard pile
    constexpr int kExhOff   = kDiscOff  + kNumCards;        // ...exhaust pile
    // enemy detail: aggregate incoming damage + per-monster slots (id/hp/block/str/
    // intent-damage/attacking/vuln/weak/poison), then potions by id.
    constexpr int kNumMonSlots = 5;                         // MonsterGroup holds up to 5
    constexpr int kMonFeats    = 9;
    constexpr int kNumPotions  = 44;                        // Potion enum size (ids 2..43 real)
    constexpr int kEnemyAggOff = kExhOff + kNumCards;       // incomingDmg, nAttacking
    constexpr int kMonOff      = kEnemyAggOff + 2;          // per-monster slots
    constexpr int kPotOff      = kMonOff + kNumMonSlots * kMonFeats;
    // misc player context: gold, potion capacity, per-turn play counters (drive
    // gold-gain cards + counter relics like Kunai/Shuriken/Nunchaku/PenNib).
    constexpr int kMiscOff     = kPotOff + kNumPotions;
    constexpr int kNumMisc     = 5;                         // gold, potionCap, cards/attacks/skills played
    // persistent (cross-turn) relic/status counters; per-turn ones like Kunai/Shuriken
    // are already covered by attacks/skillsPlayedThisTurn above.
    constexpr int kRelicCtrOff = kMiscOff + kNumMisc;
    constexpr int kNumRelicCtr = 8;
    constexpr int kStateCount  = kRelicCtrOff + kNumRelicCtr;
    constexpr int kEncounterIdx = 1;                        // "encounter" in kBaseNames
    constexpr int kMonDmgOff    = 4;                        // "mKIntent" = incoming damage (0 if not attacking)
    constexpr int kPolicyMlpEmbRows = 128;                  // policy-MLP embedding table rows
    constexpr int kPolicyMlpMaxH1 = 512;                    // policyMlpEdges stack buffer

    // STS_ACTIVE_POWER_FEATURES: unset or 1 = a power whose flag is off reads
    // 0. The engine clears some powers (Vigor, Flame Barrier, removed debuffs)
    // by their flag only, so statusMap keeps the old amount. 0 = the legacy
    // feature, which read that leftover amount. Other values are fatal.
    bool activePowerFeatures() {
        thread_local CachedFixFlag cache;
        return cachedFixFlag(cache, "STS_ACTIVE_POWER_FEATURES");
    }

    int powerVal(const Player &p, PlayerStatus s, bool activeOnly) {
        switch (s) {
            case PlayerStatus::STRENGTH:  return p.strength;
            case PlayerStatus::DEXTERITY: return p.dexterity;
            case PlayerStatus::FOCUS:     return p.focus;
            case PlayerStatus::ARTIFACT:  return p.artifact;
            default: break;
        }
        if (activeOnly && !p.hasStatusRuntime(s)) return 0;
        auto it = p.statusMap.find(s);
        if (it != p.statusMap.end()) return it->second;
        return p.hasStatusRuntime(s) ? 1 : 0;
    }
}

namespace sts::search {

CombatValueNet g_combatVNet;

// Fill the wide relic+card-location block only when something actually reads it
// (a rich net is loaded, or datagen needs full rows). Off => narrow extraction, so
// a legacy narrow net keeps the fast hot path. load() turns it on if the model uses
// any rich feature; datagen forces it on.
bool g_richCombatFeatures = false;

const std::vector<std::string>& combatFeatureNames() {
    static const std::vector<std::string> names = []{
        std::vector<std::string> v;
        for (const char *n : kBaseNames) v.emplace_back(n);
        for (const auto &pf : kPowers)   v.emplace_back(pf.name);
        for (int i = 0; i < kNumRelics; ++i) v.emplace_back("r"  + std::to_string(i));
        for (int i = 0; i < kNumCards;  ++i) v.emplace_back("hd" + std::to_string(i));  // hand
        for (int i = 0; i < kNumCards;  ++i) v.emplace_back("dr" + std::to_string(i));  // draw
        for (int i = 0; i < kNumCards;  ++i) v.emplace_back("ds" + std::to_string(i));  // discard
        for (int i = 0; i < kNumCards;  ++i) v.emplace_back("ex" + std::to_string(i));  // exhaust
        v.emplace_back("incomingDmg"); v.emplace_back("nAttacking");
        for (int i = 0; i < kNumMonSlots; ++i) {
            const std::string p = "m" + std::to_string(i);
            v.emplace_back(p+"Id");   v.emplace_back(p+"Hp");    v.emplace_back(p+"Block");
            v.emplace_back(p+"Str");  v.emplace_back(p+"Intent");v.emplace_back(p+"Atk");
            v.emplace_back(p+"Vuln"); v.emplace_back(p+"Weak");  v.emplace_back(p+"Poison");
        }
        for (int i = 0; i < kNumPotions; ++i) v.emplace_back("pot" + std::to_string(i));
        v.emplace_back("gold");         v.emplace_back("potionCap");
        v.emplace_back("cardsPlayed");  v.emplace_back("attacksPlayed"); v.emplace_back("skillsPlayed");
        v.emplace_back("happyFlowerCtr"); v.emplace_back("incenseBurnerCtr");
        v.emplace_back("inkBottleCtr");   v.emplace_back("inserterCtr");
        v.emplace_back("nunchakuCtr");    v.emplace_back("penNibCtr");
        v.emplace_back("sundialCtr");     v.emplace_back("panacheCtr");
        return v;
    }();
    return names;
}

int combatFeatureCount() { return kStateCount; }

// ---- Policy (state ++ action) features ------------------------------------
namespace {
    const char *kActionNames[] = {
        "aIsCard", "aIsPotion", "aIsEndTurn", "aIsSelect",
        "aCardId", "aCardCost", "aCardUpg", "aCardAtk", "aCardSkl", "aCardPow",
        "aTargetsEnemy", "aTargetHp", "aPlayOrder", "aObtainWeight",
        // §3.5 multi-select subset content (GAMBLE/EXHAUST_MANY and single
        // card selects): without these every select action of the same task
        // encoded identically, so priors were uniform across subsets. All
        // features appended AFTER the original 14 so the PVNet action encoder
        // (which reads the first 14) and old policy models keep working.
        "aSelectSize", "aSelTotalCost", "aSelAtk", "aSelSkl", "aSelPow",
        "aSelUpgraded", "aSelPlayOrder", "aSelObtainWeight",
    };
    constexpr int kNumAction = sizeof(kActionNames) / sizeof(kActionNames[0]);
}

const std::vector<std::string>& combatPolicyFeatureNames() {
    static const std::vector<std::string> names = []{
        std::vector<std::string> v = combatFeatureNames();   // state block first
        for (const char *n : kActionNames) v.emplace_back(n);
        return v;
    }();
    return names;
}

int combatPolicyFeatureCount() { return combatFeatureCount() + kNumAction; }

// Card-play part of the action block (a[4..13]) for card `c` aimed at monster `tgt`
// (-1 = none). `c` need not be in hand (rollout root table).
static void fillCardPlayFeatures(const BattleContext &bc, const CardInstance &c, int tgt, float *a) {
    const auto id = c.getId();
    a[4]  = (float)(int)id;
    a[5]  = (float)c.costForTurn;
    a[6]  = c.isUpgraded() ? 1.f : 0.f;
    const auto t = c.getType();
    a[7]  = (t == CardType::ATTACK) ? 1.f : 0.f;
    a[8]  = (t == CardType::SKILL)  ? 1.f : 0.f;
    a[9]  = (t == CardType::POWER)  ? 1.f : 0.f;
    if (tgt >= 0 && tgt < bc.monsters.monsterCount && bc.monsters.arr[tgt].curHp > 0) {
        a[10] = 1.f;
        a[11] = (float)bc.monsters.arr[tgt].curHp;
    }
    a[12] = (float)Expert::getPlayOrdering(id);
    a[13] = (float)Expert::getObtainWeight(id, c.isUpgraded());
}

void combatFillCardPlayFeatures(const BattleContext &bc, const CardInstance &c, int tgt, float *a) {
    for (int i = 0; i < kNumAction; ++i) a[i] = 0.f;
    a[0] = 1.f;    // aIsCard
    a[4] = -1.f;
    a[5] = -1.f;
    a[11] = -1.f;
    fillCardPlayFeatures(bc, c, tgt, a);
}

// Fill just the kNumAction action features (a = action block, not the state block).
// Separated so the policy net can extract the WIDE state once per node and only
// refill this small block per candidate edge (see computeEdgePriors).
void combatFillActionFeatures(const BattleContext &bc, const Action &action, float *a) {
    for (int i = 0; i < kNumAction; ++i) a[i] = 0.f;

    const auto at = action.getActionType();
    a[0] = (at == ActionType::CARD)     ? 1.f : 0.f;   // aIsCard
    a[1] = (at == ActionType::POTION)   ? 1.f : 0.f;   // aIsPotion
    a[2] = (at == ActionType::END_TURN) ? 1.f : 0.f;   // aIsEndTurn
    a[3] = (at == ActionType::SINGLE_CARD_SELECT || at == ActionType::MULTI_CARD_SELECT) ? 1.f : 0.f;
    a[4] = -1.f;   // aCardId
    a[5] = -1.f;   // aCardCost
    a[11] = -1.f;  // aTargetHp

    if (at == ActionType::CARD) {
        const int src = action.getSourceIdx();
        if (src >= 0 && src < bc.cards.cardsInHand)
            fillCardPlayFeatures(bc, bc.cards.hand[src], action.getTargetIdx(), a);
    }

    // §3.5: subset-content features for card select actions (hand/discard/
    // exhaust pools by task; discovery/codex have no CardInstance, size only).
    // a[14..21] default 0 for non-select actions.
    if (at == ActionType::SINGLE_CARD_SELECT || at == ActionType::MULTI_CARD_SELECT) {
        auto poolCard = [&](int idx) -> const CardInstance * {
            if (idx < 0) return nullptr;
            switch (bc.cardSelectInfo.cardSelectTask) {
                case CardSelectTask::EXHAUST_ONE:
                case CardSelectTask::FORETHOUGHT:
                case CardSelectTask::NIGHTMARE:
                case CardSelectTask::RECYCLE:
                case CardSelectTask::SETUP:
                case CardSelectTask::WARCRY:
                case CardSelectTask::ARMAMENTS:
                case CardSelectTask::GAMBLE:
                case CardSelectTask::EXHAUST_MANY:
                    return idx < bc.cards.cardsInHand ? &bc.cards.hand[idx] : nullptr;
                case CardSelectTask::HOLOGRAM:
                case CardSelectTask::LIQUID_MEMORIES_POTION:
                case CardSelectTask::HEADBUTT:
                case CardSelectTask::MEDITATE:
                    return idx < (int)bc.cards.discardPile.size()
                        ? &bc.cards.discardPile[idx] : nullptr;
                case CardSelectTask::EXHUME:
                    return idx < (int)bc.cards.exhaustPile.size()
                        ? &bc.cards.exhaustPile[idx] : nullptr;
                default:
                    return nullptr;
            }
        };

        std::array<int, 10> idxs{};
        int nSel = 0;
        if (at == ActionType::MULTI_CARD_SELECT) {
            const auto sel = action.getSelectedIdxs();
            nSel = sel.size();
            for (int i = 0; i < nSel && i < 10; ++i) idxs[i] = sel[i];
        } else {
            idxs[0] = action.getSelectIdx();
            nSel = 1;
        }
        a[14] = (float)nSel;
        for (int i = 0; i < nSel; ++i) {
            const CardInstance *c = poolCard(idxs[i]);
            if (!c) continue;
            const auto id = c->getId();
            const auto t = c->getType();
            a[15] += (float)c->costForTurn;
            if (t == CardType::ATTACK) a[16] += 1.f;
            if (t == CardType::SKILL)  a[17] += 1.f;
            if (t == CardType::POWER)  a[18] += 1.f;
            if (c->isUpgraded())       a[19] += 1.f;
            a[20] += (float)Expert::getPlayOrdering(id);
            a[21] += (float)Expert::getObtainWeight(id, c->isUpgraded());
        }
    }
}

int combatActionTargetSlot(const BattleContext &bc, const Action &action) {
    // Same condition as aTargetsEnemy in combatFillActionFeatures.
    if (action.getActionType() != ActionType::CARD) return -1;
    const int src = action.getSourceIdx();
    if (src < 0 || src >= bc.cards.cardsInHand) return -1;
    const int tgt = action.getTargetIdx();
    if (tgt >= 0 && tgt < bc.monsters.monsterCount && tgt < kNumMonSlots && bc.monsters.arr[tgt].curHp > 0)
        return tgt;
    return -1;
}

int combatMonsterSlotOffset() { return kMonOff; }

void combatExtractPolicyFeatures(const BattleContext &bc, const Action &action, float *out) {
    combatExtractFeatures(bc, out);                              // state block
    combatFillActionFeatures(bc, action, out + combatFeatureCount());  // action block
}

void combatExtractFeatures(const BattleContext &bc, float *out) {
    const auto &p = bc.player;
    int monAlive = 0, sumHp = 0, maxHp = 0, sumBlk = 0, sumStr = 0, sumArt = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (m.curHp <= 0) continue;
        ++monAlive; sumHp += m.curHp; if (m.curHp > maxHp) maxHp = m.curHp;
        sumBlk += m.block; sumStr += m.strength; sumArt += m.artifact;
    }
    int nAtk = 0, nSkl = 0, nPow = 0, nOth = 0;
    auto tally = [&](const CardInstance &c) {
        switch (c.getType()) {
            case CardType::ATTACK: ++nAtk; break;
            case CardType::POWER:  ++nPow; break;
            case CardType::SKILL:  ++nSkl; break;
            default:               ++nOth; break;
        }
    };
    for (int i = 0; i < bc.cards.cardsInHand; ++i) tally(bc.cards.hand[i]);
    for (const auto &c : bc.cards.drawPile)    tally(c);
    for (const auto &c : bc.cards.discardPile) tally(c);

    int k = 0;
    out[k++] = (float)bc.ascension;
    out[k++] = (float)(int)bc.encounter;
    out[k++] = (float)bc.turn;
    out[k++] = (float)p.curHp;
    out[k++] = (float)p.maxHp;
    out[k++] = (float)p.block;
    out[k++] = (float)p.energy;
    out[k++] = (float)p.strength;
    out[k++] = (float)p.dexterity;
    out[k++] = (float)p.focus;
    out[k++] = (float)(int)p.artifact;
    out[k++] = (float)monAlive;
    out[k++] = (float)sumHp;
    out[k++] = (float)maxHp;
    out[k++] = (float)sumBlk;
    out[k++] = (float)sumStr;
    out[k++] = (float)sumArt;
    out[k++] = (float)bc.cards.cardsInHand;
    out[k++] = (float)bc.cards.drawPile.size();
    out[k++] = (float)bc.cards.discardPile.size();
    out[k++] = (float)bc.cards.exhaustPile.size();
    out[k++] = (float)nAtk;
    out[k++] = (float)nSkl;
    out[k++] = (float)nPow;
    out[k++] = (float)nOth;
    out[k++] = (float)bc.potionCount;
    const bool activeOnly = activePowerFeatures();
    for (const auto &pf : kPowers) out[k++] = (float)powerVal(p, pf.status, activeOnly);

    // ---- rich context: relics + per-pile card-id counts (only when read) ----
    if (!g_richCombatFeatures) return;   // narrow fast path: legacy nets don't read these
    // zero the relic+card region, then fill (piles are small, ids are sparse).
    for (int i = kRelicOff; i < kStateCount; ++i) out[i] = 0.f;
    for (int r = 0; r < kNumRelics; ++r)
        if (p.hasRelicRuntime((RelicId)r)) out[kRelicOff + r] = 1.f;
    auto bump = [&](int base, const CardInstance &c) {
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCards) out[base + id] += 1.f;
    };
    for (int i = 0; i < bc.cards.cardsInHand; ++i) bump(kHandOff, bc.cards.hand[i]);
    for (const auto &c : bc.cards.drawPile)    bump(kDrawOff, c);
    for (const auto &c : bc.cards.discardPile) bump(kDiscOff, c);
    for (const auto &c : bc.cards.exhaustPile) bump(kExhOff,  c);

    // enemy detail: incoming damage (what the player faces next turn) + per-monster
    int incoming = 0, nAttacking = 0;
    for (int i = 0; i < kNumMonSlots; ++i) {
        const int b = kMonOff + i * kMonFeats;
        if (i >= bc.monsters.monsterCount || bc.monsters.arr[i].curHp <= 0) { out[b] = -1.f; continue; }
        const auto &mm = bc.monsters.arr[i];
        int idmg = 0;
        const bool atk = mm.isAttacking();
        if (atk) idmg=mm.publicIncomingDamage(bc);
        out[b+0] = (float)(int)mm.id;
        out[b+1] = (float)mm.curHp;
        out[b+2] = (float)mm.block;
        out[b+3] = (float)mm.getStatus<MonsterStatus::STRENGTH>();
        out[b+4] = (float)idmg;
        out[b+5] = atk ? 1.f : 0.f;
        out[b+6] = (float)mm.getStatus<MonsterStatus::VULNERABLE>();
        out[b+7] = (float)mm.getStatus<MonsterStatus::WEAK>();
        out[b+8] = (float)mm.getStatus<MonsterStatus::POISON>();
        incoming += idmg; nAttacking += atk ? 1 : 0;
    }
    out[kEnemyAggOff]   = (float)incoming;
    out[kEnemyAggOff+1] = (float)nAttacking;

    // potions held, by id (slots hold Potion::EMPTY_POTION_SLOT when empty; real ids >= 2)
    for (int i = 0; i < bc.potionCapacity && i < (int)bc.potions.size(); ++i) {
        const int pid = (int)bc.potions[i];
        if (pid >= 2 && pid < kNumPotions) out[kPotOff + pid] += 1.f;
    }

    // misc player context
    out[kMiscOff+0] = (float)p.gold;
    out[kMiscOff+1] = (float)bc.potionCapacity;
    out[kMiscOff+2] = (float)p.cardsPlayedThisTurn;
    out[kMiscOff+3] = (float)p.attacksPlayedThisTurn;
    out[kMiscOff+4] = (float)p.skillsPlayedThisTurn;
    out[kRelicCtrOff+0] = (float)p.happyFlowerCounter;
    out[kRelicCtrOff+1] = (float)p.incenseBurnerCounter;
    out[kRelicCtrOff+2] = (float)p.inkBottleCounter;
    out[kRelicCtrOff+3] = (float)p.inserterCounter;
    out[kRelicCtrOff+4] = (float)p.nunchakuCounter;
    out[kRelicCtrOff+5] = (float)p.penNibCounter;
    out[kRelicCtrOff+6] = (float)p.sundialCounter;
    out[kRelicCtrOff+7] = (float)p.panacheCounter;
}

bool CombatValueNet::load(const std::string &path) {
    std::ifstream f(path);
    if (!f) return false;
    std::string tok;
    isLoaded = false;
    isMlp = false;
    isSparseMlp = false;
    isEntity = false;
    isEntityPolicy = false;
    isDeepSets = false;
    encounterModels.clear();
    hasEncounterModels = false;
    trees.clear(); sel.clear(); flatNodes.clear(); flatRoots.clear();
    quantileTrees.clear(); quantileBase.clear(); nQuantiles = 0;
    xMean.clear(); xInvStd.clear(); w1.clear(); b1.clear();
    w2.clear(); b2.clear(); w3.clear();
    h1 = h2 = 0; b3 = 0.f; yMean = 0.f; yScale = 1.f;
    entityWinBonus = entityWinB = entityHpB = 0.f;
    entityScalarSel.clear(); entityScalarMean.clear(); entityScalarInv.clear();
    entityMonMean.clear(); entityMonInv.clear(); entityCard.clear(); entityRelic.clear();
    entityPotion.clear(); entityEncounter.clear(); entityMonsterId.clear(); entityIntent.clear();
    entityMonsterW.clear(); entityMonsterB.clear(); entityTrunk1W.clear(); entityTrunk1B.clear();
    entityTrunk2W.clear(); entityTrunk2B.clear(); entityWinW.clear(); entityHpW.clear();
    policyScalarSel.clear(); policyActionScalarSel.clear();
    policyScalarMean.clear(); policyScalarInv.clear(); policyMonMean.clear(); policyMonInv.clear();
    policyActionMean.clear(); policyActionInv.clear(); policyCard.clear(); policyRelic.clear();
    policyPotion.clear(); policyEncounter.clear(); policyMonsterId.clear(); policyIntent.clear();
    policyMonsterW.clear(); policyMonsterB.clear(); policyStateW.clear(); policyStateB.clear();
    policyActionCard.clear(); policyActionW.clear(); policyActionB.clear(); policyActionBiasW.clear();
    policyActionBiasB = 0.f;
    d_card = d_relic = d_pot = d_mon = d_enc = d_scalar = 0;
    encIdx = 1; nEncounter = 128;
    dsScalarMean.clear(); dsScalarInv.clear(); dsScalarW.clear(); dsScalarB.clear();
    dsScalarSel.clear();
    dsCardE.clear(); dsRelicE.clear(); dsPotionE.clear(); dsEncE.clear();
    dsMonW1.clear(); dsMonB1.clear(); dsMonW2.clear(); dsMonB2.clear();

    isPolicyMlp = false;
    pmH1 = pmH2 = 0; pmB3 = 0.f;
    pmStateW.clear(); pmActionW.clear(); pmCard.clear(); pmTargetW.clear();
    pmB1.clear(); pmW2.clear(); pmW2T.clear(); pmB2.clear(); pmW3.clear();
    pmEnc.clear(); pmMonId.clear(); pmMonDmg.clear();

    f >> tok;
    int nfeat = 0;
    if (tok == "combat_policy_mlp_v1" || tok == "combat_policy_mlp_v2") {
        const bool v2 = tok == "combat_policy_mlp_v2";
        // tools/silver_az_mlp.py export. The feature list must equal the
        // canonical policy layout exactly (state block, then action block).
        auto readVec = [&](const char *want, std::vector<float> &v, std::size_t n) {
            f >> tok; if (tok != want) return false;
            v.resize(n); for (float &x : v) f >> x; return bool(f);
        };
        int ns = 0, na = 0, nc = 0, nt = 0;
        f >> tok >> pmH1; if (tok != "h1" || pmH1 < 1) return false;
        f >> tok >> pmH2; if (tok != "h2" || pmH2 < 1) return false;
        f >> tok >> ns; if (tok != "nstate" || ns != kStateCount) return false;
        f >> tok >> na; if (tok != "naction" || na != kNumAction) return false;
        f >> tok >> nc; if (tok != "ncard" || nc != kNumCards + 1) return false;
        f >> tok >> nt; if (tok != "ntarget" || nt != kMonFeats) return false;
        const auto &canon = combatPolicyFeatureNames();
        for (int i = 0; i < ns + na; ++i) {
            std::string name; f >> tok >> name;
            if (tok != "feat" || name != canon[i]) return false;
        }
        const std::size_t H1 = pmH1, H2 = pmH2;
        std::vector<float> one;
        if (!readVec("state_w", pmStateW, ns * H1) || !readVec("action_w", pmActionW, na * H1)
                || !readVec("card", pmCard, nc * H1) || !readVec("target_w", pmTargetW, nt * H1)
                || !readVec("b1", pmB1, H1) || !readVec("w2", pmW2, H2 * H1)
                || !readVec("b2", pmB2, H2) || !readVec("w3", pmW3, H2)
                || !readVec("b3", one, 1)) return false;
        pmB3 = one[0];
        if (!f) return false;
        // combat_policy_mlp_v2 (silver-prior-arch, 2026-10-14) appends optional
        // tables `enc N`, `mon_id N`, `mon_dmg N` (N x h1, embedding projection
        // folded in). The new header keeps older loaders from reading such a
        // file as v1 and silently dropping the tables; v1 files must end at b3.
        while (f >> tok) {
            std::vector<float> *dst = tok == "enc" ? &pmEnc : tok == "mon_id" ? &pmMonId
                                    : tok == "mon_dmg" ? &pmMonDmg : nullptr;
            int rows = 0;
            if (!v2 || !dst || !(f >> rows) || rows != kPolicyMlpEmbRows || !dst->empty()) return false;
            dst->resize((std::size_t)rows * H1);
            for (float &x : *dst) f >> x;
            if (!f) return false;
        }
        // Layer 2 runs input-major (axpy over active h1 units), which -O3
        // vectorizes without reassociating a float reduction.
        pmW2T.resize(H1 * H2);
        for (std::size_t i = 0; i < H2; ++i)
            for (std::size_t j = 0; j < H1; ++j) pmW2T[j * H2 + i] = pmW2[i * H1 + j];
        isPolicyMlp = true;
        isPolicy = true;
        g_richCombatFeatures = true;
        isLoaded = true;
        this->path = path;
        return true;
    } else if (tok == "combat_policy_entity_v1") {
        isEntityPolicy = true;
        isPolicy = true;
        auto readVec = [&](const char *want, std::vector<float> &v, std::size_t n) {
            f >> tok; if (tok != want) return false;
            v.resize(n); for (float &x : v) f >> x; return bool(f);
        };
        const auto &canon = combatPolicyFeatureNames();
        std::unordered_map<std::string,int> canonIdx;
        for (int i = 0; i < (int)canon.size(); ++i) canonIdx[canon[i]] = i;
        int ns = 0; f >> tok >> ns;
        if (tok != "nscalar" || ns != 64) return false;
        policyScalarSel.resize(ns);
        for (int i = 0; i < ns; ++i) {
            std::string name; f >> tok >> name; if (tok != "scalar") return false;
            auto it = canonIdx.find(name); if (it == canonIdx.end()) return false;
            policyScalarSel[i] = it->second;
        }
        int na = 0; f >> tok >> na;
        if (tok != "nactionscalar" || na != 13) return false;
        policyActionScalarSel.resize(na);
        for (int i = 0; i < na; ++i) {
            std::string name; f >> tok >> name; if (tok != "action_scalar") return false;
            auto it = canonIdx.find(name); if (it == canonIdx.end()) return false;
            policyActionScalarSel[i] = it->second;
        }
        if (!readVec("scalar_mean", policyScalarMean, 64)
                || !readVec("scalar_inv", policyScalarInv, 64)
                || !readVec("mon_mean", policyMonMean, 7)
                || !readVec("mon_inv", policyMonInv, 7)
                || !readVec("action_mean", policyActionMean, 13)
                || !readVec("action_inv", policyActionInv, 13)
                || !readVec("card", policyCard, 4*371*12)
                || !readVec("relic", policyRelic, 128*8)
                || !readVec("potion", policyPotion, 44*4)
                || !readVec("encounter_weight", policyEncounter, 128*8)
                || !readVec("monster_id_weight", policyMonsterId, 256*12)
                || !readVec("intent_weight", policyIntent, 32*4)
                || !readVec("monster_0_weight", policyMonsterW, 24*23)
                || !readVec("monster_0_bias", policyMonsterB, 24)
                || !readVec("state_0_weight", policyStateW, 64*180)
                || !readVec("state_0_bias", policyStateB, 64)
                || !readVec("action_card_weight", policyActionCard, 371*16)
                || !readVec("action_0_weight", policyActionW, 64*29)
                || !readVec("action_0_bias", policyActionB, 64)
                || !readVec("action_bias_weight", policyActionBiasW, 29)) return false;
        std::vector<float> one;
        if (!readVec("action_bias_bias", one, 1)) return false;
        policyActionBiasB = one[0];
        if (!f) return false;
        g_richCombatFeatures = true;
        isLoaded = true;
        this->path = path;
        return true;
    } else if (tok == "combat_entity_v1") {
        isEntity = true;
        auto readVec = [&](const char *want, std::vector<float> &v, std::size_t n) {
            f >> tok; if (tok != want) return false;
            v.resize(n); for (float &x : v) f >> x; return bool(f);
        };
        f >> tok >> entityWinBonus; if (tok != "win_bonus") return false;
        int ns = 0; f >> tok >> ns; if (tok != "nscalar" || ns != 64) return false;
        const auto &canon = combatFeatureNames();
        std::unordered_map<std::string,int> canonIdx;
        for (int i = 0; i < (int)canon.size(); ++i) canonIdx[canon[i]] = i;
        entityScalarSel.resize(ns);
        for (int i = 0; i < ns; ++i) {
            std::string name; f >> tok >> name; if (tok != "scalar") return false;
            auto it = canonIdx.find(name); if (it == canonIdx.end()) return false;
            entityScalarSel[i] = it->second;
        }
        if (!readVec("scalar_mean", entityScalarMean, 64)
                || !readVec("scalar_inv", entityScalarInv, 64)
                || !readVec("mon_mean", entityMonMean, 7)
                || !readVec("mon_inv", entityMonInv, 7)
                || !readVec("card", entityCard, 4*371*16)
                || !readVec("relic", entityRelic, 128*8)
                || !readVec("potion", entityPotion, 44*4)
                || !readVec("encounter_weight", entityEncounter, 128*8)
                || !readVec("monster_id_weight", entityMonsterId, 256*12)
                || !readVec("intent_weight", entityIntent, 32*4)
                || !readVec("monster_0_weight", entityMonsterW, 32*23)
                || !readVec("monster_0_bias", entityMonsterB, 32)
                || !readVec("trunk_0_weight", entityTrunk1W, 128*212)
                || !readVec("trunk_0_bias", entityTrunk1B, 128)
                || !readVec("trunk_2_weight", entityTrunk2W, 64*128)
                || !readVec("trunk_2_bias", entityTrunk2B, 64)
                || !readVec("win_weight", entityWinW, 64)) return false;
        std::vector<float> one;
        if (!readVec("win_bias", one, 1)) return false; entityWinB = one[0];
        if (!readVec("hp_weight", entityHpW, 64)
                || !readVec("hp_bias", one, 1)) return false; entityHpB = one[0];
        if (!f) return false;
        g_richCombatFeatures = true;
        isLoaded = true;
        this->path = path;
        return true;
    } else if (tok == "combat_mlp_v1" || tok == "combat_mlp_sparse_v1") {
        isMlp = true;
        isSparseMlp = tok == "combat_mlp_sparse_v1";
        f >> tok >> nfeat;                   // "nfeat <k>"
    } else if (tok == "combat_mlp_meta_v1") {  // Reptile meta-learned MLP + per-encounter deltas
        isMlp = true;                        // dense layout (x_mean/x_invstd) + delta table
        isSparseMlp = false;
        f >> tok >> nfeat;                   // "nfeat <k>"
    } else if (tok == "combat_quantile_v1") {  // §132: quantile regression over R = 0 | 50+endHp
        f >> tok; if (tok != "nquantiles") return false;
        f >> nQuantiles;
        if (nQuantiles <= 0 || nQuantiles > 20) return false;
        f >> tok; if (tok != "nfeat") return false;
        f >> nfeat;                          // "nfeat <k>"
    } else if (tok == "combat_deepsets_v1") {
        isDeepSets = true;
        g_richCombatFeatures = true;
        // Read dimensions
        f >> tok >> d_card;   if (tok != "d_card"   || d_card   <= 0) return false;
        f >> tok >> d_relic;  if (tok != "d_relic"  || d_relic  <= 0) return false;
        f >> tok >> d_pot;    if (tok != "d_pot"    || d_pot    <= 0) return false;
        f >> tok >> d_mon;    if (tok != "d_mon"    || d_mon    <= 0) return false;
        f >> tok >> d_enc;    if (tok != "d_enc"    || d_enc    <= 0) return false;
        f >> tok >> d_scalar; if (tok != "d_scalar" || d_scalar <= 0) return false;
        f >> tok >> h1;       if (tok != "h1"       || h1       <= 0) return false;
        f >> tok >> h2;       if (tok != "h2"       || h2       <= 0) return false;
        f >> tok >> encIdx;   if (tok != "encounter_idx") return false;
        f >> tok >> nEncounter; if (tok != "n_encounter" || nEncounter <= 0) return false;
        int ns = 0;
        f >> tok >> ns;       if (tok != "nscalar" || ns <= 0) return false;

        auto readVec = [&](const char *want, std::vector<float> &v, std::size_t n) {
            f >> tok; if (tok != want) return false;
            v.resize(n); for (float &x : v) f >> x; return bool(f);
        };
        auto readIVec = [&](const char *want, std::vector<int> &v, std::size_t n) {
            f >> tok; if (tok != want) return false;
            v.resize(n); for (int &x : v) f >> x; return bool(f);
        };

        if (!readIVec("scalar_sel", dsScalarSel, ns)) return false;
        if (!readVec("scalar_mean", dsScalarMean, ns)) return false;
        if (!readVec("scalar_inv", dsScalarInv, ns)) return false;
        if (!readVec("scalar_w", dsScalarW, (std::size_t)d_scalar * ns)) return false;
        if (!readVec("scalar_b", dsScalarB, d_scalar)) return false;
        if (!readVec("card_embed", dsCardE, (std::size_t)kNumCards * d_card)) return false;
        if (!readVec("relic_embed", dsRelicE, (std::size_t)kNumRelics * d_relic)) return false;
        if (!readVec("potion_embed", dsPotionE, (std::size_t)kNumPotions * d_pot)) return false;
        if (!readVec("encounter_embed", dsEncE, (std::size_t)nEncounter * d_enc)) return false;
        if (!readVec("mon_w1", dsMonW1, (std::size_t)d_mon * kMonFeats)) return false;
        if (!readVec("mon_b1", dsMonB1, d_mon)) return false;
        if (!readVec("mon_w2", dsMonW2, (std::size_t)d_mon * d_mon)) return false;
        if (!readVec("mon_b2", dsMonB2, d_mon)) return false;
        // MLP head: w1, b1, w2, b2, w3, b3
        if (!readVec("w1", w1, (std::size_t)h1 * (4*d_card + d_relic + d_pot + d_mon + d_enc + d_scalar))) return false;
        if (!readVec("b1", b1, h1)) return false;
        if (!readVec("w2", w2, (std::size_t)h2 * h1)) return false;
        if (!readVec("b2", b2, h2)) return false;
        if (!readVec("w3", w3, h2)) return false;
        std::vector<float> one;
        if (!readVec("b3", one, 1)) return false;
        b3 = one[0];
        f >> tok >> yMean;   if (tok != "y_mean") return false;
        f >> tok >> yScale;  if (tok != "y_scale" || yScale <= 0.f) return false;
        if (!f) return false;
        isLoaded = true;
        this->path = path;
        return true;
    } else if (tok == "nfeat") {
        f >> nfeat;                          // legacy tree model
    } else if (tok == "combat_policy_trees_v1") {
        // Tree ensemble over the POLICY layout (state ++ action), e.g. the
        // synthetic Silver root prior (tools/silver_synth_gates.py export).
        isPolicy = true;
        f >> tok >> nfeat;
        if (tok != "nfeat") return false;
    } else {
        return false;
    }
    std::vector<std::string> modelFeats(nfeat);
    for (int i = 0; i < nfeat; ++i) { f >> tok >> modelFeats[i]; }   // "feat <name>"

    // map model feature index -> canonical index
    const auto &canon = isPolicy ? combatPolicyFeatureNames() : combatFeatureNames();
    std::unordered_map<std::string,int> canonIdx;
    for (int i = 0; i < (int)canon.size(); ++i) canonIdx[canon[i]] = i;
    sel.assign(nfeat, -1);
    for (int i = 0; i < nfeat; ++i) {
        auto it = canonIdx.find(modelFeats[i]);
        if (it == canonIdx.end()) return false;   // model wants a feature we don't produce
        sel[i] = it->second;
        // if this model reads any rich state feature (relic/card-location block,
        // canonical indices [kRelicOff, kStateCount)), the wide block must be filled.
        if (sel[i] >= kRelicOff && sel[i] < kStateCount) g_richCombatFeatures = true;
    }

    if (isMlp) {
        auto readVec = [&](const char *want, std::vector<float> &v, std::size_t n) {
            f >> tok;
            if (tok != want) return false;
            v.resize(n);
            for (float &x : v) f >> x;
            return bool(f);
        };
        if (!isSparseMlp && (!readVec("x_mean", xMean, nfeat)
                || !readVec("x_invstd", xInvStd, nfeat))) return false;
        f >> tok >> yMean; if (tok != "y_mean") return false;
        f >> tok >> yScale; if (tok != "y_scale") return false;
        f >> tok >> h1; if (tok != "h1" || h1 < 1) return false;
        if (!readVec("w1", w1, std::size_t(h1) * nfeat)
                || !readVec("b1", b1, h1)) return false;
        f >> tok >> h2; if (tok != "h2" || h2 < 1) return false;
        if (!readVec("w2", w2, std::size_t(h2) * h1)
                || !readVec("b2", b2, h2)
                || !readVec("w3", w3, h2)) return false;
        f >> tok >> b3; if (tok != "b3" || !f) return false;
        // combat_mlp_meta_v1: optional per-encounter delta table. Adapted weights
        // are base + delta, stored as fully self-contained per-encounter MLP
        // instances in encounterModels so predict(bc) can dispatch on the
        // encounter without touching the base weights.
        if (f >> tok) {
            if (tok != "n_encounter_deltas") return false;
            int nd = 0;
            f >> nd;
            if (nd < 0 || nd > 128) return false;
            constexpr int kNumEncounters = sizeof(monsterEncounterEnumNames)
                / sizeof(monsterEncounterEnumNames[0]);
            for (int d = 0; d < nd; ++d) {
                std::string name;
                f >> tok >> name;
                if (tok != "encounter") return false;
                int enc = -1;
                for (int e = 0; e < kNumEncounters; ++e)
                    if (name == monsterEncounterEnumNames[e]) { enc = e; break; }
                if (enc < 0) return false;   // unknown encounter name
                std::vector<float> dw1, db1, dw2, db2, dw3;
                float db3 = 0.f;
                if (!readVec("dw1", dw1, std::size_t(h1) * nfeat)
                        || !readVec("db1", db1, h1)
                        || !readVec("dw2", dw2, std::size_t(h2) * h1)
                        || !readVec("db2", db2, h2)
                        || !readVec("dw3", dw3, h2)) return false;
                f >> tok >> db3;
                if (tok != "db3" || !f) return false;
                CombatValueNet m;
                m.isMlp = true;
                m.isSparseMlp = false;
                m.isLoaded = true;
                m.isPolicy = isPolicy;
                m.sel = sel;
                m.xMean = xMean; m.xInvStd = xInvStd;
                m.h1 = h1; m.h2 = h2;
                m.yMean = yMean; m.yScale = yScale;
                m.b3 = b3 + db3;
                m.w1.resize(w1.size()); m.b1.resize(b1.size());
                m.w2.resize(w2.size()); m.b2.resize(b2.size());
                m.w3.resize(w3.size());
                for (std::size_t i = 0; i < w1.size(); ++i) m.w1[i] = w1[i] + dw1[i];
                for (std::size_t i = 0; i < b1.size(); ++i) m.b1[i] = b1[i] + db1[i];
                for (std::size_t i = 0; i < w2.size(); ++i) m.w2[i] = w2[i] + dw2[i];
                for (std::size_t i = 0; i < b2.size(); ++i) m.b2[i] = b2[i] + db2[i];
                for (std::size_t i = 0; i < w3.size(); ++i) m.w3[i] = w3[i] + dw3[i];
                encounterModels[enc] = std::move(m);
            }
            hasEncounterModels = nd > 0;
        }
        isLoaded = true;
        this->path = path;
        return true;
    }

    auto readTrees = [&](std::vector<std::vector<Node>> &out, float &bs) -> bool {
        f >> tok; if (tok != "base_score") return false;
        f >> bs;
        int ntrees = 0;
        f >> tok; if (tok != "ntrees") return false;
        f >> ntrees;
        out.assign(ntrees, {});
        for (int t = 0; t < ntrees; ++t) {
            int idx = 0, nnodes = 0;
            f >> tok; if (tok != "tree") return false;
            f >> idx >> nnodes;
            auto &nodes = out[t];
            nodes.resize(nnodes);
            for (int n = 0; n < nnodes; ++n) {
                f >> tok;
                if (tok == "L") {
                    float v; f >> v;
                    nodes[n] = { -1, v, -1, -1 };
                } else {  // "S <featIdx> <thresh> <yes> <no>"
                    int fi, yes, no; float th;
                    f >> fi >> th >> yes >> no;
                    nodes[n] = { fi, th, yes, no };
                }
            }
        }
        return bool(f);
    };
    if (nQuantiles > 0) {
        quantileBase.resize(nQuantiles);
        quantileTrees.resize(nQuantiles);
        for (int q = 0; q < nQuantiles; ++q)
            if (!readTrees(quantileTrees[q], quantileBase[q])) return false;
    } else {
        if (!readTrees(trees, baseScore)) return false;
    }
    if (!f) return false;
    flatNodes.clear(); flatRoots.clear();
    if (isPolicy && !trees.empty()) {
        // Re-lay each tree so a split's two children are adjacent (yes, then
        // no): the walk becomes left + !(x < thresh), as predictVec branches.
        // Requires children after their parent (bounded walks, no step guard),
        // feature indices and tree sizes that fit the compact node.
        bool ok = true;
        for (const auto &nodes : trees) {
            const int size = (int)nodes.size();
            if (size < 1 || size > 65535) { ok = false; break; }
            const int base = (int)flatNodes.size();
            flatRoots.push_back(base);
            flatNodes.resize(base + size);
            std::vector<std::pair<int, int>> queue{{0, 0}};   // (source node, local slot)
            int next = 1;
            for (std::size_t q = 0; q < queue.size() && ok; ++q) {
                const auto [n, slot] = queue[q];
                const auto &node = nodes[n];
                auto &flat = flatNodes[base + slot];
                flat.thresh = node.thresh;
                if (node.featIdx < 0) { flat.feat = -1; flat.left = 0; continue; }
                if (node.featIdx >= (int)sel.size() || sel[node.featIdx] > 32767
                        || node.yes <= n || node.no <= n || node.yes >= size || node.no >= size
                        || next + 1 >= size) { ok = false; break; }
                flat.feat = (std::int16_t)sel[node.featIdx];
                flat.left = (std::uint16_t)next;
                queue.push_back({node.yes, next});
                queue.push_back({node.no, next + 1});
                next += 2;
            }
            if (!ok) break;
        }
        if (!ok) { flatNodes.clear(); flatRoots.clear(); }
    }
    isLoaded = true;
    this->path = path;
    return true;
}

// Load <dir>/<ENUM_NAME>.txt per-encounter compact-tree models. Names come from
// monsterEncounterEnumNames[]; any file present is loaded and keyed by its enum
// int. <dir>/_pooled.txt (when present) replaces this object's base weights as
// the non-specialized fallback; otherwise the previously loaded base is kept.
// A missing dir / no files leaves per-encounter dispatch off and returns false;
// a partial load (any present file that fails to load) is rejected wholesale.
// All files are validated into temporaries first and this object is mutated only
// on full success, so a corrupt per-encounter file or pooled fallback can never
// destroy an already-loaded base model (e.g. the STS_VNET model).
bool CombatValueNet::loadEncounterModels(const std::string &dir) {
    auto fileExists = [](const std::string &p) {
        std::ifstream f(p);
        return f.good();
    };
    CombatValueNet pooledBase;      // staged _pooled.txt replacement base
    bool havePooled = false;
    const std::string pooled = dir + "/_pooled.txt";
    if (fileExists(pooled)) {
        if (!pooledBase.load(pooled)) return false;   // this untouched on failure
        havePooled = true;
    }
    std::unordered_map<int, CombatValueNet> newMap;
    constexpr int kNumEncounters = sizeof(monsterEncounterEnumNames)
        / sizeof(monsterEncounterEnumNames[0]);
    for (int enc = 0; enc < kNumEncounters; ++enc) {
        const std::string path = dir + "/" + monsterEncounterEnumNames[enc] + ".txt";
        if (!fileExists(path)) continue;
        CombatValueNet m;
        if (!m.load(path)) return false;   // this untouched on failure
        newMap[enc] = std::move(m);
    }
    if (newMap.empty()) return false;   // nothing specialized
    // Commit atomically: swap in the pooled base (when present) and the map.
    if (havePooled) *this = std::move(pooledBase);
    encounterModels = std::move(newMap);
    hasEncounterModels = true;
    return true;
}

void CombatValueNet::encodePolicyStateVec(const float *canonFeatures, float *state64) const {
    float z[180] = {};
    for (int i = 0; i < 64; ++i)
        z[i] = (canonFeatures[policyScalarSel[i]] - policyScalarMean[i]) * policyScalarInv[i];

    int off = 64;
    const int zoneOff[4] = {kHandOff, kDrawOff, kDiscOff, kExhOff};
    for (int zone = 0; zone < 4; ++zone) {
        for (int card = 0; card < 371; ++card) {
            const float count = canonFeatures[zoneOff[zone] + card];
            if (count == 0.f) continue;
            const float *e = policyCard.data() + (zone*371 + card)*12;
            for (int j = 0; j < 12; ++j) z[off + zone*12 + j] += count*e[j];
        }
    }
    off += 48;
    for (int id = 0; id < 128; ++id) {
        const float count = canonFeatures[kRelicOff + id];
        if (count == 0.f) continue;
        const float *e = policyRelic.data() + id*8;
        for (int j = 0; j < 8; ++j) z[off+j] += count*e[j];
    }
    off += 8;
    for (int id = 0; id < 44; ++id) {
        const float count = canonFeatures[kPotOff + id];
        if (count == 0.f) continue;
        const float *e = policyPotion.data() + id*4;
        for (int j = 0; j < 4; ++j) z[off+j] += count*e[j];
    }
    off += 4;
    const int enc = std::max(0, std::min(127, int(canonFeatures[1])));
    std::copy_n(policyEncounter.data()+enc*8, 8, z+off);
    off += 8;

    float *monSum = z+off;
    float *monMax = z+off+24;
    std::fill(monMax, monMax+24, -1e30f);
    bool anyMon = false;
    const int contIdx[7] = {1,2,3,5,6,7,8};
    for (int slot = 0; slot < 5; ++slot) {
        const float *m = canonFeatures + kMonOff + slot*9;
        if (m[1] <= 0.f) continue;
        anyMon = true;
        const int mid = std::max(0, std::min(255, int(m[0])));
        const int intent = std::max(0, std::min(31, int(m[4])));
        float minput[23];
        std::copy_n(policyMonsterId.data()+mid*12, 12, minput);
        std::copy_n(policyIntent.data()+intent*4, 4, minput+12);
        for (int j = 0; j < 7; ++j)
            minput[16+j] = (m[contIdx[j]]-policyMonMean[j])*policyMonInv[j];
        for (int j = 0; j < 24; ++j) {
            const float *w = policyMonsterW.data()+j*23;
            float sum = policyMonsterB[j];
            for (int i = 0; i < 23; ++i) sum += w[i]*minput[i];
            const float v = sum > 0.f ? sum : 0.f;
            monSum[j] += v;
            if (v > monMax[j]) monMax[j] = v;
        }
    }
    if (!anyMon) std::fill(monMax, monMax+24, 0.f);

    for (int j = 0; j < 64; ++j) {
        const float *w = policyStateW.data()+j*180;
        float sum = policyStateB[j];
        for (int i = 0; i < 180; ++i) sum += w[i]*z[i];
        state64[j] = sum > 0.f ? sum : 0.f;
    }
}

double CombatValueNet::predictPolicyActionVec(const float *canonFeatures,
                                              const float *state64) const {
    float a[29];
    for (int i = 0; i < 13; ++i)
        a[i] = (canonFeatures[policyActionScalarSel[i]] - policyActionMean[i]) * policyActionInv[i];
    std::fill(a+13, a+29, 0.f);
    const int card = int(canonFeatures[kStateCount + 4]); // aCardId in the canonical action block
    if (card >= 0 && card < 371)
        std::copy_n(policyActionCard.data()+card*16, 16, a+13);

    float score = policyActionBiasB;
    for (int i = 0; i < 29; ++i) score += policyActionBiasW[i]*a[i];
    for (int j = 0; j < 64; ++j) {
        const float *w = policyActionW.data()+j*29;
        float sum = policyActionB[j];
        for (int i = 0; i < 29; ++i) sum += w[i]*a[i];
        const float ah = sum > 0.f ? sum : 0.f;
        score += state64[j]*ah/8.f;
    }
    return score;
}

CombatOutcomePrediction CombatValueNet::predictOutcomeVec(const float *canonFeatures) const {
    if (isEntityPolicy) {
        return {};
    }
    if (isEntity) {
        thread_local std::vector<float> z(212), minput(23), mhidden(32), a1e(128), a2e(64);
        std::fill(z.begin(), z.end(), 0.f);
        for (int i = 0; i < 64; ++i)
            z[i] = (canonFeatures[entityScalarSel[i]] - entityScalarMean[i]) * entityScalarInv[i];
        int off = 64;
        const int zoneOff[4] = {kHandOff, kDrawOff, kDiscOff, kExhOff};
        for (int zone = 0; zone < 4; ++zone) {
            for (int card = 0; card < 371; ++card) {
                const float count = canonFeatures[zoneOff[zone] + card];
                if (count == 0.f) continue;
                const float *e = entityCard.data() + (zone*371 + card)*16;
                for (int j = 0; j < 16; ++j) z[off + zone*16 + j] += count*e[j];
            }
        }
        off += 64;
        for (int id = 0; id < 128; ++id) {
            const float count = canonFeatures[kRelicOff + id]; if (count == 0.f) continue;
            const float *e = entityRelic.data() + id*8;
            for (int j = 0; j < 8; ++j) z[off+j] += count*e[j];
        }
        off += 8;
        for (int id = 0; id < 44; ++id) {
            const float count = canonFeatures[kPotOff + id]; if (count == 0.f) continue;
            const float *e = entityPotion.data() + id*4;
            for (int j = 0; j < 4; ++j) z[off+j] += count*e[j];
        }
        off += 4;
        const int enc = std::max(0, std::min(127, int(canonFeatures[1])));
        std::copy_n(entityEncounter.data()+enc*8, 8, z.data()+off); off += 8;
        float *monSum = z.data()+off, *monMax = z.data()+off+32;
        std::fill(monMax, monMax+32, -1e30f); bool anyMon = false;
        const int contIdx[7] = {1,2,3,5,6,7,8};
        for (int slot = 0; slot < 5; ++slot) {
            const float *m = canonFeatures + kMonOff + slot*9;
            if (m[1] <= 0.f) continue;
            anyMon = true;
            const int mid = std::max(0, std::min(255, int(m[0])));
            const int intent = std::max(0, std::min(31, int(m[4])));
            std::copy_n(entityMonsterId.data()+mid*12, 12, minput.data());
            std::copy_n(entityIntent.data()+intent*4, 4, minput.data()+12);
            for (int j = 0; j < 7; ++j)
                minput[16+j] = (m[contIdx[j]]-entityMonMean[j])*entityMonInv[j];
            for (int j = 0; j < 32; ++j) {
                const float *w = entityMonsterW.data()+j*23; float sum = entityMonsterB[j];
                for (int i = 0; i < 23; ++i) sum += w[i]*minput[i];
                const float v = sum > 0.f ? sum : 0.f; mhidden[j] = v;
                monSum[j] += v; if (v > monMax[j]) monMax[j] = v;
            }
        }
        if (!anyMon) std::fill(monMax, monMax+32, 0.f);
        for (int j = 0; j < 128; ++j) {
            const float *w = entityTrunk1W.data()+j*212; float sum = entityTrunk1B[j];
            for (int i = 0; i < 212; ++i) sum += w[i]*z[i];
            a1e[j] = sum > 0.f ? sum : 0.f;
        }
        for (int j = 0; j < 64; ++j) {
            const float *w = entityTrunk2W.data()+j*128; float sum = entityTrunk2B[j];
            for (int i = 0; i < 128; ++i) sum += w[i]*a1e[i];
            a2e[j] = sum > 0.f ? sum : 0.f;
        }
        float wl = entityWinB, hl = entityHpB;
        for (int i = 0; i < 64; ++i) { wl += entityWinW[i]*a2e[i]; hl += entityHpW[i]*a2e[i]; }
        const float p = 1.f/(1.f+std::exp(-wl)), h = 1.f/(1.f+std::exp(-hl));
        return {p, h};
    }
    return {};
}

double CombatValueNet::predictVec(const float *canonFeatures) const {
    if (nQuantiles > 0) return predictQuantileEV(canonFeatures);
    if (isEntityPolicy) {
        float state64[64];
        encodePolicyStateVec(canonFeatures, state64);
        return predictPolicyActionVec(canonFeatures, state64);
    }
    if (isEntity) {
        const auto p = predictOutcomeVec(canonFeatures);
        return p.winProbability * (entityWinBonus + p.endHpFractionIfWin * canonFeatures[4]);
    }
    if (isDeepSets) {
        // DeepSets inference: embed → pool → MLP
        thread_local std::vector<float> pool, a1, a2;
        const int concatDim = 4*d_card + d_relic + d_pot + d_mon + d_enc + d_scalar;
        pool.resize(concatDim);
        float *p = pool.data();

        // Cards: sum-pool per zone (counts @ embedding = dot-product per dim)
        for (int z = 0; z < 4; ++z) {
            int zOff = (z == 0) ? kHandOff : (z == 1) ? kDrawOff : (z == 2) ? kDiscOff : kExhOff;
            for (int d = 0; d < d_card; ++d) {
                float sum = 0.f;
                const float *e = dsCardE.data() + (std::size_t)z * kNumCards * d_card + d;
                for (int c = 0; c < kNumCards; ++c)
                    sum += canonFeatures[zOff + c] * e[c * d_card];
                *p++ = sum;
            }
        }

        // Relics: sum-pool over present relics (binary mask)
        for (int d = 0; d < d_relic; ++d) {
            float sum = 0.f;
            for (int r = 0; r < kNumRelics; ++r)
                if (canonFeatures[kRelicOff + r] > 0.5f)
                    sum += dsRelicE[(std::size_t)r * d_relic + d];
            *p++ = sum;
        }

        // Potions: count-weighted sum
        for (int d = 0; d < d_pot; ++d) {
            float sum = 0.f;
            for (int pt = 0; pt < kNumPotions; ++pt)
                sum += canonFeatures[kPotOff + pt] * dsPotionE[(std::size_t)pt * d_pot + d];
            *p++ = sum;
        }

        // Monsters: per-slot MLP → mean-pool over alive
        {
            thread_local std::vector<float> monAct(d_mon);
            float monPool[32] = {};  // d_mon ≤ 32
            int alive = 0;
            for (int s = 0; s < kNumMonSlots; ++s) {
                int mOff = kMonOff + s * kMonFeats;
                if (canonFeatures[mOff + 1] <= 0.f) continue;  // m{i}Hp == 0 → dead
                alive++;
                // Layer 1: monFeats → d_mon
                for (int j = 0; j < d_mon; ++j) {
                    float sum = dsMonB1[j];
                    for (int i = 0; i < kMonFeats; ++i)
                        sum += canonFeatures[mOff + i] * dsMonW1[(std::size_t)j * kMonFeats + i];
                    monAct[j] = sum > 0.f ? sum : 0.f;
                }
                // Layer 2: d_mon → d_mon
                for (int j = 0; j < d_mon; ++j) {
                    float sum = dsMonB2[j];
                    for (int i = 0; i < d_mon; ++i)
                        sum += monAct[i] * dsMonW2[(std::size_t)j * d_mon + i];
                    monAct[j] = sum > 0.f ? sum : 0.f;
                }
                for (int j = 0; j < d_mon; ++j) monPool[j] += monAct[j];
            }
            float inv = alive > 0 ? 1.f / (float)alive : 1.f;
            for (int j = 0; j < d_mon; ++j) *p++ = monPool[j] * inv;
        }

        // Encounter embedding
        {
            int enc = (int)canonFeatures[encIdx];
            if (enc < 0) enc = 0;
            if (enc >= nEncounter) enc = nEncounter - 1;
            for (int d = 0; d < d_enc; ++d)
                *p++ = dsEncE[(std::size_t)enc * d_enc + d];
        }

        // Scalars: z-normalize → linear → ReLU
        {
            thread_local std::vector<float> sc(d_scalar);
            for (int j = 0; j < d_scalar; ++j) {
                float sum = dsScalarB[j];
                for (std::size_t i = 0; i < dsScalarSel.size(); ++i) {
                    float v = canonFeatures[dsScalarSel[i]];
                    v = (v - dsScalarMean[i]) * dsScalarInv[i];
                    if (v < -5.0f) v = -5.0f;
                    else if (v > 5.0f) v = 5.0f;
                    sum += v * dsScalarW[(std::size_t)j * dsScalarSel.size() + i];
                }
                sc[j] = sum > 0.f ? sum : 0.f;
            }
            for (int j = 0; j < d_scalar; ++j) *p++ = sc[j];
        }

        // MLP head
        a1.resize(h1); a2.resize(h2);
        for (int j = 0; j < h1; ++j) {
            float sum = b1[j];
            for (int i = 0; i < concatDim; ++i)
                sum += pool[i] * w1[(std::size_t)j * concatDim + i];
            a1[j] = sum > 0.f ? sum : 0.f;
        }
        for (int j = 0; j < h2; ++j) {
            float sum = b2[j];
            for (int i = 0; i < h1; ++i)
                sum += a1[i] * w2[(std::size_t)j * h1 + i];
            a2[j] = sum > 0.f ? sum : 0.f;
        }
        float out = b3;
        for (int i = 0; i < h2; ++i) out += w3[i] * a2[i];
        return (double)(yMean + yScale * out);
    }
    if (isMlp) {
        thread_local std::vector<float> x, a1, a2;
        a1.resize(h1); a2.resize(h2);
        if (isSparseMlp) {
            std::copy(b1.begin(), b1.end(), a1.begin());
            for (std::size_t i = 0; i < sel.size(); ++i) {
                const float v = canonFeatures[sel[i]];
                if (v == 0.f) continue;
                const float *w = w1.data() + i * std::size_t(h1);
                for (int j = 0; j < h1; ++j) a1[j] += v * w[j];
            }
            for (float &v : a1) if (v < 0.f) v = 0.f;
        } else {
            x.resize(sel.size());
            for (std::size_t i = 0; i < sel.size(); ++i) {
                float z = (canonFeatures[sel[i]] - xMean[i]) * xInvStd[i];
                if (z < -5.0f) z = -5.0f;
                else if (z > 5.0f) z = 5.0f;
                x[i] = z;
            }
            for (int j = 0; j < h1; ++j) {
                const float *w = w1.data() + std::size_t(j) * x.size();
                float sum = b1[j];
                for (std::size_t i = 0; i < x.size(); ++i) sum += w[i] * x[i];
                a1[j] = sum > 0.f ? sum : 0.f;
            }
        }
        for (int j = 0; j < h2; ++j) {
            const float *w = w2.data() + std::size_t(j) * h1;
            float sum = b2[j];
            for (int i = 0; i < h1; ++i) sum += w[i] * a1[i];
            a2[j] = sum > 0.f ? sum : 0.f;
        }
        float out = b3;
        for (int i = 0; i < h2; ++i) out += w3[i] * a2[i];
        return yMean + yScale * out;
    }
    double sum = baseScore;
    for (const auto &nodes : trees) {
        int n = 0;
        int steps = 0;
        while (nodes[n].featIdx >= 0) {
            if (++steps > (int)nodes.size()) {
                std::fprintf(stderr,
                             "[CombatValueNet] tree-walk exceeded %d steps "
                             "(tree %zu/%zu, node %d feat %d val %.4f, yes %d "
                             "no %d) — corrupt/cyclic model, treating node as "
                             "leaf\n",
                             (int)nodes.size(), &nodes - &trees[0], trees.size(),
                             n, nodes[n].featIdx,
                             (double)canonFeatures[sel[nodes[n].featIdx]],
                             nodes[n].yes, nodes[n].no);
                break;
            }
            const float x = canonFeatures[sel[nodes[n].featIdx]];
            n = (x < nodes[n].thresh) ? nodes[n].yes : nodes[n].no;
        }
        sum += nodes[n].thresh;   // leaf value
    }
    return sum;
}

void CombatValueNet::predictPolicyActions(const float *canonFeatures, const float *actionBlocks,
                                          int n, double *out) const {
    if (n <= 0) return;
    if (flatRoots.empty()) {
        thread_local std::vector<float> features;
        features.assign(canonFeatures, canonFeatures + kStateCount);
        features.resize(kStateCount + kNumAction);
        for (int i = 0; i < n; ++i) {
            std::copy(actionBlocks + i * kNumAction, actionBlocks + (i + 1) * kNumAction,
                      features.begin() + kStateCount);
            out[i] = predictVec(features.data());
        }
        return;
    }
    // One full feature vector per action, so a walk reads features[feat].
    constexpr int kWidth = kStateCount + kNumAction;
    thread_local std::vector<float> features;
    thread_local std::vector<int> cursor;
    features.resize(static_cast<std::size_t>(n) * kWidth);
    for (int i = 0; i < n; ++i) {
        float *f = features.data() + static_cast<std::size_t>(i) * kWidth;
        std::copy(canonFeatures, canonFeatures + kStateCount, f);
        std::copy(actionBlocks + i * kNumAction, actionBlocks + (i + 1) * kNumAction, f + kStateCount);
    }
    for (int i = 0; i < n; ++i) out[i] = baseScore;
    for (const int root : flatRoots) {
        const FlatNode *nodes = flatNodes.data() + root;
        // State-only prefix: identical for every action of this state.
        int s = 0;
        while (nodes[s].feat >= 0 && nodes[s].feat < kStateCount)
            s = nodes[s].left + !(canonFeatures[nodes[s].feat] < nodes[s].thresh);
        if (nodes[s].feat < 0) {
            for (int i = 0; i < n; ++i) out[i] += nodes[s].thresh;
            continue;
        }
        // Walk the actions in lockstep so their node loads overlap.
        cursor.assign(n, s);
        for (bool active = true; active;) {
            active = false;
            for (int i = 0; i < n; ++i) {
                const FlatNode &node = nodes[cursor[i]];
                if (node.feat < 0) continue;
                const float *f = features.data() + static_cast<std::size_t>(i) * kWidth;
                cursor[i] = node.left + !(f[node.feat] < node.thresh);
                active = true;
            }
        }
        for (int i = 0; i < n; ++i) out[i] += nodes[cursor[i]].thresh;
    }
}

// §132: EV of the terminal utility distribution = mean over quantiles of
// R = 0 | 50+endHp. On the leaf's terminal scale by construction.
double CombatValueNet::predictQuantileEV(const float *canonFeatures) const {
    double sum = 0.0;
    for (int q = 0; q < nQuantiles; ++q) {
        double s = quantileBase[q];
        for (const auto &nodes : quantileTrees[q]) {
            int n = 0;
            int steps = 0;
            while (nodes[n].featIdx >= 0) {
                if (++steps > (int)nodes.size()) {
                    std::fprintf(stderr,
                                 "[CombatValueNet] quantile tree-walk exceeded "
                                 "%d steps (quantile %d/%d, node %d) — corrupt "
                                 "model, treating node as leaf\n",
                                 (int)nodes.size(), q, nQuantiles, n);
                    break;
                }
                const float x = canonFeatures[sel[nodes[n].featIdx]];
                n = (x < nodes[n].thresh) ? nodes[n].yes : nodes[n].no;
            }
            s += nodes[n].thresh;
        }
        sum += s;
    }
    return sum / (double)nQuantiles;
}

namespace {

// Ascending indices of the features that are not +-0 (`v == 0.f` skips both
// signed zeros; the SSE2 not-equal test treats them the same way and keeps NaN).
int nonzeroFeatureIndices(const float *x, int n, std::uint16_t *out) {
    int c = 0, i = 0;
    const __m128 zero = _mm_setzero_ps();
    for (; i + 4 <= n; i += 4) {
        int m = _mm_movemask_ps(_mm_cmpneq_ps(_mm_loadu_ps(x + i), zero));
        while (m) {
            out[c++] = static_cast<std::uint16_t>(i + __builtin_ctz(m));
            m &= m - 1;
        }
    }
    for (; i < n; ++i)
        if (x[i] != 0.f) out[c++] = static_cast<std::uint16_t>(i);
    return c;
}

// Per-edge layers of predictPolicyMlp for a compile-time second-layer width.
// Same float operations in the same order as the generic loop; restrict
// pointers and a local accumulator array let the compiler keep the H2 sums in
// registers instead of reloading a vector it must assume aliases the weights.
// Adding -0.0f leaves every float unchanged, so the output sum equals skipping.
template <int H2>
void policyMlpEdges(const CombatValueNet &net, const float *__restrict base, const float *stateFeatures,
                    const float *actionBlocks, const int *targetSlots, int n, double *out) {
    const int H1 = net.pmH1;
    const float *__restrict actionW = net.pmActionW.data();
    const float *__restrict cardW = net.pmCard.data();
    const float *__restrict targetW = net.pmTargetW.data();
    const float *__restrict w2t = net.pmW2T.data();
    const float *__restrict b2 = net.pmB2.data();
    const float *__restrict w3 = net.pmW3.data();
    alignas(64) float h[kPolicyMlpMaxH1];
    for (int e = 0; e < n; ++e) {
        const float *a = actionBlocks + (std::size_t)e * kNumAction;
        for (int j = 0; j < H1; ++j) h[j] = base[j];
        for (int k = 0; k < kNumAction; ++k) {
            const float v = a[k];
            if (v == 0.f) continue;
            const float *__restrict w = actionW + (std::size_t)k * H1;
            for (int j = 0; j < H1; ++j) h[j] += v * w[j];
        }
        int card = (int)a[4] + 1;   // aCardId; -1 (no card) -> row 0
        if (card < 0 || card > kNumCards) card = 0;
        const float *__restrict c = cardW + (std::size_t)card * H1;
        for (int j = 0; j < H1; ++j) h[j] += c[j];
        const int slot = targetSlots ? targetSlots[e] : -1;
        if (slot >= 0 && slot < kNumMonSlots) {
            const float *t = stateFeatures + kMonOff + slot * kMonFeats;
            for (int k = 0; k < kMonFeats; ++k) {
                const float v = t[k];
                if (v == 0.f) continue;
                const float *__restrict w = targetW + (std::size_t)k * H1;
                for (int j = 0; j < H1; ++j) h[j] += v * w[j];
            }
        }
        alignas(64) float z[H2];
        for (int i = 0; i < H2; ++i) z[i] = b2[i];
        for (int j = 0; j < H1; ++j) {
            const float v = h[j];
            if (v <= 0.f) continue;   // ReLU
            const float *__restrict w = w2t + (std::size_t)j * H2;
            for (int i = 0; i < H2; ++i) z[i] += v * w[i];
        }
        float o = net.pmB3;
        for (int i = 0; i < H2; ++i) o += z[i] > 0.f ? w3[i] * z[i] : -0.0f;
        out[e] = o;
    }
}

}

void CombatValueNet::policyMlpBase(const float *stateFeatures, std::vector<float> &base) const {
    const int H1 = pmH1;
    base.assign(pmB1.begin(), pmB1.end());
    // v2 embedding tables (raw ids otherwise enter the state layer as plain
    // numbers). Row = rounded value clipped to the table. A monster slot counts
    // only when its id is nonzero and not -1 (empty or dead slots are -1; id 0
    // is absent from the sparse training rows); its rows are id + 1 and its
    // incoming damage (feature mKIntent).
    auto row = [](float v) {
        const int r = (int)std::lround(v);
        return r < 0 ? 0 : (r >= kPolicyMlpEmbRows ? kPolicyMlpEmbRows - 1 : r);
    };
    if (!pmEnc.empty()) {
        const float *w = &pmEnc[(std::size_t)row(stateFeatures[kEncounterIdx]) * H1];
        for (int j = 0; j < H1; ++j) base[j] += w[j];
    }
    if (!pmMonId.empty() || !pmMonDmg.empty()) {
        for (int k = 0; k < kNumMonSlots; ++k) {
            const float id = stateFeatures[kMonOff + k * kMonFeats];
            if (id == 0.f || std::lround(id) + 1 <= 0) continue;    // id 0 or empty slot (-1)
            if (!pmMonId.empty()) {
                const float *w = &pmMonId[(std::size_t)row(id + 1.f) * H1];
                for (int j = 0; j < H1; ++j) base[j] += w[j];
            }
            if (!pmMonDmg.empty()) {
                const float *w = &pmMonDmg[(std::size_t)row(stateFeatures[kMonOff + k * kMonFeats + kMonDmgOff]) * H1];
                for (int j = 0; j < H1; ++j) base[j] += w[j];
            }
        }
    }
    // Sparse state layer, once per node (about 60 nonzeros of 1,766), in
    // ascending feature order.
    {
        std::uint16_t nonzero[kStateCount];
        const int count = nonzeroFeatureIndices(stateFeatures, kStateCount, nonzero);
        float *__restrict acc = base.data();
        const float *__restrict stateW = pmStateW.data();
        for (int t = 0; t < count; ++t) {
            const float v = stateFeatures[nonzero[t]];
            const float *__restrict w = stateW + (std::size_t)nonzero[t] * H1;
            for (int j = 0; j < H1; ++j) acc[j] += v * w[j];
        }
    }
}

void CombatValueNet::predictPolicyMlp(const float *stateFeatures, const float *actionBlocks,
                                      const int *targetSlots, int n, double *out) const {
    if (n <= 0) return;
    const int H1 = pmH1, H2 = pmH2;
    thread_local std::vector<float> base, h, z;
    policyMlpBase(stateFeatures, base);
    h.resize(H1);
    z.resize(H2);
    if (H2 == 64 && H1 <= kPolicyMlpMaxH1) {
        policyMlpEdges<64>(*this, base.data(), stateFeatures, actionBlocks, targetSlots, n, out);
        return;
    }
    for (int e = 0; e < n; ++e) {
        const float *a = actionBlocks + (std::size_t)e * kNumAction;
        for (int j = 0; j < H1; ++j) h[j] = base[j];
        for (int k = 0; k < kNumAction; ++k) {
            const float v = a[k];
            if (v == 0.f) continue;
            const float *w = &pmActionW[(std::size_t)k * H1];
            for (int j = 0; j < H1; ++j) h[j] += v * w[j];
        }
        int card = (int)a[4] + 1;   // aCardId; -1 (no card) -> row 0
        if (card < 0 || card > kNumCards) card = 0;
        const float *c = &pmCard[(std::size_t)card * H1];
        for (int j = 0; j < H1; ++j) h[j] += c[j];
        const int slot = targetSlots ? targetSlots[e] : -1;
        if (slot >= 0 && slot < kNumMonSlots) {
            const float *t = stateFeatures + kMonOff + slot * kMonFeats;
            for (int k = 0; k < kMonFeats; ++k) {
                const float v = t[k];
                if (v == 0.f) continue;
                const float *w = &pmTargetW[(std::size_t)k * H1];
                for (int j = 0; j < H1; ++j) h[j] += v * w[j];
            }
        }
        for (int i = 0; i < H2; ++i) z[i] = pmB2[i];
        for (int j = 0; j < H1; ++j) {
            const float v = h[j];
            if (v <= 0.f) continue;   // ReLU
            const float *w = &pmW2T[(std::size_t)j * H2];
            for (int i = 0; i < H2; ++i) z[i] += v * w[i];
        }
        float o = pmB3;
        for (int i = 0; i < H2; ++i) if (z[i] > 0.f) o += pmW3[i] * z[i];
        out[e] = o;
    }
}

std::string CombatValueNet::description() const {
    std::string base;
    if (isPolicyMlp) base = "policy mlp " + std::to_string(pmH1) + "/" + std::to_string(pmH2);
    else if (isEntityPolicy) base = "shared entity policy 64d";
    else if (isDeepSets) base = "deepsets " + std::to_string(d_card) + "d";
    else if (isEntity) base = "entity multi-head (bonus " + std::to_string(entityWinBonus) + ")";
    else if (isMlp) base = std::string(isSparseMlp ? "sparse MLP " : "MLP ")
        + std::to_string(sel.size()) + "x"
        + std::to_string(h1) + "x" + std::to_string(h2) + "x1";
    else if (nQuantiles > 0)
        base = std::to_string(nQuantiles) + "q x" + std::to_string(quantileTrees[0].size()) + " trees (EV)";
    else base = std::to_string(trees.size()) + " trees";
    if (hasEncounterModels)
        base += " +" + std::to_string(encounterModels.size()) + " per-encounter";
    return base;
}

double CombatValueNet::predict(const BattleContext &bc, bool /*emitTrace*/) const {
    thread_local std::vector<float> feat(combatFeatureCount());
    combatExtractFeatures(bc, feat.data());
    // Per-encounter dispatch: a specialized model for this encounter overrides
    // the base weights/trees; everything else keeps the pre-existing path.
    // When hasEncounterModels is false this is a single extra bool test with no
    // branch taken, byte-identical to the old behavior.
    double v;
    if (hasEncounterModels) {
        auto it = encounterModels.find((int)bc.encounter);
        if (it != encounterModels.end()) {
            v = it->second.predictVec(feat.data());
            return v;
        }
    }
    v = predictVec(feat.data());
    return v;
}

CombatOutcomePrediction CombatValueNet::predictOutcome(const BattleContext &bc) const {
    thread_local std::vector<float> feat(combatFeatureCount());
    combatExtractFeatures(bc, feat.data());
    return predictOutcomeVec(feat.data());
}

double CombatValueNet::predictAction(const BattleContext &bc, const Action &action) const {
    thread_local std::vector<float> feat(combatPolicyFeatureCount());
    combatExtractPolicyFeatures(bc, action, feat.data());
    return predictVec(feat.data());
}

} // namespace sts::search
