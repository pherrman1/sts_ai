package stsmodelinspector;

import java.util.List;
import java.util.Map;

/** Display names only; action bindings retain their exact physical targets. */
final class TargetLabels {
    static String name(List<String> names, int oneBasedIndex) {
        if (oneBasedIndex < 1 || oneBasedIndex > names.size()) return "Unknown target";
        String name = names.get(oneBasedIndex - 1);
        if (name == null || name.isEmpty()) return "Unknown target";
        int count = 0;
        for (String other : names) if (name.equals(other)) ++count;
        return count > 1 ? name + " (" + oneBasedIndex + ")" : name;
    }

    static String silver(String label, Map<Integer, Integer> physicalIndexBySlot, List<String> names) {
        String marker = " -> Monster ";
        int arrow = label.lastIndexOf(marker);
        if (arrow < 0) return label;
        try {
            int slot = Integer.parseInt(label.substring(arrow + marker.length())) - 1;
            Integer index = physicalIndexBySlot.get(slot);
            return label.substring(0, arrow) + " -> " +
                    (index == null ? "Unknown target" : name(names, index));
        } catch (NumberFormatException invalid) {
            return label;
        }
    }
}
