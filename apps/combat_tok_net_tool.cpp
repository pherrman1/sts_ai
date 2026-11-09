// Checks and timing for the native combat net (sts::search::CombatTokNet; combat plan stage 3, 2026-11-08).
//
//   combat-tok-net-tool check MODEL.ctn FIXTURE.json
//       FIXTURE (tools/combat_net/make_native_fixture.py): rows of {wire, semantics, expect}. Encodes each wire and
//       its semantics natively, compares with the Python encoder's arrays (`expect`: model.collate of one row) and
//       the net's outputs with PyTorch's. Exit 1 on any mismatch.
//   combat-tok-net-tool forward MODEL.ctn INPUTS.json OUT.json
//       INPUTS: rows of tensorized arrays (the keys of `expect`, e.g. from a collated batch); OUT: logits, value,
//       aux per row.
//   combat-tok-net-tool encode ROWS.jsonl[.gz not supported] OUT.jsonl
//       ROWS: silverazgen root rows (wire + edges[].semantic); OUT: the native arrays per row.
//   combat-tok-net-tool bench MODEL.ctn ROWS.jsonl [REPS]
//       Thread CPU time per root of encode (from the wire JSON) and forward, over the rows of ROWS.
#include <chrono>
#include <cmath>
#include <ctime>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "sim/search/CombatTokNet.h"

using nlohmann::json;
using namespace sts::search;

namespace {

    double cpuSeconds() {
        timespec ts{};
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
        return static_cast<double>(ts.tv_sec) + 1e-9 * static_cast<double>(ts.tv_nsec);
    }

    json toJson(const CombatTokInputs &in) {
        json j;
        j["glob"] = in.glob;
        j["relics"] = in.relics;
        j["sbits"] = in.sbits;
        j["smap"] = in.smap;
        j["mcat"] = in.mcat;
        j["mnum"] = in.mnum;
        j["nmon"] = in.nmon;
        j["potions"] = in.potions;
        j["queues"] = in.queues;
        j["cards"] = in.cards;
        j["actions"] = in.actions;
        return j;
    }

    template <class A>
    void fillInts(const json &src, A &dst) {
        for (std::size_t i = 0; i < dst.size() && i < src.size(); ++i) dst[i] = src[i].get<typename A::value_type>();
    }

    CombatTokInputs fromJson(const json &j) {
        CombatTokInputs in;
        for (int i = 0; i < kCtnGlobLen; ++i) in.glob[i] = j.at("glob")[i].get<float>();
        fillInts(j.at("relics"), in.relics);
        fillInts(j.at("sbits"), in.sbits);
        for (const auto &r : j.at("smap")) in.smap.push_back({r[0].get<std::int16_t>(), r[1].get<std::int16_t>()});
        for (int m = 0; m < kCtnMonMax; ++m) {
            fillInts(j.at("mcat")[m], in.mcat[m]);
            for (int k = 0; k < kCtnMonNum; ++k) in.mnum[m][k] = j.at("mnum")[m][k].get<float>();
        }
        in.nmon = j.at("nmon").get<int>();
        fillInts(j.at("potions"), in.potions);
        for (const auto &r : j.at("queues")) {
            std::array<std::int16_t, kCtnQueueLen> q{};
            fillInts(r, q);
            in.queues.push_back(q);
        }
        for (const auto &r : j.at("cards")) {
            std::array<std::int16_t, 9> c{};
            fillInts(r, c);
            in.cards.push_back(c);
        }
        for (const auto &r : j.at("actions")) {
            std::array<std::int16_t, kCtnActionLen> a{};
            fillInts(r, a);
            in.actions.push_back(a);
        }
        return in;
    }

    json outJson(const CombatTokOutputs &o) { return {{"logits", o.logits}, {"value", o.value}, {"aux", o.aux}}; }

    CombatTokNet loadNet(const std::string &path) {
        CombatTokNet net;
        std::string err;
        if (!net.load(path, &err)) throw std::runtime_error(err);
        return net;
    }

    std::vector<json> readJsonl(const std::string &path) {
        std::ifstream f(path);
        if (!f) throw std::runtime_error("cannot open " + path);
        std::vector<json> rows;
        for (std::string line; std::getline(f, line);)
            if (!line.empty()) rows.push_back(json::parse(line));
        return rows;
    }

    std::vector<std::string> semanticsOf(const json &row) {
        std::vector<std::string> s;
        if (row.contains("semantics")) {
            for (const auto &v : row["semantics"]) s.push_back(v.get<std::string>());
        } else {
            for (const auto &e : row.at("edges")) s.push_back(e.at("semantic").get<std::string>());
        }
        return s;
    }

    void encodeRow(const json &row, CombatTokInputs &in) {
        combatTokEncodeWire(row.at("wire"), in);
        for (const auto &s : semanticsOf(row)) in.actions.push_back(combatTokActionRow(s));
    }

    // Element-wise compare of two JSON trees of numbers; float tolerance for float leaves.
    int compare(const json &a, const json &b, const std::string &path, double atol, double rtol, std::ostream &log,
                int &reported) {
        if (a.is_array() || b.is_array()) {
            if (!a.is_array() || !b.is_array() || a.size() != b.size()) {
                if (reported++ < 20) log << "  " << path << ": shape " << a.dump().substr(0, 80) << " vs "
                                         << b.dump().substr(0, 80) << "\n";
                return 1;
            }
            int bad = 0;
            for (std::size_t i = 0; i < a.size(); ++i)
                bad += compare(a[i], b[i], path + "[" + std::to_string(i) + "]", atol, rtol, log, reported);
            return bad;
        }
        const double x = a.get<double>(), y = b.get<double>();
        if (std::fabs(x - y) <= atol + rtol * std::fabs(y)) return 0;
        if (reported++ < 20) log << "  " << path << ": " << x << " vs " << y << "\n";
        return 1;
    }

    int check(const std::string &modelPath, const std::string &fixturePath) {
        const CombatTokNet net = loadNet(modelPath);
        std::ifstream f(fixturePath);
        if (!f) throw std::runtime_error("cannot open " + fixturePath);
        const json fx = json::parse(f);
        int badRows = 0, rowIdx = 0;
        double maxLogitErr = 0;
        for (const auto &row : fx.at("rows")) {
            CombatTokInputs in;
            encodeRow(row, in);
            const json got = toJson(in);
            const json &want = row.at("expect");
            int reported = 0, bad = 0;
            std::ostringstream log;
            for (const char *k : {"relics", "sbits", "smap", "mcat", "nmon", "potions", "queues", "cards", "actions"})
                bad += compare(got.at(k), want.at(k), k, 0.0, 0.0, log, reported);
            // float16-stored groups: one float16 step (2^-10 relative) for a last-bit log1p difference
            bad += compare(got.at("glob"), want.at("glob"), "glob", 1e-7, 1.0 / 1024, log, reported);
            bad += compare(got.at("mnum"), want.at("mnum"), "mnum", 1e-7, 1.0 / 1024, log, reported);
            CombatTokOutputs out;
            net.forward(in, out);
            const json o = outJson(out);
            for (const char *k : {"logits", "value", "aux"})
                bad += compare(o.at(k), want.at(k), k, 2e-4, 2e-4, log, reported);
            for (std::size_t e = 0; e < out.logits.size() && e < want.at("logits").size(); ++e)
                maxLogitErr = std::max(maxLogitErr, std::fabs(out.logits[e] - want.at("logits")[e].get<double>()));
            if (bad) {
                ++badRows;
                std::cerr << "row " << rowIdx << ": " << bad << " mismatches\n" << log.str();
            }
            ++rowIdx;
        }
        std::cout << "{\"rows\": " << rowIdx << ", \"badRows\": " << badRows << ", \"maxLogitErr\": " << maxLogitErr
                  << "}\n";
        return badRows == 0 && rowIdx > 0 ? 0 : 1;
    }

}  // namespace

int main(int argc, char **argv) {
    try {
        const std::string mode = argc > 1 ? argv[1] : "";
        if (mode == "check" && argc == 4) return check(argv[2], argv[3]);
        if (mode == "forward" && argc == 5) {
            const CombatTokNet net = loadNet(argv[2]);
            std::ifstream f(argv[3]);
            const json rows = json::parse(f);
            json outRows = json::array();
            for (const auto &r : rows.at("rows")) {
                CombatTokOutputs o;
                net.forward(fromJson(r), o);
                outRows.push_back(outJson(o));
            }
            std::ofstream(argv[4]) << json{{"rows", outRows}}.dump() << "\n";
            return 0;
        }
        if (mode == "encode" && argc == 4) {
            std::ofstream out(argv[3]);
            long long n = 0, skipped = 0;
            for (const auto &row : readJsonl(argv[2])) {
                if (row.value("kind", "root") != "root" || !row.contains("wire") || row["wire"].is_null()) {
                    ++skipped;
                    continue;
                }
                CombatTokInputs in;
                encodeRow(row, in);
                out << toJson(in).dump() << "\n";
                ++n;
            }
            std::cout << "{\"encoded\": " << n << ", \"skipped\": " << skipped << "}\n";
            return 0;
        }
        if (mode == "bench" && (argc == 4 || argc == 5)) {
            const CombatTokNet net = loadNet(argv[2]);
            const int reps = argc == 5 ? std::stoi(argv[4]) : 1;
            std::vector<json> rows;
            for (auto &r : readJsonl(argv[3]))
                if (r.value("kind", "root") == "root" && r.contains("wire") && !r["wire"].is_null()) rows.push_back(std::move(r));
            double enc = 0, fwd = 0, tokens = 0, actions = 0;
            long long n = 0;
            for (int rep = 0; rep < reps; ++rep) {
                for (const auto &row : rows) {
                    CombatTokInputs in;
                    CombatTokOutputs out;
                    const double t0 = cpuSeconds();
                    encodeRow(row, in);
                    const double t1 = cpuSeconds();
                    net.forward(in, out);
                    const double t2 = cpuSeconds();
                    enc += t1 - t0;
                    fwd += t2 - t1;
                    tokens += 1 + in.cards.size() + kCtnMonMax + in.smap.size() + in.queues.size();
                    actions += in.actions.size();
                    ++n;
                }
            }
            std::cout << json{{"roots", n}, {"encodeMs", 1e3 * enc / n}, {"forwardMs", 1e3 * fwd / n},
                              {"meanTokens", tokens / n}, {"meanActions", actions / n}, {"d", net.dim()},
                              {"layers", net.layerCount()}}.dump() << "\n";
            return 0;
        }
        std::cerr << "usage: combat-tok-net-tool check MODEL FIXTURE | forward MODEL INPUTS OUT | encode ROWS OUT"
                     " | bench MODEL ROWS [REPS]\n";
        return 2;
    } catch (const std::exception &e) {
        std::cerr << "combat-tok-net-tool: " << e.what() << "\n";
        return 1;
    }
}
