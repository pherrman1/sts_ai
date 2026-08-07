//
// See CombatValueNet.h
//
#include "sim/search/CombatValueNet.h"

#include "combat/BattleContext.h"
#include "constants/PlayerStatusEffects.h"
#include "constants/MonsterStatusEffects.h"
#include "constants/Cards.h"
#include "constants/Relics.h"
#include "sim/search/Action.h"
#include "sim/search/ExpertKnowledge.h"

#include <fstream>
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

    int powerVal(const Player &p, PlayerStatus s) {
        switch (s) {
            case PlayerStatus::STRENGTH:  return p.strength;
            case PlayerStatus::DEXTERITY: return p.dexterity;
            case PlayerStatus::FOCUS:     return p.focus;
            case PlayerStatus::ARTIFACT:  return p.artifact;
            default: break;
        }
        auto it = p.statusMap.find(s);
        if (it != p.statusMap.end()) return it->second;
        return p.hasStatusRuntime(s) ? 1 : 0;
    }
}

namespace sts::search {

CombatValueNet g_combatVNet;
bool g_useVNet = false;

CombatValueNet g_policyNet;
bool   g_usePolicyNet = false;
double g_cPuct = 2.5;   // swept best at low-mid sims (0.5 under-explores; 2.5-4 best)

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
        if (src >= 0 && src < bc.cards.cardsInHand) {
            const auto &c = bc.cards.hand[src];
            const auto id = c.getId();
            a[4]  = (float)(int)id;
            a[5]  = (float)c.costForTurn;
            a[6]  = c.isUpgraded() ? 1.f : 0.f;
            const auto t = c.getType();
            a[7]  = (t == CardType::ATTACK) ? 1.f : 0.f;
            a[8]  = (t == CardType::SKILL)  ? 1.f : 0.f;
            a[9]  = (t == CardType::POWER)  ? 1.f : 0.f;
            const int tgt = action.getTargetIdx();
            if (tgt >= 0 && tgt < bc.monsters.monsterCount && bc.monsters.arr[tgt].curHp > 0) {
                a[10] = 1.f;
                a[11] = (float)bc.monsters.arr[tgt].curHp;
            }
            a[12] = (float)Expert::getPlayOrdering(id);
            a[13] = (float)Expert::getObtainWeight(id, c.isUpgraded());
        }
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
    for (const auto &pf : kPowers) out[k++] = (float)powerVal(p, pf.status);

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
        if (atk) { const auto di = mm.getMoveBaseDamage(bc); idmg = mm.calculateDamageToPlayer(bc, di.damage) * di.attackCount; }
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
    trees.clear(); sel.clear();
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

    f >> tok;
    int nfeat = 0;
    if (tok == "combat_policy_entity_v1") {
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
        return true;
    } else if (tok == "combat_mlp_v1" || tok == "combat_mlp_sparse_v1") {
        isMlp = true;
        isSparseMlp = tok == "combat_mlp_sparse_v1";
        f >> tok >> nfeat;                   // "nfeat <k>"
    } else if (tok == "nfeat") {
        f >> nfeat;                          // legacy tree model
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
        isLoaded = true;
        return true;
    }

    f >> tok >> baseScore;                   // "base_score <f>"
    int ntrees = 0;
    f >> tok >> ntrees;                      // "ntrees <t>"

    trees.assign(ntrees, {});
    for (int t = 0; t < ntrees; ++t) {
        int idx = 0, nnodes = 0;
        f >> tok >> idx >> nnodes;           // "tree <idx> <nnodes>"
        auto &nodes = trees[t];
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
    if (!f) return false;
    isLoaded = true;
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
    if (isEntityPolicy) {
        float state64[64];
        encodePolicyStateVec(canonFeatures, state64);
        return predictPolicyActionVec(canonFeatures, state64);
    }
    if (isEntity) {
        const auto p = predictOutcomeVec(canonFeatures);
        return p.winProbability * (entityWinBonus + p.endHpFractionIfWin * canonFeatures[4]);
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
            for (std::size_t i = 0; i < sel.size(); ++i)
                x[i] = (canonFeatures[sel[i]] - xMean[i]) * xInvStd[i];
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
        while (nodes[n].featIdx >= 0) {
            const float x = canonFeatures[sel[nodes[n].featIdx]];
            n = (x < nodes[n].thresh) ? nodes[n].yes : nodes[n].no;
        }
        sum += nodes[n].thresh;   // leaf value
    }
    return sum;
}

std::string CombatValueNet::description() const {
    if (isEntityPolicy) return "shared entity policy 64d";
    if (isEntity) return "entity multi-head (bonus " + std::to_string(entityWinBonus) + ")";
    if (isMlp) return std::string(isSparseMlp ? "sparse MLP " : "MLP ")
        + std::to_string(sel.size()) + "x"
        + std::to_string(h1) + "x" + std::to_string(h2) + "x1";
    return std::to_string(trees.size()) + " trees";
}

double CombatValueNet::predict(const BattleContext &bc) const {
    thread_local std::vector<float> feat(combatFeatureCount());
    combatExtractFeatures(bc, feat.data());
    return predictVec(feat.data());
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
