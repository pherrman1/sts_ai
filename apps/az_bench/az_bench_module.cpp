// Python bridge of the stage 0 end-to-end producer (az_driver.h): tools/az_bench/e2e_bench.py drives the worker
// threads from Python and evaluates each packed batch with a PyTorch net on the GPU. The GIL is released while
// C++ waits for or packs a batch and while it posts results; batch arrays are handed to numpy without a copy.
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstring>

#include <nlohmann/json.hpp>

#include "az_driver.h"
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
                int sortWindow) -> py::object {
                 // bufs: writeable C-contiguous arrays sized for the largest buckets (e.g. numpy views of pinned
                 // torch tensors): tok_type int8, ids int16, f float16, mask bool/uint8, a_type / a_src / a_tgt
                 // int16, a_f float16, a_mask bool/uint8.
                 const int R = std::max(maxRows, rowBuckets.empty() ? 0 : rowBuckets.back());
                 const int T = tokBuckets.empty() ? search::kAmberMaxTokens : tokBuckets.back();
                 const int A = actBuckets.empty() ? search::kAmberMaxActions : actBuckets.back();
                 auto ptr = [&](const char *k, std::size_t bytes) -> void * {
                     py::array a = bufs[k].cast<py::array>();
                     if (!(a.flags() & py::array::c_style) || !a.writeable())
                         throw std::invalid_argument(std::string("next_flat: buffer ") + k + " not writeable C order");
                     if (static_cast<std::size_t>(a.nbytes()) < bytes)
                         throw std::invalid_argument(std::string("next_flat: buffer ") + k + " too small");
                     return a.mutable_data();
                 };
                 const std::size_t rt = static_cast<std::size_t>(R) * T, ra = static_cast<std::size_t>(R) * A;
                 azbench::Driver::FlatBuffers fb{
                     static_cast<std::int8_t *>(ptr("tok_type", rt)),
                     static_cast<std::int16_t *>(ptr("ids", rt * search::kAmberCat * 2)),
                     static_cast<std::uint16_t *>(ptr("f", rt * search::kAmberFloat * 2)),
                     static_cast<std::uint8_t *>(ptr("mask", rt)),
                     static_cast<std::int16_t *>(ptr("a_type", ra * 2)),
                     static_cast<std::int16_t *>(ptr("a_src", ra * 2)),
                     static_cast<std::int16_t *>(ptr("a_tgt", ra * 2)),
                     static_cast<std::uint16_t *>(ptr("a_f", ra * search::kAmberActFeat * 2)),
                     static_cast<std::uint8_t *>(ptr("a_mask", ra))};
                 azbench::Driver::FlatShape shape;
                 std::vector<std::uint32_t> tickets;
                 {
                     py::gil_scoped_release r;
                     tickets = d.nextBatchFlat(maxRows, minRows, timeoutMs, rowBuckets, tokBuckets, actBuckets, fb,
                                               shape, sortWindow);
                 }
                 if (tickets.empty()) return py::none();
                 py::array_t<std::uint32_t> t(static_cast<py::ssize_t>(tickets.size()));
                 std::memcpy(t.mutable_data(), tickets.data(), tickets.size() * sizeof(std::uint32_t));
                 return py::make_tuple(t, shape.rows, shape.rowsPadded, shape.tokens, shape.actions);
             },
             py::arg("max_rows"), py::arg("min_rows"), py::arg("timeout_ms"), py::arg("row_buckets"),
             py::arg("tok_buckets"), py::arg("act_buckets"), py::arg("bufs"), py::arg("sort_window") = 1)
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
            return o;
        });
}
