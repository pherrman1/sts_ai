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
        case ScreenState::TREASURE_ROOM:screen="treasure";break;
        case ScreenState::BOSS_RELIC_REWARDS:screen="boss_relic";d["relics"]=J::array();for(auto r:g.info.bossRelics)d["relics"].push_back(J(r));break;
        case ScreenState::CARD_SELECT:screen="selector";d={{"type",g.info.selectScreenType==CardSelectScreenType::UPGRADE?"upgrade":
            g.info.selectScreenType==CardSelectScreenType::TRANSFORM?"transform":"remove"},
            {"requiredPicks",g.info.toSelectCount},{"completedPicks",g.info.haveSelectedCards.size()},{"cards",J::array()}};
            for(const auto &c:g.info.toSelectCards)d["cards"].push_back({{"deckIndex",c.deckIdx},{"card",cardWire(c.card)}});break;
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
        o["liveChoices"].push_back({{"nativeAction",native},{"liveAction",{{"kind","choose"},{"choiceIndex",ix++}}}});
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
    std::vector<std::pair<std::string,GameContext>> fixtures;
    auto add=[&](std::string n,GameContext g){fixtures.emplace_back(n,g);};
    auto g=base;g.screenState=ScreenState::MAP_SCREEN;add("map_multiple_children",g);
    g=base;g.screenState=ScreenState::REST_ROOM;add("rest_smith_lift_dig_remove_key",g);
    g.blueKey=g.greenKey=g.redKey=true;add("rest_keys_collected",g);
    g=base;g.screenState=ScreenState::TREASURE_ROOM;add("treasure_open_leave",g);
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
    g=base;g.screenState=ScreenState::EVENT_SCREEN;g.curEvent=Event::BIG_FISH;add("event_big_fish",g);
    g.curEvent=Event::LIVING_WALL;add("event_living_wall",g);
    g.curEvent=Event::THE_WOMAN_IN_BLUE;add("event_woman_in_blue",g);
    g.curEvent=Event::THE_LIBRARY;add("unsupported_library_reward_pity",g);
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
                || name=="unsupported_library_reward_pity"
                || name=="unsupported_mushrooms_reward_pity"
                || name=="unsupported_sphere_reward_pity") {
            const std::string expected = name=="unsupported_searing_blow_upgrade_history"
                ? "SEARING_BLOW_UPGRADE_HISTORY_UNQUALIFIED"
                : "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED";
            check(!result.ok && result.code=="UNSUPPORTED"
                && result.message==expected,name+" must fail closed before scoring");
            if(output)output<<wire.dump()<<'\n';
            std::cout<<name<<" parity=BOUNDARY_CONFIRMED status=UNSUPPORTED candidates=0\n";++passed;
            continue;
        }
        check(result.ok,name+": "+result.message);
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
        auto qa=scoreLiveOocV4(publicSource,path,*model),qb=scoreLiveOocV4(live.projected,live.path,*model);
        check(qa.supported==qb.supported&&qa.reason==qb.reason,name+" score support");
        const bool v4Unsupported = name.rfind("unsupported_",0)==0
            || name=="rewards_without_cards" || name=="remove_selector" || name=="transform_selector";
        if(v4Unsupported)check(!qa.supported,name+" must be outside direct V4 support");else check(qa.supported,name+": "+qa.reason);
        check(qa.selectedIndex==qb.selectedIndex&&qa.candidates.size()==qb.candidates.size(),name+" argmax");
        std::vector<std::uint32_t> bits;
        for(std::size_t i=0;i<qa.candidates.size();++i){const auto &a=qa.candidates[i],&b=qb.candidates[i];
            check(a.semanticKey==b.semanticKey&&a.payload==b.payload&&a.primitiveBits==b.primitiveBits,name+" candidate identity");
            check(a.followUpPreview==b.followUpPreview,name+" follow-up preview parity");
            check(std::abs(a.q-b.q)<=1e-6,name+" Q parity");bits.push_back(a.primitiveBits);}
        if(qa.supported)advisor::validateLiveOocActionSet(live,bits);
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
        p["questionOutcomes"] = J::array({"MONSTER"});
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
