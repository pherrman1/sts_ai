"""Input-encoding provenance of STS_OOC_HEART1_CAPTURE rows (torch-free, so distill.py and tests share it).

wing_boots_counter: each capture row records STS_OOC_HEART1_WING_BOOTS_COUNTER (#638), 1 when its record's
Wing Boots relic counter holds the charges. Rows from before that field always encoded 0. A training set must
use one value, the one the trained weights are then deployed with."""


def row_wing_boots_counter(row):
    value = row.get("wing_boots_counter", 0)
    if value not in (0, 1):
        raise ValueError(f"wing_boots_counter must be 0 or 1, got {value!r}")
    return value


def single_wing_boots_counter(values):
    """The one value in `values` (0 when empty); raises on a mixed training set."""
    seen = set(values)
    if len(seen) > 1:
        raise ValueError("capture rows mix STS_OOC_HEART1_WING_BOOTS_COUNTER values "
                         f"{sorted(seen)}; train on one value")
    return seen.pop() if seen else 0
