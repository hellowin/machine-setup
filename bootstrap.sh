#!/usr/bin/env bash
set -euo pipefail

# Kept in the downloaded entrypoint so privilege selection needs no dependencies.
# bootstrap_main loads setup.sh after reading YAML and selecting privileges.
read_setup_config() {
  setup_config=$HOME/.machine-setup.yml
  saved_sudo=''
  if [ -L "$setup_config" ] || { [ -e "$setup_config" ] && [ ! -f "$setup_config" ]; }; then
    printf 'Expected a regular file at %s.\n' "$setup_config" >&2
    return 1
  fi
  if [ -f "$setup_config" ]; then
    saved_sudo=$(awk '
      /^[[:space:]]*(#.*)?$/ { next }
      /^sudoEnabled:/ {
        count++; value=$0
        sub(/^sudoEnabled:[[:space:]]*/, "", value)
        sub(/[[:space:]]+#.*$/, "", value)
        sub(/[[:space:]]*$/, "", value)
        if (value != "true" && value != "false" && value != "null") bad=1
      }
      END {
        if (count > 1 || bad) exit 1
        if (count == 1 && value != "null") print value
      }
    ' "$setup_config") || {
      printf 'Invalid sudo configuration in %s; use sudoEnabled: true or false.\n' "$setup_config" >&2
      return 1
    }
  fi
}

choose_setup_sudo() {
  local answer
  read_setup_config
  sudo_enabled=$saved_sudo
  if [ -f "$setup_config" ]; then
    case "$sudo_enabled" in true|false) ;; *)
      printf 'Set sudoEnabled to true or false in %s before running setup.\n' "$setup_config" >&2
      return 1 ;;
    esac
  else
    while :; do
      printf 'Do you have access to sudo? [y/n]: ' >&2
      if ! IFS= read -r answer; then
        echo 'No answer received. Rerun interactively or create ~/.machine-setup.yml with sudoEnabled: true or false.' >&2
        return 1
      fi
      case "$answer" in
        y|Y|yes|YES) sudo_enabled=true; break ;;
        n|N|no|NO) sudo_enabled=false; break ;;
        *) echo 'Please answer yes or no.' >&2 ;;
      esac
    done
  fi
  case "$sudo_enabled" in true|false) ;; *) echo 'Invalid sudo choice.' >&2; return 1 ;; esac
  printf 'Sudo enabled: %s\n' "$sudo_enabled"
}

save_setup_config() {
  local source_config temporary
  [ ! -f "$setup_config" ] || return 0
  source_config=$setup_dir/.machine-setup.yml
  temporary=$(mktemp "$HOME/.machine-setup.yml.XXXXXX")
  if ! awk -v enabled="$sudo_enabled" '
    /^sudoEnabled:/ {
      found=1
      sub(/sudoEnabled:[[:space:]]*[^[:space:]#]+/, "sudoEnabled: " enabled); print; next
    }
    { print }
    END { if (!found) print "\nsudoEnabled: " enabled }
  ' "$source_config" > "$temporary"; then
    rm -f "$temporary"
    return 1
  fi
  mv "$temporary" "$setup_config"
}

usage() {
  cat <<'HELP'
Usage: bash bootstrap.sh [--dry-run] [--repo HTTPS_URL] [--ref REF]
Local:  bash bootstrap.sh --dry-run
Remote: bash -c "$(curl -fsSL https://raw.githubusercontent.com/hellowin/machine-setup/main/bootstrap.sh)"
Environment: MACHINE_SETUP_DIR overrides the remote checkout destination.
HELP
}

bootstrap_main() {
  repo=''
  ref=main
  dry_run=false
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run) dry_run=true; shift ;;
      --repo|--ref)
        [ "$#" -ge 2 ] || { usage >&2; exit 2; }
        if [ "$1" = --repo ]; then repo=$2; else ref=$2; fi
        shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
  done

  # A downloaded or piped entrypoint uses the public repository automatically.
  # A script inside a checkout applies that checkout's current files.
  source_file=${BASH_SOURCE[0]:-}
  local_dir=''
  if [ -z "$repo" ]; then
    if [ -n "$source_file" ] && [ -f "$source_file" ]; then
      candidate_dir=$(cd "$(dirname "$source_file")" && pwd)
      if [ -f "$candidate_dir/scripts/setup.sh" ]; then
        local_dir=$candidate_dir
      fi
    fi
    if [ -z "$local_dir" ]; then
      repo=https://github.com/hellowin/machine-setup.git
    fi
  fi

  case "$(uname -s)" in
    Linux)
      [ -f /etc/os-release ] || { echo 'Cannot identify Linux distribution.' >&2; exit 1; }
      . /etc/os-release
      [ "$ID" = ubuntu ] || { echo 'This starter supports Ubuntu and macOS.' >&2; exit 1; }
      platform=ubuntu ;;
    Darwin) platform=macos ;;
    *) echo 'This starter supports Ubuntu and macOS.' >&2; exit 1 ;;
  esac

  if ! "$dry_run"; then choose_setup_sudo; fi

  if [ -n "$repo" ]; then
    case "$repo" in https://*) ;; *) echo '--repo must be an HTTPS Git URL.' >&2; exit 2 ;; esac
    setup_dir=${MACHINE_SETUP_DIR:-"$HOME/.local/share/machine-setup"}
    if "$dry_run"; then
      printf 'Would check %s prerequisites, clone/update %s at %s into %s, then apply setup.\n' "$platform" "$repo" "$ref" "$setup_dir"
      exit 0
    fi
    # The remote entrypoint has no other repository files available yet.
    if [ "$platform" = ubuntu ]; then
      # Only acquire Git if missing; package upgrades happen after fetching setup.
      # Do not reinstall or downgrade an existing prerequisite to obtain the repo.
      if ! command -v git >/dev/null 2>&1; then
        if [ "$sudo_enabled" = false ]; then
          echo 'Git is required to fetch setup. Install it yourself or ask an administrator: sudo apt-get update && sudo apt-get install -y --no-remove git' >&2
          exit 1
        fi
        sudo apt-get update
        sudo apt-get install -y --no-remove git
      fi
    else
      if ! xcode-select -p >/dev/null 2>&1; then
        echo 'macOS requires existing Command Line Tools. Install them manually (xcode-select --install) or ask IT to provision them, then rerun.' >&2
        exit 1
      fi
    fi
    if [ -e "$setup_dir" ]; then
      [ -d "$setup_dir/.git" ] || { echo 'Checkout destination exists and is not a Git repository.' >&2; exit 1; }
      [ "$(git -C "$setup_dir" remote get-url origin)" = "$repo" ] || { echo 'Existing checkout has a different origin.' >&2; exit 1; }
      [ -z "$(git -C "$setup_dir" status --porcelain)" ] || { echo 'Commit or stash checkout changes before updating.' >&2; exit 1; }
      git -C "$setup_dir" fetch origin "$ref"
      # Fast-forward only; never discard local commits or switch branches silently.
      git -C "$setup_dir" merge --ff-only FETCH_HEAD
    else
      mkdir -p "$(dirname "$setup_dir")"
      git clone --branch "$ref" --single-branch "$repo" "$setup_dir"
    fi
  else
    setup_dir=$local_dir
  fi

  [ -f "$setup_dir/scripts/setup.sh" ] || { echo 'Missing scripts/setup.sh in checkout.' >&2; exit 1; }
  . "$setup_dir/scripts/setup.sh"
  setup_main
}

if [ "${BASH_SOURCE[0]:-}" = "$0" ] || [ -z "${BASH_SOURCE[0]:-}" ]; then
  bootstrap_main "$@"
fi
