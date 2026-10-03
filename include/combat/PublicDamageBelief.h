// Finite public recipient-outcome conditioning for vanilla Bite/Nip damage.
#ifndef STS_PUBLIC_DAMAGE_BELIEF_H
#define STS_PUBLIC_DAMAGE_BELIEF_H
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
namespace sts {
struct PublicDamageObservation {
    int beforeHp=0, afterHp=0, beforeBlock=0, afterBlock=0;
    int beforeBuffer=0, afterBuffer=0, maxHp=0, strength=0, reviveHp=0;
    bool weak=false, vulnerable=false, intangible=false, oddMushroom=false;
    bool paperKrane=false, torii=false, tungstenRod=false, wrath=false;
};
inline std::uint16_t filterPublicDamageBelief(std::uint16_t prior, const PublicDamageObservation &o) {
    if(!prior || o.maxHp<1 || o.maxHp>32767 || o.beforeHp<1 || o.beforeHp>o.maxHp
            || o.afterHp<0 || o.afterHp>o.maxHp || o.beforeBlock<0 || o.beforeBlock>999
            || o.afterBlock<0 || o.afterBlock>o.beforeBlock || o.beforeBuffer<0 || o.beforeBuffer>999
            || o.afterBuffer<0 || o.afterBuffer>o.beforeBuffer || o.strength < -999 || o.strength>999
            || o.reviveHp<0 || o.reviveHp>o.maxHp) throw std::invalid_argument("invalid public damage observation");
    std::uint16_t posterior=0;
    for(int base=0;base<16;++base) if(prior&(1u<<base)) {
        float damage=static_cast<float>(base+o.strength);
        if(o.weak) damage*=o.paperKrane?0.6f:0.75f;
        if(o.vulnerable) damage*=o.oddMushroom?1.25f:1.5f;
        if(o.wrath) damage*=2;
        if(o.intangible) damage=std::min(damage,1.0f);
        int hit=std::max(0,static_cast<int>(std::floor(damage)));
        const int block=std::max(0,o.beforeBlock-hit);
        hit-=o.beforeBlock;
        if(hit>0 && o.beforeBuffer>0) hit=0;
        if(hit>0 && hit<=5 && o.torii) hit=1;
        if(hit>0 && o.tungstenRod) --hit;
        int hp=o.beforeHp-std::max(0,hit);
        if(hp<=0) hp=o.reviveHp;
        hp=std::max(0,hp);
        if(hp==o.afterHp && block==o.afterBlock && o.beforeBuffer==o.afterBuffer) posterior|=std::uint16_t(1u<<base);
    }
    if(!posterior) throw std::invalid_argument("impossible public damage observation");
    return posterior;
}
}
#endif
