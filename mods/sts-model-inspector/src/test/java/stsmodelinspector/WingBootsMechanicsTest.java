package stsmodelinspector;

import com.google.gson.Gson;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import javassist.ClassMap;
import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtField;
import javassist.CtMethod;
import javassist.CtNewConstructor;
import javassist.CtNewMethod;

/** Runs the installed vanilla connectivity/counter bytecode with inert world
 * dependencies. No game, graphics, save file or random stream is initialized. */
public final class WingBootsMechanicsTest {
    public static final class Edge {
        public int dstX,dstY;
        Edge(int x,int y){dstX=x;dstY=y;}
    }
    public static class Relic {
        public int counter;
        public boolean usedUp;
        public void usedUp(){usedUp=true;}
    }
    public static final class Player {
        public Relic relic;
        public boolean hasRelic(String id){return "WingedGreaves".equals(id)&&relic!=null;}
        public Relic getRelic(String id){return hasRelic(id)?relic:null;}
    }
    public static final class Dungeon {public static Player player=new Player();}
    public static final class ModHelper {public static boolean isModEnabled(String id){return false;}}
    public static final class SaveCounters {public List<Integer> relic_counters;}
    private static final class Loader extends ClassLoader {
        Loader(){super(WingBootsMechanicsTest.class.getClassLoader());}
        Class<?> define(CtClass type)throws Exception {
            byte[] code=type.toBytecode();return defineClass(type.getName(),code,0,code.length);
        }
    }
    private static void require(boolean value,String why){if(!value)throw new AssertionError(why);}
    private static Object node(Class<?> type,int x,int y,boolean hasEdge)throws Exception {
        Object value=type.newInstance();type.getField("x").setInt(value,x);type.getField("y").setInt(value,y);
        ArrayList<Edge> edges=new ArrayList<>();if(hasEdge)edges.add(new Edge(2,y+1));
        type.getField("edges").set(value,edges);return value;
    }
    public static void main(String[] args)throws Exception {
        ClassPool pool=new ClassPool(true);pool.appendPathList(System.getProperty("java.class.path"));
        String prefix="com.megacrit.cardcrawl.";
        CtClass originalNode=pool.get(prefix+"map.MapRoomNode");
        CtClass copiedNode=pool.makeClass("stsmodelinspector.WingBootsVanillaNode");
        copiedNode.addField(CtField.make("public int x;",copiedNode));
        copiedNode.addField(CtField.make("public int y;",copiedNode));
        copiedNode.addField(CtField.make("public java.util.ArrayList edges;",copiedNode));
        copiedNode.addConstructor(CtNewConstructor.defaultConstructor(copiedNode));
        ClassMap map=new ClassMap();
        map.put(originalNode.getName(),copiedNode.getName());
        map.put(prefix+"map.MapEdge",Edge.class.getName());
        map.put(prefix+"dungeons.AbstractDungeon",Dungeon.class.getName());
        map.put(prefix+"characters.AbstractPlayer",Player.class.getName());
        map.put(prefix+"relics.AbstractRelic",Relic.class.getName());
        map.put(prefix+"helpers.ModHelper",ModHelper.class.getName());
        for(String method:Arrays.asList("hasEdges","isConnectedTo","wingedIsConnectedTo"))
            copiedNode.addMethod(CtNewMethod.copy(originalNode.getDeclaredMethod(method),copiedNode,map));
        Loader loader=new Loader();Class<?> nodeType=loader.define(copiedNode);
        Method ordinary=nodeType.getMethod("isConnectedTo",nodeType);
        Method winged=nodeType.getMethod("wingedIsConnectedTo",nodeType);
        Method hasEdges=nodeType.getMethod("hasEdges");
        Object current=node(nodeType,1,0,true),edge=node(nodeType,2,1,true),jump=node(nodeType,5,1,true);
        Object absent=node(nodeType,4,1,false),wrongRow=node(nodeType,5,2,true),deadEnd=node(nodeType,1,0,false);
        CtClass originalRelic=pool.get(prefix+"relics.WingBoots");
        CtClass copiedRelic=pool.makeClass("stsmodelinspector.WingBootsVanillaRelic");
        copiedRelic.setSuperclass(pool.get(Relic.class.getName()));
        copiedRelic.addConstructor(CtNewConstructor.defaultConstructor(copiedRelic));
        ClassMap relicMap=new ClassMap();relicMap.put(originalRelic.getName(),copiedRelic.getName());
        relicMap.put(prefix+"relics.AbstractRelic",Relic.class.getName());
        // toMethod removes only the graphics-loading superclass constructor;
        // the vanilla constructor's counter initialization executes unchanged.
        copiedRelic.addMethod(originalRelic.getDeclaredConstructors()[0].toMethod("acquire",copiedRelic,relicMap));
        copiedRelic.addMethod(CtNewMethod.copy(originalRelic.getDeclaredMethod("setCounter"),copiedRelic,relicMap));
        Class<?> relicType=loader.define(copiedRelic);
        Relic relic=(Relic)relicType.newInstance();relicType.getMethod("acquire").invoke(relic);
        require(relic.counter==3,"vanilla acquisition charge count");Dungeon.player.relic=relic;
        Gson gson=new Gson();
        for(int counter:new int[]{-2,0,1,2,3}) {
            // Vanilla save counters are the public persisted field; decode and
            // restore through the actual relic setter before testing MCP's
            // hasEdges && (ordinary || winged) predicate.
            SaveCounters save=new SaveCounters();save.relic_counters=Arrays.asList(counter);
            SaveCounters restored=gson.fromJson(gson.toJson(save),SaveCounters.class);
            relicType.getMethod("setCounter",int.class).invoke(relic,restored.relic_counters.get(0));
            require(relic.counter==counter && (counter!=-2||relic.usedUp),"vanilla exhausted/save counter");
            require((Boolean)ordinary.invoke(current,edge),"ordinary edge lost");
            require(!(Boolean)ordinary.invoke(current,jump),"disconnected edge became ordinary");
            require((Boolean)winged.invoke(current,jump)==(counter>0),"vanilla charged jump predicate");
            require(!(Boolean)winged.invoke(current,wrongRow),"Wing Boots jumped multiple rows");
            require(!(Boolean)winged.invoke(deadEnd,jump),"node without outgoing row allowed jump");
            require(!(Boolean)hasEdges.invoke(absent),"MCP would expose nonexistent destination");
            HashMap<String,Object> projection=new HashMap<>();
            require(LiveOocCapture.nativeRelicData("WingedGreaves",relic.counter,relic.usedUp,projection)==0
                    && !projection.containsKey("unsupportedReason"),"public Wing Boots feature projection");
        }
        relicType.getMethod("acquire").invoke(relic);Dungeon.player.relic=null;
        require(!(Boolean)winged.invoke(current,jump),"removed relic retained a jump");
        Dungeon.player.relic=relic;
        require((Boolean)winged.invoke(current,jump),"reacquired relic lost jumps");
        System.out.println("WingBootsMechanicsTest passed (installed vanilla node/counter bytecode; JSON counter resume)");
    }
}
