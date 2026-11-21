// Python bridge of the stage 0 end-to-end producer (az_driver.h): tools/az_bench/e2e_bench.py drives the worker
// threads from Python and evaluates each packed batch with a PyTorch net on the GPU. The GIL is released while
// C++ waits for or packs a batch and while it posts results; batch arrays are handed to numpy without a copy.
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>

#include <cstdio>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstring>

#include <nlohmann/json.hpp>

#include "az_driver.h"
#include "az_run_driver.h"
#include "az_token_store.h"
#include "constants/Cards.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

namespace py = pybind11;
using namespace sts;

namespace {

    const char *kTypes[] = {"run", "player", "status", "monster", "card", "relic", "potion", "option", "map"};

    std::vector<azbench::Root> loadRoots(const std::string &path) {
        std::vector<azbench::Root> roots;
        std::ifstream f(path);
        if (!f) throw std::runtime_error("cannot open " + path);
        std::string line;
        while (std::getline(f, line)) {
            if (line.empty()) continue;
            const auto wire = nlohmann::json::parse(line).at("wire").get<silver_bridge::BattleStateWire>();
            azbench::Root r{search::battleContextFromWire(wire), search::searchContextFromWire(wire)};
            if (r.state.outcome == Outcome::UNDECIDED) roots.push_back(std::move(r));
        }
        if (roots.empty()) throw std::runtime_error("no undecided wire rows in " + path);
        return roots;
    }

    // numpy view of a vector owned by a shared PackedBatch (kept alive by the capsule).
    template <class T>
    py::array view(const std::shared_ptr<azbench::PackedBatch> &owner, std::vector<T> &v,
                   std::vector<py::ssize_t> shape, py::dtype dt = py::dtype::of<T>()) {
        auto *keep = new std::shared_ptr<azbench::PackedBatch>(owner);
        py::capsule cap(keep, [](void *p) { delete static_cast<std::shared_ptr<azbench::PackedBatch> *>(p); });
        std::vector<py::ssize_t> strides(shape.size());
        py::ssize_t s = static_cast<py::ssize_t>(sizeof(T));
        for (int i = static_cast<int>(shape.size()) - 1; i >= 0; --i) { strides[i] = s; s *= shape[i]; }
        return py::array(dt, shape, strides, v.data(), cap);
    }


    // Caller buffers for next_flat: writeable C-contiguous arrays sized for the largest buckets (e.g. numpy views of
    // pinned torch tensors): tok_type int8, ids int16, f float16, mask bool/uint8, a_type / a_src / a_tgt int16,
    // a_f float16, a_mask bool/uint8.
    azbench::FlatBuffers flatBuffersFrom(py::dict bufs, int R, int T, int A, bool packedTokens = false) {
        auto ptr = [&](const char *k, std::size_t bytes) -> void * {
            py::array a = bufs[k].cast<py::array>();
            if (!(a.flags() & py::array::c_style) || !a.writeable())
                throw std::invalid_argument(std::string("next_flat: buffer ") + k + " not writeable C order");
            if (static_cast<std::size_t>(a.nbytes()) < bytes)
                throw std::invalid_argument(std::string("next_flat: buffer ") + k + " too small");
            return a.mutable_data();
        };
        const std::size_t rt = static_cast<std::size_t>(R) * T, ra = static_cast<std::size_t>(R) * A;
        azbench::FlatBuffers fb{
            static_cast<std::int8_t *>(ptr("tok_type", rt)),
            static_cast<std::int16_t *>(ptr("ids", rt * search::kAmberCat * 2)),
            static_cast<std::uint16_t *>(ptr("f", rt * search::kAmberFloat * 2)),
            static_cast<std::uint8_t *>(ptr("mask", rt)),
            static_cast<std::int16_t *>(ptr("a_type", ra * 2)),
            static_cast<std::int16_t *>(ptr("a_src", ra * 2)),
            static_cast<std::int16_t *>(ptr("a_tgt", ra * 2)),
            static_cast<std::uint16_t *>(ptr("a_f", ra * search::kAmberActFeat * 2)),
            static_cast<std::uint8_t *>(ptr("a_mask", ra))};
        if (packedTokens) {   // also int32 pack_idx [R * T] and seq_off [R + 1]
            fb.packIdx = static_cast<std::int32_t *>(ptr("pack_idx", rt * 4));
            fb.seqOff = static_cast<std::int32_t *>(ptr("seq_off", (static_cast<std::size_t>(R) + 1) * 4));
            for (const char *k : {"pack_idx", "seq_off"})
                if (bufs[k].cast<py::array>().itemsize() != 4) throw std::invalid_argument(std::string("next_flat: buffer ") + k + " must be int32");
        }
        return fb;
    }

    template <class T>
    py::array_t<T> toArray(const std::vector<T> &v) {
        py::array_t<T> a(static_cast<py::ssize_t>(v.size()));
        if (!v.empty()) std::memcpy(a.mutable_data(), v.data(), v.size() * sizeof(T));
        return a;
    }

}

PYBIND11_MODULE(az_bench_native, m) {
    m.doc() = "Stage 0 end-to-end producer: worker threads with Gumbel searches whose leaves are batched for a net";

    py::class_<azbench::Driver>(m, "Driver")
        .def(py::init([](const std::string &wires, int workers, int games, int fullSims, int fastSims,
                         double fullProb, int fullCandidates, int fastCandidates, std::uint64_t seed,
                         const std::string &encoder) {
                 azbench::DriverConfig c;
                 c.workers = workers;
                 c.gamesPerWorker = games;
                 c.fullSims = fullSims;
                 c.fastSims = fastSims;
                 c.fullProb = fullProb;
                 c.fullCandidates = fullCandidates;
                 c.fastCandidates = fastCandidates;
                 c.seed = seed;
                 if (encoder == "stub") c.encode = azbench::stubEncode;
                 else if (encoder != "amber") throw std::invalid_argument("encoder: amber or stub");
                 return std::make_unique<azbench::Driver>(loadRoots(wires), c);
             }),
             py::arg("wires"), py::arg("workers") = 10, py::arg("games") = 256, py::arg("full_sims") = 64,
             py::arg("fast_sims") = 16, py::arg("full_prob") = 0.25, py::arg("full_candidates") = 16,
             py::arg("fast_candidates") = 4, py::arg("seed") = 0, py::arg("encoder") = "amber")
        .def("start", &azbench::Driver::start, py::call_guard<py::gil_scoped_release>())
        .def("stop", &azbench::Driver::stop, py::call_guard<py::gil_scoped_release>())
        .def("next_batch",
             [](azbench::Driver &d, int maxRows, int minRows, int timeoutMs) -> py::object {
                 auto b = std::make_shared<azbench::PackedBatch>();
                 bool ok;
                 {
                     py::gil_scoped_release r;
                     ok = d.nextBatch(maxRows, minRows, timeoutMs, *b);
                 }
                 if (!ok) return py::none();
                 py::dict out;
                 const py::ssize_t B = b->rows, A = b->actions;
                 for (int s = 0; s < search::kAmberTokenTypes; ++s) {
                     const py::ssize_t S = b->slots[s];
                     const std::string t = kTypes[s];
                     out[(t + "_ids").c_str()] = view(b, b->ids[s], {B, S, search::kAmberCat});
                     out[(t + "_f").c_str()] = view(b, b->f[s], {B, S, search::kAmberFloat}, py::dtype("float16"));
                     out[(t + "_mask").c_str()] = view(b, b->mask[s], {B, S}, py::dtype("bool"));
                 }
                 out["a_type"] = view(b, b->aType, {B, A});
                 out["a_src"] = view(b, b->aSrc, {B, A});
                 out["a_tgt"] = view(b, b->aTgt, {B, A});
                 out["a_f"] = view(b, b->aF, {B, A, search::kAmberActFeat}, py::dtype("float16"));
                 out["a_mask"] = view(b, b->aMask, {B, A}, py::dtype("bool"));
                 out["ticket"] = view(b, b->ticket, {B});
                 return out;
             },
             py::arg("max_rows"), py::arg("min_rows"), py::arg("timeout_ms") = 5)
        .def("next_flat",
             [](azbench::Driver &d, int maxRows, int minRows, int timeoutMs, std::vector<int> rowBuckets,
                std::vector<int> tokBuckets, std::vector<int> actBuckets, py::dict bufs,
                int sortWindow, int packThreads) -> py::object {
                 const int R = std::max(maxRows, rowBuckets.empty() ? 0 : rowBuckets.back());
                 const int T = tokBuckets.empty() ? search::kAmberMaxTokens : tokBuckets.back();
                 const int A = actBuckets.empty() ? search::kAmberMaxActions : actBuckets.back();
                 const azbench::FlatBuffers fb = flatBuffersFrom(bufs, R, T, A);
                 azbench::Driver::FlatShape shape;
                 std::vector<std::uint32_t> tickets;
                 {
                     py::gil_scoped_release r;
                     tickets = d.nextBatchFlat(maxRows, minRows, timeoutMs, rowBuckets, tokBuckets, actBuckets, fb,
                                               shape, sortWindow, packThreads);
                 }
                 if (tickets.empty()) return py::none();
                 py::array_t<std::uint32_t> t(static_cast<py::ssize_t>(tickets.size()));
                 std::memcpy(t.mutable_data(), tickets.data(), tickets.size() * sizeof(std::uint32_t));
                 return py::make_tuple(t, shape.rows, shape.rowsPadded, shape.tokens, shape.actions);
             },
             py::arg("max_rows"), py::arg("min_rows"), py::arg("timeout_ms"), py::arg("row_buckets"),
             py::arg("tok_buckets"), py::arg("act_buckets"), py::arg("bufs"), py::arg("sort_window") = 1, py::arg("pack_threads") = 1)
        .def("submit",
             [](azbench::Driver &d, py::array_t<std::uint32_t, py::array::c_style | py::array::forcecast> ticket,
                py::array_t<float, py::array::c_style | py::array::forcecast> logits,
                py::array_t<float, py::array::c_style | py::array::forcecast> value) {
                 if (logits.ndim() != 2 || value.ndim() != 1 || ticket.ndim() != 1 ||
                     logits.shape(0) != ticket.shape(0) || value.shape(0) != ticket.shape(0))
                     throw std::invalid_argument("submit: want ticket [B], logits [B, A], value [B]");
                 const int rows = static_cast<int>(ticket.shape(0)), actions = static_cast<int>(logits.shape(1));
                 const auto *t = ticket.data();
                 const auto *l = logits.data();
                 const auto *v = value.data();
                 py::gil_scoped_release r;
                 d.submit(t, rows, actions, l, v);
             },
             py::arg("ticket"), py::arg("logits"), py::arg("value"))
        .def("stats", [](const azbench::Driver &d) {
            const auto s = d.stats();
            py::dict o;
            o["evals"] = s.evals; o["moves"] = s.moves; o["fights"] = s.fights; o["wins"] = s.wins;
            o["terminal_leaves"] = s.terminalLeaves; o["encode_cut"] = s.encodeCut;
            o["batches"] = s.batches; o["batch_rows"] = s.batchRows;
            o["step_cpu"] = s.stepCpu; o["encode_cpu"] = s.encodeCpu; o["search_cpu"] = s.searchCpu;
            o["pack_s"] = s.packSeconds;
            return o;
        });

    // Global token dictionary of the replay window (selfplay.py --compact-samples, az_token_store.h). Rows are
    // tok_type [n] int8, ids [n, 4] int16, f [n, 64] float16, counts [n] int64 (references to add).
    py::class_<azbench::TokenStore>(m, "TokenStore")
        .def(py::init<std::int64_t>(), py::arg("capacity"))
        .def_property_readonly("capacity", &azbench::TokenStore::capacity)
        .def_property_readonly("free", &azbench::TokenStore::freeSlots)
        .def_property_readonly("used", &azbench::TokenStore::used)
        .def_property_readonly("nbytes", &azbench::TokenStore::bytes)
        .def("count_new",
             [](const azbench::TokenStore &st, py::array_t<std::int8_t, py::array::c_style | py::array::forcecast> t,
                py::array_t<std::int16_t, py::array::c_style | py::array::forcecast> ids,
                py::array_t<std::uint16_t, py::array::c_style> f,
                py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> counts) {
                 const auto n = static_cast<std::size_t>(t.shape(0));
                 if (ids.size() != static_cast<py::ssize_t>(n * 4) || f.size() != static_cast<py::ssize_t>(n * 64) ||
                     counts.size() != static_cast<py::ssize_t>(n))
                     throw std::invalid_argument("TokenStore.count_new: shapes");
                 py::gil_scoped_release r;
                 return st.countNew(n, t.data(), ids.data(), f.data(), counts.data());
             })
        .def("intern",
             [](azbench::TokenStore &st, py::array_t<std::int8_t, py::array::c_style | py::array::forcecast> t,
                py::array_t<std::int16_t, py::array::c_style | py::array::forcecast> ids,
                py::array_t<std::uint16_t, py::array::c_style> f,
                py::array_t<std::int64_t, py::array::c_style | py::array::forcecast> counts) {
                 const auto n = static_cast<std::size_t>(t.shape(0));
                 if (ids.size() != static_cast<py::ssize_t>(n * 4) || f.size() != static_cast<py::ssize_t>(n * 64) ||
                     counts.size() != static_cast<py::ssize_t>(n))
                     throw std::invalid_argument("TokenStore.intern: shapes");
                 py::array_t<std::int32_t> slots(static_cast<py::ssize_t>(n));
                 {
                     py::gil_scoped_release r;
                     st.intern(n, t.data(), ids.data(), f.data(), counts.data(), slots.mutable_data());
                 }
                 return slots;
             })
        .def("release",
             [](azbench::TokenStore &st, py::array_t<std::int32_t, py::array::c_style | py::array::forcecast> slots) {
                 py::gil_scoped_release r;
                 st.release(static_cast<std::size_t>(slots.size()), slots.data());
             })
        .def("restore",
             [](azbench::TokenStore &st, py::array_t<std::int8_t, py::array::c_style> t,
                py::array_t<std::int16_t, py::array::c_style> ids, py::array_t<std::uint16_t, py::array::c_style> f,
                py::array_t<std::int32_t, py::array::c_style> refs) {
                 const auto n = static_cast<py::ssize_t>(st.capacity());
                 if (t.size() != n || ids.size() != n * 4 || f.size() != n * 64 || refs.size() != n)
                     throw std::invalid_argument("TokenStore.restore: shapes (capacity differs?)");
                 py::gil_scoped_release r;
                 st.restore(t.data(), ids.data(), f.data(), refs.data());
             })
        .def("refs",
             [](py::object self) {
                 auto &st = self.cast<azbench::TokenStore &>();
                 return py::array_t<std::int32_t>({static_cast<py::ssize_t>(st.capacity())}, {sizeof(std::int32_t)},
                                                  st.refs(), self);
             })
        .def("views",
             [](py::object self) {
                 // tok_type [cap], ids [cap, 4], f [cap, 64] float16: views into the store (valid while it lives).
                 auto &st = self.cast<azbench::TokenStore &>();
                 const auto cap = static_cast<py::ssize_t>(st.capacity());
                 py::array_t<std::int8_t> t({cap}, {static_cast<py::ssize_t>(1)}, st.tokType(), self);
                 py::array_t<std::int16_t> ids({cap, static_cast<py::ssize_t>(4)},
                                               {static_cast<py::ssize_t>(8), static_cast<py::ssize_t>(2)}, st.ids(), self);
                 py::array_t<std::uint16_t> f({cap, static_cast<py::ssize_t>(64)},
                                              {static_cast<py::ssize_t>(128), static_cast<py::ssize_t>(2)}, st.f(), self);
                 return py::make_tuple(t, ids, f.attr("view")("float16"));
             });

    py::class_<azbench::RunDriver>(m, "RunDriver")
        .def(py::init([](int workers, int games, std::uint64_t seedBase, std::int64_t maxRuns, int ascension,
                         int fullSims, int fastSims, double fullProb, int fullCandidates, int fastCandidates,
                         double hpWeightCombat, double hpWeightOoc, double keepFull, double keepFast,
                         std::uint64_t searchSeed, int maxFightMoves, int testMaxHp, std::int64_t maxPending,
                         double exploreC, double pickTarget, double cVisit, double cScale, bool fastNoise,
                         bool qRescale, int utility, bool keylessHp, bool evalCache, int evalCacheCap, bool mergeCards,
                         bool chanceOnReveal, bool crossCombat, bool simHelp,
                         bool exploreAmber, double exploreT, double searchEmaLambda, bool searchEmaFullOnly,
                         bool forceKeys, std::vector<std::vector<double>> heartArms, int heartReps,
                         bool savescum, bool compactSamples, double heartLogRate, bool forceRewards, bool explorePerOffer,
                         bool exploreGapSearch, bool exploreDeckOnly, bool forcePotions, bool oocCanon,
                         bool exploreCleanKeys) {
                 azbench::RunConfig c;
                 if (!(heartLogRate >= 0 && heartLogRate <= 1)) throw std::invalid_argument("heart_log_rate: want 0..1");
                 c.heartLogRate = heartLogRate;
                 for (const auto &v : heartArms) {   // [full_sims, fast_sims, full_prob, full_candidates, fast_candidates]
                     if (v.size() != 5) throw std::invalid_argument("heart_arms: want 5 numbers per arm");
                     azbench::HeartArm a;
                     a.fullSims = static_cast<int>(v[0]); a.fastSims = static_cast<int>(v[1]); a.fullProb = v[2];
                     a.fullCandidates = static_cast<int>(v[3]); a.fastCandidates = static_cast<int>(v[4]);
                     c.heartArms.push_back(a);
                 }
                 c.heartReps = heartReps;
                 c.utility = static_cast<azbench::Utility>(utility);
                 c.keylessHp = keylessHp;
                 c.workers = workers;
                 c.gamesPerWorker = games;
                 c.seedBase = seedBase;
                 c.maxRuns = maxRuns;
                 c.ascension = ascension;
                 c.fullSims = fullSims;
                 c.fastSims = fastSims;
                 c.fullProb = fullProb;
                 c.fullCandidates = fullCandidates;
                 c.fastCandidates = fastCandidates;
                 c.hpWeightCombat = hpWeightCombat;
                 c.hpWeightOoc = hpWeightOoc;
                 c.keepFull = keepFull;
                 c.keepFast = keepFast;
                 c.searchSeed = searchSeed;
                 c.maxMovesPerFight = maxFightMoves;
                 c.testMaxHp = testMaxHp;
                 c.maxPendingSamples = maxPending;
                 c.exploreC = exploreC;
                 c.pickTarget = pickTarget;
                 c.evalCache = evalCache;
                 c.evalCacheCap = evalCacheCap;
                 c.cVisit = cVisit;
                 c.cScale = cScale;
                 c.fastNoise = fastNoise;
                 c.qRescale = qRescale;
                 c.mergeCards = mergeCards;
                 c.chanceOnReveal = chanceOnReveal;
                 c.crossCombat = crossCombat;
                 c.simHelp = simHelp;
                 c.exploreAmber = exploreAmber;
                 c.exploreT = exploreT;
                 c.searchEmaLambda = searchEmaLambda;
                 c.searchEmaFullOnly = searchEmaFullOnly;
                 c.forceKeys = forceKeys;
                 c.forceRewards = forceRewards;
                 c.forcePotions = forcePotions;
                 c.oocCanon = oocCanon;
                 c.explorePerOffer = explorePerOffer;
                 c.exploreGapSearch = exploreGapSearch;
                 c.exploreDeckOnly = exploreDeckOnly;
                 c.exploreCleanKeys = exploreCleanKeys;
                 c.savescum = savescum;
                 c.compactSamples = compactSamples;
                 return std::make_unique<azbench::RunDriver>(c);
             }),
             py::arg("workers") = 11, py::arg("games") = 700, py::arg("seed_base") = 0, py::arg("max_runs") = -1,
             py::arg("ascension") = 20, py::arg("full_sims") = 64, py::arg("fast_sims") = 16,
             py::arg("full_prob") = 0.25, py::arg("full_candidates") = 16, py::arg("fast_candidates") = 4,
             py::arg("hp_weight_combat") = 1.0, py::arg("hp_weight_ooc") = 1.0, py::arg("keep_full") = 1.0,
             py::arg("keep_fast") = 0.0, py::arg("search_seed") = 0, py::arg("max_fight_moves") = 400,
             py::arg("test_max_hp") = 0, py::arg("max_pending") = 300000,
             py::arg("explore_c") = 0.0, py::arg("pick_target") = 0.01, py::arg("c_visit") = 50.0,
             py::arg("c_scale") = 1.0, py::arg("fast_noise") = true, py::arg("q_rescale") = false,
             py::arg("utility") = 0, py::arg("keyless_hp") = false,
             py::arg("eval_cache") = false, py::arg("eval_cache_cap") = 1024, py::arg("merge_cards") = false,
             py::arg("chance_on_reveal") = false, py::arg("cross_combat") = false, py::arg("sim_help") = false,
             py::arg("explore_amber") = false, py::arg("explore_temp") = 4.0,
             py::arg("search_ema_lambda") = 0.0, py::arg("search_ema_full_only") = true,
             py::arg("force_keys") = false, py::arg("heart_arms") = std::vector<std::vector<double>>{},
             py::arg("heart_reps") = 1, py::arg("savescum") = false,
             py::arg("compact_samples") = false, py::arg("heart_log_rate") = 0.0,
             py::arg("force_rewards") = false, py::arg("explore_per_offer") = false,
             py::arg("explore_gap_search") = false, py::arg("explore_deck_only") = false,
             py::arg("force_potions") = false, py::arg("ooc_canon") = false,
             py::arg("explore_clean_keys") = false)
        .def("heart_results",
             [](const azbench::RunDriver &d) {
                 py::list out;
                 for (const auto &r : d.heartResults()) {
                     py::dict o;
                     o["seed"] = r.seed; o["arm"] = r.arm; o["rep"] = r.rep; o["win"] = r.win;
                     o["heart_hp"] = r.heartHp; o["heart_max_hp"] = r.heartMaxHp;
                     o["player_hp_start"] = r.playerHpStart; o["player_max_hp"] = r.playerMaxHp;
                     o["player_hp_end"] = r.playerHpEnd; o["turns"] = r.turns; o["moves"] = r.moves;
                     o["searched"] = r.searched; o["stall"] = r.stall; o["deck_size"] = r.deckSize;
                     o["relics"] = r.relics; o["asc"] = r.asc;
                     out.append(o);
                 }
                 return out;
             })
        .def("take_heart_run_logs",   // RunConfig::heartLogRate: the records since the last call, as dicts
             [](azbench::RunDriver &d) {
                 py::list out;
                 for (const auto &r : d.takeHeartRunLogs()) {
                     py::dict o;
                     o["seed"] = r.seed; o["asc"] = r.asc; o["win"] = r.win; o["floor"] = r.floor;
                     o["heart_hp"] = r.heartHp; o["heart_max_hp"] = r.heartMaxHp;
                     o["entry_hp"] = r.entryHp; o["entry_max_hp"] = r.entryMaxHp; o["end_hp"] = r.endHp;
                     o["turns"] = r.turns; o["gold"] = r.gold;
                     o["elites"] = r.elites; o["rest"] = r.rest; o["smith"] = r.smith;
                     auto arr = [](const auto &a) { py::list l; for (auto x : a) l.append(x); return l; };
                     // index 0..3 = first searched move of act 1..4, 4 = first searched move of the Heart fight
                     o["root_floor"] = arr(r.floorAt);
                     o["net_p_win"] = arr(r.netPWin); o["net_p_heart_death"] = arr(r.netPHeartDeath);
                     o["net_e_floor"] = arr(r.netEFloor); o["net_value"] = arr(r.netValue);
                     o["search_p_win"] = arr(r.searchPWin); o["search_value"] = arr(r.searchValue);
                     py::list fh;   // HP at the end of floor 1..56 (-1 = not reached / not recorded)
                     for (int f = 1; f < static_cast<int>(r.floorHp.size()); ++f) fh.append(r.floorHp[f]);
                     o["floor_hp"] = fh;
                     py::list deck;
                     for (const auto &[id, up] : r.deck)
                         deck.append(std::string(getCardEnumName(static_cast<CardId>(id))) + (up ? "+" : ""));
                     o["deck"] = deck;
                     py::list rel;
                     for (int id : r.relics) rel.append(getRelicName(static_cast<RelicId>(id)));
                     o["relics"] = rel;
                     py::list pot;
                     for (int id : r.potions) pot.append(getPotionName(static_cast<Potion>(id)));
                     o["potions"] = pot;
                     out.append(o);
                 }
                 return out;
             })
        .def("set_weights_version", &azbench::RunDriver::setWeightsVersion)
        .def("set_ascension", &azbench::RunDriver::setAscension)
        .def("ascension", &azbench::RunDriver::ascension)
        .def("set_force_keys", &azbench::RunDriver::setForceKeys)
        .def("force_keys", &azbench::RunDriver::forceKeys)
        .def("set_savescum", &azbench::RunDriver::setSavescum)
        .def("savescum", &azbench::RunDriver::savescum)
        .def("start", &azbench::RunDriver::start, py::call_guard<py::gil_scoped_release>())
        .def("stop", &azbench::RunDriver::stop, py::call_guard<py::gil_scoped_release>())
        .def("next_flat",
             [](azbench::RunDriver &d, int maxRows, int minRows, int timeoutMs, std::vector<int> rowBuckets,
                std::vector<int> tokBuckets, std::vector<int> actBuckets, py::dict bufs, int packThreads,
                bool packedTokens) -> py::object {
                 const int R = std::max(maxRows, rowBuckets.empty() ? 0 : rowBuckets.back());
                 const int T = tokBuckets.empty() ? search::kAmberMaxTokens : tokBuckets.back();
                 const int A = actBuckets.empty() ? search::kAmberMaxActions : actBuckets.back();
                 const azbench::FlatBuffers fb = flatBuffersFrom(bufs, R, T, A, packedTokens);
                 azbench::FlatShape shape;
                 std::vector<std::uint32_t> tickets;
                 {
                     py::gil_scoped_release r;
                     tickets = d.nextBatchFlat(maxRows, minRows, timeoutMs, rowBuckets, tokBuckets, actBuckets, fb,
                                               shape, packThreads);
                 }
                 if (tickets.empty()) return py::none();
                 if (packedTokens)   // + N: packed tokens (tok_type / ids / f / pack_idx [N], seq_off [rows_padded + 1])
                     return py::make_tuple(toArray(tickets), shape.rows, shape.rowsPadded, shape.tokens,
                                           shape.actions, shape.packed);
                 return py::make_tuple(toArray(tickets), shape.rows, shape.rowsPadded, shape.tokens, shape.actions);
             },
             py::arg("max_rows"), py::arg("min_rows"), py::arg("timeout_ms"), py::arg("row_buckets"),
             py::arg("tok_buckets"), py::arg("act_buckets"), py::arg("bufs"), py::arg("pack_threads") = 1,
             py::arg("packed_tokens") = false)
        .def("wait_requests", &azbench::RunDriver::waitRequests, py::call_guard<py::gil_scoped_release>(),
             py::arg("min_rows"), py::arg("timeout_us"),
             "Waits up to timeout_us for min_rows queued requests without taking any; True when they are there.")
        .def("submit",
             [](azbench::RunDriver &d, py::array_t<std::uint32_t, py::array::c_style | py::array::forcecast> ticket,
                py::array_t<float, py::array::c_style | py::array::forcecast> logits,
                py::array_t<float, py::array::c_style | py::array::forcecast> F,
                py::array_t<float, py::array::c_style | py::array::forcecast> ehp, py::object hpfObj,
                std::uint32_t version, py::object distObj) {
                 if (logits.ndim() != 2 || F.ndim() != 1 || ehp.ndim() != 1 || ticket.ndim() != 1 ||
                     logits.shape(0) != ticket.shape(0) || F.shape(0) != ticket.shape(0) ||
                     ehp.shape(0) != ticket.shape(0))
                     throw std::invalid_argument("submit: want ticket [B], logits [B, A], F [B], ehp [B]");
                 py::array_t<float, py::array::c_style | py::array::forcecast> hpf;
                 const float *hp = nullptr;
                 if (!hpfObj.is_none()) {
                     hpf = py::array_t<float, py::array::c_style | py::array::forcecast>::ensure(hpfObj);
                     if (!hpf || hpf.ndim() != 2 || hpf.shape(0) != ticket.shape(0) || hpf.shape(1) != azbench::kFloors)
                         throw std::invalid_argument("submit: want hpf [B, 56] (E[HP_f] / 255)");
                     hp = hpf.data();
                 }
                 py::array_t<float, py::array::c_style | py::array::forcecast> dist;
                 const float *dp = nullptr;
                 if (!distObj.is_none()) {
                     dist = py::array_t<float, py::array::c_style | py::array::forcecast>::ensure(distObj);
                     if (!dist || dist.ndim() != 2 || dist.shape(0) != ticket.shape(0) ||
                         dist.shape(1) != azbench::kOutcomeClasses)
                         throw std::invalid_argument("submit: want dist [B, 57] (outcome softmax)");
                     dp = dist.data();
                 }
                 const int rows = static_cast<int>(ticket.shape(0)), actions = static_cast<int>(logits.shape(1));
                 const auto *t = ticket.data();
                 const auto *l = logits.data();
                 const auto *f = F.data();
                 const auto *h = ehp.data();
                 py::gil_scoped_release r;
                 d.submit(t, rows, actions, l, f, h, hp, version, dp);
             },
             py::arg("ticket"), py::arg("logits"), py::arg("F"), py::arg("ehp"), py::arg("hpf") = py::none(),
             py::arg("version") = 0, py::arg("dist") = py::none())
        .def("take_samples",
             [](azbench::RunDriver &d, int maxSamples) -> py::object {
                 // Ragged arrays: sample i owns tokens tok_off[i] .. tok_off[i + 1] and actions act_off[i] ..
                 // act_off[i + 1]; a_src / a_tgt index the sample's own tokens (-1 = none); policy is NaN-free and
                 // all zero for samples without one (has_policy = 0).
                 // Compact samples (RunConfig::compactSamples; "tok_idx" present): tok_type / ids / f hold the chunk's
                 // token dictionaries (each distinct run dictionary once, back to back) and sample i's tokens are
                 // tok_base[i] + tok_idx[tok_off[i] .. tok_off[i + 1]] in them.
                 std::vector<azbench::Sample> v;
                 {
                     py::gil_scoped_release r;
                     d.takeSamples(maxSamples, v);
                 }
                 if (v.empty()) return py::none();
                 const std::size_t S = v.size();
                 const bool compact = static_cast<bool>(v[0].dict);
                 std::size_t nt = 0, na = 0;
                 for (const auto &x : v) {
                     if (static_cast<bool>(x.dict) != compact) throw std::runtime_error("take_samples: mixed compact samples");
                     nt += x.numTokens(); na += x.aType.size();
                 }
                 std::vector<std::uint16_t> tokIdx;
                 std::vector<std::int64_t> tokBase;
                 std::unordered_map<const azbench::TokenDict *, std::int64_t> dictAt;   // dictionary -> its first token
                 if (compact) {
                     tokIdx.reserve(nt);
                     tokBase.resize(S);
                     nt = 0;
                     for (const auto &x : v)
                         if (dictAt.emplace(x.dict.get(), static_cast<std::int64_t>(nt)).second) nt += x.dict->size();
                 }
                 std::vector<std::int64_t> tokOff(S + 1, 0), actOff(S + 1, 0);
                 std::vector<std::int8_t> tokType; tokType.reserve(nt);
                 std::vector<std::int16_t> ids; ids.reserve(nt * search::kAmberCat);
                 std::vector<std::uint16_t> f; f.reserve(nt * search::kAmberFloat);
                 std::vector<std::int16_t> aType, aSrc, aTgt; aType.reserve(na); aSrc.reserve(na); aTgt.reserve(na);
                 std::vector<std::uint16_t> aF; aF.reserve(na * search::kAmberActFeat);
                 std::vector<float> policy; policy.reserve(na);
                 std::vector<float> searchValue(S);
                 std::vector<std::int16_t> outcome(S), hpEnd(S), maxHp(S), floor(S);
                 std::vector<std::uint8_t> combat(S), hasPolicy(S);
                 std::vector<std::uint64_t> run(S);
                 const bool perFloor = !v[0].hpFloor.empty();   // utility AMBER: every sample has [56] labels
                 std::vector<std::int16_t> hpFloor(perFloor ? S * azbench::kFloors : 0);
                 const bool ema = !v[0].outcomeTarget.empty();   // searchEmaLambda > 0: every sample has its targets
                 const std::size_t C = azbench::kOutcomeClasses;
                 std::vector<float> searchDist(ema ? S * C : 0), outcomeTarget(ema ? S * C : 0), emaRealW(ema ? S : 0);
                 for (std::size_t i = 0; i < S; ++i) {
                     const auto &x = v[i];
                     if (compact) {
                         const std::int64_t at = dictAt.at(x.dict.get());
                         if (at == static_cast<std::int64_t>(tokType.size())) {   // the dictionary's first sample here
                             tokType.insert(tokType.end(), x.dict->tokType.begin(), x.dict->tokType.end());
                             ids.insert(ids.end(), x.dict->ids.begin(), x.dict->ids.end());
                             f.insert(f.end(), x.dict->f.begin(), x.dict->f.end());
                         }
                         tokBase[i] = at;
                         tokIdx.insert(tokIdx.end(), x.tokIdx.begin(), x.tokIdx.end());
                     } else {
                         tokType.insert(tokType.end(), x.tokType.begin(), x.tokType.end());
                         ids.insert(ids.end(), x.ids.begin(), x.ids.end());
                         f.insert(f.end(), x.f.begin(), x.f.end());
                     }
                     aType.insert(aType.end(), x.aType.begin(), x.aType.end());
                     aSrc.insert(aSrc.end(), x.aSrc.begin(), x.aSrc.end());
                     aTgt.insert(aTgt.end(), x.aTgt.begin(), x.aTgt.end());
                     aF.insert(aF.end(), x.aF.begin(), x.aF.end());
                     if (x.policy.empty()) policy.insert(policy.end(), x.aType.size(), 0.f);
                     else policy.insert(policy.end(), x.policy.begin(), x.policy.end());
                     tokOff[i + 1] = tokOff[i] + static_cast<std::int64_t>(x.numTokens());
                     actOff[i + 1] = actOff[i] + static_cast<std::int64_t>(x.aType.size());
                     searchValue[i] = x.searchValue;
                     outcome[i] = x.outcome; hpEnd[i] = x.hpEnd; maxHp[i] = x.maxHp; floor[i] = x.floor;
                     combat[i] = x.combat; hasPolicy[i] = x.policy.empty() ? 0 : 1; run[i] = x.run;
                     if (perFloor) {
                         if (x.hpFloor.size() != static_cast<std::size_t>(azbench::kFloors))
                             throw std::runtime_error("take_samples: sample without per-floor HP labels");
                         std::copy(x.hpFloor.begin(), x.hpFloor.end(), hpFloor.begin() + i * azbench::kFloors);
                     }
                     if (ema) {
                         if (x.outcomeTarget.size() != C || x.searchDist.size() != C)
                             throw std::runtime_error("take_samples: sample without search EMA targets");
                         std::copy(x.searchDist.begin(), x.searchDist.end(), searchDist.begin() + i * C);
                         std::copy(x.outcomeTarget.begin(), x.outcomeTarget.end(), outcomeTarget.begin() + i * C);
                         emaRealW[i] = x.emaRealWeight;
                     }
                 }
                 const auto nT = static_cast<py::ssize_t>(tokType.size()), nA = static_cast<py::ssize_t>(aType.size());
                 py::dict o;
                 o["tok_off"] = toArray(tokOff); o["act_off"] = toArray(actOff);
                 if (compact) { o["tok_idx"] = toArray(tokIdx); o["tok_base"] = toArray(tokBase); }
                 o["tok_type"] = toArray(tokType);
                 o["ids"] = toArray(ids).reshape({nT, static_cast<py::ssize_t>(search::kAmberCat)});
                 o["f"] = toArray(f).view("float16").reshape({nT, static_cast<py::ssize_t>(search::kAmberFloat)});
                 o["a_type"] = toArray(aType); o["a_src"] = toArray(aSrc); o["a_tgt"] = toArray(aTgt);
                 o["a_f"] = toArray(aF).view("float16").reshape({nA, static_cast<py::ssize_t>(search::kAmberActFeat)});
                 o["policy"] = toArray(policy); o["search_value"] = toArray(searchValue);
                 o["outcome"] = toArray(outcome); o["hp_end"] = toArray(hpEnd); o["max_hp"] = toArray(maxHp);
                 o["floor"] = toArray(floor); o["combat"] = toArray(combat); o["has_policy"] = toArray(hasPolicy);
                 o["run"] = toArray(run);
                 if (perFloor)
                     o["hp_floor"] = toArray(hpFloor).reshape({static_cast<py::ssize_t>(S),
                                                               static_cast<py::ssize_t>(azbench::kFloors)});
                 if (ema) {
                     const std::vector<py::ssize_t> sh{static_cast<py::ssize_t>(S), static_cast<py::ssize_t>(C)};
                     o["search_dist"] = toArray(searchDist).reshape(sh);
                     o["outcome_target"] = toArray(outcomeTarget).reshape(sh);
                     o["ema_real_weight"] = toArray(emaRealW);
                 }
                 return o;
             },
             py::arg("max_samples") = 1 << 20)
        .def("stats", [](const azbench::RunDriver &d) {
            const auto s = d.stats();
            py::dict o;
            o["evals"] = s.evals; o["moves"] = s.moves; o["searched_moves"] = s.searchedMoves;
            o["runs_started"] = s.runsStarted; o["runs_done"] = s.runsDone; o["wins"] = s.wins;
            o["floors_sum"] = s.floorsSum; o["stalls"] = s.stalls; o["terminal_leaves"] = s.terminalLeaves;
            o["encode_cut"] = s.encodeCut; o["encode_cut_ooc"] = s.encodeCutOoc; o["unsupported"] = s.unsupported; o["knowledge_failures"] = s.knowledgeFailures; o["invalid_actions"] = s.invalidActions;
            o["samples_done"] = s.samplesDone; o["samples_pending"] = s.samplesPending;
            o["batches"] = s.batches; o["batch_rows"] = s.batchRows;
            o["outcomes"] = std::vector<std::int64_t>(s.outcomes.begin(), s.outcomes.end());
            o["runs_done_asc"] = std::vector<std::int64_t>(s.runsDoneAsc.begin(), s.runsDoneAsc.end());
            o["wins_asc"] = std::vector<std::int64_t>(s.winsAsc.begin(), s.winsAsc.end());
            o["floors_sum_asc"] = std::vector<std::int64_t>(s.floorsSumAsc.begin(), s.floorsSumAsc.end());
            {   // run progress counters per ascension: name -> list of 21
                py::dict pr;
                auto field = [&](const char *name, std::int64_t azbench::RunProgress::*m) {
                    std::vector<std::int64_t> v;
                    for (const auto &p : s.progressAsc) v.push_back(p.*m);
                    pr[name] = v;
                };
                using P = azbench::RunProgress;
                field("ruby", &P::ruby); field("emerald", &P::emerald); field("sapphire", &P::sapphire);
                field("all_keys", &P::allKeys); field("campfires", &P::campfires);
                field("recall_offered", &P::recallOffered); field("rest", &P::rest); field("smith", &P::smith);
                field("recall", &P::recall); field("other_campfire", &P::otherCampfire);
                field("elites", &P::elites); field("burning_elites", &P::burningElites); field("act4", &P::act4);
                field("heart", &P::heart); field("keyless_victories", &P::keylessVictories);
                field("heart_hp_sum", &P::heartHpSum); field("heart_entry_hp_sum", &P::heartEntryHpSum);
                field("heart_turns_sum", &P::heartTurnsSum);
                field("relics_sum", &P::relicsSum); field("deck_size_sum", &P::deckSizeSum);
                field("chests", &P::chests); field("chests_skipped", &P::chestsSkipped);
                field("relics_taken_elite", &P::relicsTakenElite); field("relics_taken_chest", &P::relicsTakenChest);
                field("relics_taken_other", &P::relicsTakenOther); field("relics_left_elite", &P::relicsLeftElite);
                field("relics_left_chest", &P::relicsLeftChest); field("relics_left_other", &P::relicsLeftOther);
                field("shops", &P::shops); field("shop_cards", &P::shopCards); field("shop_relics", &P::shopRelics);
                field("shop_potions", &P::shopPotions); field("shop_removes", &P::shopRemoves);
                field("boss_relic_skips", &P::bossRelicSkips);
                field("gold_gained", &P::goldGained); field("gold_lost", &P::goldLost);
                field("sapphire_relic_forfeits", &P::sapphireRelicForfeits);
                field("ooc_potion_discards", &P::oocPotionDiscards); field("ooc_potion_drinks", &P::oocPotionDrinks);
                for (int b = 0; b < P::kHeartHpBins; ++b) {   // heart_hp_00 .. heart_hp_15: Heart HP left in [50 b, 50 b + 50)
                    std::vector<std::int64_t> v;
                    for (const auto &p : s.progressAsc) v.push_back(p.heartHpHist[b]);
                    char name[16]; std::snprintf(name, sizeof name, "heart_hp_%02d", b);
                    pr[name] = v;
                }
                o["progress_asc"] = pr;
            }
            o["ooc_roots"] = s.oocRoots; o["explore_roots"] = s.exploreRoots; o["forced_picks"] = s.forcedPicks;
            o["explore_attempts"] = s.exploreAttempts; o["explore_c_zero"] = s.exploreCZero;
            o["explore_c_inf"] = s.exploreCInf; o["explore_natural"] = s.exploreNatural;
            o["explore_natural_unplayed"] = s.exploreNaturalUnplayed;
            o["cache_hits"] = s.cacheHits;
            o["ooc_searched"] = py::make_tuple(s.oocSearched[0], s.oocSearched[1]);
            o["ooc_not_best_q"] = py::make_tuple(s.oocNotBestQ[0], s.oocNotBestQ[1]);
            o["ooc_q_spread_n"] = py::make_tuple(s.oocSpreadN[0], s.oocSpreadN[1]);
            o["ooc_q_spread_sum"] = py::make_tuple(s.oocSpreadSum[0], s.oocSpreadSum[1]);
            o["ooc_edges_det_chance"] = py::make_tuple(s.oocEdgeKinds[0], s.oocEdgeKinds[1]);
            o["tree_fight_starts"] = s.treeFightStarts;
            o["tree_fight_exits"] = s.treeFightExits;
            o["auto_gold"] = s.autoGold;
            o["savescum_runs"] = s.savescumRuns;
            o["savescum_checks"] = s.savescumChecks;
            o["savescum_mismatches"] = s.savescumMismatches;
            o["forced_keys"] = py::make_tuple(s.forcedKeys[0], s.forcedKeys[1], s.forcedKeys[2]);
            {   // exploreAmber per item class: card, deck_edit, relic, potion, event, rest, other_option, other
                py::list a, f;
                for (int k = 0; k < 8; ++k) { a.append(s.exploreAttemptsByClass[k]); f.append(s.forcedByClass[k]); }
                o["explore_attempts_by_class"] = a; o["forced_by_class"] = f;
            }
            o["key_route_masked"] = s.keyRouteMasked;
            o["forced_rewards"] = py::make_tuple(s.forcedRewards[0], s.forcedRewards[1], s.rewardRelicDeferred,
                                                 s.rewardRelicOnLeave);
            o["forced_potions"] = s.forcedPotions;
            o["ooc_canon"] = py::make_tuple(s.oocCanonScreens, s.oocCanonRemoved);
            o["heart_hp_min"] = s.heartHpMin;
            {   // memory gauges (current values): node-pool slots and their held states, per-run buffer capacities
                py::dict m;
                m["pool_nodes"] = s.memPoolNodes; m["pool_gc"] = s.memPoolGc; m["pool_bc"] = s.memPoolBc;
                m["pool_real"] = s.memPoolReal;
                m["pool_outer"] = s.memPoolOuter; m["edge_cap"] = s.memEdgeCap; m["pending_cap"] = s.memPendingCap;
                m["move_dist_cap"] = s.memMoveDistCap; m["cache_entries"] = s.memCacheEntries; m["done"] = s.memDone;
                o["mem"] = m;
            }
            o["step_cpu"] = s.stepCpu; o["encode_cpu"] = s.encodeCpu; o["search_cpu"] = s.searchCpu;
            o["pack_s"] = s.packSeconds;
            return o;
        });
}
