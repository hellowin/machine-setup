#!/usr/bin/env python3
"""Interactive, additive Git workspace provisioning. Run through mise exec."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import uuid


def run(*args, check=True, capture=True, **kwargs):
    if args[0] == "gh":
        kwargs["env"] = dict(os.environ, GH_HOST="github.com")
    return subprocess.run(args, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, **kwargs)


def text(*args):
    return run(*args).stdout.strip()


def regular(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Expected a regular file: {path}")


def write(path, content):
    regular(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        file.write(content)
        temporary = file.name
    os.replace(temporary, path)


def digest(content):
    return hashlib.sha256(content.encode()).hexdigest()


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def expanded(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Use an absolute path or ~/ path: {value}")
    if any(char in str(path) for char in '\n\r\x00*?[]'):
        raise ValueError(f"Unsupported characters in path: {value}")
    return Path(os.path.abspath(path))


def validate(config):
    if not isinstance(config, dict):
        raise ValueError("Host YAML must be a mapping")
    workspaces = config.get("workspaces", [])
    if workspaces is None:
        workspaces = []
    if not isinstance(workspaces, list):
        raise ValueError("workspaces must be a list")
    names, locations = set(), set()
    for workspace in workspaces:
        if not isinstance(workspace, dict):
            raise ValueError("Each workspace must be a mapping")
        for field in ("name", "email", "githubUser"):
            value = workspace.get(field)
            if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
                raise ValueError(f"Workspace requires a nonempty {field}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", workspace["name"]):
            raise ValueError("Workspace names must contain letters, digits, underscores or hyphens")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", workspace["githubUser"]):
            raise ValueError("Invalid GitHub username")
        if workspace["name"] in names:
            raise ValueError("Duplicate workspace name")
        names.add(workspace["name"])
        for field in ("location", "privateKey", "gitName"):
            value = workspace.get(field)
            if value is not None and (not isinstance(value, str) or not value or any(ord(c) < 32 for c in value)):
                raise ValueError(f"{field} must be a nonempty string or null")
        location = str(expanded(workspace["location"]).resolve()) if workspace.get("location") else None
        if location in locations:
            raise ValueError("Duplicate location or more than one default workspace")
        locations.add(location)
        workspace["location"] = location
        if workspace.get("privateKey"):
            workspace["privateKey"] = str(expanded(workspace["privateKey"]))
    return workspaces


def authenticate(user):
    run("gh", "auth", "switch", "--hostname", "github.com", "--user", user, check=False)
    result = run("gh", "api", "--hostname", "github.com", "user", check=False)
    if result.returncode or json.loads(result.stdout)["login"].lower() != user.lower():
        print(f"Authenticate in your browser as GitHub user {user}.", flush=True)
        run("gh", "auth", "login", "--hostname", "github.com", "--web",
            "--git-protocol", "ssh", "--skip-ssh-key", "--scopes",
            "user:email,admin:public_key,write:ssh_signing_key", capture=False)
    actual = json.loads(text("gh", "api", "--hostname", "github.com", "user"))
    if actual["login"].lower() != user.lower():
        raise ValueError(f"Expected GitHub account {user}, got {actual['login']}. Check GH_TOKEN/GITHUB_TOKEN or browser login.")
    return actual


def public_part(value):
    parts = value.split()
    if len(parts) < 2:
        raise ValueError("Invalid SSH public key")
    return " ".join(parts[:2])


def remote_keys(endpoint):
    pages = json.loads(text("gh", "api", "--hostname", "github.com", "--paginate", "--slurp", endpoint))
    return {public_part(key["key"]) for page in pages for key in page}


def choose_key(workspace, previous):
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    user = workspace["githubUser"]
    configured = workspace.get("privateKey")
    if configured:
        key = Path(configured)
    elif previous and previous.get("githubUser", "").lower() == user.lower():
        key = Path(previous["key"])
    else:
        key = ssh_dir / f"machine-setup-{user.lower()}"
        if not key.exists():
            registered = remote_keys(f"users/{user}/keys") | remote_keys(f"users/{user}/ssh_signing_keys")
            candidates = []
            for public in sorted(ssh_dir.glob("*.pub")):
                private = public.with_suffix("")
                if private.is_file() and not private.is_symlink() and not public.is_symlink():
                    if public_part(public.read_text()) in registered:
                        candidates.append(private)
            if len(candidates) == 1:
                key = candidates[0]
    regular(key)
    public = Path(str(key) + ".pub")
    regular(public)
    if not configured and not key.exists() and public.exists():
        # Keep the orphaned public key/remote registration and generate a new pair.
        key = ssh_dir / f"machine-setup-{user.lower()}-{uuid.uuid4().hex[:8]}"
        public = Path(str(key) + ".pub")
    if not key.exists():
        if public.exists():
            raise ValueError(f"Private key missing but {public} exists; restore the private key or choose another privateKey path")
        key.parent.mkdir(parents=True, exist_ok=True)
        print(f"Generating a key for {user} at {key}. Choose a passphrase when prompted.\n"
              "Guide: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent",
              flush=True)
        run("ssh-keygen", "-t", "ed25519", "-C", workspace["email"], "-f", str(key), capture=False)
    if key.stat().st_mode & 0o077:
        raise ValueError(f"Private key permissions are too open. Run: chmod 600 {shlex.quote(str(key))}")
    # Derive from the actual private key, including passphrase-protected keys.
    derived = text("ssh-keygen", "-y", "-f", str(key))
    if public.exists() and public_part(public.read_text()) != public_part(derived):
        raise ValueError(f"Public key does not match private key: {public}")
    if not public.exists():
        write(public, derived + "\n")
    return key, public


def register_key(user, public):
    selected = public_part(public.read_text())
    for endpoint, kind in (("user/keys", "authentication"), ("user/ssh_signing_keys", "signing")):
        scope = "admin:public_key" if kind == "authentication" else "write:ssh_signing_key"
        try:
            registered = remote_keys(endpoint)
        except subprocess.CalledProcessError as error:
            if not any(code in (error.stderr or "") for code in ("HTTP 403", "HTTP 404")):
                raise
            print(f"Authorizing {kind} key access in your browser for {user}.", flush=True)
            run("gh", "auth", "refresh", "--hostname", "github.com", "--scopes", scope, capture=False)
            authenticate(user)
            registered = remote_keys(endpoint)
        if selected in registered:
            continue
        title = f"machine-setup {user} {socket.gethostname()}"
        result = run("gh", "ssh-key", "add", str(public), "--type", kind, "--title", title, check=False)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            if not any(code in result.stderr for code in ("HTTP 403", "HTTP 404")):
                raise ValueError(f"Could not register {kind} key for {user}: {result.stderr}")
            print(f"Authorizing {kind} key upload in your browser for {user}.", flush=True)
            run("gh", "auth", "refresh", "--hostname", "github.com", "--scopes", scope, capture=False)
            actual = json.loads(text("gh", "api", "--hostname", "github.com", "user"))["login"]
            if actual.lower() != user.lower():
                raise ValueError("GitHub account changed during authorization")
            run("gh", "ssh-key", "add", str(public), "--type", kind, "--title", title, capture=False)


def ssh_arguments(key):
    # Ignore host aliases and identity lists that might select a different account.
    return ["ssh", "-F", "/dev/null", "-o", "IdentitiesOnly=yes", "-i", str(key)]


def verify_access(user, key):
    result = run(*ssh_arguments(key), "-T", "git@github.com", check=False)
    greeting = f"Hi {user}! You've successfully authenticated"
    if result.returncode != 1 or greeting.lower() not in (result.stdout + result.stderr).lower():
        raise ValueError(f"SSH authentication failed for {user}: {result.stdout}{result.stderr}\n"
                         "Check network access, the host-key prompt, and your organization's SSH/SSO policy.")
    # Exercise the same signing executable Git will use before claiming success.
    with tempfile.TemporaryDirectory() as directory:
        message = Path(directory) / "message"
        message.write_text("machine-setup signing check\n")
        run("ssh-keygen", "-Y", "sign", "-n", "git", "-f", str(key), str(message), capture=False)


def workspace_config(workspace, account, key):
    name = workspace.get("gitName") or account.get("name") or account["login"]
    command = shlex.join(ssh_arguments(key))
    return (f"[user]\n\tname = {quote(name)}\n\temail = {quote(workspace['email'])}\n"
            f"\tsigningKey = {quote(key)}\n[gpg]\n\tformat = ssh\n"
            f"[commit]\n\tgpgSign = true\n[core]\n\tsshCommand = {quote(command)}\n"
            '[url "git@github.com:"]\n\tinsteadOf = https://github.com/\n'
            '\tinsteadOf = ssh://git@github.com/\n')


def check_existing_repositories(workspaces, entries):
    for workspace in workspaces:
        if not workspace["location"]:
            continue
        for directory, children, _ in os.walk(workspace["location"]):
            if ".git" in children:
                children.remove(".git")
            if not (Path(directory) / ".git").exists():
                continue
            # A more specific declared workspace may govern this repository.
            matching = [(name, item) for name, item in entries.items() if item["location"] and
                        Path(directory).is_relative_to(item["location"])]
            selected_name, entry = max(matching, key=lambda item: (len(item[1]["location"]),
                                      any(workspace["name"] == item[0] for workspace in workspaces)))
            selected = next((item for item in workspaces if item["name"] == selected_name), None)
            if selected is None:
                continue  # Removed, more specific workspace is now user-managed.
            expected = {"user.email": selected["email"], "commit.gpgSign": "true", "gpg.format": "ssh",
                        "user.signingKey": entry["key"],
                        "core.sshCommand": shlex.join(ssh_arguments(Path(entry["key"])))}
            for field, value in expected.items():
                options = ["--type=bool"] if field == "commit.gpgSign" else []
                actual = text("git", "-C", directory, "config", *options, "--get", field)
                if actual != value:
                    raise ValueError(f"Repository {directory} overrides {field} ({actual}). "
                                     f"Inspect git config --show-origin {field} and resolve the override before rerunning.")


def provision(workspaces):
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "machine-setup/git"
    state_file = root / "state.json"
    regular(state_file)
    state = json.loads(state_file.read_text()) if state_file.exists() else {"entries": {}}
    entries = state["entries"]
    declared_names = {workspace["name"] for workspace in workspaces}
    index = root / "workspaces.gitconfig"
    regular(index)
    if index.exists() and digest(index.read_text()) != state.get("indexHash"):
        raise ValueError(f"User-modified configuration: {index}; resolve before rerunning")
    # Check all declared file conflicts before network calls or key generation.
    for workspace in workspaces:
        path = root / (workspace["name"] + ".gitconfig")
        regular(path)
        previous = entries.get(workspace["name"])
        if path.exists() and (not previous or digest(path.read_text()) != previous["hash"]):
            raise ValueError(f"User-modified configuration: {path}; resolve before rerunning")
    for workspace in workspaces:
        user = workspace["githubUser"]
        account = authenticate(user)
        # GitHub verification requires an email verified on the signing account.
        result = run("gh", "api", "--hostname", "github.com", "user/emails", check=False)
        if result.returncode:
            run("gh", "auth", "refresh", "--hostname", "github.com", "--scopes", "user:email", capture=False)
            authenticate(user)
            result = run("gh", "api", "--hostname", "github.com", "user/emails")
        emails = json.loads(result.stdout)
        noreply = {f"{account['id']}+{account['login']}@users.noreply.github.com".lower(),
                   f"{account['login']}@users.noreply.github.com".lower()}
        if workspace["email"].lower() not in noreply and not any(
                email["verified"] and email["email"].lower() == workspace["email"].lower() for email in emails):
            raise ValueError(f"Verify {workspace['email']} on GitHub account {user}: https://github.com/settings/emails")
        previous = entries.get(workspace["name"])
        key, public = choose_key(workspace, previous)
        register_key(user, public)
        verify_access(user, key)
        if workspace["location"]:
            Path(workspace["location"]).mkdir(parents=True, exist_ok=True)
        content = workspace_config(workspace, account, key)
        path = root / (workspace["name"] + ".gitconfig")
        write(path, content)
        # Keep undeclared entries unchanged, including their include rules.
        entries[workspace["name"]] = {"location": workspace["location"], "key": str(key),
                                       "githubUser": user, "hash": digest(content)}
        includes = "# machine-setup: retained workspace includes\n"
        for name, entry in sorted(entries.items(), key=lambda item: (len(item[1]["location"] or ""), item[0] in declared_names)):
            condition = '[include]' if not entry["location"] else f'[includeIf {quote("gitdir:" + entry["location"] + "/")}]'
            includes += f"{condition}\n\tpath = {quote(root / (name + '.gitconfig'))}\n"
        write(index, includes)
        state["indexHash"] = digest(includes)
        write(state_file, json.dumps(state, indent=2) + "\n")
        existing = run("git", "config", "--global", "--get-all", "include.path", check=False)
        if existing.returncode not in (0, 1):
            raise ValueError(existing.stderr)
        if str(index) not in existing.stdout.splitlines():
            run("git", "config", "--global", "--add", "include.path", str(index))
        print(f"Workspace {workspace['name']}: configured {workspace['email']}, SSH access and commit signing.", flush=True)
    check_existing_repositories(workspaces, entries)


def main():
    config = json.loads(text("yq", "eval", "-o=json", ".", sys.argv[1]))
    workspaces = validate(config)
    if workspaces:
        provision(workspaces)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Workspace setup failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        sys.exit(1)
