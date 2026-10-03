#!/usr/bin/env bash
set -euo pipefail
setup_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
platform=${1:?Expected ubuntu or macos}
dry_run=${2:-}
case "$platform" in ubuntu|macos) ;; *) echo 'Unsupported platform.' >&2; exit 2 ;; esac

if [ "$dry_run" = --dry-run ]; then
  printf 'Platform: %s\nPackage list:\n' "$platform"
  cat "$setup_dir/config/packages.$platform.txt"
  printf '\nWould install mise, link config/tools.toml into ~/.config/mise/conf.d,\nupgrade configured tools using mise, and add mise activation to .bashrc and .zshrc.\n'
  exit 0
fi

# Preflight the only managed file before installing packages.
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/mise/conf.d
config_target=$config_dir/machine-setup.toml
if [ -e "$config_target" ] || [ -L "$config_target" ]; then
  if [ ! -L "$config_target" ] || [ "$(readlink "$config_target")" != "$setup_dir/config/tools.toml" ]; then
    printf 'Move existing %s aside before setup; it will not be overwritten.\n' "$config_target" >&2
    exit 1
  fi
fi

. "$setup_dir/scripts/packages.sh"

packages=()
while IFS= read -r package || [ -n "$package" ]; do
  case "$package" in ''|\#*) continue ;; esac
  packages+=("$package")
done < "$setup_dir/config/packages.$platform.txt"

if [ "$platform" = ubuntu ]; then
  sudo apt-get update
  upgrade_apt_packages "${packages[@]}"
else
  if ! xcode-select -p >/dev/null 2>&1; then
    xcode-select --install
    echo 'Finish installing Command Line Tools, then rerun setup.' >&2
    exit 1
  fi
  # Homebrew's standard paths cover Apple Silicon and Intel Macs.
  if ! command -v brew >/dev/null 2>&1; then
    if [ -x /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
  if ! command -v brew >/dev/null 2>&1; then
    installer=$(mktemp)
    curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
    /bin/bash "$installer"
    rm -f "$installer"
    if [ -x /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    else
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
  brew update
  upgrade_brew_packages "${packages[@]}"
fi

if [ -x "$HOME/.local/bin/mise" ]; then
  mise_bin=$HOME/.local/bin/mise
elif command -v mise >/dev/null 2>&1; then
  mise_bin=$(command -v mise)
else
  installer=$(mktemp)
  curl -fsSL https://mise.run -o "$installer"
  sh "$installer"
  rm -f "$installer"
  mise_bin=$HOME/.local/bin/mise
fi
# Update mise through its owner; standalone binaries use native self-update.
case "$mise_bin" in
  /opt/homebrew/*|/usr/local/Cellar/*|/usr/local/bin/mise)
    if [ "$platform" = macos ] && brew list --formula mise >/dev/null 2>&1; then
      upgrade_brew_packages mise
    else
      "$mise_bin" self-update --yes
    fi ;;
  /usr/bin/mise)
    if [ "$platform" = ubuntu ] && dpkg-query -S "$mise_bin" >/dev/null 2>&1; then
      upgrade_apt_packages mise
    else
      "$mise_bin" self-update --yes
    fi ;;
  *) "$mise_bin" self-update --yes ;;
esac
mkdir -p "$config_dir"
if [ ! -L "$config_target" ]; then
  ln -s "$setup_dir/config/tools.toml" "$config_target"
fi
cd "$setup_dir"
# Explicit trust is limited to this setup repository.
"$mise_bin" trust "$setup_dir/mise.toml"
"$mise_bin" trust "$setup_dir/config/tools.toml"
# Native mise semantics: install missing versions, then upgrade within requests.
# Do not compare versions ourselves, bump requests, or force reinstalls.
"$mise_bin" install
"$mise_bin" upgrade

# Quote the executable path for Bash/Zsh; this also handles paths with spaces.
printf -v quoted_mise '%q' "$mise_bin"
for shell_name in bash zsh; do
  rc_file=$HOME/.${shell_name}rc
  activation="eval \"\$($quoted_mise activate $shell_name)\""
  if ! grep -Fqx "$activation" "$rc_file" 2>/dev/null; then
    printf '\n# machine-setup: mise tools and environment\n%s\n' "$activation" >> "$rc_file"
  fi
done
bash "$setup_dir/scripts/verify.sh" "$mise_bin"
echo 'Setup complete. Open a new terminal to load mise.'
