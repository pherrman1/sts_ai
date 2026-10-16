#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <nlohmann/json.hpp>

#include "ooc_test_state.h"
#include "game/SaveFile.h"
#include "ooc_strategic_tok_net.h"
#include "one_combat/live_ooc_policy.h"
#include "one_combat/ooc_checkpoint_policy.h"
#include "one_combat/ooc_mcts_adapter.h"
#include "one_combat/ooc_v4_encoding.h"
#include "one_combat/heart1_policy.h"
#include "sim/search/OocSemanticAction.h"

namespace {
void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}
}

int main(int argc, char **argv) {
    try {
        using namespace sts;
        using namespace sts::search;
        using namespace one_combat;
        // One fixed native fixture seed, no campaign traversal.
        GameContext gc(CharacterClass::IRONCLAD, 0x51514Du, 0);
        {
            // Native shop actions retain physical slots after purchases. A
            // compacted card vector silently shifts tokens or throws at slot 6.
            const CardId ids[] = {CardId::BASH, CardId::STRIKE_RED, CardId::DEFEND_RED,
                CardId::ANGER, CardId::CLEAVE, CardId::IRON_WAVE, CardId::POMMEL_STRIKE};
            for (const int ascension : {0, 20}) for (unsigned sold = 0; sold < 128; ++sold) {
                auto shop = gc;
                shop.ascension = ascension;
                shop.screenState = ScreenState::SHOP_ROOM;
                shop.curRoom = Room::SHOP;
                shop.gold = 999;
                shop.info.shop = Shop{};
                std::fill(std::begin(shop.info.shop.prices), std::end(shop.info.shop.prices), -1);
                unsigned remaining = 0;
                for (int slot = 0; slot < 7; ++slot) if (!(sold & (1u << slot))) {
                    ++remaining;
                    shop.info.shop.cards[slot] = Card(ids[slot], slot % 2);
                    shop.info.shop.cardPrice(slot) = 50;
                }
                heart1::Choice choice;
                require(heart1::buildChoice(shop, choice), "Arm C partial shop was unencoded");
                require(choice.record.offeredCards.size() == remaining, "Arm C shop dropped a legal card token");
                for (std::size_t i = 0; i < choice.record.offeredCards.size(); ++i) {
                    const auto slot = choice.actions[i].getIdx1();
                    require(!(sold & (1u << slot)) && choice.record.offeredCards[i] == int(ids[slot])
                            && choice.record.offeredUpgrades[i] == slot % 2,
                            "Arm C shop token lost its physical native card slot");
                }
            }
        }
        {
            // Source-qualified EventHelper interval table; all cells, including
            // saturation and zero-width overwritten last-cell behavior.
            struct Case { float monster, shop, treasure; bool previousShop; int monsterEnd,shopEnd,treasureEnd; };
            const Case cases[] = {
                {.1f,.03f,.02f,false,10,13,15}, {.1f,.03f,.02f,true,10,10,12},
                {.99f,.03f,.02f,false,99,99,100}, {1.f,0.f,0.f,false,99,99,100},
                {1.2f,.3f,.2f,true,99,99,100}, {.8f,.3f,.02f,false,80,99,100},
                {0.f,0.f,0.f,false,0,0,0}
            };
            for (const auto &c:cases) for(int cell=0;cell<100;++cell) {
                const Room expected=cell<c.monsterEnd?Room::MONSTER:cell<c.shopEnd?Room::SHOP:
                    cell<c.treasureEnd?Room::TREASURE:Room::EVENT;
                require(GameContext::questionRoomOutcomeForCell(cell,c.monster,c.shop,c.treasure,c.previousShop)==expected,
                        "question-room table differs from vanilla clipped intervals");
            }
            auto roll=gc;roll.monsterChance=1.f;roll.shopChance=0.f;roll.treasureChance=0.f;
            auto rng=roll.eventRng;const int cell=static_cast<int>(rng.random()*100.f);
            const auto expected=cell==99?Room::TREASURE:Room::MONSTER;
            require(roll.getEventRoomOutcomeHelper(false)==expected && roll.eventRng==rng,
                    "question-room transition changed draw count or table selection");
            auto forced=gc;forced.relics.add({RelicId::TINY_CHEST,3});
            rng=forced.eventRng;(void)rng.random();
            require(forced.getEventRoomOutcomeHelper(false)==Room::TREASURE && forced.eventRng==rng
                    && forced.relics.getRelicValue(RelicId::TINY_CHEST)==0 && forced.treasureChance==.02f,
                    "Tiny Chest forcing skipped draw or failed counter reset");
        }
        {
            auto route = gc;
            route.map = std::make_shared<Map>();
            for (int y=0;y<15;++y) for(int x=0;x<7;++x) {
                auto &node=route.map->nodes[y][x];node.x=x;node.y=y;node.room=Room::REST;
            }
            route.curMapNodeX=1;route.curMapNodeY=0;route.screenState=ScreenState::MAP_SCREEN;
            route.map->getNode(1,0).addEdge(2);
            route.map->getNode(2,1).addEdge(2);
            route.map->getNode(5,1).addEdge(2);
            route.map->getNode(2,2).addEdge(2);
            route.map->getNode(5,2).addEdge(2);
            for(int charges=0;charges<=3;++charges) {
                auto state=route;state.relics.add({RelicId::WING_BOOTS,0});state.wingBootsCharges=charges;
                const auto actions=GameAction::getAllActionsInState(state);
                require(actions.size()==(charges ? 2u : 1u) && actions[0].getIdx1()==2,
                        "Wing Boots changed ordinary order or candidate set");
                require(state.mapMoveCost(2)==0 && state.mapMoveCost(5)==(charges?1:-1)
                        && state.mapMoveCost(4)==-1 && state.mapMoveCost(7)==-1,
                        "Wing Boots reachability/cost mismatch");
                auto ordinary=state;GameAction(2).execute(ordinary);
                require(ordinary.wingBootsCharges==charges,"ordinary edge spent charge");
                if(charges) {
                    auto jump=state;GameAction(5).execute(jump);
                    require(jump.wingBootsCharges==charges-1 && state.wingBootsCharges==charges
                            && jump.curMapNodeX==5 && jump.curMapNodeY==1 && jump.screenState==ScreenState::REST_ROOM,
                            "jump failed to spend exactly once or mutated source copy");
                    require(jump.eventRng.counter==ordinary.eventRng.counter
                            && jump.miscRng.counter==ordinary.miscRng.counter
                            && jump.relicRng.counter==ordinary.relicRng.counter,
                            "jump eligibility spent RNG");
                    require(jump.mapMoveCost(5)==(charges>1?1:-1),"final charge did not exhaust");
                }
            }
            route.wingBootsCharges=3;
            require(route.mapMoveCost(5)==-1,"stale charge allowed unowned relic jump");
            route.obtainRelic(RelicId::WING_BOOTS);
            require(route.wingBootsCharges==3 && route.relics.getRelicValue(RelicId::WING_BOOTS)==0,
                    "native Wing Boots acquisition or frozen feature changed");
            route.relics.remove(RelicId::WING_BOOTS);
            require(route.mapMoveCost(5)==-1,"removed Wing Boots retained usable charges");
            route.wingBootsCharges=0;route.obtainRelic(RelicId::WING_BOOTS);
            require(route.wingBootsCharges==3,"reacquired Wing Boots did not reset charges");
            auto gifted=route;gifted.curEvent=Event::NLOTH;gifted.screenState=ScreenState::EVENT_SCREEN;
            for(int i=0;i<int(gifted.relics.relics.size());++i)
                if(gifted.relics.relics[i].id==RelicId::WING_BOOTS)gifted.info.relicIdx0=i;
            gifted.regainControlAction=[](GameContext &g){g.screenState=ScreenState::MAP_SCREEN;};
            GameAction(0).execute(gifted);
            require(!gifted.hasRelic(RelicId::WING_BOOTS) && gifted.wingBootsCharges==0,
                    "N'loth removal left charge state behind");
            route.curMapNodeY=-1;
            require(route.mapMoveCost(1)==0 && route.mapMoveCost(5)==-1,"first row used jump");
            route.curMapNodeY=14;
            require(route.mapMoveCost(0)==0 && route.mapMoveCost(5)==-1,"boss step used jump");
            for(int counter:{-2,0,1,2,3}) {
                SaveFile save;save.relics={RelicId::WING_BOOTS};save.relic_counters={counter};
                GameContext loaded;loaded.initRelicsFromSave(save);
                require(loaded.wingBootsCharges==std::max(0,counter)
                        && loaded.relics.getRelicValue(RelicId::WING_BOOTS)==0,"save Wing Boots counter mismatch");
            }
            for(int counter:{-3,-1,4}) {
                SaveFile save;save.relics={RelicId::WING_BOOTS};save.relic_counters={counter};
                bool rejected=false;try {GameContext loaded;loaded.initRelicsFromSave(save);}catch(const std::invalid_argument&){rejected=true;}
                require(rejected,"malformed Wing Boots save counter accepted");
            }
        }
        {
            auto upgraded = gc;
            upgraded.deck = Deck{};
            upgraded.deck.obtain(upgraded, Card(CardId::SEARING_BLOW));
            for (int i=0;i<5;++i) {
                upgraded.deck.upgrade(0);
                require(upgraded.deck.upgradeableCount==1 && upgraded.deck.cards[0].canUpgrade(),
                        "repeated Searing Blow upgrades lost upgrade eligibility");
            }
            upgraded.deck.upgradeRandomCards(upgraded.miscRng, 1);
            require(upgraded.deck.upgradeableCount==1,"random Searing Blow upgrade lost eligibility");
            upgraded.deck.remove(upgraded,0);
            require(upgraded.deck.upgradeableCount==0,"Searing Blow removal left an invalid count");
            upgraded.relics.add({RelicId::MOLTEN_EGG,0});
            const auto preview=upgraded.previewObtainCard(Card(CardId::SEARING_BLOW));
            require(preview.isUpgraded() && upgraded.previewObtainCard(preview)==preview,
                    "Egg preview upgraded a previously upgraded Searing Blow");
            upgraded.deck.obtain(upgraded,preview);
            require(upgraded.deck.cards[0]==preview && upgraded.deck.upgradeableCount==1,
                    "Egg acquisition repeated the preview upgrade");
            upgraded.deck.obtain(upgraded,Card(CardId::BASH));
            require(upgraded.deck.upgradeableCount==1,"Egg-upgraded ordinary card stayed eligible");
            upgraded.deck.upgrade(1);
            require(upgraded.deck.upgradeableCount==1,"repeated ordinary upgrade corrupted cached count");
        }
        {
            auto replacement=gc;
            replacement.screenState=ScreenState::REWARDS;
            replacement.info.rewardsContainer.clear();
            replacement.info.rewardsContainer.addPotion(Potion::FRUIT_JUICE);
            replacement.potionCount=replacement.potionCapacity;
            for(int slot=0;slot<replacement.potionCapacity;++slot) replacement.potions[slot]=Potion::FIRE_POTION;
            const auto choices=enumerateOocSemanticActions(replacement);
            require(choices.supported && choices.complete,"full belt replacement enumeration failed");
            int discards=0;
            for(const auto &choice:choices.actions) if(choice.effect==OocSemanticEffect::DISCARD_POTION) {
                ++discards;
                auto next=replacement;
                const auto result=executeOocSemanticAction(next,choice);
                require(result.ok && next.potionCount==replacement.potionCount-1
                    && next.screenState==ScreenState::REWARDS && next.info.rewardsContainer.potionCount==1,
                    "discard potion fell through into a reward or left the screen");
                const auto following=enumerateOocSemanticActions(next);
                auto take=std::find_if(following.actions.begin(),following.actions.end(),[](const auto &a) {
                    return a.effect==OocSemanticEffect::TAKE_POTION;
                });
                require(take!=following.actions.end() && executeOocSemanticAction(next,*take).ok
                    && next.potionCount==replacement.potionCount,"replacement potion not claimable");
            }
            require(discards==replacement.potionCapacity,"duplicate potion slots lost semantic identity");
            replacement.relics.add({RelicId::SOZU,0});
            const auto blocked=enumerateOocSemanticActions(replacement);
            require(std::none_of(blocked.actions.begin(),blocked.actions.end(),[](const auto &a) {
                return a.effect==OocSemanticEffect::DISCARD_POTION;
            }),"Sozu offered a discard for an unclaimable replacement");
        }
        {
            auto counterState = gc;
            counterState.floorNum = 16;
            std::mt19937_64 draws(97);
            bool sawJuzuAboveOne = false;
            const auto onLattice = [](float value, float start, float step) {
                for (int i = 0; i <= 16; ++i) {
                    if (value == start) return true;
                    start += step;
                }
                return false;
            };
            for (int i = 0; i < 256; ++i) {
                sampleLiveOocHiddenCounters(counterState, draws, 16);
                require(onLattice(counterState.monsterChance, .1f, .1f)
                        && onLattice(counterState.shopChance, .03f, .03f)
                        && onLattice(counterState.treasureChance, .02f, .02f),
                    "live room-chance prior left native increment lattice");
                require(counterState.potionChance >= -40 && counterState.potionChance <= 60
                        && counterState.potionChance % 10 == 0,
                    "live potion prior left native reachable support");
                require(counterState.cardRarityFactor >= -40 && counterState.cardRarityFactor <= 5,
                    "live card-rarity prior left native reachable support");
                sawJuzuAboveOne |= counterState.monsterChance > 1.0f;
            }
            require(sawJuzuAboveOne, "live monster prior excludes Juzu-reachable values");
            sampleLiveOocHiddenCounters(counterState, draws, 0);
            require(counterState.monsterChance == .1f
                    && counterState.shopChance == .03f
                    && counterState.treasureChance == .02f,
                "zero public event rooms allowed impossible chance increments");
            for (int i = 0; i < 32; ++i) {
                sampleLiveOocHiddenCounters(counterState, draws, 2);
                require(counterState.monsterChance <= .1f + .1f + .1f
                        && counterState.shopChance <= .03f + .03f + .03f
                        && counterState.treasureChance <= .02f + .02f + .02f,
                    "live room chance exceeded observed event-room support");
            }
            counterState.monsterChance = .1f + .1f + .1f;
            counterState.shopChance = .03f;
            counterState.treasureChance = .02f + .02f;
            bool pityVaried = false;
            for (int i = 0; i < 32; ++i) {
                counterState.potionChance = 999;
                counterState.cardRarityFactor = 999;
                sampleLiveOocHiddenCounters(counterState, draws, 2, true);
                require(counterState.monsterChance == .1f + .1f + .1f
                        && counterState.shopChance == .03f
                        && counterState.treasureChance == .02f + .02f,
                    "qualified public question history was resampled");
                require(counterState.potionChance >= -40 && counterState.potionChance <= 60
                        && counterState.potionChance % 10 == 0
                        && counterState.cardRarityFactor >= -40 && counterState.cardRarityFactor <= 5,
                    "qualified question history prevented hidden reward-pity sampling");
                pityVaried |= counterState.potionChance != 0;
            }
            require(pityVaried, "qualified history collapsed the reward prior");
        }
        {
            auto fullBelt = gc;
            fullBelt.screenState = ScreenState::REWARDS;
            fullBelt.potionCount = fullBelt.potionCapacity;
            fullBelt.info.rewardsContainer.clear();
            fullBelt.info.rewardsContainer.addPotion(Potion::FIRE_POTION);
            CardReward cards;
            cards.push_back(Card(CardId::BASH));
            fullBelt.info.rewardsContainer.addCardReward(cards);
            require(!collectFreeOocReward(fullBelt, false)
                    && fullBelt.info.rewardsContainer.potionCount == 1
                    && fullBelt.info.rewardsContainer.cardRewardCount == 1,
                "full potion belt claimed an invalid reward or hid the card decision");
        }
        {
            auto gold = gc;
            gold.screenState = ScreenState::REWARDS;
            gold.gold = 100;
            gold.curHp = 40;
            gold.info.eventData = 17;
            gold.info.rewardsContainer.clear();
            gold.info.rewardsContainer.addGold(20);
            gold.info.rewardsContainer.addGold(30);
            CardReward cards;
            cards.push_back(Card(CardId::BASH));
            gold.info.rewardsContainer.addCardReward(cards);
            gold.info.rewardsContainer.addPotion(Potion::FIRE_POTION);
            require(collectForcedRewardGold(gold), "ordinary reward gold was not collected");
            require(gold.gold == 150 && gold.info.rewardsContainer.goldRewardCount == 0
                    && gold.info.rewardsContainer.cardRewardCount == 1
                    && gold.info.rewardsContainer.potionCount == 1
                    && gold.screenState == ScreenState::REWARDS && gold.info.eventData == 17,
                "forced gold closure changed non-gold rewards or continued the room");

            auto ectoplasm = gold;
            ectoplasm.gold = 100;
            ectoplasm.info.rewardsContainer.addGold(25);
            ectoplasm.relics.add({RelicId::ECTOPLASM, 0});
            require(collectForcedRewardGold(ectoplasm) && ectoplasm.gold == 100
                    && ectoplasm.info.rewardsContainer.goldRewardCount == 0,
                "Ectoplasm gold closure changed gold or left the reward");

            auto idol = gc;
            idol.screenState = ScreenState::REWARDS;
            idol.curHp = idol.maxHp - 2;
            idol.gold = 100;
            idol.info.rewardsContainer.clear();
            idol.info.rewardsContainer.addGold(25);
            idol.relics.add({RelicId::BLOODY_IDOL, 0});
            require(collectForcedRewardGold(idol) && idol.gold == 125
                    && idol.curHp == idol.maxHp && idol.info.rewardsContainer.goldRewardCount == 0,
                "Bloody Idol gold closure did not preserve native healing and cap behavior");
        }
        gc.screenState = ScreenState::REST_ROOM;
        gc.curHp = 40;
        const PathHistory path{};
        auto model = std::make_unique<OocStrategicTokNet>();
        const auto missingModel = scoreLiveOocV4(gc, path, *model);
        require(!missingModel.supported && missingModel.reason == "MODEL_UNAVAILABLE"
                && missingModel.selectedIndex == -1, "missing model accepted");
        require(missingModel.candidates.size() == v4CandidateActions(gc).size(),
                "missing model did not retain current candidates for mapping validation");
        model->ok = true; // zero weights give exact ties for every action

        auto forcedMap = gc;
        forcedMap.screenState = ScreenState::MAP_SCREEN;
        forcedMap.curEvent = Event::INVALID;
        forcedMap.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
        for (auto &node : forcedMap.map->nodes[0]) node.room = Room::MONSTER;
        bool keptEdge = false;
        for (auto &node : forcedMap.map->nodes[0]) {
            if (!keptEdge && node.edgeCount > 0) keptEdge = true;
            else node.edgeCount = 0;
        }
        require(keptEdge, "forced live map fixture has no edge");
        PathHistory forcedPath; forcedPath.update(forcedMap);
        const auto forcedBefore = test::oocStateFingerprint(forcedMap);
        struct NoCombatSample final : CombatTransitionSampler {
            CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
                throw std::runtime_error("forced root requested CTM support");
            }
            CombatRuntimeSample sample(const GameContext &, const CombatPredictorInputV1 &,
                                       std::mt19937_64 &) const override {
                throw std::runtime_error("forced root sampled CTM");
            }
        };
        CompactTreeNet unusedWin, unusedFloor;
        unusedWin.ok = unusedFloor.ok = true;
        LiveOocMctsPolicy forcedPolicy(*model, std::make_shared<NoCombatSample>(), &unusedWin, &unusedFloor);
        const auto forcedDecision = forcedPolicy.score(forcedMap, forcedPath, 0);
        require(forcedDecision.supported && forcedDecision.trivialRootBypass && forcedDecision.selectedIndex == 0
            && forcedDecision.candidates.size() == 1
            && forcedDecision.candidates[0].prior == 1.0
            && forcedDecision.candidates[0].visitShare == 0.0
            && forcedDecision.candidates[0].visits == 0
            && !forcedDecision.valueDistribution && !forcedDecision.hpDistribution
            && !forcedDecision.candidates[0].valueDistribution && !forcedDecision.candidates[0].hpDistribution
            && forcedBefore == test::oocStateFingerprint(forcedMap),
            "live advisor returns sole map action without model sampling or mutation: "
                + forcedDecision.reason + " candidates=" + std::to_string(forcedDecision.candidates.size()));
        auto emptyRewards = forcedMap;
        emptyRewards.screenState = ScreenState::REWARDS;
        emptyRewards.info.rewardsContainer.clear();
        const auto emptyDecision = forcedPolicy.score(emptyRewards, forcedPath, 0);
        require(emptyDecision.supported && emptyDecision.trivialRootBypass
                && emptyDecision.candidates.size() == 1 && emptyDecision.candidates[0].visits == 0
                && emptyDecision.candidates[0].visitShare == 0 && !emptyDecision.valueDistribution,
                "empty rewards must return an explicit unsearched sole action");

        GameContext shop = gc;
        shop.screenState = ScreenState::SHOP_ROOM;
        shop.gold = 200;
        for (int i = 0; i < 7; ++i) shop.info.shop.cardPrice(i) = -1;
        for (int i = 0; i < 3; ++i) shop.info.shop.potionPrice(i) = -1;
        shop.info.shop.removeCost = -1;
        shop.info.shop.relics[0] = RelicId::PRISMATIC_SHARD;
        shop.info.shop.relicPrice(0) = 50;
        shop.info.shop.relics[1] = RelicId::ANCHOR;
        shop.info.shop.relicPrice(1) = 50;
        shop.info.shop.relicPrice(2) = -1;
        const auto allShopActions = search::GameAction::getAllActionsInState(shop);
        const auto shopCandidates = v4CandidateActions(shop);
        const auto isRelic = [](const auto &action) {
            return action.getRewardsActionType() == search::GameAction::RewardsActionType::RELIC
                && action.getIdx1() >= 0 && action.getIdx1() < 3;
        };
        require(std::any_of(allShopActions.begin(), allShopActions.end(), [&](const auto &action) {
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
                }), "shop fixture did not expose Prismatic Shard");
        require(std::none_of(shopCandidates.begin(), shopCandidates.end(), [&](const auto &action) {
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
                }), "Prismatic Shard remained an autonomous OOC candidate");
        require(std::any_of(shopCandidates.begin(), shopCandidates.end(), [&](const auto &action) {
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::ANCHOR;
                }), "normal relic was removed with Prismatic Shard");
        require(std::any_of(shopCandidates.begin(), shopCandidates.end(), [](const auto &action) {
                    return action.getRewardsActionType() == search::GameAction::RewardsActionType::SKIP;
                }), "shop leave action was removed with Prismatic Shard");
        const auto shopDecision = scoreLiveOocV4(shop, path, *model);
        require(shopDecision.supported, "shop with Prismatic Shard became unsupported: " + shopDecision.reason);
        require(std::none_of(shopDecision.candidates.begin(), shopDecision.candidates.end(), [&](const auto &candidate) {
                    const auto action = search::GameAction(candidate.primitiveBits);
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
                }), "scored OOC candidates still contain Prismatic Shard");

        const auto before = test::oocStateFingerprint(gc);
        int callbacks = 0;
        g_onGameActionExecute = [&](std::uint32_t, const GameContext *) { ++callbacks; };
        LiveOocV4QPolicy provider(*model);
        const auto decision = provider.score(gc, path, 0);
        g_onGameActionExecute = {};
        require(decision.supported, "campfire score failed: " + decision.reason);
        require(before == test::oocStateFingerprint(gc) && callbacks == 0,
                "read-only scoring mutated state/RNG or executed a primitive");
        require(decision.selectedIndex == 0, "ties do not choose first canonical key");
        require(decision.candidates.size() == v4CandidateActions(gc).size(), "candidate count changed");
        bool smith = false;
        for (std::size_t i = 0; i < decision.candidates.size(); ++i) {
            const auto &candidate = decision.candidates[i];
            require(candidate.q == 0.0, "zero model did not tie");
            if (i) require(decision.candidates[i-1].semanticKey < candidate.semanticKey,
                           "canonical identities not strictly sorted");
            if (candidate.primitiveBits == GameAction(1).bits) {
                const auto payload = nlohmann::json::parse(candidate.payload);
                require(payload.at("currentScreenOnly") == true && payload.at("type") == "none"
                        && !payload.contains("card"), "smith returned a target or compound plan");
                const auto preview = nlohmann::json::parse(candidate.followUpPreview);
                require(preview.at("status") == "OK" && preview.at("scope") == "selector_preview"
                        && preview.at("policy") == "v4_q" && !preview.contains("liveAction"),
                        "smith preview is not a separate display-only selector decision");
                smith = true;
            }
        }
        require(smith, "smith current-screen intent missing");
        auto wall = gc;
        wall.screenState = ScreenState::EVENT_SCREEN;
        wall.curEvent = Event::LIVING_WALL;
        const auto wallBefore = test::oocStateFingerprint(wall);
        const auto wallDecision = provider.score(wall, path, 0);
        require(wallDecision.supported && wallBefore == test::oocStateFingerprint(wall),
                "Living Wall preview changed native state");
        auto selector = wall;
        selector.openCardSelectScreen(CardSelectScreenType::UPGRADE, 1);
        const auto selectorDecision = provider.score(selector, path, 0);
        require(selectorDecision.supported, "direct upgrade selector unavailable");
        const auto &selectorBest = selectorDecision.candidates.at(selectorDecision.selectedIndex);
        const int expectedDeckIndex = selector.info.toSelectCards[GameAction(selectorBest.primitiveBits).getIdx1()].deckIdx;
        std::set<int> physicalDeckIndices;
        for (const auto &candidate : selectorDecision.candidates)
            physicalDeckIndices.insert(selector.info.toSelectCards[GameAction(candidate.primitiveBits).getIdx1()].deckIdx);
        require(physicalDeckIndices.size() == static_cast<std::size_t>(selector.deck.size()),
                "duplicate physical upgrade cards were collapsed");
        for (const auto &candidate : wallDecision.candidates) {
            const auto preview = nlohmann::json::parse(candidate.followUpPreview);
            if (candidate.primitiveBits == GameAction(2).bits) {
                require(preview.at("status") == "OK" && preview.at("q") == selectorBest.q
                        && preview.at("semanticKey") == selectorBest.semanticKey
                        && preview.at("card").at("deckIndex") == expectedDeckIndex,
                        "Living Wall upgrade preview differs from separate native selector");
            } else require(preview.at("status") == "UNSUPPORTED"
                        && preview.at("reason") == "V4_SELECTOR_UNSUPPORTED"
                        && !preview.contains("q") && !preview.contains("card"),
                        "remove/transform preview invented a scored target");
        }
        model->q2b = 200;
        const auto rawUtility = scoreLiveOocV4(gc, path, *model);
        require(rawUtility.supported && rawUtility.candidates.front().q > 100,
                "raw finite V4 utility is not clamped to probability or percentage units");
        model->q2b = std::numeric_limits<float>::infinity();
        require(scoreLiveOocV4(gc, path, *model).reason == "NONFINITE_Q", "infinite Q accepted");
        model->q2b = std::numeric_limits<float>::quiet_NaN();
        require(scoreLiveOocV4(gc, path, *model).reason == "NONFINITE_Q", "NaN Q accepted");
        model->q2b = 0;
        gc.outcome = GameOutcome::PLAYER_VICTORY;
        require(scoreLiveOocV4(gc, path, *model).reason == "EMPTY_CANDIDATE_SET", "empty candidates accepted");
        gc.outcome = GameOutcome::UNDECIDED;
        gc.screenState = ScreenState::CARD_SELECT;
        gc.info.selectScreenType = CardSelectScreenType::REMOVE;
        require(scoreLiveOocV4(gc, path, *model).reason == "V4_SCREEN_UNSUPPORTED", "removal support widened");
        gc.info.selectScreenType = CardSelectScreenType::UPGRADE;
        gc.info.toSelectCount = 2;
        gc.info.toSelectCards.clear();
        gc.info.toSelectCards.push_back(SelectScreenCard(gc.deck.cards[0], 0));
        require(scoreLiveOocV4(gc, path, *model).reason.rfind("SEMANTIC_ENUMERATION_FAILURE:", 0) == 0,
                "malformed selector cardinality was classified as fallback-safe unsupported");
        model->ok = false;
        require(scoreLiveOocV4(gc, path, *model).reason.rfind("SEMANTIC_ENUMERATION_FAILURE:", 0) == 0,
                "missing model hid malformed semantic enumeration");
        model->ok = true;
        gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer = {};
        require(scoreLiveOocV4(gc, path, *model).reason == "V4_SCREEN_UNSUPPORTED", "non-card reward support widened");
        auto &rewards = gc.info.rewardsContainer;
        rewards.cardRewardCount = 1;
        rewards.cardRewards[0].push_back(Card(CardId::BASH));
        rewards.goldRewardCount = 2;
        rewards.gold[0] = 20;
        rewards.gold[1] = 30;
        require(scoreLiveOocV4(gc, path, *model).reason == "CANDIDATE_ENUMERATION_DISAGREEMENT",
                "duplicate native primitive enumeration accepted");

        require(argc == 2 && model->load(argv[1]), "tracked V4 model failed to load");
        gc.screenState = ScreenState::REST_ROOM;
        const auto actual = scoreLiveOocV4(gc, path, *model);
        require(actual.supported, "tracked model scoring failed: " + actual.reason);
        const auto tokens = buildTokStatePure(gc, path);
        for (const auto &candidate : actual.candidates) {
            const GameAction action(candidate.primitiveBits);
            int type, c1, c2, c3, v1, v2, v3, entityType, entityId;
            float goldGePrice;
            strategicCands(gc, action, type, c1, c2, c3, v1, v2, v3);
            const int cats[6] = {c1, c2, c3, v1, v2, v3};
            tokEntity(gc, action, entityType, entityId, goldGePrice);
            const float entity[4] = {float(entityType == 0), float(entityType == 1),
                                     float(entityType == 2), float(entityType == 3)};
            const double expected = model->predictActionValue(tokens.glob, tokens.nDk, tokens.dk,
                tokens.nRl, tokens.rl, tokens.nPt, tokens.pt, action.bits, cats, type,
                int(gc.screenState), entity, entityId, goldGePrice);
            require(candidate.q == expected, "prepared scorer differs from direct V4 Q");
        }
        GameContext pending(CharacterClass::IRONCLAD, 991, 0);
        pending.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
        pending.regainControlAction = [](GameContext &state) {
            state.screenState = ScreenState::MAP_SCREEN;
            state.regainControlAction = nullptr;
        };
        bool leafSawMap = false;
        OocMctsDependencies deps;
        deps.policyAvailable = [] { return true; };
        deps.policyLogits = [](const GameContext &, const PathHistory &,
                               const std::vector<GameAction> &actions) {
            return std::vector<double>(actions.size(), 0.0);
        };
        deps.leafValue = [&](const GameContext &state, const PathHistory &) {
            leafSawMap = state.screenState == ScreenState::MAP_SCREEN;
            return 0.25;
        };
        int mapContinuationCalls = 0;
        deps.continuationStep = [&](GameContext &state, PathHistory &, std::mt19937_64 &) {
            if (state.screenState == ScreenState::MAP_SCREEN) {
                ++mapContinuationCalls;
                throw OocSearchUnsupported("MAP checkpoint was expanded");
            }
            const auto semantic = enumerateOocSemanticPrimitiveBindings(state);
            if (!semantic.supported || !semantic.complete || semantic.bindings.empty())
                throw OocSearchUnsupported("test continuation enumeration");
            GameAction(semantic.bindings.front().primitiveBits).execute(state);
        };
        OocAdapterOptions checkpoint;checkpoint.checkpointLeaves=true;
        checkpoint.stopAtMapCheckpoint=true;
        for (const auto outcome : {GameOutcome::PLAYER_LOSS, GameOutcome::PLAYER_VICTORY}) {
            auto terminalDeps = deps;
            terminalDeps.continuationStep = [outcome](GameContext &state, PathHistory &, std::mt19937_64 &rng) {
                (void)rng(); state.outcome = outcome; state.act = 4;
            };
            OocGameContextModel terminalLeaf(pending, path, {}, checkpoint, terminalDeps);
            OocGameContextModel scalarLeaf(pending, path, {}, checkpoint, terminalDeps);
            std::mt19937_64 annotatedRng(17), scalarRng(17);
            const auto sample = terminalLeaf.evaluateLeafWithOutcome(0, annotatedRng);
            const double scalar = scalarLeaf.evaluateLeaf(0, scalarRng);
            require(sample.terminal && sample.value == scalar && annotatedRng == scalarRng
                    && sample.value == (outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0),
                    "detached continuation endpoint or exact scalar/RNG parity lost");
        }
        auto zeroDeps = deps;
        zeroDeps.leafValue = [](const GameContext &, const PathHistory &) { return 0.; };
        OocGameContextModel zeroLeaf(pending, path, {}, checkpoint, zeroDeps);
        std::mt19937_64 zeroRng(17);
        const auto zeroSample = zeroLeaf.evaluateLeafWithOutcome(0, zeroRng);
        require(!zeroSample.terminal && zeroSample.value == 0,
                "nonterminal MAP model zero must not become terminal death");
        OocGameContextModel checkpointModel(pending, path, {}, checkpoint, deps);
        std::mt19937_64 checkpointRng(17);
        require(checkpointModel.evaluateLeaf(0, checkpointRng) == 0.25 && leafSawMap
                && checkpointModel.continuationMetrics().projectionSteps > 0,
                "advisor checkpoint leaf evaluated an unresolved selector");
        OocMctsConfig checkpointConfig;
        checkpointConfig.seed = 19;
        checkpointConfig.maxDepth = 32;
        const auto checkpointSearch = OocMctsPlanner(checkpointConfig).search(checkpointModel, 0, 64);
        require(checkpointSearch.metrics.simulations == 64 && mapContinuationCalls == 0,
                "downstream MAP checkpoint was revisited and expanded");
        {
            // Same qualified public counters, same native downstream route and
            // sampled RNG. Only the obsolete MAP hard leaf differs.
            auto route=pending;
            route.curMapNodeX=-1;route.curMapNodeY=-1;
            route.monsterChance=.3f;route.shopChance=.09f;route.treasureChance=.06f;
            auto map=std::make_shared<Map>(*route.map);
            for(auto &node:map->nodes[0]) if(node.edgeCount>0) node.room=Room::REST;
            route.map=map;
            OocMctsDependencies parityDeps;
            parityDeps.policyAvailable=[] {return true;};
            parityDeps.policyLogits=[](const GameContext &,const PathHistory &,const std::vector<GameAction> &actions) {
                return std::vector<double>(actions.size(),0.0);
            };
            parityDeps.leafValue=[](const GameContext &,const PathHistory &) { return .25; };
            int rootCounterSamples=0;
            parityDeps.sampleHiddenCounters=[&](GameContext &state,std::mt19937_64 &rng) {
                ++rootCounterSamples;
                sampleLiveOocHiddenCounters(state,rng,2,true);
            };
            auto expanded=checkpoint;expanded.stopAtMapCheckpoint=false;expanded.sampleNoncombat=true;
            OocGameContextModel liveRoute(route,path,{},expanded,parityDeps);
            std::mt19937_64 liveRng(23);
            const auto click=liveRoute.legalActions(0).front().id;
            const auto liveMap=liveRoute.sampleSuccessor(0,click,liveRng);
            require(!liveRoute.isLeafBoundary(liveMap),
                    "qualified downstream MAP remained a hard leaf");
            const auto choices=liveRoute.legalActions(liveMap);
            require(!choices.empty(),"qualified downstream MAP lost route choices");
            auto oracle=liveRoute.state(liveMap);
            liveRoute.candidate(liveMap,choices.front().id).primitive.execute(oracle);
            const auto liveRoom=liveRoute.sampleSuccessor(liveMap,choices.front().id,liveRng);
            const auto &a=liveRoute.state(liveRoom),&b=oracle;
            require(a.screenState==ScreenState::REST_ROOM && a.screenState==b.screenState
                    && a.floorNum==b.floorNum && a.curMapNodeX==b.curMapNodeX
                    && a.monsterChance==.3f && a.shopChance==.09f && a.treasureChance==.06f
                    && a.monsterChance==b.monsterChance && a.shopChance==b.shopChance
                    && a.treasureChance==b.treasureChance && rootCounterSamples==1,
                    "downstream route diverged or resampled qualified room counters");
        }
        {
            for (bool acquiredLater : {false,true}) {
                auto source=pending;
                source.map=std::make_shared<Map>();
                for(int y=0;y<15;++y)for(int x=0;x<7;++x) {
                    auto &node=source.map->nodes[y][x];node.x=x;node.y=y;node.room=Room::REST;
                }
                source.curMapNodeX=1;source.curMapNodeY=0;
                source.map->getNode(1,0).addEdge(2);
                source.map->getNode(2,1).addEdge(2);source.map->getNode(5,1).addEdge(2);
                if (!acquiredLater) source.obtainRelic(RelicId::WING_BOOTS);
                else source.regainControlAction=[](GameContext &g) {
                    g.obtainRelic(RelicId::WING_BOOTS);g.screenState=ScreenState::MAP_SCREEN;
                };
                auto expanded=checkpoint;expanded.stopAtMapCheckpoint=false;
                OocGameContextModel model(source,path,{},expanded,deps);
                std::mt19937_64 rng(29);
                const auto child=model.sampleSuccessor(0,model.legalActions(0).front().id,rng);
                require(model.state(child).screenState==ScreenState::MAP_SCREEN && !model.isLeafBoundary(child),
                        "public Wing Boots remained a downstream hard leaf");
                const auto choices=model.legalActions(child);
                require(choices.size()==2,"downstream Wing Boots lost an edge or jump");
                bool jumped=false;
                for(const auto &choice:choices) if(model.candidate(child,choice.id).primitive.getIdx1()==5) {
                    const auto next=model.sampleSuccessor(child,choice.id,rng);
                    require(model.state(next).curMapNodeX==5 && model.state(next).wingBootsCharges==2
                            && model.state(child).wingBootsCharges==3,"downstream jump charge/copy mismatch");
                    jumped=true;
                }
                require(jumped,"downstream Wing Boots jump unavailable");
                // Relic support cannot bypass missing public map histories.
                expanded.stopAtMapCheckpoint=true;
                OocGameContextModel unqualified(source,path,{},expanded,deps);
                const auto boundary=unqualified.sampleSuccessor(0,unqualified.legalActions(0).front().id,rng);
                require(unqualified.isLeafBoundary(boundary),"Wing Boots bypassed map-history guard");
            }
        }
        {
            // Independent JVM enumeration of every 24-bit RandomXS128 float:
            // these 16 cells have one extra atom; every other cell has 167772.
            const std::set<int> extra{0,6,13,19,26,33,39,45,52,58,66,72,79,85,91,97};
            const auto &bins=questionRoomCellCounts();
            for(int cell=0;cell<100;++cell)require(bins[cell]==167772u+extra.count(cell),"Java float-bin likelihood mismatch");
            const auto mass=[&](int lo,int hi) {
                long double count=0;for(int cell=lo;cell<hi;++cell)count+=bins[cell];return count/(1u<<24);
            };
            QuestionRoomBelief belief;
            require(belief.condition(Room::EVENT,true,false,false,-1) && belief.monster.size()==2,
                    "Juzu EVENT did not branch latent outcomes");
            const long double a=mass(0,10)/(mass(0,10)+mass(15,100)),b=1-a;
            require(std::abs(belief.monster[0].second-a)<1e-14 && belief.monster[0].first==.1f
                    && belief.monster[1].first==.1f+.1f,"single-room Bayesian likelihood differs");
            require(belief.condition(Room::EVENT,true,false,false,-1) && belief.monster.size()==3,
                    "second Juzu EVENT lost a latent state");
            const long double w0=a*mass(0,10)+b*mass(0,20),w1=a*mass(20,100),w2=b*mass(30,100),total=w0+w1+w2;
            require(std::abs(belief.monster[0].second-w0/total)<1e-14
                    && std::abs(belief.monster[1].second-w1/total)<1e-14
                    && std::abs(belief.monster[2].second-w2/total)<1e-14,"two-step latent enumeration mismatch");
            auto forced=belief;const auto before=forced.monster;
            require(forced.condition(Room::TREASURE,true,false,true,-1),"forced Tiny treasure rejected");
            for(std::size_t i=0;i<before.size();++i)
                require(forced.monster[i].first==before[i].first+.1f
                        && std::abs(forced.monster[i].second-before[i].second)<1e-14,"Tiny forced outcome reweighted latent chance");
            require(belief.condition(Room::MONSTER,false,false,false,-1) && belief.monster.size()==1
                    && belief.monster[0].first==.1f,"known MONSTER reset did not collapse belief");
            QuestionRoomBelief suppressed;
            require(!suppressed.condition(Room::SHOP,true,true,false,-1),"previous SHOP suppression ignored");
            QuestionRoomBelief impossible;
            require(!impossible.condition(Room::EVENT,true,false,true,-1),"forced Tiny EVENT accepted");
            QuestionRoomBelief flash;
            require(flash.condition(Room::EVENT,true,false,false,1) && flash.monster.size()==1
                    && flash.monster[0].first==.1f,"observed conversion did not collapse belief");
            QuestionRoomBelief noFlash;
            require(noFlash.condition(Room::EVENT,true,false,false,0) && noFlash.monster.size()==1
                    && noFlash.monster[0].first==.1f+.1f,"observed absence did not exclude conversion");
            QuestionRoomBelief clipped;clipped.monster={{.1f,.5},{.95f,.5}};clipped.shop=.1f;
            require(clipped.condition(Room::SHOP,true,false,false,-1) && clipped.monster.size()==2,
                    "saturated shop observation lost posterior");
            require(std::abs(clipped.monster[0].second-mass(10,20)/(mass(10,20)+mass(95,99)))<1e-14,
                    "non-EVENT outcome did not condition latent chances");
            std::mt19937_64 left(17),right(17);
            auto particle=gc,replica=gc;particle.shopChance=replica.shopChance=.27f;
            particle.treasureChance=replica.treasureChance=.12f;
            for(int draw=0;draw<20;++draw) {
                sampleLiveOocHiddenCounters(particle,left,4,true);
                sampleLiveOocHiddenCounters(replica,right,4,true);
                sampleQuestionChancePosterior(particle,left,clipped.monster);
                sampleQuestionChancePosterior(replica,right,clipped.monster);
                require(particle.monsterChance==replica.monsterChance && particle.shopChance==.27f
                        && particle.treasureChance==.12f,"posterior sampling changed exact counters or isolated determinism");
                require(particle.monsterChance==clipped.monster[0].first || particle.monsterChance==clipped.monster[1].first,
                        "posterior sampled outside finite support");
            }
        }
        std::cout << "live OOC policy contract PASS\n";
        return 0;
    } catch (const std::exception &error) {
        sts::search::g_onGameActionExecute = {};
        std::cerr << "live OOC policy contract FAIL: " << error.what() << '\n';
        return 1;
    }
}
