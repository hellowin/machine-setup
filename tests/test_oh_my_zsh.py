"""Oh My Zsh integration checks using isolated homes and local Git remotes."""
from pathlib import Path
import shutil
import subprocess
import unittest

from test_updates import MockTests, ROOT


class OhMyZshTests(MockTests):
    def setUp(self):
        super().setUp()
        self.home = self.base / "home"
        self.home.mkdir()
        self.env["XDG_CONFIG_HOME"] = str(self.home / ".config")

    def run_omz(self):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; setup_dir=$1; '
             '. "$1/scripts/oh-my-zsh.sh"; preflight_oh_my_zsh; setup_oh_my_zsh',
             "test", str(ROOT)], env=self.env, capture_output=True, text=True)

    def test_fresh_install_rerun_preserves_settings_and_uses_zdotdir(self):
        dotdir = self.home / "shell settings"
        dotdir.mkdir()
        self.env["ZDOTDIR"] = str(dotdir)
        rc = dotdir / ".zshrc"
        rc.write_text('export MY_SETTING=keep\nZSH_THEME="agnoster"\nplugins=(git)\n')
        for _ in range(2):
            result = self.run_omz()
            self.assertEqual(result.returncode, 0, result.stderr)
        text = rc.read_text()
        self.assertTrue(text.startswith('export MY_SETTING=keep\n'))
        self.assertIn('ZSH_THEME="agnoster"', text)
        self.assertEqual(text.count("machine-setup: Oh My Zsh"), 1)
        self.assertFalse((self.home / ".zshrc").exists())

    def test_existing_custom_installation_is_left_untouched(self):
        rc = self.home / ".zshrc"
        original = 'export ZSH="$HOME/custom-omz"\nsource "$ZSH/oh-my-zsh.sh"\n'
        rc.write_text(original)
        self.mock("git", "import sys\nsys.exit(97)\n")
        result = self.run_omz()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rc.read_text(), original)
        self.assertFalse((self.home / ".oh-my-zsh").exists())

    def test_conflicting_directory_link_or_managed_source_is_preserved(self):
        target = self.home / ".oh-my-zsh"
        target.mkdir()
        (target / "keep").write_text("keep")
        result = self.run_omz()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((target / "keep").read_text(), "keep")
        shutil.rmtree(target)
        target.symlink_to(self.base / "elsewhere")
        self.assertNotEqual(self.run_omz().returncode, 0)
        target.unlink()
        rc = self.home / ".zshrc"
        original = '# machine-setup: Oh My Zsh\nsource /other/config/oh-my-zsh.zsh\n'
        rc.write_text(original)
        self.assertNotEqual(self.run_omz().returncode, 0)
        self.assertEqual(rc.read_text(), original)

    def test_clone_failure_does_not_activate_incomplete_install(self):
        self.mock("git", "import sys\nsys.exit(42)\n")
        result = self.run_omz()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / ".zshrc").exists())

    def test_missing_zsh_gives_manual_instruction(self):
        prefix = 'command() { if [ "$*" = "-v zsh" ]; then return 1; fi; builtin command "$@"; }; '
        result = subprocess.run(
            ["bash", "-c", prefix + 'set -euo pipefail; setup_dir=$1; '
             '. "$1/scripts/oh-my-zsh.sh"; preflight_oh_my_zsh; setup_oh_my_zsh',
             "test", str(ROOT)], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("administrator", result.stderr)
        self.assertFalse((self.home / ".oh-my-zsh").exists())

    @unittest.skipUnless(shutil.which("zsh"), "Actual Zsh configuration needs Zsh")
    def test_zsh_defaults_and_overrides_load_once(self):
        target = self.home / ".oh-my-zsh"
        target.mkdir()
        (target / "oh-my-zsh.sh").write_text('print -r -- "$ZSH_THEME|${(j:,:)plugins}"\n')
        for prefix, expected in [("", "robbyrussell|git,z"),
                                 ('ZSH_THEME=agnoster; plugins=(git); ', "agnoster|git"),
                                 ('ZSH_THEME=""; plugins=(); ', "|"),
                                 ('plugins=(); ', "robbyrussell|")]:
            result = subprocess.run(
                [shutil.which("zsh"), "-f", "-c", prefix + 'source "$1"',
                 "test", str(ROOT / "config/oh-my-zsh.zsh")],
                env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)

    def real_git(self, *args):
        result = subprocess.run(
            [shutil.which("git"), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
             "-c", "commit.gpgsign=false", *map(str, args)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def local_remote(self):
        upstream = self.base / "upstream"
        self.real_git("init", "-b", "master", upstream)
        (upstream / "oh-my-zsh.sh").write_text("# initial\n")
        self.real_git("-C", upstream, "add", ".")
        self.real_git("-C", upstream, "commit", "-m", "initial")
        # Only URL routing is faked; clone, fetch, ancestry and merge use real Git.
        git_bin = shutil.which("git")
        self.mock("git", f"""import os,sys
args=sys.argv[1:]
if args[0]=='-C' and args[2:]==['remote','get-url','origin']:
    print('https://github.com/ohmyzsh/ohmyzsh.git')
    sys.exit(0)
if args[0]=='clone':
    args[args.index('https://github.com/ohmyzsh/ohmyzsh.git')]={str(upstream)!r}
os.execv({git_bin!r}, [{git_bin!r}]+args)
""")
        return upstream

    def test_real_git_fast_forward_equal_dirty_and_local_commits(self):
        upstream = self.local_remote()
        target = self.home / ".oh-my-zsh"
        self.assertEqual(self.run_omz().returncode, 0)
        initial = self.real_git("-C", target, "rev-parse", "HEAD")
        self.assertEqual(self.run_omz().returncode, 0)
        self.assertEqual(self.real_git("-C", target, "rev-parse", "HEAD"), initial)
        (upstream / "oh-my-zsh.sh").write_text("# updated\n")
        self.real_git("-C", upstream, "commit", "-am", "update")
        result = self.run_omz()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((target / "oh-my-zsh.sh").read_text(), "# updated\n")
        (target / "local").write_text("keep")
        self.assertNotEqual(self.run_omz().returncode, 0)
        self.assertEqual((target / "local").read_text(), "keep")
        self.real_git("-C", target, "add", "local")
        self.real_git("-C", target, "commit", "-m", "local")
        local_head = self.real_git("-C", target, "rev-parse", "HEAD")
        result = self.run_omz()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local commits", result.stderr)
        self.assertEqual(self.real_git("-C", target, "rev-parse", "HEAD"), local_head)

    def test_fetch_failure_wrong_branch_and_wrong_origin(self):
        upstream = self.local_remote()
        self.assertEqual(self.run_omz().returncode, 0)
        target = self.home / ".oh-my-zsh"
        before = (self.home / ".zshrc").read_bytes()
        shutil.rmtree(upstream)
        self.assertNotEqual(self.run_omz().returncode, 0)
        self.real_git("-C", target, "switch", "-c", "custom")
        self.assertNotEqual(self.run_omz().returncode, 0)
        self.mock("git", "print('https://example.invalid/other.git')\n")
        self.assertNotEqual(self.run_omz().returncode, 0)
        self.assertEqual((self.home / ".zshrc").read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
