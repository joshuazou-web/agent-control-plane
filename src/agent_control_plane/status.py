from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .trace import read_approvals, read_trace, verify_trace


def task_status(root: Path, task: str) -> dict[str, Any]:
    entries = read_trace(root, task)
    approvals = read_approvals(root, task)
    resolutions = {entry.get("gate_event_id"): entry for entry in approvals}
    open_gates = [
        entry
        for entry in entries
        if entry.get("decision") == "gate" and entry.get("event_id") not in resolutions
    ]
    decisions = Counter(str(entry.get("decision", "unknown")) for entry in entries)
    agents = Counter(str(entry.get("agent", "unknown")) for entry in entries)
    integrity = verify_trace(root, task)
    return {
        "task": task,
        "state": "waiting_for_approval" if open_gates else ("active" if entries else "not_started"),
        "events": len(entries),
        "decisions": dict(sorted(decisions.items())),
        "agents": dict(sorted(agents.items())),
        "open_gates": [
            {
                "event_id": gate.get("event_id"),
                "agent": gate.get("agent"),
                "action": gate.get("action"),
                "subject": gate.get("command") or gate.get("target"),
                "time": gate.get("time"),
            }
            for gate in open_gates
        ],
        "resolutions": len(approvals),
        "integrity": integrity,
    }
