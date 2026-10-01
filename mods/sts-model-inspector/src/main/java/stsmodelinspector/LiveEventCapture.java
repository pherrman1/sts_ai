package stsmodelinspector;

import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import java.lang.reflect.Field;
import java.util.*;

/** Public vanilla event pages; private pre-rolled rewards are never read. */
final class LiveEventCapture {
    private LiveEventCapture() {}
    static Object field(Object object, String name) throws ReflectiveOperationException {
        for (Class<?> type=object.getClass();type!=null;type=type.getSuperclass()) {
            try { Field f=type.getDeclaredField(name);f.setAccessible(true);return f.get(object); }
            catch(NoSuchFieldException ignored) {}
        }
        throw new NoSuchFieldException(name);
    }
    static String phase(Object event) throws ReflectiveOperationException {
        for(String name:Arrays.asList("curScreen","screen","screenNum")) {
            try { return String.valueOf(field(event,name)); } catch(NoSuchFieldException ignored) {}
        }
        return "unknown";
    }
    static final Map<String,String> DECISIONS=new LinkedHashMap<>();
    static final Map<String,String> LEAVES=new LinkedHashMap<>();
    static final Map<String,String> CONTINUES=new LinkedHashMap<>();
    static {
        phases(DECISIONS,"0","Cleric","Addict","DrugDealer","ForgottenAltar","Ghosts","GoldenIdolEvent","ScrapOoze","Vampires","MoaiHead","Nloth","Mushrooms");
        phases(DECISIONS,"INTRO","ShiningLight","GoldenWing","Beggar","MaskedBandits","MindBloom","TombRedMask","GoldShrine","Sssserpent","DeadAdventurer","WeMeetAgain");
        phases(DECISIONS,"1","Nest","WindingHalls");
        phases(DECISIONS,"MAIN","FaceTrader","Designer");
        phases(DECISIONS,"CHOICE","Falling");
        phases(DECISIONS,"ASK","KnowingSkull");
        phases(DECISIONS,"INTRO_2","SensoryStone");
        phases(DECISIONS,"INTRO","MysteriousSphere");
        phases(DECISIONS,"CHOOSE","NoteForYourself");
        phases(DECISIONS,"EXPLANATION","TheJoust");
        phases(DECISIONS,"FIGHT|POST_COMBAT","Colosseum");
        phases(DECISIONS,"INTRO|PAGE_1|PAGE_2|PAGE_3|LAST_PAGE","CursedTome");
        phases(LEAVES,"99","Cleric","ForgottenAltar");
        phases(LEAVES,"1","Addict","DrugDealer","MoaiHead","Nloth","Mushrooms","ScrapOoze","FountainOfCurseRemoval");
        phases(LEAVES,"1|2","Ghosts","Vampires");
        phases(LEAVES,"2","GoldenIdolEvent","Nest","WindingHalls","Duplicator");
        phases(LEAVES,"COMPLETE","ShiningLight","GoldShrine","UpgradeShrine","PurificationShrine","Transmogrifier","Bonfire","TheJoust","NoteForYourself","Lab","WeMeetAgain","KnowingSkull");
        phases(LEAVES,"RESULT","BigFish","LivingWall","TheMausoleum","TombRedMask","FaceTrader","Falling","WomanInBlue");
        phases(LEAVES,"LEAVE","Beggar","MindBloom","Colosseum","SecretPortal","SensoryStone");
        phases(LEAVES,"END","MaskedBandits","CursedTome","MysteriousSphere");
        phases(LEAVES,"MAP","GoldenWing");
        phases(LEAVES,"DISAGREE|COMPLETE","Sssserpent");
        phases(LEAVES,"DONE","Designer");
        phases(LEAVES,"ESCAPE|SUCCESS","DeadAdventurer");
        phases(LEAVES,"LEAVE","GremlinWheelGame");
        phases(LEAVES,"COMPLETE","GremlinMatchGame");
        phases(CONTINUES,"INTRO","FaceTrader","Designer","Falling","SensoryStone","NoteForYourself","Bonfire","TheJoust","Colosseum","Lab");
        phases(CONTINUES,"0","Nest","WindingHalls");
        phases(CONTINUES,"GAVE_MONEY","Beggar");
        phases(CONTINUES,"PURGE","GoldenWing");
        phases(CONTINUES,"PAID_1|PAID_2|PAID_3","MaskedBandits");
        phases(CONTINUES,"AGREE","Sssserpent");
        phases(CONTINUES,"INTRO_1","KnowingSkull");
        phases(CONTINUES,"PRE_JOUST|JOUST","TheJoust");
        phases(CONTINUES,"ACCEPT","SensoryStone");
        phases(CONTINUES,"INTRO|CHOOSE","Bonfire");
        phases(CONTINUES,"INTRO|COMPLETE|SPIN_READY","GremlinWheelGame");
        phases(CONTINUES,"FAIL","DeadAdventurer");
        phases(CONTINUES,"PRE_COMBAT","MysteriousSphere");
        phases(CONTINUES,"FIGHT","MindBloom");
        phases(CONTINUES,"ACCEPT","SecretPortal");
        phases(CONTINUES,"INTRO|RULE_EXPLANATION","GremlinMatchGame");
    }
    private static void phases(Map<String,String> table,String phase,String...classes) {
        for(String name:classes) {
            Set<String> merged=new LinkedHashSet<>();
            if(table.containsKey(name))merged.addAll(Arrays.asList(table.get(name).split("\\|")));
            merged.addAll(Arrays.asList(phase.split("\\|")));table.put(name,String.join("|",merged));
        }
    }
    static int weMeetGold(int offered,int held) {
        if(offered==0 && held<50)return -1;
        if(offered<50 || offered>150 || offered>held)throw new IllegalArgumentException("invalid We Meet Again gold offer");
        return offered;
    }
    static boolean matches(Map<String,String> table,String name,String phase) {
        String phases=table.get(name);return phases!=null && Arrays.asList(phases.split("\\|")).contains(phase);
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> map(Object o) { return (Map<String,Object>)o; }
    private static int integer(Object event,String name) throws ReflectiveOperationException {
        Object value=field(event,name);if(!(value instanceof Integer))throw new IllegalArgumentException(name);return (Integer)value;
    }
    private static void amount(Map<String,Object> d,Object e,String wire,String source) throws ReflectiveOperationException {
        d.put(wire,integer(e,source));
    }
    private static int deckIndex(Object card) {
        if(card==null)return -1;
        int index=AbstractDungeon.player.masterDeck.group.indexOf(card);
        if(index<0)throw new IllegalArgumentException("public event card absent from deck");return index;
    }
    static void capture(Map<String,Object> out,Object event,List<Object> options,List<Map<String,Object>> choices)
            throws ReflectiveOperationException {
        String name=event.getClass().getSimpleName(),phase=String.valueOf(map(out.get("event")).get("phase"));
        Map<String,Object> d=map(out.get("details"));
        if(matches(LEAVES,name,phase)||matches(CONTINUES,name,phase)) {
            if(options.size()!=1||!Integer.valueOf(0).equals(map(options.get(0)).get("index"))
                    ||!Boolean.FALSE.equals(map(options.get(0)).get("disabled")))return;
            d.put("mechanicalTransition",matches(LEAVES,name,phase)?"event_leave":"event_continue");
            d.put("eventContract","vanilla_v1");
            out.remove("unsupportedReason");return;
        }
        boolean goldenTrap="GoldenIdolEvent".equals(name)&&"1".equals(phase);
        if(!matches(DECISIONS,name,phase)&&!goldenTrap)return;
        switch(name) {
            case "Cleric": amount(d,event,"hpAmount0","healAmt");break;
            case "ShiningLight": amount(d,event,"hpAmount0","damage");break;
            case "GoldenIdolEvent": amount(d,event,"hpAmount0","damage");amount(d,event,"hpAmount1","maxHpLoss");break;
            case "ForgottenAltar":case "Ghosts":amount(d,event,"hpAmount0","hpLoss");break;
            case "Vampires":amount(d,event,"hpAmount0","maxHpLoss");break;
            case "MoaiHead":amount(d,event,"hpAmount0","hpAmt");break;
            case "WindingHalls":amount(d,event,"hpAmount0","hpAmt");amount(d,event,"hpAmount1","healAmt");amount(d,event,"hpAmount2","maxHPAmt");break;
            case "FaceTrader":amount(d,event,"hpAmount0","damage");amount(d,event,"gold","goldReward");break;
            case "Falling":
                for(String kind:Arrays.asList("skill","power","attack"))d.put(kind+"CardDeckIdx",deckIndex(field(event,kind+"Card")));
                break;
            case "Nloth":
                d.put("relicIdx0",AbstractDungeon.player.relics.indexOf(field(event,"choice1")));
                d.put("relicIdx1",AbstractDungeon.player.relics.indexOf(field(event,"choice2")));break;
            case "WeMeetAgain":
                d.put("potionIdx",AbstractDungeon.player.potions.indexOf(field(event,"potionOption")));
                d.put("cardIdx",deckIndex(field(event,"cardOption")));
                d.put("gold",weMeetGold(integer(event,"goldAmount"),AbstractDungeon.player.gold));break;
            case "Designer":d.put("upgradeOne",field(event,"adjustmentUpgradesOne"));d.put("cleanUpIsRemoveCard",field(event,"cleanUpRemovesCards"));break;
            case "KnowingSkull":
                amount(d,event,"hpAmount0","goldCost");amount(d,event,"hpAmount1","cardCost");amount(d,event,"hpAmount2","potionCost");amount(d,event,"leaveCost","leaveCost");break;
            case "ScrapOoze":
                amount(d,event,"hpAmount0","dmg");amount(d,event,"relicObtainChance","relicObtainChance");
                d.put("eventData",(integer(event,"relicObtainChance")-25)/10);break;
            case "DeadAdventurer":
                amount(d,event,"phase","numRewards");amount(d,event,"encounterChance","encounterChance");amount(d,event,"publicEnemy","enemy");
                d.put("earnedGold",integer(event,"goldRewardMetric")>0);d.put("earnedRelic",field(event,"relicRewardMetric")!=null);break;
            case "Colosseum":d.put("eventData","POST_COMBAT".equals(phase)?1:0);break;
            case "CursedTome":d.put("eventData",Arrays.asList("INTRO","PAGE_1","PAGE_2","PAGE_3","LAST_PAGE").indexOf(phase));break;
            case "NoteForYourself":d.put("noteForYourselfCard",LiveOocCapture.card((AbstractCard)field(event,"obtainCard")));break;
            default:break;
        }
        for(int i=0;i<options.size();++i) {
            int source=(Integer)map(options.get(i)).get("index"),nativeIndex=source;
            if(goldenTrap)nativeIndex+=2;
            if("Vampires".equals(name))nativeIndex=source==0?1:source==1&&Boolean.TRUE.equals(field(event,"hasVial"))?0:2;
            if("MindBloom".equals(name)&&source==2&&AbstractDungeon.floorNum>40)nativeIndex=3;
            if("TombRedMask".equals(name)&&source==1&&AbstractDungeon.player.hasRelic("Red Mask"))nativeIndex=2;
            if("Falling".equals(name)&&Integer.valueOf(-1).equals(d.get("skillCardDeckIdx"))&&Integer.valueOf(-1).equals(d.get("powerCardDeckIdx"))&&Integer.valueOf(-1).equals(d.get("attackCardDeckIdx")))nativeIndex=3;
            if("Designer".equals(name))nativeIndex=source==0?(Boolean.TRUE.equals(d.get("upgradeOne"))?0:1):source==1?(Boolean.TRUE.equals(d.get("cleanUpIsRemoveCard"))?2:3):source==2?4:5;
            if("CursedTome".equals(name)) {int stage=(Integer)d.get("eventData");if(stage>0)nativeIndex=stage+1+source;}
            if("KnowingSkull".equals(name)) {
                nativeIndex=new int[]{2,0,1,3}[source];
            }
            map(choices.get(i).get("nativeAction")).put("index",nativeIndex);
        }
        d.put("eventContract","vanilla_v1");
        out.remove("unsupportedReason");
    }
}
