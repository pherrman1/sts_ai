#include <iostream>

#include "sim/search/SilverBridge.h"

int main() {
    const auto probe = silver_bridge::constructReferenceSearcherProbe();
    if (!probe.rootAllocated || probe.rootIsChanceNode) {
        std::cout << "silver_searcher_link_closure FAIL\n";
        return 1;
    }
    std::cout << "silver_searcher_link_closure PASS\n";
    return 0;
}
