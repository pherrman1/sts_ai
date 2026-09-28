#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include "combat/BattleContextBinary.h"
#include "sim/search/SilverUselessAction.h"

int main(int argc, char **argv) {
    if (argc != 2) { std::cerr << "usage: silver_useless_replay TRACE.jsonl\n"; return 2; }
    try {
        std::ifstream in(argv[1]);
        if (!in) throw std::runtime_error("cannot open trace");
        std::string line;
        int verified = 0;
        while (std::getline(in, line)) {
            const auto row = nlohmann::json::parse(line);
            if (row.at("schema") != 1) throw std::runtime_error("unknown schema");
            if (!row.at("provably_useless").get<bool>()) continue;
            if (++verified > 128) throw std::runtime_error("local replay cap is 128 snapshots");
            const auto bytes = row.at("snapshot").get<std::vector<std::uint8_t>>();
            auto bc = sts::deserializeBattleContext(bytes.data(), bytes.size());
            bc.loopCount = row.at("root_loop_count").get<int>();
            bc.energyWasted = row.at("root_energy_wasted").get<int>();
            if (std::to_string(bc.seed) != row.at("seed").get<std::string>()
                || bc.floorNum != row.at("floor").get<int>() || bc.turn != row.at("turn").get<int>())
                throw std::runtime_error("snapshot identity mismatch");
            const auto proof = sts::search::proveSilverUselessBlock(bc,
                sts::search::Action(row.at("chosen_action").get<std::uint32_t>()));
            if (!proof.verified || proof.snapshot != bytes || proof.energySpent != row.at("energy_spent")
                || proof.blockGained != row.at("block_gained")
                || proof.energyWasteDelta != row.at("energy_wasted_delta")
                || proof.extraLoopSteps != row.at("extra_loop_steps"))
                throw std::runtime_error("mechanical proof did not reproduce: " + proof.reason);
        }
        std::cout << "silver_useless_replay verified=" << verified << " PASS\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "silver_useless_replay FAIL: " << e.what() << '\n';
        return 1;
    }
}
