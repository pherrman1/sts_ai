#include "ooc_v4_encoding.h"
#include <algorithm>
#include "game/Map.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/RunGoal.h"
using namespace sts;
using sts::search::GameAction;
using namespace one_combat;
extern bool g_collectKeys;
static constexpr int TOK_NRAW = 36;

TokState buildTokStatePure(const GameContext &gc, const PathHistory &path) {
    TokState ts{};
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case CardType::ATTACK: botAtk = id; break;
                case CardType::SKILL:  botSkill = id; break;
                case CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const FwdMap fm = forwardMapFeatures(gc);
    // 36 raw scalars: same as richRow() minus the 8 hidden-information leaks
    // (nextEliteId, nextFight0/1/2, remElites, remFights, monOffset,
    //  eliteOffset at original indices 15-22); bossId is kept (visible on act map).
    const float glob[TOK_NRAW] = {
        (float)gc.ascension, (float)gc.act, (float)gc.floorNum, (float)gc.curHp,
        (float)gc.maxHp, (float)gc.gold, (float)gc.deck.size(),
        (float)gc.potionChance, (float)gc.cardRarityFactor,
        (float)(gc.blueKey ? 1 : 0), (float)(gc.greenKey ? 1 : 0), (float)(gc.redKey ? 1 : 0),
        (float)gc.potionCount, (float)gc.potionCapacity,
        (float)gc.boss,
        (float)path.roomVisits[(int)Room::SHOP], (float)path.roomVisits[(int)Room::REST],
        (float)path.roomVisits[(int)Room::EVENT], (float)path.roomVisits[(int)Room::ELITE],
        (float)path.roomVisits[(int)Room::MONSTER], (float)path.roomVisits[(int)Room::TREASURE],
        (float)botAtk, (float)botSkill, (float)botPow,
        (float)fm.dElite, (float)fm.dRest, (float)fm.dShop, (float)fm.dBoss,
        (float)fm.cElite, (float)fm.cRest, (float)fm.cShop, (float)fm.cEvent,
        (float)fm.cMonster, (float)fm.cTreasure,
        (float)gc.curMapNodeX, (float)gc.curMapNodeY
    };
    for (int i = 0; i < TOK_NRAW; ++i) ts.glob[i] = glob[i];
    // derived threshold features (ooc-strategic-v4.md §2.1)
    // canTakeEliteKey now uses fmCElite (reachable elites on the visible map)
    // instead of the removed remElites (exact hidden-queue count).
    ts.glob[TOK_NRAW + 0] = gc.maxHp > 0 ? (float)gc.curHp / gc.maxHp : 0.0f;
    ts.glob[TOK_NRAW + 1] = (float)(gc.maxHp - gc.curHp);
    ts.glob[TOK_NRAW + 2] = gc.potionCount < gc.potionCapacity ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 3] = gc.gold >= 75 ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 4] = fm.cElite > 0
                  && !(gc.blueKey && gc.greenKey && gc.redKey) ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 5] = fm.dBoss <= 3 ? 1.0f : 0.0f;

    // deck tokens: canonical ascending cardId, upgraded=1 token before the
    // unupgraded one, capped at MAXDK=96
    ts.nDk = 0;
    for (int id = 0; id < kNumCardIds && ts.nDk < 96; ++id) {
        if (u[id] > 0) {
            ts.dk[ts.nDk][0] = id; ts.dk[ts.nDk][1] = 1; ts.dk[ts.nDk][2] = u[id]; ++ts.nDk;
        }
        if (ts.nDk < 96 && d[id] - u[id] > 0) {
            ts.dk[ts.nDk][0] = id; ts.dk[ts.nDk][1] = 0; ts.dk[ts.nDk][2] = d[id] - u[id]; ++ts.nDk;
        }
    }
    // relic tokens: canonical ascending relicId (counter = 1 + relic data)
    ts.nRl = 0;
    for (int id = 0; id < kNumRelics && ts.nRl < 64; ++id)
        if (r[id] > 0) { ts.rl[ts.nRl][0] = id; ts.rl[ts.nRl][1] = r[id]; ++ts.nRl; }
    // potion tokens: canonical ascending potionId
    ts.nPt = 0;
    for (int id = 0; id < kNumPotions && ts.nPt < 8; ++id)
        if (pot[id] > 0) { ts.pt[ts.nPt][0] = id; ts.pt[ts.nPt][1] = pot[id]; ++ts.nPt; }

    return ts;
}

namespace one_combat {
bool v4DecisionSupported(const GameContext &gc) {
    switch (gc.screenState) {
        case ScreenState::REWARDS: return gc.info.rewardsContainer.cardRewardCount > 0;
        case ScreenState::REST_ROOM:
        case ScreenState::SHOP_ROOM:
        case ScreenState::TREASURE_ROOM:
        case ScreenState::BOSS_RELIC_REWARDS: return true;
        case ScreenState::EVENT_SCREEN: return gc.curEvent != Event::INVALID && gc.curEvent != Event::MATCH_AND_KEEP;
        case ScreenState::CARD_SELECT: return gc.info.selectScreenType == CardSelectScreenType::UPGRADE;
        case ScreenState::MAP_SCREEN: return gc.map && gc.curMapNodeY != 14;
        default: return false;
    }
}
std::vector<GameAction> v4CandidateActions(const GameContext &gc) {
    auto actions = GameAction::getAllActionsInState(gc);
    actions.erase(std::remove_if(actions.begin(), actions.end(), [&](const auto &action) {
        return !sts::search::isSupportedAutonomousOocAction(gc, action)
            || !sts::search::heartKeyActionAllowed(gc, g_collectKeys, action);
    }), actions.end());
    if (gc.screenState == ScreenState::REWARDS
        && gc.info.rewardsContainer.cardRewardCount > 0 && !actions.empty()) {
        const GameAction skip(GameAction::RewardsActionType::CARD,
                              gc.info.rewardsContainer.cardRewardCount - 1, 5);
        if (std::none_of(actions.begin(), actions.end(), [&](const auto &a) { return a.bits == skip.bits; }))
            actions.push_back(skip);
    }
    return actions;
}
void strategicCands(const GameContext &gc, const search::GameAction &a,
                           int &actionType, int &c1, int &c2, int &c3,
                           int &cand1, int &cand2, int &cand3) {
    using RT = search::GameAction::RewardsActionType;
    actionType = -1; c1 = a.getIdx1(); c2 = a.getIdx2(); c3 = a.getIdx3();
    cand1 = cand2 = cand3 = -1;
    switch (gc.screenState) {
        case ScreenState::REWARDS: {
            const auto t = a.getRewardsActionType();
            actionType = (int)t;
            const auto &r = gc.info.rewardsContainer;
            switch (t) {
                case RT::GOLD:
                    if (c1 >= 0 && c1 < r.goldRewardCount) cand1 = r.gold[c1];
                    break;
                case RT::CARD:
                    if (c1 >= 0 && c1 < r.cardRewardCount
                        && c2 >= 0 && c2 < (int)r.cardRewards[c1].size()) {
                        const Card &card = r.cardRewards[c1][c2];
                        cand1 = (int)card.getId(); cand2 = card.isUpgraded() ? 1 : 0;
                    }
                    break;
                case RT::RELIC: if (c1 >= 0 && c1 < r.relicCount) cand1 = (int)r.relics[c1]; break;
                case RT::POTION: if (c1 >= 0 && c1 < r.potionCount) cand1 = (int)r.potions[c1]; break;
                case RT::KEY: cand1 = r.emeraldKey ? 2 : 3; break;
                default: break;
            }
            break;
        }
        case ScreenState::SHOP_ROOM: {
            const auto t = a.getRewardsActionType();
            actionType = (int)t;
            const auto &s = gc.info.shop;
            switch (t) {
                case RT::CARD:
                    if (c1 >= 0 && c1 < 7) {
                        cand1 = (int)s.cards[c1].getId(); cand2 = s.cardPrice(c1);
                        cand3 = s.cards[c1].isUpgraded() ? 1 : 0;
                    }
                    break;
                case RT::RELIC: if (c1 >= 0 && c1 < 3) { cand1 = (int)s.relics[c1]; cand2 = s.relicPrice(c1); } break;
                case RT::POTION: if (c1 >= 0 && c1 < 3) { cand1 = (int)s.potions[c1]; cand2 = s.potionPrice(c1); } break;
                case RT::CARD_REMOVE: cand1 = s.removeCost; break;
                default: break;
            }
            break;
        }
        case ScreenState::EVENT_SCREEN:
            cand1 = (int)gc.curEvent; cand2 = c1;
            break;
        case ScreenState::MAP_SCREEN: {
            cand1 = c1;
            const int ty = (gc.curMapNodeY == -1) ? 0 : gc.curMapNodeY + 1;
            cand2 = ty;
            if (c1 >= 0 && ty >= 0 && ty < 15 && c1 < 7)
                cand3 = (int)gc.map->nodes[ty][c1].room;
            break;
        }
        case ScreenState::BOSS_RELIC_REWARDS:
            if (c1 >= 0 && c1 < 3) cand1 = (int)gc.info.bossRelics[c1];
            break;
        case ScreenState::CARD_SELECT: {
            actionType = (int)gc.info.selectScreenType;
            if (c1 >= 0 && c1 < (int)gc.info.toSelectCards.size()) {
                cand1 = (int)gc.info.toSelectCards[c1].card.getId();
                cand2 = (int)gc.info.selectScreenType;
            }
            break;
        }
        default: break;
    }
}

// V4 decision-context entity (ooc-strategic-v4.md §2.5): the candidate card/
// relic/potion conditioning the action value (entType 0=none,1=card,2=relic,
// 3=potion), plus the gold-vs-price threshold feature (SHOP_ROOM cand2=price,
// REWARDS/GOLD cand1=gold amount; else 0).
void tokEntity(const GameContext &gc, const search::GameAction &a,
                      int &entType, int &entId, float &goldGePrice) {
    using RT = search::GameAction::RewardsActionType;
    entType = 0; entId = -1; goldGePrice = 0.0f;
    switch (gc.screenState) {
        case ScreenState::REWARDS: {
            const RT t = a.getRewardsActionType();
            const auto &r = gc.info.rewardsContainer;
            switch (t) {
                case RT::GOLD:
                    if (a.getIdx1() >= 0 && a.getIdx1() < r.goldRewardCount)
                        goldGePrice = gc.gold >= r.gold[a.getIdx1()] ? 1.0f : 0.0f;
                    break;
                case RT::CARD: {
                    const int c1 = a.getIdx1(), c2 = a.getIdx2();
                    if (c1 >= 0 && c1 < r.cardRewardCount
                        && c2 >= 0 && c2 < (int)r.cardRewards[c1].size()) {
                        entType = 1; entId = (int)r.cardRewards[c1][c2].getId();
                    }
                    break;
                }
                case RT::RELIC:
                    if (a.getIdx1() >= 0 && a.getIdx1() < r.relicCount) { entType = 2; entId = (int)r.relics[a.getIdx1()]; }
                    break;
                case RT::POTION:
                    if (a.getIdx1() >= 0 && a.getIdx1() < r.potionCount) { entType = 3; entId = (int)r.potions[a.getIdx1()]; }
                    break;
                default: break;
            }
            break;
        }
        case ScreenState::SHOP_ROOM: {
            const RT t = a.getRewardsActionType();
            const auto &s = gc.info.shop;
            int price = -1;
            switch (t) {
                case RT::CARD:
                    if (a.getIdx1() >= 0 && a.getIdx1() < 7) {
                        entType = 1; entId = (int)s.cards[a.getIdx1()].getId(); price = s.cardPrice(a.getIdx1());
                    }
                    break;
                case RT::RELIC:
                    if (a.getIdx1() >= 0 && a.getIdx1() < 3) {
                        entType = 2; entId = (int)s.relics[a.getIdx1()]; price = s.relicPrice(a.getIdx1());
                    }
                    break;
                case RT::POTION:
                    if (a.getIdx1() >= 0 && a.getIdx1() < 3) {
                        entType = 3; entId = (int)s.potions[a.getIdx1()]; price = s.potionPrice(a.getIdx1());
                    }
                    break;
                default: break;
            }
            goldGePrice = (price >= 0 && gc.gold >= price) ? 1.0f : 0.0f;  // trainer parity: price<0 -> 0
            break;
        }
        case ScreenState::CARD_SELECT:
            if (a.getIdx1() >= 0 && a.getIdx1() < (int)gc.info.toSelectCards.size()) {
                entType = 1; entId = (int)gc.info.toSelectCards[a.getIdx1()].card.getId();
            }
            break;
        default: break;
    }
}

} // namespace one_combat
