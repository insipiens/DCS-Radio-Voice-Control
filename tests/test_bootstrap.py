from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_project_uses_the_new_package_and_hook_identity(self) -> None:
        self.assertTrue((ROOT / "src" / "dcs_radio_voice_control").is_dir())
        self.assertFalse((ROOT / "src" / "combatai").exists())
        self.assertTrue((ROOT / "dcs" / "DCSRadioVoiceControl.radio_hook.lua").is_file())
        self.assertFalse((ROOT / "dcs" / "CombatAI.radio_hook.lua").exists())

    def test_runtime_is_pinned_and_hash_verified(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn('$PythonVersion = "3.13.15"', setup)
        self.assertIn("https://www.python.org/ftp/python/3.13.15/", setup)
        match = re.search(r'\$PythonSha256 = "([0-9a-f]+)"', setup)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(len(match.group(1)), 64)
        self.assertIn("Get-FileHash", setup)
        self.assertNotIn("get-pip", setup.lower())

    def test_entry_points_use_only_private_python(self) -> None:
        for filename in (
            "install.bat",
            "configuration.bat",
            "microphone.bat",
            "recording-test.bat",
            "radio-menu-test.bat",
            "run.bat",
            "transcription-test.bat",
            "uninstall.bat",
        ):
            content = (ROOT / filename).read_text(encoding="utf-8")
            self.assertTrue("runtime\\python.exe" in content or "runtime\\pythonw.exe" in content, filename)
            self.assertNotIn("py -", content.lower(), filename)

    def test_first_install_chains_configuration_into_voice_control(self) -> None:
        installer = (ROOT / "install.bat").read_text(encoding="utf-8")
        self.assertIn("configuration_store import setup_complete", installer)
        self.assertIn("DRVC_FIRST_RUN", installer)
        self.assertNotIn('if exist "%DRVC_CONFIG%"', installer)
        self.assertIn("configuration.bat\" --close-after-save", installer)
        self.assertIn('if "%DRVC_CONFIG_EXIT%"=="10" goto start_voice_control', installer)
        self.assertIn('call "%~dp0run.bat"', installer)

    def test_user_runner_launches_voice_control(self) -> None:
        runner = (ROOT / "run.bat").read_text(encoding="utf-8")
        diagnostic = (ROOT / "radio-menu-test.bat").read_text(encoding="utf-8")
        self.assertIn("-m dcs_radio_voice_control.launcher", runner)
        self.assertIn("runtime\\pythonw.exe", runner.casefold())
        self.assertIn("--tray", runner)
        self.assertIn("-m dcs_radio_voice_control", diagnostic)
        self.assertNotIn("voice_command_test", diagnostic)

    def test_sdl_controller_runtime_is_pinned_and_hash_verified(self) -> None:
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn('$PygameVersion = "2.5.8"', setup)
        self.assertIn("pygame_ce-2.5.8-cp313-cp313-win_amd64.whl", setup)
        match = re.search(r'\$PygameSha256 = "([0-9a-f]+)"', setup)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(len(match.group(1)), 64)
        self.assertIn("pygame.version.ver", setup)

    def test_stt_setup_pins_worker_and_supported_models(self) -> None:
        setup = (ROOT / "setup-stt.ps1").read_text(encoding="utf-8")
        self.assertIn('$WhisperVersion = "b4938"', setup)
        self.assertIn("whisper-bin-x64.zip", setup)
        self.assertIn("whisper-cublas-12.4.0-bin-x64.zip", setup)
        self.assertIn('[ValidateSet("auto", "cpu", "cuda12")]', setup)
        self.assertIn("dcs_radio_voice_control-whisper.exe", setup)
        self.assertIn('[string]$Compute = "auto"', setup)
        self.assertIn("whisper-server.exe", setup)
        self.assertIn("ggml-base.en.bin", setup)
        self.assertIn("ggml-small.en.bin", setup)
        self.assertIn("ggml-medium.en.bin", setup)
        self.assertGreaterEqual(setup.count("Get-FileHash"), 3)
        self.assertIn("System.Diagnostics.ProcessStartInfo", setup)
        self.assertEqual(setup.count("ReadToEndAsync()"), 2)
        self.assertNotIn("pip install", setup.lower())

    def test_installer_elevates_only_mutating_commands(self) -> None:
        installer = (ROOT / "tools" / "install.py").read_text(encoding="utf-8")
        self.assertIn('info.lpVerb = "runas"', installer)
        self.assertIn('args.command in ("install", "uninstall")', installer)

    def test_installer_starts_with_isolated_python_path(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools" / "install.py"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
