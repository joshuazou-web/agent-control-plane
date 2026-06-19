from __future__ import annotations

import json
from pathlib import Path


DEFAULT_AGENTS = {
    "agents": [
        {
            "id": "coder",
            "name": "Code worker",
            "can": [
                {"action": "read", "target": "workspace/**"},
                {"action": "write", "target": "workspace/src/**"},
                {"action": "run", "command": "python --version"},
                {"action": "run", "command": "python -m pytest*"},
            ],
            "gate": [
                {"action": "write", "target": "pyproject.toml"},
                {"action": "run", "command": "git push*"},
                {"action": "run", "command": "*publish*"},
            ],
            "cannot": [
                {"action": "delete", "target": "**"},
                {"action": "run", "command": "Remove-Item*"},
                {"action": "run", "command": "rm -rf*"},
            ],
            "budget": {"tool_calls": 40, "minutes": 20},
        }
    ]
}

DEFAULT_GOVERNANCE = {
    "kernel": ["Agent", "Task", "Authority", "Trace", "Gate"],
    "loop": ["propose", "check", "execute", "record", "escalate"],
    "default_decision": "deny",
}


def init_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tasks").mkdir(exist_ok=True)
    (root / "workspace" / "src").mkdir(parents=True, exist_ok=True)
    _write_json(root / "agents.json", DEFAULT_AGENTS)
    _write_json(root / "governance.json", DEFAULT_GOVERNANCE)


def _write_json(path: Path, payload: dict) -> None:
    if path.exists():
        return
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

