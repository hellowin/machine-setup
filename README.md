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
Only the sudo choice is configured through YAML.

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
- Zsh and [Oh My Zsh](https://ohmyz.sh/), with the `robbyrussell` theme and `git`/`z` plugins.
- Node 26 and Python 3.14, configured in `config/tools.toml`.

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
updater. Setup does not change your login shell: run `zsh` to try it, or select
Zsh in your terminal settings. Zsh configuration honors an exported `ZDOTDIR`.

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

Keep tokens and private keys outside this public repository. Credentials and
personal/work account login are configured separately.

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
