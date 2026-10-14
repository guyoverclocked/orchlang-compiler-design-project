"""Compile the SCP strengthening proofs into a disposable temporary tree."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scp-strengthening-review-") as name:
        temp = Path(name)
        library = temp / "publication_upgrade"
        strengthening = temp / "scp_strengthening"
        library.mkdir()
        strengthening.mkdir()
        shutil.copy2(ROOT / "proofs/publication_upgrade/AtomicUpdates.v", library / "AtomicUpdates.v")
        for source in ("SequentialUpdates", "Counterexamples", "Assumptions"):
            shutil.copy2(
                ROOT / f"proofs/scp_strengthening/{source}.v",
                strengthening / f"{source}.v",
            )

        commands = [
            ["coqc", "-q", "-noglob", "-Q", str(library), "PublicationUpgrade",
             str(library / "AtomicUpdates.v")],
            ["coqc", "-q", "-noglob", "-Q", str(library), "PublicationUpgrade",
             "-Q", str(strengthening), "SCPStrengthening", str(strengthening / "SequentialUpdates.v")],
            ["coqc", "-q", "-noglob", "-Q", str(library), "PublicationUpgrade",
             "-Q", str(strengthening), "SCPStrengthening", str(strengthening / "Counterexamples.v")],
            ["coqc", "-q", "-noglob", "-Q", str(library), "PublicationUpgrade",
             "-Q", str(strengthening), "SCPStrengthening", str(strengthening / "Assumptions.v")],
        ]
        print(subprocess.run(["coqc", "--version"], check=True, text=True, capture_output=True).stdout.strip())
        for index, command in enumerate(commands, 1):
            result = subprocess.run(command, text=True, capture_output=True)
            print(f"step {index}: exit={result.returncode}")
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip())
            if result.returncode:
                raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
