import unittest

from agent_control_plane.models import Proposal
from agent_control_plane.policy import decide


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


if __name__ == "__main__":
    unittest.main()
