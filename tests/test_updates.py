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

    def macos_mocks(self):
        home = self.base / "home"
        home.mkdir()
        self.env["XDG_CONFIG_HOME"] = str(home / ".config")
        for name in ("sudo", "brew", "git"):
            self.mock(name, "import sys\nprint('Unexpected privileged/system mutation', file=sys.stderr)\nsys.exit(97)\n")
        self.mock("xcode-select", "import sys\nsys.exit(0 if sys.argv[1:]==['-p'] else 98)\n")
        self.mock("mise", "import sys\nprint('Unexpected system mise invocation', file=sys.stderr)\nsys.exit(99)\n")
        self.mock("curl", "import sys\nsys.exit(96)\n")
        return home

    def run_macos(self):
        return subprocess.run(["bash", str(ROOT / "scripts/setup.sh"), "macos"],
                              env=self.env, capture_output=True, text=True)

    def test_macos_missing_clt_stops_without_installers_or_writes(self):
        home = self.macos_mocks()
        self.mock("xcode-select", "import sys\nsys.exit(1)\n")
        result = self.run_macos()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ask IT", result.stderr)
        self.assertEqual(list(home.iterdir()), [])
        # The downloaded bootstrap must also stop before invoking Git/CLT install.
        self.mock("uname", "print('Darwin')\n")
        result = subprocess.run(["bash", "-c", (ROOT / "bootstrap.sh").read_text()],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ask IT", result.stderr)
        self.assertEqual(list(home.iterdir()), [])

    def test_macos_missing_command_stops_before_mise(self):
        home = self.macos_mocks()
        # Isolate a checkout to exercise an unavailable manifest command on any host.
        checkout = self.base / "checkout"
        shutil.copytree(ROOT / "scripts", checkout / "scripts")
        (checkout / "config").mkdir()
        (checkout / "config/packages.macos.txt").write_text("machine-setup-unavailable-command\n")
        result = subprocess.run(["bash", str(checkout / "scripts/setup.sh"), "macos"],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing macOS prerequisite", result.stderr)
        self.assertEqual(list(home.iterdir()), [])

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
