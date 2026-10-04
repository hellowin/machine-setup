"""Check login-shell changes with fake account tools; never run real chsh."""
import shutil
import subprocess
import unittest

from test_updates import MockTests, ROOT


class DefaultShellTests(MockTests):
    def setUp(self):
        super().setUp()
        self.shells = self.base / "shells"
        self.shells.write_text(str(self.bin / "zsh") + "\n")
        self.state = self.base / "account-shell"
        self.state.write_text("/bin/bash")
        self.env.update(MOCK_SHELL_STATE=str(self.state), SHELL=str(self.bin / "zsh"),
                        USER="wrong-user", MOCK_SHELLS=str(self.shells))
        self.mock("id", "import sys\nassert sys.argv[1:]==['-un']\nprint('tester')\n")
        self.mock("getent", """import os,sys
from pathlib import Path
assert sys.argv[1:]==['passwd','tester']
print('tester:x:1000:1000::/home/tester:'+Path(os.environ['MOCK_SHELL_STATE']).read_text())
""")
        self.mock("dscl", """import os,sys
from pathlib import Path
assert sys.argv[1:]==['.','-read','/Users/tester','UserShell']
print('UserShell: '+Path(os.environ['MOCK_SHELL_STATE']).read_text())
""")
        self.mock("chsh", """import json,os,sys
from pathlib import Path
assert sys.argv[1]=='-s' and sys.argv[3]=='tester'
with open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(['chsh']+sys.argv[1:])+'\\n')
if os.environ.get('MOCK_CHSH_FAIL'): sys.exit(42)
if not os.environ.get('MOCK_CHSH_NO_CHANGE'):
    Path(os.environ['MOCK_SHELL_STATE']).write_text(sys.argv[2])
""")
        self.mock("sudo", """import json,os,sys
with open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(['sudo']+sys.argv[1:])+'\\n')
assert sys.argv[1]=='chsh'
os.execvp('chsh',sys.argv[1:])
""")

    def run_shell(self, platform="ubuntu", sudo="false"):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; platform=$1; sudo_enabled=$2; '
             '. "$3/scripts/default-shell.sh"; set_default_zsh "$4"',
             "test", platform, sudo, str(ROOT), str(self.shells)],
            env=self.env, capture_output=True, text=True)

    def test_ubuntu_sudo_change_targets_actual_account_and_rerun_skips(self):
        for _ in range(2):
            result = self.run_shell(sudo="true")
            self.assertEqual(result.returncode, 0, result.stderr)
        args = ["chsh", "-s", str(self.bin / "zsh"), "tester"]
        self.assertEqual(self.calls(), [["sudo"] + args, args])
        self.assertEqual(self.state.read_text(), str(self.bin / "zsh"))

    def test_no_sudo_and_macos_use_unprivileged_chsh(self):
        for platform, sudo in [("ubuntu", "false"), ("macos", "false"), ("macos", "true")]:
            with self.subTest(platform=platform, sudo=sudo):
                self.state.write_text("/bin/bash")
                result = self.run_shell(platform, sudo)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(call[0] == "chsh" for call in self.calls()))
        self.assertEqual(len(self.calls()), 3)

    def test_existing_zsh_is_preserved_even_with_stale_shell_environment(self):
        self.state.write_text("/usr/local/bin/zsh")
        self.env["SHELL"] = "/bin/bash"
        self.shells.unlink()
        self.assertEqual(self.run_shell().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_unregistered_path_uses_registered_executable_without_editing_list(self):
        registered = self.base / "registered" / "zsh"
        registered.parent.mkdir()
        shutil.copyfile(self.bin / "zsh", registered)
        registered.chmod(0o755)
        content = "# allowed shells\n/bin/bash\n" + str(registered) + "\n"
        self.shells.write_text(content)
        result = self.run_shell("macos")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_text(), str(registered))
        self.assertEqual(self.shells.read_text(), content)

    def test_missing_registration_or_shells_file_stops_without_chsh(self):
        self.shells.write_text("/bin/bash\n/missing/zsh\n")
        result = self.run_shell()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("administrator", result.stderr)
        self.shells.unlink()
        self.assertNotEqual(self.run_shell().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_lookup_failure_or_empty_record_stops_without_change(self):
        for code in ("import sys\nsys.exit(2)\n", "pass\n"):
            self.mock("getent", code)
            result = self.run_shell()
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_denied_or_ineffective_chsh_is_not_reported_as_success(self):
        for variable in ("MOCK_CHSH_FAIL", "MOCK_CHSH_NO_CHANGE"):
            self.env[variable] = "true"
            result = self.run_shell()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("administrator", result.stderr)
            self.env.pop(variable)
        self.assertEqual(self.state.read_text(), "/bin/bash")

    def test_setup_changes_shell_only_after_verification_and_reports_failure(self):
        checkout = self.base / "checkout"
        for folder in ("scripts", "config"):
            shutil.copytree(ROOT / folder, checkout / folder)
        for name in ("bootstrap.sh", ".machine-setup.yml", "mise.toml"):
            shutil.copyfile(ROOT / name, checkout / name)
        script = checkout / "scripts/setup.sh"
        script.write_text(script.read_text().replace('  set_default_zsh\n',
                                                    '  set_default_zsh "$MOCK_SHELLS"\n'))
        home = self.base / "home"
        (home / ".local/bin").mkdir(parents=True)
        (home / ".machine-setup.yml").write_text("sudoEnabled: false\n")
        mise = home / ".local/bin/mise"
        mise.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then touch \"$HOME/verified\"; fi\n")
        mise.chmod(0o755)
        self.env["XDG_CONFIG_HOME"] = str(home / ".config")
        self.env["MOCK_CHSH_FAIL"] = "true"
        result = self.run_setup("ubuntu", root=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((home / "verified").exists())
        self.assertIn("activate zsh", (home / ".zshrc").read_text())
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn("Setup complete", result.stdout)
        self.env.pop("MOCK_CHSH_FAIL")
        result = self.run_setup("ubuntu", root=checkout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Setup complete", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
