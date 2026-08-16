from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from .models import PolicyDecision, Proposal, Usage


class PolicyValidationError(ValueError):
    """Raised when a policy is unsafe or structurally invalid."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("invalid policy: " + "; ".join(errors))


def load_policy(root: Path) -> dict[str, Any]:
    agents_path = root / "agents.json"
    if not agents_path.exists():
        raise FileNotFoundError(f"Missing policy file: {agents_path}")
    with agents_path.open("r", encoding="utf-8") as f:
        policy = json.load(f)
    errors = validate_policy(policy)
    if errors:
        raise PolicyValidationError(errors)
    return policy


def decide(policy: dict[str, Any], proposal: Proposal, usage: Usage | None = None) -> PolicyDecision:
    agent = _find_agent(policy, proposal.agent)
    if agent is None:
        return PolicyDecision("deny", f"unknown agent: {proposal.agent}")
    if proposal.target is not None and not _is_safe_relative_target(proposal.target):
        return PolicyDecision("deny", "target must be a safe relative path")

    for rule in agent.get("cannot", []):
        if _matches(rule, proposal):
            return PolicyDecision("deny", "matched deny rule", rule)

    for rule in agent.get("gate", []):
        if _matches(rule, proposal):
            return PolicyDecision("gate", "matched gate rule", rule)

    for rule in agent.get("can", []):
        if _matches(rule, proposal):
            budget_decision = _check_budget(agent.get("budget", {}), usage)
            if budget_decision is not None:
                return budget_decision
            return PolicyDecision("allow", "matched allow rule", rule)

    return PolicyDecision("deny", "no allow rule matched")


def _find_agent(policy: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for agent in policy.get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    agents = policy.get("agents")
    if not isinstance(agents, list) or not agents:
        return ["agents must be a non-empty list"]

    seen_ids: set[str] = set()
    for index, agent in enumerate(agents):
        prefix = f"agents[{index}]"
        if not isinstance(agent, dict):
            errors.append(f"{prefix} must be an object")
            continue
        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            errors.append(f"{prefix}.id must be a non-empty string")
        elif agent_id in seen_ids:
            errors.append(f"duplicate agent id: {agent_id}")
        else:
            seen_ids.add(agent_id)

        for section in ("cannot", "gate", "can"):
            rules = agent.get(section, [])
            if not isinstance(rules, list):
                errors.append(f"{prefix}.{section} must be a list")
                continue
            for rule_index, rule in enumerate(rules):
                rule_prefix = f"{prefix}.{section}[{rule_index}]"
                if not isinstance(rule, dict):
                    errors.append(f"{rule_prefix} must be an object")
                    continue
                if not isinstance(rule.get("action"), str) or not rule["action"].strip():
                    errors.append(f"{rule_prefix}.action must be a non-empty string")
                selectors = [name for name in ("target", "command") if name in rule]
                if len(selectors) > 1:
                    errors.append(f"{rule_prefix} cannot contain both target and command")
                for selector in selectors:
                    if not isinstance(rule[selector], str) or not rule[selector].strip():
                        errors.append(f"{rule_prefix}.{selector} must be a non-empty string")

        budget = agent.get("budget", {})
        if not isinstance(budget, dict):
            errors.append(f"{prefix}.budget must be an object")
        else:
            for name in ("tool_calls", "minutes"):
                value = budget.get(name)
                if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0):
                    errors.append(f"{prefix}.budget.{name} must be a positive number")
    return errors


def _check_budget(budget: dict[str, Any], usage: Usage | None) -> PolicyDecision | None:
    if usage is None:
        return None
    tool_call_limit = budget.get("tool_calls")
    if tool_call_limit is not None and usage.tool_calls >= tool_call_limit:
        return PolicyDecision(
            "gate",
            "tool-call budget exhausted",
            {"budget": "tool_calls", "limit": tool_call_limit, "observed": usage.tool_calls},
        )
    minute_limit = budget.get("minutes")
    if minute_limit is not None and usage.elapsed_minutes >= minute_limit:
        return PolicyDecision(
            "gate",
            "time budget exhausted",
            {"budget": "minutes", "limit": minute_limit, "observed": round(usage.elapsed_minutes, 3)},
        )
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


def _is_safe_relative_target(target: str) -> bool:
    normalized = target.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        return False
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    return all(part not in {"", ".", ".."} for part in normalized.split("/"))
