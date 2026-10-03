# machine-setup

One-command setup for **Ubuntu, WSL Ubuntu, and macOS**, powered by [mise](https://mise.jdx.dev/).

## Install

Run in your Ubuntu or Mac terminal:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hellowin/machine-setup/main/bootstrap.sh)"
```

Run as your normal user, then open a new terminal. Ubuntu/WSL asks for your sudo
password for apt operations. macOS never uses sudo: Corporate IT must provide
Command Line Tools and install Homebrew through the managed software center.
Setup warns and stops if Homebrew is missing; install it manually through IT,
then rerun. With Homebrew available, setup installs/updates the declared formulae
as your normal user. It never runs the Homebrew or Command Line Tools installers.
If Ubuntu has no curl, install it first: `sudo apt-get update && sudo apt-get install -y curl`.

## What's included

- Git, curl, and Ubuntu build prerequisites.
- mise installation and activation in Bash and Zsh.
- Node 26 and Python 3.14, configured in `config/tools.toml`.

The checkout lives in `~/.local/share/machine-setup`. Rerun the install command to
update and reapply setup; existing checkout changes must be committed or stashed.
Declared apt/Homebrew packages upgrade when newer versions are available; equal,
newer, held, and pinned installations are preserved. No blanket OS upgrade runs.
macOS installs mise at `~/.local/bin/mise` and leaves any system/Homebrew mise
untouched. Mise uses native `self-update`, `install`, and `upgrade` behavior. Ranges such as
Node `26` track 26.x; exact pins stay pinned. Mise decides which runtime is active
and how old versions are pruned; there is no custom mise version override.
Existing shell settings are preserved, and conflicting mise configuration is not overwritten.

## Customize

Edit these files on a feature branch in your development checkout, then open a
pull request for review:

| File | Purpose |
| --- | --- |
| `config/tools.toml` | Enable mise tools and choose versions |
| `config/packages.ubuntu.txt` | Ubuntu/WSL apt packages |
| `config/packages.macos.txt` | macOS Homebrew formulae |
| `scripts/setup.sh` | Additional setup steps |

Keep tokens and private keys outside this public repository. Credentials and
personal/work account login are configured separately.

## Preview and develop

```bash
bash bootstrap.sh --dry-run  # Preview your local checkout
bash bootstrap.sh           # Apply your local checkout
bash tests/check.sh         # Run checks without installing packages
```

To preview on a new machine, add `-- --dry-run` to the install command.
For a release, replace `main` in the download URL with its tag and add
`-- --ref TAG` to the command. Use `latest` in mise configuration to follow its
latest channel, or retain ranges/pins to limit updates.

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

After a merge, CI validates `main` again and uploads a source archive with a
SHA-256 checksum as a GitHub Actions artifact, retained for 30 days. Download it
from the successful workflow run. The install URL above continues to follow
`main`; CI does not install software on a real machine or publish GitHub releases.

## Agents

Read `AGENTS.md` and the shared skill at
`.agents/skills/maintain-machine-setup/SKILL.md` before working on this repository.
Codex uses `AGENTS.md`, Claude uses `CLAUDE.md`, and Copilot uses
`.github/copilot-instructions.md`. All route to the same agent-neutral contract;
Claude and Copilot also have skill discovery links. Automatic loading depends
on the agent client and its instruction settings.
