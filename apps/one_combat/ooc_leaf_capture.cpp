#include "ooc_leaf_capture.h"
#include "run_features.h"
#include "screen_leaf_s0.h"

#include <stdexcept>

namespace one_combat {

nlohmann::json oocLeafCandidateInput(const sts::GameContext &gc, const PathHistory &path) {
    using Json = nlohmann::json;
    if (gc.potionCapacity < 0 || gc.potionCapacity > int(gc.potions.size()))
        throw std::runtime_error("leaf candidate: invalid potion capacity");
    if (gc.map && gc.curMapNodeY >= 0 && gc.curMapNodeY < 15
        && (gc.curMapNodeX < 0 || gc.curMapNodeX >= 7))
        throw std::runtime_error("leaf candidate: invalid map position");
    const auto fm = forwardMapFeatures(gc);
    Json row = {
        {"schema", "candidate-public-leaf-v1"}, {"publicParityQualified", false},
        {"omitted", {"seed", "rng", "hiddenFutureQueues", "secondBoss", "pityCounters",
                     "relicCounters", "privatePools", "continuationCallbacks"}},
        {"character", int(gc.cc)}, {"ascension", gc.ascension}, {"act", gc.act},
        {"floor", gc.floorNum}, {"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"gold", gc.gold},
        {"keys", {{"enabled", gc.keysEnabled}, {"blue", gc.blueKey},
                  {"green", gc.greenKey}, {"red", gc.redKey}}},
        {"potionCapacity", gc.potionCapacity}, {"potions", Json::array()},
        {"deck", Json::array()}, {"relicIds", Json::array()}, {"boss", int(gc.boss)},
        {"room", int(gc.curRoom)}, {"screenState", int(gc.screenState)},
        {"mapPosition", {gc.curMapNodeX, gc.curMapNodeY}}, {"mapPresent", bool(gc.map)},
        {"roomVisits", path.roomVisits},
        {"forwardMap", {{"dElite", fm.dElite}, {"dRest", fm.dRest}, {"dShop", fm.dShop},
                        {"dBoss", fm.dBoss}, {"cElite", fm.cElite}, {"cRest", fm.cRest},
                        {"cShop", fm.cShop}, {"cEvent", fm.cEvent},
                        {"cMonster", fm.cMonster}, {"cTreasure", fm.cTreasure}}}
    };
    for (int slot = 0; slot < gc.potionCapacity; ++slot)
        row["potions"].push_back({{"slot", slot}, {"id", int(gc.potions[slot])}});
    for (int i = 0; i < gc.deck.size(); ++i) {
        const auto &card = gc.deck.cards[i];
        row["deck"].push_back({{"id", int(card.id)}, {"upgraded", card.isUpgraded()},
                               {"misc", card.misc}, {"bottled", gc.deck.isCardBottled(i)}});
    }
    for (const auto &relic : gc.relics.relics) row["relicIds"].push_back(int(relic.id));
    if (gc.outcome != sts::GameOutcome::UNDECIDED) {
        // This is the present leaf's terminal identity, never a downstream label.
        row["boundary"] = {{"kind", "terminal"}, {"outcome", int(gc.outcome)}};
    } else if (gc.screenState == sts::ScreenState::BATTLE) {
        row["boundary"] = {{"kind", "battle"}, {"encounter", int(gc.info.encounter)}};
    } else {
        if (gc.screenState == sts::ScreenState::MAP_SCREEN && !gc.map)
            throw std::runtime_error("leaf candidate: map screen without visible map");
        row["boundary"] = {{"kind", "decision"}, {"publicScreen", screenLeafPublicContract(gc)}};
    }
    return row;
}

int oocLeafCandidateInputSelfTest() {
    using namespace sts;
    const auto check = [](bool ok, const char *why) {
        if (!ok) throw std::runtime_error(std::string("leaf candidate selftest: ") + why);
    };
    // Directly constructed fixture: no generated run, seed drive, or model load.
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.screenState = ScreenState::REWARDS;
    gc.ascension = 20;
    gc.boss = MonsterEncounter::HEXAGHOST;
    gc.potionCapacity = 2;
    gc.potionCount = 1;
    gc.potions[0] = Potion::FIRE_POTION;
    gc.deck.obtainRaw(Card(CardId::BASH));
    gc.deck.bottleIdxs[0] = 0;
    gc.relics.add({RelicId::NUNCHAKU, 0});
    gc.info.rewardsContainer.cardRewardCount = 1;
    gc.info.rewardsContainer.cardRewards[0].push_back(Card(CardId::ANGER));
    PathHistory path;
    const auto expected = oocLeafCandidateInput(gc, path);
    check(expected.dump() == oocLeafCandidateInput(gc, path).dump(), "nondeterministic JSON");
    auto hidden = gc;
    hidden.seed = 987654321;
    hidden.cardRng.seed0 = 111;
    hidden.cardRng.counter = 57;
    hidden.monsterList.push_back(MonsterEncounter::CULTIST);
    hidden.eliteMonsterList.push_back(MonsterEncounter::GREMLIN_NOB);
    hidden.monsterListOffset = 4;
    hidden.eliteMonsterListOffset = 3;
    hidden.secondBoss = MonsterEncounter::THE_GUARDIAN;
    hidden.potionChance = -40;
    hidden.cardRarityFactor = -20;
    hidden.monsterChance = 0.9f;
    hidden.relics.relics[0].data = 9;
    hidden.info.encounter = MonsterEncounter::JAW_WORM;
    hidden.commonRelicPool.push_back(RelicId::ANCHOR);
    auto hiddenPath = path;
    hiddenPath.lastNodeKey = 777;
    check(expected == oocLeafCandidateInput(hidden, hiddenPath), "private realization changed input");
    const auto differs = [&](const GameContext &other) {
        check(expected != oocLeafCandidateInput(other, path), "visible change missing");
    };
    auto visible = gc; --visible.curHp; differs(visible);
    visible = gc; visible.deck.cards[0].misc = 12; differs(visible);
    visible = gc; visible.deck.bottleIdxs[0] = -1; differs(visible);
    visible = gc; visible.potions[1] = visible.potions[0];
    visible.potions[0] = Potion::EMPTY_POTION_SLOT; differs(visible);
    visible = gc; visible.info.rewardsContainer.cardRewards[0][0] = Card(CardId::FLEX); differs(visible);
    auto publicPath = path; ++publicPath.roomVisits[0];
    check(expected != oocLeafCandidateInput(gc, publicPath), "public history missing");
    gc.screenState = ScreenState::BATTLE;
    gc.info.encounter = MonsterEncounter::CULTIST;
    const auto battle = oocLeafCandidateInput(gc, path);
    check(battle.at("boundary").at("encounter") == int(MonsterEncounter::CULTIST), "battle identity");
    gc.info.encounter = MonsterEncounter::JAW_WORM;
    check(battle != oocLeafCandidateInput(gc, path), "visible encounter missing");
    gc.outcome = GameOutcome::PLAYER_LOSS;
    check(oocLeafCandidateInput(gc, path).at("boundary").at("kind") == "terminal", "terminal identity");
    gc.outcome = GameOutcome::UNDECIDED;
    gc.screenState = ScreenState::INVALID;
    bool rejected = false;
    try { (void)oocLeafCandidateInput(gc, path); } catch (const std::runtime_error &) { rejected = true; }
    check(rejected, "unsupported screen accepted");
    return 0;
}

} // namespace one_combat
