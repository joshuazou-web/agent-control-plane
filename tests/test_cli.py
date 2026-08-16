from pathlib import Path
import unittest

from agent_control_plane.cli import main
from agent_control_plane.trace import read_approvals, read_trace, verify_trace


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

    def test_check_does_not_record_proposal(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main([
                    "check",
                    str(tmp_path),
                    "--task",
                    "demo",
                    "--agent",
                    "coder",
                    "--action",
                    "write",
                    "--target",
                    "workspace/src/app.py",
                ]),
                0,
            )
            self.assertEqual(read_trace(tmp_path, "demo"), [])

    def test_cli_rejects_task_path_traversal(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(main(["trace", str(tmp_path), "--task", "../outside"]), 2)
            self.assertFalse((tmp_path / "outside").exists())

    def test_gate_can_only_be_resolved_once(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "git push"]),
                0,
            )
            gate_event_id = read_trace(tmp_path, "demo")[-1]["event_id"]
            command = ["approve", str(tmp_path), "--task", "demo", "--event-id", gate_event_id]
            self.assertEqual(main(command), 0)
            self.assertEqual(main(command), 2)
            self.assertEqual(len(read_approvals(tmp_path, "demo")), 1)

    def test_reject_closes_gate_without_execution(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "git push"]),
                0,
            )
            gate_event_id = read_trace(tmp_path, "demo")[-1]["event_id"]
            self.assertEqual(
                main([
                    "reject",
                    str(tmp_path),
                    "--task",
                    "demo",
                    "--event-id",
                    gate_event_id,
                    "--reason",
                    "release window closed",
                ]),
                0,
            )
            self.assertEqual(read_approvals(tmp_path, "demo")[-1]["decision"], "rejected")
            self.assertEqual(len(read_trace(tmp_path, "demo")), 1)

    def test_verify_detects_trace_tampering(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "python --version"]),
                0,
            )
            self.assertTrue(verify_trace(tmp_path, "demo")["valid"])
            trace_path = tmp_path / "tasks" / "demo" / "trace.jsonl"
            trace_path.write_text(trace_path.read_text(encoding="utf-8").replace('"decision": "allow"', '"decision": "deny"'), encoding="utf-8")
            self.assertFalse(verify_trace(tmp_path, "demo")["valid"])
            self.assertEqual(main(["verify", str(tmp_path), "--task", "demo"]), 2)

    def test_tampered_gate_cannot_be_approved(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "git push"]),
                0,
            )
            gate_event_id = read_trace(tmp_path, "demo")[-1]["event_id"]
            trace_path = tmp_path / "tasks" / "demo" / "trace.jsonl"
            trace_path.write_text(trace_path.read_text(encoding="utf-8").replace("git push", "git push --force"), encoding="utf-8")
            self.assertEqual(main(["approve", str(tmp_path), "--task", "demo", "--event-id", gate_event_id, "--execute"]), 2)
            self.assertEqual(read_approvals(tmp_path, "demo"), [])

    def test_status_reports_open_then_resolved_gate(self):
        with self._tmpdir() as raw_tmp_path:
            tmp_path = Path(raw_tmp_path)
            self.assertEqual(main(["init", str(tmp_path)]), 0)
            self.assertEqual(
                main(["run-shell", str(tmp_path), "--task", "demo", "--agent", "coder", "--command", "git push"]),
                0,
            )
            gate_event_id = read_trace(tmp_path, "demo")[-1]["event_id"]
            self.assertEqual(main(["status", str(tmp_path), "--task", "demo"]), 0)
            self.assertEqual(main(["approve", str(tmp_path), "--task", "demo", "--event-id", gate_event_id]), 0)
            self.assertEqual(main(["status", str(tmp_path), "--task", "demo"]), 0)

    def _tmpdir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
