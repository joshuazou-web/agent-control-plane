from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bootstrap import init_project
from .models import PolicyDecision, Proposal
from .policy import decide, load_policy
from .shell_adapter import run_shell
from .trace import append_approval, append_trace, find_gate, read_trace


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

    run_parser = subparsers.add_parser("run-shell")
    _add_common(run_parser)
    run_parser.add_argument("--command", required=True)

    trace_parser = subparsers.add_parser("trace")
    trace_parser.add_argument("root")
    trace_parser.add_argument("--task", required=True)

    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("root")
    approve_parser.add_argument("--task", required=True)
    approve_parser.add_argument("--event-id", required=True)
    approve_parser.add_argument("--approver", default="user")
    approve_parser.add_argument("--execute", action="store_true")

    args = parser.parse_args(argv)
    root = Path(getattr(args, "root")).resolve()

    if args.subcommand == "init":
        init_project(root)
        print(f"initialized {root}")
        return 0

    if args.subcommand == "trace":
        print(json.dumps(read_trace(root, args.task), indent=2, ensure_ascii=False))
        return 0

    policy = load_policy(root)

    if args.subcommand == "approve":
        gate = find_gate(root, args.task, args.event_id)
        if gate is None:
            print(json.dumps({"error": "gate event not found", "event_id": args.event_id}, indent=2, ensure_ascii=False))
            return 2
        if args.execute:
            if gate.get("action") != "run" or not gate.get("command"):
                print(json.dumps({"error": "only gated run actions can execute", "event_id": args.event_id}, indent=2, ensure_ascii=False))
                return 2
        approval = append_approval(root, args.task, gate, args.approver)
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

    if args.subcommand == "propose":
        proposal = Proposal(
            agent=args.agent,
            task=args.task,
            action=args.action,
            target=args.target,
            command=args.command,
            reason=args.reason,
        )
        decision = decide(policy, proposal)
        entry = append_trace(root, proposal, decision)
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return 0 if decision.decision != "deny" else 2

    if args.subcommand == "run-shell":
        proposal = Proposal(agent=args.agent, task=args.task, action="run", command=args.command)
        decision = decide(policy, proposal)
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


if __name__ == "__main__":
    raise SystemExit(main())
