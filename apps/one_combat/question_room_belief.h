#pragma once

#include "game/GameContext.h"
#include <array>
#include <cmath>
#include <map>
#include <random>
#include <utility>
#include <vector>

namespace one_combat {
// Finite conditioning under the fair uniform 24-bit room-roll prior. This is
// not a posterior over the actual run's hidden PRNG state.
using QuestionChancePosterior = std::vector<std::pair<float,double>>;

inline const std::array<std::uint32_t,100> &questionRoomCellCounts() {
    static const auto counts=[] {
        std::array<std::uint32_t,100> result{};
        const auto lower=[](int cell) {
            std::uint32_t lo=0,hi=1u<<24;
            while(lo<hi) {
                const auto mid=lo+(hi-lo)/2;
                const float roll=static_cast<float>(mid)*0x1p-24f;
                if(static_cast<int>(roll*100.0f)<cell)lo=mid+1; else hi=mid;
            }
            return lo;
        };
        for(int i=0;i<100;++i)result[i]=lower(i+1)-lower(i);
        return result;
    }();
    return counts;
}

struct QuestionRoomBelief {
    QuestionChancePosterior monster{{0.1f,1.0}};
    float shop=0.03f,treasure=0.02f;
    // Observed conversion: -1 unknown, 0 observed absent, 1 observed flash.
    bool condition(sts::Room observed,bool juzu,bool previousShop,bool forcedTreasure,int conversion) {
        std::map<float,long double> next;
        for(const auto &[chance,weight]:monster) {
            const auto add=[&](sts::Room latent,std::uint32_t cells) {
                const bool converted=latent==sts::Room::MONSTER && juzu;
                const auto visible=converted?sts::Room::EVENT:latent;
                if(visible!=observed || (conversion>=0 && converted!=(conversion==1)))return;
                const float post=latent==sts::Room::MONSTER?0.1f:chance+0.1f;
                next[post]+=static_cast<long double>(weight)*cells;
            };
            if(forcedTreasure)add(sts::Room::TREASURE,1u<<24);
            else for(int cell=0;cell<100;++cell)
                add(sts::GameContext::questionRoomOutcomeForCell(cell,chance,shop,treasure,previousShop),
                    questionRoomCellCounts()[cell]);
        }
        long double total=0;for(const auto &[chance,weight]:next)total+=weight;
        if(!(total>0) || !std::isfinite(total))return false;
        monster.clear();for(const auto &[chance,weight]:next)if(weight>0)monster.emplace_back(chance,static_cast<double>(weight/total));
        shop=observed==sts::Room::SHOP?0.03f:shop+0.03f;
        treasure=observed==sts::Room::TREASURE?0.02f:treasure+0.02f;
        return true;
    }
};

inline void sampleQuestionChancePosterior(sts::GameContext &state,std::mt19937_64 &rng,
                                         const QuestionChancePosterior &posterior) {
    if(posterior.empty())return;
    if(posterior.size()==1) { state.monsterChance=posterior.front().first;return; }
    const double draw=std::generate_canonical<double,53>(rng);
    double cumulative=0;
    for(const auto &[chance,weight]:posterior) {
        cumulative+=weight;
        if(draw<cumulative) { state.monsterChance=chance;return; }
    }
    state.monsterChance=posterior.back().first; // roundoff at the normalized upper endpoint
}
} // namespace one_combat
