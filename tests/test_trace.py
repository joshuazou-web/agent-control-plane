import json
from pathlib import Path
import tempfile
import unittest

from agent_control_plane.models import PolicyDecision, Proposal
from agent_control_plane.trace import append_trace, verify_trace


class TraceTests(unittest.TestCase):
    def test_read_only_verification_does_not_create_task_directory(self):
        with tempfile.TemporaryDirectory() as raw_tmp_path:
            root = Path(raw_tmp_path)
            self.assertTrue(verify_trace(root, "missing")["valid"])
            self.assertFalse((root / "tasks" / "missing").exists())

    def test_task_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp_path:
            root = Path(raw_tmp_path)
            proposal = Proposal(agent="coder", task="../outside", action="read", target="workspace/file.txt")
            with self.assertRaises(ValueError):
                append_trace(root, proposal, PolicyDecision("allow", "test"))

    def test_new_entries_form_a_hash_chain(self):
        with tempfile.TemporaryDirectory() as raw_tmp_path:
            root = Path(raw_tmp_path)
            proposal = Proposal(agent="coder", task="demo", action="read", target="workspace/file.txt")
            first = append_trace(root, proposal, PolicyDecision("allow", "test"))
            second = append_trace(root, proposal, PolicyDecision("allow", "test"))
            self.assertEqual(second["previous_hash"], first["event_hash"])
            self.assertTrue(verify_trace(root, "demo")["valid"])

    def test_first_sealed_entry_anchors_legacy_entries(self):
        with tempfile.TemporaryDirectory() as raw_tmp_path:
            root = Path(raw_tmp_path)
            task_dir = root / "tasks" / "demo"
            task_dir.mkdir(parents=True)
            legacy = {"event_id": "legacy", "agent": "coder", "task": "demo", "decision": "allow"}
            (task_dir / "trace.jsonl").write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            proposal = Proposal(agent="coder", task="demo", action="read", target="workspace/file.txt")
            entry = append_trace(root, proposal, PolicyDecision("allow", "test"))
            self.assertTrue(entry["previous_hash"].startswith("legacy:"))
            verification = verify_trace(root, "demo")
            self.assertTrue(verification["valid"])
            self.assertEqual(verification["trace"]["legacy_entries"], 1)


if __name__ == "__main__":
    unittest.main()
