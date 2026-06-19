from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from .models import PolicyDecision, Proposal


def load_policy(root: Path) -> dict[str, Any]:
    agents_path = root / "agents.json"
    if not agents_path.exists():
        raise FileNotFoundError(f"Missing policy file: {agents_path}")
    with agents_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def decide(policy: dict[str, Any], proposal: Proposal) -> PolicyDecision:
    agent = _find_agent(policy, proposal.agent)
    if agent is None:
        return PolicyDecision("deny", f"unknown agent: {proposal.agent}")

    for rule in agent.get("cannot", []):
        if _matches(rule, proposal):
            return PolicyDecision("deny", "matched deny rule", rule)

    for rule in agent.get("gate", []):
        if _matches(rule, proposal):
            return PolicyDecision("gate", "matched gate rule", rule)

    for rule in agent.get("can", []):
        if _matches(rule, proposal):
            return PolicyDecision("allow", "matched allow rule", rule)

    return PolicyDecision("deny", "no allow rule matched")


def _find_agent(policy: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for agent in policy.get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def _matches(rule: dict[str, Any], proposal: Proposal) -> bool:
    if rule.get("action") != proposal.action:
        return False

    if "target" in rule:
        target = proposal.target or ""
        return fnmatch.fnmatchcase(target, rule["target"])

    if "command" in rule:
        command = proposal.command or ""
        return fnmatch.fnmatchcase(command, rule["command"])

    return True

