// Native Amber-token encoder for out-of-combat GameContext states (stage 1 of the self-play loop, 2026-11-17); see
// AmberEncoder.h for the contract and id ranges. Same AmberTokens layout as amberEncodeCombat; the RUN token carries
// a screen id (ids[2]) that combat RUN tokens never have.
//
// Information content: what the game shows on screen. Never read: seed, RNG streams, event / relic / card pools,
// the unconsumed encounter queues, the second boss, pity counters (potion / rarity / room chances), unopened chest
// tier / gold, the Dead Adventurer reward order, the burning elite's buff, face-down Match and Keep cards,
// the transform RNG reference. Event numbers are read only for the events that show them (whitelist below).
//
// Float layout per token (index: value; "/k" = divided by k; flags are 0/1; one-hots list their first value).
// Every slot past the listed ones is 0.
//
// RUN (1 token; ids[0] = current event (curEvent >= NEOW), ids[1] = act boss (its main monster id), ids[2] = screen)
//   0 act/4  1 ascension/20  2 floorNum/50 (as combat)  3 (curMapNodeX + 1)/7  4 (curMapNodeY + 1)/16
//   5-13 screen one-hot (EVENT_SCREEN .. BATTLE)  14-22 curRoom one-hot (SHOP .. NONE)
//   23 sapphire (blue) key  24 emerald (green) key  25 ruby (red) key  26 keysEnabled
//   27 potionCount/5  28 potionCapacity/5  29 deck size/30  30 relic count/20  31 shopRemoveCount/5
//   32 Wing Boots charges/3 (when owned)  33 normal fights this act/10  34 elite fights this act/5
//   35 the map has a burning elite  36 outcome victory  37 outcome loss  38 restRoomResolved
//   card select: 39 toSelectCount/3  40 picked so far/3  41 selectable cards/30  42-49 select type one-hot
//     (TRANSFORM .. BONFIRE_SPIRITS)
//   treasure room: 50-52 chest size one-hot (SMALL, MEDIUM, LARGE)
//   event screen, events that show the number only: 53 eventData/5 (Colosseum, Cursed Tome phase, Match and Keep
//     attempts)  54 phase/3 (Dead Adventurer searches, Golden Idol)  55-57 hpAmount0..2/100  58 goldLoss/100
//     (World of Goop)  59 gold/100 (We Meet Again)  60 upgradeOne  61 cleanUpIsRemoveCard (Designer In-Spire)
//   shop: 62 removeCost/100 (while offered)  63 removal offered
// PLAYER (1 token, ids none; the combat PLAYER indices where they apply)
//   0 curHp/100  1 maxHp/100  2 curHp/maxHp  7 gold/100  39 characterClass (raw)
// CARD (the master deck in deck order, then the cards the screen offers: on a card-select screen the ones that are
//   not deck cards (The Library, Neow / colorless choices) in screen order, on a reward screen every card reward
//   (group-major); ids[0] = card id; combat CARD indices where they apply)
//   10 master deck (combat zones are 0-9)  11 deck index (offered: screen index, rewards group * 4 + position)/10  12 upgraded  13 cost/3
//   14 cost/3 (costForTurn)  17 specialData/10 (CardInstance: misc, Searing Blow upgrade count)  32 bottled
//   33 canUpgrade  34 canTransform  35 selectable on the current card-select screen  36 already picked on it
//   37 offered by the screen (not a deck card)  38 card reward  39 reward group/5  40 position in the group/4
// RELIC (gc.relics order; ids[0] = relic id)  0 counter (relic data; Wing Boots: charges)/10  1 1  2 order/20
// POTION (one per filled slot; ids[0] = potion id)  0 slot/5  1 needs a target  2 1  3 drinkable out of combat
// OPTION (the screen's choices; ids[0] = the item (card / relic / potion / event id), ids[1] = the deck card,
//   relic or potion an event option names, the Note For Yourself card, or the Dead Adventurer elite's monster id)
//   3 1 (out-of-combat option)  12-28 kind one-hot (REWARD_GOLD, REWARD_CARD (unused: card rewards are CARD
//   tokens), REWARD_RELIC, REWARD_POTION, REWARD_EMERALD_KEY, REWARD_SAPPHIRE_KEY, SINGING_BOWL, SHOP_CARD, SHOP_RELIC, SHOP_POTION, SHOP_REMOVE,
//   BOSS_RELIC, REST, NEOW, EVENT, MATCH_SLOT, CHEST)  30 index within its group/16
//   31 legal now  32 price/100  33 affordable  34 gold amount/100 (gold reward, We Meet Again gold)
//   35 card upgraded  38 card specialData/10
//   39 relic paired with the sapphire key
//   kind-specific block 40-63:
//     MATCH_SLOT 40 face down unseen  41 seen  42 face up (pending pair)  43 matched
//     REST       40-46 rest option one-hot (REST, SMITH, RECALL, LIFT, TOKE, DIG, SKIP)
//     CHEST      40-42 chest size one-hot (SMALL, MEDIUM, LARGE)
//     NEOW       40-58 bonus one-hot (Neow::Bonus order)  59-63 drawback one-hot (TEN_PERCENT_HP_LOSS ..
//                LOSE_STARTER_RELIC; NONE = all 0)
//     EVENT      40-51 option index one-hot  52 names a deck card  53 a relic  54 a potion  55 a gold amount
//                56 names a monster (Dead Adventurer search: ids[1] = the elite, which the event text reveals)
// MAP (the act's nodes still reachable: current node, the boss, then by row (nearest first) and column; the rest
//   counted in out.cut; ids[0] = boss monster id on a boss token; with a Wing Boots charge every later node with an
//   exit counts as reachable)
//   0 x/6  1 y/15  2 rows ahead/15  3-10 room one-hot (SHOP .. BOSS_TREASURE)  11 edgeCount/3  12-14 edge to
//   x-1, x, x+1  15 parentCount/6  16 burning elite  17 current node  18 act boss (virtual row 15 after row 14)
//   19 reachable by ordinary edges  20 legal next destination  21 Wing Boots jump destination  22 row 14 (leads to
//   the boss)
// Actions (f = float16 bits): every out-of-combat action sets f[4] = idx1/16, f[5] = idx2/8,
//   f[6] = RewardsActionType (raw)/8 (rewards and shop screens), f[7] = screen (raw)/10, so distinct GameAction bits
//   stay distinct without the tokens. MAP_MOVE f[0] = x/6, f[1] = Wing Boots jump. Potions: f[0] = slot/5.
#include "sim/search/AmberEncoder.h"

#include <algorithm>
#include <array>
#include <memory>
#include <cstring>

#include "combat/BattleContext.h"
#include "constants/Events.h"
#include "constants/MonsterEncounters.h"
#include "game/Map.h"
#include "game/Neow.h"

namespace sts::search {

    namespace {

        using T = AmberTokenType;
        using RT = GameAction::RewardsActionType;
        constexpr std::uint8_t kNone = 0xff;
        constexpr std::uint16_t kOne = 0x3c00;   // 1.0 in float16

        enum class OptKind : int {
            REWARD_GOLD, REWARD_CARD, REWARD_RELIC, REWARD_POTION, REWARD_EMERALD_KEY, REWARD_SAPPHIRE_KEY,
            SINGING_BOWL, SHOP_CARD, SHOP_RELIC, SHOP_POTION, SHOP_REMOVE, BOSS_RELIC, REST, NEOW, EVENT,
            MATCH_SLOT, CHEST, COUNT
        };
        static_assert(static_cast<int>(OptKind::COUNT) == 17, "OPTION kind one-hot spans 12-28");

        struct Enc {
            AmberTokens &out;
            std::uint8_t deckTok[Deck::MAX_SIZE];
            std::uint8_t relicTok[kAmberCap[static_cast<int>(T::RELIC)]];
            std::uint8_t potTok[5];
            std::uint8_t mapTok[15][7];
            std::uint8_t bossTok = kNone;
            // OPTION token indices per screen item.
            std::uint8_t goldTok[2], cardTok[5][4], rRelicTok[3], rPotTok[5], keyTok = kNone, bowlTok = kNone;
            std::uint8_t shopCardTok[7], shopRelicTok[3], shopPotTok[3], removeTok = kNone;
            std::uint8_t bossRelicTok[3], restTok[7], eventTok[12], selectTok[Deck::MAX_SIZE], chestTok = kNone;

            explicit Enc(AmberTokens &o) : out(o) {
                std::memset(deckTok, kNone, sizeof(deckTok));
                std::memset(relicTok, kNone, sizeof(relicTok));
                std::memset(potTok, kNone, sizeof(potTok));
                std::memset(mapTok, kNone, sizeof(mapTok));
                std::memset(goldTok, kNone, sizeof(goldTok));
                std::memset(cardTok, kNone, sizeof(cardTok));
                std::memset(rRelicTok, kNone, sizeof(rRelicTok));
                std::memset(rPotTok, kNone, sizeof(rPotTok));
                std::memset(shopCardTok, kNone, sizeof(shopCardTok));
                std::memset(shopRelicTok, kNone, sizeof(shopRelicTok));
                std::memset(shopPotTok, kNone, sizeof(shopPotTok));
                std::memset(bossRelicTok, kNone, sizeof(bossRelicTok));
                std::memset(restTok, kNone, sizeof(restTok));
                std::memset(eventTok, kNone, sizeof(eventTok));
                std::memset(selectTok, kNone, sizeof(selectTok));
            }

            AmberToken *push(T s, std::uint8_t *idx = nullptr) {
                const int si = static_cast<int>(s);
                if (out.n[si] >= kAmberCap[si]) {
                    ++out.cut;
                    return nullptr;
                }
                const int i = out.n[si]++;
                AmberToken &t = out.tok[kAmberOff[si] + i];
                std::memset(&t, 0, sizeof(t));
                if (idx) *idx = static_cast<std::uint8_t>(i);
                return &t;
            }
        };

        inline void put(AmberToken &t, int i, float v) { t.f[i] = amberHalf(v); }
        inline void flag(AmberToken &t, int i, bool v) { t.f[i] = v ? kOne : 0; }

        inline std::int16_t cardId(CardId id) {
            return id == CardId::INVALID ? 0 : static_cast<std::int16_t>(kAmberCardBase + static_cast<int>(id) - 1);
        }
        inline std::int16_t relicId(RelicId r) {
            return r == RelicId::INVALID ? 0 : static_cast<std::int16_t>(kAmberRelicBase + static_cast<int>(r));
        }
        inline bool realPotion(Potion p) { return p != Potion::INVALID && p != Potion::EMPTY_POTION_SLOT; }
        inline std::int16_t potionId(Potion p) {
            return realPotion(p) ? static_cast<std::int16_t>(kAmberPotionBase + static_cast<int>(p) - 2) : 0;
        }
        inline std::int16_t eventId(Event e) {
            return static_cast<int>(e) >= static_cast<int>(Event::NEOW)
                ? static_cast<std::int16_t>(kAmberEventBase + static_cast<int>(e) - static_cast<int>(Event::NEOW)) : 0;
        }
        inline bool drinkableOutOfCombat(Potion p) {
            return p == Potion::BLOOD_POTION || p == Potion::FRUIT_JUICE || p == Potion::ENTROPIC_BREW;
        }

        std::int16_t bossId(MonsterEncounter b) {
            MonsterId m;
            switch (b) {
                case MonsterEncounter::SLIME_BOSS: m = MonsterId::SLIME_BOSS; break;
                case MonsterEncounter::THE_GUARDIAN: m = MonsterId::THE_GUARDIAN; break;
                case MonsterEncounter::HEXAGHOST: m = MonsterId::HEXAGHOST; break;
                case MonsterEncounter::AUTOMATON: m = MonsterId::BRONZE_AUTOMATON; break;
                case MonsterEncounter::COLLECTOR: m = MonsterId::THE_COLLECTOR; break;
                case MonsterEncounter::CHAMP: m = MonsterId::THE_CHAMP; break;
                case MonsterEncounter::AWAKENED_ONE: m = MonsterId::AWAKENED_ONE; break;
                case MonsterEncounter::TIME_EATER: m = MonsterId::TIME_EATER; break;
                case MonsterEncounter::DONU_AND_DECA: m = MonsterId::DONU; break;
                case MonsterEncounter::THE_HEART: m = MonsterId::CORRUPT_HEART; break;
                default: return 0;
            }
            return static_cast<std::int16_t>(kAmberMonsterBase + static_cast<int>(m) - 1);
        }

        // Dead Adventurer's elite as its main monster id (0 if unset).
        std::int16_t deadAdventurerElite(MonsterEncounter enc) {
            MonsterId m;
            switch (enc) {
                case MonsterEncounter::THREE_SENTRIES: m = MonsterId::SENTRY; break;
                case MonsterEncounter::GREMLIN_NOB: m = MonsterId::GREMLIN_NOB; break;
                case MonsterEncounter::LAGAVULIN_EVENT: m = MonsterId::LAGAVULIN; break;
                default: return 0;
            }
            return static_cast<std::int16_t>(kAmberMonsterBase + static_cast<int>(m) - 1);
        }

        AmberToken *option(Enc &e, OptKind kind, int index, bool legal, std::uint8_t *idx) {
            AmberToken *t = e.push(T::OPTION, idx);
            if (!t) return nullptr;
            flag(*t, 3, true);
            flag(*t, 12 + static_cast<int>(kind), true);
            put(*t, 30, index / 16.0f);
            flag(*t, 31, legal);
            return t;
        }

        void optionCard(AmberToken &t, const Card &c) {
            t.ids[0] = cardId(c.id);
            flag(t, 35, c.upgraded);
            put(t, 38, CardInstance(c).specialData / 10.0f);
        }

        // ---------------------------------------------------------------- state tokens

        bool eventShows(Event ev, int field) {
            // field: 0 eventData, 1 phase, 2..4 hpAmount0..2, 5 goldLoss, 6 gold, 7 Designer flags
            switch (field) {
                case 0: return ev == Event::COLOSSEUM || ev == Event::CURSED_TOME || ev == Event::MATCH_AND_KEEP;
                case 1: return ev == Event::DEAD_ADVENTURER || ev == Event::GOLDEN_IDOL;
                case 2:
                    switch (ev) {
                        case Event::BIG_FISH: case Event::FACE_TRADER: case Event::FORGOTTEN_ALTAR: case Event::GHOSTS:
                        case Event::GOLDEN_IDOL: case Event::KNOWING_SKULL: case Event::SHINING_LIGHT:
                        case Event::THE_CLERIC: case Event::THE_LIBRARY: case Event::THE_MOAI_HEAD:
                        case Event::THE_WOMAN_IN_BLUE: case Event::VAMPIRES: case Event::WINDING_HALLS:
                            return true;
                        default: return false;
                    }
                case 3: return ev == Event::GOLDEN_IDOL || ev == Event::KNOWING_SKULL || ev == Event::WINDING_HALLS;
                case 4: return ev == Event::KNOWING_SKULL || ev == Event::WINDING_HALLS;
                case 5: return ev == Event::WORLD_OF_GOOP;
                case 6: return ev == Event::WE_MEET_AGAIN;
                case 7: return ev == Event::DESIGNER_IN_SPIRE;
                default: return false;
            }
        }

        void run(Enc &e, const GameContext &gc) {
            AmberToken &t = *e.push(T::RUN);
            const auto &info = gc.info;
            const int screen = static_cast<int>(gc.screenState);
            t.ids[0] = eventId(gc.curEvent);
            t.ids[1] = bossId(gc.boss);
            if (screen >= 1 && screen <= static_cast<int>(ScreenState::BATTLE))
                t.ids[2] = static_cast<std::int16_t>(kAmberScreenBase + screen - 1);
            put(t, 0, gc.act / 4.0f);
            put(t, 1, gc.ascension / 20.0f);
            put(t, 2, gc.floorNum / 50.0f);
            put(t, 3, (gc.curMapNodeX + 1) / 7.0f);
            put(t, 4, (gc.curMapNodeY + 1) / 16.0f);
            if (screen >= 1 && screen <= 9) flag(t, 5 + screen - 1, true);
            const int room = static_cast<int>(gc.curRoom);
            if (room >= 0 && room <= static_cast<int>(Room::NONE)) flag(t, 14 + room, true);
            flag(t, 23, gc.blueKey);
            flag(t, 24, gc.greenKey);
            flag(t, 25, gc.redKey);
            flag(t, 26, gc.keysEnabled);
            put(t, 27, gc.potionCount / 5.0f);
            put(t, 28, gc.potionCapacity / 5.0f);
            put(t, 29, gc.deck.size() / 30.0f);
            put(t, 30, gc.relics.size() / 20.0f);
            put(t, 31, gc.shopRemoveCount / 5.0f);
            if (gc.relics.has(RelicId::WING_BOOTS)) put(t, 32, gc.wingBootsCharges / 3.0f);
            put(t, 33, std::min<int>(gc.monsterListOffset, gc.monsterList.size()) / 10.0f);
            put(t, 34, std::min<int>(gc.eliteMonsterListOffset, gc.eliteMonsterList.size()) / 5.0f);
            flag(t, 35, gc.map && gc.map->burningEliteX >= 0);
            flag(t, 36, gc.outcome == GameOutcome::PLAYER_VICTORY);
            flag(t, 37, gc.outcome == GameOutcome::PLAYER_LOSS);
            flag(t, 38, gc.restRoomResolved);
            if (gc.screenState == ScreenState::CARD_SELECT) {
                put(t, 39, info.toSelectCount / 3.0f);
                put(t, 40, info.haveSelectedCards.size() / 3.0f);
                put(t, 41, info.toSelectCards.size() / 30.0f);
                const int st = static_cast<int>(info.selectScreenType);
                if (st >= 1 && st <= 8) flag(t, 42 + st - 1, true);
            }
            if (gc.screenState == ScreenState::TREASURE_ROOM) {
                const int cs = static_cast<int>(info.chestSize);
                if (cs >= 0 && cs <= 2) flag(t, 50 + cs, true);
            }
            if (gc.screenState == ScreenState::EVENT_SCREEN) {
                const Event ev = gc.curEvent;
                if (eventShows(ev, 0)) put(t, 53, info.eventData / 5.0f);
                if (eventShows(ev, 1)) put(t, 54, info.phase / 3.0f);
                if (eventShows(ev, 2)) put(t, 55, info.hpAmount0 / 100.0f);
                if (eventShows(ev, 3)) put(t, 56, info.hpAmount1 / 100.0f);
                if (eventShows(ev, 4)) put(t, 57, info.hpAmount2 / 100.0f);
                if (eventShows(ev, 5)) put(t, 58, info.goldLoss / 100.0f);
                if (eventShows(ev, 6) && info.gold > 0) put(t, 59, info.gold / 100.0f);
                if (eventShows(ev, 7)) {
                    flag(t, 60, info.upgradeOne);
                    flag(t, 61, info.cleanUpIsRemoveCard);
                }
            }
            if (gc.screenState == ScreenState::SHOP_ROOM && info.shop.removeCost != -1) {
                put(t, 62, info.shop.removeCost / 100.0f);
                flag(t, 63, true);
            }
        }

        void player(Enc &e, const GameContext &gc) {
            AmberToken &t = *e.push(T::PLAYER);
            put(t, 0, gc.curHp / 100.0f);
            put(t, 1, gc.maxHp / 100.0f);
            put(t, 2, gc.maxHp > 0 ? static_cast<float>(gc.curHp) / static_cast<float>(gc.maxHp) : 0.0f);
            put(t, 7, gc.gold / 100.0f);
            put(t, 39, static_cast<float>(gc.cc));
        }

        // Deck index of a card-select entry, or -1 when it is not (or no longer) that deck card.
        int selectDeckIdx(const GameContext &gc, const SelectScreenCard &s) {
            const int d = s.deckIdx;
            if (d < 0 || d >= gc.deck.size()) return -1;
            return gc.deck.cards[d] == s.card ? d : -1;
        }

        // A CARD token for a card the screen offers (not a deck card): card-select choices, card rewards.
        AmberToken *offeredCard(Enc &e, const Card &c, int screenIdx, std::uint8_t *idx) {
            AmberToken *t = e.push(T::CARD, idx);
            if (!t) return nullptr;
            const CardInstance ci(c);
            t->ids[0] = cardId(c.id);
            put(*t, 11, screenIdx / 10.0f);
            flag(*t, 12, c.upgraded);
            put(*t, 13, ci.cost / 3.0f);
            put(*t, 14, ci.cost / 3.0f);
            put(*t, 17, ci.specialData / 10.0f);
            flag(*t, 33, c.canUpgrade());
            flag(*t, 34, c.canTransform());
            flag(*t, 35, true);
            flag(*t, 37, true);
            return t;
        }

        void deck(Enc &e, const GameContext &gc) {
            const auto &d = gc.deck;
            const int n = d.size();
            for (int i = 0; i < n; ++i) {
                AmberToken *t = e.push(T::CARD, &e.deckTok[i]);
                if (!t) continue;
                const Card &c = d.cards[i];
                const CardInstance ci(c);
                t->ids[0] = cardId(c.id);
                flag(*t, 10, true);
                put(*t, 11, i / 10.0f);
                flag(*t, 12, c.upgraded);
                put(*t, 13, ci.cost / 3.0f);
                put(*t, 14, ci.cost / 3.0f);
                put(*t, 17, ci.specialData / 10.0f);
                flag(*t, 32, d.isCardBottled(i));
                flag(*t, 33, c.canUpgrade());
                flag(*t, 34, c.canTransform());
            }
            if (gc.screenState != ScreenState::CARD_SELECT) return;
            const auto &info = gc.info;
            for (int i = 0; i < static_cast<int>(info.toSelectCards.size()); ++i) {
                const int di = selectDeckIdx(gc, info.toSelectCards[i]);
                if (di >= 0) {
                    if (e.deckTok[di] != kNone) flag(e.out.at(T::CARD, e.deckTok[di]), 35, true);
                    continue;
                }
                // A card offered by the screen, not in the deck (The Library, Neow / colorless choices, ...).
                offeredCard(e, info.toSelectCards[i].card, i, &e.selectTok[i]);
            }
            for (int i = 0; i < static_cast<int>(info.haveSelectedCards.size()); ++i) {
                const int di = info.haveSelectedCards[i].deckIdx;
                if (di >= 0 && di < n && e.deckTok[di] != kNone) flag(e.out.at(T::CARD, e.deckTok[di]), 36, true);
            }
        }

        void relics(Enc &e, const GameContext &gc) {
            const auto &rs = gc.relics.relics;
            const int n = static_cast<int>(rs.size());
            for (int i = 0; i < n; ++i) {
                AmberToken *t = e.push(T::RELIC, i < kAmberCap[static_cast<int>(T::RELIC)] ? &e.relicTok[i] : nullptr);
                if (!t) continue;
                t->ids[0] = relicId(rs[i].id);
                const int counter = rs[i].id == RelicId::WING_BOOTS ? gc.wingBootsCharges : rs[i].data;
                put(*t, 0, counter / 10.0f);
                flag(*t, 1, true);
                put(*t, 2, i / 20.0f);
            }
        }

        void potions(Enc &e, const GameContext &gc) {
            const int cap = gc.potionCapacity < 5 ? gc.potionCapacity : 5;
            for (int i = 0; i < cap; ++i) {
                const Potion p = gc.potions[i];
                if (!realPotion(p)) continue;
                AmberToken *t = e.push(T::POTION, &e.potTok[i]);
                if (!t) continue;
                t->ids[0] = potionId(p);
                put(*t, 0, i / 5.0f);
                flag(*t, 1, potionRequiresTarget(p));
                flag(*t, 2, true);
                flag(*t, 3, drinkableOutOfCombat(p));
            }
        }

        // ---------------------------------------------------------------- options per screen

        void rewardOptions(Enc &e, const GameContext &gc) {
            const auto &r = gc.info.rewardsContainer;
            const bool potionRoom = gc.potionCount < gc.potionCapacity;
            for (int i = 0; i < r.goldRewardCount && i < 2; ++i) {
                AmberToken *t = option(e, OptKind::REWARD_GOLD, i, true, &e.goldTok[i]);
                if (t) put(*t, 34, r.gold[i] / 100.0f);
            }
            for (int g = 0; g < r.cardRewardCount && g < 5; ++g) {
                const auto &cr = r.cardRewards[g];
                for (int x = 0; x < static_cast<int>(cr.size()) && x < 4; ++x) {
                    // Card rewards are CARD tokens: five groups of up to four cards overflow OPTION's 16 slots.
                    AmberToken *t = offeredCard(e, cr[x], g * 4 + x, &e.cardTok[g][x]);
                    if (!t) continue;
                    flag(*t, 38, true);
                    put(*t, 39, g / 5.0f);
                    put(*t, 40, x / 4.0f);
                }
            }
            if (r.cardRewardCount > 0 && gc.hasRelic(RelicId::SINGING_BOWL))
                option(e, OptKind::SINGING_BOWL, 0, true, &e.bowlTok);
            for (int i = 0; i < r.relicCount && i < 3; ++i) {
                AmberToken *t = option(e, OptKind::REWARD_RELIC, i, true, &e.rRelicTok[i]);
                if (!t) continue;
                t->ids[0] = relicId(r.relics[i]);
                flag(*t, 39, r.sapphireKey && i == r.relicCount - 1);
            }
            for (int i = 0; i < r.potionCount && i < 5; ++i) {
                AmberToken *t = option(e, OptKind::REWARD_POTION, i, potionRoom, &e.rPotTok[i]);
                if (t) t->ids[0] = potionId(r.potions[i]);
            }
            if (r.emeraldKey || r.sapphireKey)
                option(e, r.sapphireKey ? OptKind::REWARD_SAPPHIRE_KEY : OptKind::REWARD_EMERALD_KEY, 0, true, &e.keyTok);
        }

        void shopOptions(Enc &e, const GameContext &gc) {
            const auto &s = gc.info.shop;
            const bool potionOk = !Shop::rulesFixEnabled()
                || (gc.potionCount < gc.potionCapacity && !gc.hasRelic(RelicId::SOZU));
            for (int i = 0; i < 7; ++i) {
                const int price = s.cardPrice(i);
                if (price == -1) continue;
                AmberToken *t = option(e, OptKind::SHOP_CARD, i, gc.gold >= price, &e.shopCardTok[i]);
                if (!t) continue;
                optionCard(*t, s.cards[i]);
                put(*t, 32, price / 100.0f);
                flag(*t, 33, gc.gold >= price);
            }
            for (int i = 0; i < 3; ++i) {
                const int price = s.relicPrice(i);
                if (price == -1) continue;
                AmberToken *t = option(e, OptKind::SHOP_RELIC, i, gc.gold >= price, &e.shopRelicTok[i]);
                if (!t) continue;
                t->ids[0] = relicId(s.relics[i]);
                put(*t, 32, price / 100.0f);
                flag(*t, 33, gc.gold >= price);
            }
            for (int i = 0; i < 3; ++i) {
                const int price = s.potionPrice(i);
                if (price == -1) continue;
                AmberToken *t = option(e, OptKind::SHOP_POTION, i, gc.gold >= price && potionOk, &e.shopPotTok[i]);
                if (!t) continue;
                t->ids[0] = potionId(s.potions[i]);
                put(*t, 32, price / 100.0f);
                flag(*t, 33, gc.gold >= price);
            }
            if (s.removeCost != -1) {
                AmberToken *t = option(e, OptKind::SHOP_REMOVE, 0, gc.gold >= s.removeCost, &e.removeTok);
                if (t) {
                    put(*t, 32, s.removeCost / 100.0f);
                    flag(*t, 33, gc.gold >= s.removeCost);
                }
            }
        }

        void eventOptions(Enc &e, const GameContext &gc) {
            const auto &info = gc.info;
            if (gc.curEvent == Event::MATCH_AND_KEEP) {
                const int bits = GameAction::getValidEventSelectBits(gc);
                for (int i = 0; i < static_cast<int>(info.toSelectCards.size()) && i < 12; ++i) {
                    const auto &slot = info.toSelectCards[i];
                    AmberToken *t = option(e, OptKind::MATCH_SLOT, i, (bits >> i) & 1, &e.eventTok[i]);
                    if (!t) continue;
                    const int st = slot.deckIdx;
                    flag(*t, 40, st == GameContext::MATCH_AND_KEEP_UNSEEN);
                    flag(*t, 41, st == GameContext::MATCH_AND_KEEP_SEEN);
                    flag(*t, 42, st == GameContext::MATCH_AND_KEEP_FACE_UP);
                    flag(*t, 43, st == GameContext::MATCH_AND_KEEP_MATCHED);
                    if (st != GameContext::MATCH_AND_KEEP_UNSEEN) optionCard(*t, slot.card);
                }
                return;
            }
            const int bits = GameAction::getValidEventSelectBits(gc);
            for (int i = 0; i < 12; ++i) {
                if (!((bits >> i) & 1)) continue;
                if (gc.curEvent == Event::NEOW) {
                    AmberToken *t = option(e, OptKind::NEOW, i, true, &e.eventTok[i]);
                    if (!t || i >= static_cast<int>(info.neowRewards.size())) continue;
                    const int b = static_cast<int>(info.neowRewards[i].r);
                    const int d = static_cast<int>(info.neowRewards[i].d);
                    if (b >= 0 && b < static_cast<int>(Neow::Bonus::INVALID)) flag(*t, 40 + b, true);
                    if (d >= static_cast<int>(Neow::Drawback::TEN_PERCENT_HP_LOSS)
                            && d <= static_cast<int>(Neow::Drawback::LOSE_STARTER_RELIC))
                        flag(*t, 59 + d - static_cast<int>(Neow::Drawback::TEN_PERCENT_HP_LOSS), true);
                    continue;
                }
                AmberToken *t = option(e, OptKind::EVENT, i, true, &e.eventTok[i]);
                if (!t) continue;
                t->ids[0] = eventId(gc.curEvent);
                flag(*t, 40 + i, true);
                const auto deckCardRef = [&](int di) {
                    if (di < 0 || di >= gc.deck.size()) return;
                    t->ids[1] = cardId(gc.deck.cards[di].id);
                    flag(*t, 35, gc.deck.cards[di].upgraded);
                    flag(*t, 52, true);
                };
                switch (gc.curEvent) {
                    case Event::FALLING:
                        if (i == 0) deckCardRef(info.skillCardDeckIdx);
                        else if (i == 1) deckCardRef(info.powerCardDeckIdx);
                        else if (i == 2) deckCardRef(info.attackCardDeckIdx);
                        break;
                    case Event::WE_MEET_AGAIN:
                        if (i == 0 && info.potionIdx >= 0 && info.potionIdx < 5) {
                            t->ids[1] = potionId(gc.potions[info.potionIdx]);
                            flag(*t, 54, true);
                        } else if (i == 1 && info.gold > 0) {
                            put(*t, 34, info.gold / 100.0f);
                            flag(*t, 55, true);
                        } else if (i == 2) {
                            deckCardRef(info.cardIdx);
                        }
                        break;
                    case Event::NLOTH: {
                        const int ri = i == 0 ? info.relicIdx0 : i == 1 ? info.relicIdx1 : -1;
                        if (ri >= 0 && ri < gc.relics.size()) {
                            t->ids[1] = relicId(gc.relics.relics[ri].id);
                            flag(*t, 53, true);
                        }
                        break;
                    }
                    case Event::NOTE_FOR_YOURSELF:
                        if (i == 0) {
                            t->ids[1] = cardId(gc.noteForYourselfCard.id);
                            flag(*t, 35, gc.noteForYourselfCard.upgraded);
                        }
                        break;
                    case Event::DEAD_ADVENTURER:
                        // The event text names the killer (it matches one elite unambiguously): public.
                        if (i == 0) {
                            t->ids[1] = deadAdventurerElite(info.encounter);
                            flag(*t, 56, t->ids[1] != 0);
                        }
                        break;
                    default: break;
                }
            }
        }

        void options(Enc &e, const GameContext &gc) {
            const auto &info = gc.info;
            switch (gc.screenState) {
                case ScreenState::REWARDS: rewardOptions(e, gc); break;
                case ScreenState::SHOP_ROOM: shopOptions(e, gc); break;
                case ScreenState::EVENT_SCREEN: eventOptions(e, gc); break;
                case ScreenState::BOSS_RELIC_REWARDS:
                    for (int i = 0; i < 3; ++i) {
                        if (info.bossRelics[i] == RelicId::INVALID) continue;
                        AmberToken *t = option(e, OptKind::BOSS_RELIC, i, true, &e.bossRelicTok[i]);
                        if (t) t->ids[0] = relicId(info.bossRelics[i]);
                    }
                    break;
                case ScreenState::REST_ROOM:
                    for (int i = 0; i < 6; ++i) {
                        if (!GameAction(i).isValidAction(gc)) continue;
                        AmberToken *t = option(e, OptKind::REST, i, true, &e.restTok[i]);
                        if (t) flag(*t, 40 + i, true);
                    }
                    break;
                case ScreenState::TREASURE_ROOM: {
                    AmberToken *t = option(e, OptKind::CHEST, 0, true, &e.chestTok);
                    const int cs = static_cast<int>(info.chestSize);
                    if (t && cs >= 0 && cs <= 2) flag(*t, 40 + cs, true);
                    break;
                }
                default: break;
            }
        }

        // ---------------------------------------------------------------- map

        void mapNodes(Enc &e, const GameContext &gc) {
            if (!gc.map) return;
            const Map &m = *gc.map;
            const int cy = gc.curMapNodeY, cx = gc.curMapNodeX;
            const bool onMap = cy >= 0 && cy <= 14 && cx >= 0 && cx <= 6;
            // Ordinary-edge reachability (rows after the current one), and the Wing Boots jump set: with a charge
            // every later node that has an exit is a candidate (a jump can land on any next-row node with edges).
            bool reach[15][7] = {};
            if (cy < 0) {
                for (int x = 0; x < 7; ++x) reach[0][x] = m.getNode(x, 0).edgeCount > 0;
            } else if (onMap) {
                const MapNode &cur = m.getNode(cx, cy);
                for (int k = 0; k < cur.edgeCount; ++k)
                    if (cy + 1 <= 14 && cur.edges[k] >= 0 && cur.edges[k] < 7) reach[cy + 1][cur.edges[k]] = true;
            }
            for (int y = (cy < 0 ? 0 : cy + 1); y < 14; ++y)
                for (int x = 0; x < 7; ++x) {
                    if (!reach[y][x]) continue;
                    const MapNode &n = m.getNode(x, y);
                    for (int k = 0; k < n.edgeCount; ++k)
                        if (n.edges[k] >= 0 && n.edges[k] < 7) reach[y + 1][n.edges[k]] = true;
                }
            const bool jumps = gc.act >= 1 && gc.act <= 3 && gc.hasRelic(RelicId::WING_BOOTS)
                && gc.wingBootsCharges > 0 && gc.wingBootsCharges <= 3 && onMap;
            const auto token = [&](int x, int y, bool current) {
                const MapNode &n = m.getNode(x, y);
                AmberToken *t = e.push(T::MAP, &e.mapTok[y][x]);
                if (!t) return;
                if (n.room == Room::BOSS) t->ids[0] = bossId(gc.boss);   // act 4's boss node
                put(*t, 0, x / 6.0f);
                put(*t, 1, y / 15.0f);
                put(*t, 2, (y - cy) / 15.0f);
                const int room = static_cast<int>(n.room);
                if (room >= 0 && room <= static_cast<int>(Room::BOSS_TREASURE)) flag(*t, 3 + room, true);
                put(*t, 11, n.edgeCount / 3.0f);
                for (int k = 0; k < n.edgeCount; ++k) {
                    const int d = n.edges[k] - x;
                    if (y < 14 && d >= -1 && d <= 1) flag(*t, 13 + d, true);
                }
                put(*t, 15, n.parentCount / 6.0f);
                flag(*t, 16, m.burningEliteX == x && m.burningEliteY == y);
                flag(*t, 17, current);
                flag(*t, 19, reach[y][x]);
                if (!current && gc.screenState == ScreenState::MAP_SCREEN && y == cy + 1) {
                    const int cost = gc.mapMoveCost(x);
                    flag(*t, 20, cost >= 0);
                    flag(*t, 21, cost == 1);
                }
                flag(*t, 22, y == 14);
            };
            if (onMap) token(cx, cy, true);
            // The act boss after row 14 (acts 1-3; act 4's boss is an ordinary node).
            if (gc.act <= 3) {
                AmberToken *t = e.push(T::MAP, &e.bossTok);
                if (t) {
                    t->ids[0] = bossId(gc.boss);
                    put(*t, 0, 3 / 6.0f);
                    put(*t, 1, 1.0f);
                    put(*t, 2, (15 - cy) / 15.0f);
                    flag(*t, 3 + static_cast<int>(Room::BOSS), true);
                    flag(*t, 18, true);
                    flag(*t, 19, true);
                    if (gc.screenState == ScreenState::MAP_SCREEN && cy == 14) flag(*t, 20, gc.mapMoveCost(0) >= 0);
                }
            }
            for (int y = (cy < 0 ? 0 : cy + 1); y <= 14; ++y)
                for (int x = 0; x < 7; ++x) {
                    const MapNode &n = m.getNode(x, y);
                    if (n.room == Room::NONE) continue;
                    const bool jumpable = jumps && n.edgeCount > 0;
                    if (!reach[y][x] && !jumpable) continue;
                    token(x, y, false);
                }
        }

        // ---------------------------------------------------------------- actions

        void setSrc(AmberAction &a, T seg, std::uint8_t idx) {
            if (idx == kNone) return;
            a.srcSeg = static_cast<std::uint8_t>(seg);
            a.srcIdx = idx;
        }
        void setTgt(AmberAction &a, T seg, std::uint8_t idx) {
            if (idx == kNone) return;
            a.tgtSeg = static_cast<std::uint8_t>(seg);
            a.tgtIdx = idx;
        }

        void action(const Enc &e, const GameContext &gc, const GameAction &in, AmberAction &a) {
            using AT = AmberActionType;
            a = AmberAction{};
            const int i1 = in.getIdx1(), i2 = in.getIdx2();
            a.f[4] = amberHalf(i1 / 16.0f);
            a.f[5] = amberHalf(i2 / 8.0f);
            a.f[7] = amberHalf(static_cast<int>(gc.screenState) / 10.0f);
            const auto type = [&](AT t) { a.type = static_cast<std::uint8_t>(t); };
            const auto unknown = [&] { a = AmberAction{}; type(AT::UNKNOWN); };
            if (in.isPotionAction()) {
                if (i1 >= 5 || e.potTok[i1] == kNone) return unknown();
                type(in.isPotionDiscard() ? AT::DISCARD_POTION : AT::USE_POTION);
                setSrc(a, T::POTION, e.potTok[i1]);
                a.f[0] = amberHalf(i1 / 5.0f);
                a.f[6] = amberHalf(in.isPotionDiscard() ? 1.0f : 0.5f);
                return;
            }
            const auto &info = gc.info;
            switch (gc.screenState) {
                case ScreenState::EVENT_SCREEN: {
                    if (i1 >= 12 || e.eventTok[i1] == kNone) return unknown();
                    type(AT::CHOOSE_OPTION);
                    setSrc(a, T::OPTION, e.eventTok[i1]);
                    const auto deckRef = [&](int di) {
                        if (di >= 0 && di < gc.deck.size()) setTgt(a, T::CARD, e.deckTok[di]);
                    };
                    switch (gc.curEvent) {
                        case Event::FALLING:
                            if (i1 == 0) deckRef(info.skillCardDeckIdx);
                            else if (i1 == 1) deckRef(info.powerCardDeckIdx);
                            else if (i1 == 2) deckRef(info.attackCardDeckIdx);
                            break;
                        case Event::WE_MEET_AGAIN:
                            if (i1 == 0 && info.potionIdx >= 0 && info.potionIdx < 5)
                                setTgt(a, T::POTION, e.potTok[info.potionIdx]);
                            else if (i1 == 2) deckRef(info.cardIdx);
                            break;
                        case Event::NLOTH: {
                            const int ri = i1 == 0 ? info.relicIdx0 : i1 == 1 ? info.relicIdx1 : -1;
                            if (ri >= 0 && ri < kAmberCap[static_cast<int>(T::RELIC)] && ri < gc.relics.size())
                                setTgt(a, T::RELIC, e.relicTok[ri]);
                            break;
                        }
                        default: break;
                    }
                    return;
                }
                case ScreenState::REWARDS: {
                    const RT rt = in.getRewardsActionType();
                    a.f[6] = amberHalf(static_cast<int>(rt) / 8.0f);
                    std::uint8_t tok = kNone;
                    switch (rt) {
                        case RT::GOLD: tok = i1 < 2 ? e.goldTok[i1] : kNone; break;
                        case RT::CARD:
                            if (i2 == 5) {
                                tok = e.bowlTok;
                                break;
                            }
                            tok = i1 < 5 && i2 < 4 ? e.cardTok[i1][i2] : kNone;
                            if (tok == kNone) return unknown();
                            type(AT::CHOOSE_CARD);
                            setSrc(a, T::CARD, tok);
                            return;
                        case RT::RELIC: tok = i1 < 3 ? e.rRelicTok[i1] : kNone; break;
                        case RT::POTION: tok = i1 < 5 ? e.rPotTok[i1] : kNone; break;
                        case RT::KEY: tok = e.keyTok; break;
                        case RT::SKIP: type(AT::SKIP_OR_LEAVE); return;
                        default: return unknown();
                    }
                    if (tok == kNone) return unknown();
                    type(AT::CHOOSE_OPTION);
                    setSrc(a, T::OPTION, tok);
                    return;
                }
                case ScreenState::SHOP_ROOM: {
                    const RT rt = in.getRewardsActionType();
                    a.f[6] = amberHalf(static_cast<int>(rt) / 8.0f);
                    std::uint8_t tok = kNone;
                    switch (rt) {
                        case RT::CARD: tok = i1 < 7 ? e.shopCardTok[i1] : kNone; break;
                        case RT::RELIC: tok = i1 < 3 ? e.shopRelicTok[i1] : kNone; break;
                        case RT::POTION: tok = i1 < 3 ? e.shopPotTok[i1] : kNone; break;
                        case RT::CARD_REMOVE: tok = e.removeTok; break;
                        case RT::SKIP: type(AT::SKIP_OR_LEAVE); return;
                        default: return unknown();
                    }
                    if (tok == kNone) return unknown();
                    type(AT::CHOOSE_OPTION);
                    setSrc(a, T::OPTION, tok);
                    return;
                }
                case ScreenState::BOSS_RELIC_REWARDS:
                    if (i1 == 3) { type(AT::SKIP_OR_LEAVE); return; }
                    if (i1 > 3 || e.bossRelicTok[i1] == kNone) return unknown();
                    type(AT::CHOOSE_OPTION);
                    setSrc(a, T::OPTION, e.bossRelicTok[i1]);
                    return;
                case ScreenState::CARD_SELECT: {
                    if (i1 >= static_cast<int>(info.toSelectCards.size())) return unknown();
                    const int di = selectDeckIdx(gc, info.toSelectCards[i1]);
                    const std::uint8_t tok = di >= 0 ? e.deckTok[di] : e.selectTok[i1];
                    if (tok == kNone) return unknown();
                    type(AT::CHOOSE_CARD);
                    setSrc(a, T::CARD, tok);
                    return;
                }
                case ScreenState::MAP_SCREEN: {
                    const int cost = gc.mapMoveCost(i1);
                    if (cost < 0) return unknown();
                    const int cy = gc.curMapNodeY;
                    const std::uint8_t tok = cy == 14 ? e.bossTok : cy + 1 <= 14 ? e.mapTok[cy + 1][i1] : kNone;
                    if (tok == kNone) return unknown();
                    type(AT::MAP_MOVE);
                    setTgt(a, T::MAP, tok);
                    a.f[0] = amberHalf(i1 / 6.0f);
                    a.f[1] = cost == 1 ? kOne : 0;
                    return;
                }
                case ScreenState::TREASURE_ROOM:
                    if (i1 == 1) { type(AT::SKIP_OR_LEAVE); return; }
                    if (i1 != 0 || e.chestTok == kNone) return unknown();
                    type(AT::CHOOSE_OPTION);
                    setSrc(a, T::OPTION, e.chestTok);
                    return;
                case ScreenState::REST_ROOM:
                    if (i1 == 6) { type(AT::SKIP_OR_LEAVE); return; }
                    if (i1 > 6 || e.restTok[i1] == kNone) return unknown();
                    type(AT::CHOOSE_OPTION);
                    setSrc(a, T::OPTION, e.restTok[i1]);
                    return;
                default:
                    return unknown();
            }
        }

    }  // namespace

    void amberEncodeGame(const GameContext &gc, const std::vector<GameAction> &actions, AmberTokens &out) {
        out.clear();
        Enc e(out);
        run(e, gc);
        player(e, gc);
        deck(e, gc);
        relics(e, gc);
        potions(e, gc);
        options(e, gc);
        mapNodes(e, gc);
        const int n = static_cast<int>(actions.size());
        const int keep = n < kAmberMaxActions ? n : kAmberMaxActions;
        for (int i = 0; i < keep; ++i) action(e, gc, actions[i], out.act[i]);
        out.nAct = keep;
        out.cut += n - keep;
    }

    namespace {

        constexpr int kEncounterCount = static_cast<int>(MonsterEncounter::MYSTERIOUS_SPHERE_EVENT) + 1;
        static_assert(kAmberEncounterKindBase == 1018, "tools/az_bench/amber_net.py ENC_KIND_BASE reads these ids");

        struct EncounterInfo {
            std::int16_t ids[3] = {0, 0, 0};
            float hp = 0, count = 0;
        };
        using EncounterTable = std::array<std::array<EncounterInfo, kEncounterCount>, 21>;

        // Per ascension and encounter: its monsters over 8 sampled compositions (miscRng / monsterHpRng seeds 1..8).
        std::unique_ptr<EncounterTable> buildEncounterTable() {
            auto table = std::make_unique<EncounterTable>();
            auto bc = std::make_unique<BattleContext>();
            constexpr int kSamples = 8;
            for (int asc = 0; asc <= 20; ++asc) {
                for (int e = 1; e < kEncounterCount; ++e) {
                    EncounterInfo &in = (*table)[asc][e];
                    int nIds = 0;
                    for (int s = 0; s < kSamples; ++s) {
                        *bc = BattleContext{};
                        bc->ascension = asc;
                        bc->miscRng = Random(static_cast<std::uint64_t>(s + 1));
                        bc->monsterHpRng = Random(static_cast<std::uint64_t>(s + 101));
                        bc->monsters.createMonsters(*bc, static_cast<MonsterEncounter>(e));
                        for (int i = 0; i < bc->monsters.monsterCount; ++i) {
                            const Monster &m = bc->monsters.arr[i];
                            if (m.id == MonsterId::INVALID) continue;
                            in.hp += static_cast<float>(m.maxHp);
                            in.count += 1;
                            const auto id = static_cast<std::int16_t>(kAmberMonsterBase + static_cast<int>(m.id) - 1);
                            bool seen = false;
                            for (int k = 0; k < nIds; ++k) seen = seen || in.ids[k] == id;
                            if (!seen && nIds < 3) in.ids[nIds++] = id;
                        }
                    }
                    in.hp /= kSamples;
                    in.count /= kSamples;
                }
            }
            return table;
        }

        const EncounterInfo &encounterInfo(MonsterEncounter enc, int ascension) {
            static const std::unique_ptr<EncounterTable> table = buildEncounterTable();   // thread-safe init
            const int a = ascension < 0 ? 0 : (ascension > 20 ? 20 : ascension);
            const int e = static_cast<int>(enc);
            return (*table)[a][e > 0 && e < kEncounterCount ? e : 0];
        }

        void encounterToken(AmberTokens &out, const GameContext &gc, MonsterEncounter enc, int kind, float weight) {
            if (enc == MonsterEncounter::INVALID) return;
            const int si = static_cast<int>(AmberTokenType::MONSTER);
            if (out.n[si] >= kAmberCap[si]) {
                ++out.cut;
                return;
            }
            AmberToken &t = out.tok[kAmberOff[si] + out.n[si]++];
            std::memset(&t, 0, sizeof(t));
            const EncounterInfo &in = encounterInfo(enc, gc.ascension);
            for (int k = 0; k < 3; ++k) t.ids[k] = in.ids[k];
            t.ids[3] = static_cast<std::int16_t>(kAmberEncounterKindBase + kind);
            t.f[0] = amberHalf(in.hp / 100.0f);
            t.f[1] = amberHalf(in.count / 5.0f);
            t.f[2] = amberHalf(weight);
        }

    }  // namespace

    void amberAppendEncounterTokens(const GameContext &gc, AmberTokens &out) {
        encounterToken(out, gc, gc.boss, 0, 1.0f);
        if (gc.act >= 4) {
            encounterToken(out, gc, MonsterEncounter::SHIELD_AND_SPEAR, 1, 1.0f);
            return;
        }
        if (gc.act < 1) return;
        const int a = gc.act - 1;
        for (int k = 0; k < 3; ++k) encounterToken(out, gc, MonsterEncounterPool::elites[a][k], 1, 1.0f / 3.0f);
        for (int k = 0; k < MonsterEncounterPool::strongCount[a]; ++k)
            encounterToken(out, gc, MonsterEncounterPool::strongEnemies[a][k], 2, MonsterEncounterPool::strongWeights[a][k]);
    }

}
