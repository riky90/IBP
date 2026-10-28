---
name: concept-forge
description: Turns messy source material — exports, spec documents, data dumps, existing code, vault notes — into a single evidence-backed concept document (case list, as-is with located defects, requirements traced to those defects, to-be, plan) reviewed by an independent critic, plus a visual package — archify diagrams, a UX spec with Excalidraw mockups for every screen the to-be implies, and an HTML preview the user checks before anything is built — then routes the approved concept to the system that will build it — GSD for multi-milestone work, software-house for a single session — and launches it once the user approves. Orchestrates the concept-investigator, concept-architect, concept-critic and concept-diagrammer sub-agents, reusing blueprint-ux-designer and blueprint-wireframer for the screens. Handles sources that need live tools (Power BI .pbix models, databases) by extracting them first. Use when the user says "facciamo il concept di X", "capiamo come funziona davvero X e come dovrebbe funzionare", "analizza queste fonti e tirane fuori i requisiti", asks for an as-is/to-be, a data-model or process redesign, or hands over several documents and asks what they actually say — and as the entry point when they do not yet know what to build. It writes no code itself — it hands that to software-house or GSD. Not for ingesting knowledge into a vault, which is llm-wiki.
---

# Concept Forge

One run takes a pile of real sources and produces `concept.md`: the cases the material
actually shows, the as-is with its defects located and measured, requirements each traced to
the defect it closes, a to-be that resolves every case, a plan, and the questions that still
need a human. A critic blocks the run until the concept holds. Then a visual package — archify
diagrams, Excalidraw mockups of the screens, and one HTML preview that shows them all — lets the
user see whether the to-be is what they want before anything is built.

The value is evidence, not eloquence. A concept whose claims trace to counted facts survives
the first contact with the real export; one built on impressions does not.

## Agents in this system

| Agent | Owns (writes) | Runs |
|---|---|---|
| `concept-investigator` | `.concept-forge/<run-id>/digests/<slice>.md` | stage 1, one per source slice, parallel |
| `concept-architect` | `.concept-forge/<run-id>/concept.md` | stage 2, and again on revision |
| `concept-critic` | nothing (read-only) | stage 3 |
| `concept-diagrammer` | `docs/diagrams/<name>.json`, `docs/diagrams/<name>.html` | stage 5, one per planned diagram, parallel |
| `blueprint-ux-designer` (reused) | `docs/spec/SPEC-<slug>-ux.md` | stage 5, only if the to-be has user-facing screens |
| `blueprint-wireframer` (reused) | `docs/concept/wireframes/<screen-id>.excalidraw` for its batch | stage 5, after the UX spec, one per batch of 3-5 screens, parallel |

You (the orchestrator) own `state.md`, the extracts of live-tool sources, and the preview.

Write sets are disjoint by design. Each investigator owns one digest file; each diagrammer
owns one diagram's two files. Never give two parallel agents the same path.

## Run state

Everything for a run lives under `.concept-forge/<run-id>/` (`run-id` =
`YYYYMMDD-HHMM-<slug>`). Keep `state.md` there updated after every stage: what ran, what it
produced, what is outstanding, what the user decided at each gate. That is what makes a run
resumable across sessions and lets you summarize without re-reading every artifact.

`.concept-forge/` is working state, not a deliverable — add it to `.gitignore` unless the
user wants the trail committed. Delivered diagrams, the UX spec and the mockups go under `docs/`,
not inside the run directory.

## Stage 0 — Frame the question and slice the sources

Do this yourself, in the main thread. Establish with the user, in one short round:

- the question the concept must answer (one sentence);
- which sources are in scope — list the actual paths;
- where the concept document should end up. It must be a **durable path inside the repository**
  — `docs/` is the usual home. Not `.concept-forge/`, which is gitignored working state that
  stage 6 cannot hand to `gsd-ingest-docs`.

**Sources that need a live tool.** Investigators have only file tools: they cannot open a
Power BI `.pbix`, query a database or call an API. For every such source, you extract first, in
the main thread, before stage 1:

- **Power BI (`.pbix`)** — ask the user to open the file in Power BI Desktop, connect with the
  `powerbi-modeling-mcp` tools (`connection_operations` → `ListLocalInstances` → `Connect`), and
  write to `.concept-forge/<run-id>/extracts/<model>/`: the table list with row counts, the
  columns, the relationships, the DAX of every measure (`measure_operations` `ExportTMDL`), and
  the result sets the question needs (`dax_query_operations`), as CSV. The report pages inside
  the archive (`Report/definition/**/visual.json`) are readable without Desktop and show which
  measures the business actually looks at — read them first, they say what to extract.
- **Databases, APIs** — the same pattern: query once, save to `extracts/`, never let an
  investigator depend on a live connection.

Extracts of real business data stay under `.concept-forge/` (gitignored) and the source files
themselves go into `.gitignore` too. Never commit them. Each extract becomes an ordinary source
of a slice.

When the question is quantitative — "is the tool better than the human", "where is the bias" —
the extracts must carry the measure **as the business defines it** (its DAX), not a textbook
version. A requirement like "lower WMAPE than the planners" is only checkable against their
WMAPE.

Then cut the sources into disjoint slices, one per investigator. Slice by source coherence,
not by byte count: one export family, one spec document set, one code area. Three to six
slices is the usual range; one slice needs no fan-out, and beyond six the digests start
repeating each other.

Write `state.md` with the question, the slices, and the paths before spawning anything.

## Stage 1 — Investigation (fan-out, parallel)

Spawn one `concept-investigator` per slice, **all in the same turn**. Their write sets are
disjoint by construction.

```
Objective: produce an evidence digest for the source slice "<slice name>".

Context (you cannot see the conversation that produced this):
- The concept question this run must answer: <one sentence>
- <domain constraints and vocabulary the user established>
- Your slice is one of <N>; other agents cover the rest. Do not read outside your slice.

Read: <exact paths in this slice, with what matters in each>
Write: .concept-forge/<run-id>/digests/<slice>.md
Do not modify: anything else — project source, other digests, the concept document.

Done when: every source in the slice is read, facts are measured with counts, decisive lines
are quoted with location, contradictions are recorded, and unknowns are listed as questions.

Report back in under 10 lines: sources read, the findings that most change the picture, any
contradiction, and the digest path.
```

If a slice fails, apply the failure policy — do not let the architect synthesize over a hole
while presenting the result as complete.

## Stage 2 — Synthesis

Spawn one `concept-architect`:

```
Objective: write the concept document for "<subject>".

Context (you cannot see the conversation that produced this):
- The question this concept must answer: <one sentence>
- Decisions the user already made and that are not open: <list, or "none">
- Constraints: <stack, scope, what is out of scope>

Read: every digest under .concept-forge/<run-id>/digests/, plus .concept-forge/<run-id>/state.md
      <and any project document that matters: schema, README, plan>
Write: .concept-forge/<run-id>/concept.md
Do not modify: the digests, project source, documentation.

Done when: the case list is complete and counted, every as-is defect is observable, every
requirement traces to a defect and its evidence, every case is walked against the to-be, and
unknowns are open questions rather than invented facts.

Report back in under 12 lines: case count, requirement count, the decisions that shape the
to-be, open-question count, document path.
```

## Stage 3 — Critic loop (cap 3 rounds)

Spawn `concept-critic` on the concept document and the digests it rests on.

```
Objective: judge whether the concept at .concept-forge/<run-id>/concept.md is sound enough
to build on.

Read: .concept-forge/<run-id>/concept.md, every digest under .concept-forge/<run-id>/digests/
Write: nothing. You are read-only by design.

Done when: you have a PASS/FAIL verdict with each blocking finding stated as a concrete
failure — which case, which claim, what breaks.
```

On FAIL, re-spawn `concept-architect` with the findings **verbatim** in its prompt, plus the
instruction to address each one explicitly — fixed, or refuted with evidence. Then re-run the
critic.

**Cap: 3 critic rounds.** Past that the loop is not converging. Stop, show the user the
outstanding findings and the current concept, and let them decide. A fourth round costs more
than the user's judgment.

## How every gate is presented

A gate is not passed by a file existing on disk. At each gate, **in the chat**: a summary in the
user's language, written out in full so the user can decide from the chat alone; a **clickable
link** to every document the gate covers (markdown link, path relative to the working
directory); then the question with `AskUserQuestion`. Never ask for approval of a document the
user has only been told "is written".

## GATE — requirements approval

Present to the user, in their language and in about ten lines: the question, the case count,
the requirements in one line each, the two or three decisions that shape the to-be, the
critic's verdict, and the open questions. Then ask whether to proceed.

This is the cheapest point to correct a misunderstanding. Everything after it is built on the
concept.

## Stage 4 — Plan the visual package

The visual package is **part of every run**, not an option: the user approves the to-be by
seeing it, not by reading 800 lines. What is planned is *which* diagrams and screens.

From the approved concept, draft the plan and write it into `state.md`:

- **Diagrams (archify), the default set** — drop one only if the concept has nothing to put in
  it, and say so:
  1. `as-is` — the current system or process with its located defects marked;
  2. `to-be` — the target, with each defect's resolution visible;
  3. `processo` — the main end-to-end flow (workflow or sequence);
  4. `dati` — the data model or data path (data-flow), when the concept changes data.
  Add more where the concept carries a topology, lifecycle or flow the text renders badly.
- **Screens** — if the to-be has any user-facing surface (a workbench, a form, a report page),
  the UX spec and its Excalidraw mockups are in the plan. If it has none (a pure engine or batch
  change), say so in one line; the preview then shows diagrams only.

Present the plan in about six lines — each diagram with its archify type and what it shows, the
screen list or "nessuno schermo" — and let the user add or drop items with `AskUserQuestion`.
If a previous run left diagrams under `docs/diagrams/`, they are **rebuilt** from the new
concept, not patched: a diagram that outlived its concept states facts nobody re-checked.

## Stage 5 — Build the visual package (parallel)

In **one turn**, spawn one `concept-diagrammer` per planned diagram and, if screens are in the
plan, one `blueprint-ux-designer`. Write sets are disjoint.

Diagrammer brief:

```
Objective: build, validate, deliver and visually check the "<name>" diagram.

Context (you cannot see the conversation that produced this):
- Archify type: <architecture | workflow | sequence | data-flow | state>
- What this diagram must show: <one or two sentences, from the concept>
- It must state only what the concept establishes — introduce no fact of your own.

Read: <delivered concept path> (the sections named above),
      C:\Users\RINALDIR\.claude\skills\archify\SKILL.md
Write: docs/diagrams/<name>.json and docs/diagrams/<name>.html
Do not modify: the concept document or any other diagram's files.

Done when: validate reports 9/9 artifact checks with 0 errors and 0 warnings, deliver exits
zero, and visual-check passes at 1440x900, 1600x1000, 1920x1080 <and 2048x1320 if large-display>.

Report back in under 10 lines: verdict, receipt numbers, visual-check per viewport, repair
rounds, paths. No validator transcripts.
```

UX designer brief:

```
Objective: write the UX specification for the to-be of "<subject>".

Context (you cannot see the conversation that produced this):
- This is a concept-forge run. Your scope is the approved concept document, not a PRD: every
  requirement (by ID) a user sees or acts on gets at least one flow and one screen; requirements
  with no user-facing surface are listed once under "Not user-facing".
- Roles: <the roles the concept names>
- Decisions at the requirements gate: <list>
- Rules: zero source code; flows and sitemap in Mermaid; document in English; screens show and
  collect, the server decides.

Read: <delivered concept path>, .concept-forge/<run-id>/state.md
Write: docs/spec/SPEC-<slug>-ux.md
Do not modify: the concept or anything else.

Done when: each role has its flows as Mermaid flowcharts including error and empty paths; the
sitemap is Mermaid; each key screen has a structured textual wireframe with a stable screen ID;
a screen inventory maps screen ID → requirement IDs → roles.

Report back in under 12 lines: flow count, screen count, the screen IDs, open questions, path.
```

When the UX spec is back, split its screen inventory into batches of 3-5 and spawn one
`blueprint-wireframer` per batch **in the same turn**, writing
`docs/concept/wireframes/<screen-id>.excalidraw` (same brief as blueprint-forge stage B: invent
no element the text does not describe; done when each file parses as JSON with type
`"excalidraw"`, version 2 and a non-empty elements array).

## Stage 5b — HTML preview and visual gate

Load the `artifact-design` skill first, then publish one private Artifact that renders, from the
deliverables only:

- a short concept summary — the question, cases, requirements one line each with their traced
  defect;
- every archify diagram — publish each `docs/diagrams/<name>.html` as a supporting file through
  the Artifact `files` parameter and embed it in an `<iframe>`, with a link to open it full-size;
- every Excalidraw mockup — rendered with `@excalidraw/utils` `exportToSvg` from cdn.jsdelivr.net,
  or a faithful SVG rendering of the elements if the library cannot load — next to its textual
  wireframe;
- the Mermaid flows and sitemap of the UX spec (Mermaid from cdnjs or jsdelivr);
- a traceability table: requirement → defect → diagram → screen.

Navigation follows that order. The page is tooling for looking at the design; it is never added
to `docs/`.

Then the **visual gate**: following the gate format, give the preview link, the diagram list,
the screen list, and links to the UX spec and each `.excalidraw` file. Ask whether this is what
the user wants. Corrections route to the owner — the architect if the concept is wrong (then the
critic again, and the affected diagrams and screens rebuilt), the UX designer for screens (then
only the affected wireframers), the diagrammer for one diagram — and the preview is republished
to the same URL. Proceed to stage 6 only on approval.

## Stage 6 — Delivery routing (decide, say why, ask, then launch)

A concept nobody builds is a document. This stage picks **who builds it**, explains the choice
in the user's language, asks, and then actually launches it. The user should not need to know
that `gsd-ingest-docs` exists, and should never be handed a command to run themselves.

### The rule — route once, on horizon, not on topic

Read the approved concept's **Plan** and **Requirements** sections and count. Route to **GSD**
if any one of these holds:

- the plan spans more than one milestone, stage or release;
- it implies **more than eight implementation tasks** — `software-house` itself calls three to
  eight a healthy run and fifteen too big, and past eight its `plan.md` goes stale faster than
  anyone rewrites it;
- the work will not finish in one sitting, or the user expects to come back to it days later;
- per-task commits and the ability to roll one back matter;
- it needs a gate GSD owns and `software-house` has none of: security review, UI design
  contract, AI evaluation.

Route to **software-house** only when **all** of these hold:

- one coherent change, three to eight tasks, plausibly one session;
- the user wants the diff in hand and commits it themselves;
- no project state needs to survive the session.

Route to **neither** — close on the concept — when the deliverable is a decision or a document
for people rather than code, or when an open question still blocks the requirements. Say so
plainly; it is a complete outcome, not a failure.

**Route once, for the whole concept.** Never hand single phases of a GSD project to
`software-house`. The two keep plan and state in different places and different shapes:
`sh-architect` rewrites the plan from scratch and nothing updates GSD's `STATE.md`, so the
recorded state and the real state diverge silently — the one failure a non-technical user
cannot be expected to catch.

### Present and ask

Show, in about six lines and in the user's language: what the work is, **the measure that
decided it** (task count, milestone count, horizon), the system you would use and why in plain
terms, and what will happen next. Then `AskUserQuestion` with three real options — the
recommended system, the other one, and "fermati qui, tengo solo il concept".

Never launch without the answer. A GSD handoff generates an entire roadmap from the concept's
framing; if the framing is wrong the user finds out only after a project's worth of structure
exists.

### Handoff to GSD

1. The delivered concept must sit at the **durable path agreed in stage 0** — inside the
   repository, not in `.concept-forge/`, which is gitignored working state. `gsd-ingest-docs`
   canonicalizes every input path and rejects anything it cannot contain under the repo root.

2. Write `<repo>/.planning-ingest.yml`:

   ```yaml
   docs:
     - path: <delivered concept path, relative to repo root>
       type: SPEC
     - path: docs/spec/SPEC-<slug>-ux.md   # only if stage 5 produced it
       type: SPEC
   ```

   The UX spec is what GSD's UI phases (`/gsd:ui-phase`) start from — leaving it out of the
   manifest makes the UI contract be rederived from scratch.

   `SPEC` is the correct type — a document carrying requirements and a to-be outranks a PRD and
   a DOC in GSD's precedence chain (`ADR > SPEC > PRD > DOC`). **The manifest is not optional:**
   without it the concept is never discovered, because `gsd-ingest-docs` scans `docs/adr/`,
   `docs/prd/`, `docs/spec/` and `docs/**/*.md` by convention and a concept elsewhere matches
   none of them.

3. **Before launching, tell the user what it will do to their directory**, because two effects
   are not obvious and one is not reversible by them:
   - if the directory is not yet a git repository, `gsd-ingest-docs` runs `git init`;
   - if `.planning/` already exists it **merges** instead of bootstrapping, and hard-blocks on
     any contradiction with a decision already locked there.

4. Invoke the `gsd-ingest-docs` skill with `--manifest .planning-ingest.yml`. What comes back is
   `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md` and `STATE.md` — the milestones and phases.
   That is where this run ends: name `gsd-plan-phase` as the next step and stop. Do not plan or
   execute a phase inside a concept-forge run.

### Handoff to software-house

Invoke the `software-house` skill with the request stated as: build what the concept at
`<delivered path>` specifies, plus — verbatim — the constraints the user fixed at the
requirements gate. Point it at the concept path explicitly, so `sh-architect` derives the
backlog from the traced requirements instead of re-inventing it from a one-line summary.

### Record it

Write the routing decision, the measure behind it, and the launched command into `state.md`
before launching. A run that is interrupted mid-handoff must be resumable without re-deciding.

## Gates and irreversible actions

- **Requirements gate** (after the critic passes or the cap is hit) — nothing proceeds
  without approval.
- **Visual gate** (stage 5b) — the user sees the preview and approves it before routing. The
  visual package is always built; what the user chooses is its contents.
- **Delivery routing** (stage 6) — the recommendation is yours to make, the launch is not.
  Always offer "fermati qui" as a real option, and state the `git init` and `.planning/` merge
  effects *before* asking, not after. Handing off starts a run that costs far more than this
  one; approval to route does not extend to committing, pushing or deploying anything the
  downstream system produces.
- Never commit, push, publish, or write into a knowledge vault without explicit approval in
  this session. Approval for one such action does not carry to the next.
- Writing the concept into the vault as knowledge is a separate job — hand it to `llm-wiki`,
  and only if the user asks.

## Failure policy

- An agent reports failure → re-spawn once with the failure evidence added to its prompt. An
  identical retry produces an identical failure.
- Second failure → stop that branch and tell the user what was tried. Never route silently
  around a missing slice: a concept assembled without one will be trusted as if it were whole.
- An agent asks for context it was never given → the spawn prompt template here is wrong. Fix
  it in this file, not only in that one invocation.
- Partial fan-out → finish every branch that can finish, then state exactly which slices are
  missing and what the concept therefore does not cover.
- A rate-limited or interrupted subagent is a failure, not a pass. Re-spawn it.

## Closing a run

Report in the user's language: the concept path, case and requirement counts, the critic's
verdict, the diagrams and screens delivered with the preview link, **where the work was routed and on
what measure** (or that the user chose to stop at the concept), the open questions to take to
whoever can answer them, and the one next step that belongs to the downstream system — not to
this run. Keep it short — the artifacts carry the
detail.
