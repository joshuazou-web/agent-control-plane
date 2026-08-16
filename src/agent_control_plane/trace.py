from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import PolicyDecision, Proposal, Usage

GENESIS_HASH = "0" * 64


def task_dir(root: Path, task: str, *, create: bool = True) -> Path:
    if not task or task in {".", ".."} or "/" in task or "\\" in task:
        raise ValueError("task must be a single safe path segment")
    path = root / "tasks" / task
    if create:
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
    _append_chained_jsonl(path, entry)
    if decision.decision == "gate":
        _append_jsonl(task_dir(root, proposal.task) / "gates.jsonl", entry)
    return entry


def read_trace(root: Path, task: str) -> list[dict[str, Any]]:
    path = task_dir(root, task, create=False) / "trace.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_gate(root: Path, task: str, event_id: str) -> dict[str, Any] | None:
    for entry in read_trace(root, task):
        if entry.get("event_id") == event_id and entry.get("decision") == "gate":
            return entry
    return None


def append_approval(
    root: Path,
    task: str,
    gate: dict[str, Any],
    approver: str,
    decision: str = "approved",
    reason: str | None = None,
) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError(f"unsupported approval decision: {decision}")
    entry = {
        "approval_id": _approval_id(gate, approver),
        "time": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "gate_event_id": gate["event_id"],
        "approver": approver,
        "decision": decision,
        "reason": reason,
    }
    _append_chained_jsonl(task_dir(root, task) / "approvals.jsonl", entry)
    return entry


def read_approvals(root: Path, task: str) -> list[dict[str, Any]]:
    path = task_dir(root, task, create=False) / "approvals.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resolution_for_gate(root: Path, task: str, event_id: str) -> dict[str, Any] | None:
    for entry in reversed(read_approvals(root, task)):
        if entry.get("gate_event_id") == event_id:
            return entry
    return None


def task_usage(root: Path, task: str, agent: str) -> Usage:
    entries = [entry for entry in read_trace(root, task) if entry.get("agent") == agent]
    if not entries:
        return Usage()
    first_time = _parse_time(entries[0].get("time"))
    elapsed = 0.0
    if first_time is not None:
        elapsed = max(0.0, (datetime.now(timezone.utc) - first_time).total_seconds() / 60)
    return Usage(tool_calls=len(entries), elapsed_minutes=elapsed)


def verify_trace(root: Path, task: str) -> dict[str, Any]:
    trace_path = task_dir(root, task, create=False) / "trace.jsonl"
    approval_path = task_dir(root, task, create=False) / "approvals.jsonl"
    trace_result = _verify_chained_jsonl(trace_path)
    approval_result = _verify_chained_jsonl(approval_path)
    return {
        "valid": trace_result["valid"] and approval_result["valid"],
        "trace": trace_result,
        "approvals": approval_result,
    }


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _append_chained_jsonl(path: Path, entry: dict[str, Any]) -> None:
    existing = _read_jsonl(path)
    verification = _verify_entries(existing)
    if not verification["valid"]:
        raise RuntimeError(f"refusing to append to an invalid audit log: {path}")

    if not existing:
        previous_hash = GENESIS_HASH
    elif existing[-1].get("event_hash"):
        previous_hash = existing[-1]["event_hash"]
    else:
        previous_hash = _legacy_anchor(existing)

    entry["previous_hash"] = previous_hash
    entry["event_hash"] = _entry_hash(entry)
    _append_jsonl(path, entry)


def _verify_chained_jsonl(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"valid": True, "entries": 0, "sealed_entries": 0, "legacy_entries": 0, "errors": []}
    try:
        entries = _read_jsonl(path)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"valid": False, "entries": 0, "sealed_entries": 0, "legacy_entries": 0, "errors": [str(exc)]}
    return _verify_entries(entries)


def _verify_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    legacy_entries: list[dict[str, Any]] = []
    sealed_entries = 0
    expected_previous = GENESIS_HASH
    sealing_started = False

    for index, entry in enumerate(entries):
        has_hash = "event_hash" in entry or "previous_hash" in entry
        if not has_hash:
            if sealing_started:
                errors.append(f"entry {index} is unsealed after hash chaining started")
            legacy_entries.append(entry)
            continue

        if "event_hash" not in entry or "previous_hash" not in entry:
            errors.append(f"entry {index} has incomplete hash metadata")
            continue
        if not sealing_started and legacy_entries:
            expected_previous = _legacy_anchor(legacy_entries)
        sealing_started = True
        sealed_entries += 1
        if entry["previous_hash"] != expected_previous:
            errors.append(f"entry {index} previous_hash mismatch")
        calculated = _entry_hash(entry)
        if entry["event_hash"] != calculated:
            errors.append(f"entry {index} event_hash mismatch")
        expected_previous = entry["event_hash"]

    return {
        "valid": not errors,
        "entries": len(entries),
        "sealed_entries": sealed_entries,
        "legacy_entries": len(legacy_entries),
        "errors": errors,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: line {line_number} must be a JSON object")
        entries.append(value)
    return entries


def _entry_hash(entry: dict[str, Any]) -> str:
    payload = {key: value for key, value in entry.items() if key != "event_hash"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _legacy_anchor(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "legacy:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _approval_id(gate: dict[str, Any], approver: str) -> str:
    payload = json.dumps(
        {
            "gate_event_id": gate["event_id"],
            "approver": approver,
            "time": datetime.now(timezone.utc).isoformat(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
