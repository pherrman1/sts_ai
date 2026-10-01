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

using namespace sts;
using namespace one_combat;
using J = nlohmann::json;
using A = search::GameAction;
using RT = A::RewardsActionType;
static void check(bool b,const std::string &why){if(!b)throw std::runtime_error(why);}
static J cardWire(const Card &c){return {{"id",J(c.id)},{"upgraded",c.isUpgraded()},{"misc",c.misc}};}
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
    if(g.screenState==ScreenState::CARD_SELECT && g.info.selectScreenType==CardSelectScreenType::OBTAIN) {
        J labels=J::array();
        for(int i=0;i<20;++i) {
            labels.push_back("offer"+std::to_string(i));
            o["liveChoices"][i]["uuid"]="library-"+std::to_string(i);
        }
        o["mcpState"]={{"screen_type","GRID"},{"ready_for_command",true},
            {"can_cancel",false},{"can_proceed",false},{"choice_list",labels}};
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
        const J hint=boss?J{{"kind","choose"},{"choiceIndex",1}}:J{{"kind","confirm"}};
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
        invalid=wire;invalid["ooc"]["liveChoices"][0]["liveAction"]={{"kind","proceed"}};rejects(invalid);
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
    g.curEvent=Event::HYPNOTIZING_COLORED_MUSHROOMS;add("unsupported_mushrooms_reward_pity",g);
    g.curEvent=Event::MYSTERIOUS_SPHERE;add("unsupported_sphere_reward_pity",g);
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
    check(g.deck.upgradeableCount==0 && g.deck.cards[0].canUpgrade(),"Searing Blow native history fixture");
    auto recomputed=g;recomputed.deck.upgradeableCount=1;
    const auto nativeSmith=v4CandidateActions(g),recomputedSmith=v4CandidateActions(recomputed);
    check(nativeSmith.size()+1==recomputedSmith.size(),"Searing Blow history must change campfire candidates");
    add("unsupported_searing_blow_upgrade_history",g);
    int passed=0;
    for(const auto &[name,source]:fixtures){
        const auto wire=project(source,path,name);advisor::LiveOocStateV1 live;const auto result=advisor::importLiveOocStateV1(wire,live);
        if(name=="unsupported_searing_blow_upgrade_history"
                || name=="unsupported_mushrooms_reward_pity"
                || name=="unsupported_sphere_reward_pity") {
            const std::string expected = name=="unsupported_searing_blow_upgrade_history"
                ? "SEARING_BLOW_UPGRADE_HISTORY_UNQUALIFIED"
                : "NATIVE_EVENT_TRANSITION_UNQUALIFIED";
            check(!result.ok && result.code=="UNSUPPORTED"
                && result.message==expected,name+" must fail closed before scoring");
            if(output)output<<wire.dump()<<'\n';
            std::cout<<name<<" parity=BOUNDARY_CONFIRMED status=UNSUPPORTED candidates=0\n";++passed;
            continue;
        }
        check(result.ok,name+": "+result.message);
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
                auto unsupported=source;
                if(id==CardId::SEARING_BLOW)unsupported.relics.add({RelicId::MOLTEN_EGG,0});
                unsupported.info.toSelectCards[0]=SelectScreenCard(unsupported.previewObtainCard(Card(id)),-1);
                advisor::LiveOocStateV1 rejected;
                const auto result=advisor::importLiveOocStateV1(project(unsupported,path,"library_unqualified"),rejected);
                check(!result.ok && result.code=="UNSUPPORTED" && result.message==(id==CardId::SEARING_BLOW
                        ? "SEARING_BLOW_UPGRADE_HISTORY_UNQUALIFIED":"LIBRARY_NATIVE_CARD_COLOR_UNQUALIFIED"),
                        "Valid vanilla Library offer must report explicit unsupported boundary");
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
            expected.regainControlAction=[](GameContext &gc){gc.screenState=ScreenState::MAP_SCREEN;};
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
