// Heart leaf features (issue #605): the extra columns follow the rich vector
// in the documented order and read the state X2-B ignores.
#include "one_combat/heart_leaf.h"
#include <iostream>

namespace {
int failures = 0;
void require(bool ok, const char *message) {
    if (!ok) { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
float column(const std::vector<float> &x, const char *name) { return x.at(one_combat::heartLeafIdxMap().at(name)); }
}

int main() {
    using namespace one_combat;
    const auto rich = richIdxMap().size();
    require(heartLeafIdxMap().size() == rich + heartLeafExtraNames().size(), "extras extend the rich map");
    require(heartLeafIdxMap().at("x2bMargin") == int(rich), "x2bMargin is the first extra column");
    require(heartLeafBossFloor(1) == 16 && heartLeafBossFloor(2) == 33 && heartLeafBossFloor(3) == 50
            && heartLeafBossFloor(4) == 56, "boss floors include the Heart");
    sts::GameContext gc(sts::CharacterClass::IRONCLAD, 42, 20);
    PathHistory path;
    auto base = heartLeafFeatureVec(gc, path, -1.25);
    require(base.size() == heartLeafIdxMap().size(), "feature width");
    require(column(base, "x2bMargin") == -1.25f, "anchor margin is passed through");
    require(column(base, "hlDaggerDamage") == 0 && column(base, "hlSearingLevel") == 0, "starter deck has neither card");
    sts::Card dagger(sts::CardId::RITUAL_DAGGER);
    dagger.misc = 21;
    gc.deck.obtainRaw(dagger);
    sts::Card searing(sts::CardId::SEARING_BLOW);
    for (int i = 0; i < 3; ++i) searing.upgrade();
    gc.deck.obtainRaw(searing);
    gc.act = 4; gc.floorNum = 53; gc.blueKey = gc.redKey = true;
    const auto x = heartLeafFeatureVec(gc, path, 0.0);
    require(column(x, "hlDaggerDamage") == 21, "Ritual Dagger damage comes from misc");
    require(column(x, "hlSearingLevel") == 3, "Searing Blow level counts every upgrade");
    require(column(x, "hlFloorsToBoss") == 3 && column(x, "hlAct4") == 1, "Act 4 distance is to the Heart");
    require(column(x, "hlKeys") == 2, "all three keys count");
    if (failures) return 1;
    std::cout << "PASS heart leaf features\n";
    return 0;
}
