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
  repo=''
  ref=main
  dry_run=false
  checkout_dir=$HOME/.local/share/machine-setup
  if [ -f "$setup_config" ]; then
    # Read supported top-level YAML scalars without bootstrap dependencies.
    config_values=$(awk '
      /^(sudoEnabled|dryRun|repository|ref|setupDir):/ {
        key=$0; sub(/:.*/, "", key)
        if (++seen[key] > 1) exit 1
        value=$0; sub(/^[^:]+:[[:space:]]*/, "", value)
        sub(/[[:space:]]+#.*$/, "", value); sub(/[[:space:]]*$/, "", value)
        quote=substr(value, 1, 1)
        if (quote == "\047" || quote == "\042") {
          if (substr(value, length(value), 1) != quote) exit 1
          value=substr(value, 2, length(value)-2)
        }
        if (key == "sudoEnabled" && value != "true" && value != "false" && value != "null") exit 1
        if (key == "dryRun" && value != "true" && value != "false") exit 1
        if ((key == "ref" || key == "setupDir" || key == "repository") && value == "") exit 1
        print key ":" value
      }
    ' "$setup_config") || {
      printf 'Invalid configuration in %s; sudoEnabled must be true or false, dryRun must be true or false, and scalar keys must be unique.\n' "$setup_config" >&2
      return 1
    }
    while IFS= read -r setting; do
      case "$setting" in
        sudoEnabled:*) saved_sudo=${setting#*:} ;;
        dryRun:*) dry_run=${setting#*:} ;;
        repository:*) repo=${setting#*:} ;;
        ref:*) ref=${setting#*:} ;;
        setupDir:*) checkout_dir=${setting#*:} ;;
      esac
    done <<EOF
$config_values
EOF
  fi
  case "$repo" in ''|https://*) ;; *) echo 'YAML repository must be an HTTPS Git URL.' >&2; return 1 ;; esac
  case "$ref" in -*) echo 'YAML ref must not start with a dash.' >&2; return 1 ;; esac
  case "$checkout_dir" in /*) ;; *) echo 'YAML setupDir must be an absolute path.' >&2; return 1 ;; esac
}

choose_setup_sudo() {
  local answer
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

bootstrap_main() {
  if [ "$#" -ne 0 ]; then
    echo 'CLI arguments are not supported. Configure setup in ~/.machine-setup.yml.' >&2
    exit 2
  fi
  read_setup_config

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
    setup_dir=$checkout_dir
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
