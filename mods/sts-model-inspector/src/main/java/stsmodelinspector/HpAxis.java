package stsmodelinspector;

import java.util.*;

/**
 * A shared 0..axisMaxHp HP axis for one response's sample layers: bar 0 holds
 * deaths and bars 1..buckets cover HP 1..axisMaxHp. One y scale (the largest
 * share of any layer) keeps hover outlines comparable with the baseline.
 */
final class HpAxis {
    final int currentHp, maxHp, axisMaxHp;
    private final List<CombatHpOverlay.Layer> layers;

    HpAxis(int currentHp, int maxHp, int axisMaxHp, List<CombatHpOverlay.Layer> layers) {
        this.currentHp = currentHp; this.maxHp = maxHp; this.axisMaxHp = axisMaxHp;
        this.layers = Collections.unmodifiableList(new ArrayList<>(layers));
    }

    int buckets() { return Math.max(1, Math.min(40, axisMaxHp)); }

    /** Inclusive HP range of bar `bucket` in [1, buckets]; bar 0 is deaths. */
    int[] bucketRange(int bucket, int buckets) {
        if (bucket == 0) return new int[] {0, 0};
        return new int[] {1 + (bucket - 1) * axisMaxHp / buckets, bucket * axisMaxHp / buckets};
    }

    double maxShare(int buckets) {
        double maximum = 0;
        for (CombatHpOverlay.Layer layer : layers) {
            maximum = Math.max(maximum, layer.deathShare());
            for (int bucket = 1; bucket <= buckets; ++bucket) {
                int[] range = bucketRange(bucket, buckets);
                maximum = Math.max(maximum, layer.share(range[0], range[1]));
            }
        }
        return maximum;
    }
}
