#ifndef STS_LIGHTSPEED_ONE_COMBAT_S3_SIBLING_CRN_DIAGNOSTIC_H
#define STS_LIGHTSPEED_ONE_COMBAT_S3_SIBLING_CRN_DIAGNOSTIC_H

#include <string>

namespace one_combat {

bool isS3SiblingCrnDiagnosticMode(const std::string &mode);

int runS3SiblingCrnDiagnosticMode(const std::string &mode,
                                  int argc,
                                  char **argv);

} // namespace one_combat

#endif
