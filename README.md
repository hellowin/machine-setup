# machine-setup

One-command setup for **Ubuntu, WSL Ubuntu, and macOS**, powered by [mise](https://mise.jdx.dev/).

## Install

Run in your Ubuntu or Mac terminal:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hellowin/machine-setup/main/bootstrap.sh)"
```

Run as your normal user, then open a new terminal. Setup asks whether you have
access to sudo only when `~/.machine-setup.yml` does not exist, and saves your
answer there. Reruns read the YAML file without prompting. Change
`sudoEnabled` to `true` or `false` in that file to change the choice. An existing
file with a missing, null, or invalid sudo setting must be corrected before setup.
YAML configures the sudo choice and optional Git workspaces.

Ubuntu/WSL uses sudo for apt operations only when enabled. Without sudo, setup
prints package commands for you or an administrator to run and continues with
user-local mise and tools. Git, curl, and Zsh must already be available; build tools
may still be needed for some mise runtimes. If a required tool is missing, install
it manually and rerun. macOS requires existing Command Line Tools and Homebrew;
install them yourself or through Corporate IT/managed software center, then rerun.
Homebrew formula updates run as your normal user. Setup never runs the Homebrew
or Command Line Tools installers. If curl is missing, install it manually or ask
an administrator before running the download command.

## What's included

- Git, curl, and Ubuntu build prerequisites.
- mise installation and activation in Bash and Zsh.
- Zsh and [Oh My Zsh](https://ohmyz.sh/).
- Some tools configured in `config/tools.toml`.
- GitHub CLI and YAML tooling through mise; optional workspace identities, SSH access,
  and signed commits.

The checkout lives in `~/.local/share/machine-setup`. Rerun the install command to
update and reapply setup; existing checkout changes must be committed or stashed.
Declared apt/Homebrew packages upgrade when newer versions are available; equal,
newer, held, and pinned installations are preserved. No blanket OS upgrade runs.
macOS and Ubuntu without sudo install mise at `~/.local/bin/mise` and leave
any system/Homebrew mise untouched. Mise uses native `self-update`, `install`, and `upgrade` behavior. Ranges such as
Node `26` track 26.x; exact pins stay pinned. Mise decides which runtime is active
and how old versions are pruned; there is no custom mise version override.
Existing shell settings are preserved, and conflicting mise configuration is not overwritten.

Oh My Zsh is cloned into `~/.oh-my-zsh` and updated on reruns using fast-forward
Git updates. Dirty checkouts, local commits, and conflicting managed settings
stop setup without discarding changes. If `.zshrc` already loads Oh My Zsh independently,
setup preserves that configuration and installation; continue using its own
updater. After installation and verification, setup makes Zsh your default login
shell with `chsh`, unless your account already uses Zsh. It selects an executable
Zsh listed in `/etc/shells` and never edits that file. Ubuntu/WSL uses sudo for
this change when enabled; without sudo, and on macOS, `chsh` runs as your user
and may ask for your account password. If the change is denied, setup stops
with instructions to retry or ask an administrator.

Close the terminal and open a new session after setup. In WSL, reopen Ubuntu.
If your terminal profile explicitly launches Bash, remove that override so it
uses the account login shell. To change an existing installation immediately,
run `chsh -s "$(command -v zsh)"`, then reopen Ubuntu. Zsh configuration honors
an exported `ZDOTDIR`.

For a setup-managed installation, set `ZSH_THEME="your-theme"` and/or
`plugins=(git z ...)` before the `# machine-setup: Oh My Zsh` line in `.zshrc`.
Try `gst` for Git status, `gd` for diff, and `z machine-setup` to jump back to
this directory after visiting it. Autosuggestions, syntax highlighting, and
fzf are optional additions and are not installed by this setup.

## Customize

Edit these files on a feature branch in your development checkout, then open a
pull request for review:

| File | Purpose |
| --- | --- |
| `.machine-setup.yml` | Default host configuration (copied into home; host edits are preserved) |
| `config/tools.toml` | Enable mise tools and choose versions |
| `config/oh-my-zsh.zsh` | Default Oh My Zsh theme, plugins, and update policy |
| `config/packages.ubuntu.txt` | Ubuntu/WSL apt packages |
| `config/packages.macos.txt` | macOS Homebrew formulae |
| `scripts/setup.sh` | Additional setup steps |

Keep tokens, private keys, and personal/work identities outside this public
repository. Configure workspaces in the host file as described below.

## Git workspaces

Add workspaces to `~/.machine-setup.yml`, then run the same installation command:

```yaml
sudoEnabled: false
workspaces:
  - name: default
    email: me@example.com
    githubUser: my-github-account
  - name: work
    location: ~/workspace/work
    email: me@company.com
    githubUser: my-work-account
    # Optional: reuse a particular local private key.
    # privateKey: ~/.ssh/id_ed25519_work
    # Optional: otherwise use your GitHub display name or username.
    # gitName: My Name
```

Setup creates declared workspace directories and uses Git conditional includes
to select the email, SSH identity, and commit signing for repositories underneath
each location. One entry without a location supplies the global fallback. Nested
workspaces take precedence over their parents. Names must be unique; declared
locations must be unique and absolute or start with `~/`.

Run interactively. Setup selects the declared GitHub account or guides browser
login, checks the account matches, and requests any missing key-upload/email
permissions through browser authorization. The email must be verified on that
account (its GitHub noreply address is also supported). If needed, verify it at
[GitHub email settings](https://github.com/settings/emails) and rerun.

Without `privateKey`, setup reuses its previously selected key or an unambiguous
local key registered to that GitHub account. Otherwise it generates an Ed25519
key at `~/.ssh/machine-setup-USERNAME`, asking you to choose a passphrase. An
explicit missing `privateKey` is generated at the given path. Existing keys are
never replaced. Setup derives/checks the public key and registers it with GitHub
for both authentication and signing, skipping existing registrations. Private
keys remain local. See GitHub's
[key generation guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent).

Setup verifies SSH authentication as the expected account and exercises signing
before reporting success. Passphrase-protected keys may prompt during setup and
later Git operations; you can load them into your existing SSH agent with
`ssh-add ~/.ssh/machine-setup-USERNAME`. Confirm GitHub's host key when SSH asks;
see its [published fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints).

Inside configured repositories, GitHub HTTPS remotes are routed through SSH with
the selected workspace key, allowing fetch/pull/push without depending on the
currently active `gh` account. This configures access to repositories the account
is authorized to use; it does not clone repositories or grant permissions.
Organization SSO may require separately
[authorizing the SSH key](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-single-sign-on/authorizing-an-ssh-key-for-use-with-single-sign-on).
For initial clones with multiple accounts, use `gh repo clone` with the intended
account active, or `git -c core.sshCommand='ssh -i KEY -o IdentitiesOnly=yes' clone git@github.com:OWNER/REPO.git`.

New commits inherit SSH signing automatically. Existing repository overrides
are preserved; setup reports conflicting identity, signing, or SSH settings in
existing workspace repositories and asks you to resolve them. Explicit Git
command options and environment variables can still override configuration.
Linked worktrees inherit the identity selected by their common Git directory.

Reruns update declared entries and add new ones without duplicate includes.
Removing an entry leaves its directory, key, GitHub registrations, configuration
file, and include in place for you to manage. New declared entries take precedence
over retained entries at the same location. Generated Git files live under
`~/.config/machine-setup/git` (or `$XDG_CONFIG_HOME/machine-setup/git`); setup stops
if an actively managed file was edited manually. An absent or empty workspace
list makes no Git or account changes. The host YAML is preserved on every rerun;
changes to the repository template do not update an existing host file.

## Preview and develop

```bash
bash bootstrap.sh --dry-run  # Preview your local checkout
bash bootstrap.sh           # Ask about sudo on first run, then apply
bash tests/check.sh         # Run checks without installing packages
```

To preview on a new machine, add `-- --dry-run` to the install command.
Use `--repo HTTPS_URL` to select a remote repository and `MACHINE_SETUP_DIR`
to override the remote checkout destination. For a release, replace `main` in
the download URL with its tag and add `-- --ref TAG` to the command.
Use `latest` in mise configuration to follow its latest channel, or retain
ranges/pins to limit updates.

CI checks Ubuntu and macOS syntax, previews, safe reruns, update behavior, config
preservation, and whitespace with fake installers. Full clean-machine
installation is not yet verified.

All changes to `main` must go through a pull request. Branch protection applies
to administrators, requires the `Required checks` status and an up-to-date branch,
and blocks force pushes and branch deletion. Review changes in the PR before
merging; agents must wait for an explicit instruction to merge. PRs opened with
the owner's `gh` login are authored by the owner, so a separate approving review
is not required (GitHub does not allow authors to approve their own PRs).

```bash
git switch -c feature/my-change
# Edit files, then validate before committing and pushing.
bash tests/check.sh
git diff --check
git add <changed-files>
git commit -m "Describe the change"
git push -u origin feature/my-change
gh pr create --base main
```

After a merge, CI validates `main` again. The install URL above continues to
follow `main`.

## Agents

Read `AGENTS.md` and the shared skill at
`.agents/skills/maintain-machine-setup/SKILL.md` before working on this repository.
Codex uses `AGENTS.md`, Claude uses `CLAUDE.md`, and Copilot uses
`.github/copilot-instructions.md`. All route to the same agent-neutral contract;
Claude and Copilot also have skill discovery links. Automatic loading depends
on the agent client and its instruction settings.
