"""Trusted source binding and immutable evidence custody around the untrusted shaper.

The Python parser/lowerer, serializer and this binding remain in the trusted base.
Lean validates shaping of the bound core; it does not verify this source reader.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from . import compiler as K, core as C, syntax, validate


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_binding(source: bytes, profiles):
    """Derive the original core and secret list from the actual source bytes."""
    text = source.decode("utf-8", errors="strict")
    program = K.lower(syntax.parse(text), profiles)
    binding = dict(schema="orchlang-source-binding-v1", source_sha256=hashlib.sha256(source).hexdigest(),
                   original=C.stmt_json(program.body), secret_inputs=program.secret_inputs(),
                   high=program.high_vars(), slots=program.slots,
                   trust="Python source reader/lowering and serialization; Lean checks the shaped core")
    binding["binding_sha256"] = hashlib.sha256(canonical(binding)).hexdigest()
    return program, binding


def validate_candidates(source: bytes, profiles, candidates, lean=None):
    """Candidate code cannot supply its own original program or secret labels."""
    program, binding = source_binding(source, profiles)
    names = list(candidates)
    items = [validate.payload(program.high_vars(), program.body, candidates[name], program.secret_inputs())
             for name in names]
    verdicts = validate.lean_validate_batch(items, lean)
    return program, binding, dict(zip(names, verdicts))


def check_artifact(source: bytes, profiles, artifact, lean=None):
    """Re-read the source; never trust the artifact's original or secret list."""
    program,binding=source_binding(source,profiles)
    if artifact.get('schema')!='orchlang-validation-artifact-v1' or artifact.get('source_binding')!=binding:
        raise ValueError('artifact does not bind the supplied source and declared secrets')
    declared={model.key for model in program.workflow.models}
    contracts=model_contracts({key:profiles[key] for key in declared})
    if artifact.get('model_contracts')!=contracts:
        raise ValueError('artifact model contracts differ from supplied model bytes')
    candidates=artifact['candidates']
    if not isinstance(candidates,dict) or not candidates or any(not isinstance(name,str) or not name for name in candidates):
        raise ValueError('artifact must contain a nonempty named candidate map')
    items=[dict(high=program.high_vars(),original=C.stmt_json(program.body),padded=body,
                secret_inputs=program.secret_inputs()) for body in candidates.values()]
    verdicts=validate.lean_validate_batch(items,lean)
    return dict(schema='orchlang-source-check-receipt-v1',source_binding_sha256=binding['binding_sha256'],
                model_contracts=contracts,verdicts=dict(zip(candidates,verdicts)),
                accepted=all(v['accepted'] for v in verdicts),
                assumptions=['trusted Python frontend and source binding','World.Conforms',
                             'World.Transparent for functional preservation','stated logical observer only'])


def implementation_hashes(root):
    root = Path(root)
    paths = [*sorted((root / "orchlang").glob("*.py")), root / "proof/ShapeCore.lean",
             root / "experiments/run_workflow.py"]
    return {path.relative_to(root).as_posix(): sha256(path) for path in paths}


def model_contracts(profiles):
    result = {}
    for key, profile in sorted(profiles.items()):
        entry = asdict(profile)
        entry.pop("gguf")
        if entry.get("decoding_grammar") is None:
            entry.pop("decoding_grammar", None)
        entry["gguf_sha256"] = sha256(profile.gguf)
        expected = getattr(profile, "sha256", None)
        if expected and expected != entry["gguf_sha256"]:
            raise ValueError("model bytes differ from declared artifact hash: " + key)
        result[key] = entry
    return result


def open_run(directory, manifest):
    """Resume only an exactly bound run; never relabel existing observations."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "run-manifest.json"
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        # Creating an output file or editing a paper can flip this workspace
        # flag without changing any executable input. Preserve its first-run
        # value as provenance; exact source/data/model hashes remain identity.
        identity=lambda value:{k:v for k,v in value.items() if k!='git_dirty'}
        if identity(previous) != identity(manifest):
            raise ValueError("resume fingerprint mismatch; use a new evidence directory")
    else:
        if any(directory.glob("*.jsonl")) or (directory / "compile.json").exists():
            raise ValueError("existing observations have no matching custody manifest")
        with target.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return target


def checked_record_ids(path, allowed):
    """Reject partial, duplicate and out-of-corpus records rather than skipping them."""
    path = Path(path)
    if not path.exists():
        return set()
    done = set()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] in done or row["id"] not in allowed:
                raise ValueError(f"duplicate or foreign record ID at line {number}: {row['id']}")
            done.add(row["id"])
    return done
