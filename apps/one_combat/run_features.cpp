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
    std::array<bool, 7> reach{};
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const sts::MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return fm;
        const sts::MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<bool, 7> nxt{};
        for (int x = 0; x < 7; ++x) if (reach[x]) {
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
            for (int i = 0; i < n.edgeCount; ++i) nxt[n.edges[i]] = true;
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
