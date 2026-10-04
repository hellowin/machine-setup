#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for file in bootstrap.sh scripts/*.sh tests/*.sh; do
  bash -n "$file"
done
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
# CLI previews must not prompt or write anything, even without a host YAML file.
mkdir -p "$scratch/home"
HOME="$scratch/home" bash bootstrap.sh --dry-run > "$scratch/local-plan"
grep -q 'Would install mise' "$scratch/local-plan"
[ -z "$(ls -A "$scratch/home")" ]
for option in --sudo --no-sudo --unknown; do
  if HOME="$scratch/home" bash bootstrap.sh "$option" > /dev/null 2>&1; then
    echo "CLI argument unexpectedly accepted: $option" >&2; exit 1
  fi
  if HOME="$scratch/home" bash scripts/setup.sh ubuntu "$option" > /dev/null 2>&1; then
    echo "Setup argument unexpectedly accepted: $option" >&2; exit 1
  fi
done
HOME="$scratch/home" bash bootstrap.sh --help > "$scratch/help"
grep -q -- '--ref' "$scratch/help"
HOME="$scratch/home" MACHINE_SETUP_DIR="$scratch/checkout" bash bootstrap.sh --dry-run \
  --repo https://github.com/example/machine-setup.git --ref release > "$scratch/remote-plan"
grep -q "at release into $scratch/checkout" "$scratch/remote-plan"
[ ! -e "$scratch/checkout" ]
# The exact download-and-run form defaults to the public repository.
HOME="$scratch/home" bash -c "$(cat bootstrap.sh)" -- --dry-run > "$scratch/default-plan"
grep -q 'https://github.com/hellowin/machine-setup.git' "$scratch/default-plan"
run_setup() {
  bash scripts/setup.sh "$@"
}
for platform in ubuntu macos; do
  HOME="$scratch/home" run_setup "$platform" --dry-run > "$scratch/$platform-plan"
  grep -q 'git' "$scratch/$platform-plan"
  grep -q 'Would install or fast-forward update Oh My Zsh' "$scratch/$platform-plan"
  grep -q 'Would set Zsh as the account login shell' "$scratch/$platform-plan"
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
cat > "$scratch/bin/git" <<'MOCK'
#!/usr/bin/env bash
case "${1:-}" in
  clone)
    for arg in "$@"; do destination=$arg; done
    mkdir -p "$destination/.git"
    touch "$destination/oh-my-zsh.sh"
    ;;
  config)
    case "${3:-}" in --get-all) exit 1 ;; --add) exit 0 ;; *) exit 1 ;; esac
    ;;
  -C)
    case "${3:-}" in
      remote) echo 'https://github.com/ohmyzsh/ohmyzsh.git' ;;
      symbolic-ref) echo master ;;
      status|fetch|merge-base|merge) exit 0 ;;
      *) exit 1 ;;
    esac ;;
  *) exit 1 ;;
esac
MOCK
cat > "$scratch/bin/zsh" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
cat > "$scratch/bin/vim" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
cat > "$scratch/bin/getent" <<'MOCK'
#!/usr/bin/env bash
printf '%s:x:1000:1000::/home/test:/bin/zsh\n' "$2"
MOCK
cat > "$scratch/bin/dscl" <<'MOCK'
#!/usr/bin/env bash
printf 'UserShell: /bin/zsh\n'
MOCK
cat > "$scratch/bin/chsh" <<'MOCK'
#!/usr/bin/env bash
echo 'Unexpected host shell change.' >&2
exit 1
MOCK
chmod +x "$scratch/bin/"*
for platform in ubuntu macos; do
  test_home=$scratch/home-$platform
  mkdir -p "$test_home/.local/bin"
  cat > "$test_home/.local/bin/mise" <<'MOCK'
#!/usr/bin/env bash
case "${1:-}" in trust|install|upgrade|self-update|exec|--version|ls) exit 0 ;; *) exit 1 ;; esac
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
  [ "$(grep -c 'machine-setup: Oh My Zsh' "$test_home/.zshrc")" -eq 1 ]
  [ -f "$test_home/.oh-my-zsh/oh-my-zsh.sh" ]
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
python3 -B tests/test_oh_my_zsh.py
python3 -B tests/test_default_shell.py
python3 -B tests/test_workspaces.py
python3 -B tests/test_git_preferences.py
