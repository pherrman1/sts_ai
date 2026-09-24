package stsmodelinspector;

public final class GraphExportSnapshotTest {
    public static void main(String[] args) {
        String responseA = "{\"kind\":\"analysis\",\"status\":\"OK\",\"session\":\"run\",\"sequence\":4,"
                + "\"observationHash\":\"hash-a\",\"tree\":{\"id\":\"tree-a\"}}";
        String responseB = "{\"kind\":\"analysis\",\"status\":\"OK\",\"session\":\"run\",\"sequence\":5,"
                + "\"observationHash\":\"hash-b\",\"tree\":{\"id\":\"tree-b\"}}";

        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                4, "hash-a", responseA, "", 10) != null)
            throw new AssertionError("stale response sequence was paired with the clicked observation");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", responseA, "", 10) != null)
            throw new AssertionError("stale response hash was paired with the clicked observation");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", "", "", 10) != null)
            throw new AssertionError("missing response was accepted for graph export");
        String hello = "{\"kind\":\"hello\",\"status\":\"READY\",\"session\":\"run\","
                + "\"sequence\":5,\"observationHash\":\"hash-b\"}";
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", hello, "", 10) != null)
            throw new AssertionError("READY hello response was accepted as an analysis response");

        String pinned = STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", responseB, "", 10);
        if (pinned == null || !pinned.contains("\"observation\":{\"decision\":\"B\"}")
                || !pinned.contains("\"advisor\":" + responseB)
                || !pinned.contains("\"response\":{\"status\":\"OK\"")
                || !pinned.contains("\"ready\":true")
                || !pinned.contains("\"sequence\":5")
                || !pinned.contains("\"observationHash\":\"hash-b\""))
            throw new AssertionError("matching response was not materialized as the pinned graph snapshot");
        String errorAnalysis = responseB.replace("\"OK\"", "\"ERROR\"");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", errorAnalysis, "advisor reported an error", 10) == null)
            throw new AssertionError("matching analysis response was rejected based on its result status");
        System.out.println("GraphExportSnapshotTest: matching analysis identity pinning and hello rejection passed");
    }
}
