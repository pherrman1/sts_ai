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
        require(QuestionRoomHistory.capture(new ArrayList<String>(),new ArrayList<String>(),1,0,"").complete,
                "fresh run has complete empty history");
        require(!QuestionRoomHistory.capture(null,resolved,1,5,"EVENT").complete,
                "missing original path cannot qualify resolved history");
        require(!QuestionRoomHistory.capture(path,null,1,5,"EVENT").complete,
                "missing resolved path cannot qualify question history");
        System.out.println("QuestionRoomHistoryTest passed");
    }
}
