"""Exercise package guards with fake installers; never change the host machine."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.log = self.base / "calls.jsonl"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        HOME=str(self.base / "home"), MOCK_LOG=str(self.log))

    def mock(self, name, code):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + code)
        path.chmod(0o755)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def run_setup(self, platform, *options, answer="", root=ROOT):
        return subprocess.run(
            ["bash", str(root / "scripts/setup.sh"), platform, *options],
            env=self.env, input=answer, capture_output=True, text=True)

    def run_packages(self, function, packages):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; sudo_enabled=true; setup_dir=$1; . "$1/scripts/packages.sh"; shift; "$@"',
             "test", str(ROOT), function, *packages], env=self.env,
            capture_output=True, text=True)


class UpdateTests(MockTests):
    @unittest.skipUnless(shutil.which("dpkg"), "Native apt version comparison runs on Ubuntu")
    def test_apt_only_installs_missing_or_older_and_honors_holds(self):
        self.mock("apt-mark", "print('held')\n")
        versions = {"missing": ("(none)", "2.0"), "older": ("1.9", "2.0"),
                    "equal": ("2.0", "2.0"), "newer": ("3.0", "2.0"),
                    "epoch": ("2:1.0", "1:9.0"), "held": ("1.0", "2.0")}
        self.mock("apt-cache", f"import sys\nv={versions!r}[sys.argv[-1]]\nprint('Installed:', v[0])\nprint('Candidate:', v[1])\n")
        self.mock("sudo", "import os,sys,json\nwith open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n")
        for _ in range(2):
            result = self.run_packages("upgrade_apt_packages", versions.keys())
            self.assertEqual(result.returncode, 0, result.stderr)
            versions["missing"] = ("2.0", "2.0")
            versions["older"] = ("2.0", "2.0")
            self.mock("apt-cache", f"import sys\nv={versions!r}[sys.argv[-1]]\nprint('Installed:', v[0])\nprint('Candidate:', v[1])\n")
        self.assertEqual(self.calls(), [
            ["apt-get", "install", "-y", "--no-remove", "missing=2.0"],
            ["apt-get", "install", "-y", "--no-remove", "older=2.0"]])

    def test_apt_lookup_failure_stops_without_install(self):
        self.mock("apt-mark", "pass\n")
        self.mock("apt-cache", "print('Installed: (none)\\nCandidate: (none)')\n")
        result = self.run_packages("upgrade_apt_packages", ["unavailable"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_apt_install_failure_is_not_reported_as_success(self):
        self.mock("apt-mark", "pass\n")
        self.mock("apt-cache", "print('Installed: (none)\\nCandidate: 2.0')\n")
        self.mock("sudo", "import sys\nsys.exit(42)\n")
        result = self.run_packages("upgrade_apt_packages", ["broken"])
        self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(shutil.which("ruby"), "Homebrew version decisions run on macOS with Ruby")
    def test_brew_versions_revisions_and_pins(self):
        for installed, stable, revision, pinned, expected in [
            ([], "2.0", 0, False, "install"),
            (["1.9"], "2.0", 0, False, "upgrade"),
            (["2.0"], "2.0", 0, False, "keep"),
            (["3.0"], "2.0", 0, False, "keep"),
            (["1.0", "3.0"], "2.0", 0, False, "keep"),
            (["2.0_1"], "2.0", 2, False, "upgrade"),
            (["2.0_3"], "2.0", 2, False, "keep"),
            (["1.0"], "2.0", 0, True, "keep"),
            (["HEAD-abc"], "2.0", 0, False, "keep"),
        ]:
            with self.subTest(installed=installed, revision=revision, pinned=pinned):
                formula = {"versions": {"stable": stable}, "revision": revision,
                           "installed": [{"version": v} for v in installed], "pinned": pinned}
                result = subprocess.run(["ruby", str(ROOT / "scripts/brew-action.rb")],
                                        input=json.dumps({"formulae": [formula]}),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_brew_only_mutates_selected_formulae(self):
        # Test orchestration independently of the native Ruby version decision.
        self.mock("ruby", "import sys\nprint(sys.stdin.read().strip())\n")
        self.mock("brew", """import os,sys,json
args=sys.argv[1:]
if args[0]=='info':
    print({'missing':'install','older':'upgrade','equal':'keep','newer':'keep','pinned':'keep'}[args[-1]])
else:
    with open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
""")
        result = self.run_packages("upgrade_brew_packages", ["missing", "older", "equal", "newer", "pinned"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["install", "--formula", "missing"], ["upgrade", "--formula", "older"]])

    def macos_mocks(self):
        home = self.base / "home"
        home.mkdir()
        self.env["XDG_CONFIG_HOME"] = str(home / ".config")
        for name in ("sudo", "git"):
            self.mock(name, "import sys\nprint('Unexpected privileged/system mutation', file=sys.stderr)\nsys.exit(97)\n")
        self.mock("ruby", "import sys\nsys.stdin.read()\nprint('install')\n")
        self.mock("brew", """import os,sys,json
args=sys.argv[1:]
with open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='info':
    print(json.dumps({'formulae':[{'installed':[], 'versions':{'stable':'1.0'}}]}))
elif args[0] not in ('update','install','upgrade'):
    sys.exit(95)
""")
        self.mock("xcode-select", "import sys\nsys.exit(0 if sys.argv[1:]==['-p'] else 98)\n")
        self.mock("mise", "import sys\nprint('Unexpected system mise invocation', file=sys.stderr)\nsys.exit(99)\n")
        self.mock("curl", "import sys\nsys.exit(96)\n")
        return home

    def run_macos(self):
        return self.run_setup("macos", answer="no\n")

    def test_macos_missing_clt_stops_without_installers_or_writes(self):
        home = self.macos_mocks()
        self.mock("xcode-select", "import sys\nsys.exit(1)\n")
        result = self.run_macos()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ask IT", result.stderr)
        self.assertEqual(list(home.iterdir()), [])
        # The downloaded bootstrap must also stop before invoking Git/CLT install.
        self.mock("uname", "print('Darwin')\n")
        result = subprocess.run(["bash", "-c", (ROOT / "bootstrap.sh").read_text()],
                                env=self.env, input="no\n", capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ask IT", result.stderr)
        self.assertEqual(list(home.iterdir()), [])

    def test_macos_missing_brew_warns_without_installing_or_writing(self):
        home = self.macos_mocks()
        (self.bin / "brew").unlink()
        checkout = self.base / "checkout"
        shutil.copytree(ROOT / "scripts", checkout / "scripts")
        shutil.copytree(ROOT / "config", checkout / "config")
        shutil.copyfile(ROOT / "bootstrap.sh", checkout / "bootstrap.sh")
        shutil.copyfile(ROOT / ".machine-setup.yml", checkout / ".machine-setup.yml")
        # Hide host Homebrew on macOS CI, including standard-prefix discovery.
        script = checkout / "scripts/setup.sh"
        script.write_text(script.read_text().replace('/opt/homebrew/bin/brew', str(self.base / 'absent-brew'))
                          .replace('/usr/local/bin/brew', str(self.base / 'absent-brew')))
        result = subprocess.run(["bash", "-c",
                                'command() { if [ "$*" = "-v brew" ]; then return 1; fi; builtin command "$@"; }; export -f command; . "$1/bootstrap.sh"; read_setup_config; choose_setup_sudo; setup_dir=$1; platform=macos; dry_run=false; . "$1/scripts/setup.sh"; setup_main',
                                "test", str(checkout)], env=self.env, input="no\n", capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Warning: Homebrew", result.stderr)
        self.assertIn("managed software center", result.stderr)
        self.assertEqual(list(home.iterdir()), [])
        self.assertEqual(self.calls(), [])

    def test_macos_rejects_local_mise_symlink_to_system_binary(self):
        home = self.macos_mocks()
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/mise").symlink_to(self.bin / "mise")
        result = self.run_macos()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("writable user-local mise", result.stderr)
        self.assertFalse((home / ".config").exists())

    def test_macos_installs_local_mise_ignoring_system_binary_and_destination(self):
        home = self.macos_mocks()
        self.env["MISE_INSTALL_PATH"] = str(self.base / "must-not-write")
        # Fake the downloaded installer, not the host's package managers.
        installer = self.base / "installer.sh"
        installer.write_text("""#!/bin/sh
set -eu
[ "$MISE_INSTALL_PATH" = "$HOME/.local/bin/mise" ]
mkdir -p "$HOME/.local/bin"
cat > "$MISE_INSTALL_PATH" <<'MOCK'
#!/bin/sh
case "$1" in self-update|trust|install|upgrade|--version|ls) exit 0 ;; *) exit 1 ;; esac
MOCK
chmod +x "$MISE_INSTALL_PATH"
""")
        self.mock("curl", f"import sys,shutil\nshutil.copyfile({str(installer)!r}, sys.argv[sys.argv.index('-o')+1])\n")
        result = self.run_macos()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [
            ["update"], ["info", "--json=v2", "--formula", "git"],
            ["install", "--formula", "git"], ["info", "--json=v2", "--formula", "curl"],
            ["install", "--formula", "curl"]])
        self.assertTrue((home / ".local/bin/mise").is_file())
        self.assertFalse((self.base / "must-not-write").exists())
        self.assertIn(str(home / ".local/bin/mise"), (home / ".zshrc").read_text())
        # A rerun must use local mise without downloading or touching the system copy.
        self.mock("curl", "import sys\nsys.exit(96)\n")
        result = self.run_macos()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_setup_uses_native_mise_updates_and_preserves_manifest(self):
        home = self.base / "home"
        (home / ".local/bin").mkdir(parents=True)
        self.mock("sudo", "pass\n")
        self.mock("apt-mark", "pass\n")
        self.mock("apt-cache", "print('Installed: (none)\\nCandidate: 2.0')\n")
        self.mock("mise", """import os,sys,json
with open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
""")
        (home / ".local/bin/mise").symlink_to(self.bin / "mise")
        self.env["XDG_CONFIG_HOME"] = str(home / ".config")
        (home / ".machine-setup.yml").write_text("sudoEnabled: true\n")
        before = (ROOT / "config/tools.toml").read_bytes()
        for _ in range(2):
            result = self.run_setup("ubuntu")
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls.count(["self-update", "--yes"]), 2)
        self.assertEqual(calls.count(["install"]), 2)
        self.assertEqual(calls.count(["upgrade"]), 2)
        self.assertEqual((ROOT / "config/tools.toml").read_bytes(), before)
        self.assertEqual((home / ".bashrc").read_text().count("activate bash"), 1)
        self.assertEqual((home / ".zshrc").read_text().count("activate zsh"), 1)


class PrivilegeTests(MockTests):
    def ubuntu_mocks(self):
        home = self.base / "home"
        (home / ".local/bin").mkdir(parents=True)
        self.env["XDG_CONFIG_HOME"] = str(home / ".config")
        for name in ("sudo", "apt-get", "apt-cache", "apt-mark", "mise", "curl"):
            self.mock(name, "import sys\nprint('Unexpected system command', file=sys.stderr)\nsys.exit(97)\n")
        # curl and git are available, but no downloads should be needed here.
        mise = home / ".local/bin/mise"
        mise.write_text("#!/bin/sh\ncase \"$1\" in self-update|trust|install|upgrade|--version|ls) exit 0 ;; *) exit 98 ;; esac\n")
        mise.chmod(0o755)
        return home

    def run_ubuntu(self, *, answer=""):
        return self.run_setup("ubuntu", answer=answer)

    def test_ubuntu_no_sudo_prompts_persists_and_reuses_choice(self):
        home = self.ubuntu_mocks()
        before = (ROOT / ".machine-setup.yml").read_bytes()
        result = self.run_ubuntu(answer="maybe\nno\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Please answer yes or no", result.stderr)
        self.assertIn("Skipping apt", result.stdout)
        self.assertIn("sudo apt-get install", result.stdout)
        config = home / ".machine-setup.yml"
        self.assertIn("sudoEnabled: false", config.read_text())
        modified = config.stat().st_mtime_ns
        result = self.run_ubuntu()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Do you have access", result.stderr)
        self.assertEqual(config.stat().st_mtime_ns, modified)
        self.assertEqual((ROOT / ".machine-setup.yml").read_bytes(), before)

    def test_entrypoints_prompt_once_then_reuse_yaml(self):
        home = self.ubuntu_mocks()
        self.mock("uname", "print('Darwin')\n")
        self.mock("xcode-select", "import sys\nsys.exit(0 if sys.argv[1:]==['-p'] else 98)\n")
        self.mock("ruby", "import sys\nsys.stdin.read()\nprint('keep')\n")
        self.mock("brew", "pass\n")
        self.env["MACHINE_SETUP_DIR"] = str(self.base / "ignored")
        for entrypoint, answer in (("bootstrap.sh", "no\n"), ("scripts/setup.sh", "")):
            result = subprocess.run(["bash", str(ROOT / entrypoint),
                                     *(["macos"] if entrypoint == "scripts/setup.sh" else [])], env=self.env,
                                    input=answer, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr.count("Do you have access to sudo?"), int(bool(answer)))
            self.assertIn("sudoEnabled: false", (home / ".machine-setup.yml").read_text())
        self.assertFalse((self.base / "ignored").exists())

    def test_unrelated_yaml_settings_are_preserved_and_do_not_configure_setup(self):
        home = self.ubuntu_mocks()
        config = home / ".machine-setup.yml"
        for settings in ("dryRun: maybe\n", "dryRun: true\ndryRun: false\n",
                         "repository: file:///tmp/repo\n", "ref: -main\n",
                         "setupDir: relative/path\n", "ref: main\nref: other\n"):
            with self.subTest(settings=settings):
                content = "sudoEnabled: false\n" + settings
                config.write_text(content)
                result = self.run_ubuntu()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("Do you have access", result.stderr)
                self.assertEqual(config.read_text(), content)
                self.assertTrue((home / ".config").exists())

    def test_yaml_changes_privileges_and_preserves_other_settings(self):
        home = self.ubuntu_mocks()
        config = home / ".machine-setup.yml"
        config.write_text("# My settings\nsudoEnabled: false\nextra: keep\neditor:\n  name: vim\n")
        result = self.run_ubuntu(answer="no\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_text(), "# My settings\nsudoEnabled: false\nextra: keep\neditor:\n  name: vim\n")
        self.mock("sudo", "import os,sys,json\nwith open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n")
        self.mock("apt-mark", "pass\n")
        self.mock("apt-cache", "print('Installed: (none)\\nCandidate: 1.0')\n")
        config.write_text(config.read_text().replace("sudoEnabled: false", "sudoEnabled: true"))
        result = self.run_ubuntu()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudoEnabled: true", config.read_text())
        self.assertEqual(self.calls()[0], ["apt-get", "update"])

    def test_no_sudo_installs_local_mise_instead_of_using_system_copy(self):
        home = self.ubuntu_mocks()
        (home / ".local/bin/mise").unlink()
        installer = self.base / "installer.sh"
        installer.write_text("""#!/bin/sh
set -eu
[ "$MISE_INSTALL_PATH" = "$HOME/.local/bin/mise" ]
mkdir -p "$HOME/.local/bin"
cat > "$MISE_INSTALL_PATH" <<'MOCK'
#!/bin/sh
case "$1" in self-update|trust|install|upgrade|--version|ls) exit 0 ;; *) exit 1 ;; esac
MOCK
chmod +x "$MISE_INSTALL_PATH"
""")
        self.mock("curl", f"import sys,shutil\nshutil.copyfile({str(installer)!r}, sys.argv[sys.argv.index('-o')+1])\n")
        result = self.run_ubuntu(answer="no\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((home / ".local/bin/mise").is_file())

    def test_existing_yaml_without_boolean_sudo_fails_without_prompt_or_writes(self):
        home = self.ubuntu_mocks()
        config = home / ".machine-setup.yml"
        for content in ("editor: vim\n", "sudoEnabled: null # User preference\n"):
            with self.subTest(content=content):
                config.write_text(content)
                result = self.run_ubuntu(answer="no\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Do you have access", result.stderr)
                self.assertIn("Set sudoEnabled", result.stderr)
                self.assertEqual(config.read_text(), content)
                self.assertFalse((home / ".config").exists())

    def test_invalid_or_linked_yaml_fails_before_installation(self):
        home = self.ubuntu_mocks()
        config = home / ".machine-setup.yml"
        for content in ("sudoEnabled: maybe\n", "sudoEnabled:\n",
                        "sudoEnabled:\n  value: true\n",
                        "sudoEnabled: true\nsudoEnabled: false\n"):
            with self.subTest(content=content):
                config.write_text(content)
                result = self.run_ubuntu(answer="no\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid sudo configuration", result.stderr)
                self.assertEqual(config.read_text(), content)
                self.assertFalse((home / ".config").exists())
        config.unlink()
        target = self.base / "external.yml"
        target.write_text("sudoEnabled: false\n")
        config.symlink_to(target)
        result = self.run_ubuntu(answer="no\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular file", result.stderr)

    def test_unanswered_prompt_stops_without_defaulting_to_sudo(self):
        home = self.ubuntu_mocks()
        result = self.run_ubuntu()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Rerun interactively", result.stderr)
        self.assertFalse((home / ".machine-setup.yml").exists())

    def test_no_sudo_rejects_system_mise_symlink(self):
        home = self.ubuntu_mocks()
        local = home / ".local/bin/mise"
        local.unlink()
        local.symlink_to(self.bin / "mise")
        result = self.run_ubuntu(answer="no\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("writable user-local mise", result.stderr)

    def test_cli_preview_does_not_prompt_or_write(self):
        home = self.ubuntu_mocks()
        config = home / ".machine-setup.yml"
        config.write_text("sudoEnabled: null\n")
        before = config.read_bytes()
        result = self.run_setup("ubuntu", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Do you have access", result.stderr)
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((home / ".config").exists())

    @unittest.skipUnless(Path("/etc/os-release").exists() and
                         "ID=ubuntu" in Path("/etc/os-release").read_text(),
                         "Ubuntu remote bootstrap prerequisite")
    def test_downloaded_bootstrap_without_git_and_sudo_gives_manual_instruction(self):
        home = self.ubuntu_mocks()
        # Hide even a host Git without changing PATH's other required commands.
        prefix = 'command() { if [ "$*" = "-v git" ]; then return 1; fi; builtin command "$@"; }; '
        result = subprocess.run(["bash", "-c", prefix + (ROOT / "bootstrap.sh").read_text(),
                                 "test"], env=self.env, input="no\n",
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git is required", result.stderr)
        self.assertIn("administrator", result.stderr)
        self.assertFalse((home / ".local/share").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
