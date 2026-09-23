#include "sim/search/SilverPriorNet.h"

#include "sim/search/SilverWireJson.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>

namespace sts::search {
namespace {
using namespace silver_bridge;
using Json = nlohmann::json;
using Vec = std::vector<float>;
using Matrix = std::vector<Vec>;

void require(bool ok, const char *what) { if (!ok) throw std::runtime_error(what); }
std::vector<int> bits(std::uint64_t value, int width) {
    std::vector<int> out; for (int i=0;i<width;++i) if ((value >> i) & 1ULL) out.push_back(i); return out;
}
Vec append(Vec a, const Vec &b) { a.insert(a.end(), b.begin(), b.end()); return a; }
Vec normalized(const Vec &v, const Vec &mean, const Vec &sd) {
    require(v.size()==mean.size() && v.size()==sd.size(), "SilverPriorNet normalization dimension");
    Vec out(v.size()); for(std::size_t i=0;i<v.size();++i) out[i]=(v[i]-mean[i])/sd[i]; return out;
}
Vec embedding(const Matrix &table, int id) {
    require(id>=0 && static_cast<std::size_t>(id)<table.size(), "SilverPriorNet categorical id out of range"); return table[id];
}
Vec linear(const Matrix &weights, const Vec &bias, const Vec &x) {
    require(weights.size()==bias.size(), "SilverPriorNet linear output dimension");
    Vec y(weights.size());
    for(std::size_t r=0;r<weights.size();++r) {
        require(weights[r].size()==x.size(), "SilverPriorNet linear input dimension");
        float sum=bias[r]; for(std::size_t c=0;c<x.size();++c) sum += weights[r][c]*x[c]; y[r]=sum;
    }
    return y;
}
Vec gelu(Vec x) { constexpr float k=0.7071067811865475244f; for(float &v:x) v=0.5f*v*(1.0f+std::erf(v*k)); return x; }
Vec mlp(const Matrix &w0,const Vec &b0,const Matrix &w1,const Vec &b1,const Vec &x) {
    return gelu(linear(w1,b1,gelu(linear(w0,b0,x))));
}
Vec pool(const std::vector<Vec> &rows, std::size_t dim) {
    Vec out(dim,0.0f); for(const auto &r:rows) { require(r.size()==dim,"SilverPriorNet pool dimension"); for(std::size_t i=0;i<dim;++i) out[i]+=r[i]; }
    if(!rows.empty()) { const float d=std::sqrt(static_cast<float>(rows.size())); for(float &v:out)v/=d; } return out;
}
int compact(const Json &map, int id) {
    const auto it=map.find(std::to_string(id)); require(it!=map.end(),"SilverPriorNet excluded or unrecognized card id"); return it->get<int>();
}
struct CardFeature { int id; float special,cost,costTurn; bool upgraded,free,retain; };
CardFeature cardFeature(const Json &v,const Json &vocab) {
    return {compact(vocab,v.at("id").get<int>()),float(v.at("specialData").get<int>()),float(v.at("cost").get<int>()),float(v.at("costForTurn").get<int>()),v.at("upgraded").get<bool>(),v.at("freeToPlayOnce").get<bool>(),v.at("retain").get<bool>()};
}
Json cardSortKey(const CardFeature &c) {
    return Json{{"card_id",c.id},{"cost",int(c.cost)},{"costForTurn",int(c.costTurn)},{"freeToPlayOnce",c.free},{"retain",c.retain},{"specialData",int(c.special)},{"upgraded",c.upgraded}};
}
Vec cardNumeric(const CardFeature &c,float pos,bool hasPos) { return {c.special,c.cost,c.costTurn,pos,hasPos?1.f:0.f,c.upgraded?1.f:0.f,c.free?1.f:0.f,c.retain?1.f:0.f}; }
struct CardRow { CardFeature f; int zone,segment; float position; bool positioned; const CardWire *wire; };
struct MonRow { int slot,id; Vec nums,small; std::vector<int> moves,powers; };
struct PotRow { int id,slot; float available,empty; };
struct BuiltInput { Vec context; std::array<int,4> cats{}; std::vector<CardRow> cards; std::vector<MonRow> monsters; std::vector<PotRow> potions; Vec statusPool,relicPool; };

BuiltInput buildInput(const BattleStateWire &w,const std::vector<SemanticAction> &actions,const Json &vocab) {
    require(w.valid && w.version==BattleStateWire::kVersion && w.inputState==1 && w.outcome==0,"SilverPriorNet requires PLAYER_NORMAL unresolved wire");
    require(actions.size()>=2,"SilverPriorNet requires at least two legal actions");
    require(w.drawPile.valid&&w.discardPile.valid&&w.exhaustPile.valid,"SilverPriorNet invalid public pile");
    BuiltInput out; const auto &p=w.player;
    Vec g={float(w.floorNum),0.f,float(w.energyWasted),float(w.cardsDrawn),float(w.act),float(w.omamoriOwned),float(w.omamoriValue),float(w.ascension),float(w.outcome),float(w.inputState),float(w.monsterTurnIdx),float(w.endTurnQueued),float(w.turnHasEnded),float(w.skipMonsterTurn),float(w.potionCount),float(w.potionCapacity),float(w.turn),float(w.monsterCount),float(w.monstersAlive),float(w.handNormalityCount),float(w.handPainCount),float(w.strikeCount),float(w.handBloodCardCount),float(w.drawPileBloodCardCount),float(w.discardPileBloodCardCount),float(w.fullDrawOrderObserved),float(w.intentsHidden)};
    Vec q={0.f,float(p.gold),float(p.curHp),float(p.maxHp),float(p.energy),float(p.energyPerTurn),float(p.cardDrawPerTurn),0.f,float(p.orbSlots),float(p.block),float(p.artifact),float(p.dexterity),float(p.focus),float(p.strength),float(p.haveUsedNecronomiconThisTurn),float(p.combustHpLoss),float(p.devaFormEnergyPerTurn),float(p.echoFormCardsDoubled),float(p.panacheCounter),float(p.cardsPlayedThisTurn),float(p.attacksPlayedThisTurn),float(p.skillsPlayedThisTurn),float(p.cardsDiscardedThisTurn),float(p.lastAttackUnblockedDamage),float(p.timesDamagedThisCombat)};
    out.context=g; out.context.insert(out.context.end(),q.begin(),q.end());
    const auto reference=silverRootReferenceScalars(w);
    out.context.insert(out.context.end(),{float(reference.effectiveGold),float(reference.maxHp)});
    out.context.push_back(float(w.hand.size()+w.limbo.size()+w.stasisCards.size()+w.drawPile.knownBottom.size()+w.drawPile.unknown.size()+w.drawPile.knownTop.size()+w.discardPile.knownBottom.size()+w.discardPile.unknown.size()+w.discardPile.knownTop.size()+w.exhaustPile.knownBottom.size()+w.exhaustPile.unknown.size()+w.exhaustPile.knownTop.size()));
    out.context.push_back(float(w.monsters.size())); out.context.push_back(float(w.potions.size()));
    // Misc flags and roll slot bitsets are population counts, followed by exact bits.
    auto misc=bits(w.miscBits,32),extra=bits(w.extraRollMoveOnTurn,8),skip=bits(w.skipMonsterTurnBits,8);
    out.context.insert(out.context.end(),{float(misc.size()),float(extra.size()),float(skip.size())});
    for(int i=0;i<32;++i)out.context.push_back((w.miscBits>>i)&1U?1.f:0.f);
    for(int i=0;i<8;++i)out.context.push_back((w.extraRollMoveOnTurn>>i)&1U?1.f:0.f);
    for(int i=0;i<8;++i)out.context.push_back((w.skipMonsterTurnBits>>i)&1U?1.f:0.f);
    out.context.insert(out.context.end(),{w.drawPile.fullOrderObserved?1.f:0.f,w.discardPile.fullOrderObserved?1.f:0.f,w.exhaustPile.fullOrderObserved?1.f:0.f});
    const auto zoneCount=[&](int zone){return std::count_if(out.cards.begin(),out.cards.end(),[&](const CardRow &c){return c.zone==zone;});};
    // Zone rows are populated below; counts are patched after card extraction.
    const std::size_t countOffset=out.context.size(); out.context.resize(countOffset+10,0.f);
    for(auto x:p.bombs)out.context.push_back(float(x));
    for(int i=0;i<8;++i)out.context.push_back((p.orangePelletsCardTypesPlayed>>i)&1U?1.f:0.f);
    // absent card references remain explicit zeros for each limbo/stasis slot.
    for(const auto &c:w.limbo)out.context.push_back(c.id==0&&c.uniqueId<0?0.f:1.f);
    for(const auto &c:w.stasisCards)out.context.push_back(c.id==0&&c.uniqueId<0?0.f:1.f);
    (void)zoneCount;
    // Candidate-dependent hand lookup is resolved only after cards are created.
    auto addCard=[&](const CardWire &c,int zone,int segment,int pos,bool positioned,bool allowAbsent){
        if(allowAbsent&&c.id==0&&c.uniqueId<0)return;
        out.cards.push_back({cardFeature(Json{{"id",c.id},{"specialData",c.specialData},{"cost",c.cost},{"costForTurn",c.costForTurn},{"upgraded",c.upgraded},{"freeToPlayOnce",c.freeToPlayOnce},{"retain",c.retain}},vocab),zone,segment,float(positioned?pos:0),positioned,&c});
    };
    for(std::size_t i=0;i<w.hand.size();++i)addCard(w.hand[i],0,1,int(i),true,false);
    for(std::size_t i=0;i<w.limbo.size();++i)addCard(w.limbo[i],1,1,int(i),true,true);
    for(std::size_t i=0;i<w.stasisCards.size();++i)addCard(w.stasisCards[i],2,1,int(i),true,true);
    auto addPile=[&](const PileWire &pile,int zone){
        auto addOrdered=[&](const std::vector<CardWire>&cs,int seg,bool ordered){std::vector<CardWire> xs=cs;if(!ordered)std::stable_sort(xs.begin(),xs.end(),[&](const CardWire&a,const CardWire&b){auto fa=cardFeature(Json{{"id",a.id},{"specialData",a.specialData},{"cost",a.cost},{"costForTurn",a.costForTurn},{"upgraded",a.upgraded},{"freeToPlayOnce",a.freeToPlayOnce},{"retain",a.retain}},vocab);auto fb=cardFeature(Json{{"id",b.id},{"specialData",b.specialData},{"cost",b.cost},{"costForTurn",b.costForTurn},{"upgraded",b.upgraded},{"freeToPlayOnce",b.freeToPlayOnce},{"retain",b.retain}},vocab);return cardSortKey(fa).dump()<cardSortKey(fb).dump();});for(std::size_t i=0;i<xs.size();++i)addCard(xs[i],zone,seg,int(i),ordered,false);};
        addOrdered(pile.knownBottom,2,true); addOrdered(pile.unknown,3,false); addOrdered(pile.knownTop,4,true);
    };
    addPile(w.drawPile,3);addPile(w.discardPile,4);addPile(w.exhaustPile,5);
    out.context[54]=float(out.cards.size());
    // Rebuild context's zone and segment counts in the model's fixed order.
    const int zones[6]={0,1,2,3,4,5}; for(int i=0;i<6;++i)out.context[countOffset+i]=float(std::count_if(out.cards.begin(),out.cards.end(),[&](const CardRow &c){return c.zone==zones[i];}));
    const int segs[4]={1,2,3,4}; for(int i=0;i<4;++i)out.context[countOffset+6+i]=float(std::count_if(out.cards.begin(),out.cards.end(),[&](const CardRow &c){return c.segment==segs[i];}));
    for(int slot=0;slot<static_cast<int>(w.monsters.size());++slot){const auto &m=w.monsters[slot];if(slot>=w.monsterCount||m.idx<0)continue;require(m.idx==slot,"SilverPriorNet monster slot mismatch");MonRow r;r.slot=slot;r.id=m.id;r.nums={float(m.curHp),float(m.maxHp),float(m.block),float(m.strength),float(m.vulnerable),float(m.weak),float(m.uniquePower0),float(m.uniquePower1),float(m.miscInfo),float(m.isEscapingB),float(m.halfDead),float(m.escapeNext),float(m.curHp>0&&!m.isEscapingB)};if(!w.intentsHidden)r.moves={int(m.moveHistory[0]),int(m.moveHistory[1])};r.powers=bits(m.statusBits,64);r.small.assign(m.smallPowers.begin(),m.smallPowers.end());out.monsters.push_back(std::move(r));}
    require(w.potionCapacity>=0&&static_cast<std::size_t>(w.potionCapacity)<=w.potions.size(),"SilverPriorNet potion capacity");
    for(std::size_t i=0;i<w.potions.size();++i)out.potions.push_back({w.potions[i],int(i),i<static_cast<std::size_t>(w.potionCapacity)?1.f:0.f,w.potions[i]==1?1.f:0.f});
    out.statusPool.assign(16,0.f);out.relicPool.assign(16,0.f);
    for(const auto &s:p.statusMap){require(s.first>=0&&s.first<96,"SilverPriorNet status kind out of range");}
    out.cats={w.encounter,p.stance,p.characterClass,(p.lastTargetedMonster>=0&&p.lastTargetedMonster<w.monsterCount)?p.lastTargetedMonster:7};
    require(out.context.size()==144,"SilverPriorNet context feature width mismatch");
    return out;
}

} // namespace

struct SilverPriorNetV1::Impl {
    Json root; Json vocab; std::string sha;
    std::map<std::string,Matrix> w; std::map<std::string,Vec>b; std::map<std::string,Vec>norm;
    std::map<std::string,Matrix> emb; Vec nullCard,nullMon,nullPot;
    explicit Impl(const std::string &path) {
        std::ifstream f(path);if(!f)throw std::runtime_error("cannot open SilverPriorNet artifact");f>>root;
        require(root.value("schema",std::string{})=="silver_prior_native_v1"&&root.value("model_schema",0)==1&&root.value("architecture",std::string{})=="SilverPriorNetV1","SilverPriorNet artifact schema mismatch");
        require(root.value("checkpoint_sha256",std::string{})=="b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24"&&root.value("arm",std::string{})=="T2"&&root.value("seed",0)==20260922&&root.value("tau",0.0)==1.179975000005129,"SilverPriorNet artifact identity mismatch");
        require(root.value("release_sha256",std::string{})=="b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419"
                &&root.value("binding_sha256",std::string{})=="7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17"
                &&root.value("selection_sha256",std::string{})=="ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed"
                &&root.value("vocabulary_sha256",std::string{})=="7e07db8b10618d7c1e9b9b1b31d8196950c03060c54fd4d25fd057ac7918cd46","SilverPriorNet release binding mismatch");
        const Json dims={{"context",144},{"card_embedding",{158,32}},{"monster_embedding",{2048,16}},
            {"potion_embedding",{256,16}},{"candidate_outputs",1},{"hidden",{128,96}},
            {"parameter_count",232665}};
        require(root.value("dimensions",Json{})==dims,"SilverPriorNet architecture dimensions mismatch");
        vocab=root.at("vocabulary");sha=root.at("artifact_sha256").get<std::string>();
        require(vocab.is_object()&&vocab.size()==158,"SilverPriorNet compact vocabulary size mismatch");
        std::set<int> compactIds;for(auto it=vocab.begin();it!=vocab.end();++it)compactIds.insert(it.value().get<int>());
        require(compactIds.size()==158&&*compactIds.begin()==0&&*compactIds.rbegin()==157,"SilverPriorNet compact vocabulary is not bijective");
        for(auto it=root.at("state_dict").begin();it!=root.at("state_dict").end();++it){const auto &n=it.key();const auto &x=it.value();
            if(n=="null_card")nullCard=x.get<Vec>();else if(n=="null_monster")nullMon=x.get<Vec>();else if(n=="null_potion")nullPot=x.get<Vec>();
            else if(n.find(".weight")!=std::string::npos){auto key=n.substr(0,n.size()-7);const bool embeddingTable=std::count(n.begin(),n.end(),'.')==1;if(embeddingTable)emb[key]=x.get<Matrix>();else w[key]=x.get<Matrix>();}
            else if(n.find(".bias")!=std::string::npos)b[n.substr(0,n.size()-5)]=x.get<Vec>();
        }
        for(auto it=root.at("normalization").begin();it!=root.at("normalization").end();++it)norm[it.key()]=it.value().get<Vec>();
        require(nullCard.size()==64&&nullMon.size()==64&&nullPot.size()==24,"SilverPriorNet artifact parameters incomplete");
    }
    Vec layer(const std::string &name,const Vec &x)const{return linear(w.at(name),b.at(name),x);}
    Vec net(const std::string &a,const Vec&x)const{return gelu(linear(w.at(a+".2"),b.at(a+".2"),gelu(linear(w.at(a+".0"),b.at(a+".0"),x))));}
    Vec logits(const BattleStateWire &state,const std::vector<SemanticAction>&actions)const {
        const auto in=buildInput(state,actions,vocab);const auto n=in.context.size();(void)n;
        std::vector<Vec> ce;
        for(const auto &c:in.cards){Vec x=embedding(emb.at("card"),c.f.id);x=append(std::move(x),embedding(emb.at("zone"),c.zone));x=append(std::move(x),embedding(emb.at("segment"),c.segment));x=append(std::move(x),normalized(cardNumeric(c.f,c.position,c.positioned),norm.at("card_mean"),norm.at("card_std")));ce.push_back(net("card_mlp",x));}
        Vec cardState=pool(ce,64);
        std::vector<Vec> me;
        for(const auto &m:in.monsters){Vec moves(8,0.f),powers(8,0.f);for(std::size_t i=0;i<m.moves.size();++i){auto v=embedding(emb.at("move"),m.moves[i]);auto step=embedding(emb.at("move_step"),int(i));for(int j=0;j<8;++j)moves[j]+=v[j]+step[j];}if(!m.moves.empty())for(float &x:moves)x/=std::sqrt(float(m.moves.size()));for(int id:m.powers){auto v=embedding(emb.at("power"),id);for(int j=0;j<8;++j)powers[j]+=v[j];}if(!m.powers.empty())for(float &x:powers)x/=std::sqrt(float(m.powers.size()));Vec small(8,0.f);for(int id=0;id<11;++id){auto v=embedding(emb.at("small_kind"),id);float raw=(m.small[id]-norm.at("small_mean")[id])/norm.at("small_std")[id];for(int j=0;j<8;++j)small[j]+=v[j]*raw/std::sqrt(11.f);}Vec x=embedding(emb.at("monster"),m.id);x=append(std::move(x),embedding(emb.at("slot"),m.slot));x=append(std::move(x),normalized(m.nums,norm.at("monster_mean"),norm.at("monster_std")));x=append(std::move(x),moves);x=append(std::move(x),powers);x=append(std::move(x),small);me.push_back(net("mon_mlp",x));}
        Vec monState=pool(me,64);std::vector<Vec> pe;
        for(const auto &p:in.potions){Vec x=embedding(emb.at("potion"),p.id);x=append(std::move(x),embedding(emb.at("potion_slot"),p.slot));x.insert(x.end(),{p.available,p.empty});pe.push_back(gelu(layer("pot_mlp.0",x)));}
        Vec potState=pool(pe,24),status(16,0.f),relic(16,0.f);
        // status/relic presence and values are independent sets pooled by identity.
        const auto &pl=state.player;
        for(auto [k,v]:pl.statusMap){require(k>=0&&k<96,"SilverPriorNet status id out of range");Vec e=embedding(emb.at("status_kind"),k);float a=(v-norm.at("status_mean")[0])/norm.at("status_std")[0];for(int j=0;j<16;++j)status[j]+=e[j]*a;}
        for(auto k:bits(pl.statusBits0,64)){bool inMap=std::any_of(pl.statusMap.begin(),pl.statusMap.end(),[&](const auto &v){return v.first==k;});if(!inMap){Vec e=embedding(emb.at("status_kind"),k);for(int j=0;j<16;++j)status[j]+=e[j];}}
        for(auto k:bits(pl.statusBits1,32)){int id=64+k;bool inMap=std::any_of(pl.statusMap.begin(),pl.statusMap.end(),[&](const auto &v){return v.first==id;});if(!inMap){Vec e=embedding(emb.at("status_kind"),id);for(int j=0;j<16;++j)status[j]+=e[j];}}
        for(auto k:bits(pl.justAppliedBits,32)){Vec e=embedding(emb.at("just_kind"),k);for(int j=0;j<16;++j)status[j]+=e[j];}
        for(auto k:bits(pl.relicBits0,64)){Vec e=embedding(emb.at("relic_kind"),k);for(int j=0;j<16;++j)relic[j]+=e[j];}
        for(auto k:bits(pl.relicBits1,64)){Vec e=embedding(emb.at("relic_kind"),64+k);for(int j=0;j<16;++j)relic[j]+=e[j];}
        for(std::size_t i=0;i<pl.relicCounters.size();++i){Vec e=embedding(emb.at("relic_kind"),i);float a=(pl.relicCounters[i]-norm.at("relic_mean")[0])/norm.at("relic_std")[0];for(int j=0;j<16;++j)relic[j]+=e[j]*a;}
        Vec cats=embedding(emb.at("encounter"),in.cats[0]);cats=append(std::move(cats),embedding(emb.at("stance"),in.cats[1]));cats=append(std::move(cats),embedding(emb.at("character"),in.cats[2]));cats=append(std::move(cats),embedding(emb.at("last_target"),in.cats[3]));
        Vec context=normalized(in.context,norm.at("context_mean"),norm.at("context_std"));context=append(std::move(context),status);context=append(std::move(context),relic);context=append(std::move(context),cats);context=net("context_mlp",context);
        Vec stateVec=context;stateVec=append(std::move(stateVec),cardState);stateVec=append(std::move(stateVec),monState);stateVec=append(std::move(stateVec),potState);stateVec=net("state_mlp",stateVec);
        std::vector<Vec> scores; scores.reserve(actions.size());
        for(const auto &a:actions){require(a.type==SemanticActionType::CARD||a.type==SemanticActionType::POTION||a.type==SemanticActionType::END_TURN,"SilverPriorNet unsupported semantic action");int cardRef=-1,monRef=-1,potRef=-1;if(a.type==SemanticActionType::CARD){for(std::size_t i=0;i<in.cards.size();++i)if(in.cards[i].zone==0&&*in.cards[i].wire==a.card){if(cardRef!=-1)throw std::runtime_error("SilverPriorNet ambiguous card occurrence");cardRef=int(i);}require(cardRef>=0,"SilverPriorNet missing legal card occurrence");}int target=a.target;if(a.type==SemanticActionType::POTION&&a.discardPotion&&(target==-1||target>5))target=-1;if(target!=-1){require(target>=0&&target<static_cast<int>(state.monsters.size())&&target<state.monsterCount&&state.monsters[target].idx==target,"SilverPriorNet invalid target reference");for(std::size_t i=0;i<in.monsters.size();++i)if(in.monsters[i].slot==target)monRef=int(i);require(monRef>=0,"SilverPriorNet absent target monster");}if(a.type==SemanticActionType::POTION){require(a.potionSlot>=0&&a.potionSlot<state.potionCapacity&&state.potions[a.potionSlot]==a.potionId,"SilverPriorNet invalid potion slot");for(std::size_t i=0;i<in.potions.size();++i)if(in.potions[i].slot==a.potionSlot)potRef=int(i);require(potRef>=0,"SilverPriorNet absent potion");}
            int type=int(a.type),zone=int(a.source);Vec ac=embedding(emb.at("action_type"),type);ac=append(std::move(ac),embedding(emb.at("action_zone"),zone));ac=append(std::move(ac),cardRef<0?nullCard:ce[cardRef]);ac=append(std::move(ac),monRef<0?nullMon:me[monRef]);ac=append(std::move(ac),potRef<0?nullPot:pe[potRef]);ac.insert(ac.end(),{a.discardPotion?1.f:0.f,a.skipCardSelect?1.f:0.f,float(a.cardSelectTask),a.potionSlot>=0?1.f:0.f});ac=net("action_mlp",ac);Vec both=stateVec;both=append(std::move(both),ac);Vec product(stateVec.size());for(std::size_t j=0;j<product.size();++j)product[j]=stateVec[j]*ac[j];both=append(std::move(both),product);scores.push_back(layer("scorer.2",gelu(layer("scorer.0",both))));}
        Vec out;out.reserve(scores.size());for(auto &v:scores){require(v.size()==1,"SilverPriorNet scorer output");out.push_back(v[0]);}return out;
    }
};

SilverPriorNetV1::SilverPriorNetV1(const std::string &path):impl_(std::make_unique<Impl>(path)){}
SilverPriorNetV1::~SilverPriorNetV1()=default;
SilverPriorNetV1::SilverPriorNetV1(SilverPriorNetV1&&) noexcept=default;
SilverPriorNetV1 &SilverPriorNetV1::operator=(SilverPriorNetV1&&) noexcept=default;
std::vector<double> SilverPriorNetV1::logits(const silver_bridge::BattleStateWire&s,const std::vector<silver_bridge::SemanticAction>&a)const{auto f=impl_->logits(s,a);return {f.begin(),f.end()};}
std::vector<double> SilverPriorNetV1::prior(const silver_bridge::BattleStateWire&s,const std::vector<silver_bridge::SemanticAction>&a)const{auto z=logits(s,a);double m=*std::max_element(z.begin(),z.end()),sum=0;for(double &x:z){x=std::exp(x-m);sum+=x;}require(sum>0&&std::isfinite(sum),"SilverPriorNet softmax failure");for(double &x:z)x/=sum;return z;}
const std::string &SilverPriorNetV1::artifactSha256()const{return impl_->sha;}

} // namespace sts::search
