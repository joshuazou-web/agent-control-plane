# Agent Control Plane

Minimal governance kernel for personal multi-agent workflows.

It does not create a smarter agent. It wraps existing agents and tools with:

- authority checks
- approval gates
- append-only traces
- resumable task folders
- replaceable adapters

Core loop:

```text
propose -> check -> execute -> record -> escalate
```

## Quick Start

```powershell
python -m pip install -e .
python -m agent_control_plane init examples/demo
python -m agent_control_plane propose examples/demo --task demo --agent coder --action write --target workspace/src/app.py
python -m agent_control_plane run-shell examples/demo --task demo --agent coder --command "python --version"
python -m agent_control_plane run-shell examples/demo --task demo --agent coder --command "git push"
python -m agent_control_plane trace examples/demo --task demo
```

`git push` is gated by the default policy, so it is recorded but not executed.

Approve and resume a gated command:

```powershell
python -m agent_control_plane approve examples/demo --task demo --event-id <gate_event_id> --execute
```

Approval writes `approvals.jsonl`, then records the resumed execution in `trace.jsonl`.

Tests use only the Python standard library:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```

## Files

```text
examples/demo/
├── agents.json
├── governance.json
└── tasks/
    └── demo/
        ├── approvals.jsonl
        ├── gates.jsonl
        └── trace.jsonl
```

## Design

The kernel only knows five primitives:

| Primitive | Role |
|---|---|
| Agent | who is acting |
| Task | what is being done |
| Authority | what is allowed |
| Trace | what happened |
| Gate | when to stop for approval |

Rules are intentionally small. Most policy should be machine-checkable instead of repeated in prompts.
