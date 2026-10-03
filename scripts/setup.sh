#!/usr/bin/env bash
set -euo pipefail
setup_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
platform=${1:?Expected ubuntu or macos}
dry_run=${2:-}
case "$platform" in ubuntu|macos) ;; *) echo 'Unsupported platform.' >&2; exit 2 ;; esac

if [ "$dry_run" = --dry-run ]; then
  printf 'Platform: %s\n' "$platform"
  if [ "$platform" = macos ]; then
    printf 'Would require existing Command Line Tools and Homebrew, then update these formulae without sudo:\n'
  else
    printf 'Would update apt packages using sudo:\n'
  fi
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
  # IT provisions Command Line Tools and Homebrew; never run their installers.
  if ! xcode-select -p >/dev/null 2>&1; then
    echo 'macOS requires existing Command Line Tools. Ask IT to provision them, then rerun; setup never installs them or uses sudo.' >&2
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
    echo 'Warning: Homebrew is not installed or available. Install Homebrew manually through Corporate IT/managed software center, then rerun setup. Setup never installs Homebrew or uses sudo on macOS.' >&2
    exit 1
  fi
  brew update
  upgrade_brew_packages "${packages[@]}"
fi

# A user-local symlink could still target an IT-managed binary.
if [ "$platform" = macos ]; then
  local_mise=$HOME/.local/bin/mise
  if [ -L "$local_mise" ] || { [ -e "$local_mise" ] && { [ ! -w "$local_mise" ] || [ ! -w "$HOME/.local/bin" ]; }; }; then
    printf 'Move linked or non-writable %s aside; macOS requires a writable user-local mise binary.\n' "$local_mise" >&2
    exit 1
  fi
fi

if [ -x "$HOME/.local/bin/mise" ]; then
  mise_bin=$HOME/.local/bin/mise
elif [ "$platform" = ubuntu ] && command -v mise >/dev/null 2>&1; then
  mise_bin=$(command -v mise)
else
  installer=$(mktemp)
  curl -fsSL https://mise.run -o "$installer"
  MISE_INSTALL_PATH="$HOME/.local/bin/mise" sh "$installer"
  rm -f "$installer"
  mise_bin=$HOME/.local/bin/mise
fi
# macOS always uses the user-local binary, leaving IT-managed mise untouched.
# Ubuntu updates mise through its owner; standalone binaries use self-update.
case "$mise_bin" in
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
