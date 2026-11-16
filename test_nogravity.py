import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import nogravity as ng


class PatchSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nogravity-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "language_server.exe"
        self.original = b"MZ" + bytes(64) + b"ineligible\0https_proxy\0"
        self.path.write_bytes(self.original)
        self.backup = self.path.with_suffix(".exe.bak_original")
        self.path_mock = patch.object(ng, "get_ls_path", return_value=self.path)
        self.path_mock.start()
        self.addCleanup(self.path_mock.stop)
        self.proc_mock = patch.object(ng.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '"python.exe","1"\n', ""))
        self.run = self.proc_mock.start()
        self.addCleanup(self.proc_mock.stop)

    def test_patch_preserves_size_and_original(self):
        self.assertTrue(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(len(self.path.read_bytes()), len(self.original))
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(self.path.read_bytes(), ng.patched_bytes(self.original))

    def test_reapply_preserves_backup(self):
        ng.apply_nogravity_patch(silent=True)
        self.assertTrue(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_updated_version_archives_old_backup(self):
        old = b"MZold version ineligible"
        self.backup.write_bytes(old)
        self.assertTrue(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.backup.read_bytes(), self.original)
        archives = list(self.path.parent.glob("language_server.exe.*.bak_original"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), old)

    def test_proxy_hook_is_rejected_without_writes(self):
        source = self.original + b"AG_LS_PROXY"
        self.path.write_bytes(source)
        self.assertFalse(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.path.read_bytes(), source)
        self.assertFalse(self.backup.exists())

    def test_unknown_signature_is_rejected(self):
        self.path.write_bytes(b"MZunknown version")
        self.assertFalse(ng.apply_nogravity_patch(silent=True))
        self.assertFalse(self.backup.exists())

    def test_invalid_executable_is_rejected(self):
        with self.assertRaises(ValueError):
            ng.patched_bytes(b"not an exe ineligible")

    def test_running_app_is_never_killed_or_written(self):
        self.run.return_value.stdout = '"Antigravity.exe","10"\n'
        self.assertFalse(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())
        self.assertTrue(all(call.args[0][0] == "tasklist" for call in self.run.call_args_list))

    def test_process_check_failure_prevents_write(self):
        self.run.return_value.returncode = 1
        self.assertFalse(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_cli_patch_allows_desktop_to_keep_running(self):
        cli = self.path.with_name("agy.exe")
        cli.write_bytes(self.original)
        self.run.return_value.stdout = '"Antigravity.exe","10"\n'
        self.assertTrue(ng.apply_nogravity_patch(silent=True, path=cli))
        self.assertEqual(cli.read_bytes(), ng.patched_bytes(self.original))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_running_cli_is_not_written(self):
        cli = self.path.with_name("agy.exe")
        cli.write_bytes(self.original)
        self.run.return_value.stdout = '"agy.exe","10"\n'
        self.assertFalse(ng.apply_nogravity_patch(silent=True, path=cli))
        self.assertEqual(cli.read_bytes(), self.original)

    def test_all_installed_targets_have_separate_backups(self):
        cli = self.path.with_name("agy.exe")
        cli.write_bytes(self.original + b"CLI version")
        with patch.object(ng, "get_cli_path", return_value=cli):
            self.assertTrue(ng.apply_targets(silent=True))
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(cli.with_suffix(".exe.bak_original").read_bytes(), self.original + b"CLI version")

    def test_cli_only_install_is_found(self):
        cli = self.path.with_name("agy.exe")
        cli.write_bytes(self.original)
        self.path.unlink()
        with patch.object(ng, "get_cli_path", return_value=cli):
            self.assertEqual(ng.get_targets(), [("cli", cli)])
            self.assertTrue(ng.apply_targets(silent=True))

    def test_one_failure_does_not_skip_other_target(self):
        cli = self.path.with_name("agy.exe")
        cli.write_bytes(self.original)
        self.path.write_bytes(b"MZunknown version")
        with patch.object(ng, "get_cli_path", return_value=cli):
            self.assertFalse(ng.apply_targets(silent=True))
        self.assertEqual(cli.read_bytes(), ng.patched_bytes(self.original))

    def test_backup_failure_prevents_write(self):
        with patch.object(ng.shutil, "copy2", side_effect=PermissionError("blocked")):
            self.assertFalse(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_replace_failure_keeps_original_and_removes_temp(self):
        with patch.object(ng.os, "replace", side_effect=PermissionError("locked")):
            self.assertFalse(ng.apply_nogravity_patch(silent=True))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertFalse(self.path.with_suffix(".exe.tmp").exists())

    def test_stale_restore_refuses_before_confirmation_or_task_kill(self):
        self.backup.write_bytes(b"MZdifferent version ineligible")
        with patch("builtins.input", side_effect=AssertionError("must not prompt")), redirect_stdout(io.StringIO()):
            ng.restore_factory_original()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.run.assert_not_called()


class DiagnosisTests(unittest.TestCase):
    def test_server_location_is_detected_for_400_and_403(self):
        for code, body in [(400, "User location is not supported"), (403, "LOCATION_NOT_ELIGIBLE")]:
            with self.subTest(code=code):
                self.assertEqual(ng.http_verdict(code, body), "Серверный геоблок")

    def test_http_response_does_not_claim_account_access(self):
        for status in [200, 401, 403, 404, 429, 500]:
            with self.subTest(status=status):
                self.assertIn("не проверен", ng.http_verdict(status))

    def test_log_summary_reports_latest_error_without_credentials(self):
        with tempfile.TemporaryDirectory(prefix="nogravity-log-") as directory:
            path = Path(directory) / "language_server.log"
            path.write_text("W1115 12:00:00 LOCATION_NOT_ELIGIBLE Detected location: DE. Bearer SECRET\n"
                            "W1116 16:00:00 LOCATION_NOT_ELIGIBLE Detected location: RU. token=SECRET\n", encoding="utf-8")
            info = ng.recent_location_error(path)
            self.assertEqual(info["detected_location"], "RU")
            self.assertEqual(info["log_time"], "1116 16:00:00")
            self.assertNotIn("SECRET", json.dumps(info))

    def test_missing_log_is_unknown(self):
        self.assertIsNone(ng.recent_location_error(Path(tempfile.gettempdir()) / "nogravity-missing-log.txt"))


@unittest.skipUnless(os.name == "nt", "Windows launcher")
class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="NoGravity путь с пробелами ")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        for name in ["nogravity.py", "run_nogravity.bat"]:
            shutil.copy2(Path(__file__).parent / name, self.folder / name)
        self.fixture = self.folder / "language_server.exe"
        self.fixture.write_bytes(b"MZineligible")

    def run_launcher(self, env):
        env = env.copy()
        env["NOGRAVITY_LS_PATH"] = str(self.fixture)
        command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{self.folder / "run_nogravity.bat"}" --status --target desktop"'
        return subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)

    def test_unicode_and_spaces_in_launcher_path(self):
        result = self.run_launcher(os.environ)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["ls_path"], str(self.fixture))

    def test_python_install_without_path_is_found(self):
        env = os.environ.copy()
        env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
        result = self.run_launcher(env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_python_reports_error(self):
        env = os.environ.copy()
        env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
        for name in ["LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"]:
            env[name] = str(self.folder / "missing")
        result = self.run_launcher(env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Working Python 3.8+ was not found", result.stdout)


if __name__ == "__main__":
    unittest.main()
