from __future__ import annotations

import subprocess
from pathlib import Path


def run_shell(command: str, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }

