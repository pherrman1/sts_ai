package stsmodelinspector;

import java.util.*;

public final class TargetLabelsTest {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("Spike Slime (M)", "Cultist");
        Map<Integer, Integer> slots = new HashMap<>();
        slots.put(0, 1); slots.put(2, 2);
        if (!"Bash -> Cultist".equals(TargetLabels.silver("Bash -> Monster 3", slots, names))
                || !"Strike -> Spike Slime (M)".equals(TargetLabels.silver("Strike -> Monster 1", slots, names))
                || !"End Turn".equals(TargetLabels.silver("End Turn", slots, names))
                || !"Strike -> Unknown target".equals(TargetLabels.silver("Strike -> Monster 2", slots, names)))
            throw new AssertionError("native slot must resolve through physical monster identity");
        if (!"Cultist".equals(TargetLabels.name(names, 2))
                || !"Cultist (2)".equals(TargetLabels.name(Arrays.asList("Cultist", "Cultist"), 2))
                || !"Unknown target".equals(TargetLabels.name(names, 3)))
            throw new AssertionError("physical target name or duplicate distinction lost");
        System.out.println("TargetLabelsTest: sparse native slots, physical targets, duplicates and unknown targets passed");
    }
}
