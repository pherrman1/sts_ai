package stsmodelinspector;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class QuestionRoomHistoryTest {
    private static void require(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }
    public static void main(String[] args) {
        List<String> path = Arrays.asList("M", "?", "?", "?", "?");
        List<String> resolved = Arrays.asList("M", "M", "$", "T", "?");
        QuestionRoomHistory history = QuestionRoomHistory.capture(path, resolved, 1, 5, "EVENT");
        require(history.complete && history.outcomes.size() == 4, "saved outcomes must recover without a ledger");
        String[] outcomes = {"MONSTER", "SHOP", "TREASURE", "EVENT"};
        for (int i=0; i<4; ++i) {
            require(history.outcomes.get(i).get("floor").equals(i+2), "outcome floor");
            require(history.outcomes.get(i).get("outcome").equals(outcomes[i]), "resolved outcome");
        }
        require(QuestionRoomHistory.capture(path, resolved.subList(0,4), 1, 5, "EVENT").complete,
                "current observed room may finish an enter-room save");
        require(!QuestionRoomHistory.capture(path, resolved.subList(0,3), 1, 5, "EVENT").complete,
                "missing historical rooms must fail closed");
        require(!QuestionRoomHistory.capture(path, Arrays.asList("$","M","$","T","?"), 1,5,"EVENT").complete,
                "original/resolved path contradiction");
        require(!QuestionRoomHistory.capture(path, Arrays.asList("M","M",null,"T","?"), 1,5,"EVENT").complete,
                "null outside a boss chest is not a skipped floor");
        require(!QuestionRoomHistory.capture(path, Arrays.asList("M","M","E","T","?"), 1,5,"EVENT").complete,
                "unsupported question outcome");
        require(!QuestionRoomHistory.capture(path, resolved, 1,4,"EVENT").complete,
                "future save entries must not leak into an earlier observation");
        require(!QuestionRoomHistory.capture(path, resolved, 1,5,"SHOP").complete,
                "current resolved room must agree with live room class");
        require(!QuestionRoomHistory.capture(path, resolved, 1,5,"INVALID").complete,
                "unknown current room must fail closed");
        List<String> laterPath = new ArrayList<>(), laterResolved = new ArrayList<>();
        for(int i=0;i<15;++i) { laterPath.add("M"); laterResolved.add("M"); }
        laterPath.set(2,"?"); // Earlier-act question outcomes must not leak into this act.
        laterPath.add("BOSS"); laterResolved.add("B"); laterResolved.add(null);
        laterPath.add("M"); laterResolved.add("M");
        laterPath.add("?"); laterResolved.add("$");
        history = QuestionRoomHistory.capture(laterPath,laterResolved,2,19,"SHOP");
        require(history.complete && history.outcomes.size()==1
                && history.outcomes.get(0).get("floor").equals(19)
                && history.outcomes.get(0).get("outcome").equals("SHOP"),
                "boss chest placeholder must not shift act-two question floors");
        // Canary 2 (seed 111194451): the floor-16 post-boss save was continued,
        // leaving "BOSS","BOSS" in path_taken but one "B" in path_per_floor.
        List<String> reloadPath = new ArrayList<>(laterPath.subList(0,16)), reloadResolved = new ArrayList<>(laterResolved.subList(0,16));
        reloadPath.add("BOSS");
        require(QuestionRoomHistory.capture(reloadPath,reloadResolved,1,16,"BOSS").complete,
                "reloaded boss marker at the boss floor");
        reloadPath.add("M"); reloadPath.add("?");
        reloadResolved.add(null); reloadResolved.add("M");
        history = QuestionRoomHistory.capture(reloadPath,reloadResolved,2,19,"EVENT");
        require(history.complete && history.outcomes.size()==1
                && history.outcomes.get(0).get("floor").equals(19),
                "reloaded boss marker must not block act-two question history");
        reloadPath.add(16,"BOSS");
        require(!QuestionRoomHistory.capture(reloadPath,reloadResolved,2,19,"EVENT").complete,
                "only one reloaded boss marker is skipped");
        require(QuestionRoomHistory.capture(new ArrayList<String>(),new ArrayList<String>(),1,0,"").complete,
                "fresh run has complete empty history");
        require(!QuestionRoomHistory.capture(null,resolved,1,5,"EVENT").complete,
                "missing original path cannot qualify resolved history");
        require(!QuestionRoomHistory.capture(path,null,1,5,"EVENT").complete,
                "missing resolved path cannot qualify question history");
        // A20 Act 3 double boss (floors 50 and 51): the VictoryRoom null is
        // floor 52, then Act 4 rest, shop and Shield & Spear.
        QuestionRoomHistory.victoryRoomFix = true;
        List<String> a20Path = new ArrayList<>(), a20Resolved = new ArrayList<>();
        for (int act=1; act<=3; ++act) {
            for (int i=0; i<15; ++i) { a20Path.add(i == 3 ? "?" : "M"); a20Resolved.add(i == 3 ? "$" : "M"); }
            a20Path.add("BOSS"); a20Resolved.add("B");
            if (act < 3) a20Resolved.add(null);
        }
        a20Path.add("BOSS"); a20Resolved.add("B"); a20Resolved.add(null);
        require(a20Resolved.size() == 52 && a20Path.size() == 49, "A20 path fixture shape");
        require(QuestionRoomHistory.capture(a20Path,a20Resolved,4,52,QuestionRoomHistory.roomOutcome("VictoryRoom")).complete,
                "A20 Act 4 entry map (VictoryRoom) has complete history");
        a20Path.add("R"); a20Resolved.add("R");
        a20Path.add("$"); a20Resolved.add("$");
        a20Path.add("E"); a20Resolved.add("E");
        history = QuestionRoomHistory.capture(a20Path,a20Resolved,4,55,"ELITE");
        require(history.complete && history.outcomes.isEmpty() && history.allOutcomes.size() == 3,
                "A20 Act 4 history after the double boss is complete");
        List<String> singleBoss = new ArrayList<>(a20Resolved);
        singleBoss.set(50,"M");
        List<String> singlePath = new ArrayList<>(a20Path);
        singlePath.set(48,"M");
        require(!QuestionRoomHistory.capture(singlePath,singleBoss,4,55,"ELITE").complete,
                "a floor-52 null without the double boss is not a VictoryRoom");
        QuestionRoomHistory.victoryRoomFix = false;
        require(!QuestionRoomHistory.capture(a20Path,a20Resolved,4,55,"ELITE").complete,
                "STS_A20_VICTORY_ROOM_HISTORY_FIX=0 restores the old incomplete history");
        require("INVALID".equals(QuestionRoomHistory.roomOutcome("VictoryRoom")),
                "legacy VictoryRoom outcome");
        QuestionRoomHistory.victoryRoomFix = true;
        System.out.println("QuestionRoomHistoryTest passed");
    }
}
