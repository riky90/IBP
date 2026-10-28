# Claude Code tooling used for IBP

Snapshot of the two Claude Code skills that produced the IBP concept and blueprint documents,
with their sub-agents:

- `skills/concept-forge` and agents `concept-*`: the concept document (`docs/concept/`).
- `skills/blueprint-forge` and agents `blueprint-*`: the blueprint and specs (`docs/spec/`).

The live copies are in `~/.claude/skill-domains/dev/` and `~/.claude/agent-domains/dev/`
(repo riky90/.claude); in the working folder they are attached to `.claude/` through junctions,
which stay out of git. This folder is a copy for reference and is not loaded by Claude Code.
To use it on another machine, copy `skills/*` into `.claude/skills/` and `agents/*` into
`.claude/agents/`.
