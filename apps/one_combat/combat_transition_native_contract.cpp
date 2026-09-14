#include "combat_transition_native_contract.h"
#include "constants/Cards.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "constants/Rooms.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <tuple>
namespace one_combat {
namespace {
template<class T, std::size_t N> constexpr int count(const T (&)[N]) { return N; }
template<class T> int id(T v) { return static_cast<int>(v); }
using R=sts::RelicId; using C=sts::CardId; using P=sts::Potion; using E=sts::MonsterEncounter;
std::pair<std::string,int> trajectory(int rid) {
    switch(static_cast<R>(rid)) {
    case R::HAPPY_FLOWER:return {"turns",3}; case R::INCENSE_BURNER:return {"turns",6};
    case R::INSERTER:throw std::invalid_argument("unsupported_inserter");
    case R::NUNCHAKU:case R::PEN_NIB:return {"attacks",10};
    case R::INK_BOTTLE:return {"cards",10}; case R::SUNDIAL:return {"shuffles",3};
    default:return {"",0}; }
}
void legal(int rid,int data,int encounter,bool bloom) {
    auto t=trajectory(rid);
    if(t.second && (data<0 || data>=t.second)) throw std::invalid_argument("invalid_relic_counter");
    if(rid==id(R::NEOWS_LAMENT) && (data<0 || data>3)) throw std::invalid_argument("invalid_relic_counter");
    if(rid==id(R::OMAMORI) && (data<0 || data>2 || encounter==id(E::WRITHING_MASS))) throw std::invalid_argument("invalid_relic_counter");
    if(rid==id(R::LIZARD_TAIL) && (data<0 || data>1 || (data==1 && !bloom))) throw std::invalid_argument("active_unqualified_lizard");
}
std::uint64_t next(CombatTransitionRandomState &s) {
    auto a=s.seed0,b=s.seed1;s.seed0=b;a^=a<<23;s.seed1=a^b^(a>>17)^(b>>26);return s.seed1+b;
}
std::vector<int> schedule(int encounter) {
    switch(static_cast<E>(encounter)) {
    case E::GREMLIN_GANG:return {8,7,6,5}; case E::SMALL_SLIMES:case E::LARGE_SLIME:return {0};
    case E::LOTS_OF_SLIMES:return {5,4,3,2,1};case E::EXORDIUM_THUGS:return {0,3,0,3};
    case E::EXORDIUM_WILDLIFE:return {2,0,3};case E::GREMLIN_LEADER:return {8,8};
    case E::FOUR_SHAPES:return {6,5,4,3};case E::THREE_SHAPES:return {6,5,4};
    case E::SPHERE_AND_TWO_SHAPES:return {3,3};case E::THREE_LOUSE:return {0,0,0};
    case E::TWO_LOUSE:return {0,0};default:return {}; }
}
}
CombatTransitionRandomState replayNativeComposedMisc(CombatTransitionRandomState s,int encounter) {
    if(encounter<=0 || encounter>=count(sts::monsterEncounterEnumNames) || s.counter<0 || !(s.seed0|s.seed1)) throw std::invalid_argument("inherited_rng");
    for(int bound:schedule(encounter)) {
        if(s.counter==std::numeric_limits<std::int32_t>::max()) throw std::invalid_argument("rng_counter_overflow");
        ++s.counter;
        if(!bound) {next(s);continue;}
        for(;;) {const auto bits=next(s)>>1,value=bits%bound;
            // Native signed rejection check, expressed without signed overflow.
            if(bits-value+static_cast<std::uint64_t>(bound)-1 < (std::uint64_t{1}<<63)) break;}
    } return s;
}
std::vector<CombatTransitionRelicState> reconstructNativeComposedRelics(const std::vector<CombatTransitionRelicState>& pre,const std::map<std::string,int>& residues,int encounter) {
    const std::map<std::string,int> sizes{{"turns",6},{"attacks",10},{"cards",10},{"shuffles",3},{"lizard",2}};
    for(const auto &v:residues) {auto it=sizes.find(v.first);if(it==sizes.end() || v.second<0 || v.second>=it->second) throw std::invalid_argument("invalid_trajectory_residue");}
    bool bloom=std::any_of(pre.begin(),pre.end(),[](auto r){return r.id==id(R::MARK_OF_THE_BLOOM);});
    auto post=pre; for(auto &r:post) {legal(r.id,r.data,encounter,bloom);auto t=trajectory(r.id);
        if(t.second) r.data=(r.data+residues.at(t.first))%t.second;
        else if(r.id==id(R::NEOWS_LAMENT)) r.data=std::max(0,r.data-1);
    } return post;
}
std::vector<std::string> nativeComposedSupportReasons(const CombatPredictorInputV1 &pi,const CombatTransitionPersistentState &pre,const NativeComposedDomain &d) {
    if(!d.ready)return {"artifacts_not_loaded"};
    const auto &g=pi.globals;std::vector<std::string> reasons;
    auto add=[&](bool test,const char *s){if(test)reasons.emplace_back(s);};
    if(g.characterClass<0 || g.characterClass>=4 || g.encounter<0 || g.encounter>=count(sts::monsterEncounterEnumNames) || g.roomClass<0 || g.roomClass>=count(sts::roomStrings) || g.lastRoom<0 || g.lastRoom>=count(sts::roomStrings) || !std::isfinite(g.potionKeepValue) || pi.potions.size()!=5 || pi.cards.size()>128 || pi.relics.size()>64) return {"invalid_pre_state"};
    add(g.characterClass!=id(sts::CharacterClass::IRONCLAD),"non_ironclad");add(g.encounter==id(E::WRITHING_MASS),"writhing_mass");
    add(g.encounter==id(E::LOOTER)||g.encounter==id(E::TWO_THIEVES)||g.encounter==id(E::EXORDIUM_THUGS),"gold_mutating_encounter");
    bool ritual=false,goldCard=false,certified=g.characterClass==0;
    for(std::size_t i=0;i<pi.cards.size();++i) {auto c=pi.cards[i];
        if(c.cardId<0 || c.cardId>=count(sts::cardEnumStrings) || c.bottleBinding < -1 || c.bottleBinding>2)return {"invalid_pre_state"};
        if(i && std::tie(c.cardId,c.upgraded,c.misc,c.bottleBinding)<std::tie(pi.cards[i-1].cardId,pi.cards[i-1].upgraded,pi.cards[i-1].misc,pi.cards[i-1].bottleBinding))return {"invalid_pre_state"};
        ritual|=c.cardId==id(C::RITUAL_DAGGER);goldCard|=c.cardId==id(C::HAND_OF_GREED)||c.cardId==id(C::JACK_OF_ALL_TRADES)||c.cardId==id(C::TRANSMUTATION);
        auto color=sts::cardColors[c.cardId];certified&=color==sts::CardColor::RED || color==sts::CardColor::COLORLESS || color==sts::CardColor::CURSE;
    }
    add(ritual,"ritual_dagger");add(goldCard,"gold_mutating_card");bool toolbox=false;
    for(std::size_t i=0;i<pi.relics.size();++i) {auto r=pi.relics[i];if(r.relicId<0 || r.relicId>=count(sts::relicEnumNames) || r.orderIndex!=static_cast<int>(i))return {"invalid_pre_state"};toolbox|=r.relicId==id(R::TOOLBOX);}
    add(toolbox,"gold_mutating_relic");bool smoke=false,entropic=false,goldPotion=false;
    for(int i=0;i<5;++i) {auto p=pi.potions[i];if(p.slot!=i || p.potionId<0 || p.potionId>=count(sts::potionEnumNames))return {"invalid_pre_state"};smoke|=p.potionId==id(P::SMOKE_BOMB);entropic|=p.potionId==id(P::ENTROPIC_BREW);goldPotion|=p.potionId==id(P::COLORLESS_POTION);}
    add(smoke,"smoke_bomb");add(entropic,"entropic_brew");add(goldPotion,"gold_mutating_potion");add(pre.smokeBombUsed,"pre_smoke_bomb_used");add(pre.stolenGold!=0,"pre_stolen_gold_nonzero");add(!certified || entropic,"potion_not_certified");if(!reasons.empty())return reasons;
    if(pre.curHp!=g.curHp || pre.maxHp!=g.maxHp || pre.potionCapacity!=g.potionCapacity || pre.potionCount!=g.potionCount)return {"visible_pre_mismatch"};
    if(pre.relics.size()!=pi.relics.size())return {"visible_relic_mismatch"};
    for(std::size_t i=0;i<pre.relics.size();++i)if(pre.relics[i].id!=pi.relics[i].relicId || pre.relics[i].data!=pi.relics[i].data)return {"visible_relic_mismatch"};
    int active=0;for(int i=0;i<5;++i) {if(pre.potions[i]!=pi.potions[i].potionId)return {"visible_potion_mismatch"};if(pre.potions[i]<1 || pre.potions[i]>=count(sts::potionEnumNames))return {"invalid_pre_state"};active+=pre.potions[i]>1;}
    if(pre.potionCapacity<0 || pre.potionCapacity>5)return {"invalid_pre_state"};if(active!=pre.potionCount)return {"potion_count"};
    if(d.hpClasses.size()!=304 || pre.curHp<1 || pre.curHp>pre.maxHp)return {"hp_domain"};for(int i=0;i<304;++i)if(d.hpClasses[i]!=i-160)return {"hp_domain"};
    if(pre.curHp<d.preCurHpRange[0] || pre.curHp>d.preCurHpRange[1] || pre.maxHp<d.preMaxHpRange[0] || pre.maxHp>d.preMaxHpRange[1])return {"hp_envelope"};
    if(d.maxHpClasses!=d.maxHpDeltaValues || d.maxHpClasses.empty())return {"max_hp_domain"};for(int delta:d.maxHpClasses) {auto max=static_cast<std::int64_t>(pre.maxHp)+delta;if(max<=0 || max>std::numeric_limits<int>::max())return {"max_hp_state"};}
    bool bloom=std::any_of(pre.relics.begin(),pre.relics.end(),[](auto r){return r.id==id(R::MARK_OF_THE_BLOOM);});
    try {for(auto r:pre.relics) {legal(r.id,r.data,g.encounter,bloom);auto t=trajectory(r.id);if(t.second && !d.trainedGroups.count(t.first))return {"untrained_trajectory"};}}
    catch(const std::invalid_argument &e){return {e.what()};}
    for(int i:{2,4})if(pre.combatRng[i].counter<0 || !(pre.combatRng[i].seed0|pre.combatRng[i].seed1))return {"inherited_rng"};
    if(!g.encounter)return {"encounter_domain"};try {replayNativeComposedMisc(pre.combatRng[2],g.encounter);}catch(const std::exception&){return {"inherited_rng"};}
    return {};
}
}
