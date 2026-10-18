#include <cstdlib>
#include "live_ooc_state.h"

#include <algorithm>
#include <cstdint>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include "constants/SaveFileMappings.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"

namespace one_combat::advisor {

namespace {
using J = nlohmann::json;
using namespace sts;
using A = search::GameAction;
using RT = A::RewardsActionType;

void require(bool yes, const std::string &why) {
    if (!yes) throw std::invalid_argument(why);
}
int integerValue(const J &v, int lo, int hi, const std::string &key) {
    require(v.is_number_integer(), key + " must be an integer");
    if (v.is_number_unsigned()) {
        const auto n=v.get<std::uint64_t>();
        require(hi>=0 && n<=static_cast<std::uint64_t>(hi) && (lo<=0 || n>=static_cast<std::uint64_t>(lo)),key+" out of range");
        return static_cast<int>(n);
    }
    const auto n=v.get<std::int64_t>();
    require(n>=lo && n<=hi,key+" out of range");
    return static_cast<int>(n);
}
int integer(const J &o, const char *key, int lo, int hi) {
    return integerValue(o.at(key),lo,hi,key);
}
bool boolean(const J &o, const char *key) {
    require(o.at(key).is_boolean(), std::string(key) + " must be a boolean");
    return o.at(key).get<bool>();
}
std::string string(const J &o, const char *key) {
    require(o.at(key).is_string(), std::string(key) + " must be a string");
    return o.at(key).get<std::string>();
}
const J &array(const J &o, const char *key, std::size_t max) {
    const auto &v = o.at(key);
    require(v.is_array() && v.size() <= max, std::string(key) + " invalid array");
    return v;
}
template<class T> T id(const J &v, T invalid) {
    require(v.is_string(), "entity ID must be a save-file string");
    const auto result = v.get<T>();
    require(result != invalid, "unknown entity ID: " + v.dump());
    return result;
}
Card card(const J &v) {
    const auto cid = id<CardId>(v.at("id"), CardId::INVALID);
    Card c(cid, boolean(v, "upgraded") ? 1 : 0);
    c.misc = integer(v, "misc", std::numeric_limits<std::int16_t>::min(), std::numeric_limits<std::int16_t>::max());
    return c;
}
Room room(const J &v) {
    require(v.is_string(), "room must be a canonical name");
    for (int i=0; i<10; ++i) if (v == roomStrings[i]) return static_cast<Room>(i);
    throw std::invalid_argument("unknown room");
}
ScreenState screen(const std::string &name) {
    if (name == "card_reward" || name == "combat_reward" || name == "rewards") return ScreenState::REWARDS;
    if (name == "rest") return ScreenState::REST_ROOM;
    if (name == "shop") return ScreenState::SHOP_ROOM;
    if (name == "map") return ScreenState::MAP_SCREEN;
    if (name == "treasure") return ScreenState::TREASURE_ROOM;
    if (name == "boss_relic") return ScreenState::BOSS_RELIC_REWARDS;
    if (name == "event" || name == "neow") return ScreenState::EVENT_SCREEN;
    if (name == "selector" || name == "upgrade" || name == "remove") return ScreenState::CARD_SELECT;
    throw std::invalid_argument("unknown OOC screen");
}
std::uint32_t primitive(const J &choice, ScreenState s) {
    const auto &n = choice.at("nativeAction");
    const auto kind = string(n, "kind");
    const int index = integer(n, "index", 0, 255);
    if (s == ScreenState::REWARDS || s == ScreenState::SHOP_ROOM) {
        if (kind == "card") return A(RT::CARD, s == ScreenState::REWARDS ? integer(n,"group",0,4) : index,
                                    s == ScreenState::REWARDS ? index : 0).bits;
        if (kind == "gold") return A(RT::GOLD,index).bits;
        if (kind == "relic") return A(RT::RELIC,index).bits;
        if (kind == "potion") return A(RT::POTION,index).bits;
        if (kind == "discard_potion") {
            require(index<5,"discard slot out of range");
            return 0xc0000000u|static_cast<unsigned>(index);
        }
        if (kind == "key") return A(RT::KEY,index).bits;
        if (kind == "remove") return A(RT::CARD_REMOVE,index).bits;
        if (kind == "skip") return A(RT::SKIP,index).bits;
    } else if (kind == "option") return A(index).bits;
    throw std::invalid_argument("invalid nativeAction for screen");
}
void validateHint(const J &hint) {
    const auto k = string(hint, "kind");
    if (k == "choose") {
        integer(hint,"choiceIndex",1,1000);
        require(hint.size() == 2, "unexpected choose hint fields");
    } else if (k == "discard_potion") {
        integer(hint,"potionSlot",1,5);
        require(hint.size()==2,"unexpected discard hint fields");
    } else {
        require(k == "skip" || k == "proceed" || k == "cancel" || k == "confirm", "unknown liveAction kind");
        require(hint.size() == 1, "unexpected liveAction fields");
    }
}
void validateForcedChoice(const J &o, const std::string &kind) {
    const auto &choices=array(o,"liveChoices",1);
    require(choices.size()==1,"forced transition requires one live choice");
    const auto &native=choices.at(0).at("nativeAction");
    require(string(native,"kind")=="option" && integer(native,"index",0,0)==0
            && integer(native,"group",0,0)==0,"forced transition native choice mismatch");
    const auto &hint=choices.at(0).at("liveAction");
    require(string(hint,"kind")==kind,"forced transition live action mismatch");
    if(kind=="choose")integer(hint,"choiceIndex",1,1);
    validateHint(hint);
}
// Exact vanilla dialogue pages. Phase names come from the installed event
// classes; an enabled button by itself does not prove a page's continuation.
const std::map<Event,std::string> eventDecisionPages{
    {Event::THE_CLERIC,"0"},{Event::PLEADING_VAGRANT,"0"},{Event::AUGMENTER,"0"},
    {Event::FORGOTTEN_ALTAR,"0"},{Event::GHOSTS,"0"},{Event::GOLDEN_IDOL,"0|1"},
    {Event::SCRAP_OOZE,"0"},{Event::VAMPIRES,"0"},{Event::THE_MOAI_HEAD,"0"},{Event::NLOTH,"0"},
    {Event::SHINING_LIGHT,"INTRO"},{Event::WING_STATUE,"INTRO"},{Event::OLD_BEGGAR,"INTRO"},
    {Event::MASKED_BANDITS,"INTRO"},{Event::MINDBLOOM,"INTRO"},{Event::TOMB_OF_LORD_RED_MASK,"INTRO"},
    {Event::GOLDEN_SHRINE,"INTRO"},{Event::THE_SSSSSERPENT,"INTRO"},{Event::DEAD_ADVENTURER,"INTRO"},
    {Event::THE_NEST,"1"},{Event::WINDING_HALLS,"1"},{Event::FACE_TRADER,"MAIN"},
    {Event::DESIGNER_IN_SPIRE,"MAIN"},{Event::FALLING,"CHOICE"},{Event::KNOWING_SKULL,"ASK"},
    {Event::SENSORY_STONE,"INTRO_2"},{Event::NOTE_FOR_YOURSELF,"CHOOSE"},{Event::THE_JOUST,"EXPLANATION"},
    {Event::COLOSSEUM,"FIGHT|POST_COMBAT"},{Event::CURSED_TOME,"INTRO|PAGE_1|PAGE_2|PAGE_3|LAST_PAGE"},
    {Event::WE_MEET_AGAIN,"INTRO"},{Event::HYPNOTIZING_COLORED_MUSHROOMS,"0"},{Event::MYSTERIOUS_SPHERE,"INTRO"}
};
const std::map<Event,std::string> eventLeavePages{
    {Event::THE_CLERIC,"99"},{Event::FORGOTTEN_ALTAR,"99"},{Event::PLEADING_VAGRANT,"1"},
    {Event::AUGMENTER,"1"},{Event::THE_MOAI_HEAD,"1"},{Event::NLOTH,"1"},
    {Event::HYPNOTIZING_COLORED_MUSHROOMS,"1"},{Event::SCRAP_OOZE,"1"},{Event::THE_DIVINE_FOUNTAIN,"1"},
    {Event::GHOSTS,"1|2"},{Event::VAMPIRES,"1|2"},{Event::GOLDEN_IDOL,"2"},{Event::THE_NEST,"2"},
    {Event::WINDING_HALLS,"2"},{Event::DUPLICATOR,"2"},{Event::SHINING_LIGHT,"COMPLETE"},
    {Event::GOLDEN_SHRINE,"COMPLETE"},{Event::UPGRADE_SHRINE,"COMPLETE"},{Event::PURIFIER,"COMPLETE"},
    {Event::TRANSMORGRIFIER,"COMPLETE"},{Event::BONFIRE_SPIRITS,"COMPLETE"},{Event::THE_JOUST,"COMPLETE"},
    {Event::NOTE_FOR_YOURSELF,"COMPLETE"},{Event::LAB,"COMPLETE"},{Event::BIG_FISH,"RESULT"},
    {Event::LIVING_WALL,"RESULT"},{Event::THE_MAUSOLEUM,"RESULT"},{Event::TOMB_OF_LORD_RED_MASK,"RESULT"},
    {Event::FACE_TRADER,"RESULT"},{Event::FALLING,"RESULT"},{Event::THE_WOMAN_IN_BLUE,"RESULT"},
    {Event::OLD_BEGGAR,"LEAVE"},{Event::MINDBLOOM,"LEAVE"},{Event::COLOSSEUM,"LEAVE"},
    {Event::SECRET_PORTAL,"LEAVE"},{Event::SENSORY_STONE,"LEAVE"},{Event::MASKED_BANDITS,"END"},{Event::CURSED_TOME,"END"},
    {Event::MYSTERIOUS_SPHERE,"END"},{Event::WING_STATUE,"MAP"},{Event::THE_SSSSSERPENT,"DISAGREE|COMPLETE"},
    {Event::DESIGNER_IN_SPIRE,"DONE"},{Event::DEAD_ADVENTURER,"ESCAPE|SUCCESS"},
    {Event::KNOWING_SKULL,"COMPLETE"},{Event::WE_MEET_AGAIN,"COMPLETE"},{Event::WHEEL_OF_CHANGE,"LEAVE"},{Event::MATCH_AND_KEEP,"COMPLETE"}
};
const std::map<Event,std::string> eventContinuePages{
    {Event::FACE_TRADER,"INTRO"},{Event::DESIGNER_IN_SPIRE,"INTRO"},{Event::FALLING,"INTRO"},
    {Event::SENSORY_STONE,"INTRO|ACCEPT"},{Event::NOTE_FOR_YOURSELF,"INTRO"},
    {Event::BONFIRE_SPIRITS,"INTRO|CHOOSE"},{Event::THE_JOUST,"INTRO|PRE_JOUST|JOUST"},
    {Event::COLOSSEUM,"INTRO"},{Event::LAB,"INTRO"},{Event::THE_NEST,"0"},{Event::WINDING_HALLS,"0"},
    {Event::OLD_BEGGAR,"GAVE_MONEY"},{Event::WING_STATUE,"PURGE"},
    {Event::MASKED_BANDITS,"PAID_1|PAID_2|PAID_3"},{Event::THE_SSSSSERPENT,"AGREE"},
    {Event::KNOWING_SKULL,"INTRO_1"},{Event::WHEEL_OF_CHANGE,"INTRO|COMPLETE|SPIN_READY"},
    {Event::DEAD_ADVENTURER,"FAIL"},{Event::MYSTERIOUS_SPHERE,"PRE_COMBAT"},
    {Event::MINDBLOOM,"FIGHT"},{Event::SECRET_PORTAL,"ACCEPT"},
    {Event::MATCH_AND_KEEP,"INTRO|RULE_EXPLANATION"}
};
bool eventPage(const std::map<Event,std::string> &pages,Event e,const std::string &phase) {
    const auto it=pages.find(e);
    return it!=pages.end() && ("|"+it->second+"|").find("|"+phase+"|")!=std::string::npos;
}
void importMatchAndKeep(LiveOocStateV1 &state,const J &o) {
    auto &g=state.projected;const auto &d=o.at("details"),&event=o.at("event");
    require(string(d,"eventContract")=="vanilla_v1" && string(event,"id")==J(Event::MATCH_AND_KEEP).get<std::string>()
            && string(event,"phase")=="PLAY","unqualified Match and Keep page");
    g.info.eventData=integer(d,"eventData",1,5);
    boolean(d,"publicMemoryComplete");
    const auto &board=array(d,"board",12);require(board.size()==12,"Match and Keep requires twelve slots");
    g.info.toSelectCards.clear();g.info.toSelectCards.resize(12);
    std::set<int> open,slots;std::set<std::string> uuids;int faceUp=0,matched=0;
    std::array<std::string,12> identities;
    for(const auto &entry:board) {
        const int slot=integer(entry,"slot",0,11);
        require(slots.insert(slot).second,"duplicate Match and Keep slot");
        const auto uuid=string(entry,"uuid");require(!uuid.empty() && uuids.insert(uuid).second,"duplicate Match and Keep identity");
        identities[slot]=uuid;const auto status=string(entry,"state");int native;
        if(status=="unseen")native=GameContext::MATCH_AND_KEEP_UNSEEN;
        else if(status=="seen")native=GameContext::MATCH_AND_KEEP_SEEN;
        else if(status=="face_up") {native=GameContext::MATCH_AND_KEEP_FACE_UP;++faceUp;}
        else {require(status=="matched","unknown Match and Keep slot state");native=GameContext::MATCH_AND_KEEP_MATCHED;++matched;}
        Card visible;
        if(status=="unseen")require(!entry.contains("card"),"unseen Match and Keep identity leaked");
        else if(status!="matched" || entry.contains("card"))visible=card(entry.at("card"));
        g.info.toSelectCards[slot]=SelectScreenCard(visible,native);
        if(status=="unseen" || status=="seen")open.insert(slot);
    }
    require(faceUp<=1 && !open.empty() && matched%2==0 && matched<=2*(5-g.info.eventData),
            "Match and Keep public attempt progress mismatch");
    const auto &options=array(event,"options",12),&choices=array(o,"liveChoices",12);
    require(options.size()==open.size() && choices.size()==open.size(),"Match and Keep available slot count mismatch");
    for(std::size_t i=0;i<choices.size();++i) {
        const int slot=integer(options[i],"index",0,11);const auto &choice=choices[i];
        require(open.erase(slot)==1 && !boolean(options[i],"disabled"),"Match and Keep unavailable slot");
        require(string(choice.at("nativeAction"),"kind")=="option"
                && integer(choice.at("nativeAction"),"index",slot,slot)==slot
                && integer(choice.at("nativeAction"),"group",0,0)==0
                && string(choice.at("liveAction"),"kind")=="choose"
                && integer(choice.at("liveAction"),"choiceIndex",i+1,i+1)==i+1
                && string(choice,"uuid")==identities[slot],"Match and Keep live slot mapping mismatch");
    }
    state.matchAndKeep=true;
}
void importEventContract(LiveOocStateV1 &state,const J &o) {
    auto &g=state.projected;const auto &d=o.at("details"),&capture=o.at("event");
    const auto phase=string(capture,"phase");
    require(string(d,"eventContract")=="vanilla_v1" && string(capture,"id")==J(g.curEvent).get<std::string>()
            && eventPage(eventDecisionPages,g.curEvent,phase),"unqualified vanilla event page");
    if(g.curEvent==Event::GOLDEN_IDOL)g.info.phase=phase=="1"?1:0;
    const bool high=g.ascension>=15;
    const auto amount=[&](const char *key,int expected) {
        const int value=integer(d,key,0,1000000);
        require(value==expected,std::string("public event amount mismatch: ")+key);return value;
    };
    const auto frac=[&](float n){return static_cast<int>(g.maxHp*n);};
    const auto round=[&](float n){return static_cast<int>(g.maxHp*n+0.5f);};
    switch(g.curEvent) {
        case Event::THE_CLERIC:g.info.hpAmount0=amount("hpAmount0",g.gold>=35?frac(.25f):0);break;
        case Event::SHINING_LIGHT:g.info.hpAmount0=amount("hpAmount0",round(high?.3f:.2f));break;
        case Event::GOLDEN_IDOL:
            g.info.hpAmount0=amount("hpAmount0",frac(high?.35f:.25f));
            g.info.hpAmount1=amount("hpAmount1",std::max(1,frac(high?.1f:.08f)));break;
        case Event::FORGOTTEN_ALTAR:g.info.hpAmount0=amount("hpAmount0",round(high?.35f:.25f));break;
        case Event::GHOSTS:g.info.hpAmount0=amount("hpAmount0",std::min(g.maxHp-1,(g.maxHp+1)/2));break;
        case Event::VAMPIRES:g.info.hpAmount0=amount("hpAmount0",std::min(g.maxHp-1,static_cast<int>(std::ceil(g.maxHp*.3f))));break;
        case Event::THE_MOAI_HEAD:g.info.hpAmount0=amount("hpAmount0",round(high?.18f:.125f));break;
        case Event::WINDING_HALLS:
            g.info.hpAmount0=amount("hpAmount0",round(high?.18f:.125f));
            g.info.hpAmount1=amount("hpAmount1",round(high?.2f:.25f));
            g.info.hpAmount2=amount("hpAmount2",round(.05f));break;
        case Event::FACE_TRADER:
            g.info.hpAmount0=amount("hpAmount0",std::max(1,frac(.1f)));
            amount("gold",high?50:75);break;
        case Event::KNOWING_SKULL:
            g.info.hpAmount0=integer(d,"hpAmount0",6,1000000);g.info.hpAmount1=integer(d,"hpAmount1",6,1000000);
            g.info.hpAmount2=integer(d,"hpAmount2",6,1000000);amount("leaveCost",6);break;
        case Event::SCRAP_OOZE:
            require(g.info.eventData<=8,"invalid Scrap Ooze attempt count");
            amount("relicObtainChance",25+10*g.info.eventData);
            g.info.hpAmount0=amount("hpAmount0",(high?5:3)+g.info.eventData);break;
        case Event::FALLING:
            for(const auto &[index,type]:{std::pair{g.info.skillCardDeckIdx,CardType::SKILL},
                    std::pair{g.info.powerCardDeckIdx,CardType::POWER},std::pair{g.info.attackCardDeckIdx,CardType::ATTACK}})
            {
                bool eligible=false;for(int i=0;i<g.deck.size();++i)
                    if(g.deck.cards[i].getType()==type && !g.deck.isCardBottled(i))eligible=true;
                require((index>=0)==eligible && (index<0 || (g.deck.cards[index].getType()==type
                        && !g.deck.isCardBottled(index))),"Falling card eligibility mismatch");
            }
            break;
        case Event::NLOTH:
            g.info.relicIdx0=integer(d,"relicIdx0",0,g.relics.size()-1);
            g.info.relicIdx1=integer(d,"relicIdx1",0,g.relics.size()-1);
            require(g.info.relicIdx0!=g.info.relicIdx1,"N'loth duplicate offer");break;
        case Event::WE_MEET_AGAIN:
            require(g.info.potionIdx<g.potionCapacity && (g.info.potionIdx<0 || g.potions[g.info.potionIdx]!=Potion::EMPTY_POTION_SLOT),
                    "We Meet Again potion unavailable");
            require(g.info.gold==-1 || (g.info.gold>=50 && g.info.gold<=std::min(150,g.gold)),"We Meet Again gold mismatch");
            require((g.info.gold<0)==(g.gold<50),"We Meet Again unavailable gold mismatch");
            {bool eligible=false;for(const auto &c:g.deck.cards)
                if(c.getRarity()!=CardRarity::BASIC && c.getType()!=CardType::CURSE)eligible=true;
             require((g.info.cardIdx>=0)==eligible,"We Meet Again unavailable card mismatch");}
            if(g.info.cardIdx>=0)require(g.deck.cards[g.info.cardIdx].getRarity()!=CardRarity::BASIC
                    && g.deck.cards[g.info.cardIdx].getType()!=CardType::CURSE,"We Meet Again ineligible card");
            break;
        case Event::NOTE_FOR_YOURSELF:g.noteForYourselfCard=card(d.at("noteForYourselfCard"));break;
        case Event::DEAD_ADVENTURER: {
            require(g.info.phase<=2,"Dead Adventurer search already completed");
            amount("encounterChance",g.info.phase*25+(high?35:25));
            const MonsterEncounter encounters[]={MonsterEncounter::THREE_SENTRIES,MonsterEncounter::GREMLIN_NOB,MonsterEncounter::LAGAVULIN_EVENT};
            g.info.encounter=encounters[integer(d,"publicEnemy",0,2)];
            const bool gold=boolean(d,"earnedGold"),relic=boolean(d,"earnedRelic");
            const int nothing=g.info.phase-int(gold)-int(relic);
            require(nothing==0 || nothing==1,"Dead Adventurer public reward history mismatch");
            int n=0;for(int i=0;i<3;++i)if(i==0?gold:i==1?nothing==1:relic)g.info.rewards[n++]=i;
            for(int i=0;i<3;++i)if(!(i==0?gold:i==1?nothing==1:relic))g.info.rewards[n++]=i;
            state.hiddenEventState=g.info.phase<2;break;
        }
        default:break;
    }
    if(g.curEvent==Event::COLOSSEUM)require(g.info.eventData==(phase=="POST_COMBAT"?1:0),"Colosseum phase mismatch");
    if(g.curEvent==Event::CURSED_TOME) {
        const std::vector<std::string> phases{"INTRO","PAGE_1","PAGE_2","PAGE_3","LAST_PAGE"};
        require(g.info.eventData==std::find(phases.begin(),phases.end(),phase)-phases.begin(),"Cursed Tome stage mismatch");
    }
    const auto &options=array(capture,"options",8),&choices=array(o,"liveChoices",8);
    require(!options.empty() && options.size()==choices.size(),"event option mapping count mismatch");
    int bits=0,previous=-1;
    for(std::size_t i=0;i<options.size();++i) {
        const int slot=integer(options[i],"index",0,7);int native=slot;
        require(slot>previous && !boolean(options[i],"disabled"),"event enabled option order mismatch");previous=slot;
        if(g.curEvent==Event::GOLDEN_IDOL)require(slot<(phase=="1"?3:2),"Golden Idol slot invalid");
        if(g.curEvent==Event::VAMPIRES)require(slot<(g.hasRelic(RelicId::BLOOD_VIAL)?3:2),"Vampires slot invalid");
        if(g.curEvent==Event::DESIGNER_IN_SPIRE)require(slot<4,"Designer slot invalid");
        if(g.curEvent==Event::CURSED_TOME)require(slot<2,"Cursed Tome slot invalid");
        if(g.curEvent==Event::FALLING && g.info.skillCardDeckIdx<0 && g.info.powerCardDeckIdx<0 && g.info.attackCardDeckIdx<0)
            require(slot==0,"Falling empty deck slot invalid");
        if(g.curEvent==Event::GOLDEN_IDOL && phase=="1")native+=2;
        if(g.curEvent==Event::VAMPIRES)native=slot==0?1:slot==1&&g.hasRelic(RelicId::BLOOD_VIAL)?0:2;
        if(g.curEvent==Event::MINDBLOOM && slot==2 && g.floorNum>40)native=3;
        if(g.curEvent==Event::TOMB_OF_LORD_RED_MASK && g.hasRelic(RelicId::RED_MASK) && slot==1)native=2;
        if(g.curEvent==Event::FALLING && g.info.skillCardDeckIdx<0 && g.info.powerCardDeckIdx<0 && g.info.attackCardDeckIdx<0)native=3;
        if(g.curEvent==Event::DESIGNER_IN_SPIRE)native=slot==0?(g.info.upgradeOne?0:1):slot==1?(g.info.cleanUpIsRemoveCard?2:3):slot==2?4:5;
        if(g.curEvent==Event::CURSED_TOME && g.info.eventData>0)native=g.info.eventData+1+slot;
        if(g.curEvent==Event::KNOWING_SKULL) {const int indices[]={2,0,1,3};require(slot<4,"Skull slot invalid");native=indices[slot];}
        const auto &action=choices[i].at("nativeAction"),&hint=choices[i].at("liveAction");
        require(string(action,"kind")=="option" && integer(action,"index",native,native)==native
                && (!action.contains("group") || integer(action,"group",0,0)==0)
                && string(hint,"kind")=="choose" && integer(hint,"choiceIndex",i+1,i+1)==i+1,
                "event source/native/live option mismatch");
        require(!(bits&(1<<native)),"duplicate event native action");bits|=1<<native;
    }
    require(bits==A::getValidEventSelectBits(g),"public/native event option set mismatch");
    switch(g.curEvent) {
        case Event::HYPNOTIZING_COLORED_MUSHROOMS:case Event::MYSTERIOUS_SPHERE:case Event::DEAD_ADVENTURER:
        case Event::COLOSSEUM:case Event::MINDBLOOM:case Event::MASKED_BANDITS:case Event::SENSORY_STONE:
            state.hiddenEventRewardPity=!state.rewardPityHistoryComplete;break;
        default:break;
    }
}
LiveOocStateV1::LiveOocMctsRootV1 makeMctsRoot(const LiveOocStateV1 &source) {
    // The constructor supplies canonical act/pool/history support from a
    // fixed hypothetical seed. It is deliberately overwritten with the
    // public observation below and re-randomized by sampleNoncombatFuture.
    constexpr std::uint64_t hypotheticalSeed = 0x4f4f435f4c495645ULL;
    sts::GameContext root(sts::CharacterClass::IRONCLAD, hypotheticalSeed,
                          source.projected.ascension);
    if (source.projected.act != 1)
        root.transitionToAct(source.projected.act);

    root.seed = 0;
    root.outcome = source.projected.outcome;
    root.screenState = source.projected.screenState;
    root.lastRoom = source.projected.lastRoom;
    root.curEvent = source.projected.curEvent;
    root.boss = source.projected.boss;
    // Keep the constructor's public prior for hidden reward/event counters.
    // Live Java's private blizzard counters are deliberately not imported.
    root.shopRemoveCount = source.projected.shopRemoveCount;
    root.curMapNodeX = source.projected.curMapNodeX;
    root.curMapNodeY = source.projected.curMapNodeY;
    root.floorNum = source.projected.floorNum;
    root.act = source.projected.act;
    root.ascension = source.projected.ascension;
    root.cc = source.projected.cc;
    root.curHp = source.projected.curHp;
    root.maxHp = source.projected.maxHp;
    root.gold = source.projected.gold;
    root.potionCount = source.projected.potionCount;
    root.potionCapacity = source.projected.potionCapacity;
    root.potions = source.projected.potions;
    root.relics = source.projected.relics;
    root.wingBootsCharges = source.projected.wingBootsCharges;
    root.deck = source.projected.deck;
    root.blueKey = source.projected.blueKey;
    root.greenKey = source.projected.greenKey;
    root.keysEnabled = source.projected.keysEnabled;
    root.restRoomResolved = source.projected.restRoomResolved;
    root.redKey = source.projected.redKey;
    root.info = source.projected.info;
    root.noteForYourselfCard = source.projected.noteForYourselfCard;
    root.map = source.projected.map ? std::make_shared<sts::Map>(*source.projected.map) : root.map;
    if (source.projected.curRoom != sts::Room::INVALID)
        root.curRoom = source.projected.curRoom;

    if (root.curMapNodeY >= 0 && root.curMapNodeY < 15
            && root.curMapNodeX >= 0 && root.curMapNodeX < 7 && root.map)
        root.curRoom = root.map->getNode(root.curMapNodeX, root.curMapNodeY).room;
    root.lastRoom = source.projected.lastRoom == sts::Room::INVALID
        ? root.curRoom : source.projected.lastRoom;

    const auto &publicState = source.ooc.at("publicState");
    const auto &actVisits = array(publicState, "currentActPathVisits", 10);
    require(actVisits.size() == 10, "ten current-act path counters required");
    // path_taken retains '?' after conversion and the damage metric has no
    // encounter class. Only the observed, complete combat-class ledger may
    // determine which native encounter queue was consumed.
    const auto &combatFloors = array(publicState, "combatFloors", 1000);
    const auto &combatHistory = array(publicState, "combatHistory", 1000);
    const bool combatHistoryComplete = boolean(publicState, "combatHistoryComplete");
    array(publicState, "pathHistory", 1000);
    const int actStartFloor = source.projected.act <= 1 ? 0
        : source.projected.act == 2 ? 17
        : source.projected.act == 3 ? 34 : 51;
    std::vector<int> completedCombatFloors;
    for (const auto &floorValue : combatFloors) {
        const int floor = integerValue(floorValue, 1, 1000, "combat floor");
        if (floor <= actStartFloor || floor > source.projected.floorNum) continue;
        completedCombatFloors.push_back(floor);
    }
    const int eliteVisits = integerValue(actVisits.at(static_cast<int>(Room::ELITE)),
        0, 1000, "current-act elite visits");
    const int eventVisits = integerValue(actVisits.at(static_cast<int>(Room::EVENT)),
        0, 1000, "current-act event visits");
    const bool questionHistoryComplete = publicState.contains("questionHistoryComplete")
        ? boolean(publicState, "questionHistoryComplete") : false;
    bool juzuWasOwned=root.relics.has(RelicId::JUZU_BRACELET);
    for (const auto &relic : array(publicState, "acquiredRelics", 181))
        juzuWasOwned |= id<RelicId>(relic,RelicId::INVALID)==RelicId::JUZU_BRACELET;
    bool questionMonsterChanceAmbiguous=false;
    QuestionRoomBelief questionBelief;
    bool questionBeliefQualified=false;
    if(questionHistoryComplete) {
        const auto &outcomes=array(publicState,"questionOutcomes",100);
        require(outcomes.size()==static_cast<std::size_t>(eventVisits),
                "complete question history length differs from event visits");
        questionBeliefQualified=publicState.value("questionRoomRules",std::string())=="vanilla_ordinary_v1"
            && std::all_of(outcomes.begin(),outcomes.end(),[](const J &entry) {
            return entry.contains("previousRoomWasShop") && entry.contains("tinyChestForced")
                && entry.contains("juzuOwnedAtEntry");
        });
        int previousFloor=actStartFloor;
        root.monsterChance=0.1f;
        root.shopChance=0.03f;
        root.treasureChance=0.02f;
        for(const auto &entry:outcomes) {
            const int floor=integer(entry,"floor",actStartFloor+1,root.floorNum);
            require(floor>previousFloor,"question outcomes must follow floor order");
            previousFloor=floor;
            const auto name=string(entry,"outcome");
            Room outcome=Room::INVALID;
            if(name=="MONSTER")outcome=Room::MONSTER;
            else if(name=="SHOP")outcome=Room::SHOP;
            else if(name=="TREASURE")outcome=Room::TREASURE;
            else if(name=="EVENT")outcome=Room::EVENT;
            require(outcome!=Room::INVALID,"unknown public question outcome");
            const bool ownershipKnown=entry.contains("juzuOwnedAtEntry");
            const bool juzuAtEntry=ownershipKnown?boolean(entry,"juzuOwnedAtEntry"):juzuWasOwned;
            require(!(ownershipKnown && juzuAtEntry && !juzuWasOwned),
                    "Juzu ownership absent from public relic history");
            require(!(outcome==Room::MONSTER && ownershipKnown && juzuAtEntry),
                    "monster question outcome contradicts Juzu ownership");
            const bool conversionKnown=entry.contains("juzuConverted");
            const bool converted=conversionKnown?boolean(entry,"juzuConverted"):false;
            require(!conversionKnown || ownershipKnown,"Juzu conversion lacks observed ownership");
            require(!converted || (juzuAtEntry && outcome==Room::EVENT),
                    "Juzu conversion contradicts public room state");
            // All latent states use exact vanilla bin likelihoods under the
            // fair room-roll prior, including conditioning on non-EVENT rooms.
            if(questionBeliefQualified) {
                require(questionBelief.condition(outcome,juzuAtEntry,boolean(entry,"previousRoomWasShop"),
                            boolean(entry,"tinyChestForced"),conversionKnown?(converted?1:0):-1),
                        "public question history has zero likelihood under qualified room rules");
            }
            if(outcome==Room::MONSTER || converted) questionMonsterChanceAmbiguous=false;
            else if(outcome==Room::EVENT && juzuAtEntry && !conversionKnown) questionMonsterChanceAmbiguous=true;
            // Match GameContext::getEventRoomOutcomeHelper, including
            // repeated float additions. Tiny Chest's forced TREASURE takes
            // these same branches. An ambiguous Juzu EVENT stays unqualified
            // until a later observed MONSTER resets its only unknown counter.
            root.monsterChance=(outcome==Room::MONSTER || converted)?0.1f:root.monsterChance+0.1f;
            root.shopChance=outcome==Room::SHOP?0.03f:root.shopChance+0.03f;
            root.treasureChance=outcome==Room::TREASURE?0.02f:root.treasureChance+0.02f;
            if(floor==root.floorNum)root.curRoom=outcome;
            if(floor+1==root.floorNum)root.lastRoom=outcome;
        }
    }
    if(questionBeliefQualified) {
        questionMonsterChanceAmbiguous=false;
        // A multi-state value is only a transition-container placeholder.
        // Each root particle samples the posterior before any transition.
        root.monsterChance=questionBelief.monster.front().first;
    }
    int normalCombats = 0, eliteCombats = 0;
    require(!combatHistoryComplete || combatHistory.size() == completedCombatFloors.size(),
        "complete combat history length differs from public combat metric");
    for (std::size_t i = 0; i < combatHistory.size(); ++i) {
        const auto &entry = combatHistory.at(i);
        const int floor = integer(entry, "floor", 1, 1000);
        const auto kind = string(entry, "kind");
        require(floor>actStartFloor && floor<=root.floorNum,"combat history outside current act");
        const auto encounterName=entry.contains("encounter")?string(entry,"encounter"):std::string();
        if(encounterName=="COLOSSEUM_EVENT_SLAVERS" || encounterName=="COLOSSEUM_EVENT_NOBS") {
            require(root.act==2 && kind=="FIXED_EVENT","Colosseum combat requires Act 2 fixed event");
            if(encounterName=="COLOSSEUM_EVENT_NOBS") {
                require(i>0,"Colosseum Nobs requires its preceding Slaver fight");
                const auto &previous=combatHistory.at(i-1);
                require(integer(previous,"floor",actStartFloor+1,root.floorNum)==floor
                        && string(previous,"kind")=="FIXED_EVENT"
                        && string(previous,"encounter")=="COLOSSEUM_EVENT_SLAVERS",
                        "Colosseum Nobs requires same-floor Slaver fight");
            }
        }
        if(i>0) {
            const auto &previous=combatHistory.at(i-1);
            const int previousFloor=integer(previous,"floor",actStartFloor+1,root.floorNum);
            require(floor>=previousFloor,"combat history must follow floor order");
            if(floor==previousFloor)require(root.act==2 && kind=="FIXED_EVENT"
                    && string(previous,"kind")=="FIXED_EVENT"
                    && string(previous,"encounter")=="COLOSSEUM_EVENT_SLAVERS"
                    && string(entry,"encounter")=="COLOSSEUM_EVENT_NOBS",
                    "unqualified same-floor combat sequence");
        }
        require(kind == "NORMAL_QUEUE" || kind == "ELITE_QUEUE" || kind == "FIXED_EVENT"
                || kind == "BOSS", "unknown public combat class");
        if (combatHistoryComplete)
            require(floor == completedCombatFloors.at(i), "combat history floor mismatch");
        if (kind == "NORMAL_QUEUE" || kind == "ELITE_QUEUE") {
            if (!entry.contains("encounter") || !entry.at("encounter").is_string()
                    || entry.at("encounter").get<std::string>().empty()) {
                // A resumed or otherwise incomplete ledger is already a
                // fail-closed boundary below. Do not promote its missing
                // queue identity into a schema error before that boundary can
                // be reported to the live driver.
                if (!combatHistoryComplete) continue;
                require(false, "queue combat identity is incomplete");
            }
            const auto encounterName = entry.at("encounter").get<std::string>();
            MonsterEncounter encounter = MonsterEncounter::INVALID;
            for (int candidate = 1; candidate < static_cast<int>(sizeof(monsterEncounterEnumNames)
                    / sizeof(*monsterEncounterEnumNames)); ++candidate)
                if (encounterName == monsterEncounterEnumNames[candidate]) {
                    encounter = static_cast<MonsterEncounter>(candidate);
                    break;
                }
            require(encounter != MonsterEncounter::INVALID, "unknown public encounter identity");
            if (kind == "NORMAL_QUEUE") {
                require(normalCombats < static_cast<int>(root.monsterList.size()),
                        "normal encounter history exceeds native queue");
                root.monsterList[normalCombats++] = encounter;
            } else {
                require(eliteCombats < static_cast<int>(root.eliteMonsterList.size()),
                        "elite encounter history exceeds native queue");
                root.eliteMonsterList[eliteCombats++] = encounter;
            }
        }
    }
    if (combatHistoryComplete)
        require(eliteCombats == eliteVisits,
            "elite combat history differs from elite map visits");
    root.monsterListOffset = normalCombats;
    root.eliteMonsterListOffset = eliteCombats;
    const auto eraseRelic = [&](RelicId relic) {
        for (auto pool : {&root.commonRelicPool, &root.uncommonRelicPool, &root.rareRelicPool,
                          &root.shopRelicPool, &root.bossRelicPool})
            pool->erase(std::remove(pool->begin(), pool->end(), relic), pool->end());
    };
    for (const auto &relic : array(publicState, "acquiredRelics", 181)) {
        const auto relicId=id<RelicId>(relic,RelicId::INVALID);
        eraseRelic(relicId);
    }
    // Vanilla persists selected and unselected boss offers independently of
    // our complete observer checkpoint. These exact exclusions do not qualify
    // missing ordinary/shop offers or widen random-relic branch support.
    if(publicState.contains("knownRelicOffers"))
        for(const auto &relic:array(publicState,"knownRelicOffers",181))
            eraseRelic(id<RelicId>(relic,RelicId::INVALID));
    const bool seenRelicsComplete = boolean(publicState, "seenRelicsComplete");
    require(array(publicState, "seenRelics", 181).size() <= 181,
        "seen relic history too large");
    if (seenRelicsComplete) {
        for (const auto &relic : array(publicState, "seenRelics", 181))
            eraseRelic(id<RelicId>(relic, RelicId::INVALID));
    }
    // Native pools consume relics when they are offered, not when acquired.
    // Condition every currently visible offer before Courier or another
    // within-checkpoint transition can draw from the reconstructed pools.
    if (source.projected.screenState == ScreenState::SHOP_ROOM) {
        for (int i=0; i<3; ++i)
            if (source.projected.info.shop.relicPrice(i) >= 0)
                eraseRelic(source.projected.info.shop.relics[i]);
    } else if (source.projected.screenState == ScreenState::REWARDS) {
        const auto &rewards = source.projected.info.rewardsContainer;
        for (int i=0; i<rewards.relicCount; ++i) eraseRelic(rewards.relics[i]);
    } else if (source.projected.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        for (RelicId relic : source.projected.info.bossRelics) eraseRelic(relic);
    }
    const auto eraseEvent = [&](Event event) {
        for (auto pool : {&root.eventList, &root.shrineList, &root.specialOneTimeEventList})
            pool->erase(std::remove(pool->begin(), pool->end(), event), pool->end());
    };
    for (const auto &event : array(publicState, "priorEvents", 100))
        eraseEvent(id<Event>(event, Event::INVALID));
    if (root.curEvent != Event::INVALID && root.curEvent != Event::NEOW) eraseEvent(root.curEvent);

    const bool canDrawUnseenRelic = [&] {
        if (seenRelicsComplete) return false;
        // A direct MAP root searches its next room before the hard downstream
        // MAP checkpoint. Any branch may generate a relic offer there.
        if (source.projected.screenState == ScreenState::MAP_SCREEN) return true;
        if (source.projected.screenState == ScreenState::TREASURE_ROOM) return true;
        if (source.projected.screenState == ScreenState::REST_ROOM
                && root.relics.has(RelicId::SHOVEL)) return true;
        if (source.projected.screenState == ScreenState::SHOP_ROOM
                && root.relics.has(RelicId::THE_COURIER)) {
            for (int i = 0; i < 3; ++i)
                if (source.projected.info.shop.relicPrice(i) >= 0) return true;
        }
        if (source.projected.screenState != ScreenState::EVENT_SCREEN) return false;
        switch (root.curEvent) {
            case Event::BIG_FISH:
            case Event::PLEADING_VAGRANT:
            case Event::DEAD_ADVENTURER:
            case Event::SCRAP_OOZE:
            case Event::THE_MAUSOLEUM:
            case Event::MYSTERIOUS_SPHERE:
            case Event::MINDBLOOM:
            case Event::COLOSSEUM:
            case Event::WE_MEET_AGAIN:
            case Event::WHEEL_OF_CHANGE:
                return true;
            default:
                return false;
        }
    }();

    // These callbacks are only the public-screen continuation boundary. Any
    // callback that depends on an unrevealed prior room remains unsupported by
    // the importer rather than borrowing live Java state.
    // Leaving the rewards of an act 1 or 2 boss (map row 15) opens the boss
    // chest, as native afterBattle does; there is no map node to pick from.
    // A plain MAP_SCREEN there has no legal action (canary 2, 2026-10-18).
    const auto leaveRewards = [](sts::GameContext &gc) {
        gc.regainControlAction = nullptr;
        if (gc.curMapNodeY == 15 && (gc.act == 1 || gc.act == 2)) gc.enterBossTreasureRoom();
        else gc.screenState = sts::ScreenState::MAP_SCREEN;
    };
    root.regainControlAction = leaveRewards;
    if(source.ooc.at("details").value("parentPotionRewards",false)
            || source.ooc.at("details").value("parentKnownRewards",false)
            || source.ooc.at("details").contains("parentUnrevealedCardRewards")) {
        // UI Skip closes only the visible card page; sibling potions remain.
        // CARD(group,5) still means Singing Bowl when owned. The distinct
        // global SKIP primitive is scoped here to the public card-page close.
        root.regainControlAction=[leaveRewards](sts::GameContext &gc) {
            const bool cardPage=gc.info.rewardsContainer.cardRewardCount>0;
            if(cardPage)gc.info.rewardsContainer.removeCardReward(0);
            gc.screenState=cardPage?sts::ScreenState::REWARDS:sts::ScreenState::MAP_SCREEN;
            if(cardPage) gc.regainControlAction=leaveRewards;
            else leaveRewards(gc);
        };
    }
    if(root.screenState==sts::ScreenState::CARD_SELECT && source.ooc.at("details").contains("afterSelect"))
        root.regainControlAction=[](sts::GameContext &gc) {
            gc.deck.upgradeRandomCards(gc.miscRng,1);
            gc.screenState=sts::ScreenState::MAP_SCREEN;gc.regainControlAction=nullptr;
        };
    if (root.screenState == sts::ScreenState::BOSS_RELIC_REWARDS)
        root.regainControlAction = [](sts::GameContext &gc) { gc.transitionToAct(gc.act + 1); };

    LiveOocStateV1::LiveOocMctsRootV1 result;
    result.state = std::move(root);
    result.path = source.path;
    result.currentActEventVisits = eventVisits;
    result.questionHistoryComplete=questionHistoryComplete && !questionMonsterChanceAmbiguous;
    if(questionBeliefQualified)result.questionChancePosterior=questionBelief.monster;
    // Unknown sibling card identities are not captured or fabricated. Resolve
    // this visible offer and known potions, then value the resulting player
    // state at a hard checkpoint; omitted sibling choices are disclosed.
    result.mapHistoryComplete=result.questionHistoryComplete && seenRelicsComplete
        && !source.ooc.at("details").contains("parentUnrevealedCardRewards");
    // MAP roots are searchable with sampled room-outcome belief particles;
    // stopAtMapCheckpoint applies only after a searched transition. Random
    // relic branches still require complete public offer history.
    if (!combatHistoryComplete) {
        result.supported = false;
        result.reason = "PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED";
    } else if (!questionHistoryComplete && eventVisits > 0) {
        result.supported = false;
        result.reason = "PUBLIC_QUESTION_ROOM_HISTORY_UNQUALIFIED";
    } else if(questionMonsterChanceAmbiguous) {
        // A Juzu-converted monster resets monsterChance, whereas a genuine
        // event increments it. Public resolved symbols cannot distinguish
        // these cases while Juzu was owned; later known monster resets can
        // make the currently relevant counter exact again.
        result.supported=false;
        result.reason="PUBLIC_QUESTION_ROOM_HISTORY_UNQUALIFIED:Juzu_Bracelet";
    } else if (canDrawUnseenRelic) {
        result.supported = false;
        result.reason = "PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED";
    }
    return result;
}
} // namespace

ImportResult importLiveOocStateV1(const J &observation, LiveOocStateV1 &out) {
    try {
        require(string(observation,"boundary") == "ooc", "OOC boundary required");
        const auto &o = observation.at("ooc");
        integer(o,"schemaVersion",1,1);
        const auto screenName = string(o,"screen");
        require(!screenName.empty(),"OOC screen is empty");
        if (o.contains("captureError"))
            throw std::runtime_error("live capture integrity failure: " + string(o,"captureError"));
        std::string deferredUnsupportedReason;
        if (o.contains("unsupportedReason")) {
            const auto reason = string(o,"unsupportedReason");
            // Accept the former producer marker for compatible captures;
            // public charge and exact action-set validation still run below.
            const bool boundedWinged = reason
                    == "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active";
            // A normal combat reward can expose gold alongside an unopened
            // card group. Defer this one support boundary until the complete
            // capture and its live mappings have been validated below.
            const bool hiddenCardReward = reason == "CARD_GROUP_NOT_REVEALED"
                && (screenName == "combat_reward" || screenName == "rewards");
            if (!reason.empty() && !boundedWinged && !hiddenCardReward)
                return {false,"UNSUPPORTED",reason};
            if (hiddenCardReward) deferredUnsupportedReason = reason;
        }
        LiveOocStateV1 next;
        next.ooc = o;
        auto &g = next.projected;
        const auto &p = o.at("publicState");
        next.rewardPityHistoryComplete = p.contains("rewardPityHistoryComplete")
            ? boolean(p, "rewardPityHistoryComplete") : false;
        require(string(p,"character") == "IRONCLAD", "only Ironclad is representable");
        g.cc = CharacterClass::IRONCLAD;
        g.seed = 0; // Never used. No live RNG or hidden queue is imported.
        g.ascension=integer(p,"ascension",0,20); g.act=integer(p,"act",1,4);
        g.floorNum=integer(p,"floor",0,1000); g.curHp=integer(p,"hp",0,32767);
        g.maxHp=integer(p,"maxHp",1,32767); require(g.curHp<=g.maxHp,"hp exceeds maxHp");
        g.gold=integer(p,"gold",0,1000000);
        // Hidden native blizzard counters are intentionally absent. These
        // compatibility fields are populated only for exact synthetic
        // fixtures; real captures mark rewardPityHistoryComplete=false, so
        // direct V4 fails closed and MCTS does not consume these values.
        g.potionChance=30;
        g.cardRarityFactor=-18;
        g.shopRemoveCount=integer(p,"shopRemoveCount",0,100);
        g.blueKey=boolean(p,"blueKey"); g.greenKey=boolean(p,"greenKey");
        g.keysEnabled=boolean(p,"keysEnabled"); g.redKey=boolean(p,"redKey");
        g.potionCapacity=integer(p,"potionCapacity",0,5);
        const auto &potions=array(p,"potions",5); require(potions.size()==5,"five potion slots required");
        for (int i=0;i<5;++i) {
            g.potions[i]=id<Potion>(potions[i],Potion::INVALID);
            require(i<g.potionCapacity || g.potions[i]==Potion::EMPTY_POTION_SLOT,"potion outside capacity");
            g.potionCount += g.potions[i]!=Potion::EMPTY_POTION_SLOT;
        }
        for (const auto &v:array(p,"deck",Deck::MAX_SIZE)) {
            const Card c = card(v);
            const auto type = c.getType();
            require(type == CardType::ATTACK || type == CardType::SKILL
                    || type == CardType::POWER || type == CardType::CURSE,
                    "non-permanent card in deck");
            // Reconstruct bookkeeping without acquisition effects.
            // Match ordinary Deck::obtain state.
            g.deck.cards.push_back(c);
            if (type != CardType::CURSE || c.canTransform()) {
                ++g.deck.cardTypeCounts[static_cast<int>(type)];
                ++g.deck.transformableCount;
            }
            if (c.canUpgrade()) ++g.deck.upgradeableCount;
            const int binding=integer(v,"bottleBinding",-1,2);
            if(binding>=0) {
                require(g.deck.bottleIdxs[binding]==-1,"duplicate bottle binding");
                const CardType types[]={CardType::ATTACK,CardType::SKILL,CardType::POWER};
                require(g.deck.cards[g.deck.size()-1].getType()==types[binding],"bottle type mismatch");
                g.deck.bottleCard(g.deck.size()-1,types[binding]);
            }
        }
        std::set<RelicId> relicIds;
        for(const auto &v:array(p,"relics",181)) {
            const auto r=id<RelicId>(v.at("id"),RelicId::INVALID);
            require(relicIds.insert(r).second,"duplicate relic identity");
            const int modelData = integer(v,"data",-1000000,1000000);
            if (r == RelicId::WING_BOOTS) {
                require(modelData == 0, "Wing Boots model data must be zero");
                require(v.contains("liveCounter"), "Wing Boots liveCounter missing");
                g.relics.add({r, 0});
                const int counter=integer(v,"liveCounter",-2,3);
                require(counter!=-1,"unqualified Wing Boots counter");
                g.wingBootsCharges = std::max(0,counter);
            } else {
                g.relics.add({r, modelData});
            }
        }
        g.boss=id<MonsterEncounter>(p.at("boss"),MonsterEncounter::INVALID);
        const auto &m=p.at("map");
        g.curMapNodeX=integer(m,"x",-1,6); g.curMapNodeY=integer(m,"y",-1,16);
        // The native inspector uses (-1, 15) while the act-boss room is
        // active: row 15 is the transition above the 15-row visible map and
        // has no selectable map node. Preserve that sentinel instead of
        // fabricating an x-coordinate; all ordinary map rows still require
        // a real x when y is non-negative.
        require(g.curMapNodeY < 0 || g.curMapNodeX >= 0
                    || (g.curMapNodeY == 15 && g.curMapNodeX == -1),
                "invalid current map coordinate");
        g.map=std::make_shared<Map>();
        g.map->burningEliteX=integer(m,"burningEliteX",-1,6);
        g.map->burningEliteY=integer(m,"burningEliteY",-1,14);
        require((g.map->burningEliteX<0)==(g.map->burningEliteY<0),"partial burning elite coordinate");
        for(int y=0;y<15;++y)for(int x=0;x<7;++x){g.map->nodes[y][x].x=x;g.map->nodes[y][x].y=y;}
        std::set<std::pair<int,int>> seen;
        const auto &nodes=array(m,"nodes",105);
        require(nodes.size()==105,"complete 15 by 7 visible map required");
        for(const auto &n:nodes) {
            const int x=integer(n,"x",0,6),y=integer(n,"y",0,14);
            require(seen.insert({x,y}).second,"duplicate map node");
            auto &node=g.map->nodes[y][x]; node.room=room(n.at("room"));
            std::set<int> children;
            for(const auto &e:array(n,"edges",3)) {
                const auto cx=integerValue(e,0,6,"edge child x");
                require(children.insert(cx).second,"duplicate map edge");
                node.addEdge(cx);
            }
        }
        // Reconstruct parent lists from the complete visible edge set.
        for(int y=0;y<14;++y)for(int x=0;x<7;++x) {
            auto &n=g.map->nodes[y][x];
            for(int e=0;e<n.edgeCount;++e) {
                require(seen.count({n.edges[e],y+1}),"map edge target missing");
                auto &child=g.map->nodes[y+1][n.edges[e]];
                require(child.parentCount < static_cast<int>(child.parents.size()), "map parent capacity exceeded");
                child.addParent(x);
            }
        }
        require(boolean(p,"pathComplete"),"path history not reconstructed");
        const auto &visits=array(p,"pathVisits",10); require(visits.size()==10,"ten path counters required");
        for(int i=0;i<10;++i) {
            require(visits[i].is_number_integer(),"path count must be integer");
            const auto n=visits[i].get<std::int64_t>();require(n>=0 && n<=1000,"path count out of range");
            next.path.roomVisits[i]=static_cast<int>(n);
        }
        // Java's path counters already include the currently visible room.
        // Preserve the current node identity so the shared OOC provider does
        // not count that room a second time at its root.
        if (g.curMapNodeY >= 0 && g.curMapNodeY < 15
                && g.curMapNodeX >= 0 && g.curMapNodeX < 7)
            next.path.lastNodeKey = static_cast<long>(g.act) * 100000L
                + static_cast<long>(g.curMapNodeY) * 100L + g.curMapNodeX;
        g.screenState=screen(screenName);
        // Vanilla can retain the previous boss-room sentinel on the next
        // act's unchosen map. Normalize only the complete public first-row
        // boundary; row 15 during an ordinary boss transition stays refused.
        if (g.screenState==ScreenState::MAP_SCREEN && g.act>=2 && g.act<=3
                && g.floorNum==17*(g.act-1) && g.curMapNodeX==-1
                && (g.curMapNodeY==-1 || g.curMapNodeY==15)
                && o.contains("mcpState") && o.at("mcpState").is_object()) {
            const auto &mcp=o.at("mcpState");
            if (mcp.value("screen_type",std::string())=="MAP"
                    && mcp.value("room_type",std::string())=="TreasureRoomBoss"
                    && mcp.value("room_phase",std::string())=="COMPLETE"
                    && mcp.value("ready_for_command",false) && !mcp.value("can_cancel",true)
                    && !mcp.value("can_proceed",true) && mcp.value("floor",-1)==g.floorNum
                    && mcp.contains("screen_state") && mcp.at("screen_state").is_object()) {
                const auto &ui=mcp.at("screen_state");
                if (!ui.value("first_node_chosen",true) && !ui.value("boss_available",true)
                        && ui.contains("current_node") && ui.at("current_node").is_object()
                        && ui.at("current_node").value("x",0)==-1
                        && ui.at("current_node").value("y",-2)==g.curMapNodeY
                        && ui.contains("next_nodes") && ui.at("next_nodes").is_array()
                        && o.contains("liveChoices") && o.at("liveChoices").is_array()) {
                    const auto &nodes=ui.at("next_nodes"), &choices=o.at("liveChoices");
                    bool firstRow=!nodes.empty() && nodes.size()<=7 && nodes.size()==choices.size();
                    std::set<int> columns;
                    for (std::size_t i=0;firstRow && i<nodes.size();++i) {
                        const auto &node=nodes[i], &choice=choices[i];
                        const int x=integer(node,"x",0,6);
                        firstRow=node.value("y",-1)==0 && columns.insert(x).second
                            && choice.value("x",-1)==x && choice.value("y",-1)==0
                            && primitive(choice,ScreenState::MAP_SCREEN)==search::GameAction(x).bits
                            && choice.at("liveAction").value("kind",std::string())=="choose"
                            && choice.at("liveAction").value("choiceIndex",0)==static_cast<int>(i)+1;
                    }
                    for (int x=0;firstRow && x<7;++x)
                        firstRow=(g.map->getNode(x,0).edgeCount>0)==(columns.count(x)>0);
                    if (firstRow) {
                        g.curMapNodeY=-1;
                        g.curRoom=Room::BOSS_TREASURE;
                    }
                }
            }
        }
        if (g.screenState == ScreenState::REST_ROOM && o.contains("details")
                && o.at("details").is_object() && o.at("details").contains("options")) {
            const auto &options = o.at("details").at("options");
            require(options.is_array(), "rest details.options must be an array");
            g.restRoomResolved = options.size() == 1 && options.at(0).is_number_integer()
                    && options.at(0).get<int>() == 6;
        }
        const auto &d=o.at("details"); require(d.is_object(),"details must be an object");
        const auto transition=d.contains("mechanicalTransition")?string(d,"mechanicalTransition"):std::string();
        if(transition=="boss_map" || transition=="selector_confirm" || transition=="boss_chest_reveal") {
            const auto &mcp=o.at("mcpState");
            const bool completedMapReturn = transition=="boss_map" && boolean(mcp,"can_cancel")
                    && mcp.value("cancel_button",std::string())=="return"
                    && mcp.value("room_type",std::string())=="RestRoom"
                    && mcp.value("room_phase",std::string())=="COMPLETE";
            require(boolean(mcp,"ready_for_command") && (!boolean(mcp,"can_cancel") || completedMapReturn),
                    "forced transition is not the sole available continuation");
            const J choices=mcp.contains("choice_list")?array(mcp,"choice_list",1):J::array();
            if(transition=="boss_map") {
                require(g.screenState==ScreenState::MAP_SCREEN && g.act<=3 && g.curMapNodeY==14
                        && string(mcp,"screen_type")=="MAP" && !boolean(mcp,"can_proceed")
                        && choices.size()==1 && boolean(d,"bossNodeAvailable")
                        && integer(d,"nodeChoices",0,0)==0,"unqualified forced boss map transition");
                validateForcedChoice(o,"choose");
            } else if(transition=="boss_chest_reveal") {
                require(g.screenState==ScreenState::TREASURE_ROOM && g.act<=3
                        && string(d,"chestType")=="BossChest" && !boolean(d,"opened")
                        && string(mcp,"screen_type")=="CHEST" && boolean(mcp,"can_proceed")
                        && choices.size()==1,"unqualified boss chest reveal");
                require(!d.contains("relics") && !d.contains("tier") && !d.contains("haveGold"),
                        "boss chest hidden offers must not be captured");
                const auto &live=array(o,"liveChoices",2);require(live.size()==2,"boss chest requires open and proceed");
                for(int i=0;i<2;++i) {
                    require(string(live[i].at("nativeAction"),"kind")=="option"
                            && integer(live[i].at("nativeAction"),"index",i,i)==i
                            && integer(live[i].at("nativeAction"),"group",0,0)==0
                            && string(live[i].at("liveAction"),"kind")== (i==0?"choose":"proceed"),
                            "boss chest open/proceed mapping mismatch");
                    if(i==0)integer(live[i].at("liveAction"),"choiceIndex",1,1);
                }
            } else {
                require(g.screenState==ScreenState::CARD_SELECT && string(d,"type")=="confirmation"
                        && string(mcp,"screen_type")=="GRID" && boolean(mcp,"can_proceed")
                        && choices.empty() && boolean(d,"isJustForConfirming")
                        && !boolean(d,"confirmScreenUp") && boolean(d,"confirm"),
                        "unqualified selector result confirmation");
                validateForcedChoice(o,"proceed");
            }
            next.forcedOocTransition=true;
        } else require(transition.empty() || g.screenState==ScreenState::EVENT_SCREEN,
                "mechanical event transition on non-event screen");
        if(!next.forcedOocTransition && g.screenState==ScreenState::MAP_SCREEN && g.curMapNodeY>=14)
            return {false,"UNSUPPORTED","V4_BOSS_MAP_TRANSITION"};
        if(next.forcedOocTransition) {
            // No native selector or encounter transition is synthesized for
            // these public UI actions. Validation above is the entire decision.
        } else if(g.screenState==ScreenState::TREASURE_ROOM) {
            if(!boolean(d,"opened")) {
                const int size=integer(d,"chestSize",0,2);
                const char *types[]={"SmallChest","MediumChest","LargeChest"};
                require(string(d,"chestType")==types[size],"chest size/type mismatch");
                require(!d.contains("haveGold") && !d.contains("tier"),
                        "hidden chest contents must not be captured");
                g.info.chestSize=static_cast<ChestSize>(size);
                // These placeholders are never scored directly. The existing
                // MCTS transition sampler replaces both from one shared roll.
                g.info.haveGold=false;
                g.info.tier=RelicTier::COMMON;
                next.hiddenTreasureContents=true;
            }
        } else if(g.screenState==ScreenState::REWARDS) {
            auto &r=g.info.rewardsContainer;
            for(const auto &v:array(d,"gold",2)) r.addGold(integerValue(v,0,1000000,"gold reward"));
            for(const auto &group:array(d,"cardRewards",5)) {
                require(group.is_array() && !group.empty() && group.size()<=4,"invalid card reward group");
                CardReward reward;for(const auto &v:group)reward.push_back(card(v));r.addCardReward(reward);
            }
            for(const auto &v:array(d,"relics",3))r.addRelic(id<RelicId>(v,RelicId::INVALID));
            for(const auto &v:array(d,"potions",5))r.addPotion(id<Potion>(v,Potion::INVALID));
            r.emeraldKey=boolean(d,"emeraldKey");r.sapphireKey=boolean(d,"sapphireKey");
            require(!(r.emeraldKey&&r.sapphireKey),"native reward keys are mutually exclusive");
            if(d.contains("parentPotionRewards") || d.contains("parentKnownRewards") || d.contains("parentUnrevealedCardRewards")) {
                const bool parentPotions=d.contains("parentPotionRewards");
                const bool known=d.contains("parentKnownRewards");
                const bool hasKnown=r.goldRewardCount>0 || r.relicCount>0 || r.emeraldKey || r.sapphireKey;
                require(known==hasKnown && (!known || boolean(d,"parentKnownRewards")),"unqualified public parent rewards");
                if(r.sapphireKey)require(r.relicCount>0
                    && integer(d,"sapphireRelicIndex",r.relicCount-1,r.relicCount-1)==r.relicCount-1,
                    "parent sapphire relic pairing missing");
                else require(!d.contains("sapphireRelicIndex"),"unexpected parent sapphire pairing");
                const int unopened=d.contains("parentUnrevealedCardRewards")
                    ? integer(d,"parentUnrevealedCardRewards",1,4) : 0;
                require((!parentPotions || boolean(d,"parentPotionRewards"))
                        && screenName=="card_reward" && r.cardRewardCount==1
                        && (parentPotions ? r.potionCount>0 : r.potionCount==0)
                        && (parentPotions || known || unopened>0),
                        "unqualified parent reward continuation");
                bool skip=false,leave=false;std::set<int> seen;
                for(const auto &choice:array(o,"liveChoices",1024)) {
                    const auto &n=choice.at("nativeAction");
                    if(string(n,"kind")=="skip") {
                        require(!leave && integer(n,"index",0,0)==0 && integer(n,"group",0,0)==0
                            && string(choice.at("liveAction"),"kind")=="skip","invalid card close mapping");
                        leave=true;continue;
                    }
                    require(string(n,"kind")=="card" && integer(n,"group",0,0)==0,"parent reward is not clickable on card screen");
                    const int index=integer(n,"index",0,5);
                    require(index<r.cardRewards[0].size() || index==5,"card continuation choice out of bounds");
                    require(seen.insert(index).second,"duplicate card continuation choice");
                    skip|=index==5;
                }
                require(skip && leave && seen.size()==static_cast<std::size_t>(r.cardRewards[0].size()+1),"incomplete card continuation mapping");
            }
        } else if(g.screenState==ScreenState::SHOP_ROOM) {
            auto &s=g.info.shop;
            auto offers=[&](const char *key,int count,auto load) {
                const auto &vs=array(d,key,count);require(vs.size()==static_cast<std::size_t>(count),"shop slot count mismatch");
                for(int i=0;i<count;++i)load(vs[i],i);
            };
            offers("cards",7,[&](const J &v,int i){ s.cardPrice(i)=integer(v,"price",-1,1000000);if(s.cardPrice(i)>=0)s.cards[i]=card(v.at("card")); });
            offers("relics",3,[&](const J &v,int i){ s.relicPrice(i)=integer(v,"price",-1,1000000);if(s.relicPrice(i)>=0)s.relics[i]=id<RelicId>(v.at("id"),RelicId::INVALID); });
            offers("potions",3,[&](const J &v,int i){ s.potionPrice(i)=integer(v,"price",-1,1000000);if(s.potionPrice(i)>=0)s.potions[i]=id<Potion>(v.at("id"),Potion::INVALID); });
            s.removeCost=integer(d,"removeCost",-1,1000000);
        } else if(g.screenState==ScreenState::BOSS_RELIC_REWARDS) {
            const auto &rs=array(d,"relics",3);require(rs.size()==3,"three boss relics required");
            for(int i=0;i<3;++i)g.info.bossRelics[i]=id<RelicId>(rs[i],RelicId::INVALID);
        } else if(g.screenState==ScreenState::CARD_SELECT) {
            const auto kind=string(d,"type");
            if(kind=="upgrade")g.info.selectScreenType=CardSelectScreenType::UPGRADE;
            else if(kind=="remove")g.info.selectScreenType=CardSelectScreenType::REMOVE;
            else if(kind=="transform")g.info.selectScreenType=CardSelectScreenType::TRANSFORM;
            else if(kind=="transform_upgrade")g.info.selectScreenType=CardSelectScreenType::TRANSFORM_UPGRADE;
            else if(kind=="duplicate")g.info.selectScreenType=CardSelectScreenType::DUPLICATE;
            else if(kind=="bottle")g.info.selectScreenType=CardSelectScreenType::BOTTLE;
            else if(kind=="bonfire")g.info.selectScreenType=CardSelectScreenType::BONFIRE_SPIRITS;
            else if(kind=="obtain")g.info.selectScreenType=CardSelectScreenType::OBTAIN;
            else return {false,"UNSUPPORTED","selector_type:"+kind};
            g.info.toSelectCount=integer(d,"requiredPicks",1,3);
            if(d.contains("afterSelect")) {
                require(string(d,"afterSelect")=="designer_upgrade" && kind=="remove"
                        && g.info.toSelectCount==1 && string(d,"event")=="Designer"
                        && string(d,"eventPhase")=="DONE" && string(d,"eventOption")=="REMOVE_AND_UPGRADE",
                        "unqualified selector continuation");
            }
            CardType bottleType=CardType::INVALID;
            if(kind=="bottle") {
                const auto type=string(d,"bottleType");
                if(type=="attack")bottleType=CardType::ATTACK;
                else if(type=="skill")bottleType=CardType::SKILL;
                else if(type=="power")bottleType=CardType::POWER;
                else require(false,"unknown bottle selector card type");
                require(g.info.toSelectCount==1,"bottle selector requires one pick");
            }
            std::set<int> targets;
            std::set<CardId> offeredIds;
            std::set<std::string> offeredUuids;
            if(kind=="obtain") {
                require(string(d,"event")=="The Library" && integer(d,"phase",1,1)==1
                        && g.info.toSelectCount==1 && integer(d,"completedPicks",0,0)==0
                        && !boolean(d,"confirm"),"unqualified Library selector continuation");
                const auto &mcp=o.at("mcpState");
                require(string(mcp,"screen_type")=="GRID" && boolean(mcp,"ready_for_command")
                        && !boolean(mcp,"can_cancel") && !boolean(mcp,"can_proceed")
                        && array(mcp,"choice_list",20).size()==20,"Library MCP availability mismatch");
                require(array(d,"cards",20).size()==20 && array(o,"liveChoices",20).size()==20,
                        "Library requires twenty public offers");
                for(const auto &offer:array(d,"cards",20)) {
                    const auto c=card(offer.at("card"));
                    require(c==g.previewObtainCard(Card(c.id)),"Library offer preview upgrade mismatch");

                }
            }
            const auto selectedCard=[&](const J &v) {
                if(kind=="obtain") {
                    require(!v.contains("deckIndex"),"Library offer must not target the deck");
                    const auto c=card(v.at("card"));
                    require(getCardColor(c.id)==CardColor::RED && (c.getRarity()==CardRarity::COMMON
                            || c.getRarity()==CardRarity::UNCOMMON || c.getRarity()==CardRarity::RARE),
                            "Library requires reward-pool class cards");
                    require(offeredIds.insert(c.id).second && offeredUuids.insert(string(v,"uuid")).second
                            && !string(v,"uuid").empty(),"duplicate Library offer identity");
                    require(c==g.previewObtainCard(Card(c.id)),"Library offer preview upgrade mismatch");
                    return SelectScreenCard(c,-1);
                }
                const auto idx=integer(v,"deckIndex",0,g.deck.size()-1);
                const auto c=card(v.at("card"));require(c==g.deck.cards[idx],"selector card does not match deck");
                require(targets.insert(idx).second,"duplicate physical selector target");
                if(kind=="bottle")
                    require(c.getType()==bottleType && !g.deck.isCardBottled(idx),
                            "ineligible bottle selector target");
                return SelectScreenCard(c,idx);
            };
            const int completed=integer(d,"completedPicks",0,3);
            require(completed<g.info.toSelectCount,"selector has no remaining picks");
            if(completed>0 || d.contains("selectedCards")) {
                const auto &selected=array(d,"selectedCards",3);
                require(selected.size()==static_cast<std::size_t>(completed),
                        "selector completed-pick count mismatch");
                for(const auto &v:selected)g.info.haveSelectedCards.push_back(selectedCard(v));
            }
            for(const auto &v:array(d,"cards",96))
                g.info.toSelectCards.push_back(selectedCard(v));
            require(g.info.toSelectCards.size()>=g.info.toSelectCount-completed,
                    "selector has fewer targets than remaining picks");
            if(d.contains("selectorPreview")) {
                require(boolean(d,"selectorPreview") && (kind=="upgrade" || kind=="remove" || kind=="transform" || kind=="bonfire")
                        && g.info.toSelectCount==1 && completed==0 && boolean(d,"confirmScreenUp")
                        && !boolean(d,"isJustForConfirming") && boolean(d,"confirm"),"unqualified selector preview");
                const auto &mcp=o.at("mcpState");
                require(string(mcp,"screen_type")=="GRID" && boolean(mcp,"ready_for_command")
                        && boolean(mcp,"can_cancel") && boolean(mcp,"can_proceed")
                        && (!mcp.contains("choice_list") || array(mcp,"choice_list",0).empty()),"selector preview MCP availability mismatch");
                const int hovered=integer(d,"previewDeckIndex",0,g.deck.size()-1);
                require(targets.count(hovered)==1,"selector preview target missing");
                auto eligible=g;eligible.openCardSelectScreen(g.info.selectScreenType,1);
                std::set<int> expected;for(const auto &c:eligible.info.toSelectCards)expected.insert(c.deckIdx);
                require(targets==expected,"selector preview eligible targets mismatch");
                const auto &choices=array(o,"liveChoices",2);require(choices.size()==2,"selector preview requires confirm and cancel");
                for(int i=0;i<2;++i)require(string(choices[i].at("nativeAction"),"kind")=="option"
                        && integer(choices[i].at("nativeAction"),"index",i,i)==i
                        && integer(choices[i].at("nativeAction"),"group",0,0)==0
                        && string(choices[i].at("liveAction"),"kind")== (i==0?"proceed":"cancel"),
                        "selector preview action mismatch");
                next.selectorPreview=true;next.selectorPreviewDeckIndex=hovered;
            }
            if(kind=="obtain") for(int i=0;i<20;++i) {
                const auto &choice=o.at("liveChoices")[i];
                const auto &native=choice.at("nativeAction"), &hint=choice.at("liveAction");
                require(string(native,"kind")=="option" && integer(native,"index",i,i)==i
                        && (!native.contains("group") || integer(native,"group",0,0)==0)
                        && string(hint,"kind")=="choose" && integer(hint,"choiceIndex",i+1,i+1)==i+1
                        && string(choice,"uuid")==string(d.at("cards")[i],"uuid"),
                        "Library offer/live order mismatch");
            }
        } else if(g.screenState==ScreenState::EVENT_SCREEN) {
            const auto event=string(d,"event");
            g.curEvent=event=="Neow" ? Event::NEOW : id<Event>(d.at("event"),Event::INVALID);
            g.info.eventData=integer(d,"eventData",0,100);
            g.info.phase=integer(d,"phase",0,100);
            // Fields used by native candidate/semantic enumeration are explicit even when inactive.
            g.info.upgradeOne=boolean(d,"upgradeOne");g.info.cleanUpIsRemoveCard=boolean(d,"cleanUpIsRemoveCard");
            g.info.skillCardDeckIdx=integer(d,"skillCardDeckIdx",-1,g.deck.size()-1);
            g.info.powerCardDeckIdx=integer(d,"powerCardDeckIdx",-1,g.deck.size()-1);
            g.info.attackCardDeckIdx=integer(d,"attackCardDeckIdx",-1,g.deck.size()-1);
            g.info.potionIdx=integer(d,"potionIdx",-1,4);g.info.gold=integer(d,"gold",-1,1000000);
            g.info.cardIdx=integer(d,"cardIdx",-1,g.deck.size()-1);
            if(g.curEvent==Event::WORLD_OF_GOOP && !d.contains("mechanicalTransition"))
                g.info.goldLoss=integer(d,"goldLoss",0,g.gold);
            if(d.contains("mechanicalTransition")) {
                const auto transition=string(d,"mechanicalTransition");
                const auto &eventCapture=o.at("event");
                const auto phase=string(eventCapture,"phase");
                const auto capturedId=string(eventCapture,"id");
                const bool neow=g.curEvent==Event::NEOW && capturedId=="Neow"
                        && ((transition=="neow_intro" && (phase=="0" || phase=="1"))
                            || (transition=="event_leave" && phase=="99"));
                const bool goop=g.curEvent==Event::WORLD_OF_GOOP && capturedId=="World of Goop"
                        && transition=="event_leave" && phase=="RESULT";
                const bool forge=g.curEvent==Event::OMINOUS_FORGE && capturedId=="Accursed Blacksmith"
                        && transition=="event_leave" && phase=="2";
                const bool writing=g.curEvent==Event::ANCIENT_WRITING && capturedId=="Back to Basics"
                        && transition=="event_leave" && phase=="COMPLETE";
                const bool library=g.curEvent==Event::THE_LIBRARY && capturedId=="The Library"
                        && transition=="event_leave" && phase=="1";
                const bool vanilla=d.contains("eventContract") && string(d,"eventContract")=="vanilla_v1"
                        && capturedId==J(g.curEvent).get<std::string>()
                        && ((transition=="event_leave" && eventPage(eventLeavePages,g.curEvent,phase))
                            || (transition=="event_continue" && eventPage(eventContinuePages,g.curEvent,phase)));
                require(neow || goop || forge || writing || library || vanilla,"unqualified mechanical event transition");
                const auto &options=array(eventCapture,"options",1);
                require(options.size()==1 && integer(options.at(0),"index",0,0)==0
                        && !boolean(options.at(0),"disabled"),
                        "mechanical event requires sole enabled slot zero");
                const auto &choices=array(o,"liveChoices",1);
                require(choices.size()==1,"mechanical event requires one live choice");
                const auto &native=choices.at(0).at("nativeAction");
                require(string(native,"kind")=="option" && integer(native,"index",0,0)==0
                        && integer(native,"group",0,0)==0,
                        "mechanical event native choice mismatch");
                const auto &hint=choices.at(0).at("liveAction");
                require(string(hint,"kind")=="choose" && integer(hint,"choiceIndex",1,1)==1,
                        "mechanical event live choice mismatch");
                if(g.curEvent==Event::WHEEL_OF_CHANGE && phase=="SPIN_READY")
                    require(boolean(d,"startSpin") && !boolean(d,"buttonPressed")
                            && d.at("bounceTimer").is_number() && d.at("bounceTimer").get<double>()==0,
                            "Wheel spin readiness mismatch");
                next.mechanicalEventTransition=true;
            } else if(g.curEvent==Event::OMINOUS_FORGE || g.curEvent==Event::ANCIENT_WRITING) {
                const bool forge=g.curEvent==Event::OMINOUS_FORGE;
                const auto &captured=o.at("event");
                require(string(captured,"id")==event && string(captured,"phase")== (forge?"0":"INTRO")
                        && g.info.phase==0 && g.info.eventData==0,"unqualified forge/writing initial phase");
                require(forge || g.deck.getTransformableCount(1)>0,"writing has no removable card");
                const int first=forge && g.deck.getUpgradeableCount()==0 ? 1 : 0;
                const int count=(forge?3:2)-first;
                const auto &options=array(captured,"options",3);
                const auto &choices=array(o,"liveChoices",3);
                require(options.size()==count && choices.size()==count,"forge/writing choice count mismatch");
                for(int i=0;i<count;++i) {
                    require(integer(options[i],"index",first+i,first+i)==first+i && !boolean(options[i],"disabled"),
                            "forge/writing enabled slot mismatch");
                    const auto &native=choices[i].at("nativeAction");
                    const auto &hint=choices[i].at("liveAction");
                    require(string(native,"kind")=="option" && integer(native,"index",first+i,first+i)==first+i
                            && (!native.contains("group") || integer(native,"group",0,0)==0)
                            && string(hint,"kind")=="choose" && integer(hint,"choiceIndex",i+1,i+1)==i+1,
                            "forge/writing live mapping mismatch");
                }
            } else if(g.curEvent==Event::NEOW) {
                const auto &ns=array(d,"neow",4);
                require(ns.size()==2 || ns.size()==4,"two or four Neow offers required");
                g.info.neowRewards.fill({Neow::Bonus::INVALID,Neow::Drawback::INVALID});
                for(std::size_t i=0;i<ns.size();++i) {
                    g.info.neowRewards[i].r=id<Neow::Bonus>(ns[i].at("bonus"),Neow::Bonus::INVALID);
                    g.info.neowRewards[i].d=id<Neow::Drawback>(ns[i].at("drawback"),Neow::Drawback::INVALID);
                }
            }
            if (g.curEvent == Event::THE_LIBRARY && !next.mechanicalEventTransition) {
                g.info.hpAmount0=integer(d,"hpAmount0",0,g.maxHp);
                const auto &captured=o.at("event");
                require(string(captured,"id")=="The Library" && string(captured,"phase")=="0"
                        && g.info.phase==0 && g.info.eventData==0,"unqualified Library initial phase");
                require(g.info.hpAmount0==static_cast<int>(g.maxHp*(g.ascension>=15?0.2f:0.33f)+0.5f),
                        "Library public heal amount mismatch");
                const auto &options=array(captured,"options",2), &choices=array(o,"liveChoices",2);
                require(options.size()==2 && choices.size()==2,"Library requires two initial options");
                for(int i=0;i<2;++i) {
                    const auto &native=choices[i].at("nativeAction"), &hint=choices[i].at("liveAction");
                    require(integer(options[i],"index",i,i)==i && !boolean(options[i],"disabled")
                            && string(native,"kind")=="option" && integer(native,"index",i,i)==i
                            && (!native.contains("group") || integer(native,"group",0,0)==0)
                            && string(hint,"kind")=="choose" && integer(hint,"choiceIndex",i+1,i+1)==i+1,
                            "Library initial live mapping mismatch");
                }
                next.hiddenEventRewardPity=!next.rewardPityHistoryComplete;
            }
            if (g.curEvent == Event::HYPNOTIZING_COLORED_MUSHROOMS
                    || g.curEvent == Event::MYSTERIOUS_SPHERE)
                next.hiddenEventRewardPity=!next.rewardPityHistoryComplete && !next.mechanicalEventTransition;
            if(!next.mechanicalEventTransition && g.curEvent==Event::MATCH_AND_KEEP)importMatchAndKeep(next,o);
            if(!next.mechanicalEventTransition && eventDecisionPages.count(g.curEvent))
                importEventContract(next,o);
        }
        for(const auto &choice:array(o,"liveChoices",1024)) {
            primitive(choice,g.screenState);validateHint(choice.at("liveAction"));
            if (choice.at("nativeAction").at("kind")=="discard_potion") {
                const auto slot=integer(choice.at("nativeAction"),"index",0,g.potionCapacity-1);
                require(string(choice.at("liveAction"),"kind")=="discard_potion"
                    && integer(choice.at("liveAction"),"potionSlot",slot+1,slot+1)==slot+1,
                    "discard potion slot mapping mismatch");
            }
        }
        if (!deferredUnsupportedReason.empty()) {
            // Validate that every visible gold reward has exactly one
            // distinct, well-formed captured click before allowing the
            // narrowly scoped pass-through. The regular unsupported boundary
            // remains in force after the last gold disappears.
            std::set<std::string> goldActions;
            int goldChoiceCount = 0;
            const auto &gold = array(d,"gold",2);
            for (const auto &choice : array(o,"liveChoices",1024)) {
                if (string(choice.at("nativeAction"),"kind") != "gold") continue;
                const int nativeIndex = integer(choice.at("nativeAction"),"index",0,255);
                require(nativeIndex < static_cast<int>(gold.size()),
                        "gold native index outside visible rewards");
                const auto &action = choice.at("liveAction");
                require(string(action,"kind") == "choose","gold choice must lower to choose");
                require(goldActions.insert(action.dump()).second,"duplicate gold live mapping");
                ++goldChoiceCount;
            }
            require(goldChoiceCount == static_cast<int>(gold.size()),
                    "gold reward/live mapping count mismatch: rewards="
                    + std::to_string(gold.size()) + " choices=" + std::to_string(goldChoiceCount));
            if (goldChoiceCount == 0 && !forcedRewardPotionLiveAction(next))
                return {false,"UNSUPPORTED",deferredUnsupportedReason};
        }
        if(next.mechanicalEventTransition || next.forcedOocTransition) {
            next.mctsRoot.supported=false;
            next.mctsRoot.reason=next.mechanicalEventTransition
                ?"MECHANICAL_EVENT_TRANSITION_ONLY":"FORCED_OOC_TRANSITION_ONLY";
        } else next.mctsRoot = makeMctsRoot(next);
        out=std::move(next);
        return {true,{},{}};
    } catch(const std::exception &e) {
        return {false,"SCHEMA_MISMATCH",e.what()};
    }
}

J lowerLiveOocAction(const LiveOocStateV1 &state,std::uint32_t bits) {
    J found;int count=0;
    for(const auto &c:state.ooc.at("liveChoices"))if(primitive(c,state.projected.screenState)==bits){found=c.at("liveAction");++count;}
    require(count==1,"OOC primitive mapping expected one occurrence; matches="+std::to_string(count));
    return found;
}
void validateLiveOocActionSet(const LiveOocStateV1 &state,const std::vector<std::uint32_t> &bits,
                              bool allowEquivalentChoices) {
    std::set<std::uint32_t> expected(bits.begin(),bits.end()), observed;
    std::set<std::string> retainedChoices;
    std::set<std::uint32_t> omittedRewardAliases;
    std::map<std::uint32_t,std::string> choiceByPrimitive;
    if (allowEquivalentChoices && (state.projected.screenState == ScreenState::CARD_SELECT
            || state.projected.screenState == ScreenState::REWARDS)) {
        const auto bindings=search::enumerateOocSemanticPrimitiveBindings(state.projected);
        require(bindings.supported && bindings.complete,"native/live semantic enumeration incomplete");
        for(const auto &binding:bindings.bindings) {
            const auto key=search::canonicalOocMctsChoiceKey(binding.semantic, &state.projected);
            require(choiceByPrimitive.emplace(binding.primitiveBits,key).second,
                    "duplicate native semantic primitive mapping");
            if(expected.count(binding.primitiveBits)) retainedChoices.insert(key);
        }
    }
    // Multiple semantic MCTS candidates may intentionally share one source
    // click; validate the source mapping as a set, not as a semantic list.
    for(const auto &c:state.ooc.at("liveChoices")) {
        const auto bit = primitive(c,state.projected.screenState);
        if (!expected.count(bit)) {
            const auto action = search::GameAction(bit);
            const bool displayedPrismaticShard = state.projected.screenState == ScreenState::SHOP_ROOM
                && action.getRewardsActionType() == search::GameAction::RewardsActionType::RELIC
                && action.getIdx1() >= 0 && action.getIdx1() < 3
             && state.projected.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
            const auto choice=choiceByPrimitive.find(bit);
            const bool equivalent=choice!=choiceByPrimitive.end()
                && retainedChoices.count(choice->second);
            if (equivalent && state.projected.screenState == ScreenState::REWARDS) {
                require(omittedRewardAliases.insert(bit).second, "duplicate observed reward alias");
                const auto representative = std::find_if(bits.begin(), bits.end(), [&](auto retained) {
                    return choiceByPrimitive.at(retained) == choice->second;
                });
                require(representative != bits.end()
                        && lowerLiveOocAction(state, *representative) == c.at("liveAction"),
                        "equivalent reward primitives have different live actions");
            }
            require(displayedPrismaticShard || equivalent,
                    "native/live candidate enumeration disagreement: unexpected "
                    + c.at("nativeAction").dump());
            continue;
        }
        require(observed.insert(bit).second,"duplicate observed primitive mapping");
    }
    require(expected==observed,"native/live candidate enumeration disagreement");
    for(const auto b:bits)lowerLiveOocAction(state,b);
}
std::vector<std::uint32_t> liveOocPrimitiveBits(const LiveOocStateV1 &state) {
    std::vector<std::uint32_t> bits;
    for (const auto &choice : state.ooc.at("liveChoices"))
        bits.push_back(primitive(choice, state.projected.screenState));
    return bits;
}
std::optional<J> forcedRewardGoldLiveAction(const LiveOocStateV1 &state) {
    if (state.projected.screenState != sts::ScreenState::REWARDS) return std::nullopt;
    int goldChoices = 0;
    std::set<std::string> actions;
    const J *first = nullptr;
    for (const auto &choice : state.ooc.at("liveChoices")) {
        if (choice.at("nativeAction").value("kind", std::string()) != "gold") continue;
        // Keep this tied to the captured choice entry because multiple Java
        // gold rows may lower to the same native primitive bits. Execute one
        // captured choice per observation and let the caller re-observe.
        primitive(choice, state.projected.screenState); // validate native identity
        require(integer(choice.at("nativeAction"),"index",0,255)
                    < static_cast<int>(state.ooc.at("details").at("gold").size()),
                "gold native index outside visible rewards");
        const auto &action = choice.at("liveAction");
        require(string(action,"kind") == "choose","gold choice must lower to choose");
        require(actions.insert(action.dump()).second,"duplicate gold live mapping");
        if (!first) first = &choice;
        ++goldChoices;
    }
    if (goldChoices == 0) return std::nullopt;
    require(state.ooc.at("details").at("gold").size() == static_cast<std::size_t>(goldChoices),
            "gold reward/live mapping count mismatch: rewards="
            + std::to_string(state.ooc.at("details").at("gold").size())
            + " choices=" + std::to_string(goldChoices));
    return first->at("liveAction");
}
std::optional<J> forcedRewardPotionLiveAction(const LiveOocStateV1 &state) {
    const auto &g=state.projected;
    if(g.screenState!=ScreenState::REWARDS || g.potionCount>=g.potionCapacity || g.hasRelic(RelicId::SOZU)
            || state.ooc.value("screen",std::string())=="card_reward" || g.info.rewardsContainer.relicCount>0)
        return std::nullopt;
    const auto &potions=array(state.ooc.at("details"),"potions",5);
    if(potions.empty() || static_cast<int>(potions.size())>g.potionCapacity-g.potionCount) return std::nullopt;
    std::set<int> indices;std::set<std::string> actions;const J *first=nullptr;
    for(const auto &choice:state.ooc.at("liveChoices")) {
        if(choice.at("nativeAction").value("kind",std::string())!="potion") continue;
        primitive(choice,g.screenState);
        const int index=integer(choice.at("nativeAction"),"index",0,static_cast<int>(potions.size())-1);
        const auto &action=choice.at("liveAction");
        require(string(action,"kind")=="choose" && integer(action,"choiceIndex",1,1024)>0,"potion must lower to choose");
        require(indices.insert(index).second && actions.insert(action.dump()).second,"duplicate potion live mapping");
        if(!first)first=&choice;
    }
    require(indices.size()==potions.size(),"potion reward/live mapping count mismatch");
    return first->at("liveAction");
}
} // namespace one_combat::advisor
