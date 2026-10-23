"""Translation validation of shaped programs with the Lean checker."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Dict, List

from . import core as C

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(os.path.dirname(HERE), "proof", "ShapeCore.lean")


def payload(high: List[int], original: C.Stmt, padded: C.Stmt) -> Dict:
    return {"high": high, "original": C.stmt_json(original), "padded": C.stmt_json(padded)}


def lean_validate_batch(items: List[Dict], lean: str = None) -> List[Dict]:
    """Run the Lean validator on each payload; returns its JSON verdicts."""
    lean = lean or os.environ.get("LEAN", "lean")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "batch.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f)
        p = subprocess.run([lean, "--run", CHECKER, path], capture_output=True, text=True)
        if p.returncode == 2:
            raise RuntimeError(p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])


def lean_validate(high, original, padded, lean=None) -> Dict:
    return lean_validate_batch([payload(high, original, padded)], lean)[0]
