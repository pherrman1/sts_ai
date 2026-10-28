// mapdump <ascension> < seeds.txt : one JSON line per (seed, act 1-3): rooms/edges/burning elite.
#include "game/Map.h"
#include <iostream>
#include <string>
using namespace sts;
int main(int argc, char **argv) {
    const int asc = std::stoi(argv[1]);
    std::string s;
    while (std::cin >> s) {
        const std::uint64_t seed = static_cast<std::uint64_t>(std::stoll(s));
        for (int act = 1; act <= 3; ++act) {
            Map m = Map::fromSeed(seed, asc, act, true);
            std::cout << "{\"seed\":\"" << s << "\",\"act\":" << act << ",\"bx\":" << m.burningEliteX
                      << ",\"by\":" << m.burningEliteY << ",\"nodes\":[";
            bool first = true;
            for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
                const MapNode &n = m.getNode(x, y);
                if (n.room == Room::NONE) continue;
                std::cout << (first ? "" : ",") << "[" << x << "," << y << "," << int(n.room) << ",[";
                for (int k = 0; k < n.edgeCount; ++k) std::cout << (k ? "," : "") << int(n.edges[k]);
                std::cout << "]]"; first = false;
            }
            std::cout << "]}\n";
        }
    }
}
