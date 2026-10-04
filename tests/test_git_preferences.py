"""Real Git config tests with isolated homes; bootstrap fetches are simulated."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


class GitPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"))
        tools = self.home / "editor-bin"
        tools.mkdir()
        vim = tools / "vim"
        vim.write_text("#!/bin/sh\nexit 0\n")
        vim.chmod(0o755)
        self.env["PATH"] = str(tools) + os.pathsep + os.environ["PATH"]
        for name in ("GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_CONFIG_COUNT"):
            self.env.pop(name, None)

    def git(self, *args):
        return subprocess.run([GIT, *args], env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def preferences(self, prefix=""):
        return subprocess.run(["bash", "-c", prefix + 'set -euo pipefail; setup_dir=$1; '
                               '. "$1/scripts/git.sh"; setup_git_preferences', "test", str(ROOT)],
                              env=self.env, capture_output=True, text=True)

    def test_vim_overrides_previous_editors_and_reruns_do_not_duplicate(self):
        self.git("config", "--global", "core.editor", "nano")
        self.git("config", "--global", "sequence.editor", "nano")
        self.git("config", "--global", "alias.st", "status")
        for _ in range(2):
            result = self.preferences()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("var", "GIT_EDITOR"), "vim")
        self.assertEqual(self.git("var", "GIT_SEQUENCE_EDITOR"), "vim")
        self.assertEqual(self.git("config", "alias.st"), "status")
        includes = self.git("config", "--global", "--get-all", "include.path").splitlines()
        self.assertEqual(includes, [str(ROOT / "config/git.gitconfig")])

    def test_missing_vim_does_not_write_git_configuration(self):
        result = self.preferences('command() { if [ "$*" = "-v vim" ]; then return 1; fi; builtin command "$@"; }; ')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Install vim manually", result.stderr)
        self.assertFalse((self.home / ".gitconfig").exists())

    def test_broken_global_configuration_fails_without_overwrite(self):
        path = self.home / ".gitconfig"
        path.write_text("[invalid\n")
        result = self.preferences()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), "[invalid\n")

    def bootstrap(self, origin, rewrite=False):
        checkout = self.home / "checkout"
        checkout.mkdir()
        (self.home / ".machine-setup.yml").write_text("sudoEnabled: false\n")
        (checkout / "scripts").mkdir()
        (checkout / "scripts/setup.sh").write_text('setup_main() { echo "Simulated setup reached"; }\n')
        self.git("init", str(checkout))
        self.git("-C", str(checkout), "add", ".")
        self.git("-C", str(checkout), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgSign=false", "commit", "-m", "fixture")
        self.git("-C", str(checkout), "remote", "add", "origin", origin)
        if rewrite:
            self.git("config", "--global", "url.git@github.com:.insteadOf", "https://github.com/")
        binary = self.home / "bin"
        binary.mkdir()
        wrapper = binary / "git"
        wrapper.write_text(f"#!{sys.executable}\nimport os, sys\n"
                           "args=sys.argv[1:]\n"
                           "if len(args)>2 and args[0]=='-C' and args[2] in ('fetch','merge'): sys.exit(0)\n"
                           f"os.execv({GIT!r}, [{GIT!r}]+args)\n")
        wrapper.chmod(0o755)
        xcode = binary / "xcode-select"
        xcode.write_text("#!/bin/sh\nexit 0\n")
        xcode.chmod(0o755)
        self.env.update(PATH=str(binary) + os.pathsep + os.environ["PATH"], MACHINE_SETUP_DIR=str(checkout))
        return subprocess.run(["bash", "-c", (ROOT / "bootstrap.sh").read_text()],
                              env=self.env, capture_output=True, text=True)

    def test_bootstrap_accepts_stored_https_with_workspace_url_rewrite(self):
        result = self.bootstrap("https://github.com/hellowin/machine-setup.git", rewrite=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Simulated setup reached", result.stdout)

    def test_bootstrap_accepts_equivalent_ssh_origin(self):
        result = self.bootstrap("git@github.com:hellowin/machine-setup.git")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bootstrap_rejects_different_repository(self):
        result = self.bootstrap("https://github.com/other/machine-setup.git", rewrite=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different origin", result.stderr)
        self.assertNotIn("Simulated setup reached", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
