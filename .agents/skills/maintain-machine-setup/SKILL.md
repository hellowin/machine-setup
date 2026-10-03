---
name: maintain-machine-setup
description: Maintain this repository's Ubuntu, WSL, and macOS bootstrap scripts, package manifests, mise configuration, and validation while preserving repeatable upgrade behavior.
---

# Maintain machine setup

Read this skill before inspecting implementation or changing this repository.
Apply the user's current request first; these are repository defaults, not
permission to install software on the operator's machine or publish changes.

## Contract

- Keep the public README install command working on fresh Ubuntu 24.04+,
  WSL Ubuntu, and macOS with IT-provisioned Command Line Tools. Use Bash
  3.2-compatible shell features for macOS.
- **macOS is office-managed and has no sudo.** Never invoke sudo, launch
  Command Line Tools installation, run Homebrew (including its installer), or
  update system/IT-managed binaries on macOS. Check existing commands listed in
  `config/packages.macos.txt` and fail with an IT prerequisite message if absent.
  Install and self-update mise at `~/.local/bin/mise` even when a system mise is
  on PATH; explicitly set the installer destination and reject a linked or
  non-writable local mise binary. Keep tools and activation
  in user-writable locations. New tools/backends must be checked for indirect
  privilege requirements before adding them to the macOS setup.
- **Ubuntu/WSL is personally managed with sudo available.** Keep sudo for apt
  metadata refreshes and guarded package installs/upgrades.
- Reruns converge to available updates for declared Ubuntu packages. Do not
  downgrade a newer OS package, reinstall an equal version, ignore package-manager pins,
  remove existing OS packages, or run a blanket OS upgrade.
- **Let mise handle its own versions.** Use native install, upgrade, and
  self-update commands or its owning package manager. Keep requests in
  `config/tools.toml`; do not implement custom mise version comparisons, rewrite
  requests to match installed binaries, use `--bump`, or force reinstall/update.
  Mise follows its native selection and pruning semantics, including pins and
  ranges; do not promise a custom no-downgrade rule for mise-managed runtimes.
- Add packages to the platform manifests and tools to `config/tools.toml`.
  Preserve user-selected ranges and unrelated machine configuration.
- Preview mode must not install, clone, update, write configuration, require
  credentials, or invoke privileged commands. Describe intended work honestly;
  it is not an exact online update plan.
- Keep shell activation duplicate-free and refuse conflicting managed config.
  Fail visibly on lookup or install errors rather than reporting success.
- Keep remote updates fast-forward only. Never discard dirty checkout changes
  or local commits. Setup must not dirty tracked files during ordinary runs.
- Keep secrets, credentials, Git identity, and work/personal logins outside this
  public repository. Repository authorization does not authorize machine setup.

## Where to work

`bootstrap.sh` locates or fetches the checkout. `scripts/setup.sh` orchestrates
Ubuntu packages, macOS prerequisites, mise, and activation. `scripts/packages.sh`
guards Ubuntu updates using native apt comparison. Manifests live in
`config/packages.*.txt`; the macOS manifest lists required existing commands,
not packages to install. `scripts/verify.sh` checks the resulting base tools.

## Pull request workflow

Develop changes on a feature branch and open a pull request with `gh` for the
user to review. Never push directly to the default branch, bypass its protection,
or merge a pull request without the user's explicit instruction to merge.
Keep unrelated working-tree changes out of the commit. Run the required checks
before pushing and include their results in the pull request description.

## Validate changes

Run `bash tests/check.sh` and `git diff --check`. Add regression coverage for
missing, older, equal, newer, held versions and meaningful failure cases
when changing updates. Use fake installers, isolated homes, and temporary
checkouts. Cover macOS with failing sudo/Homebrew/CLT installer mocks, missing
prerequisites, and a system mise on PATH. Do not run real apt or mise upgrades
to test code unless the user requests applying setup. The GitHub Actions matrix checks Ubuntu and
macOS; report any platform not actually exercised.

Keep README installation and update instructions concise and accurate. Keep
agent entry files pointing here rather than duplicating this contract.
