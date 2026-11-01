#include "heart1_policy.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <immintrin.h>
#include <limits>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>

#include "constants/Events.h"
#include "game/Map.h"
#include "game/Neow.h"
#include "sim/search/RunGoal.h"

using namespace sts;
using GA = sts::search::GameAction;
using RT = sts::search::GameAction::RewardsActionType;
extern bool g_collectKeys;

namespace one_combat::heart1 {

// STS_OOC_HEART1_WING_BOOTS_COUNTER (#638): 1 = the Wing Boots relic counter
// carries gc.wingBootsCharges (0-3), so x_relic_counter weights trained on it
// can tell charged from spent boots. Unset or 0 = the frozen encoding, where
// the counter is relic.data, always 0 for Wing Boots (initRelicsFromSave).
// Other values are fatal. Read only when Wing Boots is owned, and by the
// capture/run provenance writers.
bool wingBootsCounter() {
    const char *value = std::getenv("STS_OOC_HEART1_WING_BOOTS_COUNTER");
    if (!value || !*value || std::string(value) == "0") return false;
    if (std::string(value) == "1") return true;
    throw std::runtime_error("STS_OOC_HEART1_WING_BOOTS_COUNTER must be 0 or 1");
}

namespace {

// silverbot/network.py FixedAction (IntEnum values).
enum FA : int {
    FA_SKIP = 1, FA_REMOVE = 2, FA_SINGING_BOWL = 3, FA_REST = 4, FA_SMITH = 5, FA_RECALL = 6,
    FA_LIFT = 7, FA_TOKE = 8, FA_DIG = 9,
    FA_NEOW_FIRST = 10,  // NEOW_THREE_CARDS .. NEOW_BOSS_RELIC follow Neow::Bonus order (10..28)
    FA_BIG_FISH_BANANA = 29, FA_FACE_TRADER_LOSE_GOLD = 32, FA_FACE_TRADER_LOSE_HP = 33,
    FA_GOLDEN_SHRINE_PRAY = 35, FA_NLOTH_OFFER_0 = 38, FA_NLOTH_OFFER_1 = 39,
    FA_SENSORY_STONE_MEMORIES = 41, FA_WINDING_HALLS_MADNESS = 44, FA_WINDING_HALLS_WRITHE = 45,
    FA_KNOWING_SKULL_OPTION_0 = 47, FA_WOMAN_IN_BLUE_OPTION_0 = 51,
    FA_ANCIENT_WRITING_ELEGANCE = 55, FA_DEAD_ADVENTURER_SEARCH = 57, FA_DUPLICATOR_DUPLICATE = 59,
    FA_OLD_BEGGAR_GIVE_GOLD = 61, FA_DIVINE_FOUNTAIN_HEAL = 63, FA_GHOSTS_AGREE = 65,
    FA_SSSSSERPENT_AGREE = 67, FA_MASKED_BANDITS_PAY = 69, FA_MUSHROOMS_HEAL = 71,
    FA_MYSTERIOUS_SPHERE_OPEN = 73, FA_NEST_AGREE = 75, FA_NOTE_FOR_YOURSELF_IGNORE = 77,
    FA_SCRAP_OOZE_ATTACK = 79, FA_SECRET_PORTAL_ENTER = 81, FA_SHINING_LIGHT_ENTER = 83,
    FA_JOUST_GIVE_GOLD = 85, FA_LIBRARY_READ = 87, FA_MAUSOLEUM_OPEN = 89,
    FA_WORLD_OF_GOOP_ENTER = 91, FA_LAB_OPTION = 93, FA_WHEEL_OF_CHANGE_OPTION = 94,
    FA_PLEADING_VAGRANT_GIVE_GOLD = 95, FA_COLOSSEUM_PHASE1_PROCEED = 98,
    FA_COLOSSEUM_PHASE2_OPTION_0 = 99, FA_CURSED_TOME_READ = 101, FA_CURSED_TOME_PHASE1_OPTION = 103,
    FA_CURSED_TOME_PHASE4_OPTION_0 = 106, FA_DESIGNER_UPGRADE_ONE = 108, FA_AUGMENTER_AGREE = 114,
    FA_FALLING_SKILL = 117, FA_FALLING_POWER = 118, FA_FALLING_ATTACK = 119,
    FA_FORGOTTEN_ALTAR_PRAY = 121, FA_GOLDEN_IDOL_TAKE = 124, FA_GOLDEN_IDOL_PHASE2_OPTION_0 = 126,
    FA_WING_STATUE_REMOVE_CARD = 129, FA_LIVING_WALL_CHANGE = 132, FA_MINDBLOOM_ACT1_BOSS = 135,
    FA_PURIFIER_PURIFY = 139, FA_TRANSMORGRIFIER_TRANSFORM = 141, FA_CLERIC_HEAL = 143,
    FA_MOAI_HEAD_GOLDEN_IDOL = 146, FA_TOMB_RED_MASK_DON_MASK = 149, FA_UPGRADE_SHRINE_UPGRADE = 152,
    FA_VAMPIRES_ACCEPT = 154, FA_WE_MEET_AGAIN_POTION = 157, FA_OMINOUS_FORGE_UPGRADE = 161,
    FA_TAKE_KEY = 164, FA_OPEN_CHEST = 165,
};

constexpr float kNormEps = 1e-5f;
constexpr int kMapAggCap = 15;
constexpr int kRelicInvalid = static_cast<int>(RelicId::INVALID);
constexpr int kCardInvalid = static_cast<int>(CardId::INVALID);

// map_event_action_to_fixed_action. -1: silverbot has no mapping (it returns
// None for Match and Keep and raises for anything else).
int eventFixedAction(const GameContext &gc, int idx1) {
    const int phase = gc.info.eventData;
    const auto pick = [&](int first, int n) { return idx1 < n ? first + idx1 : first + n - 1; };
    switch (gc.curEvent) {
        case Event::LAB: return FA_LAB_OPTION;
        case Event::WHEEL_OF_CHANGE: return FA_WHEEL_OF_CHANGE_OPTION;
        case Event::ANCIENT_WRITING: return FA_ANCIENT_WRITING_ELEGANCE + (idx1 == 0 ? 0 : 1);
        case Event::DEAD_ADVENTURER: return FA_DEAD_ADVENTURER_SEARCH + (idx1 == 0 ? 0 : 1);
        case Event::DUPLICATOR: return FA_DUPLICATOR_DUPLICATE + (idx1 == 0 ? 0 : 1);
        case Event::OLD_BEGGAR: return FA_OLD_BEGGAR_GIVE_GOLD + (idx1 == 0 ? 0 : 1);
        case Event::THE_DIVINE_FOUNTAIN: return FA_DIVINE_FOUNTAIN_HEAL + (idx1 == 0 ? 0 : 1);
        case Event::GHOSTS: return FA_GHOSTS_AGREE + (idx1 == 0 ? 0 : 1);
        case Event::THE_SSSSSERPENT: return FA_SSSSSERPENT_AGREE + (idx1 == 0 ? 0 : 1);
        case Event::MASKED_BANDITS: return FA_MASKED_BANDITS_PAY + (idx1 == 0 ? 0 : 1);
        case Event::HYPNOTIZING_COLORED_MUSHROOMS: return FA_MUSHROOMS_HEAL + (idx1 == 0 ? 0 : 1);
        case Event::MYSTERIOUS_SPHERE: return FA_MYSTERIOUS_SPHERE_OPEN + (idx1 == 0 ? 0 : 1);
        case Event::THE_NEST: return FA_NEST_AGREE + (idx1 == 0 ? 0 : 1);
        case Event::NOTE_FOR_YOURSELF: return FA_NOTE_FOR_YOURSELF_IGNORE + (idx1 == 0 ? 0 : 1);
        case Event::SCRAP_OOZE: return FA_SCRAP_OOZE_ATTACK + (idx1 == 0 ? 0 : 1);
        case Event::SECRET_PORTAL: return FA_SECRET_PORTAL_ENTER + (idx1 == 0 ? 0 : 1);
        case Event::SHINING_LIGHT: return FA_SHINING_LIGHT_ENTER + (idx1 == 0 ? 0 : 1);
        case Event::THE_JOUST: return FA_JOUST_GIVE_GOLD + (idx1 == 0 ? 0 : 1);
        case Event::THE_LIBRARY: return FA_LIBRARY_READ + (idx1 == 0 ? 0 : 1);
        case Event::THE_MAUSOLEUM: return FA_MAUSOLEUM_OPEN + (idx1 == 0 ? 0 : 1);
        case Event::WORLD_OF_GOOP: return FA_WORLD_OF_GOOP_ENTER + (idx1 == 0 ? 0 : 1);
        case Event::BIG_FISH: return pick(FA_BIG_FISH_BANANA, 3);
        case Event::FACE_TRADER: return pick(FA_FACE_TRADER_LOSE_GOLD, 3);
        case Event::GOLDEN_SHRINE: return pick(FA_GOLDEN_SHRINE_PRAY, 3);
        case Event::NLOTH: return pick(FA_NLOTH_OFFER_0, 3);
        case Event::SENSORY_STONE: return pick(FA_SENSORY_STONE_MEMORIES, 3);
        case Event::WINDING_HALLS: return pick(FA_WINDING_HALLS_MADNESS, 3);
        case Event::NEOW: {
            if (idx1 < 0 || idx1 >= int(gc.info.neowRewards.size())) return -1;
            const auto bonus = gc.info.neowRewards[idx1].r;
            if (bonus == Neow::Bonus::INVALID) return -1;
            return FA_NEOW_FIRST + static_cast<int>(bonus);
        }
        case Event::KNOWING_SKULL: return pick(FA_KNOWING_SKULL_OPTION_0, 4);
        case Event::THE_WOMAN_IN_BLUE: return pick(FA_WOMAN_IN_BLUE_OPTION_0, 4);
        case Event::PLEADING_VAGRANT: return pick(FA_PLEADING_VAGRANT_GIVE_GOLD, 3);
        case Event::COLOSSEUM:
            if (phase == 0) return FA_COLOSSEUM_PHASE1_PROCEED;
            return FA_COLOSSEUM_PHASE2_OPTION_0 + (idx1 == 0 ? 0 : 1);
        case Event::CURSED_TOME:
            switch (phase) {
                case 0: return FA_CURSED_TOME_READ + (idx1 == 0 ? 0 : 1);
                case 1: case 2: case 3: return FA_CURSED_TOME_PHASE1_OPTION + phase - 1;
                case 4: return FA_CURSED_TOME_PHASE4_OPTION_0 + (idx1 == 0 ? 0 : 1);
                default: return -1;
            }
        // The conditional events raise in silverbot on an out-of-range idx1.
        case Event::DESIGNER_IN_SPIRE: return idx1 < 6 ? FA_DESIGNER_UPGRADE_ONE + idx1 : -1;
        case Event::AUGMENTER: return idx1 < 3 ? FA_AUGMENTER_AGREE + idx1 : -1;
        case Event::FALLING: return idx1 < 4 ? FA_FALLING_SKILL + idx1 : -1;
        case Event::FORGOTTEN_ALTAR: return idx1 < 3 ? FA_FORGOTTEN_ALTAR_PRAY + idx1 : -1;
        case Event::GOLDEN_IDOL: return idx1 < 5 ? FA_GOLDEN_IDOL_TAKE + idx1 : -1;
        case Event::WING_STATUE: return idx1 < 3 ? FA_WING_STATUE_REMOVE_CARD + idx1 : -1;
        case Event::LIVING_WALL: return idx1 < 3 ? FA_LIVING_WALL_CHANGE + idx1 : -1;
        case Event::MINDBLOOM: return idx1 < 4 ? FA_MINDBLOOM_ACT1_BOSS + idx1 : -1;
        case Event::PURIFIER: return idx1 < 2 ? FA_PURIFIER_PURIFY + idx1 : -1;
        case Event::TRANSMORGRIFIER: return idx1 < 2 ? FA_TRANSMORGRIFIER_TRANSFORM + idx1 : -1;
        case Event::THE_CLERIC: return idx1 < 3 ? FA_CLERIC_HEAL + idx1 : -1;
        case Event::THE_MOAI_HEAD: return idx1 < 3 ? FA_MOAI_HEAD_GOLDEN_IDOL + idx1 : -1;
        case Event::TOMB_OF_LORD_RED_MASK: return idx1 < 3 ? FA_TOMB_RED_MASK_DON_MASK + idx1 : -1;
        case Event::UPGRADE_SHRINE: return idx1 < 2 ? FA_UPGRADE_SHRINE_UPGRADE + idx1 : -1;
        case Event::VAMPIRES: return idx1 < 3 ? FA_VAMPIRES_ACCEPT + idx1 : -1;
        case Event::WE_MEET_AGAIN: return idx1 < 4 ? FA_WE_MEET_AGAIN_POTION + idx1 : -1;
        case Event::OMINOUS_FORGE: return idx1 < 3 ? FA_OMINOUS_FORGE_UPGRADE + idx1 : -1;
        default: return -1;  // MATCH_AND_KEEP, BONFIRE_SPIRITS and unmapped events
    }
}

// extract_event_info.
FixedChoice eventFixedChoice(const GameContext &gc, int idx1, int fa) {
    FixedChoice c;
    c.action = fa;
    const auto &info = gc.info;
    const auto deckCard = [&](int idx) { return static_cast<int>(gc.deck.cards[idx].id); };
    switch (gc.curEvent) {
        case Event::NEOW:
            if (idx1 < int(info.neowRewards.size())) {
                switch (info.neowRewards[idx1].d) {
                    case Neow::Drawback::TEN_PERCENT_HP_LOSS: c.info = 1; break;
                    case Neow::Drawback::NO_GOLD: c.info = 2; break;
                    case Neow::Drawback::CURSE: c.info = 3; break;
                    case Neow::Drawback::PERCENT_DAMAGE: c.info = 4; break;
                    case Neow::Drawback::LOSE_STARTER_RELIC: c.info = 5; break;
                    default: break;
                }
            }
            break;
        case Event::FALLING:
            if (fa == FA_FALLING_SKILL && info.skillCardDeckIdx != -1) c.card = deckCard(info.skillCardDeckIdx);
            else if (fa == FA_FALLING_POWER && info.powerCardDeckIdx != -1) c.card = deckCard(info.powerCardDeckIdx);
            else if (fa == FA_FALLING_ATTACK && info.attackCardDeckIdx != -1) c.card = deckCard(info.attackCardDeckIdx);
            break;
        case Event::WE_MEET_AGAIN:
            if (info.cardIdx != -1) c.card = deckCard(info.cardIdx);
            c.gold = info.gold != -1 ? info.gold : 0;
            break;
        case Event::NLOTH:
            if (fa == FA_NLOTH_OFFER_0 && info.relicIdx0 != -1)
                c.relic = static_cast<int>(gc.relics.relics[info.relicIdx0].id);
            else if (fa == FA_NLOTH_OFFER_1 && info.relicIdx1 != -1)
                c.relic = static_cast<int>(gc.relics.relics[info.relicIdx1].id);
            break;
        case Event::WORLD_OF_GOOP:
            if (fa == FA_WORLD_OF_GOOP_ENTER) c.gold = info.goldLoss;
            break;
        case Event::FACE_TRADER:
            if (fa == FA_FACE_TRADER_LOSE_HP) c.gold = info.hpAmount0;
            break;
        case Event::GOLDEN_IDOL:
            if (fa == FA_GOLDEN_IDOL_TAKE) c.gold = info.hpAmount0;
            else if (fa == FA_GOLDEN_IDOL_PHASE2_OPTION_0) c.gold = info.hpAmount1;
            break;
        case Event::WINDING_HALLS:
            if (fa == FA_WINDING_HALLS_MADNESS) c.gold = info.hpAmount0;
            else if (fa == FA_WINDING_HALLS_WRITHE) c.gold = info.hpAmount1;
            break;
        default: break;
    }
    return c;
}

int bossEncoding(MonsterEncounter boss) {
    switch (boss) {
        case MonsterEncounter::SLIME_BOSS: return 0;
        case MonsterEncounter::HEXAGHOST: return 1;
        case MonsterEncounter::THE_GUARDIAN: return 2;
        case MonsterEncounter::CHAMP: return 3;
        case MonsterEncounter::AUTOMATON: return 4;
        case MonsterEncounter::COLLECTOR: return 5;
        case MonsterEncounter::TIME_EATER: return 6;
        case MonsterEncounter::DONU_AND_DECA: return 7;
        case MonsterEncounter::AWAKENED_ONE: return 8;
        case MonsterEncounter::THE_HEART: return 9;
        default: throw std::runtime_error("heart1: boss outside the encoding");
    }
}

// getNNRepresentation (bindings-util.cpp).
void encodeObservation(const GameContext &gc, Record &r) {
    r.fixedObservation = {std::min(gc.curHp, 200), std::min(gc.maxHp, 200), std::min(gc.gold, 1800),
                          gc.floorNum, bossEncoding(gc.boss), gc.info.toSelectCount, gc.ascension,
                          gc.redKey ? 1 : 0, gc.greenKey ? 1 : 0, gc.blueKey ? 1 : 0};
    for (const auto &c : gc.deck.cards) {
        r.deckCards.push_back(static_cast<int>(c.id));
        r.deckUpgrades.push_back(c.getUpgraded());
        r.deckMisc.push_back(c.misc);
    }
    r.act = gc.act;
    for (const auto &relic : gc.relics.relics) {
        r.relics.push_back(static_cast<int>(relic.id));
        r.relicCounters.push_back(relic.id == RelicId::WING_BOOTS && wingBootsCounter()
                                  ? gc.wingBootsCharges : relic.data);
    }
    for (int i = 0; i < gc.potionCapacity; ++i) r.potions.push_back(static_cast<int>(gc.potions[i]));

    const Map &map = *gc.map;
    bool haveLastRow = false;
    for (int y = 0; y < 15; ++y)
        for (int x = 0; x < 7; ++x) {
            const MapNode &node = map.getNode(x, y);
            if (node.room == Room::NONE) continue;
            r.mapRooms.push_back(static_cast<int>(node.room));
            r.mapXs.push_back(x);
            r.mapYs.push_back(y);
            if (y == 14) haveLastRow = true;
        }
    if (haveLastRow) {
        r.mapRooms.push_back(static_cast<int>(Room::BOSS));
        r.mapXs.push_back(3);
        r.mapYs.push_back(15);
    }
    for (int y = 0; y < 15; ++y)
        for (int x = 0; x < 7; ++x) {
            const MapNode &node = map.getNode(x, y);
            if (node.room == Room::NONE) continue;
            std::array<int, 3> paths{-1, -1, -1};
            for (int k = 0; k < node.edgeCount; ++k) {
                const int e = node.edges[k];
                if (y == 14) paths[1] = e;
                else if (e == x - 1) paths[0] = e;
                else if (e == x) paths[1] = e;
                else if (e == x + 1) paths[2] = e;
            }
            r.mapPathXs.push_back(paths);
        }
    if (haveLastRow) r.mapPathXs.push_back({-1, -1, -1});
    r.burningEliteX = map.burningEliteX;
    r.burningEliteY = map.burningEliteY;
    r.mapX = gc.curMapNodeX;
    r.mapY = gc.curMapNodeY;

    // v2 inputs (Record::runCounters): removals bought so far and the shop's current
    // removal price (-1 outside a shop or once bought). The pity counters (potion
    // chance, card rarity offset, "?" room chances) stay out: the game does not show
    // them and the invariance selftest treats them as private.
    const bool inShop = gc.screenState == ScreenState::SHOP_ROOM;
    r.runCounters = {gc.shopRemoveCount, inShop ? gc.info.shop.removeCost : -1};
    // Encounters already fought this act: the consumed prefix of the queues. OOC
    // MCTS resamples only the unconsumed suffix, so this prefix is never hidden.
    r.foughtEncounters.clear();
    for (int i = 0; i < std::min<int>(gc.monsterListOffset, gc.monsterList.size()); ++i)
        r.foughtEncounters.push_back(static_cast<int>(gc.monsterList[i]));
    for (int i = 0; i < std::min<int>(gc.eliteMonsterListOffset, gc.eliteMonsterList.size()); ++i)
        r.foughtEncounters.push_back(static_cast<int>(gc.eliteMonsterList[i]));
    if (int(r.foughtEncounters.size()) > kMaxFoughtEncounters) r.foughtEncounters.resize(kMaxFoughtEncounters);
}

// Reward groups expose their valid cards in order. Shop action indices instead
// remain physical slots after a purchase, so shops must not use this helper.
template <typename Cards>
std::vector<Card> validCards(const Cards &cards, int n) {
    std::vector<Card> out;
    for (int i = 0; i < n; ++i)
        if (cards[i].id != CardId::INVALID) out.push_back(cards[i]);
    return out;
}

}  // namespace

bool buildChoice(const GameContext &gc, Choice &out, std::string *reason) {
    const auto fail = [&](const char *why) {
        if (reason) *reason = why;
        return false;
    };
    out = Choice{};
    Record &r = out.record;
    std::vector<GA> cardActs, relicActs, potionActs, fixedActs, pathActs;
    std::vector<int> cardPrices, relicPrices, potionPrices;  // shop only (Record::offerPrices)
    auto actions = GA::getAllActionsInState(gc);
    actions.erase(std::remove_if(actions.begin(), actions.end(), [&](const GA &a) {
        return !search::heartKeyActionAllowed(gc, g_collectKeys, a);
    }), actions.end());
    const auto fixed = [&](const FixedChoice &c, const GA &a) {
        r.fixedActions.push_back(c);
        fixedActs.push_back(a);
    };
    const auto simpleFixed = [](int fa) { FixedChoice c; c.action = fa; return c; };
    const auto card = [&](const Card &c, const GA &a) {
        r.offeredCards.push_back(static_cast<int>(c.id));
        r.offeredUpgrades.push_back(c.getUpgraded());
        cardActs.push_back(a);
    };

    switch (gc.screenState) {
        case ScreenState::REWARDS: {
            const auto &rc = gc.info.rewardsContainer;
            auto all = actions;
            // silverbot's engine also offers Singing Bowl (+2 max HP) on the
            // last card reward; ours executes but does not enumerate it.
            if (rc.cardRewardCount > 0 && gc.hasRelic(RelicId::SINGING_BOWL)) {
                const GA bowl(RT::CARD, rc.cardRewardCount - 1, 5);
                if (bowl.isValidAction(gc)) {
                    const auto skip = std::find_if(all.begin(), all.end(), [](const GA &a) {
                        return a.getRewardsActionType() != RT::GOLD && a.getRewardsActionType() != RT::CARD;
                    });
                    all.insert(skip, bowl);
                }
            }
            for (const auto &a : all) {
                switch (a.getRewardsActionType()) {
                    case RT::CARD:
                        if (a.getIdx2() == 5) fixed(simpleFixed(FA_SINGING_BOWL), a);
                        else {
                            const auto cards = validCards(rc.cardRewards[a.getIdx1()],
                                                          int(rc.cardRewards[a.getIdx1()].size()));
                            card(cards.at(a.getIdx2()), a);
                        }
                        break;
                    case RT::POTION:
                        r.offeredPotions.push_back(static_cast<int>(rc.potions[a.getIdx1()]));
                        potionActs.push_back(a);
                        break;
                    case RT::RELIC:
                        r.offeredRelics.push_back(static_cast<int>(rc.relics[a.getIdx1()]));
                        relicActs.push_back(a);
                        break;
                    case RT::SKIP: fixed(simpleFixed(FA_SKIP), a); break;
                    case RT::KEY: fixed(simpleFixed(FA_TAKE_KEY), a); break;
                    default: break;  // gold is not in the choice space
                }
            }
            break;
        }
        case ScreenState::TREASURE_ROOM:
            for (const auto &a : actions) fixed(simpleFixed(a.getIdx1() == 0 ? FA_OPEN_CHEST : FA_SKIP), a);
            break;
        case ScreenState::SHOP_ROOM: {
            const auto &shop = gc.info.shop;
            for (const auto &a : actions) {
                switch (a.getRewardsActionType()) {
                    case RT::CARD:
                        card(shop.cards[a.getIdx1()], a);
                        cardPrices.push_back(shop.cardPrice(a.getIdx1()));
                        break;
                    case RT::RELIC:
                        r.offeredRelics.push_back(static_cast<int>(shop.relics[a.getIdx1()]));
                        relicActs.push_back(a);
                        relicPrices.push_back(shop.relicPrice(a.getIdx1()));
                        break;
                    case RT::POTION:
                        r.offeredPotions.push_back(static_cast<int>(shop.potions[a.getIdx1()]));
                        potionActs.push_back(a);
                        potionPrices.push_back(shop.potionPrice(a.getIdx1()));
                        break;
                    case RT::SKIP: fixed(simpleFixed(FA_SKIP), a); break;
                    case RT::CARD_REMOVE: fixed(simpleFixed(FA_REMOVE), a); break;
                    default: break;
                }
            }
            break;
        }
        case ScreenState::BOSS_RELIC_REWARDS:
            // Ours: idx 0..2 take that relic, 3 skips. silverbot: RELIC i / SKIP.
            for (const auto &a : actions) {
                if (a.getIdx1() < 3) {
                    r.offeredRelics.push_back(static_cast<int>(gc.info.bossRelics[a.getIdx1()]));
                    relicActs.push_back(a);
                } else {
                    fixed(simpleFixed(FA_SKIP), a);
                }
            }
            break;
        case ScreenState::REST_ROOM:
            for (const auto &a : actions) {
                static constexpr int restFa[] = {FA_REST, FA_SMITH, FA_RECALL, FA_LIFT, FA_TOKE, FA_DIG};
                fixed(simpleFixed(a.getIdx1() >= 0 && a.getIdx1() < 6 ? restFa[a.getIdx1()] : FA_SKIP), a);
            }
            break;
        case ScreenState::CARD_SELECT:
            for (const auto &a : actions)
                if (a.getIdx1() < int(gc.info.toSelectCards.size()))
                    card(gc.info.toSelectCards[a.getIdx1()].card, a);
            break;
        case ScreenState::MAP_SCREEN:
            for (const auto &a : actions) {
                r.paths.push_back(a.getIdx1());
                pathActs.push_back(a);
            }
            break;
        case ScreenState::EVENT_SCREEN:
            if (gc.curEvent == Event::MATCH_AND_KEEP) return fail("match_and_keep");
            for (const auto &a : actions) {
                const int fa = eventFixedAction(gc, a.getIdx1());
                if (fa < 0) return fail("unmapped_event");
                fixed(eventFixedChoice(gc, a.getIdx1(), fa), a);
            }
            break;
        default:
            return fail("unsupported_screen");
    }

    encodeObservation(gc, r);
    r.screenState = static_cast<int>(gc.screenState);
    r.selectScreenType = static_cast<int>(gc.info.selectScreenType);
    if (gc.screenState == ScreenState::SHOP_ROOM)
        for (auto *v : {&cardPrices, &relicPrices, &potionPrices}) r.offerPrices.insert(r.offerPrices.end(), v->begin(), v->end());
    for (auto *v : {&cardActs, &relicActs, &potionActs, &fixedActs, &pathActs})
        out.actions.insert(out.actions.end(), v->begin(), v->end());
    return true;
}

int takeFreeRewards(GameContext &gc) {
    int taken = 0;
    while (gc.outcome == GameOutcome::UNDECIDED && gc.screenState == ScreenState::REWARDS) {
        const auto actions = GA::getAllActionsInState(gc);
        const bool hasKey = std::any_of(actions.begin(), actions.end(),
                                        [](const GA &a) { return a.getRewardsActionType() == RT::KEY; });
        const auto it = std::find_if(actions.begin(), actions.end(), [&](const GA &a) {
            return a.getRewardsActionType() == RT::GOLD || (a.getRewardsActionType() == RT::RELIC && !hasKey);
        });
        if (it == actions.end()) break;
        it->execute(gc);
        ++taken;
    }
    return taken;
}

// ---------------------------------------------------------------- JSON

nlohmann::json recordToJson(const Record &r) {
    nlohmann::json fixed = nlohmann::json::array();
    for (const auto &f : r.fixedActions)
        fixed.push_back({{"action", f.action}, {"gold", f.gold}, {"card", f.card},
                         {"relic", f.relic}, {"info", f.info}});
    nlohmann::json pathXs = nlohmann::json::array();
    for (const auto &p : r.mapPathXs) pathXs.push_back({p[0], p[1], p[2]});
    return {{"obs.fixed_observation", r.fixedObservation},
            {"obs.deck.cards", r.deckCards}, {"obs.deck.upgrades", r.deckUpgrades},
            {"obs.deck.misc", r.deckMisc}, {"obs.act", r.act},
            {"obs.relics.relics", r.relics}, {"obs.relics.relic_counters", r.relicCounters},
            {"obs.potions", r.potions},
            {"obs.map.xs", r.mapXs}, {"obs.map.ys", r.mapYs}, {"obs.map.roomTypes", r.mapRooms},
            {"obs.map.pathXs", pathXs},
            {"obs.map.burningEliteX", r.burningEliteX}, {"obs.map.burningEliteY", r.burningEliteY},
            {"obs.mapX", r.mapX}, {"obs.mapY", r.mapY},
            {"cards_offered.cards", r.offeredCards}, {"cards_offered.upgrades", r.offeredUpgrades},
            {"relics_offered", r.offeredRelics}, {"potions_offered", r.offeredPotions},
            {"fixed_actions", fixed}, {"paths_offered", r.paths},
            {"screen_state", r.screenState}, {"select_screen_type", r.selectScreenType},
            {"obs.v2.run_counters", r.runCounters}, {"obs.v2.fought", r.foughtEncounters},
            {"offer_prices", r.offerPrices}};
}

bool buildPublicLeafRecord(const GameContext &gc, nlohmann::json &out, std::string *reason) {
    if (gc.outcome != GameOutcome::UNDECIDED) {
        if (reason) *reason = "decided_outcome";
        return false;
    }
    Choice choice;
    if (gc.screenState != ScreenState::BATTLE && buildChoice(gc, choice, reason)) {
        out = recordToJson(choice.record);
        return true;
    }
    const bool battle = gc.screenState == ScreenState::BATTLE;
    const bool match = gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::MATCH_AND_KEEP;
    if (!battle && !match) return false;
    Record record;
    encodeObservation(gc, record);
    record.screenState = static_cast<int>(gc.screenState);
    out = recordToJson(record);
    if (battle) {
        // OOC adapter boundaries precede BattleContext construction: this is the
        // encounter just entered, visible now, never a future encounter queue.
        const int encounter = static_cast<int>(gc.info.encounter);
        if (encounter <= static_cast<int>(MonsterEncounter::INVALID)
                || encounter > static_cast<int>(MonsterEncounter::MYSTERIOUS_SPHERE_EVENT)) {
            if (reason) *reason = "invalid_public_encounter";
            return false;
        }
        out["leaf.publicBattleEncounter"] = encounter;
    } else {
        out["leaf.matchAttempts"] = gc.info.eventData;
        auto &slots = out["leaf.matchSlots"] = nlohmann::json::array();
        for (int i = 0; i < static_cast<int>(gc.info.toSelectCards.size()); ++i) {
            const auto &slot = gc.info.toSelectCards[i];
            const bool seen = slot.deckIdx != GameContext::MATCH_AND_KEEP_UNSEEN;
            slots.push_back({{"position", i}, {"state", slot.deckIdx},
                {"card", seen ? static_cast<int>(slot.card.id) : -1},
                {"upgrades", seen ? slot.card.getUpgraded() : 0}});
        }
    }
    if (reason) reason->clear();
    return true;
}

Record recordFromJson(const nlohmann::json &j) {
    Record r;
    const auto ints = [&](const char *k) { return j.at(k).get<std::vector<int>>(); };
    r.fixedObservation = ints("obs.fixed_observation");
    r.deckCards = ints("obs.deck.cards");
    r.deckUpgrades = ints("obs.deck.upgrades");
    if (j.contains("obs.deck.misc")) r.deckMisc = ints("obs.deck.misc");
    r.act = j.value("obs.act", 0);
    r.relics = ints("obs.relics.relics");
    if (j.contains("obs.relics.relic_counters")) r.relicCounters = ints("obs.relics.relic_counters");
    r.potions = ints("obs.potions");
    r.mapXs = ints("obs.map.xs");
    r.mapYs = ints("obs.map.ys");
    r.mapRooms = ints("obs.map.roomTypes");
    for (const auto &p : j.at("obs.map.pathXs")) r.mapPathXs.push_back({p.at(0).get<int>(), p.at(1).get<int>(), p.at(2).get<int>()});
    r.burningEliteX = j.value("obs.map.burningEliteX", -1);
    r.burningEliteY = j.value("obs.map.burningEliteY", -1);
    r.mapX = j.at("obs.mapX").get<int>();
    r.mapY = j.at("obs.mapY").get<int>();
    r.offeredCards = ints("cards_offered.cards");
    r.offeredUpgrades = ints("cards_offered.upgrades");
    r.offeredRelics = ints("relics_offered");
    r.offeredPotions = ints("potions_offered");
    for (const auto &f : j.at("fixed_actions")) {
        FixedChoice c;
        c.action = f.at("action").get<int>();
        c.gold = f.value("gold", 0);
        c.card = f.value("card", kCardInvalid);
        c.relic = f.value("relic", kRelicInvalid);
        c.info = f.value("info", 0);
        r.fixedActions.push_back(c);
    }
    r.paths = ints("paths_offered");
    r.screenState = j.at("screen_state").get<int>();
    r.selectScreenType = j.at("select_screen_type").get<int>();
    if (j.contains("obs.v2.run_counters")) r.runCounters = ints("obs.v2.run_counters");
    if (j.contains("obs.v2.fought")) r.foughtEncounters = ints("obs.v2.fought");
    if (j.contains("offer_prices")) r.offerPrices = ints("offer_prices");
    return r;
}

// ---------------------------------------------------------------- network

namespace {

struct Tensor { std::vector<int> shape; std::vector<float> data; };

float dot(const float *a, const float *b, int n) {
    float s[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    int i = 0;
    for (; i + 8 <= n; i += 8)
        for (int k = 0; k < 8; ++k) s[k] += a[i + k] * b[i + k];
    float t = ((s[0] + s[1]) + (s[2] + s[3])) + ((s[4] + s[5]) + (s[6] + s[7]));
    for (; i < n; ++i) t += a[i] * b[i];
    return t;
}

// y[t] (+)= W x[t] + b for n tokens.
void linearScalar(const Net::Linear &l, const float *x, int n, float *y, bool accumulate) {
    for (int t = 0; t < n; ++t) {
        const float *xt = x + std::size_t(t) * l.in;
        float *yt = y + std::size_t(t) * l.out;
        for (int o = 0; o < l.out; ++o) {
            const float v = dot(l.w.data() + std::size_t(o) * l.in, xt, l.in) + (l.b.empty() ? 0.f : l.b[o]);
            yt[o] = accumulate ? yt[o] + v : v;
        }
    }
}

// The same arithmetic as linearScalar, bit for bit: each output keeps dot()'s
// eight partial sums (one AVX lane each, separate multiply and add, no FMA)
// and its reduction order. Tiles of 3 tokens x 4 outputs reuse every load.
__attribute__((target("avx"), always_inline)) inline float reduce8(__m256 v) {
    // ((s0 + s1) + (s2 + s3)) + ((s4 + s5) + (s6 + s7)), as in dot().
    const __m128 pairs = _mm_hadd_ps(_mm256_castps256_ps128(v), _mm256_extractf128_ps(v, 1));
    const __m128 quads = _mm_hadd_ps(pairs, pairs);
    return _mm_cvtss_f32(_mm_add_ss(quads, _mm_shuffle_ps(quads, quads, 1)));
}

// reduce8 of four vectors at once: lane k of the result is reduce8(vk), with the
// same pair, quad and final additions.
__attribute__((target("avx"), always_inline)) inline __m128 reduce4(__m256 a, __m256 b, __m256 c, __m256 d) {
    const __m256 quads = _mm256_hadd_ps(_mm256_hadd_ps(a, b), _mm256_hadd_ps(c, d));
    return _mm_add_ps(_mm256_castps256_ps128(quads), _mm256_extractf128_ps(quads, 1));
}

__attribute__((target("avx"))) void linearAvx(const Net::Linear &l, const float *x, int n, float *y, bool accumulate) {
    constexpr int TT = 3, OO = 4;
    const int in = l.in;
    const float *w = l.w.data();
    const auto store = [&](int t, int o, float v) {
        v += l.b.empty() ? 0.f : l.b[o];
        float &out = y[std::size_t(t) * l.out + o];
        out = accumulate ? out + v : v;
    };
    const auto single = [&](int t, int o) {
        store(t, o, dot(w + std::size_t(o) * in, x + std::size_t(t) * in, in));
    };
    const int fullT = n / TT * TT, fullO = l.out / OO * OO;
    for (int t = 0; t < fullT; t += TT) {
        for (int o = 0; o < fullO; o += OO) {
            __m256 acc[OO][TT];
            for (auto &row : acc) for (auto &a : row) a = _mm256_setzero_ps();
            for (int i = 0; i < in; i += 8) {
                __m256 v[TT];
                for (int q = 0; q < TT; ++q) v[q] = _mm256_loadu_ps(x + std::size_t(t + q) * in + i);
                for (int p = 0; p < OO; ++p) {
                    const __m256 r = _mm256_loadu_ps(w + std::size_t(o + p) * in + i);
                    for (int q = 0; q < TT; ++q) acc[p][q] = _mm256_add_ps(acc[p][q], _mm256_mul_ps(r, v[q]));
                }
            }
            // reduce4 gives store()'s four sums at once; the bias and accumulate
            // additions are the same per-element operations.
            const __m128 bias = l.b.empty() ? _mm_setzero_ps() : _mm_loadu_ps(l.b.data() + o);
            for (int q = 0; q < TT; ++q) {
                float *out = y + std::size_t(t + q) * l.out + o;
                __m128 v = _mm_add_ps(reduce4(acc[0][q], acc[1][q], acc[2][q], acc[3][q]), bias);
                if (accumulate) v = _mm_add_ps(_mm_loadu_ps(out), v);
                _mm_storeu_ps(out, v);
            }
        }
        for (int o = fullO; o < l.out; ++o)
            for (int q = 0; q < TT; ++q) single(t + q, o);
    }
    // Leftover tokens one at a time, four outputs per tile.
    for (int t = fullT; t < n; ++t) {
        const float *xt = x + std::size_t(t) * in;
        for (int o = 0; o < fullO; o += OO) {
            __m256 acc[OO];
            for (auto &a : acc) a = _mm256_setzero_ps();
            for (int i = 0; i < in; i += 8) {
                const __m256 v = _mm256_loadu_ps(xt + i);
                for (int p = 0; p < OO; ++p)
                    acc[p] = _mm256_add_ps(acc[p], _mm256_mul_ps(_mm256_loadu_ps(w + std::size_t(o + p) * in + i), v));
            }
            const __m128 bias = l.b.empty() ? _mm_setzero_ps() : _mm_loadu_ps(l.b.data() + o);
            float *out = y + std::size_t(t) * l.out + o;
            __m128 r = _mm_add_ps(reduce4(acc[0], acc[1], acc[2], acc[3]), bias);
            if (accumulate) r = _mm_add_ps(_mm_loadu_ps(out), r);
            _mm_storeu_ps(out, r);
        }
        for (int o = fullO; o < l.out; ++o) single(t, o);
    }
}

// linearAvx with two tokens per 512-bit register (low half token t, high half
// token t + 1), bit for bit: every lane keeps its token's and output's partial
// sum, with separate multiply and add. The explicitly rounded intrinsics (round
// to nearest, as the default) keep the compiler from fusing them into FMAs,
// which AVX-512 would allow. Tiles of 6 tokens x 4 outputs; leftover tokens go
// to linearAvx.
__attribute__((target("avx512f,avx512dq"))) void linearAvx512(const Net::Linear &l, const float *x, int n, float *y,
                                                               bool accumulate) {
    constexpr int PP = 3, OO = 4, rounding = _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC;
    const int in = l.in;
    const float *w = l.w.data();
    const int fullT = n / (2 * PP) * (2 * PP), fullO = l.out / OO * OO;
    for (int t = 0; t < fullT; t += 2 * PP) {
        for (int o = 0; o < fullO; o += OO) {
            __m512 acc[OO][PP];
            for (auto &row : acc) for (auto &a : row) a = _mm512_setzero_ps();
            for (int i = 0; i < in; i += 8) {
                __m512 v[PP];
                for (int q = 0; q < PP; ++q)
                    v[q] = _mm512_insertf32x8(_mm512_castps256_ps512(_mm256_loadu_ps(x + std::size_t(t + 2 * q) * in + i)),
                                              _mm256_loadu_ps(x + std::size_t(t + 2 * q + 1) * in + i), 1);
                for (int p = 0; p < OO; ++p) {
                    const __m512 r = _mm512_broadcast_f32x8(_mm256_loadu_ps(w + std::size_t(o + p) * in + i));
                    for (int q = 0; q < PP; ++q)
                        acc[p][q] = _mm512_add_round_ps(acc[p][q], _mm512_mul_round_ps(r, v[q], rounding), rounding);
                }
            }
            const __m128 bias = l.b.empty() ? _mm_setzero_ps() : _mm_loadu_ps(l.b.data() + o);
            for (int q = 0; q < PP; ++q)
                for (int half = 0; half < 2; ++half) {
                    __m256 part[OO];
                    for (int p = 0; p < OO; ++p)
                        part[p] = half ? _mm512_extractf32x8_ps(acc[p][q], 1) : _mm512_castps512_ps256(acc[p][q]);
                    float *out = y + std::size_t(t + 2 * q + half) * l.out + o;
                    __m128 r = _mm_add_ps(reduce4(part[0], part[1], part[2], part[3]), bias);
                    if (accumulate) r = _mm_add_ps(_mm_loadu_ps(out), r);
                    _mm_storeu_ps(out, r);
                }
        }
        for (int o = fullO; o < l.out; ++o)
            for (int q = 0; q < 2 * PP; ++q) {
                float v = dot(w + std::size_t(o) * in, x + std::size_t(t + q) * in, in) + (l.b.empty() ? 0.f : l.b[o]);
                float &out = y[std::size_t(t + q) * l.out + o];
                out = accumulate ? out + v : v;
            }
    }
    if (fullT < n) linearAvx(l, x + std::size_t(fullT) * in, n - fullT, y + std::size_t(fullT) * l.out, accumulate);
}

// STS_OOC_HEART1_SCALAR=1 forces the reference loop (for the bit-equality check).
bool useAvx() {
    static const bool avx = __builtin_cpu_supports("avx") && !std::getenv("STS_OOC_HEART1_SCALAR");
    return avx;
}

bool useAvx512() {
    static const bool avx512 = useAvx() && __builtin_cpu_supports("avx512f") && __builtin_cpu_supports("avx512dq");
    return avx512;
}

void linear(const Net::Linear &l, const float *x, int n, float *y, bool accumulate = false) {
    if (l.in % 8 == 0 && useAvx512()) linearAvx512(l, x, n, y, accumulate);
    else if (l.in % 8 == 0 && useAvx()) linearAvx(l, x, n, y, accumulate);
    else linearScalar(l, x, n, y, accumulate);
}

// std::exp(float) for an array, four lanes at a time. The lanes repeat glibc's
// __expf_fma fast path (sysdeps/ieee754/flt-32/e_expf.c, EXP2F_TABLE_BITS 5,
// the same constants, table and fused operations); its special-case inputs
// (|x| >= ~88, inf, nan) go to std::exp. Used only after a start-up self-test
// finds it bitwise equal to this process's std::exp, so a libm or CPU with a
// different expf keeps the scalar calls.
namespace expf4 {
constexpr std::uint64_t kTable[32] = {
    0x3ff0000000000000, 0x3fefd9b0d3158574, 0x3fefb5586cf9890f, 0x3fef9301d0125b51, 0x3fef72b83c7d517b,
    0x3fef54873168b9aa, 0x3fef387a6e756238, 0x3fef1e9df51fdee1, 0x3fef06fe0a31b715, 0x3feef1a7373aa9cb,
    0x3feedea64c123422, 0x3feece086061892d, 0x3feebfdad5362a27, 0x3feeb42b569d4f82, 0x3feeab07dd485429,
    0x3feea47eb03a5585, 0x3feea09e667f3bcd, 0x3fee9f75e8ec5f74, 0x3feea11473eb0187, 0x3feea589994cce13,
    0x3feeace5422aa0db, 0x3feeb737b0cdc5e5, 0x3feec49182a3f090, 0x3feed503b23e255d, 0x3feee89f995ad3ad,
    0x3feeff76f2fb5e47, 0x3fef199bdd85529c, 0x3fef3720dcef9069, 0x3fef5818dcfba487, 0x3fef7c97337b9b5f,
    0x3fefa4afa2a490da, 0x3fefd0765b6e4540};
constexpr std::uint64_t kShift = 0x4338000000000000, kInvLn2N = 0x40471547652b82fe, kC0 = 0x3ebc6af84b912394,
                        kC1 = 0x3f2ebfce50fac4f3, kC2 = 0x3f962e42ff0c52d6;

__attribute__((target("avx2,fma"))) void apply(float *v, int n) {
    const auto bcast = [](std::uint64_t bits) { double d; std::memcpy(&d, &bits, 8); return d; };
    const __m256d shift = _mm256_set1_pd(bcast(kShift)), invLn2N = _mm256_set1_pd(bcast(kInvLn2N));
    const __m256d c0 = _mm256_set1_pd(bcast(kC0)), c1 = _mm256_set1_pd(bcast(kC1)), c2 = _mm256_set1_pd(bcast(kC2));
    const __m256d one = _mm256_set1_pd(1.0);
    const __m256i mask = _mm256_set1_epi64x(31);
    const __m128i abstopLimit = _mm_set1_epi32(0x42a), abstopMask = _mm_set1_epi32(0x7ff);
    int i = 0;
    for (; i + 4 <= n; i += 4) {
        const __m128 x = _mm_loadu_ps(v + i);
        const __m128i abstop = _mm_and_si128(_mm_srli_epi32(_mm_castps_si128(x), 20), abstopMask);
        const int special = _mm_movemask_ps(_mm_castsi128_ps(_mm_cmpgt_epi32(abstop, abstopLimit)));
        const __m256d xd = _mm256_cvtps_pd(x);
        __m256d kd = _mm256_fmadd_pd(invLn2N, xd, shift);
        const __m256i ki = _mm256_castpd_si256(kd);
        kd = _mm256_sub_pd(kd, shift);
        const __m256d r = _mm256_fmsub_pd(invLn2N, xd, kd);
        const __m256i t = _mm256_add_epi64(
            _mm256_i64gather_epi64(reinterpret_cast<const long long *>(kTable), _mm256_and_si256(ki, mask), 8),
            _mm256_slli_epi64(ki, 47));
        const __m256d z = _mm256_fmadd_pd(r, c0, c1);
        const __m256d r2 = _mm256_mul_pd(r, r);
        __m256d y = _mm256_fmadd_pd(r, c2, one);
        y = _mm256_fmadd_pd(z, r2, y);
        y = _mm256_mul_pd(y, _mm256_castsi256_pd(t));
        float out[4];
        _mm_storeu_ps(out, _mm256_cvtpd_ps(y));
        for (int k = 0; k < 4; ++k) v[i + k] = (special >> k) & 1 ? std::exp(v[i + k]) : out[k];
    }
    for (; i < n; ++i) v[i] = std::exp(v[i]);
}

// Every 4093rd bit pattern (1.05M floats, all signs and exponents) plus the
// special-case boundaries.
bool selfTest() {
    std::vector<float> in, got;
    for (std::uint64_t b = 0; b <= 0xffffffffull; b += 4093) {
        float f;
        const std::uint32_t u = std::uint32_t(b);
        std::memcpy(&f, &u, 4);
        in.push_back(f);
    }
    for (std::uint32_t u : {0x42b17217u, 0x42b17218u, 0xc2cff1b4u, 0xc2cff1b5u, 0xc2ce8ecfu, 0xc2ce8ed0u,
                            0x42a00000u, 0x42afffffu, 0xc2afffffu, 0x80000000u, 0x0u, 0x7f800000u, 0xff800000u}) {
        float f;
        std::memcpy(&f, &u, 4);
        in.push_back(f);
    }
    got = in;
    apply(got.data(), int(got.size()));
    for (std::size_t k = 0; k < in.size(); ++k) {
        const float want = std::exp(in[k]);
        if (std::memcmp(&want, &got[k], 4) != 0 && !(std::isnan(want) && std::isnan(got[k]))) return false;
    }
    return true;
}

bool usable() {
    static const bool ok = useAvx() && __builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma") && selfTest();
    return ok;
}
}  // namespace expf4

// v[k] = std::exp(v[k]).
void expInPlace(float *v, int n) {
    if (expf4::usable()) return expf4::apply(v, n);
    for (int k = 0; k < n; ++k) v[k] = std::exp(v[k]);
}

// dot()'s eight partial sums of q (in registers) and k.
__attribute__((target("avx"), always_inline)) inline __m256 scorePartial(const __m256 *q, const float *k, int chunks) {
    __m256 s = _mm256_setzero_ps();
    for (int c = 0; c < chunks; ++c) s = _mm256_add_ps(s, _mm256_mul_ps(q[c], _mm256_loadu_ps(k + 8 * c)));
    return s;
}

// One attention head for queries [q0, n), bit for bit the scalar loop in
// forwardRecord: each score keeps dot()'s partial sums and reduction (eight
// keys reduced at once), max/exp/sum stay sequential, and each output
// dimension sums p * v over the keys in key order. Needs headDim % 8 == 0, <= 32.
__attribute__((target("avx"))) void attendHeadAvx(const float *qkv, int n, int q0, int dim, int off, int headDim,
                                                  float scale, float *scores, float *att) {
    const std::size_t stride = std::size_t(3) * dim;
    const int chunks = headDim / 8;
    for (int i = q0; i < n; ++i) {
        const float *q = qkv + std::size_t(i) * stride + off;
        __m256 qc[4];
        for (int c = 0; c < chunks; ++c) qc[c] = _mm256_loadu_ps(q + 8 * c);
        const float *keys = qkv + dim + off;
#define PARTIAL(j) scorePartial(qc, keys + std::size_t(j) * stride, chunks)
        int j = 0;
        for (; j + 8 <= n; j += 8) {
            const __m128 lo = reduce4(PARTIAL(j), PARTIAL(j + 1), PARTIAL(j + 2), PARTIAL(j + 3));
            const __m128 hi = reduce4(PARTIAL(j + 4), PARTIAL(j + 5), PARTIAL(j + 6), PARTIAL(j + 7));
            _mm256_storeu_ps(scores + j, _mm256_mul_ps(_mm256_set_m128(hi, lo), _mm256_set1_ps(scale)));
        }
        for (; j < n; ++j) scores[j] = reduce8(PARTIAL(j)) * scale;
#undef PARTIAL
        float mx = -std::numeric_limits<float>::infinity();
        for (int t = 0; t < n; ++t) mx = std::max(mx, scores[t]);
        float sum = 0;
        for (int t = 0; t < n; ++t) scores[t] -= mx;
        expInPlace(scores, n);
        for (int t = 0; t < n; ++t) sum += scores[t];
        // The same divisions, eight at a time.
        int t = 0;
        for (; t + 8 <= n; t += 8) _mm256_storeu_ps(scores + t, _mm256_div_ps(_mm256_loadu_ps(scores + t), _mm256_set1_ps(sum)));
        for (; t < n; ++t) scores[t] = scores[t] / sum;
        __m256 o[4];
        for (int c = 0; c < chunks; ++c) o[c] = _mm256_setzero_ps();
        for (int t = 0; t < n; ++t) {
            const __m256 p = _mm256_set1_ps(scores[t]);
            const float *v = qkv + std::size_t(t) * stride + 2 * dim + off;
            for (int c = 0; c < chunks; ++c) o[c] = _mm256_add_ps(o[c], _mm256_mul_ps(p, _mm256_loadu_ps(v + 8 * c)));
        }
        float *out = att + std::size_t(i) * dim + off;
        for (int c = 0; c < chunks; ++c) _mm256_storeu_ps(out + 8 * c, o[c]);
    }
}

void rmsNorm(const float *x, const std::vector<float> &w, float *y) {
    const int dim = int(w.size());
    float ss = 0;
    for (int i = 0; i < dim; ++i) ss += x[i] * x[i];
    const float inv = 1.0f / std::sqrt(ss / dim + kNormEps);
    for (int i = 0; i < dim; ++i) y[i] = x[i] * inv * w[i];
}

void addEmbedding(const Net::Embedding &e, int idx, float *out) {
    if (idx < 0 || idx >= e.rows) throw std::runtime_error("heart1: embedding index out of range");
    const float *row = e.w.data() + std::size_t(idx) * e.dim;
    for (int i = 0; i < e.dim; ++i) out[i] += row[i];
}

// Projected FixedVec rows (sinusoidal features, projection, bias) by weights
// and input bits. A row's projection does not depend on the other rows of its
// call, so adding the remembered row is the same addition linear() makes.
// Per thread and shared by every loaded net, whose row widths can differ (a
// width-64 student serving next to a width-256 teacher), so the index stores
// each row's float offset. Dropped whole when full.
struct FixedVecMemo {
    struct Key {
        std::uint64_t id;
        std::array<std::uint32_t, 4> bits;
        bool operator==(const Key &o) const { return id == o.id && bits == o.bits; }
    };
    struct Hash {
        std::size_t operator()(const Key &k) const {
            std::uint64_t h = k.id * 0x9E3779B97F4A7C15ull;
            for (auto b : k.bits) h = (h ^ b) * 0x100000001B3ull;
            return std::size_t(h ^ (h >> 29));
        }
    };
    static constexpr std::size_t kMaxFloats = std::size_t(1) << 20;
    std::unordered_map<Key, std::size_t, Hash> index;  // offset into rows
    std::vector<float> rows;
};
thread_local FixedVecMemo fixedVecMemo;

std::uint64_t newMemoId() {
    static std::atomic<std::uint64_t> next{1};
    return next++;
}

void sinusoids(const Net::FixedVec &f, const float *x, float *s) {
    const int half = int(f.invFreq.size()), dim = 2 * half;
    for (int k = 0; k < f.features; ++k)
        for (int j = 0; j < half; ++j) {
            const float a = x[k] * f.invFreq[j];
            s[std::size_t(k) * dim + j] = std::sin(a);
            s[std::size_t(k) * dim + half + j] = std::cos(a);
        }
}

// addFixedVecRows through the memo (weights with at most four features; off
// under STS_OOC_HEART1_SCALAR=1).
void addFixedVecRowsMemo(const Net::FixedVec &f, const float *x, int n, float *out) {
    auto &m = fixedVecMemo;
    const int dim = f.proj.out, sdim = 2 * int(f.invFreq.size());
    if (m.rows.size() + std::size_t(n) * dim > FixedVecMemo::kMaxFloats) { m.index.clear(); m.rows.clear(); }
    std::vector<std::size_t> offset(n);
    std::vector<int> missRows;
    for (int r = 0; r < n; ++r) {
        FixedVecMemo::Key key{f.memoId, {0, 0, 0, 0}};
        std::memcpy(key.bits.data(), x + std::size_t(r) * f.features, sizeof(float) * f.features);
        const auto [it, inserted] = m.index.emplace(key, m.rows.size());
        if (inserted) { m.rows.resize(m.rows.size() + dim); missRows.push_back(r); }
        offset[r] = it->second;
    }
    if (!missRows.empty()) {
        const std::size_t width = std::size_t(f.features) * sdim;
        std::vector<float> s(width * missRows.size()), proj(std::size_t(dim) * missRows.size());
        for (std::size_t i = 0; i < missRows.size(); ++i)
            sinusoids(f, x + std::size_t(missRows[i]) * f.features, s.data() + i * width);
        linear(f.proj, s.data(), int(missRows.size()), proj.data());
        for (std::size_t i = 0; i < missRows.size(); ++i)
            std::copy_n(proj.data() + i * dim, dim, m.rows.data() + offset[missRows[i]]);
    }
    for (int r = 0; r < n; ++r) {
        const float *v = m.rows.data() + offset[r];
        float *o = out + std::size_t(r) * dim;
        for (int d = 0; d < dim; ++d) o[d] = o[d] + v[d];
    }
}

// FixedVecEmbedding: sinusoidal features then a projection.
void addFixedVec(const Net::FixedVec &f, const float *x, float *out) {
    if (f.memoId && f.features <= 4 && useAvx()) return addFixedVecRowsMemo(f, x, 1, out);
    const int half = int(f.invFreq.size()), dim = 2 * half;
    std::vector<float> s(std::size_t(f.features) * dim);
    for (int k = 0; k < f.features; ++k)
        for (int j = 0; j < half; ++j) {
            const float a = x[k] * f.invFreq[j];
            s[std::size_t(k) * dim + j] = std::sin(a);
            s[std::size_t(k) * dim + half + j] = std::cos(a);
        }
    linear(f.proj, s.data(), 1, out, /*accumulate=*/true);
}

// addFixedVec for n consecutive rows (x: n x features) in one projection call:
// every row gets the same additions in the same order.
void addFixedVecRows(const Net::FixedVec &f, const float *x, int n, float *out) {
    if (n == 0) return;
    if (f.memoId && f.features <= 4 && useAvx()) return addFixedVecRowsMemo(f, x, n, out);
    const int half = int(f.invFreq.size()), dim = 2 * half;
    const std::size_t width = std::size_t(f.features) * dim;
    std::vector<float> s(width * n);
    for (int r = 0; r < n; ++r)
        for (int k = 0; k < f.features; ++k)
            for (int j = 0; j < half; ++j) {
                const float a = x[std::size_t(r) * f.features + k] * f.invFreq[j];
                s[r * width + std::size_t(k) * dim + j] = std::sin(a);
                s[r * width + std::size_t(k) * dim + half + j] = std::cos(a);
            }
    linear(f.proj, s.data(), n, out, /*accumulate=*/true);
}

struct DagFeatures {
    std::vector<int> minE, maxE, dR;
    std::vector<bool> reach;
    std::vector<int> destRooms;
    std::vector<std::array<int, 3>> optCone;
    std::vector<int> optBurn;
};

// map_dag_features.
DagFeatures mapDagFeatures(const Record &r) {
    const int n = int(r.mapXs.size());
    std::map<std::pair<int, int>, int> idx;
    for (int j = 0; j < n; ++j) idx.emplace(std::make_pair(r.mapXs[j], r.mapYs[j]), j);
    const auto find = [&](int x, int y) {
        const auto it = idx.find({x, y});
        return it == idx.end() ? -1 : it->second;
    };
    std::vector<std::vector<int>> succ(n);
    for (int j = 0; j < n; ++j)
        for (int e : r.mapPathXs[j]) {
            const int k = find(e, r.mapYs[j] + 1);
            if (e >= 0 && k >= 0) succ[j].push_back(k);
        }
    const int ELITE = static_cast<int>(Room::ELITE), REST = static_cast<int>(Room::REST);
    DagFeatures d;
    d.minE.assign(n, 0); d.maxE.assign(n, 0); d.dR.assign(n, kMapAggCap);
    std::vector<int> order(n);
    for (int j = 0; j < n; ++j) order[j] = j;
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return -r.mapYs[a] < -r.mapYs[b]; });
    for (int j : order) {
        const int e = r.mapRooms[j] == ELITE ? 1 : 0;
        int mn = 0, mx = 0, dr = std::numeric_limits<int>::max();
        if (!succ[j].empty()) {
            mn = std::numeric_limits<int>::max(); mx = std::numeric_limits<int>::min();
            for (int k : succ[j]) { mn = std::min(mn, d.minE[k]); mx = std::max(mx, d.maxE[k]); dr = std::min(dr, d.dR[k]); }
        }
        d.minE[j] = e + mn;
        d.maxE[j] = e + mx;
        if (r.mapRooms[j] == REST) d.dR[j] = 0;
        else if (!succ[j].empty()) d.dR[j] = std::min(kMapAggCap, 1 + dr);
    }
    std::vector<bool> reachesBurn(n, false);
    const int bn = r.burningEliteX >= 0 ? find(r.burningEliteX, r.burningEliteY) : -1;
    if (bn >= 0)
        for (int j : order) {
            bool any = j == bn;
            for (int k : succ[j]) any = any || reachesBurn[k];
            reachesBurn[j] = any;
        }
    const int cur = find(r.mapX, r.mapY);
    std::vector<int> frontier;
    if (cur >= 0) frontier = succ[cur];
    else for (int j = 0; j < n; ++j) if (r.mapYs[j] == 0) frontier.push_back(j);
    for (int px : r.paths) {
        const int k = find(px, r.mapY + 1);
        if (k >= 0 && std::find(frontier.begin(), frontier.end(), k) == frontier.end()) frontier.push_back(k);
    }
    d.reach.assign(n, false);
    std::vector<int> stack = frontier;
    while (!stack.empty()) {
        const int j = stack.back();
        stack.pop_back();
        if (!d.reach[j]) {
            d.reach[j] = true;
            stack.insert(stack.end(), succ[j].begin(), succ[j].end());
        }
    }
    for (int px : r.paths) {
        const int k = find(px, r.mapY + 1);
        d.destRooms.push_back(k >= 0 ? r.mapRooms[k] : 0);
        if (k >= 0) {
            d.optCone.push_back({d.minE[k], d.maxE[k], d.dR[k]});
            d.optBurn.push_back(reachesBurn[k] ? 1 : 0);
        } else {
            d.optCone.push_back({0, 0, kMapAggCap});
            d.optBurn.push_back(0);
        }
    }
    return d;
}

}  // namespace

bool Net::load(const std::string &file, std::string *error) {
    forwardId_ = 0;
    const auto fail = [&](const std::string &why) {
        if (error) *error = why;
        return false;
    };
    std::ifstream in(file, std::ios::binary);
    if (!in) return fail("cannot open " + file);
    char magic[8];
    in.read(magic, 8);
    if (!in || std::memcmp(magic, "HEART1W\x01", 8) != 0) return fail("bad magic in " + file);
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char *>(&count), 4);
    std::map<std::string, Tensor> tensors;
    for (std::uint32_t i = 0; in && i < count; ++i) {
        std::uint32_t len = 0, ndim = 0;
        in.read(reinterpret_cast<char *>(&len), 4);
        std::string name(len, '\0');
        in.read(name.data(), len);
        in.read(reinterpret_cast<char *>(&ndim), 4);
        Tensor t;
        std::size_t total = 1;
        for (std::uint32_t d = 0; d < ndim; ++d) {
            std::uint32_t dim = 0;
            in.read(reinterpret_cast<char *>(&dim), 4);
            t.shape.push_back(int(dim));
            total *= dim;
        }
        t.data.resize(total);
        in.read(reinterpret_cast<char *>(t.data.data()), std::streamsize(total * sizeof(float)));
        tensors.emplace(std::move(name), std::move(t));
    }
    if (!in) return fail("truncated weights file " + file);

    // Sizes come from the tensors (heart1: dim 256, hidden 1024, 4 layers). The
    // head count is not in a state dict: the export's meta.n_heads, else
    // silverbot's ModelHP default 8. meta.trim_map != 0: the network was trained
    // on records without the map rows below the current floor (see forward).
    const auto shapeOf = [&](const std::string &name) {
        const auto it = tensors.find(name);
        return it == tensors.end() ? std::vector<int>{} : it->second.shape;
    };
    const auto meta = [&](const std::string &name, float fallback) {
        const auto it = tensors.find(name);
        if (it == tensors.end()) return fallback;
        return it->second.data.size() == 1 ? it->second.data[0] : std::numeric_limits<float>::quiet_NaN();
    };
    const auto normShape = shapeOf("norm.w"), hiddenShape = shapeOf("layers.0.mlp.w1.weight");
    if (normShape.size() != 1 || hiddenShape.size() != 2) return fail("cannot read the network size from " + file);
    const int dim = normShape[0], hidden = hiddenShape[0];
    const float headsMeta = meta("meta.n_heads", 8.f), trimMeta = meta("meta.trim_map", 0.f);
    const int heads = int(headsMeta);
    int layers = 0;
    while (tensors.count("layers." + std::to_string(layers) + ".norm1.w")) ++layers;
    if (!(float(heads) == headsMeta) || heads < 1 || dim < 2 || dim % 2 != 0 || dim % heads != 0 || layers < 1
        || hidden < 1 || !(trimMeta == 0.f || trimMeta == 1.f))
        return fail("bad network size or meta tensors in " + file);
    dim_ = dim; heads_ = heads; hidden_ = hidden; trimMap_ = trimMeta != 0.f;

    std::string missing;
    const auto take = [&](const std::string &name, std::vector<int> shape) -> std::vector<float> {
        const auto it = tensors.find(name);
        if (it == tensors.end()) { missing += " " + name; return {}; }
        if (!shape.empty() && shape[0] < 0) shape[0] = it->second.shape.empty() ? 0 : it->second.shape[0];
        if (it->second.shape != shape) { missing += " shape:" + name; return {}; }
        return it->second.data;
    };
    const auto embedding = [&](const std::string &name) {
        Embedding e;
        e.w = take(name, {-1, dim});
        e.rows = int(e.w.size() / dim);
        e.dim = dim;
        return e;
    };
    const auto lin = [&](const std::string &prefix, int out, int inDim, bool bias) {
        Linear l;
        l.out = out; l.in = inDim;
        l.w = take(prefix + ".weight", {out, inDim});
        if (bias) l.b = take(prefix + ".bias", {out});
        return l;
    };
    const auto fixedVec = [&](const std::string &prefix, int features) {
        FixedVec f;
        f.features = features;
        f.invFreq = take(prefix + ".num_embed.inv_freq", {dim / 2});
        f.proj = lin(prefix + ".proj", dim, features * dim, true);
        f.memoId = newMemoId();
        return f;
    };
    const std::string O = "obs_embed.component_embeddings.";
    const std::string F = O + "fixed_obs.scalar_embedding.component_embeddings.";
    const std::string M = O + "map_nodes.element_embedding.component_embeddings.";
    const std::string C = "choice_embed.component_embeddings.";
    const std::string FX = C + "fixed.element_embedding.component_embeddings.";
    const std::string PA = C + "paths.element_embedding.component_embeddings.";
    card_ = embedding(O + "deck.element_embedding.component_embeddings.0.embedding.weight");
    upgrade_ = embedding(O + "deck.element_embedding.component_embeddings.1.weight");
    relic_ = embedding(O + "relics.element_embedding.embedding.weight");
    potion_ = embedding(O + "potions.element_embedding.embedding.weight");
    fixedObs_ = fixedVec(F + "fixed_observation", 5);
    boss_ = embedding(F + "boss.weight");
    ascension_ = embedding(F + "ascension.weight");
    keyRuby_ = embedding(F + "key_ruby.weight");
    keyEmerald_ = embedding(F + "key_emerald.weight");
    keySapphire_ = embedding(F + "key_sapphire.weight");
    screen_ = embedding(F + "screen_state.embedding.weight");
    mapRoom_ = embedding(M + "room.embedding.weight");
    isCurrent_ = embedding(M + "is_current.embedding.weight");
    pos_ = fixedVec(M + "pos", 2);
    pathXs_ = fixedVec(M + "path_xs", 3);
    rel_ = fixedVec(M + "rel", 2);
    reachable_ = embedding(M + "reachable.embedding.weight");
    agg_ = fixedVec(M + "agg", 3);
    burning_ = embedding(M + "burning.weight");
    obsPosition_ = embedding("obs_embed.position_embedding.weight");
    // The choice-side card/upgrade/relic/potion tables are the same modules
    // as the observation's (silverbot EmbedCache); the export checks that.
    selectScreen_ = embedding(C + "cards.element_embedding.component_embeddings.2.embedding.weight");
    fixedAction_ = embedding(FX + "action.embedding.weight");
    gold_ = fixedVec(FX + "gold", 1);
    info_ = embedding(FX + "info.embedding.weight");
    pathX_ = fixedVec(PA + "x", 1);
    pathRoom_ = embedding(PA + "room.embedding.weight");
    cone_ = fixedVec(PA + "cone", 3);
    reachesBurn_ = embedding(PA + "reaches_burn.weight");
    choicePosition_ = embedding("choice_embed.position_embedding.weight");
    extraInputs_ = tensors.count("x_act.weight") > 0;
    if (extraInputs_) {
        deckMisc_ = fixedVec("x_deck_misc", 1);
        relicCounter_ = fixedVec("x_relic_counter", 1);
        act_ = embedding("x_act.weight");
    }
    extraInputsV2_ = tensors.count("x2_run.proj.weight") > 0;
    if (extraInputsV2_) {
        runCounters_ = fixedVec("x2_run", kRunCounterCount);
        offerPrice_ = fixedVec("x2_price", 1);
        fought_ = embedding("x2_fought.weight");
    }
    blocks_.assign(layers, {});
    for (int i = 0; i < layers; ++i) {
        const std::string L = "layers." + std::to_string(i) + ".";
        auto &b = blocks_[i];
        b.norm1 = take(L + "norm1.w", {dim});
        b.norm2 = take(L + "norm2.w", {dim});
        b.inProj.out = 3 * dim; b.inProj.in = dim;
        b.inProj.w = take(L + "attn.in_proj_weight", {3 * dim, dim});
        b.inProj.b = take(L + "attn.in_proj_bias", {3 * dim});
        b.outProj = lin(L + "attn.out_proj", dim, dim, true);
        b.w1 = lin(L + "mlp.w1", hidden, dim, true);
        b.w2 = lin(L + "mlp.w2", dim, hidden, false);
        b.v = lin(L + "mlp.v", hidden, dim, false);
    }
    finalNorm_ = take("norm.w", {dim});
    valueNorm_ = take("value_head_norm.w", {dim});
    choiceLogits_ = lin("choice_logits", 1, dim, true);
    valueHead_ = lin("value_head", 1, dim, true);
    if (!missing.empty()) return fail("missing or misshaped tensors:" + missing);
    for (auto &b : blocks_) {
        b.inProjKV.out = 2 * dim; b.inProjKV.in = dim;
        b.inProjKV.w.assign(b.inProj.w.begin() + std::ptrdiff_t(dim) * dim, b.inProj.w.end());
        b.inProjKV.b.assign(b.inProj.b.begin() + dim, b.inProj.b.end());
    }
    constexpr int kCardCount = int(sizeof(cardStringIds) / sizeof(cardStringIds[0]));
    if (card_.rows != kCardCount || relic_.rows != kRelicInvalid + 1
        || screen_.rows != static_cast<int>(ScreenState::BATTLE) + 1)
        return fail("enum sizes differ from this engine");
    path_ = file;
    forwardId_ = newMemoId();
    return true;
}

// distill.py trim(): drop the map rows below the current floor (none before the
// first map node).
static Record trimmedMap(const Record &in) {
    Record r = in;
    r.mapXs.clear(); r.mapYs.clear(); r.mapRooms.clear(); r.mapPathXs.clear();
    for (std::size_t j = 0; j < in.mapYs.size(); ++j)
        if (in.mapYs[j] >= in.mapY) {
            r.mapXs.push_back(in.mapXs[j]);
            r.mapYs.push_back(in.mapYs[j]);
            r.mapRooms.push_back(in.mapRooms[j]);
            r.mapPathXs.push_back(in.mapPathXs[j]);
        }
    return r;
}

namespace {
// FNV-1a over every Record field (equality decides a hit; this only picks the slot).
std::uint64_t recordHash(const Record &r) {
    std::uint64_t h = 0xcbf29ce484222325ull;
    const auto mix = [&h](std::int64_t v) { h = (h ^ std::uint64_t(v)) * 0x100000001b3ull; };
    const auto ints = [&mix](const std::vector<int> &v) { mix(std::int64_t(v.size())); for (int x : v) mix(x); };
    ints(r.fixedObservation); ints(r.deckCards); ints(r.deckUpgrades); ints(r.deckMisc); mix(r.act);
    ints(r.relics); ints(r.relicCounters); ints(r.potions); ints(r.mapXs); ints(r.mapYs); ints(r.mapRooms);
    mix(std::int64_t(r.mapPathXs.size()));
    for (const auto &a : r.mapPathXs) for (int x : a) mix(x);
    mix(r.burningEliteX); mix(r.burningEliteY); mix(r.mapX); mix(r.mapY);
    ints(r.offeredCards); ints(r.offeredUpgrades); ints(r.offeredRelics); ints(r.offeredPotions);
    mix(std::int64_t(r.fixedActions.size()));
    for (const auto &f : r.fixedActions) { mix(f.action); mix(f.gold); mix(f.card); mix(f.relic); mix(f.info); }
    ints(r.paths); mix(r.screenState); mix(r.selectScreenType);
    ints(r.runCounters); ints(r.foughtEncounters); ints(r.offerPrices);
    return h;
}

// Recent outputs per thread, direct-mapped by record hash. A slot holds the
// whole record, so a hit is an equal input to the same net and pass.
struct ForwardMemo {
    struct Slot { std::uint64_t net = 0; bool logitsOnly = false; std::uint64_t hash = 0; Record record; Output out; };
    static constexpr std::size_t kSlots = 4096;
    std::vector<Slot> slots = std::vector<Slot>(kSlots);
};
thread_local ForwardMemo forwardMemo;
}  // namespace

Output Net::forward(const Record &record, bool logitsOnly, bool memo) const {
    const auto run = [&] {
        return trimMap_ && record.mapY >= 0 ? forwardRecord(trimmedMap(record), logitsOnly)
                                            : forwardRecord(record, logitsOnly);
    };
    if (!memo || !forwardId_) return run();
    const std::uint64_t h = recordHash(record);
    auto &slot = forwardMemo.slots[h % ForwardMemo::kSlots];
    if (slot.net == forwardId_ && slot.logitsOnly == logitsOnly && slot.hash == h && slot.record == record) return slot.out;
    Output out = run();
    slot.net = forwardId_; slot.logitsOnly = logitsOnly; slot.hash = h; slot.record = record; slot.out = out;
    return out;
}

Output Net::forwardRecord(const Record &r, bool logitsOnly) const {
    const int kDim = dim_, kHeads = heads_, kHeadDim = dim_ / heads_, kHidden = hidden_;
    const DagFeatures dag = mapDagFeatures(r);
    const int nDeck = int(r.deckCards.size()), nRelic = int(r.relics.size()), nPot = int(r.potions.size());
    const int nMap = int(r.mapXs.size());
    const int nObs = nDeck + nRelic + nPot + 1 + nMap;
    const int nChoice = r.choiceCount();
    const int n = nObs + nChoice;
    // Choice-less records still have a value (pooled observation tokens); callers that need logits check choiceCount.
    // Per-thread scratch, reused across calls: x starts zeroed, every other
    // buffer is written before it is read.
    thread_local struct { std::vector<float> x, xn, qkv, kv, att, h1, h2, scores, silu; } scratch;
    auto &x = scratch.x;
    x.assign(std::size_t(n) * kDim, 0.f);
    int t = 0;
    const auto row = [&](int i) { return x.data() + std::size_t(i) * kDim; };
    const auto position = [&](const Embedding &e, int key) { addEmbedding(e, key, row(t)); ++t; };

    // student_inputs.py clamps: misc and relic counters to [-1, 999], act to [0, 4];
    // the extra inputs are added after silverbot's token sum (position included).
    const auto clampInput = [](int v, int lo, int hi) { return float(std::min(std::max(v, lo), hi)); };
    for (int i = 0; i < nDeck; ++i) {
        addEmbedding(card_, r.deckCards[i], row(t));
        addEmbedding(upgrade_, r.deckUpgrades[i], row(t));
        if (extraInputs_) {
            addEmbedding(obsPosition_, 0, row(t));
            const float misc = clampInput(i < int(r.deckMisc.size()) ? r.deckMisc[i] : 0, -1, 999);
            addFixedVec(deckMisc_, &misc, row(t));
            ++t;
        } else {
            position(obsPosition_, 0);
        }
    }
    for (int i = 0; i < nRelic; ++i) {
        addEmbedding(relic_, r.relics[i], row(t));
        if (extraInputs_) {
            addEmbedding(obsPosition_, 1, row(t));
            const float counter = clampInput(i < int(r.relicCounters.size()) ? r.relicCounters[i] : 0, -1, 999);
            addFixedVec(relicCounter_, &counter, row(t));
            ++t;
        } else {
            position(obsPosition_, 1);
        }
    }
    for (int i = 0; i < nPot; ++i) { addEmbedding(potion_, r.potions[i], row(t)); position(obsPosition_, 2); }
    {
        const auto &fo = r.fixedObservation;
        const float scalars[5] = {float(fo[0]), float(fo[1]), float(fo[2]), float(fo[3]), float(fo[5])};
        addFixedVec(fixedObs_, scalars, row(t));
        addEmbedding(boss_, fo[4], row(t));
        addEmbedding(ascension_, fo[6], row(t));
        addEmbedding(keyRuby_, fo[7], row(t));
        addEmbedding(keyEmerald_, fo[8], row(t));
        addEmbedding(keySapphire_, fo[9], row(t));
        addEmbedding(screen_, r.screenState, row(t));
        if (extraInputs_) {
            addEmbedding(obsPosition_, 3, row(t));
            addEmbedding(act_, int(clampInput(r.act, 0, 4)), row(t));
        } else {
            addEmbedding(obsPosition_, 3, row(t));
        }
        if (extraInputsV2_) {
            // v2 (student_inputs.py --v2): run counters clamped to [-1, 999]; a record
            // without them (older captures) reads all -1. Fought encounters are summed.
            float run[kRunCounterCount];
            for (int k = 0; k < kRunCounterCount; ++k)
                run[k] = clampInput(k < int(r.runCounters.size()) ? r.runCounters[k] : -1, -1, 999);
            addFixedVec(runCounters_, run, row(t));
            const int nFought = std::min<int>(r.foughtEncounters.size(), kMaxFoughtEncounters);
            for (int i = 0; i < nFought; ++i) addEmbedding(fought_, r.foughtEncounters[i], row(t));
        }
        ++t;
    }
    // Map tokens: the per-token additions of silverbot's order, one feature at a
    // time over all map rows so each projection runs batched.
    {
        const int m0 = t;
        std::vector<float> f2(std::size_t(nMap) * 2), f3(std::size_t(nMap) * 3);
        for (int j = 0; j < nMap; ++j) {
            float *out = row(m0 + j);
            addEmbedding(mapRoom_, r.mapRooms[j], out);
            addEmbedding(isCurrent_, r.mapXs[j] == r.mapX && r.mapYs[j] == r.mapY ? 1 : 0, out);
        }
        for (int j = 0; j < nMap; ++j) { f2[2 * j] = float(r.mapXs[j]); f2[2 * j + 1] = float(r.mapYs[j]); }
        addFixedVecRows(pos_, f2.data(), nMap, row(m0));
        for (int j = 0; j < nMap; ++j)
            for (int k = 0; k < 3; ++k) f3[3 * j + k] = float(r.mapPathXs[j][k]);
        addFixedVecRows(pathXs_, f3.data(), nMap, row(m0));
        for (int j = 0; j < nMap; ++j) { f2[2 * j] = float(r.mapXs[j] - r.mapX); f2[2 * j + 1] = float(r.mapYs[j] - r.mapY); }
        addFixedVecRows(rel_, f2.data(), nMap, row(m0));
        for (int j = 0; j < nMap; ++j) addEmbedding(reachable_, dag.reach[j] ? 1 : 0, row(m0 + j));
        // collate_fn divides in Python floats, then stores float32.
        for (int j = 0; j < nMap; ++j) {
            f3[3 * j] = float(double(dag.minE[j]) / kMapAggCap);
            f3[3 * j + 1] = float(double(dag.maxE[j]) / kMapAggCap);
            f3[3 * j + 2] = float(double(dag.dR[j]) / kMapAggCap);
        }
        addFixedVecRows(agg_, f3.data(), nMap, row(m0));
        for (int j = 0; j < nMap; ++j) {
            const bool burning = r.burningEliteX >= 0 && r.mapXs[j] == r.burningEliteX && r.mapYs[j] == r.burningEliteY;
            addEmbedding(burning_, burning ? 1 : 0, row(m0 + j));
            position(obsPosition_, 4);
        }
    }
    // v2 shop prices (clamped to [-1, 999]) on the tokens that have one (shop offers),
    // added after the token's position embedding like the other extra inputs.
    int priceIdx = 0;
    const auto price = [&] {
        if (!extraInputsV2_) return;
        const int i = priceIdx++;
        if (i >= int(r.offerPrices.size()) || r.offerPrices[i] < 0) return;
        const float p = clampInput(r.offerPrices[i], -1, 999);
        addFixedVec(offerPrice_, &p, row(t - 1));
    };
    for (std::size_t i = 0; i < r.offeredCards.size(); ++i) {
        addEmbedding(card_, r.offeredCards[i], row(t));
        addEmbedding(upgrade_, r.offeredUpgrades[i], row(t));
        addEmbedding(selectScreen_, r.selectScreenType, row(t));
        position(choicePosition_, 0);
        price();
    }
    for (int id : r.offeredRelics) { addEmbedding(relic_, id, row(t)); position(choicePosition_, 1); price(); }
    for (int id : r.offeredPotions) { addEmbedding(potion_, id, row(t)); position(choicePosition_, 2); price(); }
    for (const auto &f : r.fixedActions) {
        float *out = row(t);
        addEmbedding(fixedAction_, f.action, out);
        const float gold = float(f.gold);
        addFixedVec(gold_, &gold, out);
        addEmbedding(card_, f.card, out);
        addEmbedding(relic_, f.relic, out);
        addEmbedding(info_, f.info, out);
        position(choicePosition_, 3);
    }
    {
        const int p0 = t, nPath = int(r.paths.size());
        std::vector<float> px(nPath), cone(std::size_t(nPath) * 3);
        for (int i = 0; i < nPath; ++i) px[i] = float(r.paths[i]);
        addFixedVecRows(pathX_, px.data(), nPath, row(p0));
        for (int i = 0; i < nPath; ++i) addEmbedding(pathRoom_, dag.destRooms[i], row(p0 + i));
        // collate_fn divides the float32 tensor by MAP_AGG_CAP.
        for (int i = 0; i < nPath; ++i)
            for (int k = 0; k < 3; ++k) cone[3 * i + k] = float(dag.optCone[i][k]) / float(kMapAggCap);
        addFixedVecRows(cone_, cone.data(), nPath, row(p0));
        for (int i = 0; i < nPath; ++i) {
            addEmbedding(reachesBurn_, dag.optBurn[i], row(p0 + i));
            position(choicePosition_, 4);
        }
    }

    // Padding tokens are key-masked in silverbot, so attending over the valid
    // tokens alone gives the same outputs at every valid position.
    auto &xn = scratch.xn, &qkv = scratch.qkv, &att = scratch.att, &h1 = scratch.h1, &h2 = scratch.h2,
         &scores = scratch.scores, &kv = scratch.kv, &silu = scratch.silu;
    xn.resize(std::size_t(n) * kDim); qkv.resize(std::size_t(n) * 3 * kDim); att.resize(std::size_t(n) * kDim);
    h1.resize(std::size_t(n) * kHidden); h2.resize(std::size_t(n) * kHidden); scores.resize(n);
    const float scale = 1.0f / std::sqrt(float(kHeadDim));
    // STS_OOC_HEART1_SCALAR=1 keeps every reference loop below.
    const bool vectorized = useAvx(), attendAvx = vectorized && kHeadDim % 8 == 0 && kHeadDim <= 32;
    for (std::size_t bi = 0; bi < blocks_.size(); ++bi) {
        const auto &b = blocks_[bi];
        // Every row is computed independently after the keys and values, so the
        // last block can skip the rows no logit reads.
        const int q0 = logitsOnly && bi + 1 == blocks_.size() ? nObs : 0, nq = n - q0;
        for (int i = 0; i < n; ++i) rmsNorm(row(i), b.norm1, xn.data() + std::size_t(i) * kDim);
        if (q0 == 0) {
            linear(b.inProj, xn.data(), n, qkv.data());
        } else {
            // Rows before q0 are only keys and values: their query outputs are never read.
            linear(b.inProj, xn.data() + std::size_t(q0) * kDim, nq, qkv.data() + std::size_t(q0) * 3 * kDim);
            kv.resize(std::size_t(q0) * 2 * kDim);
            linear(b.inProjKV, xn.data(), q0, kv.data());
            for (int i = 0; i < q0; ++i)
                std::copy_n(kv.data() + std::size_t(i) * 2 * kDim, 2 * kDim, qkv.data() + std::size_t(i) * 3 * kDim + kDim);
        }
        if (attendAvx)
            for (int hd = 0; hd < kHeads; ++hd)
                attendHeadAvx(qkv.data(), n, q0, kDim, hd * kHeadDim, kHeadDim, scale, scores.data(), att.data());
        else for (int hd = 0; hd < kHeads; ++hd) {
            for (int i = q0; i < n; ++i) {
                const float *q = qkv.data() + std::size_t(i) * 3 * kDim + hd * kHeadDim;
                float mx = -std::numeric_limits<float>::infinity();
                for (int j = 0; j < n; ++j) {
                    const float *k = qkv.data() + std::size_t(j) * 3 * kDim + kDim + hd * kHeadDim;
                    scores[j] = dot(q, k, kHeadDim) * scale;
                    mx = std::max(mx, scores[j]);
                }
                float sum = 0;
                for (int j = 0; j < n; ++j) { scores[j] = std::exp(scores[j] - mx); sum += scores[j]; }
                float *o = att.data() + std::size_t(i) * kDim + hd * kHeadDim;
                std::fill(o, o + kHeadDim, 0.f);
                for (int j = 0; j < n; ++j) {
                    const float p = scores[j] / sum;
                    const float *v = qkv.data() + std::size_t(j) * 3 * kDim + 2 * kDim + hd * kHeadDim;
                    for (int d = 0; d < kHeadDim; ++d) o[d] += p * v[d];
                }
            }
        }
        const std::size_t o0 = std::size_t(q0) * kDim, h0 = std::size_t(q0) * kHidden;
        linear(b.outProj, att.data() + o0, nq, x.data() + o0, /*accumulate=*/true);
        for (int i = q0; i < n; ++i) rmsNorm(row(i), b.norm2, xn.data() + std::size_t(i) * kDim);
        linear(b.w1, xn.data() + o0, nq, h1.data() + h0);
        linear(b.v, xn.data() + o0, nq, h2.data() + h0);
        if (vectorized) {
            // The same SiLU, its exps taken in one pass.
            const std::size_t m = h1.size() - h0;
            silu.resize(m);
            for (std::size_t i = 0; i < m; ++i) silu[i] = -h1[h0 + i];
            expInPlace(silu.data(), int(m));
            for (std::size_t i = 0; i < m; ++i) h1[h0 + i] = h1[h0 + i] / (1.0f + silu[i]) * h2[h0 + i];
        } else {
            for (std::size_t i = h0; i < h1.size(); ++i) {
                const float a = h1[i];
                h1[i] = a / (1.0f + std::exp(-a)) * h2[i];
            }
        }
        linear(b.w2, h1.data() + h0, nq, x.data() + o0, /*accumulate=*/true);
    }

    Output out;
    out.logits.resize(nChoice);
    if (logitsOnly) {
        for (int c = 0; c < nChoice; ++c) {
            float *xc = xn.data() + std::size_t(nObs + c) * kDim;
            rmsNorm(row(nObs + c), finalNorm_, xc);
            out.logits[c] = dot(choiceLogits_.w.data(), xc, kDim) + choiceLogits_.b[0];
        }
        return out;
    }
    for (int i = 0; i < n; ++i) rmsNorm(row(i), finalNorm_, xn.data() + std::size_t(i) * kDim);
    for (int c = 0; c < nChoice; ++c)
        out.logits[c] = dot(choiceLogits_.w.data(), xn.data() + std::size_t(nObs + c) * kDim, kDim) + choiceLogits_.b[0];
    std::vector<float> pooled(kDim, 0.f), vn(kDim);
    for (int i = 0; i < n; ++i) {
        rmsNorm(xn.data() + std::size_t(i) * kDim, valueNorm_, vn.data());
        for (int d = 0; d < kDim; ++d) pooled[d] += vn[d];
    }
    for (int d = 0; d < kDim; ++d) pooled[d] /= float(n);
    out.value = dot(valueHead_.w.data(), pooled.data(), kDim) + valueHead_.b[0];
    out.pooled = std::move(pooled);
    return out;
}

// ---------------------------------------------------------------- policy

namespace {
std::once_flag g_loadOnce;
Net g_net;
std::mutex g_traceMutex;

const char *weightsPath() {
    const char *p = std::getenv("STS_OOC_HEART1");
    return p && *p ? p : nullptr;
}
}  // namespace

bool enabled() { return weightsPath() != nullptr; }

const Net &net() {
    std::call_once(g_loadOnce, [] {
        std::string error;
        if (!g_net.load(weightsPath(), &error))
            throw std::runtime_error("STS_OOC_HEART1: " + error);
        std::fprintf(stderr, "[heart1] loaded %s (dim %d, heads %d, hidden %d, layers %d, trim_map %d)\n",
                     g_net.path().c_str(), g_net.dim(), g_net.heads(), g_net.hidden(), g_net.layers(),
                     g_net.trimMap() ? 1 : 0);
    });
    return g_net;
}

bool policyStep(GameContext &gc) {
    if (!enabled()) return false;
    const Net &model = net();
    const int freeTaken = takeFreeRewards(gc);
    if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState == ScreenState::BATTLE) return freeTaken > 0;
    Choice choice;
    if (!buildChoice(gc, choice)) return freeTaken > 0;
    const int nChoice = choice.record.choiceCount();
    if (nChoice == 0) return freeTaken > 0;
    int chosen = 0;
    Output scored;
    const char *trace = std::getenv("STS_OOC_HEART1_TRACE");
    const bool tracing = trace && *trace;
    if (nChoice > 1) {
        scored = model.forward(choice.record, /*logitsOnly=*/!tracing);
        // Temperature 0: np.argmax, first maximum in token order.
        chosen = int(std::max_element(scored.logits.begin(), scored.logits.end()) - scored.logits.begin());
    }
    if (tracing && nChoice > 1) {
        nlohmann::json line = {{"seed", std::to_string(gc.seed)}, {"act", gc.act}, {"floor", gc.floorNum},
                               {"record", recordToJson(choice.record)}, {"logits", scored.logits},
                               {"value", scored.value}, {"chosen", chosen},
                               {"bits", choice.actions[chosen].bits}};
        std::lock_guard<std::mutex> lock(g_traceMutex);
        std::ofstream(trace, std::ios::app) << line.dump() << '\n';
    }
    choice.actions[chosen].execute(gc);
    return true;
}

std::optional<std::vector<double>> mapPriorLogits(const Choice &choice, const std::vector<float> &logits,
                                                  bool singingBowl, const std::vector<GA> &actions,
                                                  std::map<std::string, std::uint64_t> *tally) {
    if (logits.size() != choice.actions.size()) throw std::runtime_error("heart1: logit count mismatch");
    // A primitive behind several tokens keeps its best token.
    std::map<std::uint32_t, double> byBits;
    for (std::size_t i = 0; i < choice.actions.size(); ++i) {
        const auto [it, inserted] = byBits.emplace(choice.actions[i].bits, logits[i]);
        if (!inserted) it->second = std::max(it->second, double(logits[i]));
    }
    // Fixed tokens follow the card, relic and potion tokens.
    const Record &r = choice.record;
    const std::size_t fixedStart = r.offeredCards.size() + r.offeredRelics.size() + r.offeredPotions.size();
    const auto fixedLogit = [&](int fa) -> std::optional<double> {
        for (std::size_t k = 0; k < r.fixedActions.size(); ++k)
            if (r.fixedActions[k].action == fa) return double(logits.at(fixedStart + k));
        return std::nullopt;
    };
    const bool rewards = r.screenState == static_cast<int>(ScreenState::REWARDS);
    const bool shop = r.screenState == static_cast<int>(ScreenState::SHOP_ROOM);
    double lo = std::numeric_limits<double>::infinity(), hi = -lo;
    for (const float l : logits) { lo = std::min(lo, double(l)); hi = std::max(hi, double(l)); }
    const std::string where = rewards ? "REWARDS" : shop ? "SHOP" : "screen" + std::to_string(r.screenState);
    std::map<std::string, std::uint64_t> mapped;
    const auto fail = [&](const char *kind) -> std::optional<std::vector<double>> {
        if (tally) ++(*tally)["fallback:" + where + ":" + kind];
        return std::nullopt;
    };
    std::vector<double> out;
    out.reserve(actions.size());
    for (const auto action : actions) {
        if (const auto it = byBits.find(action.bits); it != byBits.end()) { out.push_back(it->second); continue; }
        // Tree primitives silverbot's choice space lacks:
        // - skip one card reward (CARD idx2 5 without Singing Bowl): silverbot declines a card by skipping;
        //   with Singing Bowl, silverbot offers the bowl token on the last card reward only.
        // - gold: silverbot always takes it for free (take_free_rewards), so heart1's best logit.
        // - discard a held potion for a reward or shop potion: silverbot's engine offers no discard, so
        //   heart1's lowest logit at the node.
        if (rewards && action.getRewardsActionType() == GA::RewardsActionType::CARD && action.getIdx2() == 5) {
            const auto l = fixedLogit(singingBowl ? FA_SINGING_BOWL : FA_SKIP);
            if (!l) return fail(singingBowl ? "bowl_no_token" : "skip_card_no_token");
            out.push_back(*l);
            ++mapped[singingBowl ? "bowl" : "skip_card"];
        } else if (rewards && action.getRewardsActionType() == GA::RewardsActionType::GOLD) {
            out.push_back(hi);
            ++mapped["gold"];
        } else if ((rewards || shop) && action.isPotionDiscard()) {
            out.push_back(lo);
            ++mapped["discard_potion"];
        } else {
            return fail(action.isPotionDiscard() ? "discard_potion" : "no_token");
        }
    }
    if (tally) {
        ++(*tally)["scored:" + where];
        for (const auto &[kind, n] : mapped) (*tally)["mapped:" + where + ":" + kind] += n;
    }
    return out;
}

std::vector<TokenMapping> mapChoiceTokens(const Choice &choice, bool singingBowl, const std::vector<GA> &actions) {
    const Record &r = choice.record;
    const std::size_t fixedStart = r.offeredCards.size() + r.offeredRelics.size() + r.offeredPotions.size();
    const auto fixedToken = [&](int fa) {
        for (std::size_t k = 0; k < r.fixedActions.size(); ++k)
            if (r.fixedActions[k].action == fa) return int(fixedStart + k);
        return -1;
    };
    const bool rewards = r.screenState == static_cast<int>(ScreenState::REWARDS);
    const bool shop = r.screenState == static_cast<int>(ScreenState::SHOP_ROOM);
    std::vector<TokenMapping> out(actions.size());
    for (std::size_t a = 0; a < actions.size(); ++a) {
        const auto action = actions[a];
        auto &m = out[a];
        for (std::size_t i = 0; i < choice.actions.size(); ++i)
            if (choice.actions[i].bits == action.bits) m.tokens.push_back(int(i));
        if (!m.tokens.empty()) { m.kind = "token"; continue; }
        // Same order and rules as mapPriorLogits.
        if (rewards && action.getRewardsActionType() == GA::RewardsActionType::CARD && action.getIdx2() == 5) {
            const int t = fixedToken(singingBowl ? FA_SINGING_BOWL : FA_SKIP);
            if (t >= 0) { m.tokens = {t}; m.kind = singingBowl ? "bowl" : "skip_card"; }
            else m.kind = "none";
        } else if (rewards && action.getRewardsActionType() == GA::RewardsActionType::GOLD) {
            m.kind = "gold";
        } else if ((rewards || shop) && action.isPotionDiscard()) {
            m.kind = "discard_potion";
        } else {
            m.kind = "none";
        }
    }
    return out;
}

void fixedVecMemoSelfTest() {
    if (!useAvx()) return;  // the memo is off without AVX
    // Two nets of different row width on one thread, calls interleaved with
    // repeated inputs: every memo row equals the unmemoized projection bitwise.
    const auto make = [](int out, unsigned seed) {
        Net::FixedVec f;
        f.features = 2;
        f.invFreq = {1.0f, 0.37f, 0.11f, 0.029f};
        f.proj.out = out;
        f.proj.in = f.features * 2 * int(f.invFreq.size());
        std::uint32_t state = seed;
        const auto next = [&state] { state = state * 1664525u + 1013904223u; return float(state >> 8) / float(1 << 24) - 0.5f; };
        f.proj.w.resize(std::size_t(f.proj.out) * f.proj.in);
        for (float &w : f.proj.w) w = next();
        f.proj.b.resize(f.proj.out);
        for (float &b : f.proj.b) b = next();
        f.memoId = newMemoId();
        return f;
    };
    const Net::FixedVec narrow = make(64, 1), wide = make(256, 2);
    fixedVecMemo = FixedVecMemo{};
    for (int call = 0; call < 40; ++call) {
        const Net::FixedVec &f = call % 3 == 1 ? wide : narrow;
        const int n = 1 + call % 5;
        std::vector<float> x(std::size_t(n) * f.features);
        for (std::size_t i = 0; i < x.size(); ++i) x[i] = float((call * 7 + int(i) * 3) % 11);
        std::vector<float> got(std::size_t(n) * f.proj.out, 0.25f), want = got;
        addFixedVecRows(f, x.data(), n, got.data());
        Net::FixedVec plain = f;
        plain.memoId = 0;
        addFixedVecRows(plain, x.data(), n, want.data());
        if (std::memcmp(got.data(), want.data(), sizeof(float) * got.size()) != 0)
            throw std::runtime_error("heart1 FixedVec memo selftest: mixed-width rows differ from the plain projection");
    }
    fixedVecMemo = FixedVecMemo{};
}

void linearSelfTest() {
    // Every projection kernel this CPU uses against the reference loop, bitwise,
    // over token counts that hit the full tiles and each leftover path.
    Net::Linear l;
    l.out = 68;
    l.in = 64;
    std::uint32_t state = 7;
    const auto next = [&state] { state = state * 1664525u + 1013904223u; return float(state >> 8) / float(1 << 24) - 0.5f; };
    l.w.resize(std::size_t(l.out) * l.in);
    for (float &w : l.w) w = next();
    l.b.resize(l.out);
    for (float &b : l.b) b = next();
    for (int n : {1, 2, 3, 5, 6, 7, 12, 13, 17})
        for (bool accumulate : {false, true}) {
            std::vector<float> x(std::size_t(n) * l.in);
            for (float &v : x) v = next() * 8;
            std::vector<float> want(std::size_t(n) * l.out), got;
            for (float &v : want) v = next();
            got = want;
            linearScalar(l, x.data(), n, want.data(), accumulate);
            linear(l, x.data(), n, got.data(), accumulate);
            if (std::memcmp(got.data(), want.data(), sizeof(float) * got.size()) != 0)
                throw std::runtime_error("heart1 linear selftest: vector projection differs from the reference loop");
        }
}

void priorMappingSelfTest() {
    const auto require = [](bool ok, const char *what) {
        if (!ok) throw std::runtime_error(std::string("heart1 prior mapping selftest: ") + what);
    };
    // The record builder is usable without network weights and ignores hidden
    // future/RNG fields. This is a limited invariance fixture, not live parity.
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD; gc.ascension = 20; gc.act = 1;
    gc.curHp = 70; gc.maxHp = 80; gc.boss = MonsterEncounter::HEXAGHOST;
    gc.map = std::make_shared<Map>(); gc.screenState = ScreenState::REST_ROOM;
    gc.curRoom = Room::REST; gc.keysEnabled = true;
    gc.deck.obtainRaw(Card(CardId::BASH));
    gc.relics.add({RelicId::NUNCHAKU, 2});
    Choice first, hidden;
    require(buildChoice(gc, first), "weight-free public record fixture");
    auto altered = gc;
    altered.seed = 987654321; altered.miscRng = Random(456);
    altered.cardRarityFactor = -35; altered.secondBoss = MonsterEncounter::TIME_EATER;
    altered.monsterList.push_back(MonsterEncounter::CULTIST);
    require(buildChoice(altered, hidden) && recordToJson(first.record) == recordToJson(hidden.record),
        "record must ignore seed, RNG, hidden counters and future encounter queue");
    altered.relics.getRelicValueRef(RelicId::NUNCHAKU) = 3;
    require(buildChoice(altered, hidden) && recordToJson(first.record) != recordToJson(hidden.record),
        "record retains a public relic counter");
    nlohmann::json leaf, changed;
    auto boundary = gc;
    boundary.screenState = ScreenState::BATTLE;
    boundary.info.encounter = MonsterEncounter::CULTIST;
    require(buildPublicLeafRecord(boundary, leaf), "battle-start leaf record");
    boundary.monsterList.push_back(MonsterEncounter::SLIME_BOSS);
    boundary.miscRng = Random(123);
    boundary.secondBoss = MonsterEncounter::TIME_EATER;
    require(buildPublicLeafRecord(boundary, changed) && leaf == changed, "battle record ignores future/RNG");
    boundary.info.encounter = MonsterEncounter::JAW_WORM;
    require(buildPublicLeafRecord(boundary, changed) && leaf != changed, "battle record keeps current encounter");
    boundary.screenState = ScreenState::EVENT_SCREEN;
    boundary.curEvent = Event::MATCH_AND_KEEP;
    boundary.info.eventData = 5;
    boundary.info.toSelectCards.clear();
    boundary.info.toSelectCards.push_back({Card(CardId::BASH), GameContext::MATCH_AND_KEEP_UNSEEN});
    boundary.info.toSelectCards.push_back({Card(CardId::STRIKE_RED), GameContext::MATCH_AND_KEEP_SEEN});
    require(buildPublicLeafRecord(boundary, leaf), "memory-game leaf record");
    boundary.info.toSelectCards[0].card = Card(CardId::DEFEND_RED, 1);
    boundary.miscRng = Random(789);
    require(buildPublicLeafRecord(boundary, changed) && leaf == changed, "unseen board identity is masked");
    boundary.info.toSelectCards[1].card = Card(CardId::DEFEND_RED);
    require(buildPublicLeafRecord(boundary, changed) && leaf != changed, "visible board identity is retained");
    require(buildPublicLeafRecord(boundary, leaf), "memory-game visible update");
    --boundary.info.eventData;
    require(buildPublicLeafRecord(boundary, changed) && leaf != changed, "public attempts retained");
    boundary.outcome = GameOutcome::PLAYER_LOSS;
    require(!buildPublicLeafRecord(boundary, changed), "true terminal rejected");
    Choice c;
    c.record.screenState = static_cast<int>(ScreenState::REWARDS);
    c.record.offeredCards = {1, 2};
    c.record.offeredUpgrades = {0, 0};
    FixedChoice skip;
    skip.action = FA_SKIP;
    c.record.fixedActions = {skip};
    c.actions = {GA(RT::CARD, 0, 0), GA(RT::CARD, 0, 1), GA(RT::SKIP)};
    const std::vector<float> logits{0.5f, 2.0f, -1.0f};
    std::map<std::string, std::uint64_t> tally;
    const auto got = mapPriorLogits(c, logits, false,
        {GA(RT::CARD, 0, 0), GA(RT::CARD, 0, 1), GA(RT::CARD, 0, 5), GA(RT::GOLD, 0), GA(0xc0000001u), GA(RT::SKIP)},
        &tally);
    require(got && *got == std::vector<double>{0.5, 2.0, -1.0, 2.0, -1.0, -1.0},
            "skip card -> skip token, gold -> best, discard -> lowest");
    {
        // mapChoiceTokens must name exactly the logits mapPriorLogits used.
        const std::vector<GA> primitives{GA(RT::CARD, 0, 0), GA(RT::CARD, 0, 1), GA(RT::CARD, 0, 5),
            GA(RT::GOLD, 0), GA(0xc0000001u), GA(RT::SKIP)};
        const auto tokens = mapChoiceTokens(c, false, primitives);
        const std::vector<std::string> kinds{"token", "token", "skip_card", "gold", "discard_potion", "token"};
        require(tokens.size() == primitives.size(), "token mapping size");
        for (std::size_t i = 0; i < tokens.size(); ++i) {
            require(tokens[i].kind == kinds[i], "token mapping kind");
            double v = tokens[i].kind == "gold" ? 2.0 : tokens[i].kind == "discard_potion" ? -1.0
                : -std::numeric_limits<double>::infinity();
            for (const int t : tokens[i].tokens) v = std::max(v, double(logits.at(t)));
            require(v == (*got)[i], "token mapping agrees with mapPriorLogits");
        }
        require(mapChoiceTokens(c, true, {GA(RT::CARD, 0, 5)})[0].kind == "none"
                && mapChoiceTokens(c, false, {GA(RT::RELIC, 0)})[0].kind == "none", "unmapped token kinds");
    }
    require(tally["scored:REWARDS"] == 1 && tally["mapped:REWARDS:skip_card"] == 1
            && tally["mapped:REWARDS:gold"] == 1 && tally["mapped:REWARDS:discard_potion"] == 1, "tally of mappings");
    require(!mapPriorLogits(c, logits, true, {GA(RT::CARD, 0, 5)}, &tally)
            && tally["fallback:REWARDS:bowl_no_token"] == 1, "bowl without a bowl token falls back");
    require(!mapPriorLogits(c, logits, false, {GA(RT::RELIC, 0)}, &tally)
            && tally["fallback:REWARDS:no_token"] == 1, "unmapped primitive falls back");
    c.record.screenState = static_cast<int>(ScreenState::MAP_SCREEN);
    require(!mapPriorLogits(c, logits, false, {GA(RT::CARD, 0, 5)}, &tally), "skip-card mapping is REWARDS only");
}

nlohmann::json leafAnnotation(const GameContext &gc) {
    Choice choice;
    std::string reason;
    if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState == ScreenState::BATTLE)
        return {{"unsupported", "terminal_or_battle"}};
    if (!buildChoice(gc, choice, &reason) || choice.record.choiceCount() == 0)
        return {{"unsupported", reason.empty() ? "no_choice" : reason}};
    const Output scored = net().forward(choice.record);
    return {{"value", scored.value}, {"record", recordToJson(choice.record)}};
}

namespace {
// STS_OOC_HEART1_CAPTURE: distillation rows from prior calls (observation only).
struct Capture {
    std::string path;
    std::uint64_t every = 8, selectEvery = 1;
    std::mutex mutex;
    std::uint64_t calls = 0, selects = 0;
    std::unordered_set<std::size_t> seen;
};

std::uint64_t positiveKnob(const char *key, std::uint64_t fallback) {
    const char *p = std::getenv(key);
    if (!p || !*p) return fallback;
    char *end = nullptr;
    const unsigned long long v = std::strtoull(p, &end, 10);
    if (*end || v == 0) throw std::runtime_error(std::string(key) + " must be a positive integer");
    return std::uint64_t(v);
}

Capture *capture() {
    static Capture *c = [] () -> Capture * {
        const char *p = std::getenv("STS_OOC_HEART1_CAPTURE");
        if (!p || !*p) return nullptr;
        auto *out = new Capture;
        out->path = p;
        out->every = positiveKnob("STS_OOC_HEART1_CAPTURE_EVERY", 8);
        out->selectEvery = positiveKnob("STS_OOC_HEART1_CAPTURE_SELECT_EVERY", 1);
        return out;
    }();
    return c;
}

// The capture labels with STS_OOC_HEART1_TEACHER when set (e.g. heart1 while a
// student serves the prior), else with the serving net.
const Net &teacher() {
    static const Net *t = [] {
        const char *p = std::getenv("STS_OOC_HEART1_TEACHER");
        if (!p || !*p) return &net();
        auto *model = new Net;
        std::string error;
        if (!model->load(p, &error)) throw std::runtime_error("STS_OOC_HEART1_TEACHER: " + error);
        std::fprintf(stderr, "[heart1] capture teacher %s (dim %d, layers %d)\n", p, model->dim(), model->layers());
        return static_cast<const Net *>(model);
    }();
    return *t;
}

// Sources whose successor can be a card select (smith, toke, shop removal,
// event options, boss relics such as Astrolabe).
bool maySelect(const GameContext &gc, const GA &a) {
    switch (gc.screenState) {
        case ScreenState::REST_ROOM: case ScreenState::EVENT_SCREEN: case ScreenState::BOSS_RELIC_REWARDS:
            return true;
        case ScreenState::SHOP_ROOM: return a.getRewardsActionType() == RT::CARD_REMOVE;
        default: return false;
    }
}

// One JSON line per new record (records already written by this process are skipped).
void captureRow(Capture &c, nlohmann::json row, const Choice &choice, const std::vector<float> *serve) {
    const auto record = recordToJson(choice.record);
    const std::size_t key = std::hash<std::string>{}(record.dump());
    {
        std::lock_guard<std::mutex> lock(c.mutex);
        if (!c.seen.insert(key).second) return;
    }
    const Output scored = teacher().forward(choice.record);
    std::vector<std::uint32_t> tokenBits;
    for (const auto &a : choice.actions) tokenBits.push_back(a.bits);
    row["record"] = record;
    row["logits"] = scored.logits;
    row["value"] = scored.value;
    row["token_bits"] = tokenBits;
    if (serve) row["serve"] = *serve;
    const std::string line = row.dump() + '\n';
    std::lock_guard<std::mutex> lock(c.mutex);
    // One append write per line, so forked writers do not interleave.
    std::FILE *f = std::fopen(c.path.c_str(), "a");
    if (!f || std::fwrite(line.data(), 1, line.size(), f) != line.size() || std::fclose(f) != 0)
        throw std::runtime_error("STS_OOC_HEART1_CAPTURE: write failed");
}

}  // namespace

nlohmann::json captureBase(const GameContext &gc, const char *kind) {
    // deck_misc follows obs.deck.cards (Ritual Dagger damage, Genetic Algorithm block), which heart1 does not see.
    std::vector<int> misc;
    for (const auto &c : gc.deck.cards) misc.push_back(c.misc);
    return {{"kind", kind}, {"act", gc.act}, {"floor", gc.floorNum},
            {"screen", int(gc.screenState)}, {"select_type", int(gc.info.selectScreenType)}, {"deck_misc", misc},
            {"wing_boots_counter", wingBootsCounter() ? 1 : 0}};
}

namespace {

// Every EVERY-th prior call writes the node; every SELECT_EVERY-th card select that a
// source opens is written too (the state the tree reaches only as a compound
// candidate, so the prior is never asked there).
void captureCall(const GameContext &gc, const Choice &choice, const std::vector<float> &serve,
                 const std::vector<GA> &actions) {
    Capture &c = *capture();
    std::uint64_t call;
    {
        std::lock_guard<std::mutex> lock(c.mutex);
        call = c.calls++;
    }
    if (call % c.every == 0) {
        auto row = captureBase(gc, "node");
        std::vector<std::uint32_t> bits;
        for (const auto a : actions) bits.push_back(a.bits);
        row["src_bits"] = bits;
        captureRow(c, std::move(row), choice, &serve);
    }
    for (const auto a : actions) {
        if (!maySelect(gc, a) || !a.isValidAction(gc)) continue;
        GameContext next = gc;
        if (gc.map) next.map = std::make_shared<Map>(*gc.map);
        a.execute(next);
        Choice select;
        if (next.outcome != GameOutcome::UNDECIDED || next.screenState != ScreenState::CARD_SELECT
                || !buildChoice(next, select) || select.record.choiceCount() < 2)
            continue;
        {
            std::lock_guard<std::mutex> lock(c.mutex);
            if (c.selects++ % c.selectEvery != 0) continue;
        }
        auto row = captureBase(next, "select");
        row["parent_screen"] = int(gc.screenState);
        row["parent_bits"] = a.bits;
        const auto served = enabled() ? net().forward(select.record, /*logitsOnly=*/true).logits : std::vector<float>{};
        captureRow(c, std::move(row), select, &served);
    }
}
}  // namespace

std::optional<std::vector<double>> priorLogits(const GameContext &gc, const std::vector<GA> &actions,
                                               std::map<std::string, std::uint64_t> *tally) {
    Choice choice;
    if (!enabled() || gc.outcome != GameOutcome::UNDECIDED || gc.screenState == ScreenState::BATTLE
            || !buildChoice(gc, choice) || choice.record.choiceCount() == 0) {
        if (tally) ++(*tally)["fallback:screen" + std::to_string(static_cast<int>(gc.screenState)) + ":unencoded"];
        return std::nullopt;
    }
    const auto logits = net().forward(choice.record, /*logitsOnly=*/true).logits;
    if (capture()) captureCall(gc, choice, logits, actions);
    return mapPriorLogits(choice, logits, gc.hasRelic(RelicId::SINGING_BOWL), actions, tally);
}

std::optional<std::vector<double>> priorLogits(const Net &model, const GameContext &gc,
                                               const std::vector<GA> &actions,
                                               std::map<std::string, std::uint64_t> *tally) {
    Choice choice;
    if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState == ScreenState::BATTLE
            || !buildChoice(gc, choice) || choice.record.choiceCount() == 0) {
        if (tally) ++(*tally)["fallback:screen" + std::to_string(static_cast<int>(gc.screenState)) + ":unencoded"];
        return std::nullopt;
    }
    return mapPriorLogits(choice, model.forward(choice.record).logits, gc.hasRelic(RelicId::SINGING_BOWL),
                          actions, tally);
}

namespace {
nlohmann::json scoreJson(const Net &model, const Record &record) {
    const Output out = model.forward(record);
    const int best = int(std::max_element(out.logits.begin(), out.logits.end()) - out.logits.begin());
    return {{"logits", out.logits}, {"value", out.value}, {"pooled", out.pooled}, {"argmax", best}};
}

Net loadOrThrow(const std::string &path) {
    Net model;
    std::string error;
    if (!model.load(path, &error)) throw std::runtime_error("heart1: " + error);
    return model;
}
}  // namespace

int scoreCommand(int argc, char **argv) {
    if (argc != 5) {
        std::fprintf(stderr, "usage: one_combat heart1score <weights.bin> <records.jsonl> <out.jsonl>\n");
        return 2;
    }
    const Net model = loadOrThrow(argv[2]);
    std::ifstream in(argv[3]);
    std::ofstream out(argv[4]);
    if (!in || !out) throw std::runtime_error("heart1score: cannot open input or output");
    std::string line;
    int n = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const auto j = nlohmann::json::parse(line);
        out << scoreJson(model, recordFromJson(j.contains("record") ? j.at("record") : j)).dump() << '\n';
        ++n;
    }
    std::printf("heart1score records=%d -> %s\n", n, argv[4]);
    return 0;
}

int logitsCheckCommand(int argc, char **argv) {
    if (argc != 4 && argc != 5) {
        std::fprintf(stderr, "usage: one_combat heart1logitscheck <weights.bin> <records.jsonl> [reps]\n");
        return 2;
    }
    const Net model = loadOrThrow(argv[2]);
    const int reps = argc == 5 ? std::max(1, std::stoi(argv[4])) : 1;
    std::ifstream in(argv[3]);
    if (!in) throw std::runtime_error("heart1logitscheck: cannot open records");
    std::vector<Record> records;
    std::string line;
    while (std::getline(in, line))
        if (!line.empty()) {
            const auto j = nlohmann::json::parse(line);
            records.push_back(recordFromJson(j.contains("record") ? j.at("record") : j));
        }
    // Bitwise: the logits-only pass must reproduce every full-pass logit.
    int mismatches = 0, logits = 0;
    for (const auto &r : records) {
        const auto full = model.forward(r).logits, fast = model.forward(r, /*logitsOnly=*/true).logits;
        logits += int(full.size());
        if (full.size() != fast.size() || std::memcmp(full.data(), fast.data(), full.size() * sizeof(float)) != 0)
            ++mismatches;
    }
    const auto time = [&](bool logitsOnly) {
        const auto start = std::chrono::steady_clock::now();
        float sink = 0;
        for (int k = 0; k < reps; ++k)
            for (const auto &r : records) {
                const auto out = model.forward(r, logitsOnly, /*memo=*/false);
                if (!out.logits.empty()) sink += out.logits[0];
            }
        const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        return std::make_pair(s, sink);
    };
    const auto full = time(false), fast = time(true);
    const double calls = double(records.size()) * reps;
    std::printf("heart1logitscheck records=%zu logits=%d mismatched_records=%d full_us=%.1f logits_only_us=%.1f speedup=%.3f (%g)\n",
                records.size(), logits, mismatches, 1e6 * full.first / calls, 1e6 * fast.first / calls,
                full.first / fast.first, double(full.second + fast.second));
    return mismatches == 0 ? 0 : 1;
}

int replayCommand(int argc, char **argv) {
    if (argc != 7) {
        std::fprintf(stderr, "usage: one_combat heart1replay <weights.bin> <asc> <seed> <plan.json> <out.jsonl>\n");
        return 2;
    }
    const Net model = loadOrThrow(argv[2]);
    const int asc = std::stoi(argv[3]);
    const std::uint64_t seed = std::stoull(argv[4]);
    std::ifstream planIn(argv[5]);
    if (!planIn) throw std::runtime_error("heart1replay: cannot open plan");
    const auto plan = nlohmann::json::parse(planIn);
    std::ofstream out(argv[6]);
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    int step = 0;
    for (const auto &s : plan) {
        nlohmann::json row = {{"step", step}};
        // silverbot keeps a reward screen open with only "proceed" left after
        // a Neow card or potion pick; ours has already left it. Skip that step.
        if (s.value("proceed_only", false) && gc.screenState != ScreenState::REWARDS) {
            row["skipped"] = "proceed_absent";
            out << row.dump() << '\n';
            ++step;
            continue;
        }
        if (s.value("record", false)) {
            Choice choice;
            std::string reason;
            if (!buildChoice(gc, choice, &reason)) {
                row["unsupported"] = reason;
            } else {
                row["record"] = recordToJson(choice.record);
                std::vector<std::uint32_t> bits;
                for (const auto &a : choice.actions) bits.push_back(a.bits);
                row["bits"] = bits;
                if (choice.record.choiceCount() > 1) row.update(scoreJson(model, choice.record));
            }
            out << row.dump() << '\n';
        }
        const GA action(s.at("bits").get<std::uint32_t>());
        if (!action.isValidAction(gc)) {
            out << nlohmann::json({{"step", step}, {"invalid_action", action.bits}}).dump() << '\n';
            return 1;
        }
        action.execute(gc);
        ++step;
    }
    return 0;
}

}  // namespace one_combat::heart1
