package stsmodelinspector;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Reconstruct only publicly resolved rooms from vanilla's persisted metrics. */
final class QuestionRoomHistory {
    final List<Map<String,Object>> outcomes = new ArrayList<>();
    final List<Map<String,Object>> allOutcomes = new ArrayList<>();
    // Absolute floor alignment, including boss-chest placeholders. Used only
    // after complete validates both persisted paths against the current room.
    final List<String> rooms = new ArrayList<>();
    boolean complete;

    static QuestionRoomHistory capture(List<String> original, List<String> resolved,
            int act, int floor, String currentOutcome) {
        QuestionRoomHistory result = new QuestionRoomHistory();
        if (original == null || resolved == null || act < 1 || act > 4 || floor < 0
                || resolved.size() > floor || resolved.size() < floor - 1) return result;
        int start = act <= 1 ? 0 : act == 2 ? 17 : act == 3 ? 34 : 51;
        if (floor < start) return result;
        int source = 0;
        for (int i=0; i<floor; ++i) {
            int visitedFloor = i+1;
            String outcome = i < resolved.size() ? symbol(resolved.get(i)) : currentOutcome;
            result.rooms.add(outcome);
            if (visitedFloor == floor && !outcome.equals(currentOutcome)) return result;
            // Vanilla records the boss chest as null in path_per_floor and
            // omits it from path_taken. Never drop arbitrary missing entries.
            if ("NONE".equals(outcome) && visitedFloor % 17 == 0) {
                if (reloadedBossMarker(original, source)) ++source;
                continue;
            }
            if (source >= original.size()) return result;
            String room = symbol(original.get(source++));
            if ("EVENT".equals(room)) {
                if (!Arrays.asList("MONSTER","SHOP","TREASURE","EVENT").contains(outcome)) return result;
                Map<String,Object> entry = new LinkedHashMap<>();
                entry.put("floor",visitedFloor); entry.put("outcome",outcome);
                entry.put("previousRoomWasShop",i>0 && "SHOP".equals(result.rooms.get(i-1)));
                result.allOutcomes.add(entry);
                if (visitedFloor > start) result.outcomes.add(entry);
            } else if ("INVALID".equals(room) || "NONE".equals(room) || !room.equals(outcome)) return result;
        }
        // At the boss floor itself the duplicate is the last path entry.
        if (floor % 17 == 16 && source == original.size() - 1 && reloadedBossMarker(original, source)) ++source;
        result.complete = source == original.size();
        return result;
    }

    // Continuing a post-combat boss save reruns MonsterRoomBoss.onPlayerEntry,
    // which appends "BOSS" to path_taken again (path_per_floor keeps one "B"), so a second adjacent "BOSS" before
    // the boss chest is that reload marker, not a room.
    private static boolean reloadedBossMarker(List<String> original, int source) {
        return source > 0 && source < original.size()
                && "BOSS".equals(symbol(original.get(source)))
                && "BOSS".equals(symbol(original.get(source - 1)));
    }

    static String roomOutcome(String roomClass) {
        switch (roomClass) {
            case "EventRoom": return "EVENT";
            case "MonsterRoom": return "MONSTER";
            case "ShopRoom": return "SHOP";
            case "TreasureRoom": return "TREASURE";
            case "TreasureRoomBoss": return "NONE";
            case "MonsterRoomBoss": return "BOSS";
            case "MonsterRoomElite": return "ELITE";
            case "RestRoom": return "REST";
            default: return "INVALID";
        }
    }

    private static String symbol(String raw) {
        if (raw == null) return "NONE";
        switch (raw) {
            case "M": return "MONSTER";
            case "?": return "EVENT";
            case "$": return "SHOP";
            case "T": return "TREASURE";
            case "E": return "ELITE";
            case "R": return "REST";
            case "B": case "BOSS": return "BOSS";
            default: return "INVALID";
        }
    }
}
