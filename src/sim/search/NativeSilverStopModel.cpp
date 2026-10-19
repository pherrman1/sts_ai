// Selector between the compiled learned-stop models (NativeSilverStopModel.h).
#include "sim/search/NativeSilverStopModel.h"

#include <cstdlib>
#include <stdexcept>
#include <string>

namespace sts::search {

namespace {
struct StopModel {
    bool (*trained)();
    const char *(*id)();
    double (*threshold)();
    double (*risk)(const NativeSilverStopFeatures &);
};

const StopModel &selectedStopModel() {
    static const StopModel model = [] {
        const StopModel a20 {nativeSilverStopModelA20Trained, nativeSilverStopModelA20Id,
                             nativeSilverStopModelA20DefaultThreshold, nativeSilverStopModelA20Risk};
        const StopModel a0 {nativeSilverStopModelA0Trained, nativeSilverStopModelA0Id,
                            nativeSilverStopModelA0DefaultThreshold, nativeSilverStopModelA0Risk};
        const char *raw = std::getenv("STS_SILVER_LEARNED_STOP_MODEL");
        if (!raw || !*raw || std::string(raw) == a20.id()) return a20;
        if (std::string(raw) == a0.id()) return a0;
        throw std::runtime_error(std::string("STS_SILVER_LEARNED_STOP_MODEL must be ") + a20.id() + " or "
                                 + a0.id() + ", got " + raw);
    }();
    return model;
}
}

bool nativeSilverStopModelTrained() { return selectedStopModel().trained(); }
const char *nativeSilverStopModelId() { return selectedStopModel().id(); }
double nativeSilverStopModelDefaultThreshold() { return selectedStopModel().threshold(); }
double nativeSilverStopModelRisk(const NativeSilverStopFeatures &x) { return selectedStopModel().risk(x); }

}
