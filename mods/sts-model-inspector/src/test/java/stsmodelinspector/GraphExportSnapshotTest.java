package stsmodelinspector;

public final class GraphExportSnapshotTest {
    public static void main(String[] args) {
        String responseA = "{\"status\":\"READY\",\"session\":\"run\",\"sequence\":4,"
                + "\"observationHash\":\"hash-a\",\"tree\":{\"id\":\"tree-a\"}}";
        String responseB = "{\"status\":\"READY\",\"session\":\"run\",\"sequence\":5,"
                + "\"observationHash\":\"hash-b\",\"tree\":{\"id\":\"tree-b\"}}";

        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                4, "hash-a", responseA, "ready", "", 10) != null)
            throw new AssertionError("stale response sequence was paired with the clicked observation");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", responseA, "ready", "", 10) != null)
            throw new AssertionError("stale response hash was paired with the clicked observation");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", responseB, "waiting", "", 10) != null)
            throw new AssertionError("waiting response was accepted for graph export");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", responseB, "error", "", 10) != null)
            throw new AssertionError("error response was accepted for graph export");
        String errorJson = responseB.replace("READY", "ERROR");
        if (STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", errorJson, "ready", "", 10) != null)
            throw new AssertionError("non-READY advisor payload was accepted for graph export");

        String pinned = STSModelInspector.graphSnapshotJson("run", 5, "hash-b", "{\"decision\":\"B\"}",
                5, "hash-b", responseB, "ready", "", 10);
        if (pinned == null || !pinned.contains("\"observation\":{\"decision\":\"B\"}")
                || !pinned.contains("\"advisor\":" + responseB)
                || !pinned.contains("\"ready\":true")
                || !pinned.contains("\"sequence\":5")
                || !pinned.contains("\"observationHash\":\"hash-b\""))
            throw new AssertionError("matching response was not materialized as the pinned graph snapshot");
        System.out.println("GraphExportSnapshotTest: ready identity pinning and stale/waiting rejection passed");
    }
}
