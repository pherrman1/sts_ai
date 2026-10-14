#pragma once
#include "ooc_mcts_adapter.h"
#include <functional>
namespace one_combat {
using AuditFork = std::function<nlohmann::json(const std::function<nlohmann::json()> &, int, int)>;
int runSelectiveSilverAudit(std::uint64_t seed, const std::string &plan, const std::string &out,
    std::shared_ptr<const CombatTransitionSampler>, OocAdapterOptions, sts::search::OocMctsConfig,
    const AuditFork &);
nlohmann::json selectiveAuditSourcePolicy();
nlohmann::json oocSelectiveSilverAuditSpec();
int oocSelectiveSilverAuditGen(std::uint64_t seed, const std::string &plan, const std::string &out);
}
