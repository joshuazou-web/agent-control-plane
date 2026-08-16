import unittest

from agent_control_plane.models import Proposal, Usage
from agent_control_plane.policy import decide, validate_policy


POLICY = {
    "agents": [
        {
            "id": "coder",
            "can": [
                {"action": "write", "target": "workspace/src/**"},
                {"action": "run", "command": "python --version"},
            ],
            "gate": [
                {"action": "run", "command": "git push*"},
            ],
            "cannot": [
                {"action": "delete", "target": "**"},
            ],
            "budget": {"tool_calls": 2, "minutes": 10},
        }
    ]
}


class PolicyTests(unittest.TestCase):
    def test_allows_matching_write(self):
        decision = decide(POLICY, Proposal(agent="coder", task="demo", action="write", target="workspace/src/app.py"))
        self.assertEqual(decision.decision, "allow")

    def test_gates_matching_command(self):
        decision = decide(POLICY, Proposal(agent="coder", task="demo", action="run", command="git push origin main"))
        self.assertEqual(decision.decision, "gate")

    def test_denies_destructive_action_before_allow(self):
        decision = decide(POLICY, Proposal(agent="coder", task="demo", action="delete", target="workspace/src/app.py"))
        self.assertEqual(decision.decision, "deny")

    def test_denies_unknown_agent(self):
        decision = decide(POLICY, Proposal(agent="unknown", task="demo", action="write", target="workspace/src/app.py"))
        self.assertEqual(decision.decision, "deny")

    def test_gates_allowed_action_when_budget_is_exhausted(self):
        decision = decide(
            POLICY,
            Proposal(agent="coder", task="demo", action="run", command="python --version"),
            Usage(tool_calls=2, elapsed_minutes=1),
        )
        self.assertEqual(decision.decision, "gate")
        self.assertEqual(decision.reason, "tool-call budget exhausted")

    def test_deny_rule_still_wins_when_budget_is_exhausted(self):
        decision = decide(
            POLICY,
            Proposal(agent="coder", task="demo", action="delete", target="workspace/src/app.py"),
            Usage(tool_calls=100, elapsed_minutes=100),
        )
        self.assertEqual(decision.decision, "deny")

    def test_validate_policy_rejects_duplicate_agent_and_bad_rule(self):
        invalid = {
            "agents": [
                {"id": "coder", "can": [{"action": "read", "target": "**", "command": "echo *"}]},
                {"id": "coder", "budget": {"tool_calls": 0}},
            ]
        }
        errors = validate_policy(invalid)
        self.assertTrue(any("both target and command" in error for error in errors))
        self.assertTrue(any("duplicate agent id" in error for error in errors))
        self.assertTrue(any("positive number" in error for error in errors))

    def test_denies_target_path_traversal(self):
        decision = decide(
            POLICY,
            Proposal(agent="coder", task="demo", action="write", target="workspace/src/../secrets.txt"),
        )
        self.assertEqual(decision.decision, "deny")
        self.assertIn("safe relative path", decision.reason)


if __name__ == "__main__":
    unittest.main()
