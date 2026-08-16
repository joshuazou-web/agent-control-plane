# Agent Control Plane

[![CI](https://github.com/joshuazou-web/agent-control-plane/actions/workflows/ci.yml/badge.svg)](https://github.com/joshuazou-web/agent-control-plane/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)

**Turn agent rules from prompt text into enforceable runtime decisions.**

Agent Control Plane is a small, dependency-free Python kernel that sits between an AI agent and its tools. Every proposed action is evaluated as `allow`, `gate`, or `deny`, then recorded in a tamper-evident audit trail.

```text
agent proposal
      │
      ▼
┌──────────────┐     deny     ┌─────────────┐
│ policy engine├─────────────►│ audit trail │
└──────┬───────┘              └─────────────┘
       │ allow / gate                ▲
       ▼                             │
┌──────────────┐  approval  ┌────────┴───────┐
│ tool adapter │◄───────────┤ human reviewer│
└──────────────┘            └────────────────┘
```

It does not make an agent smarter. It makes the agent's authority explicit, reviewable, and harder to bypass accidentally.

## What is enforced

| Control | Behavior |
|---|---|
| Default deny | Unmatched actions do not execute |
| Rule precedence | `cannot` → explicit `gate` → `can` + budget → deny |
| Human gates | Sensitive actions pause until approved or rejected |
| One-shot resolution | A gate cannot be approved, rejected, or executed twice |
| Approval TTL | Stale gates expire instead of remaining executable forever |
| Runtime budgets | Per-agent tool-call and elapsed-time limits become gates |
| Audit integrity | Trace and approval logs use linked SHA-256 hashes |
| Policy validation | Invalid agents, rules, selectors, and budgets fail closed |
| Dry-run checks | Decisions can be explained without execution or recording |

## Quick start

Requires Python 3.11+.

```powershell
python -m pip install -e .
agentcp init examples/local-demo
agentcp validate examples/local-demo
```

Evaluate an action without changing state:

```powershell
agentcp check examples/local-demo --task release --agent coder --action write --target workspace/src/app.py
```

Run an allowed command, then propose one that requires approval:

```powershell
agentcp run-shell examples/local-demo --task release --agent coder --command "python --version"
agentcp run-shell examples/local-demo --task release --agent coder --command "git push"
agentcp status examples/local-demo --task release
```

Resolve the gate using the `event_id` returned by the second command:

```powershell
agentcp approve examples/local-demo --task release --event-id <event_id> --approver josh --reason "release reviewed" --execute

# Or close it without execution:
agentcp reject examples/local-demo --task release --event-id <event_id> --approver josh --reason "release window closed"
```

Verify that stored audit events have not been edited or reordered:

```powershell
agentcp verify examples/local-demo --task release
agentcp trace examples/local-demo --task release
```

## Policy model

`agents.json` defines authority by agent identity. Rules use case-sensitive shell-style glob patterns.

```json
{
  "agents": [
    {
      "id": "coder",
      "can": [
        {"action": "read", "target": "workspace/**"},
        {"action": "write", "target": "workspace/src/**"},
        {"action": "run", "command": "python -m pytest*"}
      ],
      "gate": [
        {"action": "run", "command": "git push*"},
        {"action": "run", "command": "*publish*"}
      ],
      "cannot": [
        {"action": "delete", "target": "**"},
        {"action": "run", "command": "rm -rf*"}
      ],
      "budget": {"tool_calls": 40, "minutes": 20}
    }
  ]
}
```

The evaluation order is deliberate:

1. Unknown agents are denied.
2. A matching `cannot` rule always denies.
3. A matching explicit `gate` rule pauses for human review.
4. A matching `can` rule is checked against the task budget.
5. Everything else is denied.

This keeps policy behavior deterministic and makes destructive rules win over broad allow rules.

## Task records

Each task is resumable and self-contained:

```text
project/
├── agents.json
├── governance.json
├── workspace/
└── tasks/
    └── release/
        ├── approvals.jsonl
        ├── gates.jsonl
        └── trace.jsonl
```

New trace and approval events are hash-linked. Existing `0.1.x` logs remain readable; the first new event anchors their complete legacy prefix. The verifier reports how many entries are legacy and how many are sealed.

## CLI

| Command | Purpose | Mutates state |
|---|---|---|
| `init` | Create a governed project | Yes |
| `validate` | Validate `agents.json` | No |
| `check` | Explain a policy decision | No |
| `propose` | Decide and record a non-shell action | Yes |
| `run-shell` | Decide, optionally execute, and record a command | Yes |
| `approve` | Approve a gate, optionally executing a shell action | Yes |
| `reject` | Reject and close a gate | Yes |
| `status` | Summarize task decisions and open gates | No |
| `verify` | Verify audit hash chains | No |
| `trace` | Print the task event stream | No |

## Architecture

The kernel remains intentionally compact, but its boundaries are explicit:

| Module | Responsibility |
|---|---|
| `policy.py` | Validate policies and return deterministic decisions |
| `trace.py` | Append, resolve, migrate, and verify audit events |
| `status.py` | Derive task state and unresolved gates from event history |
| `shell_adapter.py` | Execute bounded shell commands and capture results |
| `cli.py` | Orchestrate policy, approval, execution, and reporting |

Adapters are replaceable. The policy engine and audit trail do not depend on a particular model provider or agent framework.

## Security boundary

Agent Control Plane is an enforcement and audit layer, **not an operating-system sandbox**. A process that can edit the policy, delete the audit directory, or call tools outside the control plane is already outside its trust boundary. Hash chains reveal modification or reordering; they do not prevent deletion or protect against a compromised host.

See [Threat model](docs/THREAT_MODEL.md) for assets, assumptions, covered threats, and explicit non-goals.

## Development

The runtime has no third-party dependencies. Tests use the Python standard library:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests -v
```

CI runs the suite on Python 3.11, 3.12, and 3.13.

## Roadmap

- signed approvals and pluggable identity providers
- SQLite and remote append-only audit stores
- structured command adapters that avoid shell parsing
- policy version pinning per task
- OpenTelemetry events and webhook approval backends

The project is alpha software. Use it as a governance kernel or reference architecture, not as a substitute for host isolation.
