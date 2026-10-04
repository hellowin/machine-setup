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
- **Privilege access is a user choice, independent of OS.** Ask whether sudo is
  available only when `~/.machine-setup.yml` does not exist, persist
  `sudoEnabled`, and reuse it on reruns. Existing host files must specify
  `sudoEnabled: true` or `false`; never prompt to repair them. All setup settings
  come from YAML; reject CLI arguments and do not use environment overrides
  for those settings. Keep the repository's `.machine-setup.yml` as the
  default template; do not overwrite unrelated host configuration.
- Ubuntu/WSL uses sudo for apt metadata refreshes and guarded package updates
  only when enabled. Without sudo, show manual package instructions and continue
  user-local setup if required tools are present. Never try unprivileged apt
  writes. Missing bootstrap prerequisites must give actionable instructions.
- macOS requires existing Command Line Tools and Homebrew. Discover Homebrew on
  PATH or at its standard Apple Silicon/Intel prefixes. If missing, direct the
  user to manual installation or IT and stop before package updates or config
  writes. Never launch these installers automatically. Homebrew formula updates
  use normal user permissions regardless of the sudo choice.
- macOS and all no-sudo setups install/self-update mise at `~/.local/bin/mise`,
  ignoring system mise. Set the installer destination explicitly and reject a
  linked or non-writable local binary. Keep tools and activation user-writable.
  Check new formulae/tools/backends for indirect privilege requirements before
  adding them to no-sudo setup.
- Reruns converge to available updates for declared apt/Homebrew packages. Do not
  downgrade a newer OS package, reinstall an equal version, ignore package-manager
  pins, remove existing OS packages, or run a blanket OS upgrade.
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
platform packages, mise, and activation. `scripts/packages.sh` guards package
updates using native apt comparison and Homebrew metadata; `brew-action.rb`
compares Homebrew formula versions and revisions. Package lists live in
`config/packages.*.txt`. `scripts/verify.sh` checks the resulting base tools.

## Pull request workflow

Develop changes on a feature branch and open a pull request with `gh` for the
user to review. Never push directly to the default branch, bypass its protection,
or merge a pull request without the user's explicit instruction to merge.
Keep unrelated working-tree changes out of the commit. Run the required checks
before pushing and include their results in the pull request description.

## Validate changes

Run `bash tests/check.sh` and `git diff --check`. Add regression coverage for
missing, older, equal, newer, held/pinned versions and meaningful failure cases
when changing updates. Use fake installers, isolated homes, and temporary
checkouts. Cover macOS with failing sudo/CLT installer mocks, missing Homebrew
and Command Line Tools, successful brew updates, and a system mise on PATH.
Do not run real apt, Homebrew, or mise upgrades to test code unless the user
requests applying setup. The GitHub Actions matrix checks Ubuntu and macOS;
report any platform not actually exercised.

Keep README installation and update instructions concise and accurate. Keep
agent entry files pointing here rather than duplicating this contract.
