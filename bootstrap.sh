#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: bash bootstrap.sh [--dry-run] [--repo HTTPS_URL] [--ref REF]
Local:  bash bootstrap.sh --dry-run
Remote: bash -c "$(curl -fsSL https://raw.githubusercontent.com/hellowin/machine-setup/main/bootstrap.sh)"
Environment: MACHINE_SETUP_DIR overrides the remote checkout destination.
HELP
}
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
      sudo apt-get update
      sudo apt-get install -y --no-remove git
    fi
  else
    if ! xcode-select -p >/dev/null 2>&1; then
      echo 'macOS requires existing Command Line Tools. Ask IT to provision them, then rerun; setup never installs them or uses sudo.' >&2
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
if "$dry_run"; then
  bash "$setup_dir/scripts/setup.sh" "$platform" --dry-run
else
  bash "$setup_dir/scripts/setup.sh" "$platform"
fi
