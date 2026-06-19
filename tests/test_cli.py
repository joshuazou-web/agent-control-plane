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

    def _tmpdir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
