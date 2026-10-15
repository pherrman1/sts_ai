"""Seed-free startup regression: capture policy after all options are applied."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="sts-leaf-startup-") as directory:
        output = Path(directory) / "capture.jsonl"
        env = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
        env.update({
            "STS_NATIVE_OOC": "1", "STS_OOC_MCTS": "1",
            "STS_OOC_STRATEGIC_TOK_NN": str(repo / "selfplay/models/ooc_strategic_tok_final.native"),
            "STS_OOC_MCTS_LEAF_VALUE": "native", "STS_OOC_MCTS_LEAF_COMBATS": "3",
            "STS_OOC_MCTS_LEAF_CAPTURE": str(output),
            "STS_EVENT_V": "1", "STS_SHOP_WIN": "1", "STS_PATH_V": "1",
        })
        command = ["bash", str(repo / "tools/seed_guard.sh"), str(binary), "oocmctsconfigselftest"]
        result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        raw = output.read_bytes()
        header = json.loads(raw)
        provenance = header["provenance"]
        flags = provenance["oocPolicy"]["flags"]
        assert flags["event_v"] and flags["shop_win"] and flags["path_v"], flags
        assert provenance["binarySha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
        assert "STS_OOC_MCTS_LEAF_CAPTURE" not in provenance["oocPolicy"]["ooc_mcts"]["environment"]
        result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
        assert result.returncode != 0 and "requires a new writable file" in result.stderr
        assert output.read_bytes() == raw, "existing capture changed"
        # Explicit misuse fails instead of silently producing no data.
        env["STS_OOC_MCTS"] = "0"
        result = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
        assert result.returncode != 0 and "requires STS_OOC_MCTS=1" in result.stderr
    print("PASS leaf capture startup policy, binary custody, exclusive output and disabled-MCTS rejection")


if __name__ == "__main__":
    main()
