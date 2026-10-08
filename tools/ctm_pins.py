#!/usr/bin/env python3
"""Research-only identity pins for retraining the CTM stack on a new corpus.

The CTM training, export and qualification tools pin the production corpus,
split, prepared arrays, checkpoints and row counts as module constants.  A
retrain on another corpus (#418 Path B) replaces those constants through one
JSON file named by ``STS_CTM_PINS``; nothing else reads the file.

Unset (the default), ``value(key, default)`` returns ``default`` unchanged and
``receipt()`` is empty, so every tool behaves and records exactly as before.

Set, the file must use schema ``ctm_retrain_pins_v1`` with a flat ``pins``
object.  ``value`` then requires the key (fail closed) unless the call passes
``required=False``, which keeps the production default for warm starts the
retrain deliberately reuses.  ``receipt()`` returns the file's SHA256 so
outputs record which pins produced them.

`python tools/ctm_pins.py` lists every key with its production default.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ENV = "STS_CTM_PINS"
SCHEMA = "ctm_retrain_pins_v1"
_cache: tuple[str, dict, str] | None = None


def _load() -> tuple[dict, str] | None:
    global _cache
    path = os.environ.get(ENV)
    if not path:
        return None
    if _cache is None or _cache[0] != path:
        raw = Path(path).read_bytes()
        data = json.loads(raw)
        if data.get("schema") != SCHEMA or not isinstance(data.get("pins"), dict):
            raise ValueError(f"{ENV}={path} is not a {SCHEMA} file")
        _cache = (path, data["pins"], hashlib.sha256(raw).hexdigest())
    return _cache[1], _cache[2]


def active() -> bool:
    return _load() is not None


def value(key: str, default, required: bool = True):
    """Return the pinned value for ``key``; ``default`` when pins are inactive."""
    loaded = _load()
    if loaded is None:
        return default
    pins, _ = loaded
    if key in pins:
        return pins[key]
    if required:
        raise KeyError(f"{ENV} pins file has no {key!r}")
    return default


def receipt() -> dict:
    """Provenance to merge into a receipt: empty unless pins are active."""
    loaded = _load()
    return {} if loaded is None else {"ctmPinsSha256": loaded[1]}


def strip(obj):
    """``obj`` without the receipt key ``json_dump`` adds under pins.

    A tool that re-reads its own JSON output and compares it with the value it
    wrote (a recipe, or a checkpoint's embedded metadata) compares the
    stripped object; the pins file may also differ between chain stages.
    """
    if isinstance(obj, dict) and "ctmPinsSha256" in obj:
        return {k: v for k, v in obj.items() if k != "ctmPinsSha256"}
    return obj


def declared_keys(root: Path | None = None) -> dict[str, str]:
    """Map every ``_pins.value`` key in ``tools/`` to its production default's source text."""
    import ast
    root = root or Path(__file__).resolve().parent
    keys: dict[str, str] = {}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "value" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "_pins"):
                key = node.args[0]
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    raise ValueError(f"{path.name}:{node.lineno}: pin key must be a string literal")
                if not key.value.startswith(path.stem + "."):
                    raise ValueError(f"{path.name}:{node.lineno}: pin key {key.value!r} must start with {path.stem}.")
                if key.value in keys:
                    raise ValueError(f"{path.name}:{node.lineno}: duplicate pin key {key.value!r}")
                keys[key.value] = ast.unparse(node.args[1])
    return keys


if __name__ == "__main__":
    # List the keys a pins file must provide, with the production defaults.
    print(json.dumps(declared_keys(), indent=1, sort_keys=True))
