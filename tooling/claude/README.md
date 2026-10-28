# Claude Code tooling used for IBP

Snapshot of the Claude Code skills and sub-agents used on IBP:

- `skills/concept-forge` and agents `concept-*`: the concept document (`docs/concept/`).
- `skills/blueprint-forge` and agents `blueprint-*`: the blueprint and specs (`docs/spec/`).
- `skills/gsd-*`, agents `gsd-*` and `get-shit-done/` (GSD 1.42.3): the phase planning and
  execution workflow behind `.planning/`. The skills and agents read their workflows, templates
  and `bin/` tools from `~/.claude/get-shit-done/`, so that folder is required.

The live copies are in `~/.claude/skill-domains/dev/`, `~/.claude/agent-domains/dev/` and
`~/.claude/get-shit-done/` (repo riky90/.claude); in the working folder they are attached to
`.claude/` through junctions, which stay out of git. This folder is a copy for reference and is
not loaded by Claude Code. To use it on another machine, copy `skills/*` into `.claude/skills/`,
`agents/*` into `.claude/agents/` and `get-shit-done/` into `~/.claude/get-shit-done/`.
