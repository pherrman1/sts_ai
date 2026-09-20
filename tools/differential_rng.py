#!/usr/bin/env python3
"""Bounded preflight for the installed vanilla Java RNG implementation."""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any


def inspect_vanilla_rng(jar: Path) -> dict[str, Any]:
    jar = Path(jar)
    required = {
        "com/megacrit/cardcrawl/random/Random.class",
        "com/badlogic/gdx/math/RandomXS128.class",
    }
    try:
        with zipfile.ZipFile(jar) as archive:
            missing = sorted(required - set(archive.namelist()))
    except (OSError, zipfile.BadZipFile) as error:
        return {"available": False, "reason": f"jar_unreadable:{error}"}
    if missing:
        return {"available": False, "reason": "missing_classes", "missing": missing}
    try:
        result = subprocess.run(
            ["javap", "-classpath", str(jar), "-private", "com.megacrit.cardcrawl.random.Random"],
            text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "reason": f"javap_unavailable:{error}"}
    text = result.stdout + result.stderr
    checks = {
        "counter": bool(re.search(r"\bint counter;", text)),
        "random_xs128": "RandomXS128 random;" in text,
    }
    try:
        xs = subprocess.run(
            ["javap", "-classpath", str(jar), "-private", "com.badlogic.gdx.math.RandomXS128"],
            text=True, capture_output=True, timeout=10, check=False)
        xs_text = xs.stdout + xs.stderr
        checks.update({"seed0": bool(re.search(r"\blong seed0;", xs_text)),
                       "seed1": bool(re.search(r"\blong seed1;", xs_text)),
                       "get_state": "getState(int)" in xs_text})
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "reason": f"javap_xs128_unavailable:{error}", "checks": checks}
    return {"available": result.returncode == 0 and all(checks.values()),
            "jar": str(jar), "checks": checks,
            "captureContract": ["counter", "random.getState(0)", "random.getState(1)"],
            "reason": None if all(checks.values()) else "unexpected_random_class_layout"}
