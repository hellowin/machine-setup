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


class UpdateTests(unittest.TestCase):
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

    def run_packages(self, function, packages):
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail; setup_dir=$1; . "$1/scripts/packages.sh"; shift; "$@"',
             "test", str(ROOT), function, *packages], env=self.env,
            capture_output=True, text=True)

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
        before = (ROOT / "config/tools.toml").read_bytes()
        for _ in range(2):
            result = subprocess.run(["bash", str(ROOT / "scripts/setup.sh"), "ubuntu"],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls.count(["self-update", "--yes"]), 2)
        self.assertEqual(calls.count(["install"]), 2)
        self.assertEqual(calls.count(["upgrade"]), 2)
        self.assertEqual((ROOT / "config/tools.toml").read_bytes(), before)
        self.assertEqual((home / ".bashrc").read_text().count("activate bash"), 1)
        self.assertEqual((home / ".zshrc").read_text().count("activate zsh"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
