from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bootstrap import init_project
from .models import Proposal
from .policy import decide, load_policy
from .shell_adapter import run_shell
from .trace import append_trace, read_trace


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
