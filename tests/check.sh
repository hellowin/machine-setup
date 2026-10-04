#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for file in bootstrap.sh scripts/*.sh tests/*.sh; do
  bash -n "$file"
done
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
# YAML previews must not prompt or write anything.
mkdir -p "$scratch/home"
printf 'sudoEnabled: false\ndryRun: true\n' > "$scratch/home/.machine-setup.yml"
HOME="$scratch/home" bash bootstrap.sh > "$scratch/local-plan"
grep -q 'Would install mise' "$scratch/local-plan"
[ "$(ls -A "$scratch/home" | wc -l | tr -d ' ')" -eq 1 ]
for option in --sudo --no-sudo --dry-run --repo --ref --help --unknown ubuntu; do
  for entrypoint in bootstrap.sh scripts/setup.sh; do
    if HOME="$scratch/home" bash "$entrypoint" "$option" > /dev/null 2>&1; then
      echo "CLI argument unexpectedly accepted: $entrypoint $option" >&2; exit 1
    fi
  done
done
printf 'sudoEnabled: false\ndryRun: true\nrepository: https://github.com/example/machine-setup.git\nref: release\nsetupDir: %s/checkout\n' "$scratch" > "$scratch/home/.machine-setup.yml"
HOME="$scratch/home" MACHINE_SETUP_DIR="$scratch/ignored" bash bootstrap.sh > "$scratch/remote-plan"
grep -q "at release into $scratch/checkout" "$scratch/remote-plan"
[ ! -e "$scratch/checkout" ]
printf 'sudoEnabled: false\ndryRun: true\n' > "$scratch/home/.machine-setup.yml"
# The exact download-and-run form defaults to the public repository.
HOME="$scratch/home" bash -c "$(cat bootstrap.sh)" > "$scratch/default-plan"
grep -q 'https://github.com/hellowin/machine-setup.git' "$scratch/default-plan"
# Internal helper allows both package manifests to be tested on each CI host.
run_setup() {
  bash -c 'set -euo pipefail; setup_dir=$PWD; platform=$1;
    . ./bootstrap.sh; read_setup_config;
    if ! "$dry_run"; then choose_setup_sudo; fi;
    . ./scripts/setup.sh; setup_main' test "$1"
}
for platform in ubuntu macos; do
  HOME="$scratch/home" run_setup "$platform" > "$scratch/$platform-plan"
  grep -q 'git' "$scratch/$platform-plan"
done
# Exercise actual setup control flow using isolated homes and fake installers.
mkdir -p "$scratch/bin"
cat > "$scratch/bin/sudo" <<'MOCK'
#!/usr/bin/env bash
[ "${MOCK_PLATFORM:-}" = ubuntu ] || { echo "Unexpected sudo on macOS." >&2; exit 1; }
[ "${1:-}" = apt-get ] || exit 1
MOCK
cat > "$scratch/bin/brew" <<'MOCK'
#!/usr/bin/env bash
case "${1:-}" in
  info) printf '{"formulae":[{"installed":[],"versions":{"stable":"1.0"}}]}\n' ;;
  update|install|upgrade) exit 0 ;;
  *) exit 1 ;;
esac
MOCK
cat > "$scratch/bin/ruby" <<'MOCK'
#!/usr/bin/env bash
cat >/dev/null
printf 'install\n'
MOCK
cat > "$scratch/bin/apt-mark" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
cat > "$scratch/bin/apt-cache" <<'MOCK'
#!/usr/bin/env bash
printf 'Installed: (none)\nCandidate: 1.0\n'
MOCK
cat > "$scratch/bin/xcode-select" <<'MOCK'
#!/usr/bin/env bash
[ "${1:-}" = -p ] || { echo "Unexpected CLT installer invocation." >&2; exit 1; }
MOCK
cat > "$scratch/bin/curl" <<'MOCK'
#!/usr/bin/env bash
echo 'Unexpected installer download in isolated check.' >&2
exit 1
MOCK
chmod +x "$scratch/bin/"*
for platform in ubuntu macos; do
  test_home=$scratch/home-$platform
  mkdir -p "$test_home/.local/bin"
  cat > "$test_home/.local/bin/mise" <<'MOCK'
#!/usr/bin/env bash
case "${1:-}" in trust|install|upgrade|self-update|--version|ls) exit 0 ;; *) exit 1 ;; esac
MOCK
  chmod +x "$test_home/.local/bin/mise"
  printf '# Existing shell configuration\n' > "$test_home/.bashrc"
  sudo_choice=false
  if [ "$platform" = ubuntu ]; then sudo_choice=true; fi
  printf 'sudoEnabled: %s\n' "$sudo_choice" > "$test_home/.machine-setup.yml"
  for iteration in 1 2; do
    MOCK_PLATFORM="$platform" HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" PATH="$scratch/bin:$PATH" \
      run_setup "$platform" > "$scratch/$platform-apply"
  done
  [ "$(grep -c 'activate bash' "$test_home/.bashrc")" -eq 1 ]
  [ "$(grep -c 'activate zsh' "$test_home/.zshrc")" -eq 1 ]
  grep -q '# Existing shell configuration' "$test_home/.bashrc"
  [ -L "$test_home/.config/mise/conf.d/machine-setup.toml" ]
  rm "$test_home/.config/mise/conf.d/machine-setup.toml"
  printf 'existing config\n' > "$test_home/.config/mise/conf.d/machine-setup.toml"
  if MOCK_PLATFORM="$platform" HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" PATH="$scratch/bin:$PATH" \
    run_setup "$platform" > /dev/null 2>&1; then
    echo 'Conflicting config unexpectedly overwritten.' >&2; exit 1
  fi
  grep -qx 'existing config' "$test_home/.config/mise/conf.d/machine-setup.toml"
done
printf 'Syntax, previews, repeated setup, and configuration preservation checks passed.\n'

python3 tests/test_updates.py
