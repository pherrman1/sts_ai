// Out-of-combat Amber encoder (amberEncodeGame) over random-legal whole A20 runs (battles skipped).
//
// Every visited decision state is encoded with its legal actions plus the out-of-combat potion drinks / discards and
// the Singing Bowl reward: no UNKNOWN action, src / tgt in range and on live tokens, every choosing action has its
// token, distinct GameAction bits give distinct (type, src, tgt, f) tuples, ids inside the vocabulary, finite floats,
// out.cut only from MAP / deck / relic overflow, the same state encodes to the same bytes, and a copy whose private
// fields (seed, RNG streams, pools, unconsumed encounter queues, second boss, pity counters, unopened chest roll,
// Dead Adventurer reward order, burning-elite buff, transform RNG) are scrambled encodes to the same bytes.
// Every out-of-combat ScreenState must be visited. Fixed seeds 1..N (no gameplay evaluation, outcomes unused).
#include "sim/search/AmberEncoder.h"

#include "constants/MonsterEncounters.h"
#include "game/Map.h"
#include "game/Neow.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using namespace sts;
using namespace sts::search;

namespace {

    int g_fail = 0;
    void check(bool ok, const std::string &what, const GameContext &gc) {
        if (ok) return;
        if (++g_fail <= 30)
            std::cerr << "FAIL: " << what << " (seed " << gc.seed << " floor " << gc.floorNum << " screen "
                      << static_cast<int>(gc.screenState) << " event " << static_cast<int>(gc.curEvent) << ")\n";
    }

    // Live bytes only: counts, the live tokens of every segment and the live actions.
    std::vector<std::uint8_t> liveBytes(const AmberTokens &t) {
        std::vector<std::uint8_t> b;
        const auto add = [&](const void *p, std::size_t n) {
            const auto *c = static_cast<const std::uint8_t *>(p);
            b.insert(b.end(), c, c + n);
        };
        add(t.n.data(), t.n.size());
        add(&t.nAct, sizeof(t.nAct));
        add(&t.cut, sizeof(t.cut));
        for (int s = 0; s < kAmberTokenTypes; ++s)
            for (int i = 0; i < t.n[s]; ++i) add(&t.tok[kAmberOff[s] + i], sizeof(AmberToken));
        for (int i = 0; i < t.nAct; ++i) add(&t.act[i], sizeof(AmberAction));
        return b;
    }

    // All actions the encoder must handle in this state.
    std::vector<GameAction> actionsFor(const GameContext &gc) {
        auto actions = GameAction::getAllActionsInState(gc);
        if (gc.outcome != GameOutcome::UNDECIDED) return actions;
        for (int slot = 0; slot < gc.potionCapacity; ++slot) {
            const GameAction drink(0x80000000u | static_cast<unsigned>(slot));
            const GameAction discard(0xC0000000u | static_cast<unsigned>(slot));
            if (gc.screenState != ScreenState::CARD_SELECT && drink.isValidAction(gc)) actions.push_back(drink);
            if (discard.isValidAction(gc)) actions.push_back(discard);
        }
        if (gc.screenState == ScreenState::REWARDS && gc.hasRelic(RelicId::SINGING_BOWL)) {
            const auto &r = gc.info.rewardsContainer;
            for (int g = 0; g < r.cardRewardCount; ++g) {
                const GameAction bowl(GameAction::RewardsActionType::CARD, g, 5);
                if (bowl.isValidAction(gc)) actions.push_back(bowl);
            }
        }
        return actions;
    }

    void scramblePrivate(GameContext &gc, int k) {
        gc.seed = 1000003ULL * (k + 7);
        Random *streams[] = {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng, &gc.mathUtilRng,
                             &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng, &gc.monsterRng, &gc.neowRng,
                             &gc.potionRng, &gc.relicRng, &gc.shuffleRng, &gc.treasureRng};
        int i = 0;
        for (auto *rng : streams) *rng = Random(97ULL * (k + 3) + i++);
        // Only the consumed queue prefix (fights already fought) is public.
        const int mo = std::min<int>(gc.monsterListOffset, gc.monsterList.size());
        const int eo = std::min<int>(gc.eliteMonsterListOffset, gc.eliteMonsterList.size());
        gc.monsterList.resize(mo);
        gc.eliteMonsterList.resize(eo);
        const MonsterEncounter normals[] = {MonsterEncounter::CULTIST, MonsterEncounter::JAW_WORM,
                                            MonsterEncounter::SNECKO, MonsterEncounter::CHOSEN};
        for (int j = 0; j < 3 && static_cast<int>(gc.monsterList.size()) < 16; ++j)
            gc.monsterList.push_back(normals[(j + k) % 4]);
        if (static_cast<int>(gc.eliteMonsterList.size()) < 10)
            gc.eliteMonsterList.push_back(k % 2 ? MonsterEncounter::SLAVERS : MonsterEncounter::GREMLIN_LEADER);
        gc.secondBoss = k % 2 ? MonsterEncounter::TIME_EATER : MonsterEncounter::AWAKENED_ONE;
        gc.potionChance = 10 * k - 20;
        gc.cardRarityFactor = -40 + 9 * k;
        gc.monsterChance = 0.1f * k;
        gc.shopChance = 0.03f * k;
        gc.treasureChance = 0.02f * k;
        gc.eventList = k % 2 ? std::vector<Event>{Event::BIG_FISH} : std::vector<Event>{};
        gc.shrineList = k % 2 ? std::vector<Event>{Event::PURIFIER} : std::vector<Event>{Event::GOLDEN_SHRINE};
        gc.specialOneTimeEventList = {};
        gc.commonRelicPool = {RelicId::ANCHOR};
        gc.uncommonRelicPool = {};
        gc.rareRelicPool = k % 2 ? std::vector<RelicId>{RelicId::GIRYA} : std::vector<RelicId>{};
        gc.shopRelicPool = {};
        gc.bossRelicPool = {RelicId::SOZU};
        std::rotate(gc.colorlessCardPool.begin(), gc.colorlessCardPool.begin() + 1 + k % 5, gc.colorlessCardPool.end());
        gc.info.tier = k % 2 ? RelicTier::RARE : RelicTier::COMMON;
        gc.info.haveGold = k % 2;
        gc.info.rewards = {k % 3, (k + 1) % 3, (k + 2) % 3};
        gc.info.transformRng = k % 2 ? MISC_RNG : NEOW_RNG;
        // The Dead Adventurer elite is public (event text); elsewhere a non-battle encounter field is stale.
        if (gc.screenState != ScreenState::BATTLE
                && !(gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::DEAD_ADVENTURER))
            gc.info.encounter = k % 2 ? MonsterEncounter::GREMLIN_NOB : MonsterEncounter::THREE_SENTRIES;
        if (gc.map) {
            gc.map = std::make_shared<Map>(*gc.map);   // never mutate the shared map of the original
            gc.map->burningEliteBuff = k % 4;
        }
        // Face-down Match and Keep cards are hidden: swap two unseen slots' cards.
        if (gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::MATCH_AND_KEEP) {
            auto &s = gc.info.toSelectCards;
            int a = -1;
            for (int j = 0; j < static_cast<int>(s.size()); ++j) {
                if (s[j].deckIdx != GameContext::MATCH_AND_KEEP_UNSEEN) continue;
                if (a < 0) { a = j; continue; }
                std::swap(s[a].card, s[j].card);
                break;
            }
        }
    }

    using Tuple = std::tuple<int, int, int, int, int, std::vector<std::uint16_t>>;

    void verify(const GameContext &gc, const std::vector<GameAction> &actions, const AmberTokens &t,
                std::map<std::string, int> &cutBy) {
        check(t.n[static_cast<int>(AmberTokenType::RUN)] == 1, "one RUN token", gc);
        check(t.n[static_cast<int>(AmberTokenType::PLAYER)] == 1, "one PLAYER token", gc);
        check(t.n[static_cast<int>(AmberTokenType::STATUS)] == 0 && t.n[static_cast<int>(AmberTokenType::MONSTER)] == 0,
              "no combat-only tokens", gc);
        for (int s = 0; s < kAmberTokenTypes; ++s) {
            check(t.n[s] <= kAmberCap[s], "segment within capacity", gc);
            for (int i = 0; i < t.n[s]; ++i) {
                const AmberToken &tok = t.tok[kAmberOff[s] + i];
                for (const auto id : tok.ids) check(id >= 0 && id < kAmberGameIdEnd, "id in vocabulary", gc);
                for (const auto h : tok.f) check(((h >> 10) & 0x1f) != 0x1f, "finite float", gc);
            }
        }
        // Capacity cuts come only from MAP, the deck (CARD) or relics.
        if (t.cut > 0) {
            const int expectAct = std::max(0, static_cast<int>(actions.size()) - kAmberMaxActions);
            bool full = false;
            for (const auto s : {AmberTokenType::MAP, AmberTokenType::CARD, AmberTokenType::RELIC})
                if (t.n[static_cast<int>(s)] == kAmberCap[static_cast<int>(s)]) {
                    full = true;
                    ++cutBy[s == AmberTokenType::MAP ? "MAP" : s == AmberTokenType::CARD ? "CARD" : "RELIC"];
                }
            check(full && expectAct == 0, "cut only from MAP / deck / relic overflow", gc);
        }
        check(t.nAct == std::min<int>(actions.size(), kAmberMaxActions), "one AmberAction per action", gc);
        std::map<std::uint32_t, Tuple> seen;
        std::set<Tuple> tuples;
        for (int i = 0; i < t.nAct; ++i) {
            const AmberAction &a = t.act[i];
            const auto ty = static_cast<AmberActionType>(a.type);
            check(a.type < kAmberActionTypes, "type in range", gc);
            check(ty != AmberActionType::UNKNOWN, "known action type (bits " + std::to_string(actions[i].bits) + ")", gc);
            const bool potion = ty == AmberActionType::USE_POTION || ty == AmberActionType::DISCARD_POTION;
            check(potion || a.type >= 10, "out-of-combat or potion type", gc);
            for (const auto [seg, idx] : {std::pair<int, int>{a.srcSeg, a.srcIdx}, {a.tgtSeg, a.tgtIdx}}) {
                if (seg == kAmberNoSeg) continue;
                check(seg < kAmberTokenTypes && idx < t.n[seg], "src / tgt on a live token", gc);
            }
            if (ty == AmberActionType::CHOOSE_OPTION)
                check(a.srcSeg == static_cast<int>(AmberTokenType::OPTION), "CHOOSE_OPTION has its OPTION", gc);
            if (ty == AmberActionType::CHOOSE_CARD)
                check(a.srcSeg == static_cast<int>(AmberTokenType::CARD), "CHOOSE_CARD has its CARD", gc);
            if (potion) check(a.srcSeg == static_cast<int>(AmberTokenType::POTION), "potion action has its POTION", gc);
            if (ty == AmberActionType::MAP_MOVE)
                check(a.tgtSeg == static_cast<int>(AmberTokenType::MAP), "MAP_MOVE has its MAP", gc);
            if (ty == AmberActionType::SKIP_OR_LEAVE)
                check(a.srcSeg == kAmberNoSeg && a.tgtSeg == kAmberNoSeg, "SKIP_OR_LEAVE has no token", gc);
            Tuple tu{a.type, a.srcSeg, a.srcIdx, a.tgtSeg, a.tgtIdx,
                     std::vector<std::uint16_t>(a.f.begin(), a.f.end())};
            const auto it = seen.find(actions[i].bits);
            if (it != seen.end()) {
                check(it->second == tu, "identical bits encode identically", gc);
                continue;
            }
            check(tuples.insert(tu).second, "distinct actions give distinct tuples", gc);
            seen.emplace(actions[i].bits, tu);
        }
    }

    // The fullest reward screen: five card rewards of four cards (the container's limit; review of #1080 found five
    // card rewards on seed 1117 floor 44), two gold, three relics with the sapphire key, five potions, Singing
    // Bowl. Every action must resolve to its token with no capacity cut outside MAP.
    void fullRewardScreen(const GameContext &from) {
        GameContext gc = from;
        gc.screenState = ScreenState::REWARDS;
        gc.potionCapacity = 5;
        gc.potionCount = 0;
        for (auto &p : gc.potions) p = Potion::EMPTY_POTION_SLOT;
        if (!gc.hasRelic(RelicId::SINGING_BOWL)) gc.relics.add({RelicId::SINGING_BOWL, 0});
        Rewards r;
        const CardId ids[] = {CardId::ANGER, CardId::CLOTHESLINE, CardId::SHRUG_IT_OFF, CardId::POMMEL_STRIKE,
                              CardId::INFLAME};
        for (int g = 0; g < 5; ++g) {
            CardReward cr;
            for (int x = 0; x < 4; ++x) cr.push_back(Card(ids[(g + x) % 5], x % 2));
            r.addCardReward(cr);
        }
        r.addGold(25);
        r.addGold(40);
        r.addRelic(RelicId::ANCHOR);
        r.addRelic(RelicId::KUNAI);
        r.addRelic(RelicId::GIRYA);
        for (int i = 0; i < 5; ++i) r.addPotion(i % 2 ? Potion::FIRE_POTION : Potion::BLOCK_POTION);
        r.sapphireKey = true;
        gc.info.rewardsContainer = r;
        const auto actions = actionsFor(gc);
        AmberTokens t;
        amberEncodeGame(gc, actions, t);
        std::map<std::string, int> cutBy;
        verify(gc, actions, t, cutBy);
        int cards = 0;
        for (const auto &a : actions)
            if (a.getRewardsActionType() == GameAction::RewardsActionType::CARD && a.getIdx2() != 5) ++cards;
        check(cards == 20, "fixture offers 20 reward cards", gc);
        check(t.cut == 0 || t.n[static_cast<int>(AmberTokenType::MAP)] == kAmberCap[static_cast<int>(AmberTokenType::MAP)],
              "full reward screen: no cut outside MAP", gc);
        for (int i = 0; i < t.nAct; ++i)
            check(t.act[i].srcSeg != kAmberNoSeg || t.act[i].type == static_cast<int>(AmberActionType::SKIP_OR_LEAVE),
                  "full reward screen: every choice has its token", gc);
    }

}

int main(int argc, char **argv) {
    const int runs = argc > 1 ? std::atoi(argv[1]) : 200;
    std::map<int, int> screens;
    std::set<int> events;
    std::map<int, int> types;
    std::map<std::string, int> cutBy;
    long states = 0, scrambled = 0, victories = 0, act4 = 0, deadAdventurerChecks = 0;
    bool fullRewardDone = false;
    double encodeNs = 0;
    AmberTokens a, b;
    for (int run = 0; run < runs; ++run) {
        const std::uint64_t seed = 1 + run;
        GameContext gc(CharacterClass::IRONCLAD, seed, 20);
        gc.skipBattles = true;
        std::mt19937 rng(static_cast<unsigned>(seed));
        for (int step = 0; step < 3000 && gc.outcome == GameOutcome::UNDECIDED; ++step) {
            const auto actions = actionsFor(gc);
            if (actions.empty()) break;
            if (run == 0 && gc.screenState == ScreenState::REWARDS && !fullRewardDone) {
                fullRewardScreen(gc);
                fullRewardDone = true;
            }
            ++states;
            ++screens[static_cast<int>(gc.screenState)];
            if (gc.screenState == ScreenState::EVENT_SCREEN) events.insert(static_cast<int>(gc.curEvent));
            if (gc.act == 4) ++act4;

            std::memset(&a, 0xa5, sizeof(a));
            const auto t0 = std::chrono::steady_clock::now();
            amberEncodeGame(gc, actions, a);
            encodeNs += std::chrono::duration<double, std::nano>(std::chrono::steady_clock::now() - t0).count();
            verify(gc, actions, a, cutBy);
            for (int i = 0; i < a.nAct; ++i) ++types[a.act[i].type];

            std::memset(&b, 0x3c, sizeof(b));
            amberEncodeGame(gc, actions, b);
            check(liveBytes(a) == liveBytes(b), "deterministic", gc);

            {   // encounter tokens (RunConfig::enemyTokens): appended MONSTER tokens only, one per possible fight
                b = a;
                amberAppendEncounterTokens(gc, b);
                const int mi = static_cast<int>(AmberTokenType::MONSTER);
                const int want = (gc.boss != MonsterEncounter::INVALID)
                    + (gc.act >= 4 ? 1 : gc.act >= 1 ? 3 + MonsterEncounterPool::strongCount[gc.act - 1] : 0);
                check(b.n[mi] == want && b.cut == a.cut, "one encounter token per fight of the act", gc);
                for (int s = 0; s < kAmberTokenTypes; ++s)
                    if (s != mi) check(b.n[s] == a.n[s], "encounter tokens leave other segments alone", gc);
                for (int i = 0; i < b.n[mi]; ++i) {
                    const AmberToken &tok = b.tok[kAmberOff[mi] + i];
                    const int kind = tok.ids[3] - kAmberEncounterKindBase;
                    check(kind >= 0 && kind < kAmberEncounterKinds, "encounter kind id", gc);
                    check(kind == (i == 0 ? 0 : (gc.act >= 4 || i <= 3) ? 1 : 2), "boss, elites, hallway order", gc);
                    check(tok.ids[0] >= kAmberMonsterBase && tok.ids[0] < kAmberMoveBase, "encounter has a monster", gc);
                    for (int k = 1; k < 3; ++k)
                        check(tok.ids[k] == 0 || (tok.ids[k] >= kAmberMonsterBase && tok.ids[k] < kAmberMoveBase),
                              "encounter ids are monsters", gc);
                    check(amberHalfToFloat(tok.f[0]) > 0.05f && amberHalfToFloat(tok.f[1]) > 0.1f, "HP and count", gc);
                }
                AmberTokens c = a;
                amberAppendEncounterTokens(gc, c);
                check(liveBytes(b) == liveBytes(c), "encounter tokens deterministic", gc);
            }

            if (step % 3 == 0) {
                GameContext priv = gc;
                scramblePrivate(priv, run + step);
                amberEncodeGame(priv, actions, b);
                check(liveBytes(a) == liveBytes(b), "private fields do not reach the tokens", gc);
                ++scrambled;
            }
            if (step % 7 == 0) {   // every visible field must reach the tokens
                const auto visible = [&](const char *what, auto &&mutate) {
                    GameContext vis = gc;
                    if (vis.map) vis.map = std::make_shared<Map>(*vis.map);
                    if (!mutate(vis)) return;
                    amberEncodeGame(vis, actions, b);
                    check(liveBytes(a) != liveBytes(b), std::string(what) + " reaches the tokens", gc);
                };
                visible("gold", [](GameContext &g) { g.gold += 13; return true; });
                visible("curHp", [](GameContext &g) { if (g.curHp < 2) return false; --g.curHp; return true; });
                visible("maxHp", [](GameContext &g) { ++g.maxHp; return true; });
                visible("floor", [](GameContext &g) { ++g.floorNum; return true; });
                visible("act", [](GameContext &g) { g.act = g.act % 4 + 1; return true; });
                visible("ascension", [](GameContext &g) { g.ascension = 19; return true; });
                visible("ruby key", [](GameContext &g) { g.redKey = !g.redKey; return true; });
                visible("emerald key", [](GameContext &g) { g.greenKey = !g.greenKey; return true; });
                visible("sapphire key", [](GameContext &g) { g.blueKey = !g.blueKey; return true; });
                visible("boss", [](GameContext &g) {
                    g.boss = g.boss == MonsterEncounter::HEXAGHOST ? MonsterEncounter::SLIME_BOSS : MonsterEncounter::HEXAGHOST;
                    return true;
                });
                visible("removals bought", [](GameContext &g) { ++g.shopRemoveCount; return true; });
                visible("fights fought", [](GameContext &g) {
                    if (g.monsterListOffset >= static_cast<int>(g.monsterList.size())) return false;
                    ++g.monsterListOffset;
                    return true;
                });
                visible("deck card upgrade", [](GameContext &g) {
                    if (g.deck.size() == 0) return false;
                    g.deck.cards[g.deck.size() - 1].upgraded = !g.deck.cards[g.deck.size() - 1].upgraded;
                    return true;
                });
                visible("deck card misc", [](GameContext &g) {
                    if (g.deck.size() == 0 || g.deck.cards[0].id == CardId::SEARING_BLOW) return false;
                    ++g.deck.cards[0].misc;
                    return true;
                });
                visible("deck card", [](GameContext &g) {
                    if (g.deck.size() == 0) return false;
                    g.deck.cards[0].id = g.deck.cards[0].id == CardId::BASH ? CardId::ANGER : CardId::BASH;
                    return true;
                });
                visible("relic counter", [](GameContext &g) {
                    if (g.relics.relics.empty() || g.relics.relics[0].id == RelicId::WING_BOOTS) return false;
                    ++g.relics.relics[0].data;
                    return true;
                });
                visible("potion", [](GameContext &g) {
                    if (g.potionCapacity < 1) return false;
                    g.potions[0] = g.potions[0] == Potion::FIRE_POTION ? Potion::BLOCK_POTION : Potion::FIRE_POTION;
                    return true;
                });
                visible("map position", [](GameContext &g) {
                    if (!g.map || g.curMapNodeY < 0 || g.curMapNodeY > 13) return false;
                    for (int x = 0; x < 7; ++x)
                        if (x != g.curMapNodeX && g.map->getNode(x, g.curMapNodeY).room != Room::NONE) {
                            g.curMapNodeX = x;
                            return true;
                        }
                    return false;
                });
                visible("map room type", [](GameContext &g) {
                    if (!g.map || g.curMapNodeY >= 13) return false;
                    const int y = g.curMapNodeY + 1;
                    for (int x = 0; x < 7; ++x) {
                        auto &n = g.map->getNode(x, y);
                        if (n.room == Room::NONE || n.room == Room::BOSS) continue;
                        if (g.curMapNodeY >= 0 && g.mapMoveCost(x) < 0) continue;
                        n.room = n.room == Room::REST ? Room::ELITE : Room::REST;
                        return true;
                    }
                    return false;
                });
                visible("burning elite", [](GameContext &g) {
                    if (!g.map || g.curMapNodeY >= 13 || g.act > 3) return false;
                    const int y = g.curMapNodeY + 1;
                    for (int x = 0; x < 7; ++x)
                        if (g.map->getNode(x, y).room != Room::NONE && (g.curMapNodeY < 0 || g.mapMoveCost(x) >= 0)
                                && !(g.map->burningEliteX == x && g.map->burningEliteY == y)) {
                            g.map->burningEliteX = x;
                            g.map->burningEliteY = y;
                            return true;
                        }
                    return false;
                });
                // The current screen's numbers.
                if (gc.screenState == ScreenState::SHOP_ROOM)
                    visible("shop price", [](GameContext &g) {
                        for (int i = 0; i < 13; ++i)
                            if (g.info.shop.prices[i] > 0) { ++g.info.shop.prices[i]; return true; }
                        return false;
                    });
                if (gc.screenState == ScreenState::REWARDS)
                    visible("reward", [](GameContext &g) {
                        auto &r = g.info.rewardsContainer;
                        if (r.goldRewardCount > 0) { ++r.gold[0]; return true; }
                        if (r.cardRewardCount > 0 && r.cardRewards[0].size() > 0) {
                            r.cardRewards[0][0].upgraded = !r.cardRewards[0][0].upgraded;
                            return true;
                        }
                        return false;
                    });
                if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS)
                    visible("boss relic", [](GameContext &g) {
                        g.info.bossRelics[0] = g.info.bossRelics[0] == RelicId::SOZU ? RelicId::ECTOPLASM : RelicId::SOZU;
                        return true;
                    });
                if (gc.screenState == ScreenState::TREASURE_ROOM)
                    visible("chest size", [](GameContext &g) {
                        g.info.chestSize = g.info.chestSize == ChestSize::SMALL ? ChestSize::LARGE : ChestSize::SMALL;
                        return true;
                    });
                if (gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::DEAD_ADVENTURER
                        && (GameAction::getValidEventSelectBits(gc) & 1))
                    visible("dead adventurer elite", [&](GameContext &g) {
                        ++deadAdventurerChecks;
                        g.info.encounter = g.info.encounter == MonsterEncounter::GREMLIN_NOB
                            ? MonsterEncounter::LAGAVULIN_EVENT : MonsterEncounter::GREMLIN_NOB;
                        return true;
                    });
                if (gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::NEOW)
                    visible("neow drawback", [](GameContext &g) {
                        for (auto &o : g.info.neowRewards)
                            if (o.r != Neow::Bonus::INVALID) {
                                o.d = o.d == Neow::Drawback::CURSE ? Neow::Drawback::NO_GOLD : Neow::Drawback::CURSE;
                                return true;
                            }
                        return false;
                    });
            }

            // Mostly the ordinary legal actions; sometimes a potion action.
            const auto base = GameAction::getAllActionsInState(gc);
            const GameAction pick = (rng() % 20 == 0 || base.empty())
                ? actions[rng() % actions.size()] : base[rng() % base.size()];
            pick.execute(gc);
        }
        if (gc.outcome == GameOutcome::PLAYER_VICTORY) ++victories;
    }
    const ScreenState need[] = {ScreenState::EVENT_SCREEN, ScreenState::REWARDS, ScreenState::BOSS_RELIC_REWARDS,
                                ScreenState::CARD_SELECT, ScreenState::MAP_SCREEN, ScreenState::TREASURE_ROOM,
                                ScreenState::REST_ROOM, ScreenState::SHOP_ROOM};
    for (const auto s : need)
        if (!screens.count(static_cast<int>(s))) {
            std::cerr << "FAIL: screen " << static_cast<int>(s) << " never visited\n";
            ++g_fail;
        }
    if (!fullRewardDone) {
        std::cerr << "FAIL: full reward screen fixture never ran\n";
        ++g_fail;
    }
    if (deadAdventurerChecks == 0) {
        std::cerr << "FAIL: no Dead Adventurer elite visibility check ran\n";
        ++g_fail;
    }
    for (const int ty : {2, 3, 10, 11, 12, 13})
        if (!types.count(ty)) {
            std::cerr << "FAIL: action type " << ty << " never produced\n";
            ++g_fail;
        }
    std::cout << "amber_game_encoder: " << runs << " runs, " << states << " states (" << scrambled
              << " scrambled), victories " << victories << ", act-4 states " << act4 << ", events seen "
              << events.size() << ", Dead Adventurer checks " << deadAdventurerChecks << ", mean encode " << encodeNs / std::max(1L, states) / 1000.0 << " us\n  screens:";
    for (const auto &[s, c] : screens) std::cout << ' ' << s << '=' << c;
    std::cout << "\n  action types:";
    for (const auto &[ty, c] : types) std::cout << ' ' << ty << '=' << c;
    std::cout << "\n  cut states by full segment:";
    for (const auto &[k, c] : cutBy) std::cout << ' ' << k << '=' << c;
    std::cout << '\n';
    if (g_fail) {
        std::cerr << "amber_game_encoder: " << g_fail << " failures\n";
        return 1;
    }
    std::cout << "amber_game_encoder: OK\n";
    return 0;
}
