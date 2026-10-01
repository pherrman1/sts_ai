package stsmodelinspector;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** Derive only facts retained in vanilla public metrics, never live queues or RNG. */
final class PublicHistoryRecovery {
    private PublicHistoryRecovery() {}
    private static final class Encounter {
        final int act;
        final String kind, nativeId;
        Encounter(int act, String kind, String nativeId) {
            this.act=act; this.kind=kind; this.nativeId=nativeId;
        }
    }
    private static final Map<String,Encounter> ENCOUNTERS = new LinkedHashMap<>();
    private static void aliases(int act, String kind, String... pairs) {
        for (int i=0;i<pairs.length;i+=2)
            ENCOUNTERS.put(pairs[i],new Encounter(act,kind,pairs[i+1]));
    }
    static {
        // These are MonsterHelper's stable metric keys, not localized monster names.
        aliases(1,"NORMAL_QUEUE","Cultist","CULTIST","Jaw Worm","JAW_WORM","2 Louse","TWO_LOUSE",
                "Small Slimes","SMALL_SLIMES","Blue Slaver","BLUE_SLAVER","Gremlin Gang","GREMLIN_GANG",
                "Looter","LOOTER","Large Slime","LARGE_SLIME","Lots of Slimes","LOTS_OF_SLIMES",
                "Exordium Thugs","EXORDIUM_THUGS","Exordium Wildlife","EXORDIUM_WILDLIFE",
                "Red Slaver","RED_SLAVER","3 Louse","THREE_LOUSE","2 Fungi Beasts","TWO_FUNGI_BEASTS");
        aliases(1,"ELITE_QUEUE","Gremlin Nob","GREMLIN_NOB","Lagavulin","LAGAVULIN","3 Sentries","THREE_SENTRIES");
        aliases(1,"BOSS","Slime Boss","SLIME_BOSS","The Guardian","THE_GUARDIAN","Hexaghost","HEXAGHOST");
        aliases(2,"NORMAL_QUEUE","Spheric Guardian","SPHERIC_GUARDIAN","Chosen","CHOSEN",
                "Shell Parasite","SHELL_PARASITE","3 Byrds","THREE_BYRDS","2 Thieves","TWO_THIEVES",
                "Chosen and Byrds","CHOSEN_AND_BYRDS","Sentry and Sphere","SENTRY_AND_SPHERE",
                "Snake Plant","SNAKE_PLANT","Snecko","SNECKO","Centurion and Healer","CENTURION_AND_HEALER",
                "Cultist and Chosen","CULTIST_AND_CHOSEN","3 Cultists","THREE_CULTIST",
                "Shelled Parasite and Fungi","SHELLED_PARASITE_AND_FUNGI");
        aliases(2,"ELITE_QUEUE","Gremlin Leader","GREMLIN_LEADER","Slavers","SLAVERS","Book of Stabbing","BOOK_OF_STABBING");
        aliases(2,"BOSS","Automaton","AUTOMATON","Collector","COLLECTOR","Champ","CHAMP");
        aliases(3,"NORMAL_QUEUE","3 Darklings","THREE_DARKLINGS","Orb Walker","ORB_WALKER",
                "3 Shapes","THREE_SHAPES","Spire Growth","SPIRE_GROWTH","Transient","TRANSIENT",
                "4 Shapes","FOUR_SHAPES","Maw","MAW","Sphere and 2 Shapes","SPHERE_AND_TWO_SHAPES",
                "Jaw Worm Horde","JAW_WORM_HORDE","Writhing Mass","WRITHING_MASS");
        aliases(3,"ELITE_QUEUE","Giant Head","GIANT_HEAD","Nemesis","NEMESIS","Reptomancer","REPTOMANCER");
        aliases(3,"BOSS","Awakened One","AWAKENED_ONE","Time Eater","TIME_EATER","Donu and Deca","DONU_AND_DECA");
        aliases(1,"FIXED_EVENT","Lagavulin Event","LAGAVULIN_EVENT","The Mushroom Lair","MUSHROOMS_EVENT");
        aliases(2,"FIXED_EVENT","Colosseum Slavers","COLOSSEUM_EVENT_SLAVERS","Colosseum Nobs","COLOSSEUM_EVENT_NOBS",
                "Masked Bandits","MASKED_BANDITS_EVENT");
        aliases(3,"FIXED_EVENT","Mysterious Sphere","MYSTERIOUS_SPHERE_EVENT");
    }
    static Integer floor(Object value, int maximum) {
        if (!(value instanceof Number)) return null;
        Number number=(Number)value;
        int floor=number.intValue();
        return floor>=0 && floor<=maximum && number.doubleValue()==floor ? floor : null;
    }
    private static Map<?,?> record(Object raw) { return raw instanceof Map ? (Map<?,?>)raw : null; }

    /** Null means insufficient/contradictory metrics; never return a guessed prefix. */
    static List<Map<String,Object>> combats(QuestionRoomHistory path, List<?> metrics, int act, int currentFloor) {
        if (!path.complete || metrics==null || act<1 || act>3 || metrics.size()>1000) return null;
        int start=act==1?0:act==2?17:34, previous=-1;
        List<Map<String,Object>> result=new ArrayList<>();
        for(Object raw:metrics) {
            Map<?,?> metric=record(raw);
            Integer f=metric==null?null:floor(metric.get("floor"),currentFloor);
            if(f==null || f<1 || f<previous || f>path.rooms.size()) return null;
            previous=f;
            if(f<=start) continue;
            Object key=metric.get("enemies");
            Encounter encounter=key instanceof String?ENCOUNTERS.get(key):null;
            if(encounter==null || encounter.act!=act) return null;
            String room=path.rooms.get(f-1), kind=encounter.kind, nativeId=encounter.nativeId;
            String expected="NORMAL_QUEUE".equals(kind)?"MONSTER":"ELITE_QUEUE".equals(kind)?"ELITE"
                    :"BOSS".equals(kind)?"BOSS":"EVENT";
            if(!room.equals(expected)) return null;
            if(!result.isEmpty() && f.equals(result.get(result.size()-1).get("floor"))) {
                if(act!=2 || !"COLOSSEUM_EVENT_SLAVERS".equals(result.get(result.size()-1).get("encounter"))
                        || !"COLOSSEUM_EVENT_NOBS".equals(nativeId)) return null;
            } else if("COLOSSEUM_EVENT_NOBS".equals(nativeId)) return null;
            Map<String,Object> entry=new LinkedHashMap<>();
            entry.put("floor",f);entry.put("kind",kind);entry.put("encounter",nativeId);result.add(entry);
        }
        // Every resolved ordinary/elite/boss room in the completed prefix must
        // have its combat metric. The current room may still be pre-combat.
        for(int f=start+1;f<currentFloor;++f) {
            String room=path.rooms.get(f-1);
            if(Arrays.asList("MONSTER","ELITE","BOSS").contains(room)) {
                boolean found=false;
                for(Map<String,Object> entry:result) found|=Integer.valueOf(f).equals(entry.get("floor"));
                if(!found) return null;
            }
        }
        return result;
    }

    /** Known boss offers are useful even when the global offer ledger is incomplete. */
    static List<String> bossOffers(List<?> metrics) {
        LinkedHashSet<String> result=new LinkedHashSet<>();
        if(metrics==null) return new ArrayList<>();
        if(metrics.size()>3) throw new IllegalArgumentException("boss offer history too large");
        for(Object raw:metrics) {
            Map<?,?> entry=record(raw);
            if(entry==null || !(entry.get("not_picked") instanceof List))
                throw new IllegalArgumentException("invalid boss offer metric");
            List<?> skipped=(List<?>)entry.get("not_picked");
            int count=skipped.size()+(entry.containsKey("picked")?1:0);
            if(count<1 || count>3) throw new IllegalArgumentException("invalid boss offer count");
            List<Object> offers=new ArrayList<>(skipped);
            if(entry.containsKey("picked")) offers.add(entry.get("picked"));
            LinkedHashSet<String> local=new LinkedHashSet<>();
            for(Object offer:offers) {
                if(!(offer instanceof String) || ((String)offer).isEmpty() || !local.add((String)offer))
                    throw new IllegalArgumentException("invalid boss offer identity");
                result.add((String)offer);
            }
        }
        return new ArrayList<>(result);
    }

    /** Attach ownership only when the complete metric chronology agrees with current ownership. */
    static void annotateJuzu(List<Map<String,Object>> outcomes, List<?> obtained, List<?> events,
            boolean currentlyOwned, int currentFloor) {
        TreeMap<Integer,Boolean> changes=ownershipChanges("Juzu Bracelet",obtained,events,currentlyOwned,currentFloor);
        if(changes==null) return;
        for(Map<String,Object> outcome:outcomes) {
            int f=((Number)outcome.get("floor")).intValue();
            Map.Entry<Integer,Boolean> before=changes.lowerEntry(f);
            outcome.put("juzuOwnedAtEntry",before!=null && before.getValue());
        }
    }

    /** Tiny Chest starts at zero onEquip and increments on every owned '?' across acts. */
    static void annotateTinyChest(QuestionRoomHistory history,List<?> obtained,List<?> events,
            boolean currentlyOwned,int currentCounter,int currentFloor) {
        if(!history.complete) return;
        TreeMap<Integer,Boolean> changes=ownershipChanges("Tiny Chest",obtained,events,currentlyOwned,currentFloor);
        if(changes==null) return;
        Map<Integer,Map<String,Object>> questions=new LinkedHashMap<>();
        for(Map<String,Object> entry:history.allOutcomes) questions.put(((Number)entry.get("floor")).intValue(),entry);
        Map<Integer,Boolean> forced=new LinkedHashMap<>();
        boolean owned=false; int counter=0;
        for(int f=0;f<=currentFloor;++f) {
            Map<String,Object> entry=questions.get(f);
            if(entry!=null) {
                boolean force=owned && ++counter==4;
                if(force) counter=0;
                if(force && !"TREASURE".equals(entry.get("outcome"))) return;
                forced.put(f,force);
            }
            Boolean after=changes.get(f);
            if(after!=null) { owned=after; if(owned)counter=0; }
        }
        if(currentlyOwned && (currentCounter<0 || currentCounter>3 || currentCounter!=counter)) return;
        for(Map<String,Object> entry:history.allOutcomes)
            entry.put("tinyChestForced",forced.get(((Number)entry.get("floor")).intValue()));
    }

    private static TreeMap<Integer,Boolean> ownershipChanges(String relic,List<?> obtained,List<?> events,
            boolean currentlyOwned,int currentFloor) {
        if(obtained==null || events==null) return null;
        TreeMap<Integer,Boolean> changes=new TreeMap<>();
        for(Object raw:obtained) {
            Map<?,?> entry=record(raw);
            Integer f=entry==null?null:floor(entry.get("floor"),currentFloor);
            if(f==null || !(entry.get("key") instanceof String)) return null;
            if(relic.equals(entry.get("key")) && !change(changes,f,true)) return null;
        }
        for(Object raw:events) {
            Map<?,?> entry=record(raw);
            Integer f=entry==null?null:floor(entry.get("floor"),currentFloor);
            if(f==null) return null;
            for(String name:Arrays.asList("relics_obtained","relics_lost")) {
                Object values=entry.get(name);
                if(values==null) continue;
                if(!(values instanceof List)) return null;
                for(Object value:(List<?>)values) {
                    if(!(value instanceof String)) return null;
                    if(relic.equals(value) && !change(changes,f,"relics_obtained".equals(name))) return null;
                }
            }
        }
        boolean owned=false;
        for(boolean next:changes.values()) { if(next==owned)return null; owned=next; }
        return owned==currentlyOwned?changes:null;
    }
    private static boolean change(TreeMap<Integer,Boolean> changes,int floor,boolean owned) {
        Boolean old=changes.get(floor);
        if(old!=null && old!=owned) return false;
        changes.put(floor,owned);return true;
    }
}
