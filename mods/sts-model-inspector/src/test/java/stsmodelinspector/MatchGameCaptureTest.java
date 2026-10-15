package stsmodelinspector;
import java.util.*;

public final class MatchGameCaptureTest {
    static void check(boolean test,String reason){if(!test)throw new AssertionError(reason);}
    @SuppressWarnings("unchecked") static Map<String,Object> row(List<Object> board,int slot){return (Map<String,Object>)board.get(slot);}
    static List<MatchGameCapture.PublicSlot> hidden(){List<MatchGameCapture.PublicSlot> cards=new ArrayList<>();for(int i=0;i<12;++i)cards.add(new MatchGameCapture.PublicSlot(i,"uuid"+i,false,null));return cards;}
    public static void main(String[]args) {
        Map<Integer,String> ids=new HashMap<>();for(int i=0;i<12;++i)ids.put(i,"uuid"+i);
        Object boardOwner=new Object();MatchGameCapture.Memory memory=new MatchGameCapture.Memory();
        List<MatchGameCapture.PublicSlot> cards=hidden();memory.observe(boardOwner,ids,cards,5);
        check(memory.complete&&memory.error==null,"fresh board observation");
        for(Object raw:memory.board(cards))check(!((Map<?,?>)raw).containsKey("card"),"unseen identity leaked");
        Map<String,Object> anger=MatchGameCapture.obj("id","Anger","upgraded",false,"misc",0);
        cards.set(4,new MatchGameCapture.PublicSlot(4,"uuid4",true,anger));memory.observe(boardOwner,ids,cards,5);
        check("face_up".equals(row(memory.board(cards),4).get("state")),"first physical flip lost");
        cards.set(8,new MatchGameCapture.PublicSlot(8,"uuid8",true,anger));memory.observe(boardOwner,ids,cards,5);
        cards=hidden();memory.observe(boardOwner,ids,cards,4);
        check("seen".equals(row(memory.board(cards),4).get("state"))&&row(memory.board(cards),8).containsKey("card"),"public flip memory lost after turn down");
        cards.remove(8);cards.remove(4);memory.observe(boardOwner,ids,cards,3);
        check("matched".equals(row(memory.board(cards),4).get("state"))&&"matched".equals(row(memory.board(cards),8).get("state")),"matched physical slots lost");
        memory.observe(new Object(),ids,hidden(),5);
        check(memory.seen.isEmpty()&&memory.complete,"new board reused prior knowledge");
        MatchGameCapture.Memory resumed=new MatchGameCapture.Memory();resumed.observe(new Object(),ids,hidden(),3);
        check(!resumed.complete&&resumed.seen.isEmpty(),"mid-board attachment invented past identities");
        MatchGameCapture.Memory invalid=new MatchGameCapture.Memory();cards=hidden();cards.set(0,new MatchGameCapture.PublicSlot(0,"uuid0",false,anger));invalid.observe(new Object(),ids,cards,5);
        check("MATCH_HIDDEN_CARD_LEAK".equals(invalid.error),"hidden card payload accepted");
        invalid=new MatchGameCapture.Memory();cards=hidden();cards.set(0,new MatchGameCapture.PublicSlot(1,"uuid1",false,null));invalid.observe(new Object(),ids,cards,5);
        check(invalid.error!=null,"duplicate physical board slot accepted");
        System.out.println("MatchGameCaptureTest: hidden identity exclusion, public flip memory, matched slots, fresh-board reset and incomplete attachment passed");
    }
}
