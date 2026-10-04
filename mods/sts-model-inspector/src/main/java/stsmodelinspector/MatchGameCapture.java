package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.cards.CardGroup;
import com.megacrit.cardcrawl.events.shrines.GremlinMatchGame;
import java.util.*;

/** Remembers only cards actually shown face up; never reads a face-down card ID. */
public final class MatchGameCapture {
    private MatchGameCapture() {}
    private static final Memory memory=new Memory();
    static final class PublicSlot {
        final int slot;final String uuid;final boolean faceUp;final Map<String,Object> card;
        PublicSlot(int slot,String uuid,boolean faceUp,Map<String,Object> card) {
            this.slot=slot;this.uuid=uuid;this.faceUp=faceUp;this.card=card;
        }
    }
    static final class Memory {
        Object owner;boolean complete;String error;
        final Map<Integer,String> identities=new HashMap<>();
        final Map<Integer,Map<String,Object>> seen=new HashMap<>();
        void observe(Object current,Map<Integer,String> physical,List<PublicSlot> visible,int attempts) {
            if(owner!=current) {owner=current;complete=attempts==5&&visible.size()==12;error=null;identities.clear();seen.clear();identities.putAll(physical);}
            if(error!=null)return;
            if(physical.size()!=12||!physical.equals(identities)||new HashSet<>(physical.values()).size()!=12) {error="MATCH_BOARD_IDENTITY_UNQUALIFIED";return;}
            for(int i=0;i<12;++i)if(physical.get(i)==null||physical.get(i).isEmpty()) {error="MATCH_BOARD_IDENTITY_UNQUALIFIED";return;}
            Set<Integer> slots=new HashSet<>();
            for(PublicSlot card:visible) {
                if(card.slot<0||card.slot>=12||!Objects.equals(physical.get(card.slot),card.uuid)||!slots.add(card.slot)) {error="MATCH_BOARD_IDENTITY_UNQUALIFIED";return;}
                if(card.faceUp) {
                    if(card.card==null) {error="MATCH_PUBLIC_CARD_MISSING";return;}
                    if(seen.containsKey(card.slot)&&!seen.get(card.slot).equals(card.card)) {error="MATCH_PUBLIC_CARD_CHANGED";return;}
                    seen.put(card.slot,new LinkedHashMap<>(card.card));
                } else if(card.card!=null) {error="MATCH_HIDDEN_CARD_LEAK";return;}
            }
        }
        List<Object> board(List<PublicSlot> visible) {
            Map<Integer,PublicSlot> alive=new HashMap<>();for(PublicSlot card:visible)alive.put(card.slot,card);
            List<Object> result=new ArrayList<>();
            for(int i=0;i<12;++i) {
                PublicSlot current=alive.get(i);
                String state=current==null?"matched":current.faceUp?"face_up":seen.containsKey(i)?"seen":"unseen";
                Map<String,Object> row=obj("slot",i,"uuid",identities.get(i),"state",state);
                if(seen.containsKey(i))row.put("card",new LinkedHashMap<>(seen.get(i)));
                result.add(row);
            }
            return result;
        }
    }
    @SpirePatch(clz=GremlinMatchGame.class,method="update")
    public static final class ObserveFlips {
        @SpirePostfixPatch public static void after(GremlinMatchGame __instance) {
            try { if("PLAY".equals(LiveEventCapture.phase(__instance)))observe(__instance); }
            catch(ReflectiveOperationException|RuntimeException failure) {memory.error="MATCH_CAPTURE_UNQUALIFIED";}
        }
    }
    @SuppressWarnings("unchecked") private static List<PublicSlot> observe(Object event)throws ReflectiveOperationException {
        Map<UUID,Integer> positions=(Map<UUID,Integer>)Class.forName("mcpthespire.patches.GremlinMatchGamePatch").getField("cardPositions").get(null);
        if(positions==null)throw new IllegalArgumentException("match positions absent");
        Map<Integer,String> physical=new HashMap<>();
        for(Map.Entry<UUID,Integer> entry:positions.entrySet()) {
            if(physical.put(entry.getValue(),entry.getKey().toString())!=null)throw new IllegalArgumentException("duplicate match position");
        }
        List<PublicSlot> visible=new ArrayList<>();
        for(AbstractCard card:((CardGroup)LiveEventCapture.field(event,"cards")).group) {
            Integer slot=positions.get(card.uuid);if(slot==null)throw new IllegalArgumentException("unknown match UUID");
            // isFlipped means the back is showing. Keep this guard outside
            // card() so no hidden identity/upgrades/misc are even inspected.
            visible.add(new PublicSlot(slot,card.uuid.toString(),!card.isFlipped,
                    card.isFlipped?null:LiveOocCapture.card(card)));
        }
        memory.observe(event,physical,visible,(Integer)LiveEventCapture.field(event,"attemptCount"));return visible;
    }
    @SuppressWarnings("unchecked") static void capture(Map<String,Object> out,Object event,List<Map<String,Object>> choices,List<?> labels)
            throws ReflectiveOperationException {
        if(!"GremlinMatchGame".equals(event.getClass().getSimpleName())||!"PLAY".equals(LiveEventCapture.phase(event)))return;
        List<PublicSlot> visible=observe(event);
        if(memory.error!=null) {out.put("unsupportedReason",memory.error);return;}
        if(((Number)LiveEventCapture.field(event,"waitTimer")).floatValue()>0f
                ||Boolean.TRUE.equals(LiveEventCapture.field(event,"gameDone"))) {out.put("unsupportedReason","MATCH_ANIMATION_RESOLVING");return;}
        int count=0,faceUp=0;for(PublicSlot slot:visible)if(slot.faceUp)++faceUp;else ++count;
        if(faceUp>1||count!=labels.size()||count==0) {out.put("unsupportedReason","MATCH_CHOICE_MAPPING_UNQUALIFIED");return;}
        Map<String,Object> details=(Map<String,Object>)out.get("details");
        details.put("eventContract","vanilla_v1");details.put("board",memory.board(visible));
        details.put("eventData",LiveEventCapture.field(event,"attemptCount"));
        details.put("publicMemoryComplete",memory.complete);
        List<Object> options=new ArrayList<>();choices.clear();int occurrence=0;
        for(PublicSlot slot:visible)if(!slot.faceUp) {
            if(!("card"+slot.slot).equals(labels.get(occurrence)))throw new IllegalArgumentException("match label/physical slot mismatch");
            options.add(obj("index",slot.slot,"disabled",false));
            choices.add(obj("uuid",slot.uuid,"nativeAction",obj("kind","option","index",slot.slot,"group",0),
                    "liveAction",obj("kind","choose","choiceIndex",++occurrence)));
        }
        ((Map<String,Object>)out.get("event")).put("options",options);out.remove("unsupportedReason");
    }
    static Map<String,Object> obj(Object...pairs){Map<String,Object> result=new LinkedHashMap<>();for(int i=0;i<pairs.length;i+=2)result.put((String)pairs[i],pairs[i+1]);return result;}
}
