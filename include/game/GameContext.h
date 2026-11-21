//
// Created by gamerpuppy on 6/24/2021.
//

#ifndef STS_LIGHTSPEED_GAMECONTEXT_H
#define STS_LIGHTSPEED_GAMECONTEXT_H

#include <vector>
#include <array>
#include <functional>
#include <memory>

#include "data_structure/fixed_list.h"

#include "constants/Misc.h"
#include "constants/CardPools.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "constants/Events.h"
#include "constants/MonsterEncounters.h"
#include "constants/CharacterClasses.h"

#include "game/Random.h"
#include "game/Map.h"
#include "game/Neow.h"
#include "game/RelicContainer.h"
#include "game/Card.h"
#include "game/Rewards.h"
#include "game/Deck.h"
#include "game/Shop.h"

namespace sts {

    enum class GameOutcome {
        PLAYER_LOSS,
        UNDECIDED,
        PLAYER_VICTORY,
    };

    enum RngReference {
        MISC_RNG,
        CARD_RNG,
        NEOW_RNG,
    };

    enum class CardSelectScreenType {
        INVALID=0,
        TRANSFORM,
        TRANSFORM_UPGRADE,
        UPGRADE,
        REMOVE,
        DUPLICATE,
        OBTAIN,
        BOTTLE,
        BONFIRE_SPIRITS,
    };

    enum class ScreenState {
        INVALID=0,
        EVENT_SCREEN,
        REWARDS,
        BOSS_RELIC_REWARDS,
        CARD_SELECT,
        MAP_SCREEN,
        TREASURE_ROOM,
        REST_ROOM,
        SHOP_ROOM,
        BATTLE,
    };

    struct SelectScreenCard {
        Card card;
        std::int16_t deckIdx = -1;

        SelectScreenCard() = default;
        SelectScreenCard(const Card &card);
        SelectScreenCard(const Card &card, int deckIdx);
    };

    struct ScreenStateInfo {
        // This object is copied into every counterfactual branch.  Give every
        // inactive-screen field a deterministic sentinel/value: leaving POD
        // members uninitialized made an otherwise identical run depend on stack
        // reuse after a prior run.
        MonsterEncounter encounter = MonsterEncounter::INVALID;

        // CardSelectScreen
        RngReference transformRng = CARD_RNG;
        CardSelectScreenType selectScreenType = CardSelectScreenType::INVALID;
        int toSelectCount = 0;
        fixed_list<SelectScreenCard, Deck::MAX_SIZE> toSelectCards;
        fixed_list<SelectScreenCard,3> haveSelectedCards;

        // Events
        int eventData = 0;

        int hpAmount0 = 0;
        int hpAmount1 = 0;
        int hpAmount2 = 0;

        // Dead Adventurer
        int phase = 0;
        std::array<int,3> rewards{};

        // Designer In-Spire
        bool upgradeOne = false;
        bool cleanUpIsRemoveCard = false;

        // Treasure Room
        bool haveGold = false;
        ChestSize chestSize = ChestSize::INVALID;
        RelicTier tier = RelicTier::INVALID;

        // World of Goop
        int goldLoss = 0;

        // We Meet Again Event
        int potionIdx = -1;
        int gold = 0;
        int cardIdx = -1;

        // N'loth
        int relicIdx0 = -1;
        int relicIdx1 = -1;

        // Falling
        int skillCardDeckIdx = -1;
        int powerCardDeckIdx = -1;
        int attackCardDeckIdx = -1;

        // Boss Room
        RelicId bossRelics[3] {RelicId::INVALID, RelicId::INVALID, RelicId::INVALID};

        NeowOptions neowRewards;
        Rewards rewardsContainer;

        // from combats
        int stolenGold = 0;

        // Shop Room
        Shop shop;
    };


    class GameContext;

    // STS_ENGINE_FIDELITY_FIX: unset or 1 = out-of-combat and burning-elite
    // rules follow the game (2026-10-17 engine A20 fidelity audit); 0 = the
    // legacy simulator rules. Other values are fatal. Read per call.
    bool engineFidelityFix();
    // STS_DU_VU_DOLL_COUNT_FIX: unset or 1 = Du-Vu Doll data is the number of
    // CURSE-type master-deck cards, refreshed on every deck change as Java's
    // onEquip/onMasterDeckChange do; 0 = the legacy data 0 (no Strength).
    // Other values are fatal. Read per call.
    bool duVuDollCountFix();
    typedef std::function<void(GameContext&)> GameContextAction;

    class BattleContext;
    class SaveFile;

    struct GameContext {
        static constexpr float SHRINE_CHANCE = 0.25F;

        sts::Card noteForYourselfCard = Card(CardId::IRON_WAVE);

        static constexpr bool disableColosseum = false;
        static constexpr bool disableMatchAndKeep = false;
        static constexpr bool disablePrismaticShard = true;
        bool skipBattles = false;

        // ********* hidden from player *********
        std::uint64_t seed;

        Random aiRng;
        Random cardRandomRng;
        Random cardRng;
        Random eventRng;
        Random mathUtilRng;
        Random merchantRng;
        Random miscRng;
        Random monsterHpRng;
        Random monsterRng;
        Random neowRng;
        Random potionRng;
        Random relicRng;
        Random shuffleRng;
        Random treasureRng;

        // todo change these to fixed lists
        std::vector<Event> eventList;
        std::vector<Event> shrineList;
        std::vector<Event> specialOneTimeEventList;

        std::vector<RelicId> commonRelicPool;
        std::vector<RelicId> uncommonRelicPool;
        std::vector<RelicId> rareRelicPool;
        std::vector<RelicId> shopRelicPool;
        std::vector<RelicId> bossRelicPool;

        std::array<CardId, 35> colorlessCardPool = baseColorlessPool;

        int monsterListOffset = 0;
        fixed_list<MonsterEncounter, 16> monsterList;
        int eliteMonsterListOffset = 0;
        fixed_list<MonsterEncounter, 10> eliteMonsterList;
        MonsterEncounter secondBoss = MonsterEncounter::INVALID;

        // ********* player information *********

        GameOutcome outcome = GameOutcome::UNDECIDED;
        ScreenState screenState = ScreenState::INVALID;
        ScreenStateInfo info;

        Room lastRoom = Room::INVALID;
        Event curEvent = Event::INVALID;
        Room curRoom = Room::INVALID;
        MonsterEncounter boss = MonsterEncounter::INVALID;

        float monsterChance = 0.1f;
        float shopChance = 0.03f;
        float treasureChance = 0.02f;
        int potionChance = 0;
        int cardRarityFactor = 5;
        int wingBootsCharges = 0;
        int shopRemoveCount = 0;
        bool speedrunPace = false; // todo load from save

        int curMapNodeX = -1;
        int curMapNodeY = -1;
        std::shared_ptr<Map> map = nullptr; // todo fix memory leak

        int act = 1;
        int ascension = 0;
        int floorNum = 0;

        CharacterClass cc;
        int curHp = 80;
        int maxHp = 80;
        int gold = 99;

        int potionCount = 0;
        int potionCapacity = 0;
        std::array<Potion, 5> potions {Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                                       Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                                       Potion::EMPTY_POTION_SLOT};

        RelicContainer relics;
        Deck deck;

        bool blueKey = false;
        bool greenKey = false;
        // Whether the act exposes the Ruby-key campfire option.  The native
        // simulator keeps this enabled for ordinary generated runs; the live
        // importer sets it from Java's public final-act setting.
        bool keysEnabled = true;
        // Live OOC imports set this when Java has already resolved the
        // campfire and exposes only the proceed button. Ordinary simulator
        // rooms leave it false while the rest action is selectable.
        bool restRoomResolved = false;
        bool redKey = false;

        GameContextAction regainControlAction = nullptr;
        bool smokeBombUsed = false;

        GameContext() = default;
        GameContext(CharacterClass cc, std::uint64_t seed, int ascensionLevel, bool rngFix = false);

        // RNG Fix mod (Steam workshop 2181005326, source github.com/Nickel-makes/RngFix at 88b5885, the mod the
        // Amber Eye page names for training and evaluation), off by default. The vanilla game seeds every stream
        // with the run seed, so their outputs are correlated. With rngFix each stream gets its own seed, raw
        // output k of Random(seed) (Random::derivedSeed):
        //   k = 0 monsterRng, 1 eventRng, 2 merchantRng, 3 cardRng, 4 treasureRng, 5 relicRng, 6 potionRng
        //       (seeded once at the start of the run),
        //   k = 7 monsterHpRng, 8 aiRng, 9 shuffleRng, 10 cardRandomRng, 11 miscRng
        //       (reseeded on every floor with derivedSeed(seed, k) + floorNum instead of seed + floorNum),
        //   k = 13 Neow's generator, k = 14 the generator that picks the event of an event room (advanced to
        //       eventRng's counter; the vanilla game uses a copy of eventRng there).
        // The map generator is not changed by the mod. Set by the constructor only; copies keep it.
        bool rngFix = false;
        enum FloorStream { FLOOR_MONSTER_HP = 7, FLOOR_AI = 8, FLOOR_SHUFFLE = 9, FLOOR_CARD_RANDOM = 10, FLOOR_MISC = 11 };
        // The state a per-floor stream is reset to on the current floor.
        [[nodiscard]] Random floorRng(FloorStream stream) const {
            return Random((rngFix ? Random::derivedSeed(seed, stream) : seed) + static_cast<std::uint64_t>(floorNum));
        }
        // A new floor: reset the per-floor streams the out-of-combat game holds (a combat sets its own in
        // BattleContext::init).
        void reseedFloorRngs() {
            miscRng = floorRng(FLOOR_MISC);
            shuffleRng = floorRng(FLOOR_SHUFFLE);
            cardRandomRng = floorRng(FLOOR_CARD_RANDOM);
        }

        void initFromSave(const SaveFile &s);
        void initRelicsFromSave(const SaveFile &s);

        // const methods
        [[nodiscard]] const MapNode& getCurMapNode() const;
        [[nodiscard]] int fractionMaxHp(float percent, HpType type=HpType::FLOOR) const;
        [[nodiscard]] bool hasRelic(RelicId r) const;
        // Java eliteTrigger: elite rooms plus the Dead Adventurer fight and
        // Colosseum's Nob fight, which trigger elite relic effects.
        [[nodiscard]] bool isEliteTriggerCombat() const;
        [[nodiscard]] bool hasKey(Key key) const;

        [[nodiscard]] bool hasLessThanTwoCampfireRelics() const;
        [[nodiscard]] bool relicCanSpawn(RelicId relic, bool shopRoom) const;

        [[nodiscard]] bool canAddOneTimeEvent(Event shrine) const;
        [[nodiscard]] bool canAddEvent(Event event) const;

        // initialization
        void initRelics();
        void initPlayer();
        void generateMonsters();
        void generateWeakMonsters();
        void generateStrongMonsters();
        void generateElites();
        void generateBoss();
        void populateMonsterList(const MonsterEncounter monsters[], const float weights[], int monstersSize, int numMonsters);
        void populateFirstStrongEnemy(const MonsterEncounter monsters[], const float weights[], int monstersSize);

        // room setup
        void transitionToAct(int act);
        // -1 invalid, 0 ordinary edge, 1 charged Wing Boots jump.
        int mapMoveCost(int mapNodeX) const;
        void transitionToMapNode(int mapNodeX);
        void setupEvent();
        void setupTreasureRoom();
        void enterBossTreasureRoom();
        void enterAct3VictoryRoom();
        void enterBattle(MonsterEncounter encounter);
        void afterBattle();
        // Post-combat relic effects that Java runs on every combat end
        // (Face of Cleric). afterBattle() calls it; event fight
        // continuations that replace afterBattle() must call it too.
        void relicsOnCombatEnd();

        // actions
        void obtainCard(Card c, int count=1);
        int masterDeckCurseCount() const;
        void syncDuVuDollCounter();
        void obtainGold(int amount);
        void obtainKey(Key key);
        void obtainPotion(Potion p);
        bool obtainRelic(RelicId r);

        RelicId returnRandomRelic(RelicTier tier, bool shopRoom=false, bool fromFront=true);
        RelicId returnNonCampfireRelic(RelicTier tier, bool shopRoom=false);
        void rollEscapedCombatRewardRng();
        RelicId returnRandomScreenlessRelic(RelicTier tier, bool shopRoom=false);

        Card previewObtainCard(Card card);
        void relicsOnEnterRoom(Room room);

        CardRarity rollCardRarity(Room room);
        CardId returnTrulyRandomCardFromAvailable(Random &rng, CardId exclude);

        Card getTransformedCard(Random &rng, CardId exclude, bool autoUpgrade= false);

        CardId returnColorlessCard(CardRarity rarity);
        int getRandomPlayerPotionIdx();
        int getRandomPlayerNonBasicCardIdx();

        MonsterEncounter getMonsterForRoomCreation();
        MonsterEncounter getEliteForRoomCreation();

        void addPotionRewards(Rewards &r);
        CardReward createCardReward(Room room);
        CardReward createColorlessCardReward();

        Rewards createCombatReward();
        Rewards createEliteCombatReward();
        Rewards createBossCombatReward();

        Event getShrine(Random &eventRngCopy);
        Event getEvent(Random &eventRngCopy);
        Event generateEvent(Random eventRngCopy);
        // Vanilla ordinary-run EventHelper table, before Tiny Chest/Juzu effects.
        static Room questionRoomOutcomeForCell(int cell, float monster, float shop,
                                              float treasure, bool previousRoomWasShop);
        Room getEventRoomOutcomeHelper(bool lastRoomWasShop);

        // actions
        void damagePlayer(int amount, bool playerOwned = false);
        void playerLoseHp(int amount);
        void playerOnDie();
        void playerHeal(int amount);
        void playerIncreaseMaxHp(int amount);
        void loseGold(int amount, bool inShop=false);
        void loseMaxHp(int amount);


        void drinkPotion(Potion p);
        void drinkPotionAtIdx(int idx);
        void discardPotionAtIdx(int idx);


        void openTreasureRoomChest();
        void selectScreenTransform();
        void openCombatRewardScreen(Rewards reward);
        void openCardSelectScreen(CardSelectScreenType type, int selectCount, bool initSelectCards=true);

        // interface methods
        void chooseNeowOption(const Neow::Option &gc);
        void chooseBossRelic(int idx);
        void chooseEventOption(int idx);
        void chooseSelectCardScreenOption(int idx);
        void chooseCampfireOption(int idx);
        // Match and Keep slot state lives in info.toSelectCards[i].deckIdx:
        // -1 unseen, 1 seen face down, 2 face up this attempt, 0 matched.
        static constexpr int MATCH_AND_KEEP_UNSEEN = -1;
        static constexpr int MATCH_AND_KEEP_MATCHED = 0;
        static constexpr int MATCH_AND_KEEP_SEEN = 1;
        static constexpr int MATCH_AND_KEEP_FACE_UP = 2;
        void chooseMatchAndKeepSlot(int idx); // one click
        void chooseMatchAndKeepCards(int idx1, int idx2); // both clicks of one attempt
        void chooseTreasureRoomOption(bool openChest);

        void regainControl();
    };


}



#endif //STS_LIGHTSPEED_GAMECONTEXT_H
