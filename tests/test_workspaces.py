#!/usr/bin/env python3
"""Exercise real Git config and signatures without network or host credentials."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("workspaces", Path(__file__).resolve().parents[1] / "scripts/workspaces.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
                                          "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.active = "wrong-account"
        self.keys = {kind: set() for kind in ("authentication", "signing")}
        self.uploads = 0
        self.logins = 0
        self.real_run = ws.run
        self.patcher = patch.object(ws, "run", side_effect=self.fake_run)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def fake_run(self, *args, **kwargs):
        output, status = "", 0
        if args[0] == "gh":
            if args[1:3] == ("auth", "switch"):
                self.active = args[-1]
            elif args[1:3] == ("auth", "login"):
                self.active = "alice"
                self.logins += 1
            elif args[1] == "api":
                endpoint = args[-1]
                if endpoint == "user":
                    output = json.dumps({"login": self.active, "id": 123, "name": "Alice"})
                elif endpoint == "user/emails":
                    output = json.dumps([{"email": "alice@example.com", "verified": True},
                                         {"email": "work@example.com", "verified": True}])
                else:
                    kind = "signing" if endpoint.endswith("ssh_signing_keys") else "authentication"
                    output = json.dumps([[{"key": key} for key in self.keys[kind]]])
            elif args[1:3] == ("ssh-key", "add"):
                kind = args[args.index("--type") + 1]
                self.keys[kind].add(ws.public_part(Path(args[3]).read_text()))
                self.uploads += 1
            else:
                raise AssertionError(args)
        elif args[0] == "ssh":
            output, status = f"Hi {self.active}! You've successfully authenticated", 1
        elif args[:3] == ("ssh-keygen", "-t", "ed25519"):
            # Real key generation, with no interactive passphrase in tests.
            return self.real_run(*args, "-N", "", capture=True)
        elif args[:3] == ("ssh-keygen", "-Y", "sign"):
            return self.real_run(*args, capture=True)
        else:
            return self.real_run(*args, **kwargs)
        result = subprocess.CompletedProcess(args, status, output, "")
        if kwargs.get("check", True) and status:
            raise subprocess.CalledProcessError(status, args, output, "")
        return result

    def config(self, name="personal", location="~/workspace/personal", email="alice@example.com"):
        return ws.validate({"workspaces": [{"name": name, "location": location,
                                           "email": email, "githubUser": "alice"}]})

    def git(self, repo, *args):
        return self.real_run("git", "-C", str(repo), *args).stdout.strip()

    def test_real_signed_commit_and_additive_reruns(self):
        ws.provision(self.config("default", None))
        ws.provision(self.config())
        repo = self.home / "workspace/personal/deep/repo"
        repo.mkdir(parents=True)
        self.git(repo, "init")
        self.git(repo, "commit", "--allow-empty", "-m", "signed")
        self.assertEqual(self.git(repo, "config", "user.email"), "alice@example.com")
        self.assertIn("BEGIN SSH SIGNATURE", self.git(repo, "cat-file", "commit", "HEAD"))
        allowed = self.home / "allowed-signers"
        public = (self.home / ".ssh/machine-setup-alice.pub").read_text().strip()
        allowed.write_text(f"alice@example.com {public}\n")
        self.git(repo, "-c", f"gpg.ssh.allowedSignersFile={allowed}", "verify-commit", "HEAD")
        before = self.uploads
        ws.provision(self.config())
        self.assertEqual(self.uploads, before)
        ws.provision(self.config("work", "~/workspace/work", "work@example.com"))
        self.assertEqual(self.git(repo, "config", "user.email"), "alice@example.com")
        work = self.home / "workspace/work/repo"
        work.mkdir()
        self.git(work, "init")
        self.assertEqual(self.git(work, "config", "user.email"), "work@example.com")
        outside = self.home / "elsewhere"
        outside.mkdir()
        self.git(outside, "init")
        self.assertEqual(self.git(outside, "config", "user.email"), "alice@example.com")
        includes = self.real_run("git", "config", "--global", "--get-all", "include.path").stdout.splitlines()
        self.assertEqual(len(includes), 1)
        self.assertTrue((self.home / "workspace/personal").is_dir())
        # No network command is used by these real Git configuration assertions.
        self.assertEqual(self.git(work, "config", "--get", "url.git@github.com:.insteadOf"), "ssh://git@github.com/")

    def test_nested_workspace_wins_and_unrelated_global_preserved(self):
        self.real_run("git", "config", "--global", "alias.st", "status")
        ws.provision(self.config())
        ws.provision(self.config("nested", "~/workspace/personal/nested", "work@example.com"))
        repo = self.home / "workspace/personal/nested/repo"
        repo.mkdir()
        self.git(repo, "init")
        self.assertEqual(self.git(repo, "config", "user.email"), "work@example.com")
        self.assertEqual(self.git(repo, "config", "alias.st"), "status")

    def test_modified_config_is_not_overwritten(self):
        ws.provision(self.config())
        path = self.home / ".config/machine-setup/git/personal.gitconfig"
        path.write_text("user changes\n")
        with self.assertRaisesRegex(ValueError, "User-modified"):
            ws.provision(self.config())
        self.assertEqual(path.read_text(), "user changes\n")

    def test_missing_explicit_key_generates_and_registers(self):
        config = self.config()
        config[0]["privateKey"] = str(self.home / ".ssh/explicit")
        ws.provision(config)
        self.assertTrue((self.home / ".ssh/explicit").exists())
        self.assertEqual(self.uploads, 2)

    def test_mismatched_public_key_and_open_permissions_fail(self):
        ws.provision(self.config())
        key = self.home / ".ssh/machine-setup-alice"
        key.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "permissions"):
            ws.provision(self.config())
        key.chmod(0o600)
        Path(str(key) + ".pub").write_text("ssh-ed25519 wrong\n")
        with self.assertRaisesRegex(ValueError, "does not match"):
            ws.provision(self.config())

    def test_validation_rejects_duplicate_defaults_and_relative_paths(self):
        with self.assertRaisesRegex(ValueError, "must be a list"):
            ws.validate({"workspaces": False})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ws.validate({"workspaces": [{"name": name, "email": "a", "githubUser": "alice"}
                                        for name in ("one", "two")]})
        with self.assertRaisesRegex(ValueError, "absolute"):
            self.config(location="relative")

    def test_wrong_browser_account_fails(self):
        # Switching an unavailable account fails; browser logs in as alice.
        original = self.fake_run
        def unavailable(*args, **kwargs):
            if args[:3] == ("gh", "auth", "switch"):
                return subprocess.CompletedProcess(args, 1, "", "")
            return original(*args, **kwargs)
        with patch.object(ws, "run", side_effect=unavailable):
            with self.assertRaisesRegex(ValueError, "Expected GitHub account bob"):
                ws.authenticate("bob")
        self.assertEqual(self.logins, 1)

    def test_private_repository_transport_uses_workspace_key(self):
        ws.provision(self.config())
        repo = self.home / "workspace/personal/repo"
        repo.mkdir()
        remote = self.home / "remote.git"
        self.real_run("git", "init", "--bare", str(remote))
        self.git(repo, "init")
        self.git(repo, "commit", "--allow-empty", "-m", "signed")
        self.git(repo, "remote", "add", "origin", "https://github.com/test/private.git")
        binary = self.home / "bin"
        binary.mkdir()
        ssh = binary / "ssh"
        ssh.write_text("#!/usr/bin/env python3\nimport os, sys, subprocess\n"
                       "from pathlib import Path\n"
                       "Path(os.environ['TEST_LOG']).write_text(' '.join(sys.argv))\n"
                       "command = 'git-receive-pack' if sys.argv[-1].startswith('git-receive-pack') else 'git-upload-pack'\n"
                       "sys.exit(subprocess.call([command, os.environ['TEST_REMOTE']]))\n")
        ssh.chmod(0o755)
        log = self.home / "ssh.log"
        with patch.dict(os.environ, {"PATH": str(binary) + os.pathsep + os.environ['PATH'],
                                      "TEST_REMOTE": str(remote), "TEST_LOG": str(log)}):
            self.git(repo, "push", "origin", "HEAD:refs/heads/main")
            self.git(repo, "fetch", "origin", "main")
        self.assertIn(str(self.home / ".ssh/machine-setup-alice"), log.read_text())
        self.assertIn("git@github.com", log.read_text())

    def test_existing_local_override_is_reported(self):
        ws.provision(self.config())
        repo = self.home / "workspace/personal/repo"
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "commit.gpgSign", "false")
        with self.assertRaisesRegex(ValueError, "overrides commit.gpgSign"):
            ws.provision(self.config())

    def test_missing_scope_guides_browser_refresh_before_upload(self):
        original = self.fake_run
        granted = False
        def missing_scope(*args, **kwargs):
            nonlocal granted
            if args[:3] == ("gh", "auth", "refresh"):
                granted = True
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[0] == "gh" and args[1] == "api" and args[-1] == "user/ssh_signing_keys" and not granted:
                raise subprocess.CalledProcessError(1, args, "", "HTTP 403 missing scope")
            return original(*args, **kwargs)
        with patch.object(ws, "run", side_effect=missing_scope):
            ws.provision(self.config())
        self.assertTrue(granted)
        self.assertEqual(self.uploads, 2)

    def test_replacement_default_keeps_old_file_and_selects_new_identity(self):
        ws.provision(self.config("default", None))
        old = self.home / ".config/machine-setup/git/default.gitconfig"
        content = old.read_text()
        ws.provision(self.config("new-default", None, "work@example.com"))
        self.assertEqual(old.read_text(), content)
        self.assertEqual(self.real_run("git", "config", "--global", "--includes", "user.email").stdout.strip(), "work@example.com")

    def test_empty_workspace_list_makes_no_changes(self):
        with patch.object(ws, "text", return_value='{"sudoEnabled": false, "workspaces": []}'), \
                patch.object(sys, "argv", ["workspaces.py", "config.yml"]):
            ws.main()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_lost_private_key_generates_replacement_without_removing_old_public_key(self):
        ws.provision(self.config())
        private = self.home / ".ssh/machine-setup-alice"
        public = Path(str(private) + ".pub")
        previous = public.read_text()
        private.unlink()
        ws.provision(self.config())
        self.assertEqual(public.read_text(), previous)
        state = json.loads((self.home / ".config/machine-setup/git/state.json").read_text())
        self.assertNotEqual(state["entries"]["personal"]["key"], str(private))
        self.assertEqual(self.uploads, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
