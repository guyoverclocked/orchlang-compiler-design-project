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


def payload(high: List[int], original: C.Stmt, padded: C.Stmt, secrets: List[int]) -> Dict:
    """`secrets` are the declared secret input variables; the validator also checks
    that each is labelled high (theorem secret_inputs_sound)."""
    return {"high": high, "original": C.stmt_json(original), "padded": C.stmt_json(padded),
            "secret_inputs": sorted(secrets)}


def lean_validate_batch(items: List[Dict], lean: str = None) -> List[Dict]:
    """Run the Lean validator on each payload; returns its JSON verdicts."""
    lean = lean or os.environ.get("LEAN", "lean")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "batch.json")
        with open(path, "w", encoding="utf-8") as f:
            # Raw UTF-8: Lean's JSON parser does not join escaped UTF-16
            # surrogate pairs, so astral characters must not be escaped.
            json.dump(items, f, ensure_ascii=False)
        p = subprocess.run([lean, "--run", CHECKER, path], capture_output=True, text=True,encoding='utf-8')
        if p.returncode == 2:
            raise RuntimeError(p.stderr)
        if p.returncode not in (0,1):
            raise RuntimeError('Lean checker process failed: '+str(p.returncode))
        # JSON may contain literal U+0085/U+2028. splitlines() treats those as
        # record delimiters even inside a valid JSON string; only LF frames it.
        result=json.loads(p.stdout.rstrip('\r\n').rsplit('\n',1)[-1])
        if not isinstance(result,list) or len(result)!=len(items) or any(not isinstance(v,dict) or type(v.get('accepted')) is not bool for v in result):
            raise RuntimeError('Lean returned an invalid verdict denominator or schema')
        if (p.returncode==0)!=all(v['accepted'] for v in result):
            raise RuntimeError('Lean exit status disagrees with its verdicts')
        return result


def lean_validate(high, original, padded, secrets, lean=None) -> Dict:
    return lean_validate_batch([payload(high, original, padded, secrets)], lean)[0]
