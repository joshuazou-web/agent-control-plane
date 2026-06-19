from pathlib import Path
import unittest

from agent_control_plane.cli import main
from agent_control_plane.trace import read_trace


class CliTests(unittest.TestCase):
    def test_run_shell_records_allowed_command(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "python --version"]),
                0,
            )
            entries = read_trace(tmp_path, "demo")
            self.assertEqual(entries[-1]["decision"], "allow")
            self.assertEqual(entries[-1]["result"]["returncode"], 0)

    def test_run_shell_gates_git_push(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "git push"]), 0)
            entries = read_trace(tmp_path, "demo")
            self.assertEqual(entries[-1]["decision"], "gate")
            self.assertIsNone(entries[-1]["result"])

    def test_approve_executes_gated_command(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "echo publish-test"]), 0)
            gate_event_id = read_trace(tmp_path, "demo")[-1]["event_id"]
            self.assertEqual(
                main([
                    "approve",
                    str(tmp_path),
                    "--task",
                    "demo",
                    "--event-id",
                    gate_event_id,
                    "--approver",
                    "user",
                    "--execute",
                ]),
                0,
            )
            entries = read_trace(tmp_path, "demo")
            self.assertEqual(entries[-1]["decision"], "allow")
            self.assertEqual(entries[-1]["decision_reason"], "approved gate")
            self.assertIsNotNone(entries[-1]["result"])

    def test_approve_missing_gate_fails(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(main(["approve", str(tmp_path), "--task", "demo", "--event-id", "missing"]), 2)

    def test_execute_non_run_gate_does_not_write_approval(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main([
                    "propose",
                    str(tmp_path),
                    "--task",
                    "demo",
                    "--agent",
                    "coder",
                    "--action",
                    "write",
                    "--target",
                    "pyproject.toml",
                ]),
                0,
            )
            gate_event_id = read_trace(tmp_path, "demo")[-1]["event_id"]
            self.assertEqual(main(["approve", str(tmp_path), "--task", "demo", "--event-id", gate_event_id, "--execute"]), 2)
            self.assertFalse((tmp_path / "tasks" / "demo" / "approvals.jsonl").exists())

    def _tmpdir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
