package stsmodelinspector;

import java.util.HashMap;
import java.util.Map;

/** Pure projection tests: no game, rendering context, RNG, or save is initialized. */
public final class LiveOocCaptureTest {
    private static final class FakeNeowReward {
        private final Object type;
        private final boolean activated;
        FakeNeowReward(Object type, boolean activated) { this.type = type; this.activated = activated; }
    }
    private static Map<String,Object> obj(Object... values) {
        Map<String,Object> out = new HashMap<>();
        for (int i = 0; i < values.length; i += 2) out.put((String)values[i], values[i + 1]);
        return out;
    }
    private static void check(String id, int counter, boolean usedUp, int expected, String reason) {
        Map<String,Object> state = new HashMap<>();
        int actual = LiveOocCapture.nativeRelicData(id, counter, usedUp, state);
        if (actual != expected || (reason == null ? state.containsKey("unsupportedReason")
                : !reason.equals(state.get("unsupportedReason"))))
            throw new AssertionError(id + ": " + actual + " " + state);
    }
    public static void main(String[] args) throws Exception {
        Map<String,Object> parent=obj("potions",new java.util.ArrayList<Object>());
        if(LiveOocCapture.captureParentRewards(parent,java.util.Arrays.asList(obj("type","POTION","potion","SpeedPotion")))!=null
                || !Boolean.TRUE.equals(parent.get("parentPotionRewards"))
                || !parent.get("potions").equals(java.util.Arrays.asList("SpeedPotion"))) throw new AssertionError("parent potion lost");
        Map<String,Object> known=obj("potions",new java.util.ArrayList<Object>(),"gold",new java.util.ArrayList<Object>(),
                "relics",new java.util.ArrayList<Object>());
        if(LiveOocCapture.captureParentRewards(known,java.util.Arrays.asList(
                obj("type","GOLD","gold",42),obj("type","RELIC","identity","paired","relic","Anchor"),
                obj("type","RELIC","identity","other","relic","Vajra"),
                obj("type","SAPPHIRE_KEY","linkedRelicIdentity","paired")))!=null
                ||!Boolean.TRUE.equals(known.get("parentKnownRewards"))
                ||!known.get("relics").equals(java.util.Arrays.asList("Vajra","Anchor"))
                ||!Integer.valueOf(1).equals(known.get("sapphireRelicIndex")))
            throw new AssertionError("known parent rewards or sapphire pair lost");
        try {
            LiveOocCapture.captureParentRewards(known,java.util.Arrays.asList(obj("type","SAPPHIRE_KEY","linkedRelicIdentity","absent")));
            throw new AssertionError("absent sapphire pair accepted");
        }catch(IllegalArgumentException expected) {}
        Map<String,Object> unknown=obj("potions",new java.util.ArrayList<Object>());
        if(LiveOocCapture.captureParentRewards(unknown,java.util.Arrays.asList(obj("type","UNKNOWN")))==null)
            throw new AssertionError("unknown sibling accepted");
        Map<String,Object> multi=obj("potions",new java.util.ArrayList<Object>());
        if(LiveOocCapture.captureParentRewards(multi,java.util.Arrays.asList(
                obj("type","CARD"),obj("type","CARD"),obj("type","POTION","potion","SpeedPotion")))!=null
                || !Integer.valueOf(2).equals(multi.get("parentUnrevealedCardRewards"))
                || !Boolean.TRUE.equals(multi.get("parentPotionRewards")))throw new AssertionError("multiple reward continuation lost");
        if(multi.containsKey("cardRewards"))throw new AssertionError("unopened sibling cards leaked");
        Object skipPlayer=new Object(),reward=new Object(),other=new Object();
        CardRewardSkipObserver.Ledger ledger=new CardRewardSkipObserver.Ledger();ledger.bind(skipPlayer,1);ledger.skip(reward);
        if(!ledger.contains(reward) || ledger.contains(other))throw new AssertionError("skip occurrence identity lost");
        ledger.reopen(reward);if(ledger.contains(reward))throw new AssertionError("reopened offer remains declined");
        ledger.skip(reward);ledger.bind(skipPlayer,2);if(ledger.contains(reward))throw new AssertionError("skip leaked floor");
        ledger.skip(reward);ledger.bind(new Object(),2);if(ledger.contains(reward))throw new AssertionError("skip leaked run");
        javassist.ClassPool skipPool=new javassist.ClassPool(true);
        skipPool.appendClassPath(new javassist.LoaderClassPath(LiveOocCaptureTest.class.getClassLoader()));
        javassist.CtClass skip=skipPool.get("com.megacrit.cardcrawl.ui.buttons.SkipCardButton");
        CardRewardSkipObserver.Skip.raw(skip.getDeclaredMethod("update"));skip.toBytecode();skip.detach();
        javassist.CtClass rewardScreen=skipPool.get("com.megacrit.cardcrawl.screens.CardRewardScreen");
        CardRewardSkipObserver.Open.raw(rewardScreen.getDeclaredMethod("open",new javassist.CtClass[]{
            skipPool.get("java.util.ArrayList"),skipPool.get("com.megacrit.cardcrawl.rewards.RewardItem"),skipPool.get("java.lang.String")}));
        rewardScreen.toBytecode();rewardScreen.detach();
        String mcpJar=System.getProperty("sts.mcp.jar");
        if(mcpJar!=null) {
            skipPool.appendClassPath(mcpJar);
            javassist.CtClass mcp=skipPool.get("mcpthespire.ChoiceScreenUtils");
            javassist.CtMethod method=mcp.getDeclaredMethod("pressCancelButton",new javassist.CtClass[0]);
            method.insertBefore("{ stsmodelinspector.CardRewardSkipObserver.McpSkip.prefix(); }");
            mcp.toBytecode();mcp.detach();
        }
        if (!"Match and Keep".equals(LiveOocCapture.canonicalEventId("Match and Keep!"))
                || !"Sensory Stone".equals(LiveOocCapture.canonicalEventId("SensoryStone")))
            throw new AssertionError("Match canonical ID");
        // Overnight 2026-10-19: the capture after [Play] lands in the 2 s bounce.
        if(!LiveOocCapture.wheelSpinReady(true,1,"INTRO",true,false,1.85f)
                || !LiveOocCapture.wheelSpinReady(true,1,"INTRO",true,false,0f))
            throw new AssertionError("Wheel spin window rejected");
        if(LiveOocCapture.wheelSpinReady(true,1,"INTRO",true,true,0f)
                || LiveOocCapture.wheelSpinReady(true,1,"INTRO",false,false,1f)
                || LiveOocCapture.wheelSpinReady(false,1,"INTRO",true,false,0f)
                || LiveOocCapture.wheelSpinReady(true,1,"COMPLETE",true,false,0f)
                || LiveOocCapture.wheelSpinReady(true,1,"INTRO",true,false,-1f))
            throw new AssertionError("Wheel spin qualification too wide");
        for(int defect=-1;defect<5;++defect) {
            Map<String,Object> state=obj("screen_type","CHEST","ready_for_command",defect!=0,
                    "can_cancel",defect==1,"can_proceed",defect!=2,"choice_list",java.util.Arrays.asList("open"));
            Map<String,Object> out=obj("mcpState",state);
            java.util.List<Map<String,Object>> choices=new java.util.ArrayList<>();
            boolean accepted=LiveOocCapture.captureBossChestReveal(out,choices,java.util.Arrays.asList("open"),
                    defect==3?"SmallChest":"BossChest",defect==4?4:2);
            if(accepted!=(defect==-1))throw new AssertionError("boss reveal qualification "+defect);
            if(accepted && (choices.size()!=2 || !"proceed".equals(((Map<?,?>)choices.get(1).get("liveAction")).get("kind"))
                    || !"boss_chest_reveal".equals(((Map<?,?>)out.get("details")).get("mechanicalTransition"))))
                throw new AssertionError("boss reveal hides real skip choice");
        }
        for (int defect=-1; defect<9; ++defect) {
            Map<String,Object> state=obj("screen_type","GRID","ready_for_command",defect!=0,
                    "can_cancel",defect!=1,"can_proceed",defect!=2);
            java.util.List<Object> targets=new java.util.ArrayList<>();
            targets.add(obj("deckIndex",2,"uuid","physical-2","card",obj("id","Strike_R")));
            targets.add(defect==3?targets.get(0):obj("deckIndex",4,"uuid","physical-4","card",obj("id","Bash")));
            Map<String,Object> out=obj("mcpState",state);
            java.util.List<Map<String,Object>> choices=new java.util.ArrayList<>();
            boolean accepted=LiveOocCapture.captureSelectorPreview(out,choices,
                    defect==4?java.util.Arrays.asList("unexpected"):java.util.Collections.emptyList(),targets,
                    defect==5?"duplicate":"upgrade",defect==6?3:4,defect==7?2:1,defect==8?1:0);
            if(accepted!=(defect==-1))throw new AssertionError("preview qualification "+defect);
            if(accepted && (choices.size()!=2 || !"proceed".equals(((Map<?,?>)choices.get(0).get("liveAction")).get("kind"))
                    || !"cancel".equals(((Map<?,?>)choices.get(1).get("liveAction")).get("kind"))
                    || !Integer.valueOf(4).equals(((Map<?,?>)out.get("details")).get("previewDeckIndex"))))
                throw new AssertionError("preview mutation identity/buttons");
            if(!accepted&&!choices.isEmpty())throw new AssertionError("partial preview choices");
        }
        {
            Map<String,Object> out=obj("mcpState",obj("screen_type","GRID","ready_for_command",true,
                    "can_cancel",true,"can_proceed",true));
            if(!LiveOocCapture.captureSelectorPreview(out,new java.util.ArrayList<Map<String,Object>>(),
                    java.util.Collections.emptyList(),java.util.Arrays.<Object>asList(obj("deckIndex",0,
                    "uuid","offering","card",obj("id","Bash"))),"bonfire",0,1,0))
                throw new AssertionError("Bonfire purge preview loses sacrifice semantics");
        }
        for(int variant=0;variant<5;++variant) {
            java.util.List<Map<String,Object>> discards=new java.util.ArrayList<>();
            LiveOocCapture.capturePotionDiscards(discards,java.util.Arrays.asList("Fire Potion",
                    variant==1?"Potion Slot":"Block Potion","Potion Slot"),variant==4?3:2,
                    variant!=2,variant==3);
            if(discards.size()!=(variant==0?2:0))throw new AssertionError("potion discard gate "+variant);
            if(variant==0 && (!Integer.valueOf(1).equals(((Map<?,?>)discards.get(1).get("nativeAction")).get("index"))
                    || !Integer.valueOf(2).equals(((Map<?,?>)discards.get(1).get("liveAction")).get("potionSlot"))))
                throw new AssertionError("potion discard physical slot mapping");
        }
        for(int variant=0;variant<3;++variant) {
            java.util.List<Map<String,Object>> choices=new java.util.ArrayList<>();
            LiveOocCapture.captureShopPotionChoice(choices,
                    java.util.Arrays.asList("card", "relic", "potion"), 2, 1,
                    variant!=1, variant==2);
            if(choices.size()!=(variant==0?1:0))throw new AssertionError("shop potion capacity/Sozu gate");
            if(variant==0 && (!Integer.valueOf(3).equals(((Map<?,?>)choices.get(0).get("liveAction")).get("choiceIndex"))
                    || !Integer.valueOf(1).equals(((Map<?,?>)choices.get(0).get("nativeAction")).get("index"))))
                throw new AssertionError("shop potion physical choice index shifted");
        }
        // Problem 79: a Courier replacement inherits the bought card's slot by
        // list index, also after an earlier non-Courier purchase shifted the list.
        Object a=new Object(),b=new Object(),c=new Object(),d=new Object(),e=new Object(),x=new Object(),y=new Object();
        Map<Object,Integer> shopSlots=new java.util.IdentityHashMap<>();
        shopSlots.put(a,0);shopSlots.put(b,1);shopSlots.put(c,2);shopSlots.put(d,3);shopSlots.put(e,4);
        if(!Integer.valueOf(1).equals(LiveOocCapture.replacementSlot(java.util.Arrays.asList(a,x,c,d,e),
                java.util.Arrays.asList(a,b,c,d,e),shopSlots,x)))throw new AssertionError("Courier replacement slot");
        if(!Integer.valueOf(2).equals(LiveOocCapture.replacementSlot(java.util.Arrays.asList(b,y,d,e),
                java.util.Arrays.asList(b,c,d,e),shopSlots,y)))throw new AssertionError("Courier slot after a removal");
        if(LiveOocCapture.replacementSlot(java.util.Arrays.asList(a,b,c,d,e),java.util.Arrays.asList(a,b,c,d,e),shopSlots,x)!=null
                || LiveOocCapture.replacementSlot(java.util.Arrays.asList(x,a,c,d,e),java.util.Arrays.asList(a,b,c,d,e),shopSlots,x)!=null
                || LiveOocCapture.replacementSlot(java.util.Arrays.asList(a,c,d,e,x),java.util.Arrays.asList(a,c,d,e),shopSlots,x)!=null)
            throw new AssertionError("unrepresented shop replacement accepted");
        java.util.List<Object> libraryCards=new java.util.ArrayList<>();
        java.util.List<String> libraryLabels=new java.util.ArrayList<>();
        for(int i=0;i<20;++i) {
            libraryCards.add(obj("uuid","uuid-"+i,"card",obj("id","card-"+i)));
            libraryLabels.add("offer-"+i);
        }
        for(int defect=-1;defect<6;++defect) {
            Map<String,Object> state=obj("screen_type","GRID","ready_for_command",true,
                    "can_cancel",defect==0,"can_proceed",false,"choice_list",libraryLabels);
            Map<String,Object> out=obj("mcpState",state);
            java.util.List<Object> offers=new java.util.ArrayList<>(libraryCards);
            if(defect==3) offers.set(0,offers.get(1));
            if(defect==4) offers.remove(0);
            if(defect==5) offers.set(0,obj("uuid","uuid-0","deckIndex",0,"card",obj("id","card-0")));
            java.util.List<Map<String,Object>> choices=new java.util.ArrayList<>();
            boolean accepted=LiveOocCapture.captureLibrarySelector(out,choices,libraryLabels,offers,
                    defect==1?2:1,defect==2?1:0);
            if(accepted!=(defect==-1))throw new AssertionError("Library selector qualification "+defect);
            if(accepted) {
                if(choices.size()!=20 || !"uuid-7".equals(choices.get(7).get("uuid"))
                        || !Integer.valueOf(8).equals(((Map<?,?>)choices.get(7).get("liveAction")).get("choiceIndex"))
                        || offers.size()!=20 || ((Map<?,?>)offers.get(7)).containsKey("deckIndex"))
                    throw new AssertionError("Library offered order or deck independence lost");
            } else if(!choices.isEmpty())throw new AssertionError("Partial Library action mapping");
        }
        if(!"obtain".equals(LiveOocCapture.selectorType(false,false,false,
                java.util.Arrays.asList("TheLibrary"),false,false).get("type"))
                || !"other".equals(LiveOocCapture.selectorType(true,false,false,
                java.util.Arrays.asList("TheLibrary"),false,false).get("type")))
            throw new AssertionError("Library selector owner/flags mismatch");
        for (boolean forge : new boolean[]{false,true}) {
            String simple=forge?"AccursedBlacksmith":"BackToBasics";
            for (int upgradeable : new int[]{0,3}) {
                java.util.List<Object> options=new java.util.ArrayList<>();
                for(int i=forge && upgradeable==0?1:0;i<(forge?3:2);++i)
                    options.add(obj("index",i,"disabled",false));
                Map<String,Object> out=obj("details",obj(),"unsupportedReason","phase");
                LiveOocCapture.captureForgeOrWriting(out,simple,forge?"0":"INTRO",options,upgradeable,3);
                if(out.containsKey("unsupportedReason")) throw new AssertionError("forge/writing initial rejected");
                out.put("unsupportedReason","phase");
                LiveOocCapture.captureForgeOrWriting(out,simple,"1",options,upgradeable,3);
                if(!out.containsKey("unsupportedReason")) throw new AssertionError("unknown event phase accepted");
                options.set(0,obj("index",0,"disabled",true));
                LiveOocCapture.captureForgeOrWriting(out,simple,forge?"0":"INTRO",options,upgradeable,3);
                if(!out.containsKey("unsupportedReason")) throw new AssertionError("disabled event choice accepted");
            }
            Map<String,Object> result=obj("details",obj(),"unsupportedReason","phase");
            java.util.List<Object> sole=java.util.Arrays.asList(obj("index",0,"disabled",false));
            LiveOocCapture.captureForgeOrWriting(result,simple,forge?"2":"COMPLETE",sole,0,0);
            if(result.containsKey("unsupportedReason") || !"event_leave".equals(
                    ((Map<?,?>)result.get("details")).get("mechanicalTransition")))
                throw new AssertionError("forge/writing result rejected");
        }
        String[] chestTypes={"SmallChest","MediumChest","LargeChest"};
        for(int i=0;i<chestTypes.length;++i) {
            Map<String,Object> out=obj("details",obj("chestType",chestTypes[i],"opened",false));
            java.util.List<Map<String,Object>> choices=new java.util.ArrayList<>();
            LiveOocCapture.captureUnopenedTreasure(out,choices,java.util.Arrays.asList("open"),chestTypes[i],true);
            Map<?,?> details=(Map<?,?>)out.get("details");
            if(out.containsKey("unsupportedReason") || !Integer.valueOf(i).equals(details.get("chestSize"))
                    || choices.size()!=2 || details.containsKey("haveGold") || details.containsKey("tier")
                    || !"choose".equals(((Map<?,?>)choices.get(0).get("liveAction")).get("kind"))
                    || !"proceed".equals(((Map<?,?>)choices.get(1).get("liveAction")).get("kind")))
                throw new AssertionError("public chest size/actions projection mismatch");
        }
        Map<String,Object> unknownChest=obj("details",obj());
        java.util.List<Map<String,Object>> chestChoices=new java.util.ArrayList<>();
        LiveOocCapture.captureUnopenedTreasure(unknownChest,chestChoices,java.util.Arrays.asList("open"),"BossChest",true);
        if(!unknownChest.containsKey("unsupportedReason") || ((Map<?,?>)unknownChest.get("details")).containsKey("chestSize"))
            throw new AssertionError("boss chest promoted to ordinary public prior");
        Map<String,Object> noLeave=obj("details",obj());chestChoices.clear();
        LiveOocCapture.captureUnopenedTreasure(noLeave,chestChoices,java.util.Arrays.asList("open"),"SmallChest",false);
        if(!noLeave.containsKey("unsupportedReason") || chestChoices.size()!=1)
            throw new AssertionError("unavailable chest Leave was fabricated");
        Map<String,Object> noOpen=obj("details",obj());chestChoices.clear();
        LiveOocCapture.captureUnopenedTreasure(noOpen,chestChoices,java.util.Collections.emptyList(),"SmallChest",true);
        if(!noOpen.containsKey("unsupportedReason") || chestChoices.size()!=1)
            throw new AssertionError("unavailable chest Open was fabricated");
        for (boolean boss : new boolean[]{false,true}) {
            java.util.List<String> labels = boss ? java.util.Arrays.asList("Boss") : java.util.Collections.emptyList();
            Map<String,Object> mcp = obj("screen_type",boss ? "MAP" : "GRID","ready_for_command",true,
                    "can_proceed",!boss,"can_cancel",false,"choice_list",labels);
            Map<String,Object> captured = obj("mcpState",mcp);
            java.util.List<Map<String,Object>> choices = new java.util.ArrayList<>();
            boolean ok = boss ? LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,14,0)
                    : LiveOocCapture.captureSelectorConfirmation(captured,choices,labels,true,false);
            if (!ok || choices.size()!=1 || !(boss?"boss_map":"selector_confirm").equals(
                    ((Map<?,?>)captured.get("details")).get("mechanicalTransition")))
                throw new AssertionError("sole public continuation missing");
            if (!boss && !"proceed".equals(((Map<?,?>)choices.get(0).get("liveAction")).get("kind")))
                throw new AssertionError("confirmation did not use advertised Proceed command");
            choices.clear();mcp.put("can_cancel",true);
            ok = boss ? LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,14,0)
                    : LiveOocCapture.captureSelectorConfirmation(captured,choices,labels,true,false);
            if (ok || !choices.isEmpty()) throw new AssertionError("cancelable screen was forced");
            if (boss) {
                mcp.put("cancel_button","return");mcp.put("room_type","RestRoom");mcp.put("room_phase","COMPLETE");
                if (!LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,14,0) || choices.size()!=1)
                    throw new AssertionError("completed campfire map Return blocked forced boss entrance");
                choices.clear();mcp.put("room_phase","INCOMPLETE");
                if (LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,14,0))
                    throw new AssertionError("unfinished campfire map bypassed its decision");
                mcp.put("room_phase","COMPLETE");mcp.put("cancel_button","cancel");
                if (LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,14,0))
                    throw new AssertionError("unknown cancel button qualified as map Return");
            }
            mcp.put("can_cancel",false);
            if (boss) {
                if (LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,13,0)
                        || LiveOocCapture.captureForcedBossMap(captured,choices,labels,4,14,0)
                        || LiveOocCapture.captureForcedBossMap(captured,choices,labels,1,14,1))
                    throw new AssertionError("non-boss map was forced");
            } else {
                if (LiveOocCapture.captureSelectorConfirmation(captured,choices,labels,true,true)
                        || LiveOocCapture.captureSelectorConfirmation(captured,choices,labels,false,false))
                    throw new AssertionError("selector preview was forced");
            }
        }
        java.util.List<Object> goopOptions = java.util.Arrays.asList(
                obj("index",0,"disabled",false), obj("index",1,"disabled",false));
        for (int[] values : new int[][]{{11,75,0,0}, {11,75,17,17}, {11,75,45,100}}) {
            Map<String,Object> captured = obj("details",obj(),"unsupportedReason","phase");
            LiveOocCapture.captureGoopPuddle(captured,"INTRO",goopOptions,values[0],values[1],values[2],values[3]);
            if (captured.containsKey("unsupportedReason")
                    || !Integer.valueOf(values[2]).equals(((Map<?,?>)captured.get("details")).get("goldLoss")))
                throw new AssertionError("public Goop loss was not preserved");
        }
        for (int[] values : new int[][]{{10,75,20,100}, {11,80,20,100}, {11,75,-1,100}, {11,75,21,20}}) {
            Map<String,Object> rejected = obj("details",obj(),"unsupportedReason","phase");
            LiveOocCapture.captureGoopPuddle(rejected,"INTRO",goopOptions,values[0],values[1],values[2],values[3]);
            if (!rejected.containsKey("unsupportedReason")) throw new AssertionError("invalid Goop parameters accepted");
        }
        Map<String,Object> goopOutro = obj("details",obj(),"unsupportedReason","phase");
        LiveOocCapture.captureGoopPuddle(goopOutro,"RESULT",goopOptions,11,75,20,100);
        if (!goopOutro.containsKey("unsupportedReason")) throw new AssertionError("Goop outro imported as initial choice");
        java.util.List<Object> oneOption = java.util.Arrays.asList(obj("index", 0, "disabled", false));
        LiveOocCapture.captureGoopPuddle(goopOutro,"RESULT",oneOption,11,75,20,0);
        if (goopOutro.containsKey("unsupportedReason")
                || !"event_leave".equals(((Map<?,?>)goopOutro.get("details")).get("mechanicalTransition")))
            throw new AssertionError("Goop Leave transition not captured after paying gold loss");
        for (String phase : new String[]{"0", "1", "99"}) {
            Map<String,Object> captured = obj("details", obj(), "unsupportedReason", "phase");
            LiveOocCapture.captureNeowTransition(captured, phase, oneOption);
            if (captured.containsKey("unsupportedReason")
                    || !("99".equals(phase) ? "event_leave" : "neow_intro").equals(
                            ((Map<?,?>)captured.get("details")).get("mechanicalTransition")))
                throw new AssertionError("verified Neow transition not captured: " + phase);
        }
        for (String phase : new String[]{"2", "3", "10", "999", "UNKNOWN"}) {
            Map<String,Object> rejected = obj("details", obj(), "unsupportedReason", "phase");
            LiveOocCapture.captureNeowTransition(rejected, phase, oneOption);
            if (!rejected.containsKey("unsupportedReason")) throw new AssertionError("unverified Neow transition accepted");
        }
        for (java.util.List<Object> options : java.util.Arrays.<java.util.List<Object>>asList(
                java.util.Collections.<Object>emptyList(),
                java.util.Arrays.asList(obj("index", 1, "disabled", false)),
                java.util.Arrays.asList(obj("index", 0, "disabled", true)),
                java.util.Arrays.asList(obj("index", 0, "disabled", false), obj("index", 1, "disabled", false)))) {
            Map<String,Object> rejected = obj("details", obj(), "unsupportedReason", "phase");
            LiveOocCapture.captureNeowTransition(rejected, "1", options);
            if (!rejected.containsKey("unsupportedReason")) throw new AssertionError("ambiguous Neow transition accepted");
        }
        String[][] ownerSelectors = {{"BackToBasics", "remove", ""}, {"Astrolabe", "transform_upgrade", ""},
                {"DollysMirror", "duplicate", ""}, {"Bottled Flame", "bottle", "attack"},
                {"Bottled Lightning", "bottle", "skill"}, {"Bottled Tornado", "bottle", "power"},
                {"NeowRemoveTwo", "remove", ""}, {"NeowTransformTwo", "transform", ""}};
        for (String[] row : ownerSelectors) {
            Map<String,Object> type = LiveOocCapture.selectorType(false, false, false,
                    java.util.Arrays.asList(row[0]), false, false);
            if (!row[1].equals(type.get("type")) || !row[2].equals(type.getOrDefault("bottleType", "")))
                throw new AssertionError("wrong owned selector: " + row[0]);
            if (!"other".equals(LiveOocCapture.selectorType(true, false, false,
                    java.util.Arrays.asList(row[0]), false, false).get("type")))
                throw new AssertionError("contradictory owned selector accepted");
        }
        // Live problem 103: only the activated two-card Neow reward owns the
        // unflagged grid.
        LiveOocCapture.neowTwoCardFix = true;
        if (!"NeowRemoveTwo".equals(LiveOocCapture.neowTwoCardOwner(java.util.Arrays.asList(
                    new FakeNeowReward("THREE_CARDS", false), new FakeNeowReward("REMOVE_TWO", true))))
                || !"NeowTransformTwo".equals(LiveOocCapture.neowTwoCardOwner(java.util.Arrays.asList(
                    new FakeNeowReward("TRANSFORM_TWO_CARDS", true), new FakeNeowReward("REMOVE_TWO", false))))
                || LiveOocCapture.neowTwoCardOwner(java.util.Arrays.asList(new FakeNeowReward("REMOVE_TWO", false))) != null
                || LiveOocCapture.neowTwoCardOwner(java.util.Arrays.asList(new FakeNeowReward("REMOVE_CARD", true))) != null
                || LiveOocCapture.neowTwoCardOwner(java.util.Arrays.asList(
                    new FakeNeowReward("REMOVE_TWO", true), new FakeNeowReward("TRANSFORM_TWO_CARDS", true))) != null
                || LiveOocCapture.neowTwoCardOwner(null) != null)
            throw new AssertionError("Neow two-card selector owner");
        LiveOocCapture.neowTwoCardFix = false;
        if (LiveOocCapture.neowTwoCardOwner(java.util.Arrays.asList(new FakeNeowReward("REMOVE_TWO", true))) != null)
            throw new AssertionError("STS_NEOW_TWO_CARD_SELECTOR_FIX=0 restores the unowned grid");
        LiveOocCapture.neowTwoCardFix = true;
        java.util.List<String> noOwners = java.util.Collections.emptyList();
        if (!"bonfire".equals(LiveOocCapture.selectorType(false,true,false,noOwners,true,false).get("type"))
                || !"duplicate".equals(LiveOocCapture.selectorType(false,false,false,noOwners,false,true).get("type"))
                || !"remove".equals(LiveOocCapture.selectorType(false,true,false,noOwners,false,false).get("type"))
                || !"other".equals(LiveOocCapture.selectorType(false,false,false,
                        java.util.Arrays.asList("Astrolabe","DollysMirror"),false,false).get("type"))
                || !"other".equals(LiveOocCapture.selectorType(false,false,false,noOwners,false,false).get("type")))
            throw new AssertionError("selector owner qualification mismatch");
        for (int count : new int[]{2,4}) {
            java.util.List<Object> offers = new java.util.ArrayList<>();
            java.util.List<Object> options = new java.util.ArrayList<>();
            for (int i=0; i<count; ++i) {
                offers.add(obj("type", i==0 ? "THREE_ENEMY_KILL" : "TEN_PERCENT_HP_BONUS", "drawback", "NONE"));
                options.add(obj("index", i, "disabled", false));
            }
            Map<String,Object> captured = obj("screen", "event", "details", obj(),
                    "unsupportedReason", "EVENT_PHASE_UNREPRESENTABLE:Neow:3");
            LiveOocCapture.captureNeowOffers(captured, offers, "3", options);
            java.util.List<?> actual = (java.util.List<?>)((Map<?,?>)captured.get("details")).get("neow");
            if (!"neow".equals(captured.get("screen")) || captured.containsKey("unsupportedReason")
                    || actual.size()!=count)
                throw new AssertionError("Neow offer count was not preserved");
            for (int i=0; i<count; ++i)
                if (!((Map<?,?>)offers.get(i)).get("type").equals(((Map<?,?>)actual.get(i)).get("bonus")))
                    throw new AssertionError("Neow offer order was changed");
            for (String phase : new String[]{"0","1","2","4"}) {
                Map<String,Object> rejected = obj("screen","event","details",obj(),"unsupportedReason","phase");
                LiveOocCapture.captureNeowOffers(rejected,offers,phase,options);
                if (!rejected.containsKey("unsupportedReason")) throw new AssertionError("Neow non-choice phase accepted");
            }
            for (int slot : new int[]{-1,1,4}) {
                options.set(0,obj("index",slot,"disabled",false));
                Map<String,Object> rejected = obj("screen","event","details",obj(),"unsupportedReason","slots");
                LiveOocCapture.captureNeowOffers(rejected,offers,"3",options);
                if (!rejected.containsKey("unsupportedReason")) throw new AssertionError("Neow slot mismatch accepted");
            }
            options.set(0,obj("index",0,"disabled",true));
            Map<String,Object> disabled = obj("screen","event","details",obj(),"unsupportedReason","disabled");
            LiveOocCapture.captureNeowOffers(disabled,offers,"3",options);
            if (!disabled.containsKey("unsupportedReason")) throw new AssertionError("disabled Neow slot accepted");
            options.remove(0);
            Map<String,Object> rejected = obj("screen","event","details",obj(),"unsupportedReason","missing");
            LiveOocCapture.captureNeowOffers(rejected,offers,"3",options);
            if (!rejected.containsKey("unsupportedReason")) throw new AssertionError("incomplete Neow buttons accepted");
        }
        check("MawBank", -1, false, 1, null);
        check("MawBank", -2, true, 0, null);
        check("Happy Flower", 2, false, 2, null);
        check("Pen Nib", 9, false, 9, null);
        check("Girya", 3, false, 3, null);
        check("Omamori", 2, false, 2, null);
        check("Omamori", -2, true, 0, null);
        check("Omamori", 0, false, 0, null);
        check("NeowsBlessing", -2, true, 0, null);
        check("NeowsBlessing", 3, false, 3, null);
        check("NeowsBlessing", -1, true, -1, null);
        check("Ancient Tea Set", -2, false, 1, null);
        check("Ancient Tea Set", -1, false, 0, null);
        check("Burning Blood", -1, false, -1, null);
        check("Lizard Tail", -1, false, 1, null);
        check("Lizard Tail", -2, true, 0, null);
        check("Lizard Tail", -2, false, 0, null);
        check("Matryoshka", 2, false, 2, null);
        check("Matryoshka", 1, false, 1, null);
        for(int counter:new int[]{-2,0,1,2,3})
            check("WingedGreaves", counter, counter==-2, 0, null);
        check("NlothsMask", 1, false, 1, null);
        check("NlothsMask", -2, false, 0, null);
        check("NlothsMask", 2, false, 2, "RELIC_NATIVE_STATE_UNREPRESENTABLE:NlothsMask:counter");
        check("Matryoshka", -1, false, -1, "RELIC_NATIVE_STATE_UNREPRESENTABLE:Matryoshka:counter");
        check("Matryoshka", -2, true, 0, null);
        check("Du-Vu Doll", 1, false, 1, null);
        check("Du-Vu Doll", 0, false, 0, null);
        check("UnqualifiedCounter", 3, false, 3, "RELIC_NATIVE_COUNTER_UNQUALIFIED:UnqualifiedCounter");
        if (!"GAMBLE".equals(STSModelInspector.handSelectionTask("", true, true, 99)))
            throw new AssertionError("Gambler's Brew hand selector was not classified as GAMBLE");
        if (!"".equals(STSModelInspector.handSelectionTask("", false, true, 99)))
            throw new AssertionError("unknown fixed-size hand selector was over-promoted");
        if (LiveOocCapture.nativeEdgeDestination(14, 3, 16) != 3)
            throw new AssertionError("vanilla terminal boss edge lost");
        if (LiveOocCapture.nativeEdgeDestination(7, 6, 8) != 6)
            throw new AssertionError("ordinary visible edge changed");
        int[][] invalid = {{13, 3, 16}, {14, 2, 16}, {14, 3, 15}, {7, 7, 8}, {7, 3, 9}};
        for (int[] edge : invalid) {
            boolean rejected = false;
            try { LiveOocCapture.nativeEdgeDestination(edge[0], edge[1], edge[2]); }
            catch (IllegalArgumentException expected) { rejected = true; }
            if (!rejected) throw new AssertionError("invalid map edge accepted");
        }
        if (!"combat_reward".equals(LiveOocCapture.canonicalScreen("COMBAT_REWARD"))
                || !"selector".equals(LiveOocCapture.canonicalScreen("GRID"))
                || !"boss_relic".equals(LiveOocCapture.canonicalScreen("BOSS_REWARD")))
            throw new AssertionError("early canonical screen correlation lost");
        java.util.List<String> persistedPath = new java.util.ArrayList<>();
        for (int i = 0; i < 15; ++i) persistedPath.add("M");
        persistedPath.add("unknown-boss-marker");
        persistedPath.add("M");
        java.util.List<String> qualified = LiveOocCapture.canonicalPathHistory(
                persistedPath, false, "", 2, java.util.Arrays.asList(16, 18));
        if (!"BOSS".equals(qualified.get(15)) || !"MONSTER".equals(qualified.get(16)))
            throw new AssertionError("completed public boss marker stayed incomplete in Act 2");
        if (!"INVALID".equals(LiveOocCapture.canonicalPathHistory(
                persistedPath, false, "", 2, java.util.Arrays.asList(18)).get(15)))
            throw new AssertionError("unknown path marker was promoted without a boss combat");
        persistedPath.remove(0);
        if (!"INVALID".equals(LiveOocCapture.canonicalPathHistory(
                persistedPath, false, "", 2, java.util.Arrays.asList(16, 18)).get(14)))
            throw new AssertionError("incomplete prior map history was promoted to a boss");
        java.util.List<String> vanillaBossPath = new java.util.ArrayList<>();
        for(int act=1;act<=2;++act) {
            for(int room=0;room<15;++room)vanillaBossPath.add("M");
            vanillaBossPath.add("BOSS");
        }
        java.util.List<String> actThree = LiveOocCapture.canonicalPathHistory(
                vanillaBossPath,true,"",3,java.util.Arrays.asList(16,33));
        if(!"BOSS".equals(actThree.get(15)) || !"BOSS".equals(actThree.get(31)))
            throw new AssertionError("vanilla BOSS path marker lost on Act 3 entry");
        if(!"BOSS".equals(LiveOocCapture.canonicalPathHistory(
                vanillaBossPath.subList(0,16),true,"REST",1,
                java.util.Collections.<Integer>emptyList()).get(15)))
            throw new AssertionError("public boss room was replaced with its preceding campfire");
        Map<String,Object> openedChest = new HashMap<>();
        java.util.List<Map<String,Object>> openedChoices = new java.util.ArrayList<>();
        LiveOocCapture.captureOpenedTreasure(openedChest, openedChoices, true);
        if (openedChoices.size() != 1
                || !"proceed".equals(((Map<?,?>)openedChoices.get(0).get("liveAction")).get("kind"))
                || openedChest.containsKey("unsupportedReason"))
            throw new AssertionError("open boss chest lost its sole live Proceed action");
        openedChoices.clear();
        LiveOocCapture.captureOpenedTreasure(openedChest, openedChoices, false);
        if (!openedChoices.isEmpty()
                || !"CHEST_ALREADY_OPEN".equals(openedChest.get("unsupportedReason")))
            throw new AssertionError("open chest without Proceed exposed a false live action");
        Map<String,Object> phaseUnsupported = obj("publicState", obj("pathComplete", true,
                "unsupportedReason", "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"),
                "unsupportedReason", "EVENT_PHASE_UNREPRESENTABLE:Beggar:LEAVE");
        LiveOocCapture.finalizeSupportReason(phaseUnsupported);
        if (!"EVENT_PHASE_UNREPRESENTABLE:Beggar:LEAVE".equals(phaseUnsupported.get("unsupportedReason")))
            throw new AssertionError("relic warning hid the unsupported event outro phase");
        Map<String,Object> missingPath = obj("publicState", obj("pathComplete", false,
                "unsupportedReason", "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"));
        LiveOocCapture.finalizeSupportReason(missingPath);
        if (!"PATH_HISTORY_UNAVAILABLE".equals(missingPath.get("unsupportedReason")))
            throw new AssertionError("relic warning hid incomplete public path history");
        Map<String,Object> failed = new HashMap<>();
        Map<String,Object> core = new HashMap<>();
        Map<String,Object> mcp = new HashMap<>();
        java.util.List<Object> choices = new java.util.ArrayList<>();
        failed.put("screen", "combat_reward"); failed.put("publicState", core);
        failed.put("mcpState", mcp); failed.put("liveChoices", choices);
        LiveOocCapture.recordCaptureError(failed, new IllegalArgumentException("choice occurrence unavailable"));
        if (!"IllegalArgumentException:choice occurrence unavailable".equals(failed.get("captureError"))
                || failed.containsKey("unsupportedReason") || failed.get("publicState") != core
                || failed.get("mcpState") != mcp || failed.get("liveChoices") != choices
                || !"combat_reward".equals(failed.get("screen")))
            throw new AssertionError("integrity failure became fallback or lost correlation");
        // An earlier support reason must not swallow a later integrity error;
        // the native importer gives captureError precedence over unsupported.
        failed.put("unsupportedReason", "CARD_GROUP_NOT_REVEALED");
        LiveOocCapture.recordCaptureError(failed, new NoSuchMethodException("read-only API missing"));
        if (!"NoSuchMethodException:read-only API missing".equals(failed.get("captureError")))
            throw new AssertionError("reflective integrity failure was hidden");
        if (!"Neow".equals(LiveOocCapture.canonicalEventId("NEOW"))
                || !"Big Fish".equals(LiveOocCapture.canonicalEventId("Big Fish")))
            throw new AssertionError("event canonical save identity mismatch");
        if (!LiveOocCapture.simpleInitialEventSupported("WomanInBlue")
                || LiveOocCapture.simpleInitialEventSupported("WomanInBlueDialogue")
                || LiveOocCapture.simpleInitialEventSupported("ShiningLight")
                || LiveOocCapture.simpleInitialEventSupported("Ghosts")
                || LiveOocCapture.simpleInitialEventSupported("WindingHalls")
                || LiveOocCapture.simpleInitialEventSupported("WorldOfGoop"))
            throw new AssertionError("Woman in Blue initial-phase support boundary mismatch");
        Object firstReward = new Object(), secondReward = new Object();
        String firstIdentity = LiveOocCapture.rewardIdentity(firstReward, null, null);
        if (!firstIdentity.equals(LiveOocCapture.rewardIdentity(firstReward, null, null))
                || firstIdentity.equals(LiveOocCapture.rewardIdentity(secondReward, null, null)))
            throw new AssertionError("physical reward identity is unstable or ambiguous");
        if (firstIdentity.equals(LiveOocCapture.rewardIdentity(firstReward, new Object(), null)))
            throw new AssertionError("reward identity reused after run boundary");
        LiveOocCapture.SeenRelicOffers seen = new LiveOocCapture.SeenRelicOffers();
        Object player = new Object();
        seen.observe(player, 10, 5, false, "shop", obj("relics",
                java.util.Arrays.asList(obj("id", "Anchor", "price", 120))));
        if (seen.complete()) throw new AssertionError("mid-run offer history became complete");
        player = new Object();
        seen.observe(player, 11, 0, true, "neow", obj());
        if (!seen.complete() || !seen.snapshot().isEmpty())
            throw new AssertionError("fresh-run offer history did not reset");
        seen.observe(player, 11, 1, false, "shop", obj("relics",
                java.util.Arrays.asList(obj("id", "Anchor", "price", 120))));
        seen.observe(player, 11, 1, false, "combat_reward", obj("relics",
                java.util.Arrays.asList("Vajra", "Anchor")));
        if (!seen.complete() || !seen.snapshot().equals(java.util.Arrays.asList("Anchor", "Vajra")))
            throw new AssertionError("visible offered relics were lost or duplicated");
        seen.observe(player, 11, 3, false, "map", obj());
        if (seen.complete()) throw new AssertionError("missed floors retained complete history");
        LiveOocCapture.CombatClassHistory combats = new LiveOocCapture.CombatClassHistory();
        Object group = new Object();
        combats.observe(player, 12345, 1, 3, true, true, group, "FIXED_EVENT", "MUSHROOMS_EVENT");
        combats.observe(player, 12345, 1, 3, true, true, new Object(), "FIXED_EVENT", "MUSHROOMS_EVENT");
        combats.observe(player, 12345, 1, 3, false, false, null, null, "");
        combats.observe(player, 12345, 1, 5, false, true, new Object(), "NORMAL_QUEUE", "JAW_WORM");
        combats.observe(player, 12345, 1, 8, false, true, new Object(), "ELITE_QUEUE", "GREMLIN_NOB");
        if (!combats.completeFor(java.util.Arrays.asList(3, 5, 8))
                || combats.snapshot().size() != 3
                || !"FIXED_EVENT".equals(combats.snapshot().get(0).get("kind")))
            throw new AssertionError("complete combat-class ledger lost fixed-event distinction");
        if (combats.completeFor(java.util.Arrays.asList(3, 5, 9)))
            throw new AssertionError("wrong combat metric floor qualified the ledger");
        LiveOocCapture.CombatClassHistory summoner = new LiveOocCapture.CombatClassHistory();
        Object summonerGroup = new Object();
        summoner.observe(player, 12345, 2, 28, true, true, summonerGroup,
                "ELITE_QUEUE", "GREMLIN_LEADER");
        // SpawnMonsterAction retains dead objects in the same MonsterGroup.
        // Its later composition no longer identifies the original queue draw.
        summoner.observe(player, 12345, 2, 28, true, true, summonerGroup,
                "ELITE_QUEUE", "");
        if (!summoner.completeFor(java.util.Arrays.asList(28))
                || !"GREMLIN_LEADER".equals(summoner.snapshot().get(0).get("encounter")))
            throw new AssertionError("summons invalidated the captured queue encounter");
        summoner.observe(player, 12345, 2, 28, true, true, new Object(),
                "ELITE_QUEUE", "BOOK_OF_STABBING");
        if (summoner.complete())
            throw new AssertionError("replacement group bypassed encounter validation");
        combats.observe(new Object(), 12345, 1, 9, false, true, new Object(), "NORMAL_QUEUE", "CULTIST");
        if (combats.completeFor(java.util.Arrays.asList(3, 5, 8, 9)))
            throw new AssertionError("new observer reconstructed an unbound same-seed ledger");
        combats.observe(player, 12345, 2, 18, true, true, new Object(), "NORMAL_QUEUE", "CULTIST");
        if (!combats.completeFor(java.util.Arrays.asList(18)))
            throw new AssertionError("new act did not reset complete combat-class history");
        combats.resetForFreshRun(player, 12345, 1);
        if (!combats.snapshot().isEmpty() || !combats.completeFor(java.util.Collections.emptyList()))
            throw new AssertionError("fresh same-seed run retained previous history");
        if (!"RED_SLAVER".equals(STSModelInspector.singleEncounterName("SlaverRed", false))
                || !"RED_SLAVER".equals(STSModelInspector.singleEncounterName("RedSlaver", false))
                || !"BLUE_SLAVER".equals(STSModelInspector.singleEncounterName("SlaverBlue", false))
                || !"BLUE_SLAVER".equals(STSModelInspector.singleEncounterName("BlueSlaver", false)))
            throw new AssertionError("canonical Slaver runtime identity mismatch");
        System.out.println("LiveOocCaptureTest: Neow offers/transitions, Goop public choices/Leave, selector ownership, relic counters, map/path, integrity, reward and combat history checks passed");
    }
}
