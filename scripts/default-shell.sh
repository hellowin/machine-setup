#!/usr/bin/env bash

account_login_shell() {
  if [ "$platform" = macos ]; then
    dscl . -read "/Users/$1" UserShell | awk '$1 == "UserShell:" && NF == 2 { print $2 }'
  else
    getent passwd "$1" | awk -F: -v account="$1" '$1 == account && NF == 7 { print $7 }'
  fi
}

set_default_zsh() {
  local account current_shell zsh_shell candidate shells_file
  shells_file=${1:-/etc/shells}
  account=$(id -un) || return 1
  current_shell=$(account_login_shell "$account") || {
    printf 'Cannot look up the login shell for %s; it was not changed.\n' "$account" >&2
    return 1
  }
  if [ -z "$account" ] || [ -z "$current_shell" ]; then
    printf 'Cannot determine the account login shell; it was not changed.\n' >&2
    return 1
  fi
  # Keep an existing Zsh choice, including a different registered Zsh path.
  case "$current_shell" in
    /*/zsh) printf 'Zsh is already the default login shell for %s.\n' "$account"; return 0 ;;
  esac

  if [ ! -r "$shells_file" ]; then
    printf 'Cannot read %s. Ask an administrator to register Zsh as a login shell, then rerun.\n' "$shells_file" >&2
    return 1
  fi
  zsh_shell=$(command -v zsh) || return 1
  # Homebrew Zsh may not be registered; use an existing registered Zsh instead.
  if [ ! -x "$zsh_shell" ] || ! grep -Fxq "$zsh_shell" "$shells_file"; then
    zsh_shell=
    while IFS= read -r candidate || [ -n "$candidate" ]; do
      case "$candidate" in
        /*/zsh)
          if [ -x "$candidate" ]; then zsh_shell=$candidate; break; fi ;;
      esac
    done < "$shells_file"
  fi
  if [ -z "$zsh_shell" ]; then
    printf 'No executable Zsh is registered in %s. Ask an administrator to register Zsh, then rerun.\n' "$shells_file" >&2
    return 1
  fi
  if ! command -v chsh >/dev/null 2>&1; then
    printf 'Missing chsh. Ask an administrator to set the login shell for %s to %s.\n' "$account" "$zsh_shell" >&2
    return 1
  fi
  printf 'Setting the default login shell for %s to %s.\n' "$account" "$zsh_shell"
  if [ "$platform" = ubuntu ] && [ "$sudo_enabled" = true ]; then
    if ! sudo chsh -s "$zsh_shell" "$account"; then
      printf 'Could not change the login shell. Run manually: sudo chsh -s %q %q\n' "$zsh_shell" "$account" >&2
      return 1
    fi
  elif ! chsh -s "$zsh_shell" "$account"; then
    printf 'Could not change the login shell. Run manually: chsh -s %q %q\nOr ask your administrator to make the change.\n' "$zsh_shell" "$account" >&2
    return 1
  fi
  current_shell=$(account_login_shell "$account") || return 1
  if [ "$current_shell" != "$zsh_shell" ]; then
    printf 'The account login shell was not updated to %s. Ask an administrator to check the account, then rerun.\n' "$zsh_shell" >&2
    return 1
  fi
}
