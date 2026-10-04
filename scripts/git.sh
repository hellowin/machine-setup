#!/usr/bin/env bash

setup_git_preferences() {
  command -v vim >/dev/null 2>&1 || {
    echo 'Missing required editor: vim. Install vim manually or ask an administrator, then rerun.' >&2
    return 1
  }
  local git_preferences existing_includes status
  git_preferences=$setup_dir/config/git.gitconfig
  existing_includes=$(git config --global --get-all include.path) && status=0 || status=$?
  case "$status" in 0|1) ;; *) echo 'Cannot read global Git includes.' >&2; return "$status" ;; esac
  if ! printf '%s\n' "$existing_includes" | grep -Fxq "$git_preferences"; then
    git config --global --add include.path "$git_preferences" || return 1
  fi
}
