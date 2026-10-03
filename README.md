# machine-setup

One-command setup for **Ubuntu, WSL Ubuntu, and macOS**, powered by [mise](https://mise.jdx.dev/).

## Install

Run in your Ubuntu or Mac terminal:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hellowin/machine-setup/main/bootstrap.sh)"
```

Run as your normal user. Enter your password when asked, then open a new terminal.
On a fresh Mac, finish Apple's Command Line Tools installation if prompted and
rerun the command. Homebrew may also ask for confirmation.
If Ubuntu has no curl, install it first: `sudo apt-get update && sudo apt-get install -y curl`.

## What's included

- Git, curl, and Ubuntu build prerequisites.
- mise installation and activation in Bash and Zsh.
- Node 26 and Python 3.14, configured in `config/tools.toml`.

The checkout lives in `~/.local/share/machine-setup`. Rerun the install command to
update and reapply setup; existing checkout changes must be committed or stashed.
Declared apt/Homebrew packages upgrade when newer versions are available; equal,
newer, held, and pinned installations are preserved. No blanket OS upgrade runs.
Mise uses native `self-update`, `install`, and `upgrade` behavior. Ranges such as
Node `26` track 26.x; exact pins stay pinned. Mise decides which runtime is active
and how old versions are pruned; there is no custom mise version override.
Existing shell settings are preserved, and conflicting mise configuration is not overwritten.

## Customize

Edit these files in your development checkout and push to GitHub:

| File | Purpose |
| --- | --- |
| `config/tools.toml` | Enable mise tools and choose versions |
| `config/packages.ubuntu.txt` | Ubuntu/WSL apt packages |
| `config/packages.macos.txt` | macOS Homebrew packages |
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

CI checks Ubuntu and macOS syntax, previews, safe reruns, and config preservation
with fake installers. Full clean-machine installation is not yet verified.

## Agents

Read `AGENTS.md` and the shared skill at
`.agents/skills/maintain-machine-setup/SKILL.md` before working on this repository.
Codex uses `AGENTS.md`, Claude uses `CLAUDE.md`, and Copilot uses
`.github/copilot-instructions.md`. All route to the same agent-neutral contract;
Claude and Copilot also have skill discovery links. Automatic loading depends
on the agent client and its instruction settings.
