#!/usr/bin/env python3
"""Install and validate a worktree-independent live Slay the Spire runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CTM_NAME = "combat_transition_near_full_except_smoke_v2.native"
OOC_NAME = "ooc_strategic_tok_final.native"
MANAGED_KEYS = ("advisor", "ctmModel", "oocModel")


class RuntimeFailure(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeFailure(f"command failed: {' '.join(command)}: {exc}") from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_runtime_root() -> Path:
    override = os.environ.get("STS_LIVE_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    return (Path(data_home).expanduser() if data_home else Path.home() / ".local/share") / "sts-ai/live-runtime"


def default_config_path() -> Path:
    return Path(os.environ.get("STS_MODEL_INSPECTOR_CONFIG", Path.home() / ".sts-model-inspector.properties")).expanduser()


def default_active_path() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser()
    return cache_home / "sts-live-driver/active-runtime.json"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class RuntimeManager:
    def __init__(self, repo: Path, root: Path, config: Path, active: Path):
        self.repo = repo.resolve()
        self.root = root.expanduser().resolve()
        self.config = config.expanduser().resolve()
        self.active = active.expanduser().resolve()
        self.releases = self.root / "releases"
        self.current = self.root / "current"

    def git_state(self) -> tuple[str, bool]:
        try:
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
            dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=self.repo, text=True).strip())
            return head, dirty
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeFailure(f"cannot inspect source Git state: {exc}") from exc

    def load_manifest(self, release: Path | None = None) -> dict[str, Any]:
        path = (release or self.current) / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeFailure(f"runtime manifest unreadable: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise RuntimeFailure(f"runtime manifest is not an object: {path}")
        return value

    def validate_release(self, release: Path | None = None) -> dict[str, Any]:
        release = (release or self.current).resolve()
        manifest = self.load_manifest(release)
        checks = (("one_combat_advisor", "advisorSha256", True), (f"models/{CTM_NAME}", "ctmSha256", False))
        if manifest.get("oocModelSha256"):
            checks += ((f"models/{OOC_NAME}", "oocModelSha256", False),)
        for relative, key, executable in checks:
            artifact = release / relative
            if not artifact.is_file():
                raise RuntimeFailure(f"runtime artifact missing: {artifact}")
            if executable and not os.access(artifact, os.X_OK):
                raise RuntimeFailure(f"runtime advisor is not executable: {artifact}")
            actual = sha256(artifact)
            if actual != manifest.get(key):
                raise RuntimeFailure(f"runtime artifact hash mismatch: {artifact}: expected {manifest.get(key)}, got {actual}")
        return manifest

    def config_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.config.is_file():
            return values
        for line in self.config.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def desired_config(self, manifest: dict[str, Any]) -> dict[str, str]:
        desired = {
            "advisor": str(self.current / "one_combat_advisor"),
            "ctmModel": str(self.current / "models" / CTM_NAME),
        }
        if manifest.get("oocModelSha256"):
            desired["oocModel"] = str(self.current / "models" / OOC_NAME)
        return desired

    def repair_config(self, manifest: dict[str, Any] | None = None) -> bool:
        manifest = manifest or self.validate_release()
        desired = self.desired_config(manifest)
        original = self.config.read_text(encoding="utf-8") if self.config.is_file() else ""
        output: list[str] = []
        replaced: set[str] = set()
        for line in original.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            ending = line[len(content):]
            if content.lstrip().startswith("#") or "=" not in content:
                output.append(line)
                continue
            key = content.split("=", 1)[0].strip()
            if key not in MANAGED_KEYS:
                output.append(line)
            elif key in desired and key not in replaced:
                output.append(f"{key}={desired[key]}{ending or os.linesep}")
                replaced.add(key)
            # Drop duplicates and unsupported stale oocModel entries.
        for key, value in desired.items():
            if key not in replaced:
                output.append(f"{key}={value}{os.linesep}")
        updated = "".join(output)
        if updated == original:
            return False
        self.config.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.config.name}.", dir=self.config.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            if self.config.exists():
                os.chmod(temporary, self.config.stat().st_mode)
            os.replace(temporary, self.config)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return True

    def config_ok(self, manifest: dict[str, Any]) -> tuple[bool, str]:
        values = self.config_values()
        desired = self.desired_config(manifest)
        for key, expected in desired.items():
            actual = values.get(key)
            if actual != expected:
                return False, f"{key}={actual or '<unset>'}, expected {expected}"
            if "/.codex/worktrees/" in actual:
                return False, f"{key} points into an ephemeral Codex worktree"
        for key in MANAGED_KEYS:
            if "/.codex/worktrees/" in values.get(key, ""):
                return False, f"{key} points into an ephemeral Codex worktree"
        return True, "ok"

    def activate(self, release: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f".current.{os.getpid()}"
        try:
            temporary.unlink(missing_ok=True)
            temporary.symlink_to(Path("releases") / release.name)
            os.replace(temporary, self.current)
        finally:
            temporary.unlink(missing_ok=True)

    def find_cached(self, git_head: str, hashes: dict[str, str] | None = None) -> Path | None:
        if not self.releases.is_dir():
            return None
        for release in self.releases.iterdir():
            try:
                manifest = self.validate_release(release)
            except RuntimeFailure:
                continue
            matches_hashes = hashes is None or (
                manifest.get("advisorSha256") == hashes.get("advisor")
                and manifest.get("ctmSha256") == hashes.get("ctm")
                and manifest.get("oocModelSha256") == hashes.get("ooc")
            )
            if manifest.get("gitHead") == git_head and matches_hashes:
                return release
        return None

    def build_advisor(self) -> Path:
        run([sys.executable, "tools/agent/worktree.py", "preflight", "."], self.repo)
        run([sys.executable, "tools/agent/worktree.py", "check", "."], self.repo)
        run([sys.executable, "tools/agent/build.py",
             "--configure-preset", "linux-gcc-debug-ccache",
             "--build-preset", "linux-gcc-debug-ccache-build",
             "--target", "one_combat_advisor"], self.repo)
        candidates = [self.repo / "build" / name / "one_combat_advisor"
                      for name in ("linux-gcc-debug-ccache", "linux-gcc-debug")]
        built = [path for path in candidates if path.is_file() and os.access(path, os.X_OK)]
        if not built:
            raise RuntimeFailure(f"focused build did not create executable advisor under {self.repo / 'build'}")
        return max(built, key=lambda path: path.stat().st_mtime_ns)

    def install(self, advisor_source: Path | None = None) -> dict[str, Any]:
        head, dirty = self.git_state()
        advisor_source = (advisor_source or self.build_advisor()).resolve()
        if not advisor_source.is_file() or not os.access(advisor_source, os.X_OK):
            raise RuntimeFailure(f"advisor is missing or not executable: {advisor_source}")
        ctm = self.repo / "selfplay/models" / CTM_NAME
        ooc = self.repo / "selfplay/models" / OOC_NAME
        if not ctm.is_file():
            raise RuntimeFailure(f"tracked CTM model missing: {ctm}")
        hashes = {"advisor": sha256(advisor_source), "ctm": sha256(ctm)}
        if ooc.is_file():
            hashes["ooc"] = sha256(ooc)
        cached = self.find_cached(head, hashes)
        if cached:
            manifest = self.validate_release(cached)
            self.activate(cached)
            self.repair_config(manifest)
            return manifest
        runtime_id = f"{head[:12]}-{hashes['advisor'][:12]}"
        self.releases.mkdir(parents=True, exist_ok=True)
        final = self.releases / runtime_id
        if final.exists():
            runtime_id = f"{runtime_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            final = self.releases / runtime_id
        staging = Path(tempfile.mkdtemp(prefix=f".{runtime_id}.", dir=self.releases))
        try:
            shutil.copy2(advisor_source, staging / "one_combat_advisor")
            (staging / "models").mkdir()
            shutil.copy2(ctm, staging / "models" / CTM_NAME)
            if ooc.is_file():
                shutil.copy2(ooc, staging / "models" / OOC_NAME)
            manifest: dict[str, Any] = {
                "runtimeId": runtime_id,
                "gitHead": head,
                "dirty": dirty,
                "advisorSha256": hashes["advisor"],
                "ctmSha256": hashes["ctm"],
                "installedAt": utc_now(),
            }
            if "ooc" in hashes:
                manifest["oocModelSha256"] = hashes["ooc"]
            atomic_json(staging / "manifest.json", manifest)
            self.validate_release(staging)
            os.replace(staging, final)
            self.activate(final)
            self.repair_config(manifest)
            return manifest
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def ensure(self) -> dict[str, Any]:
        try:
            manifest = self.validate_release()
        except RuntimeFailure:
            head, dirty = self.git_state()
            cached = None if dirty else self.find_cached(head)
            if cached:
                manifest = self.validate_release(cached)
                self.activate(cached)
                self.repair_config(manifest)
                return manifest
            return self.install()
        self.repair_config(manifest)
        return manifest

    def endpoint_status(self) -> str:
        try:
            with socket.create_connection(("127.0.0.1", int(os.environ.get("STS_MCP_PORT", "8080"))), timeout=0.15):
                return "reachable"
        except OSError:
            return "offline"

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {"runtimeRoot": str(self.root), "currentRelease": None, "usable": False,
                                  "configPath": str(self.config), "mcpEndpoint": self.endpoint_status()}
        try:
            manifest = self.validate_release()
            result.update({"currentRelease": str(self.current.resolve()), "manifest": manifest,
                           "advisorExecutable": True, "config": self.config_ok(manifest), "usable": self.config_ok(manifest)[0]})
        except RuntimeFailure as exc:
            result["error"] = str(exc)
        if self.active.is_file():
            try:
                active = json.loads(self.active.read_text(encoding="utf-8"))
                result["activeRuntime"] = active
                installed_id = result.get("manifest", {}).get("runtimeId")
                result["activeRuntimeMatchesCurrent"] = active.get("runtimeId") == installed_id
            except (OSError, json.JSONDecodeError) as exc:
                result["activeRuntimeError"] = str(exc)
        return result

    def record_active(self, inspector_jar: Path) -> dict[str, Any]:
        manifest = self.validate_release()
        value = {key: manifest[key] for key in ("runtimeId", "gitHead", "advisorSha256", "ctmSha256")}
        if manifest.get("oocModelSha256"):
            value["oocModelSha256"] = manifest["oocModelSha256"]
        value["inspectorJarSha256"] = sha256(inspector_jar) if inspector_jar.is_file() else None
        value["startedAt"] = utc_now()
        atomic_json(self.active, value)
        return value

    def deploy_inspector(self, game_dir: Path, modthespire: Path) -> str:
        basemod = game_dir / "mods/BaseMod.jar"
        game_jar = game_dir / "desktop-1.0.jar"
        for path in (modthespire, basemod, game_jar):
            if not path.is_file():
                raise RuntimeFailure(f"Java mod deployment dependency missing: {path}")
        run([str(self.repo / "mods/sts-model-inspector/build.sh"), str(modthespire), str(basemod), str(game_jar)], self.repo)
        built = self.repo / "mods/sts-model-inspector/build/sts-model-inspector.jar"
        destination = game_dir / "mods/sts-model-inspector.jar"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}")
        try:
            shutil.copy2(built, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return sha256(destination)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("status", "ensure", "install", "repair-config", "deploy-inspector", "record-active"))
    result.add_argument("--runtime-dir", type=Path, default=default_runtime_root())
    result.add_argument("--config", type=Path, default=default_config_path())
    result.add_argument("--active-runtime", type=Path, default=default_active_path())
    result.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    result.add_argument("--advisor-source", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--game-dir", type=Path)
    result.add_argument("--modthespire-jar", type=Path)
    result.add_argument("--inspector-jar", type=Path)
    result.add_argument("--json", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    manager = RuntimeManager(args.repo_root, args.runtime_dir, args.config, args.active_runtime)
    try:
        if args.command == "status":
            value = manager.status()
            code = 0 if value["usable"] else 1
        elif args.command == "ensure":
            value = manager.ensure()
            code = 0
        elif args.command == "install":
            value = manager.install(args.advisor_source)
            code = 0
        elif args.command == "repair-config":
            value = {"changed": manager.repair_config(), "config": str(manager.config)}
            code = 0
        elif args.command == "deploy-inspector":
            if not args.game_dir or not args.modthespire_jar:
                raise RuntimeFailure("deploy-inspector requires --game-dir and --modthespire-jar")
            value = {"inspectorJarSha256": manager.deploy_inspector(args.game_dir, args.modthespire_jar)}
            code = 0
        else:
            if not args.inspector_jar:
                raise RuntimeFailure("record-active requires --inspector-jar")
            value = manager.record_active(args.inspector_jar)
            code = 0
        if args.json:
            print(json.dumps(value, sort_keys=True))
        else:
            print(json.dumps(value, indent=2, sort_keys=True))
        return code
    except RuntimeFailure as exc:
        print(f"live-game-runtime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
