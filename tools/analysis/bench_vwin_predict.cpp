#include "compact_tree.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

int main(int argc, char **argv) {
    if (argc < 2 || argc > 3) {
        std::cerr << "usage: bench_vwin_predict <trees.txt> [calls]\n";
        return 2;
    }
    const std::string model_path = argv[1];
    const int calls = argc == 3 ? std::stoi(argv[2]) : 20000;
    if (calls < 10000) {
        std::cerr << "calls must be at least 10000\n";
        return 2;
    }

    std::ifstream in(model_path);
    if (!in) {
        std::cerr << "cannot open " << model_path << "\n";
        return 1;
    }
    std::unordered_map<std::string, int> feature_idx;
    std::string line;
    while (std::getline(in, line)) {
        std::string key, name;
        std::istringstream parser(line);
        parser >> key;
        if (key == "feat") {
            parser >> name;
            feature_idx.emplace(name, static_cast<int>(feature_idx.size()));
        }
    }

    one_combat::CompactTreeNet model;
    if (!model.load(model_path, feature_idx, "v_win latency benchmark")) return 1;
    std::vector<float> raw(feature_idx.size(), 0.0f);
    const auto put = [&](const char *name, float value) {
        const auto it = feature_idx.find(name);
        if (it != feature_idx.end()) raw[it->second] = value;
    };
    put("act", 1.0f);
    put("floor", 30.0f);
    put("curHp", 60.0f);
    put("maxHp", 80.0f);
    put("gold", 100.0f);
    put("potionCount", 1.0f);
    put("potionCapacity", 3.0f);

    std::vector<double> micros;
    micros.reserve(calls);
    double sink = 0.0;
    for (int i = 0; i < calls; ++i) {
        const auto start = std::chrono::steady_clock::now();
        sink += model.predict(raw);
        const auto end = std::chrono::steady_clock::now();
        micros.push_back(std::chrono::duration<double, std::micro>(end - start).count());
    }
    std::sort(micros.begin(), micros.end());
    const double median = micros[micros.size() / 2];
    const double p95 = micros[static_cast<std::size_t>(0.95 * (micros.size() - 1))];
    std::cout << std::setprecision(10)
              << "{\"calls\":" << calls
              << ",\"median_us\":" << median
              << ",\"p95_us\":" << p95
              << ",\"sink\":" << sink << "}\n";
    return 0;
}
