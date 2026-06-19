from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import PolicyDecision, Proposal


def task_dir(root: Path, task: str) -> Path:
    path = root / "tasks" / task
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_trace(root: Path, proposal: Proposal, decision: PolicyDecision, result: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "event_id": _event_id(proposal, decision),
        "time": datetime.now(timezone.utc).isoformat(),
        "agent": proposal.agent,
        "task": proposal.task,
        "action": proposal.action,
        "target": proposal.target,
        "command": proposal.command,
        "reason": proposal.reason,
        "decision": decision.decision,
        "decision_reason": decision.reason,
        "rule": decision.rule,
        "result": result,
    }
    path = task_dir(root, proposal.task) / "trace.jsonl"
    _append_jsonl(path, entry)
    if decision.decision == "gate":
        _append_jsonl(task_dir(root, proposal.task) / "gates.jsonl", entry)
    return entry


def read_trace(root: Path, task: str) -> list[dict[str, Any]]:
    path = task_dir(root, task) / "trace.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _event_id(proposal: Proposal, decision: PolicyDecision) -> str:
    payload = json.dumps(
        {
            "agent": proposal.agent,
            "task": proposal.task,
            "action": proposal.action,
            "target": proposal.target,
            "command": proposal.command,
            "decision": decision.decision,
            "time": datetime.now(timezone.utc).isoformat(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

