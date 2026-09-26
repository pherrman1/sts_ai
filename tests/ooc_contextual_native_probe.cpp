#include "ooc_strategic_tok_net.h"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <time.h>
#include <vector>

using Json = nlohmann::json;

namespace {
using Net = OocStrategicTokNet;
constexpr std::array<float, Net::DECKDIM> kAttentionDeckGolden = {
    -0.942901313f, 1.54385173f, 0.646974027f, -0.0874548182f,
    -3.01819682f, 1.68712866f, 2.33106971f, -1.63921452f,
    1.14547133f, 2.15668821f, 0.885743082f, -0.38766101f,
    -0.32863757f, -1.80774391f, 0.662711143f, 0.141145781f,
    0.555907428f, 0.415193468f, 0.197439134f, 1.81830132f,
    -1.16771758f, 0.454212219f, 1.30274236f, -0.0718409196f,
    -1.97890139f, -0.39426145f, -0.464067698f, 0.311064243f,
    -1.20211136f, -2.19085431f, 0.342792779f, 1.10881054f,
};

struct StateInput {
    float glob[Net::NGLB]{};
    int nDk = 0, nRl = 0, nPt = 0;
    int dk[Net::MAXDK][3]{};
    int rl[Net::MAXRL][2]{};
    int pt[Net::MAXPT][2]{};
};

struct SourceInput {
    std::uint32_t bits = 0;
    int cats[6]{};
    int actionType = 0;
    int screen = 0;
    int entityType = 0;
    int entityId = -1;
    float price = 0;
};

struct CandidateInput {
    std::uint32_t primitiveBits = 0;
    std::vector<std::size_t> sources;
};

struct PriorInput {
    std::string key;
    StateInput state;
    std::vector<SourceInput> sources;
    std::vector<CandidateInput> candidates;
    std::vector<std::size_t> multiplicity;
    double temperature = 1.0;
};

struct PriorOutput {
    std::vector<float> deck;
    std::vector<double> sourceLogits;
    std::vector<double> candidateLogits;
    std::vector<double> normalizedPrior;
};

double benchmarkSink = 0;

double threadCpuSeconds() {
    timespec value{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != 0)
        throw std::runtime_error("clock_gettime(CLOCK_THREAD_CPUTIME_ID) failed");
    return static_cast<double>(value.tv_sec) + static_cast<double>(value.tv_nsec) * 1e-9;
}

template <std::size_t N>
void readIntTokens(const Json &items, int (&out)[N][2], int &count,
                   const char *label) {
    if (!items.is_array() || items.size() > N)
        throw std::runtime_error(std::string("invalid ") + label + " token count");
    count = static_cast<int>(items.size());
    for (int i = 0; i < count; ++i) {
        if (!items[i].is_array() || items[i].size() != 2)
            throw std::runtime_error(std::string("invalid ") + label + " token width");
        out[i][0] = items[i][0].get<int>();
        out[i][1] = items[i][1].get<int>();
    }
}

PriorInput parsePrior(const Json &row) {
    PriorInput result;
    result.key = row.value("priorKey", std::string{});
    const Json &tokens = row.at("tokenState");
    const auto &glob = tokens.at("glob");
    if (!glob.is_array() || glob.size() != Net::NGLB)
        throw std::runtime_error("captured global vector must have 42 values");
    for (int i = 0; i < Net::NGLB; ++i) {
        result.state.glob[i] = glob[i].get<float>();
        if (!std::isfinite(result.state.glob[i]))
            throw std::runtime_error("captured global vector contains a non-finite value");
    }
    const Json &deck = tokens.at("deck");
    const Json &deckTokens = deck.at("tokens");
    if (deck.value("nDk", -1) != static_cast<int>(deckTokens.size())
            || deckTokens.size() > Net::MAXDK)
        throw std::runtime_error("captured deck token count differs from payload");
    result.state.nDk = static_cast<int>(deckTokens.size());
    for (int i = 0; i < result.state.nDk; ++i) {
        if (!deckTokens[i].is_array() || deckTokens[i].size() != 3)
            throw std::runtime_error("captured deck token width differs from three");
        for (int j = 0; j < 3; ++j) result.state.dk[i][j] = deckTokens[i][j].get<int>();
    }
    const Json &relic = tokens.at("relic");
    readIntTokens(relic.at("tokens"), result.state.rl, result.state.nRl, "relic");
    if (relic.value("nRl", -1) != result.state.nRl)
        throw std::runtime_error("captured relic token count differs from payload");
    const Json &potion = tokens.at("potion");
    readIntTokens(potion.at("tokens"), result.state.pt, result.state.nPt, "potion");
    if (potion.value("nPt", -1) != result.state.nPt)
        throw std::runtime_error("captured potion token count differs from payload");

    result.temperature = row.at("priorTemperature").get<double>();
    if (!std::isfinite(result.temperature) || result.temperature <= 0)
        throw std::runtime_error("captured prior temperature is invalid");

    const auto &sources = row.at("sourcePrimitives");
    std::map<std::uint32_t, std::size_t> sourceIndex;
    result.sources.reserve(sources.size());
    for (const auto &item : sources) {
        SourceInput source;
        source.bits = item.at("primitiveBits").get<std::uint32_t>();
        const auto &cats = item.at("cats");
        if (!cats.is_array() || cats.size() != 6)
            throw std::runtime_error("captured source category width differs from six");
        for (int i = 0; i < 6; ++i) source.cats[i] = cats[i].get<int>();
        source.actionType = item.at("actionType").get<int>();
        source.screen = item.at("screen").get<int>();
        source.entityType = item.at("entityType").get<int>();
        source.entityId = item.at("entityId").get<int>();
        source.price = item.at("goldGePrice").get<float>();
        if (source.entityType < 0 || source.entityType > 3 || !std::isfinite(source.price))
            throw std::runtime_error("captured source entity feature is invalid");
        if (!sourceIndex.emplace(source.bits, result.sources.size()).second)
            throw std::runtime_error("captured source primitive bits are duplicated");
        result.sources.push_back(source);
    }

    const auto &candidates = row.at("candidates");
    if (row.at("candidateCount").get<std::size_t>() != candidates.size())
        throw std::runtime_error("captured candidate count differs from payload");
    result.candidates.reserve(candidates.size());
    std::map<std::uint32_t, std::size_t> counts;
    for (const auto &item : candidates) {
        CandidateInput candidate;
        candidate.primitiveBits = item.at("primitiveBits").get<std::uint32_t>();
        ++counts[candidate.primitiveBits];
        const auto &group = item.at("priorSourceGroup");
        if (group.empty()) {
            const auto found = sourceIndex.find(candidate.primitiveBits);
            if (found == sourceIndex.end())
                throw std::runtime_error("direct candidate is missing its source primitive");
            candidate.sources.push_back(found->second);
        } else {
            for (const auto &bits : group) {
                const auto found = sourceIndex.find(bits.get<std::uint32_t>());
                if (found == sourceIndex.end())
                    throw std::runtime_error("semantic group is missing a source primitive");
                candidate.sources.push_back(found->second);
            }
        }
        result.candidates.push_back(std::move(candidate));
    }
    if (result.candidates.size() < 2 || result.sources.empty())
        throw std::runtime_error("eligible prior has insufficient source or candidate rows");
    for (const auto &candidate : result.candidates)
        result.multiplicity.push_back(counts.at(candidate.primitiveBits));
    return result;
}

std::vector<PriorInput> readPriors() {
    std::vector<PriorInput> rows;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        rows.push_back(parsePrior(Json::parse(line)));
    }
    if (rows.empty()) throw std::runtime_error("no captured priors were provided on stdin");
    return rows;
}

PriorOutput evaluatePrior(const Net &model, const PriorInput &row, bool includeDeck = true) {
    PriorOutput result;
    if (includeDeck) {
        result.deck.resize(Net::DECKDIM);
        model.encodeDeck(row.state.nDk, row.state.dk, result.deck.data());
    }
    const auto prepared = model.prepareState(row.state.glob, row.state.nDk, row.state.dk,
        row.state.nRl, row.state.rl, row.state.nPt, row.state.pt);
    const auto prefix = model.preparePolicyPrefix(prepared);
    result.sourceLogits.reserve(row.sources.size());
    for (const auto &source : row.sources) {
        const float entity[4] = {float(source.entityType == 0), float(source.entityType == 1),
                                 float(source.entityType == 2), float(source.entityType == 3)};
        const float logit = model.predictPolicyLogit(prepared, prefix, source.bits, source.cats,
            source.actionType, source.screen, entity, source.entityId, source.price);
        if (!std::isfinite(logit)) throw std::runtime_error("native source logit is non-finite");
        result.sourceLogits.push_back(logit);
    }
    result.candidateLogits.reserve(row.candidates.size());
    for (const auto &candidate : row.candidates) {
        double sum = 0;
        for (const auto source : candidate.sources) sum += result.sourceLogits.at(source);
        result.candidateLogits.push_back(sum / candidate.sources.size());
    }
    const double largest = *std::max_element(result.candidateLogits.begin(), result.candidateLogits.end());
    std::vector<double> weights;
    weights.reserve(result.candidateLogits.size());
    double total = 0;
    for (std::size_t i = 0; i < result.candidateLogits.size(); ++i) {
        const double weight = std::exp((result.candidateLogits[i] - largest) / row.temperature)
            / row.multiplicity[i];
        if (!std::isfinite(weight) || weight < 0)
            throw std::runtime_error("native candidate prior weight is invalid");
        weights.push_back(weight);
        total += weight;
    }
    if (!std::isfinite(total) || total <= 0)
        throw std::runtime_error("native normalized candidate prior has invalid mass");
    result.normalizedPrior.reserve(weights.size());
    for (const double weight : weights) result.normalizedPrior.push_back(weight / total);
    return result;
}

Json outputJson(const PriorInput &row, const PriorOutput &out) {
    return Json{{"priorKey", row.key}, {"deckRepresentation", out.deck},
                {"sourceLogits", out.sourceLogits}, {"candidateLogits", out.candidateLogits},
                {"normalizedPrior", out.normalizedPrior}};
}

void verifyModelVersion(const Net &model, Net::DeckEncoderVersion expected,
                        const char *label) {
    if (!model.ok || model.deckEncoderVersion != expected)
        throw std::runtime_error(std::string(label) + " artifact loaded with wrong deck encoder version");
}

int compatibility(const std::string &path) {
    Net model;
    if (!model.load(path, true)) throw std::runtime_error("attention artifact failed to load");
    verifyModelVersion(model, Net::DeckEncoderVersion::AttentionV4, "OOC_STRAT_V4");
    const int deck[Net::MAXDK][3] = {{1, 0, 5}, {42, 1, 2}, {100, 0, 1}};
    float encoded[Net::DECKDIM];
    model.encodeDeck(3, deck, encoded);
    float maxError = 0;
    for (int i = 0; i < Net::DECKDIM; ++i)
        maxError = std::max(maxError, std::abs(encoded[i] - kAttentionDeckGolden[i]));
    if (maxError > 2e-5f)
        throw std::runtime_error("OOC_STRAT_V4 attention deck golden changed; max error="
            + std::to_string(maxError));
    float empty[Net::DECKDIM];
    model.encodeDeck(0, deck, empty);
    for (float value : empty)
        if (value != 0) throw std::runtime_error("empty attention deck is not zero");
    std::cout << "PASS OOC_STRAT_V4 attention compatibility max_deck_error=" << maxError << '\n';
    return 0;
}

int contextualLoad(const std::string &path, bool profileCheck) {
    Net model;
    if (!model.load(path, true)) throw std::runtime_error("contextual artifact failed to load");
    verifyModelVersion(model, Net::DeckEncoderVersion::ContextualC1, "OOC_STRAT_C1");
    const int deck[Net::MAXDK][3] = {{1, 0, 5}, {42, 1, 2}, {100, 0, 1}};
    const int relic[Net::MAXRL][2] = {{1, 1}, {23, 4}};
    const int potion[Net::MAXPT][2] = {{2, 1}, {7, 2}};
    float encoded[Net::DECKDIM];
    model.encodeDeck(3, deck, encoded);
    for (float value : encoded)
        if (!std::isfinite(value)) throw std::runtime_error("contextual deck representation is non-finite");
    float empty[Net::DECKDIM];
    model.encodeDeck(0, deck, empty);
    for (float value : empty)
        if (value != 0) throw std::runtime_error("empty contextual deck is not zero");
    float glob[Net::NGLB]{};
    if (profileCheck) {
        one_combat::OocProfileScope parent(one_combat::OocProfileBucket::PolicyPredict);
        (void)model.prepareState(glob, 3, deck, 2, relic, 2, potion);
        const auto stateCalls = one_combat::oocProfileCounters[
            static_cast<std::size_t>(one_combat::OocProfileBucket::V4StateNetwork)].calls;
        const auto deckCalls = one_combat::oocProfileCounters[
            static_cast<std::size_t>(one_combat::OocProfileBucket::V4EncodeDeck)].calls;
        if (stateCalls != 1 || deckCalls != 1)
            throw std::runtime_error("contextual deck time was not attributed to V4 profiler buckets");
    } else {
        const auto state = model.prepareState(glob, 3, deck, 2, relic, 2, potion);
        const auto prefix = model.preparePolicyPrefix(state);
        const int cats[6] = {};
        const float entity[4] = {1, 0, 0, 0};
        if (!std::isfinite(model.predictPolicyLogit(state, prefix, 0, cats, -1, 1,
                entity, -1, 0)))
            throw std::runtime_error("contextual policy inference is non-finite");
    }
    std::cout << "PASS OOC_STRAT_C1 contextual artifact load and inference"
              << (profileCheck ? " with V4 profiler attribution" : "") << '\n';
    return 0;
}

int contextualRejectsTrailingBytes(const std::string &path) {
    const auto tempPath = std::filesystem::temp_directory_path()
        / ("ooc-contextual-trailing-"
           + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count())
           + ".native");
    {
        std::ifstream source(path, std::ios::binary);
        std::ofstream corrupted(tempPath, std::ios::binary | std::ios::trunc);
        if (!source || !corrupted) throw std::runtime_error("cannot create trailing-byte fixture");
        corrupted << source.rdbuf();
        corrupted.put('\0');
        if (!corrupted) throw std::runtime_error("cannot write trailing-byte fixture");
    }
    Net model;
    const bool loaded = model.load(tempPath.string(), true);
    std::filesystem::remove(tempPath);
    if (loaded) throw std::runtime_error("OOC_STRAT_C1 accepted unexpected trailing bytes");
    std::cout << "PASS OOC_STRAT_C1 rejects unexpected trailing bytes\n";
    return 0;
}

int replay(const std::string &modelPath) {
    Net model;
    if (!model.load(modelPath, true)) throw std::runtime_error("native artifact failed to load");
    verifyModelVersion(model, Net::DeckEncoderVersion::ContextualC1, "OOC_STRAT_C1");
    const auto rows = readPriors();
    for (const auto &row : rows) std::cout << outputJson(row, evaluatePrior(model, row)).dump() << '\n';
    return 0;
}

struct Samples {
    std::vector<double> seconds;
    std::map<std::string, std::vector<double>> byDeckBucket;
    std::uint64_t sourceCandidateCalls = 0;
};

std::string deckBucket(int count) {
    if (count == 0) return "0";
    if (count <= 8) return "1-8";
    if (count <= 16) return "9-16";
    if (count <= 32) return "17-32";
    if (count <= 64) return "33-64";
    return "65-96";
}

void runTimedPass(const Net &model, const std::vector<PriorInput> &rows,
                  const std::string &kind, Samples &samples) {
    for (const auto &row : rows) {
        const double start = threadCpuSeconds();
        double checksum = 0;
        if (kind == "deck") {
            float output[Net::DECKDIM];
            model.encodeDeck(row.state.nDk, row.state.dk, output);
            for (float value : output) checksum += value;
        } else if (kind == "prepare") {
            const auto output = model.prepareState(row.state.glob, row.state.nDk, row.state.dk,
                row.state.nRl, row.state.rl, row.state.nPt, row.state.pt);
            for (float value : output.values) checksum += value;
        } else {
            const auto output = evaluatePrior(model, row, false);
            for (const double value : output.normalizedPrior) checksum += value;
            samples.sourceCandidateCalls += row.sources.size();
        }
        benchmarkSink += checksum;
        const double elapsed = threadCpuSeconds() - start;
        samples.seconds.push_back(elapsed);
        samples.byDeckBucket[deckBucket(row.state.nDk)].push_back(elapsed);
    }
}

Json sampleStats(const std::vector<double> &input) {
    if (input.empty()) return Json{{"calls", 0}};
    std::vector<double> sorted = input;
    std::sort(sorted.begin(), sorted.end());
    const auto quantile = [&](double q) {
        const auto index = static_cast<std::size_t>(std::ceil(q * sorted.size())) - 1;
        return sorted[std::min(index, sorted.size() - 1)];
    };
    double total = 0;
    for (const auto value : input) total += value;
    return Json{{"calls", input.size()}, {"total_cpu_seconds", total},
        {"mean_seconds_per_call", total / input.size()}, {"median_seconds_per_call", quantile(.50)},
        {"p90_seconds_per_call", quantile(.90)}, {"p99_seconds_per_call", quantile(.99)}};
}

Json samplesJson(const Samples &samples) {
    Json byBucket = Json::object();
    for (const auto &[bucket, values] : samples.byDeckBucket)
        byBucket[bucket] = sampleStats(values);
    return Json{{"all", sampleStats(samples.seconds)}, {"by_deck_token_count", byBucket},
                {"source_candidate_calls", samples.sourceCandidateCalls}};
}

int benchmark(const std::string &attentionPath, const std::string &contextualPath, int passes) {
    if (passes < 2 || passes > 20) throw std::runtime_error("benchmark passes must be in 2..20");
    Net attention, contextual;
    if (!attention.load(attentionPath, true) || !contextual.load(contextualPath, true))
        throw std::runtime_error("benchmark model loading failed");
    verifyModelVersion(attention, Net::DeckEncoderVersion::AttentionV4, "attention");
    verifyModelVersion(contextual, Net::DeckEncoderVersion::ContextualC1, "contextual");
    const auto rows = readPriors(); // Input parsing/decompression is outside every timed region.

    // Warm both model arms once over the complete fixed population.
    for (const auto &row : rows) {
        (void)evaluatePrior(attention, row, false);
        (void)evaluatePrior(contextual, row, false);
    }

    Json metrics = Json::object();
    for (const std::string kind : {"deck", "prepare", "prior"}) {
        Samples a, b;
        for (int pass = 0; pass < passes; ++pass) {
            if (pass % 2 == 0) {
                runTimedPass(attention, rows, kind, a);
                runTimedPass(contextual, rows, kind, b);
            } else {
                runTimedPass(contextual, rows, kind, b);
                runTimedPass(attention, rows, kind, a);
            }
        }
        const Json aJson = samplesJson(a);
        const Json bJson = samplesJson(b);
        const double ratio = bJson.at("all").at("total_cpu_seconds").get<double>()
            / aJson.at("all").at("total_cpu_seconds").get<double>();
        metrics[kind] = {{"attention", aJson}, {"contextual", bJson},
                         {"b_over_a_ratio", ratio}, {"reduction_percent", (1.0 - ratio) * 100.0}};
    }
    std::cout << Json{{"format", "ooc-contextual-native-performance-v1"},
        {"prior_count", rows.size()}, {"measured_passes_per_arm", passes},
        {"warmup_passes_per_arm", 1}, {"thread_cpu_clock", "CLOCK_THREAD_CPUTIME_ID"},
        {"order", "alternating A/B and B/A by measured pass; A=attention, B=contextual"},
        {"metrics", metrics}, {"benchmark_sink", static_cast<double>(benchmarkSink)}}.dump(2) << '\n';
    return 0;
}
} // namespace

int main(int argc, char **argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "--compat") return compatibility(argv[2]);
        if (argc == 3 && std::string(argv[1]) == "--context-load")
            return contextualLoad(argv[2], false);
        if (argc == 3 && std::string(argv[1]) == "--profile-check")
            return contextualLoad(argv[2], true);
        if (argc == 3 && std::string(argv[1]) == "--reject-trailing-context")
            return contextualRejectsTrailingBytes(argv[2]);
        if (argc == 3 && std::string(argv[1]) == "--replay") return replay(argv[2]);
        if (argc == 5 && std::string(argv[1]) == "--benchmark")
            return benchmark(argv[2], argv[3], std::stoi(argv[4]));
        std::cerr << "usage: " << argv[0]
                  << " --compat ATTENTION.native | --context-load CONTEXT.native"
                     " | --profile-check CONTEXT.native | --reject-trailing-context CONTEXT.native"
                     " | --replay CONTEXT.native"
                     " | --benchmark ATTENTION.native CONTEXT.native PASSES < trace.jsonl\n";
        return 2;
    } catch (const std::exception &error) {
        std::cerr << "ooc_contextual_native_probe: " << error.what() << '\n';
        return 1;
    }
}
