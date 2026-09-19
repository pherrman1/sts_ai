#include "live_silver_importer.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <unordered_map>

#include "combat/CardInstance.h"
#include "constants/CharacterClasses.h"
#include "constants/MonsterIds.h"
#include "constants/MonsterMoves.h"
#include "constants/MonsterStatusEffects.h"
#include "constants/PlayerStatusEffects.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "constants/SaveFileMappings.h"

namespace one_combat::advisor {
namespace {
using json = nlohmann::json;
struct CardRecord { std::string uuid; silver_bridge::CardWire wire; };

std::uint64_t fnv1a(const std::string &s, std::uint64_t h=1469598103934665603ULL) {
    for (unsigned char c : s) { h ^= c; h *= 1099511628211ULL; } return h;
}
bool integer(const json &o, const char *n, int &v) {
    if (!o.contains(n) || !o.at(n).is_number_integer()) return false;
    v=o.at(n).get<int>(); return true;
}
bool boolean(const json &o, const char *n, bool &v) {
    if (!o.contains(n) || !o.at(n).is_boolean()) return false;
    v=o.at(n).get<bool>(); return true;
}
bool forbiddenRng(const json &o) {
    for (const char *n : {"rng","aiRng","cardRandomRng","miscRng","monsterHpRng","potionRng","shuffleRng","seed"})
        if (o.contains(n)) return true;
    return false;
}
bool parseCard(const json &j, CardRecord &r) {
    if (!j.is_object() || !j.contains("id") || !j.at("id").is_string()
        || !j.contains("uuid") || !j.at("uuid").is_string()
        || !j.contains("misc") || !j.at("misc").is_number_integer()
        || !j.contains("cost") || !j.at("cost").is_number_integer()
        || !j.contains("costForTurn") || !j.at("costForTurn").is_number_integer()
        || !j.contains("upgraded") || !j.at("upgraded").is_boolean()
        || !j.contains("freeToPlayOnce") || !j.at("freeToPlayOnce").is_boolean()
        || !j.contains("retain") || !j.at("retain").is_boolean()) return false;
    try {
        const auto id=j.at("id").get<sts::CardId>(); if (id==sts::CardId::INVALID) return false;
        r.uuid=j.at("uuid").get<std::string>(); r.wire.id=static_cast<std::int16_t>(id);
        r.wire.specialData=j.at("misc").get<std::int16_t>(); r.wire.cost=j.at("cost").get<std::int16_t>();
        r.wire.costForTurn=j.at("costForTurn").get<std::int16_t>(); r.wire.upgraded=j.at("upgraded").get<bool>();
        r.wire.freeToPlayOnce=j.at("freeToPlayOnce").get<bool>(); r.wire.retain=j.at("retain").get<bool>();
        return true;
    } catch (...) { return false; }
}
bool cardLess(const silver_bridge::CardWire &a,const silver_bridge::CardWire &b) {
    if(a.id!=b.id)return a.id<b.id; if(a.uniqueId!=b.uniqueId)return a.uniqueId<b.uniqueId;
    if(a.specialData!=b.specialData)return a.specialData<b.specialData; if(a.cost!=b.cost)return a.cost<b.cost;
    if(a.costForTurn!=b.costForTurn)return a.costForTurn<b.costForTurn; if(a.upgraded!=b.upgraded)return a.upgraded<b.upgraded;
    if(a.freeToPlayOnce!=b.freeToPlayOnce)return a.freeToPlayOnce<b.freeToPlayOnce; return a.retain<b.retain;
}
bool isStrike(const silver_bridge::CardWire &c){return sts::CardInstance(static_cast<sts::CardId>(c.id)).isStrikeCard();}
bool isBlood(const silver_bridge::CardWire &c){return sts::CardInstance(static_cast<sts::CardId>(c.id)).isBloodCard();}
bool isNormality(const silver_bridge::CardWire &c){return c.id==static_cast<std::int16_t>(sts::CardId::NORMALITY);}
bool isPain(const silver_bridge::CardWire &c){return c.id==static_cast<std::int16_t>(sts::CardId::PAIN);}
template<class P> int count(const std::vector<silver_bridge::CardWire>&v,P p){return std::count_if(v.begin(),v.end(),p);}

int monsterId(const std::string &id) {
    if(id=="Cultist")return static_cast<int>(sts::MonsterId::CULTIST);
    if(id=="JawWorm")return static_cast<int>(sts::MonsterId::JAW_WORM);
    if(id=="Gremlin Nob"||id=="GremlinNob")return static_cast<int>(sts::MonsterId::GREMLIN_NOB);
    return 0;
}
int moveId(const std::string &id,int m) {
    using M=sts::MonsterMoveId;
    if(id=="Cultist")return m==3?int(M::CULTIST_INCANTATION):m==1?int(M::CULTIST_DARK_STRIKE):0;
    if(id=="JawWorm")return m==1?int(M::JAW_WORM_CHOMP):m==2?int(M::JAW_WORM_THRASH):m==3?int(M::JAW_WORM_BELLOW):0;
    if(id=="Gremlin Nob"||id=="GremlinNob")return m==3?int(M::GREMLIN_NOB_BELLOW):m==1?int(M::GREMLIN_NOB_RUSH):m==2?int(M::GREMLIN_NOB_SKULL_BASH):0;
    return 0;
}
bool power(const json &j,std::string &id,int &amount){return j.is_object()&&j.contains("id")&&j.at("id").is_string()&&integer(j,"amount",amount)&&(id=j.at("id").get<std::string>(),true);}
bool playerPowers(const json &a,silver_bridge::PlayerWire &p) {
    if(!a.is_array())return false;
    for(const auto &j:a){std::string id;int n=0;if(!power(j,id,n)||n<=0)return false;
        if(id!="Vulnerable")return false; constexpr int s=int(PlayerStatus::VULNERABLE);
        p.statusBits0|=1ULL<<s;p.statusMap.emplace_back(s,n);
    } return true;
}
bool monsterPowers(const json&a,const std::string&id,silver_bridge::MonsterWire&m){
    if(!a.is_array())return false;bool unique=false;
    for(const auto&j:a){std::string p;int n=0;if(!power(j,p,n)||n<=0)return false;
        // Native Strength is a dedicated scalar; unlike ordinary monster
        // statuses, applying it does not set the corresponding status bit.
        if(p=="Strength"){m.strength=n;}
        else if(p=="Vulnerable"){m.vulnerable=n;m.statusBits|=1ULL<<int(sts::MonsterStatus::VULNERABLE);}
        else if(p=="Ritual"&&id=="Cultist"&&!unique){unique=true;m.uniquePower0=n;m.statusBits|=1ULL<<int(sts::MonsterStatus::RITUAL);}
        else if(p=="Enrage"&&(id=="Gremlin Nob"||id=="GremlinNob")&&!unique){unique=true;m.uniquePower0=n;m.statusBits|=1ULL<<int(sts::MonsterStatus::ENRAGE);}
        else return false;
    }return true;
}
}

SilverRootImportResult importSilverRoot(const json &observation) {
    SilverRootImportResult result; auto &w=result.wire;
    const auto bad=[&](const char*r){result.reason=r;return result;};
    if(!observation.contains("silverRoot")||!observation.at("silverRoot").is_object())return bad("silver_root_missing");
    const auto&r=observation.at("silverRoot"); if(forbiddenRng(observation)||forbiddenRng(r))return bad("silver_rng_field");
    int schema=0,playerTurn=0,decision=0,act=0,floor=0,asc=0,hp=0,maxHp=0,gold=0,potionCapacity=0;bool burning=false;
    if(!integer(r,"schemaVersion",schema)||schema!=3)return bad("silver_schema_version");
    if(!integer(r,"playerTurn",playerTurn)||playerTurn<1||!integer(r,"decisionInTurn",decision)||decision<0)return bad("silver_turn_state");
    result.playerTurn=playerTurn;result.decisionInTurn=decision;
    if(!integer(r,"act",act)||act!=1)return bad("silver_act"); if(!integer(r,"floor",floor)||floor<1)return bad("silver_floor");
    if(!integer(r,"ascension",asc)||!integer(r,"hp",hp)||!integer(r,"maxHp",maxHp)||!integer(r,"gold",gold)||!integer(r,"potionCapacity",potionCapacity)||!boolean(r,"burningElite",burning))return bad("silver_root_state");
    if(burning)return bad("silver_burning_elite"); if(!r.contains("roomClass")||!r.at("roomClass").is_string())return bad("silver_room_class");
    if(observation.value("character",std::string())!="IRONCLAD"||r.value("character",std::string())!="IRONCLAD")return bad("silver_character");
    if(!r.contains("combat")||!r.at("combat").is_object())return bad("silver_combat_missing");const auto&c=r.at("combat");
    if(forbiddenRng(c))return bad("silver_rng_field");bool dome=false,eye=false,select=false,resolving=false;
    if(!boolean(c,"runicDome",dome)||dome)return bad("silver_runic_dome");if(!boolean(c,"frozenEye",eye)||eye)return bad("silver_frozen_eye");
    if(!boolean(c,"cardSelect",select)||!boolean(c,"resolving",resolving)||select||resolving)return bad("silver_card_select");
    int turn=0,energy=0,block=0,played=0,attacks=0,skills=0,discarded=0,lastTarget=1,lastDamage=0,timesDamaged=0;bool vulnerableSeen=false;
    if(!integer(c,"turn",turn)||turn!=playerTurn||!integer(c,"energy",energy)||!integer(c,"block",block)||!integer(c,"cardsPlayedThisTurn",played)||played!=decision||!integer(c,"attacksPlayedThisTurn",attacks)||!integer(c,"skillsPlayedThisTurn",skills)||!integer(c,"cardsDiscardedThisTurn",discarded)||!integer(c,"lastTargetedMonster",lastTarget)||!integer(c,"lastAttackUnblockedDamage",lastDamage)||!integer(c,"timesDamagedThisCombat",timesDamaged)||!boolean(c,"playerVulnerableSeen",vulnerableSeen))return bad("silver_player_state");
    if(played<0||attacks<0||skills<0||discarded<0||attacks+skills!=played||lastTarget<0||lastTarget>1)return bad("silver_player_state");
    if(potionCapacity!=3)return bad("silver_unmapped_potion_state");

    std::vector<CardRecord> cards;
    for(const char*p:{"hand","draw","discard","exhaust"}){if(!c.contains(p)||!c.at(p).is_array())return bad("silver_missing_state");for(const auto&j:c.at(p)){CardRecord x;if(!parseCard(j,x))return bad("silver_unknown_card");cards.push_back(x);}}
    if(cards.size()!=10)return bad("silver_nonstarter_deck");int strikes=0,defends=0,bashes=0;
    for(const auto&x:cards){auto id=static_cast<sts::CardId>(x.wire.id);int cost=1;if(id==sts::CardId::STRIKE_RED)++strikes;else if(id==sts::CardId::DEFEND_RED)++defends;else if(id==sts::CardId::BASH){++bashes;cost=2;}else return bad("silver_nonstarter_deck");if(x.wire.upgraded||x.wire.specialData||x.wire.cost!=cost||x.wire.costForTurn!=cost||x.wire.freeToPlayOnce||x.wire.retain)return bad("silver_nonstarter_deck");}
    if(strikes!=5||defends!=4||bashes!=1)return bad("silver_nonstarter_deck");
    std::sort(cards.begin(),cards.end(),[](const auto&a,const auto&b){return a.uuid<b.uuid;});std::set<std::string>ids;std::unordered_map<std::string,silver_bridge::CardWire>by;
    for(int i=0;i<int(cards.size());++i){if(cards[i].uuid.empty()||!ids.insert(cards[i].uuid).second)return bad("silver_card_identity");cards[i].wire.uniqueId=i;by.emplace(cards[i].uuid,cards[i].wire);}
    const auto pile=[&](const char*n,std::vector<silver_bridge::CardWire>&out,bool sort){for(const auto&j:c.at(n))out.push_back(by.at(j.at("uuid").get<std::string>()));if(sort)std::sort(out.begin(),out.end(),cardLess);};
    pile("hand",w.hand,false);pile("draw",w.drawPile.unknown,true);pile("discard",w.discardPile.unknown,true);pile("exhaust",w.exhaustPile.unknown,true);
    w.drawPile.valid=w.discardPile.valid=w.exhaustPile.valid=true;w.nextUniqueCardId=10;w.strikeCount=strikes;
    w.handNormalityCount=count(w.hand,isNormality);w.handPainCount=count(w.hand,isPain);w.handBloodCardCount=count(w.hand,isBlood);w.drawPileBloodCardCount=count(w.drawPile.unknown,isBlood);w.discardPileBloodCardCount=count(w.discardPile.unknown,isBlood);
    w.version=silver_bridge::BattleStateWire::kVersion;w.valid=true;w.floorNum=floor;w.act=act;w.ascension=asc;w.inputState=1;w.monsterTurnIdx=playerTurn==1?6:1;w.turn=playerTurn-1;w.cardsDrawn=playerTurn*5;w.potionCapacity=3;w.potions.fill(static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT));
    auto&p=w.player;p.characterClass=static_cast<std::int16_t>(sts::CharacterClass::IRONCLAD);p.curHp=hp;p.maxHp=maxHp;p.gold=gold;p.energy=energy;p.energyPerTurn=3;p.cardDrawPerTurn=5;p.block=block;p.lastTargetedMonster=lastTarget;p.cardsPlayedThisTurn=played;p.attacksPlayedThisTurn=attacks;p.skillsPlayedThisTurn=skills;p.cardsDiscardedThisTurn=discarded;p.lastAttackUnblockedDamage=lastDamage;p.timesDamagedThisCombat=timesDamaged;
    if(!c.contains("playerPowers")||!playerPowers(c.at("playerPowers"),p))return bad("silver_unmapped_player_power");int bb=int(sts::RelicId::BURNING_BLOOD);p.relicBits0=bb<64?1ULL<<bb:0;p.relicBits1=bb>=64?1ULL<<(bb-64):0;
    // Player::decrementStatus leaves an observable-history-dependent zero map
    // entry after Vulnerable expires. Preserve it without relaxing Silver's
    // strict state equality.
    if(vulnerableSeen&&p.statusMap.empty())p.statusMap.emplace_back(static_cast<int>(PlayerStatus::VULNERABLE),0);
    if(!c.contains("relics")||!c.at("relics").is_array()||c.at("relics").size()!=1||c.at("relics")[0].value("id",std::string())!="Burning Blood"||!c.at("relics")[0].contains("counter")||!c.at("relics")[0].at("counter").is_number_integer())return bad("silver_unmapped_relic_state");
    if(!c.contains("potions")||!c.at("potions").is_array()||c.at("potions").size()!=3)return bad("silver_unmapped_potion_state");for(int i=0;i<3;++i)if(c.at("potions")[i].value("slot",-1)!=i||c.at("potions")[i].value("id",std::string())!="Potion Slot")return bad("silver_unmapped_potion_state");
    if(!c.contains("monsters")||!c.at("monsters").is_array()||c.at("monsters").size()!=1)return bad("silver_unknown_monster");const auto&mj=c.at("monsters")[0];
    if(!mj.is_object()||!mj.contains("id")||!mj.at("id").is_string()||!integer(mj,"hp",w.monsters[0].curHp)||!integer(mj,"maxHp",w.monsters[0].maxHp)||!integer(mj,"block",w.monsters[0].block)||!mj.contains("moveHistory")||!mj.at("moveHistory").is_array())return bad("silver_monster_state");
    std::string mid=mj.at("id").get<std::string>();int canonical=monsterId(mid);if(!canonical)return bad("silver_unknown_monster");std::string room=r.at("roomClass").get<std::string>();if(((mid=="Gremlin Nob"||mid=="GremlinNob")?"ELITE":"MONSTER")!=room)return bad("silver_room_class");
    auto&m=w.monsters[0];m.idx=0;m.id=canonical;const auto&hist=mj.at("moveHistory");if(hist.empty()||hist.size()>2)return bad("silver_unknown_move");for(std::size_t i=0;i<hist.size();++i){if(!hist[i].is_number_integer())return bad("silver_unknown_move");int mm=moveId(mid,hist[hist.size()-1-i].get<int>());if(!mm)return bad("silver_unknown_move");m.moveHistory[i]=mm;}
    if(!mj.contains("powers")||!monsterPowers(mj.at("powers"),mid,m))return bad("silver_unmapped_monster_power");w.monsterCount=w.monstersAlive=1;if(mid=="Cultist")w.encounter=int(sts::MonsterEncounter::CULTIST);else if(mid=="JawWorm")w.encounter=int(sts::MonsterEncounter::JAW_WORM);else w.encounter=int(sts::MonsterEncounter::GREMLIN_NOB);
    for(auto&s:w.stasisCards){s.uniqueId=-1;s.cost=s.costForTurn=1;}w.limbo.assign(10,silver_bridge::CardWire{});for(auto&x:w.limbo)x.uniqueId=-1;w.curCardQueueItem.card.uniqueId=-1;
    if(c.contains("lastCard")&&!c.at("lastCard").is_null()){CardRecord x;const auto&j=c.at("lastCard");if(!parseCard(j,x)||!by.count(x.uuid))return bad("silver_last_card");w.curCardQueueItem.card=by.at(x.uuid);if(!integer(j,"target",w.curCardQueueItem.target)||!integer(j,"energyOnUse",w.curCardQueueItem.energyOnUse))return bad("silver_last_card");}else if(playerTurn>1&&played==0)w.curCardQueueItem.isEndTurn=true;
    std::string entry=observation.value("combatEntryHash",std::string());if(entry.empty())return bad("silver_combat_entry_hash");w.isolatedSearchSeed=fnv1a(entry+":silver-live-v3");w.observedGeneration=std::uint64_t(playerTurn)*100+decision+1;result.ok=true;return result;
}

std::string silverActionLabel(const silver_bridge::SemanticAction&a,const silver_bridge::BattleStateWire&s){
    if(a.type==silver_bridge::SemanticActionType::END_TURN)return "End Turn";if(a.type==silver_bridge::SemanticActionType::POTION)return "Potion";if(a.type!=silver_bridge::SemanticActionType::CARD)return "Card selection";
    static const std::map<int,std::string>cards={{int(sts::CardId::BASH),"Bash"},{int(sts::CardId::STRIKE_RED),"Strike"},{int(sts::CardId::DEFEND_RED),"Defend"}};auto it=cards.find(a.card.id);std::string name=it==cards.end()?"Card":it->second;
    if(a.target>=0&&a.target<s.monsterCount){static const std::map<int,std::string>monsters={{int(sts::MonsterId::CULTIST),"Cultist"},{int(sts::MonsterId::JAW_WORM),"Jaw Worm"},{int(sts::MonsterId::GREMLIN_NOB),"Gremlin Nob"}};auto m=monsters.find(s.monsters[a.target].id);return name+" -> "+(m==monsters.end()?"Monster "+std::to_string(a.target+1):m->second);}return name;
}
}
