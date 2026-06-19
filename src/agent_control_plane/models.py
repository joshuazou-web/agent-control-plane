from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["allow", "gate", "deny"]


@dataclass(frozen=True)
class Proposal:
    agent: str
    task: str
    action: str
    target: str | None = None
    command: str | None = None
    reason: str | None = None

    def subject(self) -> str:
        if self.command:
            return self.command
        return self.target or ""


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reason: str
    rule: dict[str, Any] | None = None

