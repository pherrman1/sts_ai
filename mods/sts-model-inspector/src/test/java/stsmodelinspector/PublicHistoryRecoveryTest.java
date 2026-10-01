package stsmodelinspector;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class PublicHistoryRecoveryTest {
    private static void require(boolean ok,String why) { if(!ok)throw new AssertionError(why); }
    private static Map<String,Object> obj(Object... fields) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(int i=0;i<fields.length;i+=2)result.put((String)fields[i],fields[i+1]);return result;
    }
    private static List<Map<String,Object>> metrics() {
        return new ArrayList<>(Arrays.asList(obj("floor",1,"enemies","Jaw Worm"),
                obj("floor",2,"enemies","2 Louse"),obj("floor",3,"enemies","The Mushroom Lair"),
                obj("floor",4,"enemies","3 Sentries")));
    }
    public static void main(String[] args) {
        QuestionRoomHistory path=QuestionRoomHistory.capture(Arrays.asList("M","?","?","E","R"),
                Arrays.asList("M","M","?","E","R"),1,5,"REST");
        List<Map<String,Object>> recovered=PublicHistoryRecovery.combats(path,metrics(),1,5);
        require(recovered!=null && recovered.size()==4,"legacy join");
        require(recovered.get(1).get("kind").equals("NORMAL_QUEUE")
                && recovered.get(1).get("encounter").equals("TWO_LOUSE"),"converted hallway alias");
        require(recovered.get(2).get("kind").equals("FIXED_EVENT")
                && recovered.get(3).get("encounter").equals("THREE_SENTRIES"),"fixed versus elite");
        for(int bad=0;bad<6;++bad) {
            List<Map<String,Object>> invalid=metrics();
            if(bad==0)invalid.get(1).remove("enemies");
            if(bad==1)invalid.get(1).put("enemies","2 Louse localized or modded");
            if(bad==2)invalid.get(1).put("enemies","3 Sentries");
            if(bad==3)invalid.get(1).put("floor",2.5);
            if(bad==4)invalid.remove(1);
            if(bad==5)invalid.add(obj("floor",4,"enemies","3 Sentries"));
            require(PublicHistoryRecovery.combats(path,invalid,1,5)==null,"invalid history "+bad);
        }
        Object player=new Object();
        new RelicOfferRecorder().receivePreStartGame();
        LiveOocCapture.CombatClassHistory ledger=new LiveOocCapture.CombatClassHistory();
        require(ledger.recoverLegacy(player,9,1,5,path,metrics(),Arrays.asList(1,2,3,4)),"legacy migration");
        require(ledger.completeFor(Arrays.asList(1,2,3,4)),"migrated ledger completeness");
        RelicOfferRecorder.SaveData checkpoint=new RelicOfferRecorder.SaveData();
        checkpoint.combatAct=1;checkpoint.combatComplete=true;checkpoint.combatEntries=ledger.snapshot();
        require(new LiveOocCapture.CombatClassHistory().restoreCheckpoint(player,9,1,5,checkpoint,
                Arrays.asList(1,2,3,4)),"recovered ledger persists through existing checkpoint");
        require(!LiveOocCapture.seenRelicOffers.complete(),"combat migration qualified relic history");
        new RelicOfferRecorder().onLoadRaw(new com.google.gson.JsonObject());
        require(!new LiveOocCapture.CombatClassHistory().recoverLegacy(player,9,1,5,path,metrics(),
                Arrays.asList(1,2,3,4)),"malformed checkpoint healed by migration");

        List<String> offers=PublicHistoryRecovery.bossOffers(Arrays.asList(
                obj("picked","Runic Dome","not_picked",Arrays.asList("Black Star","Snecko Eye")),
                obj("not_picked",Arrays.asList("Sozu","Coffee Dripper","Cursed Key"))));
        require(offers.size()==6 && offers.contains("Runic Dome") && offers.contains("Cursed Key"),"boss skipped offers");
        require(!LiveOocCapture.seenRelicOffers.complete(),"boss subset qualified global offer history");
        boolean rejected=false;
        try { PublicHistoryRecovery.bossOffers(Arrays.asList(obj("picked","Sozu","not_picked",Arrays.asList("Sozu")))); }
        catch(IllegalArgumentException expected) { rejected=true; }
        require(rejected,"duplicate boss offer accepted");

        List<Map<String,Object>> outcomes=new ArrayList<>();
        for(int f:Arrays.asList(2,4,6,8))outcomes.add(obj("floor",f,"outcome","EVENT"));
        List<Map<String,Object>> acquired=Arrays.asList(obj("floor",4,"key","Juzu Bracelet"));
        List<Map<String,Object>> events=Arrays.asList(obj("floor",4,"relics_obtained",Arrays.asList("Juzu Bracelet")),
                obj("floor",6,"relics_lost",Arrays.asList("Juzu Bracelet")));
        PublicHistoryRecovery.annotateJuzu(outcomes,acquired,events,false,8);
        require(Boolean.FALSE.equals(outcomes.get(0).get("juzuOwnedAtEntry"))
                && Boolean.FALSE.equals(outcomes.get(1).get("juzuOwnedAtEntry"))
                && Boolean.TRUE.equals(outcomes.get(2).get("juzuOwnedAtEntry"))
                && Boolean.FALSE.equals(outcomes.get(3).get("juzuOwnedAtEntry")),"gain/loss inside floor ordering");
        for(int bad=0;bad<4;++bad) {
            List<Map<String,Object>> unknown=Arrays.asList(obj("floor",5,"outcome","EVENT"));
            PublicHistoryRecovery.annotateJuzu(unknown,bad==0?null:acquired,
                    bad==1?Collections.emptyList():bad==2?Arrays.asList(obj("floor",4,"relics_lost",Arrays.asList("Juzu Bracelet"))):events,
                    bad==3,8);
            require(!unknown.get(0).containsKey("juzuOwnedAtEntry"),"ambiguous ownership fabricated "+bad);
        }
        QuestionRoomHistory tiny=QuestionRoomHistory.capture(Arrays.asList("?","?","?","?","?"),
                Arrays.asList("?","?","?","?","T"),1,5,"TREASURE");
        List<Map<String,Object>> tinyGain=Arrays.asList(obj("floor",1,"key","Tiny Chest"));
        PublicHistoryRecovery.annotateTinyChest(tiny,tinyGain,Collections.emptyList(),true,0,5);
        require(Boolean.FALSE.equals(tiny.outcomes.get(0).get("tinyChestForced"))
                && Boolean.TRUE.equals(tiny.outcomes.get(4).get("tinyChestForced")),"Tiny acquired after entry roll");
        tiny=QuestionRoomHistory.capture(Arrays.asList("?","?","?","?","?"),
                Arrays.asList("?","?","?","?","T"),1,5,"TREASURE");
        PublicHistoryRecovery.annotateTinyChest(tiny,tinyGain,Collections.emptyList(),true,1,5);
        require(!tiny.outcomes.get(0).containsKey("tinyChestForced"),"Tiny counter contradiction fabricated forcing");
        List<String> original=new ArrayList<>(),resolved=new ArrayList<>();
        for(int f=1;f<=19;++f) {
            String room=f==16?"B":f==17?null:f==2||f==4||f==6||f==19?"?":"M";
            if(f!=17)original.add(room);resolved.add(f==19?"T":room);
        }
        tiny=QuestionRoomHistory.capture(original,resolved,2,19,"TREASURE");
        PublicHistoryRecovery.annotateTinyChest(tiny,tinyGain,Collections.emptyList(),true,0,19);
        require(tiny.outcomes.size()==1 && Boolean.TRUE.equals(tiny.outcomes.get(0).get("tinyChestForced")),
                "Tiny counter must span act reset");
        QuestionRoomHistory shop=QuestionRoomHistory.capture(Arrays.asList("$","?","?"),
                Arrays.asList("$","?","?"),1,3,"EVENT");
        require(Boolean.TRUE.equals(shop.outcomes.get(0).get("previousRoomWasShop"))
                && Boolean.FALSE.equals(shop.outcomes.get(1).get("previousRoomWasShop")),"previous shop suppression history");
        PublicHistoryRecovery.annotateTinyChest(shop,Collections.emptyList(),Collections.emptyList(),false,0,3);
        require(Boolean.FALSE.equals(shop.outcomes.get(0).get("tinyChestForced")),"never-owned Tiny known absent");
        System.out.println("PublicHistoryRecoveryTest passed");
    }
}
