# Threat model

This document states what Agent Control Plane protects, what it assumes, and what it does not claim to solve.

## Assets

- Tool authority granted to each agent.
- Human approval decisions.
- The sequence and contents of task audit events.
- Execution results captured by adapters.
- Resource budgets assigned to agents.

## Trust assumptions

- Agents invoke tools through the control plane instead of bypassing it.
- The host, Python interpreter, and repository configuration are trusted.
- Policy and governance files are writable only by authorized operators.
- Approver identity supplied to the local CLI is an audit label, not strong authentication.
- The operating system provides process and filesystem isolation where required.

## Threats addressed

| Threat | Control |
|---|---|
| Unknown agent requests authority | Unknown identities fail closed |
| Broad allow overlaps a destructive deny | Deny rules have highest precedence |
| Sensitive action executes without review | Gate rules pause before adapter execution |
| Approval is replayed | Gate resolutions are one-shot |
| Old pending approval is used later | Approval TTL expires stale gates |
| Agent exceeds assigned task budget | Allowed actions become gates at the limit |
| Audit entry is edited or reordered | Linked SHA-256 hashes fail verification |
| Invalid policy silently weakens controls | Structural validation fails closed |
| Command never returns | Shell adapter records a 120-second timeout |

## Non-goals

- Preventing a privileged host user from deleting the entire task directory.
- Sandboxing arbitrary shell commands.
- Authenticating a local `--approver` string.
- Protecting secrets that are printed by an executed command.
- Detecting semantic command equivalence or every shell-obfuscation technique.
- Coordinating distributed writes from multiple processes.

For stronger deployments, combine this kernel with OS/container isolation, authenticated approval services, immutable remote logging, secret redaction, and structured tool adapters.

## Fail-closed behavior

Policy loading fails when the file is missing, malformed, or structurally invalid. Unknown agents and unmatched actions are denied. An invalid hash chain refuses new chained appends, preserving evidence instead of extending a corrupted history.

## Legacy audit logs

Version `0.1.x` wrote unsealed JSONL. Version `0.2.x` accepts a contiguous legacy prefix and anchors its canonical digest in the first sealed event. After sealing begins, any later unsealed event is invalid. A legacy-only log is readable but does not become tamper-evident until a sealed event is appended.
