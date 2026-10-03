Before taking action in this repository, read `AGENTS.md` and
`.agents/skills/maintain-machine-setup/SKILL.md`. They contain the shared
maintenance contract for Codex, Claude, Copilot, and other agents.

Keep bootstrap reruns repeatable, preserve newer OS packages, and let mise
manage its own versions. Validate changes with `bash tests/check.sh` and
`git diff --check`; do not apply real machine setup to test repository changes.
