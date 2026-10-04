#!/usr/bin/env bash

# Never evaluate the user's shell configuration during setup.
preflight_oh_my_zsh() {
  omz_dir=$HOME/.oh-my-zsh
  zsh_rc=${ZDOTDIR:-$HOME}/.zshrc
  printf -v omz_source 'source %q' "$setup_dir/config/oh-my-zsh.zsh"
  omz_mode=new
  if [ -e "$zsh_rc" ] || [ -L "$zsh_rc" ]; then
    if [ ! -f "$zsh_rc" ] || [ ! -r "$zsh_rc" ]; then
      printf 'Cannot read Zsh configuration: %s\n' "$zsh_rc" >&2
      return 1
    fi
    if grep -Fq 'machine-setup: Oh My Zsh' "$zsh_rc"; then
      if [ "$(grep -Fxc "$omz_source" "$zsh_rc")" != 1 ] ||
         [ "$(grep -Fc 'machine-setup: Oh My Zsh' "$zsh_rc")" != 1 ] ||
         [ "$(grep -Ec '^[[:space:]]*[^#].*(oh-my-zsh\.sh|oh-my-zsh\.zsh)' "$zsh_rc")" != 1 ]; then
        printf 'Conflicting managed Oh My Zsh configuration in %s; resolve it before rerunning.\n' "$zsh_rc" >&2
        return 1
      fi
      omz_mode=managed
    elif grep -Eq '^[[:space:]]*[^#].*(oh-my-zsh\.sh|oh-my-zsh\.zsh)' "$zsh_rc"; then
      omz_mode=existing
      return 0
    fi
  fi
  if [ -L "$omz_dir" ] || { [ -e "$omz_dir" ] && [ ! -d "$omz_dir/.git" ]; }; then
    printf 'Move conflicting %s aside; setup requires an Oh My Zsh Git checkout.\n' "$omz_dir" >&2
    return 1
  fi
  if [ -d "$omz_dir" ]; then
    omz_remote=$(git -C "$omz_dir" remote get-url origin) || return 1
    case "$omz_remote" in
      https://github.com/ohmyzsh/ohmyzsh.git|https://github.com/ohmyzsh/ohmyzsh|git@github.com:ohmyzsh/ohmyzsh.git) ;;
      *) printf 'Unexpected Oh My Zsh origin in %s; it will not be updated.\n' "$omz_dir" >&2; return 1 ;;
    esac
    omz_branch=$(git -C "$omz_dir" symbolic-ref --short HEAD) || return 1
    omz_status=$(git -C "$omz_dir" status --porcelain) || return 1
    if [ "$omz_branch" != master ] || [ -n "$omz_status" ]; then
      printf 'Oh My Zsh must be clean and on master before setup: %s\n' "$omz_dir" >&2
      return 1
    fi
  fi
}

setup_oh_my_zsh() {
  if [ "$omz_mode" = existing ]; then
    printf 'Preserving existing Oh My Zsh configuration and its installation; use its own updater.\n'
    return 0
  fi
  command -v zsh >/dev/null 2>&1 || {
    printf 'Missing required tool: zsh. Install it manually or ask an administrator, then rerun.\n' >&2
    return 1
  }
  if [ -d "$omz_dir" ]; then
    git -C "$omz_dir" fetch origin master
    # Refuse local commits, including commits ahead of upstream.
    if ! git -C "$omz_dir" merge-base --is-ancestor HEAD FETCH_HEAD; then
      printf 'Oh My Zsh has local commits; resolve them before updating %s.\n' "$omz_dir" >&2
      return 1
    fi
    git -C "$omz_dir" merge --ff-only FETCH_HEAD
  else
    git clone --depth=1 --branch master https://github.com/ohmyzsh/ohmyzsh.git "$omz_dir"
  fi
  if [ ! -f "$omz_dir/oh-my-zsh.sh" ]; then
    printf 'Missing Oh My Zsh entry point in %s.\n' "$omz_dir" >&2
    return 1
  fi
  if [ "$omz_mode" = new ]; then
    mkdir -p "$(dirname "$zsh_rc")"
    printf '\n# machine-setup: Oh My Zsh\n%s\n' "$omz_source" >> "$zsh_rc"
  fi
}
