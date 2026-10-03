# Repository instructions

Before taking action in this repository, read
[the shared maintenance skill](.agents/skills/maintain-machine-setup/SKILL.md).
It is the common contract for all agents working here.

Keep setup repeatable, preserve newer OS packages, and let mise manage its own
versions. Validate with `bash tests/check.sh` and `git diff --check`.
Do not apply machine setup merely to validate repository changes.
