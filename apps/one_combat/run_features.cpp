#include "run_features.h"

#include <algorithm>
#include <array>
#include <sstream>

namespace one_combat {

void PathHistory::update(const sts::GameContext &gc) {
    if (gc.curMapNodeY < 0 || gc.curMapNodeY >= 15 || gc.curMapNodeX < 0 || gc.curMapNodeX >= 7)
        return;
    const long key = (long)gc.act * 100000 + (long)gc.curMapNodeY * 100 + gc.curMapNodeX;
    if (key == lastNodeKey) return;
    lastNodeKey = key;
    const int ri = (int)gc.getCurMapNode().room;
    if (ri >= 0 && ri < 10) ++roomVisits[ri];
}

FwdMap forwardMapFeatures(const sts::GameContext &gc) {
    FwdMap fm;
    fm.dBoss = 14 - std::max(gc.curMapNodeY, 0);
    if (gc.map == nullptr) return fm;
    const sts::Map &map = *gc.map;
    // Track remaining Wing Boots charges along each visible path. The frozen
    // model has no charge scalar, but its existing forward-map features can
    // describe rooms reachable through the public charged map edges.
    std::array<std::array<bool, 4>, 7> reach{};
    const int charges = std::clamp(gc.wingBootsCharges, 0, 3);
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const sts::MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x][charges] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return fm;
        const sts::MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]][charges] = true;
        if (charges > 0 && cur.edgeCount > 0 && gc.curMapNodeY < 14)
            for (int x = 0; x < 7; ++x)
                if (map.getNode(x, startRow).room != sts::Room::NONE)
                    reach[x][charges - 1] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<std::array<bool, 4>, 7> nxt{};
        for (int x = 0; x < 7; ++x) if (std::any_of(reach[x].begin(), reach[x].end(),
                                                     [](bool found) { return found; })) {
            const sts::MapNode &n = map.getNode(x, y);
            const int d = y - base;
            switch (n.room) {
                case sts::Room::ELITE:    ++fm.cElite;    fm.dElite = std::min(fm.dElite, d); break;
                case sts::Room::REST:     ++fm.cRest;     fm.dRest  = std::min(fm.dRest,  d); break;
                case sts::Room::SHOP:     ++fm.cShop;     fm.dShop  = std::min(fm.dShop,  d); break;
                case sts::Room::EVENT:    ++fm.cEvent;    break;
                case sts::Room::MONSTER:  ++fm.cMonster;  break;
                case sts::Room::TREASURE: ++fm.cTreasure; break;
                default: break;
            }
            for (int charge = 0; charge <= 3; ++charge) {
                if (!reach[x][charge]) continue;
                for (int i = 0; i < n.edgeCount; ++i)
                    nxt[n.edges[i]][charge] = true;
                if (charge > 0 && n.edgeCount > 0 && y < 14)
                    for (int destination = 0; destination < 7; ++destination)
                        if (map.getNode(destination, y + 1).room != sts::Room::NONE)
                            nxt[destination][charge - 1] = true;
            }
        }
        reach = nxt;
    }
    return fm;
}

std::string richHeader() {
    std::ostringstream h;
    h << "seed,ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor,"
         "blueKey,greenKey,redKey,potionCount,potionCapacity,"
         "bossId,nextEliteId,nextFight0,nextFight1,nextFight2,remElites,remFights,monOffset,eliteOffset,"
         "pvShop,pvRest,pvEvent,pvElite,pvMonster,pvTreasure,"
         "bottledAtkId,bottledSkillId,bottledPowId";
    for (int i = 0; i < kNumCardIds; ++i) h << ",d" << i;
    for (int i = 0; i < kNumCardIds; ++i) h << ",u" << i;
    for (int i = 0; i < kNumRelics;  ++i) h << ",r" << i;
    for (int i = 0; i < kNumPotions; ++i) h << ",pot" << i;
    h << ",fmDElite,fmDRest,fmDShop,fmDBoss,fmCElite,fmCRest,fmCShop,fmCEvent,fmCMonster,fmCTreasure";
    h << ",curMapX,curMapY";
    h << ",won,finalFloor,endHp";
    return h.str();
}

std::string richRow(const sts::GameContext &gc, const PathHistory &path) {
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const sts::Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case sts::CardType::ATTACK: botAtk = id; break;
                case sts::CardType::SKILL:  botSkill = id; break;
                case sts::CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == sts::Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const int nextElite = gc.eliteMonsterListOffset < gc.eliteMonsterList.size()
                        ? (int)gc.eliteMonsterList[gc.eliteMonsterListOffset] : 0;
    auto nf = [&](int k) -> int {
        const int idx = gc.monsterListOffset + k;
        return idx < gc.monsterList.size() ? (int)gc.monsterList[idx] : 0;
    };
    std::ostringstream o;
    o << gc.ascension << ',' << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ','
      << gc.gold << ',' << gc.deck.size() << ',' << gc.potionChance << ',' << gc.cardRarityFactor << ','
      << (gc.blueKey ? 1 : 0) << ',' << (gc.greenKey ? 1 : 0) << ',' << (gc.redKey ? 1 : 0) << ','
      << gc.potionCount << ',' << gc.potionCapacity << ','
      << (int)gc.boss << ',' << nextElite << ',' << nf(0) << ',' << nf(1) << ',' << nf(2) << ','
      << (gc.eliteMonsterList.size() - gc.eliteMonsterListOffset) << ','
      << (gc.monsterList.size() - gc.monsterListOffset) << ','
      << gc.monsterListOffset << ',' << gc.eliteMonsterListOffset << ','
      << path.roomVisits[(int)sts::Room::SHOP]  << ',' << path.roomVisits[(int)sts::Room::REST]     << ','
      << path.roomVisits[(int)sts::Room::EVENT] << ',' << path.roomVisits[(int)sts::Room::ELITE]    << ','
      << path.roomVisits[(int)sts::Room::MONSTER] << ',' << path.roomVisits[(int)sts::Room::TREASURE] << ','
      << botAtk << ',' << botSkill << ',' << botPow;
    for (int i = 0; i < kNumCardIds; ++i) o << ',' << d[i];
    for (int i = 0; i < kNumCardIds; ++i) o << ',' << u[i];
    for (int i = 0; i < kNumRelics;  ++i) o << ',' << r[i];
    for (int i = 0; i < kNumPotions; ++i) o << ',' << pot[i];
    const FwdMap fm = forwardMapFeatures(gc);
    o << ',' << fm.dElite << ',' << fm.dRest << ',' << fm.dShop << ',' << fm.dBoss
      << ',' << fm.cElite << ',' << fm.cRest << ',' << fm.cShop << ',' << fm.cEvent
      << ',' << fm.cMonster << ',' << fm.cTreasure;
    o << ',' << gc.curMapNodeX << ',' << gc.curMapNodeY;
    return o.str();
}

std::vector<float> richFeatureVec(const sts::GameContext &gc, const PathHistory &path) {
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const sts::Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case sts::CardType::ATTACK: botAtk = id; break;
                case sts::CardType::SKILL:  botSkill = id; break;
                case sts::CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == sts::Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const int nextElite = gc.eliteMonsterListOffset < gc.eliteMonsterList.size()
                        ? (int)gc.eliteMonsterList[gc.eliteMonsterListOffset] : 0;
    auto nf = [&](int k) -> int {
        const int idx = gc.monsterListOffset + k;
        return idx < gc.monsterList.size() ? (int)gc.monsterList[idx] : 0;
    };
    std::vector<float> values;
    values.reserve(32 + 2 * kNumCardIds + kNumRelics + kNumPotions + 12);
    const auto append = [&](auto value) { values.push_back(static_cast<float>(value)); };
    append(gc.ascension);
    append(gc.act);
    append(gc.floorNum);
    append(gc.curHp);
    append(gc.maxHp);
    append(gc.gold);
    append(gc.deck.size());
    append(gc.potionChance);
    append(gc.cardRarityFactor);
    append((gc.blueKey ? 1 : 0));
    append((gc.greenKey ? 1 : 0));
    append((gc.redKey ? 1 : 0));
    append(gc.potionCount);
    append(gc.potionCapacity);
    append((int)gc.boss);
    append(nextElite);
    append(nf(0));
    append(nf(1));
    append(nf(2));
    append((gc.eliteMonsterList.size() - gc.eliteMonsterListOffset));
    append((gc.monsterList.size() - gc.monsterListOffset));
    append(gc.monsterListOffset);
    append(gc.eliteMonsterListOffset);
    append(path.roomVisits[(int)sts::Room::SHOP]);
    append(path.roomVisits[(int)sts::Room::REST]);
    append(path.roomVisits[(int)sts::Room::EVENT]);
    append(path.roomVisits[(int)sts::Room::ELITE]);
    append(path.roomVisits[(int)sts::Room::MONSTER]);
    append(path.roomVisits[(int)sts::Room::TREASURE]);
    append(botAtk);
    append(botSkill);
    append(botPow);
    for (int i = 0; i < kNumCardIds; ++i) append(d[i]);
    for (int i = 0; i < kNumCardIds; ++i) append(u[i]);
    for (int i = 0; i < kNumRelics;  ++i) append(r[i]);
    for (int i = 0; i < kNumPotions; ++i) append(pot[i]);
    const FwdMap fm = forwardMapFeatures(gc);
    append(fm.dElite);
    append(fm.dRest);
    append(fm.dShop);
    append(fm.dBoss);
    append(fm.cElite);
    append(fm.cRest);
    append(fm.cShop);
    append(fm.cEvent);
    append(fm.cMonster);
    append(fm.cTreasure);
    append(gc.curMapNodeX);
    append(gc.curMapNodeY);
    return values;
}

std::string richStateHeader() {
    std::string h = richHeader();
    const std::string prefix = "seed,";
    if (h.rfind(prefix, 0) == 0) h.erase(0, prefix.size());
    const std::string labels = ",won,finalFloor,endHp";
    const size_t p = h.rfind(labels); if (p != std::string::npos) h.erase(p);
    return h;
}

const std::unordered_map<std::string, int> &richIdxMap() {
    static std::unordered_map<std::string, int> m;
    if (m.empty()) {
        std::string h = richHeader(); std::vector<std::string> names; std::string cur;
        for (char c : h) { if (c == ',') { names.push_back(cur); cur.clear(); } else cur += c; }
        names.push_back(cur);
        for (int i = 1; i + 3 < (int)names.size(); ++i) m[names[i]] = i - 1;
    }
    return m;
}

} // namespace one_combat
