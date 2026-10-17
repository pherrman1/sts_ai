#include "combat_transition_near_full.h"
#include "game/Game.h"
#include "constants/Cards.h"
#include "constants/Relics.h"
#include "constants/Potions.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <set>
#include <tuple>
namespace one_combat {
namespace {
using Vec=std::vector<float>;using C=sts::CardId;using R=sts::RelicId;using P=sts::Potion;using E=sts::MonsterEncounter;
void require(bool v,const char *why){if(!v)throw std::runtime_error(why);}
void append(Vec &a,const Vec& b){a.insert(a.end(),b.begin(),b.end());}
int cap(int encounter) {
    switch(static_cast<E>(encounter)) {
    case E::TWO_LOUSE:
    case E::TWO_FUNGI_BEASTS:
    case E::TWO_THIEVES:
    case E::CHOSEN_AND_BYRDS:
    case E::SENTRY_AND_SPHERE:
    case E::CENTURION_AND_HEALER:
    case E::CULTIST_AND_CHOSEN:
    case E::SHELLED_PARASITE_AND_FUNGI:
    case E::DONU_AND_DECA:
    case E::SHIELD_AND_SPEAR:
    case E::COLOSSEUM_EVENT_NOBS:
    case E::COLOSSEUM_EVENT_SLAVERS:
    case E::MYSTERIOUS_SPHERE_EVENT:
    case E::SMALL_SLIMES:
    case E::LARGE_SLIME:
    case E::EXORDIUM_THUGS:
    case E::EXORDIUM_WILDLIFE:
        return 2;
    case E::THREE_LOUSE:
    case E::THREE_SENTRIES:
    case E::THREE_BYRDS:
    case E::THREE_CULTIST:
    case E::SLAVERS:
    case E::THREE_SHAPES:
    case E::SPHERE_AND_TWO_SHAPES:
    case E::JAW_WORM_HORDE:
    case E::AWAKENED_ONE:
    case E::MASKED_BANDITS_EVENT:
    case E::MUSHROOMS_EVENT:
        return 3;
    case E::GREMLIN_GANG:
    case E::FOUR_SHAPES:
    case E::SLIME_BOSS:
        return 4;
    case E::LOTS_OF_SLIMES:
        return 5;
    default:return 1;}
}
bool boss(int e){switch(static_cast<E>(e)) {
case E::SLIME_BOSS:case E::THE_GUARDIAN:case E::HEXAGHOST:case E::CHAMP:case E::COLLECTOR:case E::AUTOMATON:case E::AWAKENED_ONE:case E::DONU_AND_DECA:case E::TIME_EATER:case E::THE_HEART:return true;
default:return false;}}
bool has(const CombatTransitionPersistentState &s,R r){return std::any_of(s.relics.begin(),s.relics.end(),[&](auto v){return v.id==int(r);});}
int data(const CombatTransitionPersistentState &s,R r){for(auto v:s.relics)if(v.id==int(r))return v.data;return 0;}
struct Conditions {int mode;Vec mechanical,hp,bits,events;};
Conditions conditions(const CombatTransitionPersistentState& pre,const CombatPredictorInputV1 &pi,int ending,int maximum,int mask,const std::vector<int>& consumed,bool escaped) {
    auto count=[&](C id,int upgrade=-1){return int(std::count_if(pi.cards.begin(),pi.cards.end(),[&](auto c){return c.cardId==int(id)&&(upgrade<0||int(c.upgraded)==upgrade);}));};
    auto used=[&](P p){return std::find(consumed.begin(),consumed.end(),int(p))!=consumed.end();};
    int trans=count(C::TRANSMUTATION),jack=count(C::JACK_OF_ALL_TRADES),tool=has(pre,R::TOOLBOX),color=used(P::COLORLESS_POTION);
    int generated=trans+jack+tool+color,normal=count(C::HAND_OF_GREED,0),upgraded=count(C::HAND_OF_GREED,1);
    bool upgrade=generated||count(C::ARMAMENTS)||count(C::APOTHEOSIS)||count(C::DISCOVERY)||count(C::CHRYSALIS)||has(pre,R::WARPED_TONGS)||has(pre,R::DEAD_BRANCH)||has(pre,R::NILRYS_CODEX)||used(P::SKILL_POTION)||used(P::BLESSING_OF_THE_FORGE);
    bool ecto=has(pre,R::ECTOPLASM);int thieves=pi.globals.encounter==int(E::TWO_THIEVES)?2:int(pi.globals.encounter==int(E::LOOTER)||pi.globals.encounter==int(E::EXORDIUM_THUGS));
    Conditions out;out.mode=int((normal||generated)&&!ecto)+2*int((upgraded||generated||(normal&&upgrade))&&!ecto);
    out.mechanical={pre.gold/90.f,float(normal+upgraded),float(generated),float(upgraded+count(C::TRANSMUTATION,1)),float(normal+count(C::TRANSMUTATION,0)+jack+tool+color),float(trans),float(jack),float(tool),float(color),float(upgrade),float(ecto),float(has(pre,R::BLOODY_IDOL)),float(thieves),float(cap(pi.globals.encounter)-int(escaped)),(pi.globals.ascension>=17?20.f:15.f)/15};
    out.hp={(ending-pre.curHp)/160.f,float(ending)/maximum,(maximum-pre.maxHp)/10.f};for(int i=0;i<5;++i)out.bits.push_back(float((mask>>i)&1));
    int daggers=0,daggerPlus=0;for(auto c:pre.deck)if(c.id==int(C::RITUAL_DAGGER)){++daggers;daggerPlus+=c.upgraded;}
    out.events={data(pre,R::OMAMORI)/2.f,float(has(pre,R::DARKSTONE_PERIAPT)),float(daggers),float(daggerPlus),float(pi.globals.encounter==int(E::WRITHING_MASS)),float(escaped),float(upgrade),float(color)};
    return out;
}
std::vector<std::pair<int,int>> gains(int budget,const std::vector<int>& payouts){std::set<std::pair<int,int>> result{{0,0}},level{{0,0}};for(int n=1;n<=budget;++n){std::set<std::pair<int,int>> next;for(auto x:level)for(int p:payouts)next.emplace(n,x.second+p);result.insert(next.begin(),next.end());level=std::move(next);}return {result.begin(),result.end()};}
// Native fatal-hit closure. Profiles retain the ordinary kill budget needed by
// Ritual Dagger; shared HoG/Dagger kills cannot count the same fatal hit twice.
using Profile=std::array<int,4>;
std::vector<Profile> profiles(int gold,int encounter,int ascension,int mode,bool escaped){
    using Key=std::tuple<int,int,int,int,bool>;static thread_local std::map<Key,std::vector<Profile>> cache;
    Key key{gold,encounter,ascension,mode,escaped};auto found=cache.find(key);if(found!=cache.end())return found->second;
    std::vector<int> payouts;if(mode&1)payouts.push_back(20);if(mode&2)payouts.push_back(25);int maximum=cap(encounter);std::vector<int> thiefCounts;
    if(encounter==int(E::EXORDIUM_THUGS))thiefCounts={0,1};else thiefCounts={encounter==int(E::TWO_THIEVES)?2:int(encounter==int(E::LOOTER))};std::set<Profile> result;
    for(int thieves:thiefCounts){
        if(!thieves){int budget=maximum-int(escaped);for(auto p:gains(budget,payouts))if(gold+p.second<=32767)result.insert({gold+p.second,0,p.first,budget-p.first});continue;}
        using State=std::tuple<int,std::array<int,2>,std::array<char,2>,int,int>;
        std::array<char,2> initial{{'A',thieves==2?'A':'E'}};std::set<State> states{{gold,{{0,0}},initial,0,0}};int otherCap=maximum-thieves;
        for(int turn=1;turn<=6;++turn){std::set<State> player;
            for(const auto &state:states){auto [current,stolen,status,others,hogs]=state;
                std::function<void(int,int,std::array<char,2>,int)> phase;
                phase=[&](int i,int purse,std::array<char,2> updated,int thiefHogs){
                    if(i==thieves){for(auto p:gains(otherCap-others,payouts))if(purse+p.second<=32767)player.emplace(purse+p.second,stolen,updated,others+p.first,hogs+thiefHogs+p.first);return;}
                    phase(i+1,purse,updated,thiefHogs);
                    if(status[i]!='O'&&status[i]!='H'&&status[i]!='E'){auto killed=updated;killed[i]='O';phase(i+1,purse,killed,thiefHogs);for(int p:payouts){killed[i]='H';phase(i+1,purse+p,killed,thiefHogs+1);}}
                };phase(0,current,status,0);
            }
            states.clear();for(const auto &state:player){auto [current,stolen,status,others,hogs]=state;bool alive=false;int ordinaryThieves=0,recovery=0;
                for(int i=0;i<thieves;++i){alive|=status[i]=='A'||status[i]=='L'||status[i]=='B';ordinaryThieves+=status[i]=='O';if(status[i]=='O'||status[i]=='H'||(escaped&&(status[i]=='A'||status[i]=='L')))recovery+=stolen[i];}
                if(escaped){if(alive||otherCap-others>0)result.insert({current,recovery,hogs,otherCap-others+ordinaryThieves-int(!alive)});}
                else if(!alive)result.insert({current,recovery,hogs,otherCap-others+ordinaryThieves});
                std::function<void(int,int,std::array<int,2>,std::array<char,2>)> enemy;
                enemy=[&](int i,int purse,std::array<int,2> taken,std::array<char,2> updated){
                    if(i==thieves){states.emplace(purse,taken,updated,others,hogs);return;}
                    for(bool lunge:{false,true}){if(lunge && !(turn==3&&status[i]=='A'))continue;auto t=taken;auto u=updated;int remaining=purse;
                        if((turn<=2&&status[i]=='A')||(turn==3&&status[i]=='A'&&lunge)){int paid=std::min(remaining,ascension>=17?20:15);remaining-=paid;t[i]+=paid;}
                        if(turn==3&&status[i]=='A')u[i]=lunge?'L':'B';else if(turn==4&&status[i]=='L')u[i]='B';else if((turn==4||turn==5)&&status[i]=='B')u[i]='E';
                        enemy(i+1,remaining,t,u);
                    }
                };enemy(0,current,stolen,status);
            }
        }
    }
    std::vector<Profile> out(result.begin(),result.end());if(cache.size()>=8192)cache.clear();cache.emplace(key,out);return out;
}
std::vector<std::vector<int>> daggerCandidates(const CombatTransitionPersistentState& pre,int encounter,bool upgrade,bool escaped){
    // The first Awakened One phase is half-dead and cannot pay Ritual growth.
    int maximum=cap(encounter)-int(escaped);std::vector<std::vector<std::pair<int,int>>> options;
    for(auto c:pre.deck)if(c.id==int(C::RITUAL_DAGGER)){std::vector<int> payouts=c.upgraded?std::vector<int>{5}:(upgrade?std::vector<int>{3,5}:std::vector<int>{3});std::vector<std::pair<int,int>> amounts;
        for(auto p:gains(maximum,payouts)){auto it=std::find_if(amounts.begin(),amounts.end(),[&](auto value){return value.first==p.second;});if(it==amounts.end())amounts.emplace_back(p.second,p.first);else it->second=std::min(it->second,p.first);}options.push_back(amounts);}
    std::vector<std::vector<int>> result;std::vector<int> selected;
    std::function<void(size_t,int)> visit=[&](size_t i,int kills){if(i==options.size()){result.push_back(selected);return;}for(auto p:options[i])if(kills+p.second<=maximum){selected.push_back(p.first);visit(i+1,kills+p.second);selected.pop_back();}};visit(0,0);return result;
}
int daggerMinimum(const CombatTransitionPersistentState& pre,int encounter,bool upgrade,bool escaped,const std::vector<int>& amounts){int maximum=cap(encounter)-int(escaped),total=0;size_t i=0;for(auto card:pre.deck)if(card.id==int(C::RITUAL_DAGGER)){
    require(i<amounts.size(),"Dagger candidate identity");std::vector<int> payouts=card.upgraded?std::vector<int>{5}:(upgrade?std::vector<int>{3,5}:std::vector<int>{3});int best=maximum+1;for(auto p:gains(maximum,payouts))if(p.second==amounts[i])best=std::min(best,p.first);require(best<=maximum,"Dagger native increment");total+=best;++i;}require(i==amounts.size(),"Dagger candidate count");return total;}
}
CombatRuntimeSample sampleNearFull(const CombatTransitionRuntime &net,const NativeComposedDomain &domain,const CombatTransitionPersistentState &pre,const CombatPredictorInputV1 &pi,std::mt19937_64 &rng,float survival,const Vec &givenMaximum,const Vec &givenZ,const Vec &givenZp,bool survivalAlreadyWon){
    auto uniform=[&](){return std::generate_canonical<double,53>(rng);};
    auto category=[&](const Vec &p){double u=uniform(),sum=0;int last=-1;for(size_t i=0;i<p.size();++i){require(std::isfinite(p[i])&&p[i]>=0,"near-full probability");sum+=p[i];if(p[i]>0)last=int(i);if(u<sum)return int(i);}require(last>=0&&std::abs(sum-1)<1e-6,"near-full probability total");return last;};
    if(!survivalAlreadyWon && uniform()>=survival)return {CombatRuntimeSample::Outcome::DEATH,{}};
    auto z=givenZ.empty()?net.hpEncoding(pi):givenZ;auto maximumProb=!givenMaximum.empty()?givenMaximum:net.sharedHpEncoder()?net.maxHp(z):net.maxHp(pi);auto zp=givenZp.empty()?net.potionEncoding(pi):givenZp;
    auto post=pre;int d=category(maximumProb);post.maxHp+=domain.maxHpClasses.at(d);
    const bool bossFight=boss(pi.globals.encounter);
    // Escape capability: the escape is drawn before HP, and HP and the potion trajectory are
    // conditioned on it. A conditioned victory (the Lizard branches) never escapes.
    int e=-1;
    if(net.escapeCapable()) {
        e=0;
        if(!survivalAlreadyWon && CombatTransitionRuntime::escapeEligible(pre.potions,pre.potionCapacity,bossFight))
            e=uniform()<net.escapeProbability(z)?1:0;
    }
    int h=category(net.signedHp(z,d,pre.curHp,post.maxHp,e));
    post.curHp+=domain.hpClasses.at(h);
    float fraction=float(post.curHp)/post.maxHp;int initialMask=0,originalBits=0;for(int slot=0;slot<5;++slot)if(pre.potions[slot]>1)originalBits|=1<<slot;
    std::vector<int> consumed;bool escaped=false,origin=false;sts::Random potionRng;bool sozu=has(pre,R::SOZU);
    for(;;){int action=category(net.potionInventory(zp,post.potions,pre.potionCapacity,d,fraction,bossFight,e)),mask=action&31;bool use=action>=32;initialMask|=mask&originalBits;std::vector<int> cleared;
        for(int slot=0;slot<5;++slot)if(mask&(1<<slot)){int p=post.potions[slot];cleared.push_back(p);if((p!=int(P::ENTROPIC_BREW)&&p!=int(P::SMOKE_BOMB))||use)consumed.push_back(p);post.potions[slot]=1;}
        auto selected=[&](P p){return std::find(cleared.begin(),cleared.end(),int(p))!=cleared.end();};
        if(selected(P::SMOKE_BOMB)&&use){escaped=true;break;}
        if(selected(P::ENTROPIC_BREW)&&use){require(pre.potionCapacity>=1,"Brew capacity");if(!origin){potionRng=sts::Random(rng());origin=true;}
            for(int i=0;i<pre.potionCapacity;++i){int potion=int(sts::returnRandomPotion(potionRng,sts::CharacterClass::IRONCLAD,true));if(!sozu)for(int slot=0;slot<pre.potionCapacity;++slot)if(post.potions[slot]==1){post.potions[slot]=potion;break;}}
            continue;
        }
        bool triggerCleared=selected(P::ENTROPIC_BREW)||selected(P::SMOKE_BOMB),triggerRemaining=std::any_of(post.potions.begin(),post.potions.end(),[](int p){return p==int(P::ENTROPIC_BREW)||p==int(P::SMOKE_BOMB);});
        if(mask==0||(!triggerCleared&&!triggerRemaining))break;
    }
    require(e==-1 || escaped==(e==1),"escape draw and potion trajectory disagree");
    post.potionCount=int(std::count_if(post.potions.begin(),post.potions.end(),[](int p){return p>1;}));post.smokeBombUsed=escaped;
    if(origin)post.combatRng[4]={potionRng.counter,potionRng.seed0,potionRng.seed1};
    auto probabilities=net.relic(z,h,fraction,initialMask,escaped);std::map<std::string,int> residues;for(auto name:{"turns","attacks","cards","shuffles"})residues[name]=category(probabilities.at(name));
    bool writhing=pi.globals.encounter==int(E::WRITHING_MASS);std::vector<CombatTransitionRelicState> before;for(auto r:pre.relics)if(!(writhing&&r.id==int(R::OMAMORI)))before.push_back(r);
    auto reconstructed=reconstructNativeComposedRelics(before,residues,pi.globals.encounter);size_t ri=0;for(auto &r:post.relics)if(!(writhing&&r.id==int(R::OMAMORI)))r=reconstructed.at(ri++);
    auto cond=conditions(pre,pi,post.curHp,post.maxHp,initialMask,consumed,escaped);auto context=z;append(context,cond.hp);append(context,cond.bits);append(context,cond.events);
    if(writhing){bool om=data(pre,R::OMAMORI)>0;std::vector<std::vector<Vec>> candidates{{{0,0,0}},{{1,float(om),float(!om)}}};std::vector<bool> legal{true,!(has(pre,R::DARKSTONE_PERIAPT)&&!om&&post.maxHp-pre.maxHp<6)};
        if(category(net.event("writhing",context,candidates,legal))){if(om){for(auto &r:post.relics)if(r.id==int(R::OMAMORI))r.data=std::max(0,r.data-1);}else{post.deck.push_back({int(C::PARASITE),0,false});++post.cardTypeCounts[3];++post.transformableCount;}}
    }
    bool upgrade=cond.mechanical[9]>0;auto amounts=daggerCandidates(pre,pi.globals.encounter,upgrade,escaped);require(!amounts.empty(),"empty Dagger closure");std::vector<int> dagger;
    bool hasDagger=std::any_of(pre.deck.begin(),pre.deck.end(),[](auto c){return c.id==int(C::RITUAL_DAGGER);});
    if(hasDagger){std::vector<std::vector<Vec>> candidates;for(const auto &value:amounts){std::vector<Vec> event;size_t i=0;for(auto c:pre.deck)if(c.id==int(C::RITUAL_DAGGER))event.push_back({c.misc/100.f,float(c.upgraded),value.at(i++)/20.f});candidates.push_back(event);}dagger=amounts.at(category(net.event("ritual",context,candidates,std::vector<bool>(amounts.size(),true))));}
    else {dagger=amounts.front();category(Vec{1});} // Python consumes the deterministic Dagger draw too.
    int minimum=daggerMinimum(pre,pi.globals.encounter,upgrade,escaped,dagger);std::set<std::pair<int,int>> pairs;
    for(auto profile:profiles(pre.gold,pi.globals.encounter,pi.globals.ascension,cond.mode,escaped))if(profile[3]>=minimum)pairs.emplace(profile[0],profile[1]);require(!pairs.empty(),"empty joint gold closure");std::vector<std::pair<int,int>> posts(pairs.begin(),pairs.end());
    size_t choice=0;if(posts.size()>1){auto goldContext=z;append(goldContext,cond.mechanical);append(goldContext,cond.hp);append(goldContext,cond.bits);std::vector<Vec> candidates;
        for(auto p:posts){int delta=p.first-pre.gold;candidates.push_back({delta/90.f,p.second/90.f,float(delta==0),float(p.second==0),float(delta>0),(delta+p.second)/90.f});}choice=category(net.gold(goldContext,candidates));}
    else category(Vec{1}); // Match scalar Python sampler draw order.
    post.gold=posts.at(choice).first;post.stolenGold=posts.at(choice).second;size_t di=0;for(auto &card:post.deck)if(card.id==int(C::RITUAL_DAGGER)){int misc=int(card.misc)+dagger.at(di++);require(misc>=-32768&&misc<=32767,"Dagger int16 overflow");card.misc=static_cast<std::int16_t>(misc);}
    post.combatRng[2]=replayNativeComposedMisc(pre.combatRng[2],pi.globals.encounter);
    return {escaped?CombatRuntimeSample::Outcome::ESCAPE:CombatRuntimeSample::Outcome::VICTORY,std::move(post)};
}
nlohmann::json nearFullDiagnostics(const CombatTransitionRuntime& net,const CombatTransitionPersistentState& pre,const CombatPredictorInputV1& pi,int delta,int ending,int maximum,int mask,const std::vector<int>& consumed,bool escaped,const std::vector<int>& dagger) {
    auto z=net.hpEncoding(pi),zp=net.potionEncoding(pi);auto cond=conditions(pre,pi,ending,maximum,mask,consumed,escaped);auto context=z;append(context,cond.hp);append(context,cond.bits);append(context,cond.events);
    nlohmann::json out={{"mechanical",cond.mechanical},{"hpConditions",cond.hp},{"bits",cond.bits},{"eventConditions",cond.events},{"hpEncoding",z},{"potionEncoding",zp},{"potion",net.potionInventory(zp,pre.potions,pre.potionCapacity,delta,float(ending)/maximum,boss(pi.globals.encounter))},{"relic",net.relic(z,net.hpClassIndex(ending-pre.curHp),float(ending)/maximum,mask,escaped)}};
    if(pi.globals.encounter==int(E::WRITHING_MASS)){bool om=data(pre,R::OMAMORI)>0;out["writhing"]=net.event("writhing",context,{{{0,0,0}},{{1,float(om),float(!om)}}},{true,!(has(pre,R::DARKSTONE_PERIAPT)&&!om&&maximum-pre.maxHp<6)});}
    auto values=daggerCandidates(pre,pi.globals.encounter,cond.mechanical[9]>0,escaped);std::vector<std::vector<Vec>> candidates;bool present=false;
    for(auto value:values){std::vector<Vec> event;size_t i=0;for(auto c:pre.deck)if(c.id==int(C::RITUAL_DAGGER)){present=true;event.push_back({c.misc/100.f,float(c.upgraded),value.at(i++)/20.f});}candidates.push_back(event);}
    out["ritualCandidates"]=values;out["ritual"]=present?net.event("ritual",context,candidates,std::vector<bool>(values.size(),true)):Vec{1};
    int minimum=daggerMinimum(pre,pi.globals.encounter,cond.mechanical[9]>0,escaped,dagger);std::set<std::pair<int,int>> pairs;for(auto p:profiles(pre.gold,pi.globals.encounter,pi.globals.ascension,cond.mode,escaped))if(p[3]>=minimum)pairs.emplace(p[0],p[1]);std::vector<std::pair<int,int>> posts(pairs.begin(),pairs.end());std::vector<Vec> features;
    for(auto p:posts){int d=p.first-pre.gold;features.push_back({d/90.f,p.second/90.f,float(d==0),float(p.second==0),float(d>0),(d+p.second)/90.f});}
    auto goldContext=z;append(goldContext,cond.mechanical);append(goldContext,cond.hp);append(goldContext,cond.bits);out["goldCandidates"]=posts;out["gold"]=posts.size()>1?net.gold(goldContext,features):Vec{1};return out;
}

}
