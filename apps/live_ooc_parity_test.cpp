#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "constants/SaveFileMappings.h"
#include "one_combat/live_ooc_state.h"
#include "one_combat/live_ooc_policy.h"
#include "one_combat/ooc_v4_encoding.h"
#include "ooc_strategic_tok_net.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/GameAction.h"
#include "sim/search/MatchAndKeepPolicy.h"

using namespace sts;
using namespace one_combat;
using J = nlohmann::json;
using A = search::GameAction;
using RT = A::RewardsActionType;
static void check(bool b,const std::string &why){if(!b)throw std::runtime_error(why);}
static J cardWire(const Card &c){return {{"id",J(c.id)},{"upgraded",c.isUpgraded()},{"misc",c.misc}};}
static std::string eventPageForFixture(const GameContext &g) {
    switch(g.curEvent) {
        case Event::THE_CLERIC:case Event::PLEADING_VAGRANT:case Event::AUGMENTER:
        case Event::FORGOTTEN_ALTAR:case Event::GHOSTS:case Event::SCRAP_OOZE:case Event::VAMPIRES:
        case Event::THE_MOAI_HEAD:case Event::NLOTH:case Event::HYPNOTIZING_COLORED_MUSHROOMS:return "0";
        case Event::GOLDEN_IDOL:return g.info.phase==1?"1":"0";
        case Event::SHINING_LIGHT:case Event::WING_STATUE:case Event::OLD_BEGGAR:case Event::MASKED_BANDITS:
        case Event::MINDBLOOM:case Event::TOMB_OF_LORD_RED_MASK:case Event::GOLDEN_SHRINE:
        case Event::THE_SSSSSERPENT:case Event::DEAD_ADVENTURER:case Event::WE_MEET_AGAIN:
        case Event::MYSTERIOUS_SPHERE:return "INTRO";
        case Event::THE_NEST:case Event::WINDING_HALLS:return "1";
        case Event::FACE_TRADER:case Event::DESIGNER_IN_SPIRE:return "MAIN";
        case Event::FALLING:return "CHOICE";case Event::KNOWING_SKULL:return "ASK";
        case Event::SENSORY_STONE:return "INTRO_2";case Event::NOTE_FOR_YOURSELF:return "CHOOSE";
        case Event::THE_JOUST:return "EXPLANATION";
        case Event::COLOSSEUM:return g.info.eventData==0?"FIGHT":"POST_COMBAT";
        case Event::CURSED_TOME:return std::array<std::string,5>{"INTRO","PAGE_1","PAGE_2","PAGE_3","LAST_PAGE"}[g.info.eventData];
        default:return "";
    }
}
// Independent native fixture projection: no serialization of native internal
// memory, RNG states, pools, encounters, callbacks or future outcomes.
static J project(const GameContext &g,const PathHistory &path,const std::string &name) {
    J p={{"character","IRONCLAD"},{"ascension",g.ascension},{"act",g.act},{"floor",g.floorNum},
        {"hp",g.curHp},{"maxHp",g.maxHp},{"gold",g.gold},
        {"blueKey",g.blueKey},{"greenKey",g.greenKey},{"keysEnabled",g.keysEnabled},{"redKey",g.redKey},
        {"potionCapacity",g.potionCapacity},{"potions",J::array()},{"deck",J::array()},{"relics",J::array()},
        {"boss",J(g.boss)},{"pathComplete",true},{"pathVisits",path.roomVisits},
        {"currentActPathVisits",J::array({0,0,0,0,0,0,0,0,0,0})},{"acquiredRelics",J::array()},
        {"pathHistory",J::array()},{"combatFloors",J::array()},
        {"combatHistory",J::array()},{"combatHistoryComplete",true},
        {"seenRelics",J::array()},{"seenRelicsComplete",true},
        {"rewardPityHistoryComplete",true},
        {"priorEvents",J::array()},{"shopRemoveCount",g.shopRemoveCount}};
    for(const auto pot:g.potions)p["potions"].push_back(J(pot));
    for(int i=0;i<g.deck.size();++i){auto c=cardWire(g.deck.cards[i]);int bottle=-1;
        for(int j=0;j<3;++j)if(g.deck.bottleIdxs[j]==i)bottle=j;c["bottleBinding"]=bottle;p["deck"].push_back(c);}
    for(const auto &r:g.relics.relics){p["relics"].push_back({{"id",J(r.id)},{"data",r.data}});p["acquiredRelics"].push_back(J(r.id));}
    J m={{"x",g.curMapNodeX},{"y",g.curMapNodeY},{"burningEliteX",g.map->burningEliteX},
        {"burningEliteY",g.map->burningEliteY},{"nodes",J::array()}};
    for(const auto &row:g.map->nodes)for(const auto &n:row){J es=J::array();for(int i=0;i<n.edgeCount;++i)es.push_back(n.edges[i]);
        m["nodes"].push_back({{"x",n.x},{"y",n.y},{"room",roomStrings[static_cast<int>(n.room)]},{"edges",es}});}
    p["map"]=m;
    J d=J::object();std::string screen;
    switch(g.screenState){
        case ScreenState::REWARDS:{screen="card_reward";const auto &r=g.info.rewardsContainer;
            d={{"gold",J::array()},{"cardRewards",J::array()},{"relics",J::array()},{"potions",J::array()},
                {"emeraldKey",r.emeraldKey},{"sapphireKey",r.sapphireKey}};
            for(int i=0;i<r.goldRewardCount;++i)d["gold"].push_back(r.gold[i]);
            for(int i=0;i<r.cardRewardCount;++i){J cs=J::array();for(const auto &c:r.cardRewards[i])cs.push_back(cardWire(c));d["cardRewards"].push_back(cs);}
            for(int i=0;i<r.relicCount;++i)d["relics"].push_back(J(r.relics[i]));
            for(int i=0;i<r.potionCount;++i)d["potions"].push_back(J(r.potions[i]));break;}
        case ScreenState::REST_ROOM:screen="rest";break;
        case ScreenState::MAP_SCREEN:screen="map";break;
        case ScreenState::TREASURE_ROOM:{screen="treasure";
            const char *types[]={"SmallChest","MediumChest","LargeChest"};
            const int size=static_cast<int>(g.info.chestSize);
            check(size>=0 && size<3,"fixture chest size");
            d={{"chestType",types[size]},{"chestSize",size},{"opened",false}};break;}
        case ScreenState::BOSS_RELIC_REWARDS:screen="boss_relic";d["relics"]=J::array();for(auto r:g.info.bossRelics)d["relics"].push_back(J(r));break;
        case ScreenState::CARD_SELECT:{screen="selector";
            const char *types[]={"invalid","transform","transform_upgrade","upgrade","remove",
                "duplicate","obtain","bottle","bonfire"};
            d={{"type",types[static_cast<int>(g.info.selectScreenType)]},
                {"requiredPicks",g.info.toSelectCount},{"completedPicks",g.info.haveSelectedCards.size()},
                {"cards",J::array()},{"selectedCards",J::array()}};
            for(const auto &c:g.info.toSelectCards)d["cards"].push_back({{"deckIndex",c.deckIdx},{"card",cardWire(c.card)}});
            for(const auto &c:g.info.haveSelectedCards)d["selectedCards"].push_back({{"deckIndex",c.deckIdx},{"card",cardWire(c.card)}});
            if(g.info.selectScreenType==CardSelectScreenType::OBTAIN) {
                d["event"]="The Library";d["phase"]=1;d["confirm"]=false;
                for(int i=0;i<static_cast<int>(d["cards"].size());++i) {
                    d["cards"][i].erase("deckIndex");d["cards"][i]["uuid"]="library-"+std::to_string(i);
                }
            }
            if(g.info.selectScreenType==CardSelectScreenType::BOTTLE) {
                const char *types[]={"attack","skill","power"};
                d["bottleType"]=types[static_cast<int>(g.info.toSelectCards[0].card.getType())];
            }
            break;}
        case ScreenState::SHOP_ROOM:{screen="shop";const auto &s=g.info.shop;
            d={{"cards",J::array()},{"relics",J::array()},{"potions",J::array()},{"removeCost",s.removeCost}};
            for(int i=0;i<7;++i)d["cards"].push_back({{"card",s.cardPrice(i)<0?J():cardWire(s.cards[i])},{"price",s.cardPrice(i)}});
            for(int i=0;i<3;++i){d["relics"].push_back({{"id",J(s.relics[i])},{"price",s.relicPrice(i)}});
                d["potions"].push_back({{"id",J(s.potions[i])},{"price",s.potionPrice(i)}});}break;}
        case ScreenState::EVENT_SCREEN:{screen="event";const auto &i=g.info;
            d={{"event",g.curEvent==Event::NEOW?J("Neow"):J(g.curEvent)},{"eventData",i.eventData},{"phase",i.phase},
                {"upgradeOne",i.upgradeOne},{"cleanUpIsRemoveCard",i.cleanUpIsRemoveCard},{"skillCardDeckIdx",i.skillCardDeckIdx},
                {"powerCardDeckIdx",i.powerCardDeckIdx},{"attackCardDeckIdx",i.attackCardDeckIdx},{"potionIdx",i.potionIdx},
                {"gold",i.gold},{"cardIdx",i.cardIdx}};
            if(g.curEvent==Event::WORLD_OF_GOOP)d["goldLoss"]=i.goldLoss;
            if(g.curEvent==Event::THE_LIBRARY)d["hpAmount0"]=i.hpAmount0;
            if(g.curEvent==Event::NEOW){d["neow"]=J::array();for(const auto &n:i.neowRewards)d["neow"].push_back({{"bonus",J(n.r)},{"drawback",J(n.d)}});}break;}
        default:throw std::runtime_error("fixture screen missing");
    }
    J o={{"schemaVersion",1},{"screen",screen},{"publicState",p},{"details",d},{"liveChoices",J::array()}};
    int ix=1;
    for(const auto &a:v4CandidateActions(g)) {
        J native={{"kind","option"},{"index",a.getIdx1()}};
        if(g.screenState==ScreenState::REWARDS||g.screenState==ScreenState::SHOP_ROOM){
            const char *kinds[]={"card","gold","key","potion","relic","remove","skip"};
            native["kind"]=kinds[static_cast<int>(a.getRewardsActionType())];
            if(g.screenState==ScreenState::REWARDS&&a.getRewardsActionType()==RT::CARD){native["group"]=a.getIdx1();native["index"]=a.getIdx2();}
        }
        J liveAction={{"kind","choose"},{"choiceIndex",ix++}};
        if(g.screenState==ScreenState::REWARDS && !g.hasRelic(RelicId::SINGING_BOWL)) {
            const auto &r=g.info.rewardsContainer;
            const bool finalCard=r.cardRewardCount==1 && r.goldRewardCount==0 && r.relicCount==0
                && r.potionCount==0 && !r.emeraldKey && !r.sapphireKey;
            if(finalCard && (a.getRewardsActionType()==RT::SKIP
                    || (a.getRewardsActionType()==RT::CARD && a.getIdx2()==5)))
                // Java exposes one Skip button for these two native aliases.
                // Distinct synthetic choose indices would fail MCTS mapping
                // validation when it merges the equivalent search choices.
                liveAction={{"kind","skip"}};
        }
        o["liveChoices"].push_back({{"nativeAction",native},{"liveAction",liveAction}});
    }
    for(const auto &binding:sts::search::enumerateOocSemanticPrimitiveBindings(g).bindings) {
        const auto a=A(binding.primitiveBits);
        if(a.isPotionDiscard()) o["liveChoices"].push_back({
            {"nativeAction",{{"kind","discard_potion"},{"index",a.getIdx1()},{"group",0}}},
            {"liveAction",{{"kind","discard_potion"},{"potionSlot",a.getIdx1()+1}}}});
    }
    if (g.screenState == ScreenState::SHOP_ROOM) {
        const auto &s = g.info.shop;
        for (int i = 0; i < 3; ++i) {
            if (s.relics[i] != RelicId::PRISMATIC_SHARD || s.relicPrice(i) < 0) continue;
            o["liveChoices"].push_back({
                {"nativeAction", {{"kind", "relic"}, {"index", i}}},
                {"liveAction", {{"kind", "choose"}, {"choiceIndex", ix++}}}});
        }
    }
    if(g.screenState==ScreenState::EVENT_SCREEN
            && (g.curEvent==Event::OMINOUS_FORGE || g.curEvent==Event::ANCIENT_WRITING || g.curEvent==Event::THE_LIBRARY)) {
        J options=J::array();
        for(const auto &choice:o["liveChoices"])
            options.push_back({{"index",choice["nativeAction"]["index"]},{"disabled",false}});
        o["event"]={{"id",J(g.curEvent)},{"phase",g.curEvent==Event::ANCIENT_WRITING?"INTRO":"0"},
            {"options",options}};
    }
    if(g.screenState==ScreenState::EVENT_SCREEN && !eventPageForFixture(g).empty()) {
        auto &details=o["details"];
        details["eventContract"]="vanilla_v1";
        for(const auto &[key,value]:{std::pair{"hpAmount0",g.info.hpAmount0},std::pair{"hpAmount1",g.info.hpAmount1},
                std::pair{"hpAmount2",g.info.hpAmount2},std::pair{"relicIdx0",g.info.relicIdx0},std::pair{"relicIdx1",g.info.relicIdx1}})
            details[key]=value;
        if(g.curEvent==Event::FACE_TRADER)details["gold"]=g.ascension>=15?50:75;
        if(g.curEvent==Event::KNOWING_SKULL)details["leaveCost"]=6;
        if(g.curEvent==Event::SCRAP_OOZE)details["relicObtainChance"]=25+10*g.info.eventData;
        if(g.curEvent==Event::NOTE_FOR_YOURSELF)details["noteForYourselfCard"]=cardWire(g.noteForYourselfCard);
        if(g.curEvent==Event::DEAD_ADVENTURER) {
            details["encounterChance"]=g.info.phase*25+(g.ascension>=15?35:25);
            details["publicEnemy"]=g.info.encounter==MonsterEncounter::THREE_SENTRIES?0:
                g.info.encounter==MonsterEncounter::GREMLIN_NOB?1:2;
            details["earnedGold"]=std::find(g.info.rewards.begin(),g.info.rewards.begin()+g.info.phase,0)!=g.info.rewards.begin()+g.info.phase;
            details["earnedRelic"]=std::find(g.info.rewards.begin(),g.info.rewards.begin()+g.info.phase,2)!=g.info.rewards.begin()+g.info.phase;
        }
        std::vector<std::pair<int,J>> mapped;
        for(const auto &choice:o["liveChoices"]) {
            const int native=choice["nativeAction"]["index"].get<int>();int slot=native;
            if(g.curEvent==Event::GOLDEN_IDOL && eventPageForFixture(g)=="1")slot-=2;
            if(g.curEvent==Event::VAMPIRES)slot=native==1?0:native==0?1:g.hasRelic(RelicId::BLOOD_VIAL)?2:1;
            if(g.curEvent==Event::MINDBLOOM && native==3)slot=2;
            if(g.curEvent==Event::TOMB_OF_LORD_RED_MASK && g.hasRelic(RelicId::RED_MASK) && native==2)slot=1;
            if(g.curEvent==Event::FALLING && native==3)slot=0;
            if(g.curEvent==Event::DESIGNER_IN_SPIRE)slot=native<2?0:native<4?1:native-2;
            if(g.curEvent==Event::CURSED_TOME && g.info.eventData>0)slot=native-g.info.eventData-1;
            if(g.curEvent==Event::KNOWING_SKULL)slot=std::array<int,4>{1,2,0,3}[native];
            mapped.push_back({slot,choice});
        }
        std::sort(mapped.begin(),mapped.end(),[](const auto &a,const auto &b){return a.first<b.first;});
        o["liveChoices"]=J::array();J options=J::array();
        for(auto &[slot,choice]:mapped) {
            choice["liveAction"]={{"kind","choose"},{"choiceIndex",o["liveChoices"].size()+1}};
            o["liveChoices"].push_back(choice);options.push_back({{"index",slot},{"disabled",false}});
        }
        o["event"]={{"id",J(g.curEvent)},{"phase",eventPageForFixture(g)},{"options",options}};
    }
    if(g.screenState==ScreenState::CARD_SELECT && g.info.selectScreenType==CardSelectScreenType::OBTAIN) {
        J labels=J::array();
        for(int i=0;i<20;++i) {
            labels.push_back("offer"+std::to_string(i));
            o["liveChoices"][i]["uuid"]="library-"+std::to_string(i);
        }
        o["mcpState"]={{"screen_type","GRID"},{"ready_for_command",true},
            {"can_cancel",false},{"can_proceed",false},{"choice_list",labels}};
    }
    if(name=="designer_remove_upgrade") {
        o["details"]["afterSelect"]="designer_upgrade";o["details"]["event"]="Designer";
        o["details"]["eventPhase"]="DONE";o["details"]["eventOption"]="REMOVE_AND_UPGRADE";
    }
    return {{"boundary","ooc"},{"ooc",o},{"fixture",name}};
}
static std::array<int,7> cats(const GameContext &g,A a){std::array<int,7> r{};strategicCands(g,a,r[0],r[1],r[2],r[3],r[4],r[5],r[6]);return r;}
static void sameTokens(const TokState &a,const TokState &b){
    for(int i=0;i<42;++i)check(a.glob[i]==b.glob[i],"global "+std::to_string(i));
    check(a.nDk==b.nDk&&a.nRl==b.nRl&&a.nPt==b.nPt,"token sizes");
    for(int i=0;i<a.nDk;++i)for(int j=0;j<3;++j)check(a.dk[i][j]==b.dk[i][j],"deck tokens");
    for(int i=0;i<a.nRl;++i)for(int j=0;j<2;++j)check(a.rl[i][j]==b.rl[i][j],"relic tokens");
    for(int i=0;i<a.nPt;++i)for(int j=0;j<2;++j)check(a.pt[i][j]==b.pt[i][j],"potion tokens");
}
int main(int argc,char **argv){try{
    check(argc==2||argc==3,"model path [fixture output] required");
    auto model=std::make_unique<OocStrategicTokNet>();check(model->load(argv[1]),"model load");
    std::ofstream output;if(argc==3)output.open(argv[2]);
    // One fixed native initialization; no game rollout and no model mutation.
    GameContext base(CharacterClass::IRONCLAD,126700,0);
    base.boss=MonsterEncounter::HEXAGHOST;base.floorNum=7;base.gold=777;base.curHp=51;
    base.potionChance=10;base.cardRarityFactor=-2;base.curMapNodeX=-1;base.curMapNodeY=-1;
    base.potions[1]=Potion::FIRE_POTION;base.potionCount=1;
    base.relics.add({RelicId::GIRYA,2});base.relics.add({RelicId::SHOVEL,0});base.relics.add({RelicId::PEACE_PIPE,0});
    base.deck.obtain(base,Card(CardId::RITUAL_DAGGER));base.deck.cards[base.deck.size()-1].misc=23;
    base.deck.bottleCard(base.deck.size()-1,CardType::ATTACK);
    base.deck.obtain(base,Card(CardId::STRIKE_RED,1));
    PathHistory path;path.roomVisits={1,2,3,4,5,6,1,1,0,0};
    // Final-card skip and leave are one search choice, while the complete
    // captured primitive mapping remains validated (including both aliases).
    for (int variant = 0; variant < 4; ++variant) {
        auto source = base;
        source.screenState = ScreenState::REWARDS;
        source.info.rewardsContainer.clear();
        CardReward cards;
        for (auto id : {CardId::SEVER_SOUL, CardId::ANGER, CardId::FLEX}) cards.push_back(Card(id));
        source.info.rewardsContainer.addCardReward(cards);
        if (variant == 1) source.relics.add({RelicId::SINGING_BOWL, 0});
        if (variant == 2) source.info.rewardsContainer.addRelic(RelicId::ANCHOR);
        if (variant == 3) source.info.rewardsContainer.addCardReward(cards);
        auto wire = project(source, path, "final_card_boundary");
        for (auto &choice : wire["ooc"]["liveChoices"]) {
            const auto &native = choice["nativeAction"];
            if (variant != 0 && (native["kind"] == "skip"
                    || (native["kind"] == "card" && native["index"] == 5)))
                choice["liveAction"] = {{"kind", "skip"}};
        }
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire, live).ok, "final-card fixture import");
        OocAdapterOptions options;
        options.uniformPrior = true;
        options.checkpointLeaves = true;
        options.stopAtMapCheckpoint = true;
        const auto captured = advisor::liveOocPrimitiveBits(live);
        options.rootPrimitiveBits = std::set<std::uint32_t>(captured.begin(), captured.end());
        OocMctsDependencies deps;
        deps.policyAvailable = [] { return true; };
        deps.policyLogits = [](const GameContext &, const PathHistory &, const std::vector<A> &as) {
            return std::vector<double>(as.size(), 0.0);
        };
        deps.leafValue = [](const GameContext &, const PathHistory &) { return 0.5; };
        OocGameContextModel root(live.mctsRoot.state, live.mctsRoot.path, {}, options, deps);
        const auto actions = root.legalActions(0);
        check(actions.size() == captured.size() - (variant == 0 ? 1 : 0),
              "reward aliases collapsed outside final plain card group");
        std::vector<std::uint32_t> bits;
        std::mt19937_64 rng(380);
        for (const auto &action : actions) {
            bits.push_back(root.candidate(0, action.id).primitive.bits);
            if (variant == 0) {
                const auto child = root.sampleSuccessor(0, action.id, rng);
                check(root.state(child).screenState == ScreenState::MAP_SCREEN && root.isLeafBoundary(child),
                      "final card successor must immediately reach map checkpoint");
            }
        }
        advisor::validateLiveOocActionSet(live, bits, true);
        if (variant == 0) {
            check(actions.size() == 4, "three cards plus one skip expected");
            search::OocMctsConfig config;
            config.seed = 380;
            config.maxDepth = 1;
            const auto result = search::OocMctsPlanner(config).search(root, 0, 8);
            check(!result.aborted && result.rootActions.size() == 4 && result.selectedAction,
                  "final-card search must finish within one transition to the map boundary");
            auto rejects = [&](const advisor::LiveOocStateV1 &state, const auto &candidateBits, bool aliases) {
                bool rejected = false;
                try { advisor::validateLiveOocActionSet(state, candidateBits, aliases); }
                catch (const std::exception &) { rejected = true; }
                check(rejected, "invalid reward mapping accepted");
            };
            rejects(live, bits, false);
            auto missing = bits;
            missing.erase(std::find_if(missing.begin(), missing.end(), [](auto b) {
                const A a(b); return a.getRewardsActionType() == RT::CARD && a.getIdx2() != 5;
            }));
            rejects(live, missing, true);
            auto mismatched = live;
            for (auto &choice : mismatched.ooc["liveChoices"])
                if (choice["nativeAction"]["kind"] == "skip") choice["liveAction"] = {{"kind", "proceed"}};
            rejects(mismatched, bits, true);
            auto duplicate = live;
            for (const auto &choice : live.ooc["liveChoices"])
                if (choice["nativeAction"]["kind"] == "skip") duplicate.ooc["liveChoices"].push_back(choice);
            rejects(duplicate, bits, true);
            for (const auto alias : {A(RT::CARD, 0, 5), A(RT::SKIP)}) {
                auto restricted = options;
                restricted.rootPrimitiveBits = std::set<std::uint32_t>{alias.bits};
                OocGameContextModel one(live.mctsRoot.state, live.mctsRoot.path, {}, restricted, deps);
                const auto choices = one.legalActions(0);
                check(choices.size() == 1 && one.candidate(0, choices[0].id).primitive.bits == alias.bits,
                      "root filtering must retain whichever skip alias is captured");
            }
        }
    }
    {
        auto source = base;
        source.screenState = ScreenState::REWARDS;
        source.info.rewardsContainer.clear();
        source.info.rewardsContainer.addGold(25);
        source.info.rewardsContainer.addGold(40);
        CardReward cards;
        cards.push_back(Card(CardId::BASH));
        source.info.rewardsContainer.addCardReward(cards);
        const auto wire = project(source, path, "forced_gold_pass_through");
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire, live).ok, "forced-gold fixture import");
        const auto action = advisor::forcedRewardGoldLiveAction(live);
        check(action.has_value(), "live reward gold was not recognized as forced");
        check(action->value("kind", std::string()) == "choose"
                && action->value("choiceIndex", 0) > 0,
            "forced-gold live action did not retain its captured lowering");

        auto afterFirst = wire;
        auto &choices = afterFirst["ooc"]["liveChoices"];
        const auto first = std::find_if(choices.begin(), choices.end(), [&](const auto &choice) {
            return choice.at("nativeAction").value("kind", std::string()) == "gold"
                && choice.at("liveAction") == *action;
        });
        check(first != choices.end(), "first forced gold choice missing from observation");
        choices.erase(first);
        afterFirst["ooc"]["details"]["gold"].erase(
            afterFirst["ooc"]["details"]["gold"].begin());
        advisor::LiveOocStateV1 secondLive;
        check(advisor::importLiveOocStateV1(afterFirst, secondLive).ok, "second gold fixture import");
        const auto secondAction = advisor::forcedRewardGoldLiveAction(secondLive);
        check(secondAction.has_value() && *secondAction != *action,
            "second observation did not select the other captured gold action");

        auto afterSecond = afterFirst;
        auto &remaining = afterSecond["ooc"]["liveChoices"];
        remaining.erase(std::remove_if(remaining.begin(), remaining.end(), [](const auto &choice) {
            return choice.at("nativeAction").value("kind", std::string()) == "gold";
        }), remaining.end());
        afterSecond["ooc"]["details"]["gold"] = nlohmann::json::array();
        advisor::LiveOocStateV1 noGold;
        check(advisor::importLiveOocStateV1(afterSecond, noGold).ok, "gold-removed fixture import");
        check(!advisor::forcedRewardGoldLiveAction(noGold).has_value(),
            "live gold pass-through persisted after all gold choices were removed");
        for (auto relic : {RelicId::BOTTLED_FLAME, RelicId::BOTTLED_LIGHTNING,
                           RelicId::BOTTLED_TORNADO}) {
            auto bottle = base;
            bottle.screenState = ScreenState::REWARDS;
            bottle.info.rewardsContainer.clear();
            bottle.info.rewardsContainer.addRelic(relic);
            advisor::LiveOocStateV1 liveBottle;
            check(advisor::importLiveOocStateV1(project(bottle, path, "bottle_take_or_skip"), liveBottle).ok,
                "Bottled relic fixture import");
            check(!advisor::forcedRewardGoldLiveAction(liveBottle),
                "Bottled relic triggered forced reward pass-through");
            bool canTakeBottle = false, canSkipBottle = false;
            for (const auto &choice : liveBottle.ooc.at("liveChoices")) {
                const auto kind = choice.at("nativeAction").value("kind", std::string());
                canTakeBottle |= kind == "relic";
                canSkipBottle |= kind == "skip";
            }
            check(canTakeBottle && canSkipBottle,
                "Bottled relic live choice must retain take and skip");
        }
    }
    // Captured Neow choices, including reordered offers and nontrivial live indices.
    for (bool reverse : {false, true}) {
        auto source=base; source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=Event::NEOW;
        auto wire=project(source,path,"neow_two_offers");
        auto &offers=wire["ooc"]["details"]["neow"];
        offers=J::array({{{"bonus","THREE_ENEMY_KILL"},{"drawback","NONE"}},
                         {{"bonus","TEN_PERCENT_HP_BONUS"},{"drawback","NONE"}}});
        if(reverse) std::swap(offers[0],offers[1]);
        wire["ooc"]["liveChoices"]=J::array({
            {{"nativeAction",{{"kind","option"},{"index",0}}},{"liveAction",{{"kind","choose"},{"choiceIndex",7}}}},
            {{"nativeAction",{{"kind","option"},{"index",1}}},{"liveAction",{{"kind","choose"},{"choiceIndex",3}}}}});
        advisor::LiveOocStateV1 live;
        const auto imported=advisor::importLiveOocStateV1(wire,live);
        check(imported.ok,"two-offer Neow import: "+imported.message);
        const auto actions=v4CandidateActions(live.projected);
        check(actions.size()==2 && actions[0].getIdx1()==0 && actions[1].getIdx1()==1,
              "two Neow offers must produce exactly two ordered actions");
        check(live.projected.info.neowRewards[2].r==Neow::Bonus::INVALID
            && live.mctsRoot.state.info.neowRewards[3].r==Neow::Bonus::INVALID,
            "missing Neow slots must not contain fabricated offers");
        std::vector<std::uint32_t> bits;
        for(int i=0;i<2;++i) {
            bits.push_back(actions[i].bits);
            check(J(live.mctsRoot.state.info.neowRewards[i].r)==offers[i]["bonus"],"Neow offer order/identity");
            check(advisor::lowerLiveOocAction(live,actions[i].bits)["choiceIndex"]==(i==0?7:3),
                  "Neow live mapping lost captured index");
            auto after=live.mctsRoot.state;
            actions[i].execute(after);
            const bool lament=offers[i]["bonus"]=="THREE_ENEMY_KILL";
            check(after.screenState==ScreenState::MAP_SCREEN
                && (lament ? after.hasRelic(RelicId::NEOWS_LAMENT)
                           : after.maxHp==live.mctsRoot.state.maxHp+live.mctsRoot.state.maxHp/10),
                "Neow transition applied wrong offer");
        }
        advisor::validateLiveOocActionSet(live,bits);
        OocMctsDependencies deps;
        deps.policyAvailable=[] {return true;};
        deps.policyLogits=[](const GameContext &,const PathHistory &,const std::vector<A> &as) {
            return std::vector<double>(as.size(),0.0);
        };
        deps.leafValue=[](const GameContext &g,const PathHistory &) {
            return g.hasRelic(RelicId::NEOWS_LAMENT) ? 0.75 : 0.25;
        };
        OocAdapterOptions options; options.checkpointLeaves=true; options.stopAtMapCheckpoint=true;
        OocGameContextModel root(live.mctsRoot.state,live.mctsRoot.path,{},options,deps);
        sts::search::OocMctsConfig config;config.seed=31;
        const auto result=sts::search::OocMctsPlanner(config).search(root,0,32);
        check(!result.aborted && result.rootActions.size()==2 && result.selectedAction,
              "two-offer root must run ordinary OOC MCTS");
        const auto selected=root.candidate(0,*result.selectedAction).primitive;
        check(selected.getIdx1()==(reverse?1:0),"MCTS must value the actual captured Lament offer");
        for(const auto &a:result.rootActions) check(a.visits>0,"both real Neow offers must be searched");
        for(int count : {0,1,3,5}) {
            auto invalid=wire;invalid["ooc"]["details"]["neow"]=J::array();
            for(int i=0;i<count;++i) invalid["ooc"]["details"]["neow"].push_back(offers[0]);
            advisor::LiveOocStateV1 rejected;
            check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"invalid Neow count accepted");
        }
    }
    for(const std::string phase:{"0","1","99","RESULT"}) {
        const bool goop=phase=="RESULT";
        auto source=base;source.screenState=ScreenState::EVENT_SCREEN;
        source.curEvent=goop?Event::WORLD_OF_GOOP:Event::NEOW;
        auto wire=project(source,path,"mechanical_neow");
        wire["ooc"]["details"].erase("neow");
        wire["ooc"]["details"].erase("goldLoss");
        wire["ooc"]["details"]["mechanicalTransition"]=goop || phase=="99"?"event_leave":"neow_intro";
        wire["ooc"]["event"]={{"id",goop?"World of Goop":"Neow"},{"phase",phase},
            {"options",J::array({{{"index",0},{"disabled",false}}})}};
        wire["ooc"]["liveChoices"]=J::array({{
            {"nativeAction",{{"kind","option"},{"index",0},{"group",0}}},
            {"liveAction",{{"kind","choose"},{"choiceIndex",1}}}}});
        advisor::LiveOocStateV1 live;
        const auto imported=advisor::importLiveOocStateV1(wire,live);
        check(imported.ok && live.mechanicalEventTransition && !live.mctsRoot.supported,
                "Neow mechanical transition import: "+imported.message);
        check(advisor::lowerLiveOocAction(live,A(0).bits)==wire["ooc"]["liveChoices"][0]["liveAction"],
                "Neow mechanical click lowering changed");
        const auto rejects=[&](J invalid) {
            advisor::LiveOocStateV1 rejected;
            check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"unqualified mechanical transition accepted");
        };
        auto invalid=wire;invalid["ooc"]["event"]["phase"]="2";rejects(invalid);
        invalid=wire;invalid["ooc"]["event"]["phase"]="3";rejects(invalid);
        invalid=wire;invalid["ooc"]["event"]["id"]="Big Fish";rejects(invalid);
        invalid=wire;invalid["ooc"]["details"]["mechanicalTransition"]="other";rejects(invalid);
        invalid=wire;invalid["ooc"]["event"]["options"][0]["disabled"]=true;rejects(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"].push_back(invalid["ooc"]["liveChoices"][0]);rejects(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"][0]["liveAction"]["choiceIndex"]=2;rejects(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"][0]["nativeAction"]["index"]=1;rejects(invalid);
    }
    for(const auto event:{Event::OMINOUS_FORGE,Event::ANCIENT_WRITING}) {
        auto source=base;source.screenState=ScreenState::EVENT_SCREEN;source.curEvent=event;
        source.info.phase=0;source.info.eventData=0;
        auto wire=project(source,path,"verified_simple_event");
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire,live).ok,"forge/writing initial import");
        const auto reject=[&](J invalid) {
            advisor::LiveOocStateV1 rejected;
            check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"forge/writing malformed state accepted");
        };
        auto invalid=wire;invalid["ooc"]["event"]["phase"]="1";reject(invalid);
        invalid=wire;invalid["ooc"]["event"]["id"]="Big Fish";reject(invalid);
        invalid=wire;invalid["ooc"]["event"]["options"][0]["disabled"]=true;reject(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"][0]["nativeAction"]["index"]=2;reject(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"][0]["liveAction"]["choiceIndex"]=2;reject(invalid);
        wire["ooc"]["details"]["mechanicalTransition"]="event_leave";
        wire["ooc"]["event"]["phase"]=event==Event::OMINOUS_FORGE?"2":"COMPLETE";
        wire["ooc"]["event"]["options"]=J::array({{{"index",0},{"disabled",false}}});
        wire["ooc"]["liveChoices"]=J::array({{
            {"nativeAction",{{"kind","option"},{"index",0},{"group",0}}},
            {"liveAction",{{"kind","choose"},{"choiceIndex",1}}}}});
        check(advisor::importLiveOocStateV1(wire,live).ok && live.mechanicalEventTransition,
                "forge/writing result did not qualify mechanical Leave");
        invalid=wire;invalid["ooc"]["event"]["phase"]="1";reject(invalid);
        invalid=wire;invalid["ooc"]["event"]["options"].push_back({{"index",1},{"disabled",false}});reject(invalid);
        wire["fixture"]=event==Event::OMINOUS_FORGE?"event_forge_leave":"event_writing_leave";
        if(output.is_open())output<<wire.dump()<<'\n';
    }
    {
        auto source=base;source.screenState=ScreenState::EVENT_SCREEN;source.curEvent=Event::OMINOUS_FORGE;
        source.info.phase=0;source.info.eventData=0;
        for(const int idx:source.deck.getUpgradeableCardIdxs())source.deck.upgrade(idx);
        auto wire=project(source,path,"forge_without_upgrade");
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire,live).ok && wire["ooc"]["liveChoices"].size()==2
                && wire["ooc"]["liveChoices"][0]["nativeAction"]["index"]==1,
                "forge disabled upgrade shifted option occurrence");
        wire["ooc"]["event"]["options"][0]["index"]=0;
        wire["ooc"]["liveChoices"][0]["nativeAction"]["index"]=0;
        check(!advisor::importLiveOocStateV1(wire,live).ok,"forge enabled nonexistent upgrade");
    }
    for(const bool boss:{false,true}) {
        auto source=base;
        source.screenState=boss?ScreenState::MAP_SCREEN:ScreenState::CARD_SELECT;
        if(boss){source.curMapNodeX=3;source.curMapNodeY=14;}
        else source.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        auto wire=project(source,path,boss?"forced_boss_map":"forced_selector_confirmation");
        auto &o=wire["ooc"];
        o["details"]=boss?J{{"mechanicalTransition","boss_map"},{"bossNodeAvailable",true},{"nodeChoices",0}}
            :J{{"type","confirmation"},{"mechanicalTransition","selector_confirm"},
                {"isJustForConfirming",true},{"confirmScreenUp",false},{"confirm",true}};
        o["mcpState"]={{"screen_type",boss?"MAP":"GRID"},{"ready_for_command",true},
            {"can_proceed",!boss},{"can_cancel",false},{"choice_list",boss?J::array({"Boss"}):J::array()}};
        const J hint=boss?J{{"kind","choose"},{"choiceIndex",1}}:J{{"kind","proceed"}};
        o["liveChoices"]=J::array({{{"nativeAction",{{"kind","option"},{"index",0},{"group",0}}},{"liveAction",hint}}});
        // Neither history nor a value model is necessary for the sole click.
        o["publicState"]["combatHistoryComplete"]=false;
        o["publicState"]["questionHistoryComplete"]=false;
        o["publicState"]["seenRelicsComplete"]=false;
        advisor::LiveOocStateV1 live;
        const auto imported=advisor::importLiveOocStateV1(wire,live);
        check(imported.ok && live.forcedOocTransition && !live.mctsRoot.supported,
                "forced OOC import: "+imported.message);
        check(advisor::lowerLiveOocAction(live,A(0).bits)==hint,"forced OOC lowering changed");
        if(output)output<<wire.dump()<<'\n';
        const auto rejects=[&](J invalid) {
            advisor::LiveOocStateV1 rejected;
            check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"forged forced OOC transition accepted");
        };
        auto invalid=wire;invalid["ooc"]["mcpState"]["can_cancel"]=true;rejects(invalid);
        invalid=wire;invalid["ooc"]["mcpState"]["ready_for_command"]=false;rejects(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"].push_back(invalid["ooc"]["liveChoices"][0]);rejects(invalid);
        invalid=wire;invalid["ooc"]["liveChoices"][0]["liveAction"]={{"kind",boss?"proceed":"confirm"}};rejects(invalid);
        if(boss) {
            invalid=wire;invalid["ooc"]["publicState"]["map"]["y"]=13;rejects(invalid);
            invalid=wire;invalid["ooc"]["publicState"]["act"]=4;rejects(invalid);
            invalid=wire;invalid["ooc"]["details"]["bossNodeAvailable"]=false;rejects(invalid);
            invalid=wire;invalid["ooc"]["details"]["nodeChoices"]=1;rejects(invalid);
        } else {
            invalid=wire;invalid["ooc"]["details"]["confirmScreenUp"]=true;rejects(invalid);
            invalid=wire;invalid["ooc"]["details"]["isJustForConfirming"]=false;rejects(invalid);
            invalid=wire;invalid["ooc"]["mcpState"]["choice_list"]=J::array({"Strike"});rejects(invalid);
            // MCP omits choice_list entirely when Choose is unavailable.
            auto absent=wire;absent["ooc"]["mcpState"].erase("choice_list");
            check(advisor::importLiveOocStateV1(absent,live).ok,"confirmation without Choose command rejected");
        }
    }
    std::vector<std::pair<std::string,GameContext>> fixtures;
    auto add=[&](std::string n,GameContext g){fixtures.emplace_back(n,g);};
    auto g=base;g.screenState=ScreenState::MAP_SCREEN;add("map_multiple_children",g);
    g=base;g.screenState=ScreenState::REST_ROOM;add("rest_smith_lift_dig_remove_key",g);
    g.blueKey=g.greenKey=g.redKey=true;add("rest_keys_collected",g);
    g=base;g.screenState=ScreenState::TREASURE_ROOM;g.info.chestSize=ChestSize::SMALL;add("treasure_open_leave",g);
    for(int size=0;size<3;++size) {
        auto source=g;source.info.chestSize=static_cast<ChestSize>(size);
        const auto wire=project(source,path,"public_chest_size");
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire,live).ok && live.hiddenTreasureContents
                && live.mctsRoot.supported
                && live.mctsRoot.state.info.chestSize==source.info.chestSize,
                "public chest size did not reach sampled root");
        for(const auto &field:{"chestType","chestSize","opened"}) {
            auto missing=wire;missing["ooc"]["details"].erase(field);
            check(!advisor::importLiveOocStateV1(missing,live).ok,"missing chest field accepted");
        }
        for(const auto &field:{"haveGold","tier"}) {
            auto leaked=wire;leaked["ooc"]["details"][field]=0;
            check(!advisor::importLiveOocStateV1(leaked,live).ok,"hidden chest field accepted");
        }
        auto mismatch=wire;mismatch["ooc"]["details"]["chestSize"]=(size+1)%3;
        check(!advisor::importLiveOocStateV1(mismatch,live).ok,"mismatched chest size accepted");
    }
    g=base;g.screenState=ScreenState::REWARDS;g.info.rewardsContainer.clear();
    CardReward cards;cards.push_back(Card(CardId::STRIKE_RED));cards.push_back(Card(CardId::STRIKE_RED));cards.push_back(Card(CardId::BASH,1));
    g.info.rewardsContainer.addCardReward(cards);add("card_reward_duplicate_take_skip",g);
    g.info.rewardsContainer.addCardReward(cards);add("multiple_card_groups",g);
    g.info.rewardsContainer.addGold(31);g.info.rewardsContainer.addRelic(RelicId::ANCHOR);
    g.info.rewardsContainer.addPotion(Potion::DEXTERITY_POTION);g.info.rewardsContainer.sapphireKey=true;add("mixed_combat_rewards_key",g);
    g.info.rewardsContainer.clear();g.info.rewardsContainer.addGold(20);add("rewards_without_cards",g);
    g=base;g.screenState=ScreenState::SHOP_ROOM;std::fill(std::begin(g.info.shop.prices),std::end(g.info.shop.prices),-1);
    g.info.shop.cards[0]=Card(CardId::BASH);g.info.shop.cardPrice(0)=51;g.info.shop.cards[1]=Card(CardId::BASH);g.info.shop.cardPrice(1)=51;
    g.info.shop.relics[0]=RelicId::ANCHOR;g.info.shop.relicPrice(0)=150;
    g.info.shop.potions[0]=Potion::FIRE_POTION;g.info.shop.potionPrice(0)=45;g.info.shop.removeCost=75;add("shop_all_purchases_duplicates_leave_remove",g);
    g.info.shop.relics[0]=RelicId::PRISMATIC_SHARD;g.info.shop.relicPrice(0)=150;
    add("shop_prismatic_shard_displayed_but_excluded",g);
    g=base;g.screenState=ScreenState::BOSS_RELIC_REWARDS;g.info.bossRelics[0]=RelicId::BLACK_BLOOD;g.info.bossRelics[1]=RelicId::COFFEE_DRIPPER;g.info.bossRelics[2]=RelicId::FUSION_HAMMER;add("boss_relic_take_skip",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);add("upgrade_duplicate_physical_cards",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::REMOVE,1);add("remove_selector",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::TRANSFORM,1);add("transform_selector",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::DUPLICATE,1);add("duplicate_selector",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::BONFIRE_SPIRITS,1);add("bonfire_selector",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::REMOVE,2);
    add("empty_cage_first_selector",g);g.chooseSelectCardScreenOption(0);add("empty_cage_last_selector",g);
    g=base;g.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,3);
    add("astrolabe_first_selector",g);g.chooseSelectCardScreenOption(0);
    add("astrolabe_second_selector",g);g.chooseSelectCardScreenOption(0);add("astrolabe_last_selector",g);
    for(const auto bottle:{RelicId::BOTTLED_FLAME,RelicId::BOTTLED_LIGHTNING,RelicId::BOTTLED_TORNADO}) {
        g=base;g.deck.removeBottle(CardType::ATTACK);g.deck.obtain(g,Card(CardId::INFLAME));
        g.obtainRelic(bottle);add("bottle_selector_"+std::to_string(static_cast<int>(bottle)),g);
    }
    g=base;g.screenState=ScreenState::EVENT_SCREEN;g.curEvent=Event::BIG_FISH;add("event_big_fish",g);
    g.curEvent=Event::LIVING_WALL;add("event_living_wall",g);
    g.curEvent=Event::THE_WOMAN_IN_BLUE;add("event_woman_in_blue",g);
    g.curEvent=Event::WORLD_OF_GOOP;g.info.goldLoss=33;add("event_world_of_goop",g);
    g.curEvent=Event::OMINOUS_FORGE;g.info.phase=0;g.info.eventData=0;add("event_ominous_forge",g);
    g.curEvent=Event::ANCIENT_WRITING;add("event_ancient_writing",g);
    g.curEvent=Event::THE_LIBRARY;g.info.hpAmount0=static_cast<int>(g.maxHp*(g.ascension>=15?0.2f:0.33f)+0.5f);
    add("event_library",g);
    { auto grid=g;grid.chooseEventOption(0);add("library_obtain_selector",grid); }
    g.curEvent=Event::HYPNOTIZING_COLORED_MUSHROOMS;add("event_mushrooms",g);
    g.curEvent=Event::MYSTERIOUS_SPHERE;add("event_sphere",g);
    for(const auto event:{Event::THE_CLERIC,Event::PLEADING_VAGRANT,Event::AUGMENTER,
            Event::FORGOTTEN_ALTAR,Event::GHOSTS,Event::GOLDEN_IDOL,Event::SCRAP_OOZE,
            Event::VAMPIRES,Event::THE_MOAI_HEAD,Event::SHINING_LIGHT,Event::WING_STATUE,
            Event::OLD_BEGGAR,Event::MASKED_BANDITS,Event::MINDBLOOM,Event::TOMB_OF_LORD_RED_MASK,
            Event::GOLDEN_SHRINE,Event::THE_SSSSSERPENT,Event::DEAD_ADVENTURER,Event::THE_NEST,
            Event::WINDING_HALLS,Event::FACE_TRADER,Event::DESIGNER_IN_SPIRE,Event::FALLING,
            Event::KNOWING_SKULL,Event::SENSORY_STONE,Event::NOTE_FOR_YOURSELF,Event::THE_JOUST,
            Event::COLOSSEUM,Event::CURSED_TOME,Event::WE_MEET_AGAIN}) {
        g=base;g.curEvent=event;g.setupEvent();
        if(event==Event::SCRAP_OOZE)g.info.hpAmount0=g.ascension>=15?5:3;
        if(event==Event::NOTE_FOR_YOURSELF)g.noteForYourselfCard=Card(CardId::BASH);
        add("vanilla_event_"+std::to_string(static_cast<int>(event)),g);
    }
    {
        auto curses=base;curses.obtainRelic(RelicId::OMAMORI);curses.obtainRelic(RelicId::DARKSTONE_PERIAPT);
        const int size=curses.deck.size(),hp=curses.maxHp;
        curses.deck.obtain(curses,Card(CardId::REGRET));
        check(curses.deck.size()==size && curses.maxHp==hp,"Omamori must suppress Darkstone on intercepted curse");
        curses.deck.obtain(curses,Card(CardId::REGRET),3);
        check(curses.deck.size()==size+2 && curses.maxHp==hp+12
                && curses.relics.getRelicValueRef(RelicId::OMAMORI)==0,
                "Darkstone must trigger only for actually obtained curses in a batch");
    }
    {
        auto zeroDamage=base;zeroDamage.obtainRelic(RelicId::TUNGSTEN_ROD);
        zeroDamage.regainControlAction=[](GameContext &gc){gc.screenState=ScreenState::MAP_SCREEN;};
        zeroDamage.maxHp=2;zeroDamage.curHp=1;zeroDamage.curEvent=Event::SHINING_LIGHT;zeroDamage.setupEvent();
        check(zeroDamage.info.hpAmount0==0,"low maximum HP Shining Light rounds damage to zero");
        zeroDamage.chooseEventOption(0);check(zeroDamage.curHp==1,"zero event damage must not heal with Tungsten");
        zeroDamage.playerLoseHp(0);zeroDamage.playerLoseHp(1);
        check(zeroDamage.curHp==1,"zero or fully reduced HP loss must not heal");
    }
    for(int phase=1;phase<=4;++phase) {
        g=base;g.curEvent=Event::CURSED_TOME;g.setupEvent();g.info.eventData=phase;
        add("cursed_tome_stage_"+std::to_string(phase),g);
    }
    for(int phase=0;phase<3;++phase) {
        g=base;g.curEvent=Event::DEAD_ADVENTURER;g.setupEvent();g.info.phase=phase;g.info.rewards={0,1,2};
        g.info.encounter=std::array<MonsterEncounter,3>{MonsterEncounter::THREE_SENTRIES,MonsterEncounter::GREMLIN_NOB,MonsterEncounter::LAGAVULIN_EVENT}[phase];
        add("dead_adventurer_public_"+std::to_string(phase),g);
    }
    g=base;g.curEvent=Event::COLOSSEUM;g.setupEvent();g.info.eventData=1;add("colosseum_post_combat",g);
    g=base;g.deck=Deck{};g.deck.obtain(g,Card(CardId::BASH));g.obtainRelic(RelicId::BOTTLED_FLAME);
    g.regainControlAction=[](GameContext &gc){gc.screenState=ScreenState::MAP_SCREEN;};
    g.chooseSelectCardScreenOption(0);g.curEvent=Event::FALLING;g.setupEvent();
    check(g.info.attackCardDeckIdx==-1 && A::getValidEventSelectBits(g)==8,"Falling must exclude bottled cards");
    add("falling_only_bottled",g);
    g=base;g.curEvent=Event::NLOTH;g.obtainRelic(RelicId::VAJRA);g.setupEvent();add("event_nloth",g);
    g=base;g.curEvent=Event::NOTE_FOR_YOURSELF;g.noteForYourselfCard=Card(CardId::REGRET);
    g.obtainRelic(RelicId::OMAMORI);g.obtainRelic(RelicId::DARKSTONE_PERIAPT);g.obtainRelic(RelicId::CERAMIC_FISH);
    g.setupEvent();add("note_stored_curse",g);
    g=base;g.gold=0;g.curEvent=Event::THE_CLERIC;g.setupEvent();g.info.hpAmount0=0;add("cleric_no_gold",g);
    g=base;g.curEvent=Event::SHINING_LIGHT;for(int i=0;i<g.deck.size();++i)if(g.deck.cards[i].canUpgrade())g.deck.upgrade(i);g.setupEvent();add("shining_no_targets",g);
    g=base;g.curEvent=Event::GOLDEN_IDOL;g.obtainRelic(RelicId::GOLDEN_IDOL);g.setupEvent();
    add("golden_idol_already_owned",g);g.chooseEventOption(0);add("golden_idol_trap",g);
    g=base;g.screenState=ScreenState::EVENT_SCREEN;g.curEvent=Event::DESIGNER_IN_SPIRE;
    g.chooseEventOption(4);add("designer_remove_upgrade",g);
    g=base;g.screenState=ScreenState::EVENT_SCREEN;g.curEvent=Event::NEOW;add("neow",g);
    g=base;g.deck=Deck{};g.deck.obtain(g,Card(CardId::BASH));g.screenState=ScreenState::EVENT_SCREEN;
    g.curEvent=Event::AUGMENTER;add("thin_deck_augmenter",g);
    g.curEvent=Event::DESIGNER_IN_SPIRE;g.info.upgradeOne=true;g.info.cleanUpIsRemoveCard=false;add("thin_deck_designer",g);
    g.deck.obtain(g,Card(CardId::ASCENDERS_BANE));add("untransformable_curse_designer",g);
    g=base;g.screenState=ScreenState::BOSS_RELIC_REWARDS;g.curMapNodeY=15;g.curMapNodeX=3;
    g.info.bossRelics[0]=RelicId::BLACK_BLOOD;g.info.bossRelics[1]=RelicId::COFFEE_DRIPPER;g.info.bossRelics[2]=RelicId::FUSION_HAMMER;
    add("boss_room_coordinate",g);
    g=base;g.deck=Deck{};g.deck.obtain(g,Card(CardId::SEARING_BLOW));g.screenState=ScreenState::REST_ROOM;
    add("unupgraded_searing_blow",g);
    g.deck.upgrade(0);
    check(g.deck.upgradeableCount==1 && g.deck.cards[0].canUpgrade(),"Searing Blow remains eligible after upgrade");
    add("upgraded_searing_blow",g);
    int passed=0;
    for(const auto &[name,source]:fixtures){
        const auto wire=project(source,path,name);advisor::LiveOocStateV1 live;const auto result=advisor::importLiveOocStateV1(wire,live);
        check(result.ok,name+": "+result.message);
        if(wire["ooc"]["details"].contains("eventContract")) {
            for(int defect=0;defect<3;++defect) {
                auto bad=wire;
                if(defect==0)bad["ooc"]["event"]["phase"]="FORGED";
                if(defect==1)bad["ooc"]["details"].erase("eventContract");
                if(defect==2)bad["ooc"]["liveChoices"][0]["nativeAction"]["index"]=7;
                advisor::LiveOocStateV1 rejected;
                check(!advisor::importLiveOocStateV1(bad,rejected).ok,name+" malformed event accepted");
            }
        }
        if(name=="event_mushrooms" || name=="event_sphere") {
            auto outcome=live.mctsRoot.state;outcome.chooseEventOption(1);
            check(outcome.gold==source.gold,name+" leave must not grant gold");
            if(name=="event_mushrooms")check(outcome.deck.size()==source.deck.size()+1
                    && outcome.deck.cards.back().id==CardId::PARASITE
                    && outcome.curHp==std::min(source.maxHp,source.curHp+source.maxHp/4),
                    "Mushrooms leave must heal then obtain Parasite");
        }
        if(source.curEvent==Event::DESIGNER_IN_SPIRE && source.screenState==ScreenState::EVENT_SCREEN) {
            auto upgraded=live.mctsRoot.state;upgraded.chooseEventOption(1);
            check(upgraded.gold==std::max(0,source.gold-(source.ascension>=15?50:40)),"Designer random upgrades must charge adjustment cost");
            if(source.deck.getTransformableCount(2)>=2) {
                auto transformed=live.mctsRoot.state;transformed.chooseEventOption(3);
                check(transformed.screenState==ScreenState::CARD_SELECT
                        && transformed.info.selectScreenType==CardSelectScreenType::TRANSFORM
                        && transformed.info.toSelectCount==2,"Designer transforms must await two public choices");
            }
        }
        if(name=="golden_idol_already_owned") {
            auto outcome=live.mctsRoot.state;outcome.chooseEventOption(0);
            check(outcome.hasRelic(RelicId::CIRCLET) && outcome.info.phase==1
                    && A::getValidEventSelectBits(outcome)==0b11100,"owned Golden Idol must offer Circlet then trap choices");
        }
        if(name=="note_stored_curse") {
            auto outcome=live.mctsRoot.state;outcome.chooseEventOption(0);
            check(outcome.deck.size()==source.deck.size()+1 && outcome.deck.cards.back().id==CardId::REGRET
                    && outcome.relics.getRelicValueRef(RelicId::OMAMORI)==2
                    && outcome.maxHp==source.maxHp+6 && outcome.gold==source.gold+9,
                    "Note stored curse must invoke relic hooks without Omamori interception");
        }
        if(name=="event_library") {
            auto healed=live.mctsRoot.state;healed.chooseEventOption(1);
            check(healed.curHp==std::min(source.maxHp,source.curHp+source.info.hpAmount0),"Library public heal transition");
            auto unknown=wire;unknown["ooc"]["publicState"]["rewardPityHistoryComplete"]=false;
            advisor::LiveOocStateV1 belief;
            check(advisor::importLiveOocStateV1(unknown,belief).ok && belief.hiddenEventRewardPity,
                    "Library unknown pity must reach public-belief policy");
            for(int defect=0;defect<3;++defect) {
                auto bad=wire;
                if(defect==0)bad["ooc"]["details"].erase("hpAmount0");
                if(defect==1)bad["ooc"]["details"]["hpAmount0"]=0;
                if(defect==2)bad["ooc"]["event"]["phase"]="1";
                check(!advisor::importLiveOocStateV1(bad,belief).ok,"Library malformed initial state accepted");
            }
        }
        if(name=="library_obtain_selector") {
            check(live.projected.deck.size()==source.deck.size(),"Library import mutated deck");
            auto obtained=live.mctsRoot.state;const auto offer=obtained.info.toSelectCards[7].card;
            obtained.chooseSelectCardScreenOption(7);
            check(obtained.deck.size()==source.deck.size()+1 && obtained.deck.cards.back()==offer,
                    "Library visible offer must be obtained after selection");
            auto eggSource=source;eggSource.relics.add({RelicId::TOXIC_EGG,0});
            int eggChoice=-1;
            for(int i=0;i<static_cast<int>(eggSource.info.toSelectCards.size());++i) {
                auto &c=eggSource.info.toSelectCards[i].card;c=eggSource.previewObtainCard(Card(c.id));
                if(c.getType()==CardType::SKILL)eggChoice=i;
            }
            check(eggChoice>=0,"Library Egg fixture requires a skill");
            advisor::LiveOocStateV1 eggLive;
            check(advisor::importLiveOocStateV1(project(eggSource,path,"library_egg"),eggLive).ok,
                    "Library legitimate Egg preview rejected");
            const auto eggCard=eggLive.mctsRoot.state.info.toSelectCards[eggChoice].card;
            eggLive.mctsRoot.state.chooseSelectCardScreenOption(eggChoice);
            check(eggCard.upgraded && eggLive.mctsRoot.state.deck.cards.back()==eggCard,
                    "Library Egg preview/obtain mismatch");
            for(const auto id:{CardId::BRUTALITY,CardId::COMBUST,CardId::SEARING_BLOW}) {
                auto supported=source;
                if(id==CardId::SEARING_BLOW)supported.relics.add({RelicId::MOLTEN_EGG,0});
                for(int i=1;i<static_cast<int>(supported.info.toSelectCards.size());++i)
                    if(supported.info.toSelectCards[i].card.id==id)
                        std::swap(supported.info.toSelectCards[0],supported.info.toSelectCards[i]);
                supported.info.toSelectCards[0]=SelectScreenCard(Card(id),-1);
                for(auto &offer:supported.info.toSelectCards)
                    offer.card=supported.previewObtainCard(Card(offer.card.id));
                advisor::LiveOocStateV1 imported;
                const auto valid=advisor::importLiveOocStateV1(project(supported,path,"library_red_offer"),imported);
                check(valid.ok,"Valid red Library offer rejected: "+valid.message);
                const auto offered=imported.mctsRoot.state.info.toSelectCards[0].card;
                imported.mctsRoot.state.chooseSelectCardScreenOption(0);
                check(imported.mctsRoot.state.deck.cards.back()==offered,"Library offer changed during obtain");
            }
            for(int defect=0;defect<5;++defect) {
                auto bad=wire;
                if(defect==0)bad["ooc"]["details"]["cards"][0]["deckIndex"]=0;
                if(defect==1)bad["ooc"]["details"]["event"]="Big Fish";
                if(defect==2)bad["ooc"]["mcpState"]["can_cancel"]=true;
                if(defect==3)bad["ooc"]["details"]["cards"][0]=bad["ooc"]["details"]["cards"][1];
                if(defect==4)bad["ooc"]["details"]["cards"][0]["card"]["upgraded"]=true;
                advisor::LiveOocStateV1 invalid;
                check(!advisor::importLiveOocStateV1(bad,invalid).ok,"Library malformed selector accepted");
            }
        }
        if(source.curEvent==Event::WORLD_OF_GOOP) {
            check(live.projected.info.goldLoss==33 && live.mctsRoot.state.info.goldLoss==33,
                    "World of Goop must preserve visible gold loss");
            for(int option:{0,1}) {
                auto expected=source,actual=live.mctsRoot.state;
                expected.regainControlAction=[](GameContext &gc){gc.screenState=ScreenState::MAP_SCREEN;};
                expected.chooseEventOption(option);actual.chooseEventOption(option);
                check(expected.gold==actual.gold && expected.curHp==actual.curHp
                        && expected.screenState==actual.screenState,"World of Goop transition mismatch");
            }
            const auto rejects=[&](J invalid) {
                advisor::LiveOocStateV1 rejected;
                check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"invalid World of Goop gold loss accepted");
            };
            auto invalid=wire;invalid["ooc"]["details"].erase("goldLoss");rejects(invalid);
            invalid=wire;invalid["ooc"]["details"]["goldLoss"]=source.gold+1;rejects(invalid);
            invalid=wire;invalid["ooc"]["details"]["goldLoss"]=-1;rejects(invalid);
        }
        if(name=="neow") {
            check(v4CandidateActions(live.projected).size()==4,"ordinary Neow must retain four offers");
            for(int i=0;i<4;++i) {
                check(live.projected.info.neowRewards[i].r==source.info.neowRewards[i].r
                    && live.projected.info.neowRewards[i].d==source.info.neowRewards[i].d
                    && live.mctsRoot.state.info.neowRewards[i].r==source.info.neowRewards[i].r,
                    "ordinary Neow identity/order changed");
                check(advisor::lowerLiveOocAction(live,A(i).bits)["choiceIndex"]==i+1,
                    "ordinary Neow live mapping changed");
            }
        }

        check(live.mctsRoot.state.monsterListOffset==0
                && live.mctsRoot.state.eliteMonsterListOffset==0,
                name+" empty public combat history must not borrow path-symbol counts");
        for(const auto &owned:source.relics.relics) for(const auto *pool:{&live.mctsRoot.state.commonRelicPool,
                &live.mctsRoot.state.uncommonRelicPool,&live.mctsRoot.state.rareRelicPool,
                &live.mctsRoot.state.shopRelicPool,&live.mctsRoot.state.bossRelicPool})
            check(std::find(pool->begin(),pool->end(),owned.id)==pool->end(),name+" acquired relic remained in support");
        const auto visibleRelicRemoved = [&](RelicId relic) {
            for (const auto *pool:{&live.mctsRoot.state.commonRelicPool,
                    &live.mctsRoot.state.uncommonRelicPool,&live.mctsRoot.state.rareRelicPool,
                    &live.mctsRoot.state.shopRelicPool,&live.mctsRoot.state.bossRelicPool})
                check(std::find(pool->begin(),pool->end(),relic)==pool->end(),
                      name+" visible relic remained in support");
        };
        if (source.screenState==ScreenState::SHOP_ROOM)
            for(int i=0;i<3;++i)if(source.info.shop.relicPrice(i)>=0)visibleRelicRemoved(source.info.shop.relics[i]);
        if (source.screenState==ScreenState::REWARDS)
            for(int i=0;i<source.info.rewardsContainer.relicCount;++i)
                visibleRelicRemoved(source.info.rewardsContainer.relics[i]);
        if (source.screenState==ScreenState::BOSS_RELIC_REWARDS)
            for(RelicId relic:source.info.bossRelics)visibleRelicRemoved(relic);
        auto publicSource=source;publicSource.potionChance=30;publicSource.cardRarityFactor=-18;
        sameTokens(buildTokStatePure(publicSource,path),buildTokStatePure(live.projected,live.path));
        check(source.deck.cardTypeCounts==live.projected.deck.cardTypeCounts,name+" deck type counts");
        check(source.deck.transformableCount==live.projected.deck.transformableCount,name+" transformable count");
        check(source.deck.upgradeableCount==live.projected.deck.upgradeableCount,name+" upgradeable count");
        for(int y=0;y<15;++y)for(int x=0;x<7;++x){const auto &a=source.map->nodes[y][x],&b=live.projected.map->nodes[y][x];
            check(a.room==b.room&&a.edgeCount==b.edgeCount,name+" map node");
            for(int i=0;i<a.edgeCount;++i)check(a.edges[i]==b.edges[i],name+" map edges");}
        const auto aa=v4CandidateActions(source),bb=v4CandidateActions(live.projected);check(aa.size()==bb.size(),name+" candidate size");
        for(std::size_t i=0;i<aa.size();++i){check(aa[i].bits==bb[i].bits,name+" candidate bits/order");check(cats(source,aa[i])==cats(live.projected,bb[i]),name+" strategicCands");
            int ta,ia,tb,ib;float ga,gb;tokEntity(source,aa[i],ta,ia,ga);tokEntity(live.projected,bb[i],tb,ib,gb);check(ta==tb&&ia==ib&&ga==gb,name+" tokEntity");}
        const auto sa=search::enumerateOocSemanticActions(source),sb=search::enumerateOocSemanticActions(live.projected);
        check(sa.supported==sb.supported&&sa.complete==sb.complete&&sa.actions.size()==sb.actions.size(),name+" semantic support");
        for(std::size_t i=0;i<sa.actions.size();++i){check(search::canonicalOocSemanticActionKey(sa.actions[i])==search::canonicalOocSemanticActionKey(sb.actions[i]),name+" semantic key");
            check(search::oocSemanticActionPayloadJson(sa.actions[i])==search::oocSemanticActionPayloadJson(sb.actions[i]),name+" semantic payload");}
        if(source.screenState==ScreenState::REWARDS) {
            // Exercise the exported fixture's MCTS mapping without a search.
            // V4 keeps both skip primitives, so V4 parity alone cannot detect
            // an incorrect distinct live click for equivalent skip aliases.
            const auto bindings=search::enumerateOocSemanticPrimitiveBindings(live.projected);
            check(bindings.supported && bindings.complete,name+" reward bindings incomplete");
            const auto captured=advisor::liveOocPrimitiveBits(live);
            const std::set<std::uint32_t> capturedBits(captured.begin(),captured.end());
            std::set<std::string> retained;
            std::vector<std::uint32_t> representativeBits;
            for(const auto &binding:bindings.bindings)
                if(capturedBits.count(binding.primitiveBits)
                        && retained.insert(search::canonicalOocMctsChoiceKey(binding.semantic,&live.projected)).second)
                    representativeBits.push_back(binding.primitiveBits);
            advisor::validateLiveOocActionSet(live,representativeBits,true);
        }
        auto qa=scoreLiveOocV4(publicSource,path,*model),qb=scoreLiveOocV4(live.projected,live.path,*model);
        check(qa.supported==qb.supported&&qa.reason==qb.reason,name+" score support");
        const bool v4Unsupported = name.rfind("unsupported_",0)==0
            || name=="rewards_without_cards" || (source.screenState==ScreenState::CARD_SELECT
                && source.info.selectScreenType!=CardSelectScreenType::UPGRADE);
        if(v4Unsupported)check(!qa.supported,name+" must be outside direct V4 support");else check(qa.supported,name+": "+qa.reason);
        check(qa.selectedIndex==qb.selectedIndex&&qa.candidates.size()==qb.candidates.size(),name+" argmax");
        std::vector<std::uint32_t> bits;
        for(std::size_t i=0;i<qa.candidates.size();++i){const auto &a=qa.candidates[i],&b=qb.candidates[i];
            check(a.semanticKey==b.semanticKey&&a.payload==b.payload&&a.primitiveBits==b.primitiveBits,name+" candidate identity");
            check(a.followUpPreview==b.followUpPreview,name+" follow-up preview parity");
            check(std::abs(a.q-b.q)<=1e-6,name+" Q parity");bits.push_back(a.primitiveBits);}
        if(qa.supported)advisor::validateLiveOocActionSet(live,bits);
        if(source.screenState==ScreenState::CARD_SELECT) {
            check(live.projected.info.toSelectCount==source.info.toSelectCount
                    && live.projected.info.haveSelectedCards.size()==source.info.haveSelectedCards.size(),
                    name+" selector progress lost");
            // Import must preserve both current choices and the eventual
            // deck mutation. Give the native and imported fixture identical
            // hypothetical transform streams; no live RNG is imported.
            auto expected=source,actual=live.mctsRoot.state;
            if(name!="designer_remove_upgrade")expected.regainControlAction=[](GameContext &gc){gc.screenState=ScreenState::MAP_SCREEN;};
            expected.cardRng=actual.cardRng=Random(900);
            expected.miscRng=actual.miscRng=Random(901);
            while(expected.screenState==ScreenState::CARD_SELECT) {
                const auto before=search::enumerateOocSemanticPrimitiveBindings(actual);
                check(before.supported && before.complete,name+" imported selector enumeration incomplete");
                expected.chooseSelectCardScreenOption(0);actual.chooseSelectCardScreenOption(0);
            }
            check(expected.screenState==actual.screenState && expected.deck.size()==actual.deck.size()
                    && expected.deck.bottleIdxs==actual.deck.bottleIdxs
                    && expected.maxHp==actual.maxHp && expected.curHp==actual.curHp,
                    name+" selector completion state differs");
            for(int i=0;i<expected.deck.size();++i)
                check(expected.deck.cards[i]==actual.deck.cards[i],name+" selector completion deck differs");
            const auto rejects=[&](J invalid) {
                advisor::LiveOocStateV1 rejected;
                check(!advisor::importLiveOocStateV1(invalid,rejected).ok,
                        name+" malformed selector accepted");
            };
            auto invalid=wire;invalid["ooc"]["details"]["cards"].push_back(invalid["ooc"]["details"]["cards"][0]);rejects(invalid);
            invalid=wire;invalid["ooc"]["details"]["completedPicks"]=source.info.toSelectCount;rejects(invalid);
            if(!source.info.haveSelectedCards.empty()) {
                invalid=wire;invalid["ooc"]["details"].erase("selectedCards");rejects(invalid);
                invalid=wire;invalid["ooc"]["details"]["cards"][0]=invalid["ooc"]["details"]["selectedCards"][0];rejects(invalid);
                invalid=wire;invalid["ooc"]["details"]["selectedCards"][0]["card"]["misc"]=123;rejects(invalid);
            }
            if(source.info.selectScreenType==CardSelectScreenType::BOTTLE) {
                invalid=wire;invalid["ooc"]["details"]["bottleType"]="curse";rejects(invalid);
                invalid=wire;invalid["ooc"]["details"]["bottleType"]=source.info.toSelectCards[0].card.getType()==CardType::ATTACK?"skill":"attack";rejects(invalid);
            }
        }
        if(output)output<<wire.dump()<<'\n';
        std::cout<<name<<" parity=PASS status="<<(qa.supported?"OK":"UNSUPPORTED")<<" candidates="<<qa.candidates.size()<<'\n';++passed;
    }
    {
        auto source = base;
        source.screenState = ScreenState::REWARDS;
        auto wire = project(source, path, "question_to_monster_history");
        auto &p = wire["ooc"]["publicState"];
        p["combatFloors"] = J::array({6});
        p["combatHistory"] = J::array({{{"floor",6},{"kind","NORMAL_QUEUE"},
            {"encounter","JAW_WORM"}}});
        p["pathHistory"] = J::array({"MONSTER", "MONSTER", "MONSTER", "MONSTER", "MONSTER", "EVENT"});
        advisor::LiveOocStateV1 live;
        const auto result = advisor::importLiveOocStateV1(wire, live);
        check(result.ok, "question-to-monster public combat history import: " + result.message);
        check(live.mctsRoot.state.monsterListOffset == 1
                && live.mctsRoot.state.eliteMonsterListOffset == 0,
                "question-to-monster must consume the normal encounter queue");
    }
    {
        auto source = base;
        source.screenState = ScreenState::REWARDS;
        source.act = 2;
        source.floorNum = 23;
        auto wire = project(source, path, "act_two_elite_and_question_monster");
        auto &p = wire["ooc"]["publicState"];
        p["currentActPathVisits"][static_cast<int>(Room::ELITE)] = 1;
        p["currentActPathVisits"][static_cast<int>(Room::EVENT)] = 1;
        p["pathVisits"][static_cast<int>(Room::EVENT)] = 8;
        p["combatFloors"] = J::array({20, 23});
        p["combatHistory"] = J::array({{{"floor",20},{"kind","NORMAL_QUEUE"}},
                                        {{"floor",23},{"kind","ELITE_QUEUE"}}});
        p["combatHistory"][0]["encounter"] = "JAW_WORM";
        p["combatHistory"][1]["encounter"] = "GREMLIN_NOB";
        p["questionHistoryComplete"] = true;
        p["questionOutcomes"] = J::array({{{"floor",20},{"outcome","MONSTER"}}});
        // Earlier act transitions mean path_taken[22] does not exist.
        p["pathHistory"] = J::array({"MONSTER", "EVENT", "ELITE"});
        advisor::LiveOocStateV1 live;
        const auto result = advisor::importLiveOocStateV1(wire, live);
        check(result.ok, "act-two public combat history import");
        check(live.mctsRoot.state.monsterListOffset == 1
                && live.mctsRoot.state.eliteMonsterListOffset == 1,
                "act-two elite and question-monster must consume separate queues");
        check(live.mctsRoot.currentActEventVisits == 1,
                "room belief must use current-act event visits, not whole-run path visits");
        check(live.mctsRoot.questionHistoryComplete && live.mctsRoot.state.monsterChance==0.1f
                && live.mctsRoot.state.shopChance==0.03f+0.03f
                && live.mctsRoot.state.treasureChance==0.02f+0.02f,
                "resolved question monster must reconstruct exact room counters");
    }
    {
        auto source=base;source.screenState=ScreenState::REST_ROOM;
        auto wire=project(source,path,"resolved_question_history");
        auto &p=wire["ooc"]["publicState"];
        p["questionHistoryComplete"]=true;
        p["currentActPathVisits"][static_cast<int>(Room::EVENT)]=4;
        p["questionOutcomes"]=J::array({{{"floor",2},{"outcome","EVENT"}},
            {{"floor",4},{"outcome","SHOP"}},{{"floor",6},{"outcome","TREASURE"}},
            {{"floor",7},{"outcome","EVENT"}}});
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire,live).ok && live.mctsRoot.questionHistoryComplete,
                "complete resolved question history rejected");
        check(live.mctsRoot.state.monsterChance==0.1f+0.1f+0.1f+0.1f+0.1f
                && live.mctsRoot.state.shopChance==0.03f+0.03f+0.03f
                && live.mctsRoot.state.treasureChance==0.02f+0.02f
                && live.mctsRoot.state.curRoom==Room::EVENT && live.mctsRoot.state.lastRoom==Room::TREASURE,
                "resolved question counters or room identities differ");
        auto tiny=wire;tiny["ooc"]["publicState"]["relics"].push_back({{"id",J(RelicId::TINY_CHEST)},{"data",0}});
        advisor::LiveOocStateV1 tinyLive;
        check(advisor::importLiveOocStateV1(tiny,tinyLive).ok && tinyLive.mctsRoot.questionHistoryComplete
                && tinyLive.mctsRoot.state.treasureChance==live.mctsRoot.state.treasureChance,
                "Tiny Chest resolved treasure was treated as ambiguous");
        auto juzu=wire;juzu["ooc"]["publicState"]["acquiredRelics"].push_back(J(RelicId::JUZU_BRACELET));
        advisor::LiveOocStateV1 ambiguous;
        check(advisor::importLiveOocStateV1(juzu,ambiguous).ok && !ambiguous.mctsRoot.supported
                && !ambiguous.mctsRoot.questionHistoryComplete
                && ambiguous.mctsRoot.reason=="PUBLIC_QUESTION_ROOM_HISTORY_UNQUALIFIED:Juzu_Bracelet",
                "formerly owned Juzu fabricated the hidden monster reset");
        auto timed=juzu;
        for(auto &entry:timed["ooc"]["publicState"]["questionOutcomes"])
            entry["juzuOwnedAtEntry"]=false;
        advisor::LiveOocStateV1 exact;
        check(advisor::importLiveOocStateV1(timed,exact).ok && exact.mctsRoot.supported
                && exact.mctsRoot.questionHistoryComplete && exact.mctsRoot.mapHistoryComplete
                && exact.mctsRoot.state.monsterChance==live.mctsRoot.state.monsterChance,
                "Juzu acquired after public events contaminated prior room chances");
        timed["ooc"]["publicState"]["questionOutcomes"][0]["juzuOwnedAtEntry"]=true;
        check(advisor::importLiveOocStateV1(timed,exact).ok && !exact.mctsRoot.supported,
                "later loss of Juzu erased an unresolved prior conversion");
        timed["ooc"]["publicState"]["questionOutcomes"][3]["outcome"]="MONSTER";
        check(advisor::importLiveOocStateV1(timed,exact).ok && exact.mctsRoot.supported
                && exact.mctsRoot.questionHistoryComplete && exact.mctsRoot.state.monsterChance==0.1f,
                "known monster reset failed to recover exact current room chances");
        timed["ooc"]["publicState"]["questionOutcomes"][3]["juzuOwnedAtEntry"]=true;
        check(!advisor::importLiveOocStateV1(timed,exact).ok,
                "Juzu-owned MONSTER contradiction accepted");
        timed=juzu;timed["ooc"]["publicState"]["questionOutcomes"][0]["juzuOwnedAtEntry"]="false";
        check(!advisor::importLiveOocStateV1(timed,exact).ok,"string Juzu ownership accepted");
        auto observed=juzu;
        for(auto &entry:observed["ooc"]["publicState"]["questionOutcomes"]) {
            entry["juzuOwnedAtEntry"]=true;entry["juzuConverted"]=false;
        }
        check(advisor::importLiveOocStateV1(observed,exact).ok && exact.mctsRoot.supported
                && exact.mctsRoot.state.monsterChance==live.mctsRoot.state.monsterChance,
                "observed no-flash Juzu events were treated as unknown conversions");
        observed["ooc"]["publicState"]["questionOutcomes"][3]["juzuConverted"]=true;
        check(advisor::importLiveOocStateV1(observed,exact).ok && exact.mctsRoot.supported
                && exact.mctsRoot.state.monsterChance==0.1f,
                "observed Juzu flash did not reset monster chance");
        observed["ooc"]["publicState"]["questionOutcomes"][0].erase("juzuConverted");
        check(advisor::importLiveOocStateV1(observed,exact).ok && exact.mctsRoot.supported,
                "later observed Juzu conversion failed to clear earlier ambiguity");
        for(int malformed=0;malformed<4;++malformed) {
            auto invalid=observed;auto &entry=invalid["ooc"]["publicState"]["questionOutcomes"][3];
            if(malformed==0)entry.erase("juzuOwnedAtEntry");
            if(malformed==1)entry["juzuOwnedAtEntry"]=false;
            if(malformed==2)entry["outcome"]="SHOP";
            if(malformed==3)entry["juzuConverted"]="true";
            check(!advisor::importLiveOocStateV1(invalid,exact).ok,"malformed observed Juzu conversion accepted");
        }
        auto posterior=juzu;
        posterior["ooc"]["publicState"]["questionRoomRules"]="vanilla_ordinary_v1";
        for(auto &entry:posterior["ooc"]["publicState"]["questionOutcomes"]) {
            entry["juzuOwnedAtEntry"]=true;entry["previousRoomWasShop"]=false;entry["tinyChestForced"]=false;
        }
        check(advisor::importLiveOocStateV1(posterior,exact).ok && exact.mctsRoot.supported
                && exact.mctsRoot.questionHistoryComplete && exact.mctsRoot.mapHistoryComplete
                && exact.mctsRoot.questionChancePosterior.size()>1,
                "qualified Juzu posterior was discarded as missing history");
        const auto distribution=exact.mctsRoot.questionChancePosterior;
        auto unknownTiny=posterior;unknownTiny["ooc"]["publicState"]["questionOutcomes"][0].erase("tinyChestForced");
        check(advisor::importLiveOocStateV1(unknownTiny,exact).ok && !exact.mctsRoot.supported,
                "unknown historical Tiny forcing guessed a prior");
        auto forced=posterior;forced["ooc"]["publicState"]["questionOutcomes"][2]["tinyChestForced"]=true;
        check(advisor::importLiveOocStateV1(forced,exact).ok && exact.mctsRoot.supported,
                "qualified forced Tiny treasure posterior rejected");
        forced["ooc"]["publicState"]["questionOutcomes"][0]["tinyChestForced"]=true;
        check(!advisor::importLiveOocStateV1(forced,exact).ok,"zero-likelihood Tiny EVENT accepted");
        auto impossible=posterior;impossible["ooc"]["publicState"]["questionOutcomes"][1]["previousRoomWasShop"]=true;
        check(!advisor::importLiveOocStateV1(impossible,exact).ok,"suppressed shop outcome accepted");
        auto hiddenChanged=posterior;hiddenChanged["observationHash"]="different-public-request-id";
        check(advisor::importLiveOocStateV1(hiddenChanged,exact).ok && exact.mctsRoot.questionChancePosterior==distribution,
                "posterior depended on request identity");
        const auto rejects=[&](J invalid) {
            advisor::LiveOocStateV1 rejected;
            check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"malformed question history accepted");
        };
        auto invalid=wire;invalid["ooc"]["publicState"]["questionOutcomes"].erase(0);rejects(invalid);
        invalid=wire;invalid["ooc"]["publicState"]["questionOutcomes"][1]["floor"]=2;rejects(invalid);
        invalid=wire;invalid["ooc"]["publicState"]["questionOutcomes"][3]["floor"]=8;rejects(invalid);
        invalid=wire;invalid["ooc"]["publicState"]["questionOutcomes"][0]["outcome"]="BOSS";rejects(invalid);
    }
    {
        auto source=base;source.screenState=ScreenState::REST_ROOM;
        source.relics.remove(RelicId::SHOVEL);
        auto wire=project(source,path,"known_boss_offers_do_not_qualify_global_history");
        auto &p=wire["ooc"]["publicState"];
        p["seenRelicsComplete"]=false;
        p["knownRelicOffers"]=J::array({J(RelicId::RUNIC_DOME),J(RelicId::BLACK_STAR)});
        advisor::LiveOocStateV1 recovered;
        check(advisor::importLiveOocStateV1(wire,recovered).ok && recovered.mctsRoot.supported
                && !recovered.mctsRoot.mapHistoryComplete,"boss subset promoted missing global offers");
        for(auto relic:{RelicId::RUNIC_DOME,RelicId::BLACK_STAR})
            check(std::find(recovered.mctsRoot.state.bossRelicPool.begin(),
                    recovered.mctsRoot.state.bossRelicPool.end(),relic)
                    ==recovered.mctsRoot.state.bossRelicPool.end(),"saved unselected boss offer remained eligible");
        source.screenState=ScreenState::MAP_SCREEN;
        wire=project(source,path,"known_boss_offers_keep_map_guard");
        wire["ooc"]["publicState"]["seenRelicsComplete"]=false;
        wire["ooc"]["publicState"]["knownRelicOffers"]=J::array({J(RelicId::RUNIC_DOME),J(RelicId::BLACK_STAR)});
        check(advisor::importLiveOocStateV1(wire,recovered).ok && !recovered.mctsRoot.supported
                && recovered.mctsRoot.reason=="PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED",
                "known boss subset bypassed missing shop stock gate");
    }
    {
        auto source = base;
        source.screenState = ScreenState::MAP_SCREEN;
        source.floorNum = 9;
        auto wire = project(source, path, "fixed_event_combat_does_not_consume_hallway_queue");
        auto &p = wire["ooc"]["publicState"];
        p["combatFloors"] = J::array({3, 5, 8});
        p["combatHistory"] = J::array({{{"floor",3},{"kind","FIXED_EVENT"}},
                                        {{"floor",5},{"kind","NORMAL_QUEUE"},{"encounter","JAW_WORM"}},
                                        {{"floor",8},{"kind","ELITE_QUEUE"},{"encounter","GREMLIN_NOB"}}});
        p["currentActPathVisits"][static_cast<int>(Room::ELITE)] = 1;
        advisor::LiveOocStateV1 live;
        check(advisor::importLiveOocStateV1(wire, live).ok, "fixed-event combat import");
        check(live.mctsRoot.state.monsterListOffset == 1
                && live.mctsRoot.state.eliteMonsterListOffset == 1,
              "fixed event fight must not consume either encounter queue");
        p["combatHistoryComplete"] = false;
        check(advisor::importLiveOocStateV1(wire, live).ok && !live.mctsRoot.supported
                && live.mctsRoot.reason == "PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED",
              "resumed incomplete combat history must fail closed");
        p["combatHistory"][1].erase("encounter");
        const auto incompleteMissingIdentity = advisor::importLiveOocStateV1(wire, live);
        check(incompleteMissingIdentity.ok && !live.mctsRoot.supported
                && live.mctsRoot.reason == "PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED",
              "incomplete queue identity must remain a clean unsupported boundary");
    }
    {
        auto source = base;
        source.screenState = ScreenState::MAP_SCREEN;
        auto wire = project(source, path, "active_winged_map_boundary");
        wire["ooc"]["publicState"]["relics"].push_back(
                {{"id", J(RelicId::WING_BOOTS)}, {"data", 0}, {"liveCounter", 1}});
        wire["ooc"]["publicState"]["acquiredRelics"].push_back(J(RelicId::WING_BOOTS));
        advisor::LiveOocStateV1 live;
        const auto imported = advisor::importLiveOocStateV1(wire, live);
        check(imported.ok && !live.mctsRoot.supported
                && live.mctsRoot.reason == "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active",
              "active Wing Boots MAP roots must fail closed");
    }
    {
        auto source=base;source.screenState=ScreenState::MAP_SCREEN;
        source.curMapNodeX=1;source.curMapNodeY=0;
        source.map=std::make_shared<Map>();
        for(int y=0;y<15;++y)for(int x=0;x<7;++x) {
            auto &n=source.map->nodes[y][x];n.x=x;n.y=y;n.room=Room::REST;
        }
        source.map->getNode(1,0).addEdge(2);
        source.map->getNode(2,1).addEdge(2);source.map->getNode(5,1).addEdge(2);
        source.relics.add({RelicId::WING_BOOTS,0});source.wingBootsCharges=1;
        auto wire=project(source,path,"opt_in_winged_map");
        auto &p=wire["ooc"]["publicState"];
        for(auto &r:p["relics"])if(r["id"]==J(RelicId::WING_BOOTS))r["liveCounter"]=1;
        p["questionHistoryComplete"]=true;p["questionOutcomes"]=J::array();
        auto &choices=wire["ooc"]["liveChoices"];
        std::reverse(choices.begin(),choices.end());
        for(int i=0;i<int(choices.size());++i)choices[i]["liveAction"]["choiceIndex"]=i+1;
        setenv("STS_LIVE_OOC_WING_BOOTS","1",1);
        advisor::LiveOocStateV1 live;
        const auto imported=advisor::importLiveOocStateV1(wire,live);
        check(imported.ok && live.mctsRoot.supported && live.mctsRoot.state.wingBootsCharges==1,
                "opt-in Wing Boots root did not import");
        const auto actions=v4CandidateActions(live.mctsRoot.state);
        check(actions.size()==2 && live.mctsRoot.state.mapMoveCost(5)==1,
                "opt-in Wing Boots candidate set lost jump");
        auto jump=live.mctsRoot.state;A(5).execute(jump);
        check(jump.wingBootsCharges==0 && jump.curMapNodeX==5 && jump.curMapNodeY==1,
                "imported Wing Boots jump did not consume final charge");
        std::vector<std::uint32_t> bits;for(const auto &a:actions)bits.push_back(a.bits);
        advisor::validateLiveOocActionSet(live,bits);
        check(advisor::lowerLiveOocAction(live,A(5).bits).at("choiceIndex")==1,
                "jump column was confused with reordered MCP occurrence");
        for(int mutation=0;mutation<3;++mutation) {
            auto invalid=wire;
            if(mutation==0)invalid["ooc"]["liveChoices"].erase(0);
            else if(mutation==1)invalid["ooc"]["liveChoices"].push_back(choices[0]);
            else {auto extra=choices[0];extra["nativeAction"]["index"]=4;extra["liveAction"]["choiceIndex"]=3;
                invalid["ooc"]["liveChoices"].push_back(extra);}
            advisor::LiveOocStateV1 rejected;bool failed=false;
            try {const auto status=advisor::importLiveOocStateV1(invalid,rejected);
                if(!status.ok)failed=true;else advisor::validateLiveOocActionSet(rejected,bits);
            }catch(const std::exception&){failed=true;}
            check(failed,"incomplete/duplicate/extra jump mapping accepted");
        }
        unsetenv("STS_LIVE_OOC_WING_BOOTS");
        if(output)output<<wire.dump()<<'\n';
    }
    {
        auto source=base;source.screenState=ScreenState::REWARDS;
        for(bool question:{false,true})for(bool seen:{false,true}) {
            auto wire=project(source,path,"map_history_prerequisites");
            auto &p=wire["ooc"]["publicState"];
            p["questionHistoryComplete"]=question;p["questionOutcomes"]=J::array();p["seenRelicsComplete"]=seen;
            advisor::LiveOocStateV1 live;
            check(advisor::importLiveOocStateV1(wire,live).ok && live.mctsRoot.supported
                    && live.mctsRoot.mapHistoryComplete==(question&&seen),"downstream map requires both histories");
            p["relics"].push_back({{"id",J(RelicId::WING_BOOTS)},{"data",0},{"liveCounter",2}});
            check(advisor::importLiveOocStateV1(wire,live).ok && live.mctsRoot.state.wingBootsCharges==2,
                    "transition root lost public Wing Boots charges");
            p["relics"].back()["liveCounter"]=-2;
            check(advisor::importLiveOocStateV1(wire,live).ok && live.projected.wingBootsCharges==0
                    && live.mctsRoot.state.wingBootsCharges==0,"spent Wing Boots sentinel rejected");
            for(int invalid:{-3,-1,4}) {
                p["relics"].back()["liveCounter"]=invalid;
                check(!advisor::importLiveOocStateV1(wire,live).ok,"invalid Wing Boots counter accepted");
            }
        }
    }
    {
        auto source = base;
        source.screenState = ScreenState::MAP_SCREEN;
        auto wire = project(source, path, "incomplete_seen_relic_map_history");
        wire["ooc"]["publicState"]["seenRelicsComplete"] = false;
        advisor::LiveOocStateV1 live;
        const auto result = advisor::importLiveOocStateV1(wire, live);
        check(result.ok && !live.mctsRoot.supported
                && live.mctsRoot.reason == "PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED",
            "MAP search must fail closed without prior offered-relic history");
    }
    {
        auto source = base;
        source.screenState = ScreenState::EVENT_SCREEN;
        source.curEvent = Event::BIG_FISH;
        auto wire = project(source, path, "incomplete_seen_relic_history");
        wire["ooc"]["publicState"]["seenRelicsComplete"] = false;
        advisor::LiveOocStateV1 live;
        const auto result = advisor::importLiveOocStateV1(wire, live);
        check(result.ok && !live.mctsRoot.supported
                && live.mctsRoot.reason == "PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED",
            "random relic event must fail closed without seen relic history");
    }
    {
        auto source=base;source.act=2;source.floorNum=23;source.screenState=ScreenState::REWARDS;
        auto wire=project(source,path,"colosseum_two_combat_history");auto &p=wire["ooc"]["publicState"];
        p["combatFloors"]=J::array({20,22,22});
        p["combatHistory"]=J::array({{{"floor",20},{"kind","NORMAL_QUEUE"},{"encounter","CHOSEN"}},
            {{"floor",22},{"kind","FIXED_EVENT"},{"encounter","COLOSSEUM_EVENT_SLAVERS"}},
            {{"floor",22},{"kind","FIXED_EVENT"},{"encounter","COLOSSEUM_EVENT_NOBS"}}});
        advisor::LiveOocStateV1 imported;const auto result=advisor::importLiveOocStateV1(wire,imported);
        check(result.ok && imported.mctsRoot.supported,"Colosseum same-floor history: "+result.message);
        check(imported.mctsRoot.state.monsterListOffset==1 && imported.mctsRoot.state.eliteMonsterListOffset==0,
                "both Colosseum combats must preserve encounter queue offsets");
        for(int defect=0;defect<8;++defect) {
            auto bad=wire;auto &history=bad["ooc"]["publicState"]["combatHistory"];
            if(defect==0)history[2]["kind"]="NORMAL_QUEUE";
            if(defect==1)history[2]["encounter"]="COLOSSEUM_EVENT_SLAVERS";
            if(defect==2)history[1]["encounter"]="GREMLIN_NOB";
            if(defect==3)bad["ooc"]["publicState"]["combatFloors"]=J::array({20,22});
            if(defect==4) {history.push_back(history[2]);bad["ooc"]["publicState"]["combatFloors"].push_back(22);}
            if(defect==5) {history=J::array({history[2]});bad["ooc"]["publicState"]["combatFloors"]=J::array({22});}
            if(defect==6)bad["ooc"]["publicState"]["act"]=1;
            if(defect==7)history[1]["kind"]="NORMAL_QUEUE";
            advisor::LiveOocStateV1 rejected;check(!advisor::importLiveOocStateV1(bad,rejected).ok,"forged same-floor combat history accepted");
        }
        if(output)output<<wire.dump()<<'\n';++passed;
    }
    for(const auto type:{CardSelectScreenType::UPGRADE,CardSelectScreenType::REMOVE,CardSelectScreenType::TRANSFORM,CardSelectScreenType::BONFIRE_SPIRITS}) {
        auto source=base;source.openCardSelectScreen(type,1);
        auto preview=project(source,path,"selector_preview_"+std::to_string(static_cast<int>(type)));
        auto &o=preview["ooc"];auto &d=o["details"];
        d["selectorPreview"]=true;d["previewDeckIndex"]=source.info.toSelectCards[0].deckIdx;
        d["confirmScreenUp"]=true;d["isJustForConfirming"]=false;d["confirm"]=true;
        o["mcpState"]={{"screen_type","GRID"},{"ready_for_command",true},{"can_cancel",true},{"can_proceed",true},{"choice_list",J::array()}};
        o["liveChoices"]=J::array();
        for(int i=0;i<2;++i)o["liveChoices"].push_back({{"nativeAction",{{"kind","option"},{"index",i},{"group",0}}},
            {"liveAction",{{"kind",i==0?"proceed":"cancel"}}}});
        advisor::LiveOocStateV1 imported;const auto result=advisor::importLiveOocStateV1(preview,imported);
        check(result.ok && imported.selectorPreview,"selector preview import: "+result.message);
        check(imported.selectorPreviewDeckIndex==source.info.toSelectCards[0].deckIdx
                && imported.projected.info.toSelectCards.size()==source.info.toSelectCards.size(),"selector preview original targets");
        for(int defect=0;defect<5;++defect) {
            auto bad=preview;
            if(defect==0)bad["ooc"]["details"]["cards"].erase(0);
            if(defect==1)bad["ooc"]["details"]["completedPicks"]=1;
            if(defect==2)bad["ooc"]["liveChoices"][1]["liveAction"]["kind"]="proceed";
            if(defect==3)bad["ooc"]["mcpState"]["can_cancel"]=false;
            if(defect==4)bad["ooc"]["liveChoices"][0]["liveAction"]["kind"]="confirm";
            advisor::LiveOocStateV1 rejected;check(!advisor::importLiveOocStateV1(bad,rejected).ok,"malformed selector preview accepted");
        }
        if(output)output<<preview.dump()<<'\n';++passed;
    }
    for(int variant=0;variant<3;++variant) {
        auto match=project(base,path,"match_public_"+std::to_string(variant));auto &o=match["ooc"];
        auto &d=o["details"];d["event"]=J(Event::MATCH_AND_KEEP);d.erase("neow");
        d["eventContract"]="vanilla_v1";d["eventData"]=5;d["publicMemoryComplete"]=true;d["board"]=J::array();
        o["event"]={{"id",J(Event::MATCH_AND_KEEP)},{"phase","PLAY"},{"options",J::array()}};
        o["liveChoices"]=J::array();
        for(int slot=0;slot<12;++slot) {
            const bool known=variant>0 && slot<2,face=variant==2 && slot==0;
            const auto uuid="match-"+std::to_string(slot);
            J entry={{"slot",slot},{"uuid",uuid},{"state",face?"face_up":known?"seen":"unseen"}};
            if(known)entry["card"]=cardWire(Card(CardId::BASH));d["board"].push_back(entry);
            if(face)continue;
            o["event"]["options"].push_back({{"index",slot},{"disabled",false}});
            o["liveChoices"].push_back({{"uuid",uuid},{"nativeAction",{{"kind","option"},{"index",slot},{"group",0}}},
                {"liveAction",{{"kind","choose"},{"choiceIndex",o["liveChoices"].size()+1}}}});
        }
        advisor::LiveOocStateV1 imported;const auto result=advisor::importLiveOocStateV1(match,imported);
        check(result.ok && imported.matchAndKeep,"public Match and Keep import: "+result.message);
        const int chosen=search::chooseMatchAndKeepSlot(imported.projected,[](const Card &){return true;});
        check(chosen==(variant==2?1:0),"public Match and Keep slot decision");
        for(int defect=0;defect<4;++defect) {
            auto bad=match;
            if(defect==0)bad["ooc"]["details"]["board"][11]["card"]=cardWire(Card(CardId::BASH));
            if(defect==1)bad["ooc"]["details"]["board"][11]["uuid"]="match-0";
            if(defect==2)bad["ooc"]["liveChoices"][0]["uuid"]="mismatch";
            if(defect==3)bad["ooc"]["event"]["phase"]="COMPLETE";
            advisor::LiveOocStateV1 rejected;check(!advisor::importLiveOocStateV1(bad,rejected).ok,"malformed Match and Keep accepted");
        }
        if(output)output<<match.dump()<<'\n';++passed;
    }
    {
        auto source=base;source.screenState=ScreenState::REWARDS;
        source.info.rewardsContainer.clear();source.info.rewardsContainer.addPotion(Potion::FRUIT_JUICE);
        source.potionCount=source.potionCapacity;
        for(int i=0;i<source.potionCapacity;++i)source.potions[i]=Potion::FIRE_POTION;
        auto full=project(source,path,"full_belt_potion_reward");
        advisor::LiveOocStateV1 live;const auto imported=advisor::importLiveOocStateV1(full,live);
        check(imported.ok,"full belt import: "+imported.message);
        std::vector<std::uint32_t> bits;
        for(const auto &binding:sts::search::enumerateOocSemanticPrimitiveBindings(live.mctsRoot.state).bindings)
            bits.push_back(binding.primitiveBits);
        advisor::validateLiveOocActionSet(live,bits);
        for(int slot=0;slot<source.potionCapacity;++slot)
            check(advisor::lowerLiveOocAction(live,0xc0000000u|static_cast<unsigned>(slot))
                ==J({{"kind","discard_potion"},{"potionSlot",slot+1}}),"discard slot lower mismatch");
        auto invalid=full;invalid["ooc"]["liveChoices"].back()["liveAction"]["potionSlot"]=1;
        advisor::LiveOocStateV1 rejected;
        check(!advisor::importLiveOocStateV1(invalid,rejected).ok,"discard slot mismatch accepted");
        if(output)output<<full.dump()<<'\n';++passed;
    }
    auto wire=project(base,path,"malformed"); // base is Neow
    const auto reject=[&](J w){advisor::LiveOocStateV1 live;check(!advisor::importLiveOocStateV1(w,live).ok,"malformed accepted");};
    auto bad=wire;bad["ooc"]["schemaVersion"]=2;reject(bad);
    bad=wire;bad["ooc"]["publicState"]["deck"][0]["id"]="UNKNOWN";reject(bad);
    bad=wire;bad["ooc"]["publicState"]["relics"][0]["id"]="UNKNOWN";reject(bad);
    bad=wire;bad["ooc"]["publicState"]["deck"][0]["id"]="Burn";reject(bad);
    bad=wire;bad["ooc"]["publicState"]["potions"][0]="UNKNOWN";reject(bad);
    bad=wire;bad["ooc"]["publicState"]["pathComplete"]=false;reject(bad);
    bad=wire;bad["ooc"]["publicState"]["map"]["nodes"][0]["edges"]={7};reject(bad);
    bad=wire;bad["ooc"]["publicState"].erase("currentActPathVisits");reject(bad);
    bad=wire;bad["ooc"]["publicState"]["map"]["nodes"][0]["edges"]={4294967296ULL};reject(bad);
    bad=wire;bad["ooc"]["publicState"]["map"]["x"]=18446744073709551615ULL;reject(bad);
    bad=wire;bad["ooc"]["publicState"]["map"]["nodes"].erase(0);reject(bad);
    bad=wire;for(int x=0;x<7;++x)bad["ooc"]["publicState"]["map"]["nodes"][x]["edges"]={3};reject(bad);
    advisor::LiveOocStateV1 live;check(advisor::importLiveOocStateV1(wire,live).ok,"baseline import");
    auto conditioned=wire;conditioned["ooc"]["publicState"]["priorEvents"]={"Big Fish"};
    conditioned["ooc"]["publicState"]["shopRemoveCount"]=3;
    advisor::LiveOocStateV1 conditionedLive;check(advisor::importLiveOocStateV1(conditioned,conditionedLive).ok,"history import");
    check(conditionedLive.mctsRoot.state.shopRemoveCount==3,"shop removal history not reconstructed");
    for(const auto *pool:{&conditionedLive.mctsRoot.state.eventList,&conditionedLive.mctsRoot.state.shrineList,
            &conditionedLive.mctsRoot.state.specialOneTimeEventList})
        check(std::find(pool->begin(),pool->end(),Event::BIG_FISH)==pool->end(),"prior event remained eligible");
    const auto first=v4CandidateActions(live.projected).front().bits;
    live.ooc["liveChoices"].push_back(live.ooc["liveChoices"][0]);
    bool failed=false;try{advisor::lowerLiveOocAction(live,first);}catch(...){failed=true;}check(failed,"duplicate lowering accepted");
    live.ooc["liveChoices"]=J::array();failed=false;try{advisor::lowerLiveOocAction(live,first);}catch(...){failed=true;}check(failed,"missing lowering accepted");
    std::cout<<"live_ooc_parity PASS fixtures="<<passed<<" globals=42 token/candidate/semantic/Q exact\n";
    return 0;
}catch(const std::exception &e){std::cerr<<"live_ooc_parity FAIL "<<e.what()<<'\n';return 1;}}
