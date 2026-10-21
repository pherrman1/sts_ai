package stsmodelinspector;

import java.util.*;

/** Source-shaped event objects avoid initializing the game or revealing hidden outcomes. */
public final class LiveEventCaptureTest {
    static class Base { int screenNum=0; }
    static class Cleric extends Base { int healAmt=20; int unusedHiddenRelic=987; }
    static class GoldenIdolEvent extends Base { int damage=24,maxHpLoss=8; }
    static class ShiningLight { String screen="INTRO";int damage=16; }
    static class Designer extends Base { String curScreen="MAIN";boolean adjustmentUpgradesOne,cleanUpRemovesCards; }
    static class CursedTome { String screen="INTRO";int hiddenBook=2; }
    static class KnowingSkull { String screen="ASK";int goldCost=8,cardCost=7,potionCost=6,leaveCost=6; }
    static class ScrapOoze extends Base { int dmg=5,relicObtainChance=45; }
    static class DeadAdventurer { String screen="INTRO";int numRewards=2,encounterChance=75,enemy=1,goldRewardMetric=30;Object relicRewardMetric=null;String rewards="MUST_NOT_CAPTURE"; }
    static class Lab { String screen="INTRO"; }
    static class Bonfire { String screen="CHOOSE"; }
    static class Ghosts extends Base { int hpLoss=40; }
    static class Mushrooms extends Base {}
    static class TheJoust { String screen="HALT"; }
    static class Unknown { String screen="COMPLETE"; }
    static Map<String,Object> obj(Object...pairs) {Map<String,Object> m=new LinkedHashMap<>();for(int i=0;i<pairs.length;i+=2)m.put((String)pairs[i],pairs[i+1]);return m;}
    @SuppressWarnings("unchecked") static Map<String,Object> map(Object v){return (Map<String,Object>)v;}
    static Map<String,Object> capture(Object event,int...slots)throws Exception {
        List<Object> options=new ArrayList<>();List<Map<String,Object>> choices=new ArrayList<>();
        for(int slot:slots){options.add(obj("index",slot,"disabled",false));choices.add(obj("nativeAction",obj("index",slot)));}
        Map<String,Object> out=obj("details",obj(),"event",obj("phase",LiveEventCapture.phase(event)),"unsupportedReason","phase","liveChoices",choices);
        LiveEventCapture.capture(out,event,options,choices);return out;
    }
    static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    @SuppressWarnings("unchecked") static void indices(Map<String,Object> out,int...expected){
        List<Map<String,Object>> choices=(List<Map<String,Object>>)out.get("liveChoices");
        for(int i=0;i<expected.length;++i)check(Integer.valueOf(expected[i]).equals(map(choices.get(i).get("nativeAction")).get("index")),"physical/native event option mismatch");
    }
    public static void main(String[]args)throws Exception {
        check(LiveEventCapture.weMeetGold(0,49)==-1 && LiveEventCapture.weMeetGold(50,50)==50
                && LiveEventCapture.weMeetGold(150,200)==150,"We Meet Again no-gold sentinel");
        for(int[] malformed:new int[][]{{0,50},{-1,49},{49,100},{151,200},{100,99}}) {
            try {LiveEventCapture.weMeetGold(malformed[0],malformed[1]);throw new AssertionError("malformed gold offer accepted");}
            catch(IllegalArgumentException expected) {}
        }
        for(String name:Arrays.asList("SensoryStone","Bonfire"))
            check(LiveEventCapture.matches(LiveEventCapture.CONTINUES,name,"INTRO"),"later phases replaced intro "+name);
        check(LiveEventCapture.matches(LiveEventCapture.LEAVES,"SensoryStone","LEAVE"),"Sensory Stone reward exit missing");
        Cleric cleric=new Cleric();Map<String,Object> out=capture(cleric,0,1,2);
        check(map(out.get("details")).get("hpAmount0").equals(20),"public heal missing");
        check(!out.containsKey("unsupportedReason")&&!out.toString().contains("987"),"hidden field leaked");
        cleric.screenNum=99;out=capture(cleric,0);
        check("event_leave".equals(map(out.get("details")).get("mechanicalTransition")),"inherited proceed phase");
        check(capture(cleric,0,1).containsKey("unsupportedReason"),"multiple choices treated as forced");
        GoldenIdolEvent idol=new GoldenIdolEvent();idol.screenNum=1;out=capture(idol,0,1,2);indices(out,2,3,4);
        check(map(out.get("details")).get("hpAmount1").equals(8),"public trap amount missing");
        idol.screenNum=7;check(capture(idol,0).containsKey("unsupportedReason"),"unknown trap phase accepted");
        ShiningLight light=new ShiningLight();out=capture(light,1);indices(out,1);
        check(map(out.get("details")).get("hpAmount0").equals(16),"disabled upgrade slot changed click mapping");
        Designer designer=new Designer();out=capture(designer,0,1,2,3);indices(out,1,3,4,5);
        designer.adjustmentUpgradesOne=true;designer.cleanUpRemovesCards=true;
        indices(capture(designer,0,1,2,3),0,2,4,5);
        check("MAIN".equals(LiveEventCapture.phase(designer)),"inherited screenNum hid Designer curScreen");
        for(int stage=0;stage<5;++stage){CursedTome tome=new CursedTome();tome.screen=new String[]{"INTRO","PAGE_1","PAGE_2","PAGE_3","LAST_PAGE"}[stage];
            out=stage==0||stage==4?capture(tome,0,1):capture(tome,0);
            check(map(out.get("details")).get("eventData").equals(stage),"tome phase counter");
            if(stage==0)indices(out,0,1);else if(stage==4)indices(out,5,6);else indices(out,stage+1);
            check(!out.toString().contains("hiddenBook"),"hidden book captured");}
        out=capture(new KnowingSkull(),0,1,2,3);indices(out,2,0,1,3);
        check(map(out.get("details")).get("hpAmount0").equals(8),"skull repeated public cost missing");
        out=capture(new ScrapOoze(),0,1);check(map(out.get("details")).get("eventData").equals(2),"ooze public progress");
        out=capture(new DeadAdventurer(),0,1);check(map(out.get("details")).get("phase").equals(2)
                &&Boolean.TRUE.equals(map(out.get("details")).get("earnedGold"))&&!out.toString().contains("MUST_NOT_CAPTURE"),"adventurer public history/hidden rewards");
        for(Object event:Arrays.asList(new Lab(),new Bonfire()))check("event_continue".equals(map(capture(event,0).get("details")).get("mechanicalTransition")),"forced offer opening");
        Mushrooms mushrooms=new Mushrooms();mushrooms.screenNum=2;out=capture(mushrooms,0);
        check("event_continue".equals(map(out.get("details")).get("mechanicalTransition"))&&!out.containsKey("unsupportedReason"),"Mushrooms ambush Fight not forced");
        mushrooms.screenNum=1;check("event_leave".equals(map(capture(mushrooms,0).get("details")).get("mechanicalTransition")),"Mushrooms leave page changed");
        mushrooms.screenNum=3;check(capture(mushrooms,0).containsKey("unsupportedReason"),"unknown Mushrooms page accepted");
        TheJoust joust=new TheJoust();out=capture(joust,0);
        check("event_continue".equals(map(out.get("details")).get("mechanicalTransition"))&&!out.containsKey("unsupportedReason"),"Joust HALT Continue not forced");
        joust.screen="EXPLANATION";check(capture(joust,0,1).containsKey("unsupportedReason"),"Joust bet treated as forced");
        joust.screen="INTRO";check(capture(joust,0).containsKey("unsupportedReason"),"nonexistent Joust INTRO page accepted");
        check(capture(new Unknown(),0).containsKey("unsupportedReason"),"unknown class accepted as leave");
        for(String owner:Arrays.asList("DrugDealer","DesignerTransform"))check("transform".equals(LiveOocCapture.selectorType(false,false,false,Arrays.asList(owner),false,false).get("type")),"unflagged transform owner");
        check("remove".equals(LiveOocCapture.selectorType(false,false,false,Arrays.asList("NoteForYourself"),false,false).get("type")),"Note selector owner");
        System.out.println("LiveEventCaptureTest: public fields, phases, source-slot remaps, forced pages, hidden-state exclusion and selector owners passed");
    }
}
