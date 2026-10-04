#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for file in bootstrap.sh scripts/*.sh tests/*.sh; do
  bash -n "$file"
done
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
# Preview must work without credentials, a writable home, or installer calls.
HOME="$scratch/home" bash bootstrap.sh --dry-run > "$scratch/local-plan"
[ ! -e "$scratch/home" ]
grep -q 'Would install mise' "$scratch/local-plan"
HOME="$scratch/home" MACHINE_SETUP_DIR="$scratch/checkout" bash bootstrap.sh --dry-run \
  --repo https://github.com/example/machine-setup.git > "$scratch/remote-plan"
[ ! -e "$scratch/checkout" ]
if bash bootstrap.sh --unknown > /dev/null 2>&1; then
  echo 'Unknown option unexpectedly accepted.' >&2; exit 1
fi
if bash bootstrap.sh --repo > /dev/null 2>&1; then
  echo 'Missing repo argument unexpectedly accepted.' >&2; exit 1
fi
if bash bootstrap.sh --dry-run --repo file:///tmp/repo > /dev/null 2>&1; then
  echo 'Non-HTTPS repository unexpectedly accepted.' >&2; exit 1
fi
# The exact download-and-run form must default to our public repository.
HOME="$scratch/home" bash -c "$(cat bootstrap.sh)" -- --dry-run > "$scratch/default-plan"
grep -q 'https://github.com/hellowin/machine-setup.git' "$scratch/default-plan"
[ ! -e "$scratch/home" ]
# Check both package manifests even when running on only one platform.
for platform in ubuntu macos; do
  bash scripts/setup.sh "$platform" --dry-run > "$scratch/$platform-plan"
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
  sudo_option=--no-sudo
  if [ "$platform" = ubuntu ]; then sudo_option=--sudo; fi
  for iteration in 1 2; do
    MOCK_PLATFORM="$platform" HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" PATH="$scratch/bin:$PATH" \
      bash scripts/setup.sh "$platform" "$sudo_option" > "$scratch/$platform-apply"
  done
  [ "$(grep -c 'activate bash' "$test_home/.bashrc")" -eq 1 ]
  [ "$(grep -c 'activate zsh' "$test_home/.zshrc")" -eq 1 ]
  grep -q '# Existing shell configuration' "$test_home/.bashrc"
  [ -L "$test_home/.config/mise/conf.d/machine-setup.toml" ]
  rm "$test_home/.config/mise/conf.d/machine-setup.toml"
  printf 'existing config\n' > "$test_home/.config/mise/conf.d/machine-setup.toml"
  if MOCK_PLATFORM="$platform" HOME="$test_home" XDG_CONFIG_HOME="$test_home/.config" PATH="$scratch/bin:$PATH" \
    bash scripts/setup.sh "$platform" "$sudo_option" > /dev/null 2>&1; then
    echo 'Conflicting config unexpectedly overwritten.' >&2; exit 1
  fi
  grep -qx 'existing config' "$test_home/.config/mise/conf.d/machine-setup.toml"
done
printf 'Syntax, previews, repeated setup, and configuration preservation checks passed.\n'

python3 tests/test_updates.py
