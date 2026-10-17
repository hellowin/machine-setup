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
  autosuggestions_dir=$omz_dir/custom/plugins/zsh-autosuggestions
  preflight_zsh_checkout "$omz_dir" ohmyzsh/ohmyzsh || return 1
  preflight_zsh_checkout "$autosuggestions_dir" zsh-users/zsh-autosuggestions
}

# Both managed repositories must be safe before setup changes either one.
preflight_zsh_checkout() {
  local target=$1 repository=$2 remote branch status
  if [ -L "$target" ] || { [ -e "$target" ] && [ ! -d "$target/.git" ]; }; then
    printf 'Move conflicting %s aside; setup requires a Git checkout.\n' "$target" >&2
    return 1
  fi
  if [ -d "$target" ]; then
    remote=$(git -C "$target" remote get-url origin) || return 1
    case "$remote" in
      "https://github.com/$repository.git"|"https://github.com/$repository"|"git@github.com:$repository.git") ;;
      *) printf 'Unexpected origin in %s; it will not be updated.\n' "$target" >&2; return 1 ;;
    esac
    branch=$(git -C "$target" symbolic-ref --short HEAD) || return 1
    status=$(git -C "$target" status --porcelain) || return 1
    if [ "$branch" != master ] || [ -n "$status" ]; then
      printf 'Checkout must be clean and on master before setup: %s\n' "$target" >&2
      return 1
    fi
  fi
}

update_zsh_checkout() {
  local target=$1 repository=$2 entrypoint=$3
  if [ -d "$target" ]; then
    git -C "$target" fetch origin master || return 1
    # Refuse local commits, including commits ahead of upstream.
    if ! git -C "$target" merge-base --is-ancestor HEAD FETCH_HEAD; then
      printf 'Checkout has local commits; resolve them before updating %s.\n' "$target" >&2
      return 1
    fi
    git -C "$target" merge --ff-only FETCH_HEAD || return 1
  else
    mkdir -p "$(dirname "$target")" || return 1
    git clone --depth=1 --branch master "https://github.com/$repository.git" "$target" || return 1
  fi
  if [ ! -f "$target/$entrypoint" ]; then
    printf 'Missing Zsh entry point: %s/%s\n' "$target" "$entrypoint" >&2
    return 1
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
  update_zsh_checkout "$omz_dir" ohmyzsh/ohmyzsh oh-my-zsh.sh || return 1
  update_zsh_checkout "$autosuggestions_dir" zsh-users/zsh-autosuggestions zsh-autosuggestions.zsh || return 1
  if [ "$omz_mode" = new ]; then
    mkdir -p "$(dirname "$zsh_rc")"
    printf '\n# machine-setup: Oh My Zsh\n%s\n' "$omz_source" >> "$zsh_rc"
  fi
}
