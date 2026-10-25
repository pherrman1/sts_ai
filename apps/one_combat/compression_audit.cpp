// Offline public-input audit. Reconstructed later states are used only for
// semantic enumeration and prior inference, never for transitions or values.
#include "compression_audit.h"
#include "heart1_policy.h"
#include "sim/search/GameAction.h"
#include <fstream>
#include <stdexcept>
using namespace sts;
namespace one_combat {
namespace {
int burden(const Card &c) {
    return c.getType() != CardType::POWER && !doesCardExhaust(c.id, c.upgraded)
        && c.id != CardId::ASCENDERS_BANE && c.id != CardId::DAZED
        && c.id != CardId::VOID && c.id != CardId::CLUMSY;
}
GameContext publicReward(const nlohmann::json &row) {
    const auto r = heart1::recordFromJson(row.at("record"));
    GameContext gc(CharacterClass::IRONCLAD, row.at("seed").get<std::uint64_t>(), 20);
    gc.act = row.at("act");
    gc.map = std::make_shared<Map>(Map::fromSeed(gc.seed, 20, gc.act, true));
    gc.screenState = ScreenState::REWARDS;
    gc.curEvent = Event::INVALID;
    gc.curHp = r.fixedObservation.at(0); gc.maxHp = r.fixedObservation.at(1);
    gc.gold = r.fixedObservation.at(2); gc.floorNum = r.fixedObservation.at(3);
    const MonsterEncounter bosses[] = {MonsterEncounter::SLIME_BOSS, MonsterEncounter::HEXAGHOST,
        MonsterEncounter::THE_GUARDIAN, MonsterEncounter::CHAMP, MonsterEncounter::AUTOMATON,
        MonsterEncounter::COLLECTOR, MonsterEncounter::TIME_EATER, MonsterEncounter::DONU_AND_DECA,
        MonsterEncounter::AWAKENED_ONE, MonsterEncounter::THE_HEART};
    gc.boss = bosses[r.fixedObservation.at(4)];
    gc.info.toSelectCount = r.fixedObservation.at(5);
    gc.info.selectScreenType = static_cast<CardSelectScreenType>(r.selectScreenType);
    gc.redKey = r.fixedObservation.at(7); gc.greenKey = r.fixedObservation.at(8);
    gc.blueKey = r.fixedObservation.at(9); gc.keysEnabled = true;
    gc.curMapNodeX = r.mapX; gc.curMapNodeY = r.mapY;
    gc.deck = {};
    for (std::size_t i=0; i<r.deckCards.size(); ++i) {
        Card c(static_cast<CardId>(r.deckCards[i]), r.deckUpgrades.at(i));
        // No misc-bearing card occurs in these retained cases.
        if (c.id == CardId::RITUAL_DAGGER || c.id == CardId::GENETIC_ALGORITHM)
            throw std::runtime_error("audit: missing historical card misc");
        gc.deck.obtainRaw(c);
    }
    gc.relics = {};
    for (std::size_t i=0;i<r.relics.size();++i)
        gc.relics.add({static_cast<RelicId>(r.relics[i]),r.relicCounters.at(i)});
    gc.potionCount=0;gc.potionCapacity=r.potions.size();
    for (std::size_t i=0;i<r.potions.size();++i) {
        gc.potions[i]=static_cast<Potion>(r.potions[i]);
        if(gc.potions[i]!=Potion::EMPTY_POTION_SLOT) ++gc.potionCount;
    }
    auto &rewards=gc.info.rewardsContainer;rewards={};
    CardReward cards;
    for(std::size_t i=0;i<r.offeredCards.size();++i)
        cards.push_back(Card(static_cast<CardId>(r.offeredCards[i]),r.offeredUpgrades.at(i)));
    rewards.addCardReward(cards);
    for(auto id:r.offeredRelics) rewards.addRelic(static_cast<RelicId>(id));
    for(auto id:r.offeredPotions) rewards.addPotion(static_cast<Potion>(id));
    for(const auto &gold:row.at("trace").at("offer").at("gold")) rewards.addGold(gold.get<int>());
    for(const auto &fixed:r.fixedActions) if(fixed.action==164) {
        if(row.at("trace").at("pre").at("room")=="ELITE") rewards.emeraldKey=true;
        else throw std::runtime_error("audit unsupported key offer context");
    }
    return gc;
}
}
int compressionAuditCommand(const std::string &input,const std::string &output,bool values) {
    std::ifstream in(input);std::ofstream out(output);
    if(!in || !out) throw std::runtime_error("audit input/output unavailable");
    std::string line;
    while(std::getline(in,line)) {
        auto row=nlohmann::json::parse(line);
        auto gc=publicReward(row);
        const auto expected=heart1::recordFromJson(row.at("record"));
        heart1::Choice choice;
        if(!heart1::buildChoice(gc,choice) || choice.record!=expected)
            throw std::runtime_error("audit public input parity failed at "+row.at("case").get<std::string>()+
                " decision "+row.at("decision").dump()+" actual="+heart1::recordToJson(choice.record).dump());
        bool exact=false;
        if(row.at("floor")==0) {
            // The sole pre-combat Neow card reward is reconstructible without
            // playing a run. Require full current public-record equality.
            GameContext initial(CharacterClass::IRONCLAD,row.at("seed").get<std::uint64_t>(),20);
            initial.keysEnabled=true;
            for(const auto action:sts::search::GameAction::getAllActionsInState(initial)) {
                auto candidate=initial; action.execute(candidate);
                heart1::Choice c;
                if(heart1::buildChoice(candidate,c) && c.record==expected) {gc=std::move(candidate);exact=true;break;}
            }
            if(!exact) throw std::runtime_error("audit initial reward reconstruction mismatch");
        }
        int cycle=gc.hasRelic(RelicId::MARK_OF_PAIN)?2:0;
        for(const auto &c:gc.deck.cards) cycle+=burden(c);
        auto result=compressionAuditRoot(gc,exact && values);
        result["case"]=row.at("case");result["decision"]=row.at("decision");
        result["state_index"]=row.at("state_index");result["floor"]=row.at("floor");
        result["seed"]=row.at("seed");result["public_record_parity"]=true;
        result["permanent_deck_size"]=gc.deck.size();result["cycle_burden"]=cycle;
        result["value_state_qualified"]=exact;
        result["value_unavailable_reason"]=exact?nlohmann::json(nullptr):nlohmann::json(
            "retained public record lacks replay snapshot, RNG/counters, pools, callbacks and path/policy history; public projection used only for prior/enumeration");
        for(auto &action:result["actions"]) {
            action["deck_after"]=gc.deck.size();action["cycle_after"]=cycle;
            // Reward takes insert exactly the public card; other audited
            // deck-size-neutral choices leave the recurring card count alone.
            if(action["effect"]==5) {
                Card c(static_cast<CardId>(action["card"].get<int>()),action["upgraded"].get<bool>());
                action["deck_after"]=gc.deck.size()+1;action["cycle_after"]=cycle+burden(c);
            }
            if(action["effect"]==8 && action["relic"]==static_cast<int>(RelicId::MARK_OF_PAIN))
                action["cycle_after"]=cycle+2;
        }
        out<<result.dump()<<'\n';out.flush();
    }
    return 0;
}
}
