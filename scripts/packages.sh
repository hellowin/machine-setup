#!/usr/bin/env bash
# Sourced by setup.sh; callers refresh the package manager once per run.
upgrade_apt_packages() {
  local package policy installed candidate held
  held=$(apt-mark showhold)
  for package in "$@"; do
    case "$package" in -*|*=*|*/*) echo 'Use unpinned apt package names in the manifest.' >&2; return 1 ;; esac
    if printf '%s\n' "$held" | grep -Fqx "$package"; then
      printf 'Keep held apt package: %s\n' "$package"
      continue
    fi
    policy=$(LC_ALL=C apt-cache policy "$package")
    installed=$(printf '%s\n' "$policy" | awk '$1 == "Installed:" { print $2; exit }')
    candidate=$(printf '%s\n' "$policy" | awk '$1 == "Candidate:" { print $2; exit }')
    if [ -z "$candidate" ] || [ "$candidate" = '(none)' ]; then
      printf 'No apt candidate for %s.\n' "$package" >&2
      return 1
    fi
    if [ -n "$installed" ] && [ "$installed" != '(none)' ] && dpkg --compare-versions "$installed" ge "$candidate"; then
      printf 'Keep %s %s (candidate %s).\n' "$package" "$installed" "$candidate"
    else
      # No downgrade/removal overrides. A race that would downgrade aborts safely.
      sudo apt-get install -y --no-remove "$package=$candidate"
    fi
  done
}
