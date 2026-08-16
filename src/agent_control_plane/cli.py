from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .bootstrap import init_project
from .models import PolicyDecision, Proposal
from .policy import PolicyValidationError, decide, load_policy
from .shell_adapter import run_shell
from .status import task_status
from .trace import (
    append_approval,
    append_trace,
    find_gate,
    read_trace,
    resolution_for_gate,
    task_dir,
    task_usage,
    verify_trace,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentcp")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("root")

    propose_parser = subparsers.add_parser("propose")
    _add_common(propose_parser)
    propose_parser.add_argument("--action", required=True)
    propose_parser.add_argument("--target")
    propose_parser.add_argument("--command")
    propose_parser.add_argument("--reason")

    check_parser = subparsers.add_parser("check", help="evaluate a proposal without recording or executing it")
    _add_common(check_parser)
    check_parser.add_argument("--action", required=True)
    check_parser.add_argument("--target")
    check_parser.add_argument("--command")
    check_parser.add_argument("--reason")

    run_parser = subparsers.add_parser("run-shell")
    _add_common(run_parser)
    run_parser.add_argument("--command", required=True)

    trace_parser = subparsers.add_parser("trace")
    trace_parser.add_argument("root")
    trace_parser.add_argument("--task", required=True)

    status_parser = subparsers.add_parser("status", help="summarize task decisions and unresolved gates")
    status_parser.add_argument("root")
    status_parser.add_argument("--task", required=True)

    verify_parser = subparsers.add_parser("verify", help="verify task audit-log integrity")
    verify_parser.add_argument("root")
    verify_parser.add_argument("--task", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate policy configuration")
    validate_parser.add_argument("root")

    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("root")
    approve_parser.add_argument("--task", required=True)
    approve_parser.add_argument("--event-id", required=True)
    approve_parser.add_argument("--approver", default="user")
    approve_parser.add_argument("--reason")
    approve_parser.add_argument("--execute", action="store_true")

    reject_parser = subparsers.add_parser("reject", help="reject a gated action")
    reject_parser.add_argument("root")
    reject_parser.add_argument("--task", required=True)
    reject_parser.add_argument("--event-id", required=True)
    reject_parser.add_argument("--approver", default="user")
    reject_parser.add_argument("--reason", required=True)

    args = parser.parse_args(argv)
    root = Path(getattr(args, "root")).resolve()

    if args.subcommand == "init":
        init_project(root)
        print(f"initialized {root}")
        return 0

    if hasattr(args, "task"):
        try:
            task_dir(root, args.task, create=False)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False))
            return 2

    if args.subcommand == "trace":
        print(json.dumps(read_trace(root, args.task), indent=2, ensure_ascii=False))
        return 0

    if args.subcommand == "status":
        payload = task_status(root, args.task)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["integrity"]["valid"] else 2

    if args.subcommand == "verify":
        payload = verify_trace(root, args.task)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["valid"] else 2

    try:
        policy = load_policy(root)
    except (FileNotFoundError, json.JSONDecodeError, PolicyValidationError) as exc:
        errors = exc.errors if isinstance(exc, PolicyValidationError) else [str(exc)]
        print(json.dumps({"valid": False, "errors": errors}, indent=2, ensure_ascii=False))
        return 2

    if args.subcommand == "validate":
        print(json.dumps({"valid": True, "agents": len(policy["agents"])}, indent=2, ensure_ascii=False))
        return 0

    if args.subcommand in {"approve", "reject"}:
        integrity = verify_trace(root, args.task)
        if not integrity["valid"]:
            print(
                json.dumps(
                    {"error": "audit log integrity check failed", "integrity": integrity},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2
        gate = find_gate(root, args.task, args.event_id)
        if gate is None:
            print(json.dumps({"error": "gate event not found", "event_id": args.event_id}, indent=2, ensure_ascii=False))
            return 2
        existing_resolution = resolution_for_gate(root, args.task, args.event_id)
        if existing_resolution is not None:
            print(
                json.dumps(
                    {"error": "gate already resolved", "event_id": args.event_id, "resolution": existing_resolution},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2
        if _gate_expired(root, gate):
            print(json.dumps({"error": "gate approval window expired", "event_id": args.event_id}, indent=2, ensure_ascii=False))
            return 2
        if args.subcommand == "reject":
            rejection = append_approval(root, args.task, gate, args.approver, decision="rejected", reason=args.reason)
            print(json.dumps({"rejection": rejection}, indent=2, ensure_ascii=False))
            return 0
        if args.execute:
            if gate.get("action") != "run" or not gate.get("command"):
                print(json.dumps({"error": "only gated run actions can execute", "event_id": args.event_id}, indent=2, ensure_ascii=False))
                return 2
        approval = append_approval(root, args.task, gate, args.approver, reason=args.reason)
        result = None
        replay = None
        if args.execute:
            proposal = Proposal(
                agent=gate["agent"],
                task=gate["task"],
                action=gate["action"],
                target=gate.get("target"),
                command=gate.get("command"),
                reason=f"approved by {args.approver} for gate {args.event_id}",
            )
            result = run_shell(proposal.command or "", root)
            replay = append_trace(
                root,
                proposal,
                decision=PolicyDecision(
                    "allow",
                    "approved gate",
                    {"approved_gate_event_id": args.event_id, "approver": args.approver},
                ),
                result=result,
            )
        print(json.dumps({"approval": approval, "executed": replay is not None, "trace": replay}, indent=2, ensure_ascii=False))
        return 0

    if args.subcommand in {"check", "propose"}:
        proposal = Proposal(
            agent=args.agent,
            task=args.task,
            action=args.action,
            target=args.target,
            command=args.command,
            reason=args.reason,
        )
        decision = decide(policy, proposal, task_usage(root, args.task, args.agent))
        if args.subcommand == "check":
            payload = {
                "proposal": {
                    "agent": proposal.agent,
                    "task": proposal.task,
                    "action": proposal.action,
                    "target": proposal.target,
                    "command": proposal.command,
                    "reason": proposal.reason,
                },
                "decision": decision.decision,
                "decision_reason": decision.reason,
                "rule": decision.rule,
                "recorded": False,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if decision.decision != "deny" else 2
        entry = append_trace(root, proposal, decision)
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return 0 if decision.decision != "deny" else 2

    if args.subcommand == "run-shell":
        proposal = Proposal(agent=args.agent, task=args.task, action="run", command=args.command)
        decision = decide(policy, proposal, task_usage(root, args.task, args.agent))
        result = None
        if decision.decision == "allow":
            result = run_shell(args.command, root)
        entry = append_trace(root, proposal, decision, result)
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return 0 if decision.decision != "deny" else 2

    return 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("root")
    parser.add_argument("--task", required=True)
    parser.add_argument("--agent", required=True)


def _gate_expired(root: Path, gate: dict[str, object]) -> bool:
    governance_path = root / "governance.json"
    if not governance_path.exists():
        return False
    try:
        governance = json.loads(governance_path.read_text(encoding="utf-8"))
        ttl = governance.get("approval_ttl_minutes")
        gate_time = datetime.fromisoformat(str(gate["time"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return False
    if ttl is None:
        return False
    if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
        return True
    if gate_time.tzinfo is None:
        gate_time = gate_time.replace(tzinfo=timezone.utc)
    elapsed_minutes = (datetime.now(timezone.utc) - gate_time.astimezone(timezone.utc)).total_seconds() / 60
    return elapsed_minutes > ttl


if __name__ == "__main__":
    raise SystemExit(main())
