import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { finalAssistantText, runPiChild } from "./runner.ts";

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sts-runner-test-"));
const fakePi = path.join(tmpDir, "pi");

try {
  fs.writeFileSync(fakePi, `#!/usr/bin/env node
for (let i = 0; i < 12000; i++) {
  console.log(JSON.stringify({
    type: "message_update",
    assistantMessageEvent: { type: "thinking_delta", delta: "abcdefghij" },
  }));
}
console.log(JSON.stringify({
  type: "message_end",
  message: { role: "assistant", content: [{ type: "text", text: "final response" }] },
}));
console.log(JSON.stringify({ type: "agent_end" }));
`);
  fs.chmodSync(fakePi, 0o755);

  const oldPath = process.env.PATH;
  process.env.PATH = `${tmpDir}${path.delimiter}${oldPath || ""}`;
  try {
    const seen = [];
    const result = await runPiChild({
      cwd: process.cwd(),
      args: [],
      hardTimeoutMs: 10_000,
      idleTimeoutMs: 5_000,
      onEvent: (event) => seen.push(event.type),
    });

    assert.equal(result.exitCode, 0);
    assert.equal(result.wasTimedOut, false);
    assert.equal(finalAssistantText(result.events), "final response\n");
    assert.equal(seen.at(-1), "agent_end");
    assert.ok(seen.length > 12_000, "all events must reach the live callback");
    assert.ok(result.events.length < seen.length, "delta retention must remain bounded");

    fs.writeFileSync(fakePi, `#!/usr/bin/env node
setInterval(() => {}, 1000);
`);
    const idleResult = await runPiChild({
      cwd: process.cwd(),
      args: [],
      hardTimeoutMs: 5_000,
      idleTimeoutMs: 100,
    });
    assert.equal(idleResult.wasTimedOut, true);
    assert.equal(idleResult.timeoutKind, "idle");

    fs.writeFileSync(fakePi, `#!/usr/bin/env node
console.log(JSON.stringify({
  type: "message_end",
  message: { role: "assistant", content: [{ type: "text", text: "done" }] },
}));
console.log(JSON.stringify({ type: "agent_end" }));
setTimeout(() => {}, 300);
`);
    const closingResult = await runPiChild({
      cwd: process.cwd(),
      args: [],
      hardTimeoutMs: 100,
      idleTimeoutMs: 100,
    });
    assert.equal(closingResult.exitCode, 0);
    assert.equal(closingResult.wasTimedOut, false);
  } finally {
    process.env.PATH = oldPath;
  }
} finally {
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

console.log("runner lifecycle regression: PASS");
