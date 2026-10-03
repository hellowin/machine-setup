#!/usr/bin/env bash
set -euo pipefail
mise_bin=${1:-mise}
for tool in git curl; do
  command -v "$tool" >/dev/null || { printf 'Missing required tool: %s\n' "$tool" >&2; exit 1; }
done
"$mise_bin" --version
"$mise_bin" ls
printf 'Base tools verified.\n'
