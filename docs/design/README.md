# Design documents — ACME Facility Incident Management

Design artifacts for ACME Facility Incident Management. Written before the code, kept current
alongside it: the implementation follows these documents, and where a deploy taught something
different (T123's header finding, A2's reversal) the document says so in place. For the delivered
system, its measured numbers and the demo script, start at the root [`NOTES.md`](../../NOTES.md).

| File | What it is |
|---|---|
| [plan.md](plan.md) | The implementation plan. Current, revision 4. Start here. |
| [api.md](api.md) | The HTTP contract for all three services: 57 endpoints, roles, errors, and the decisions taken. |
| [tasks.md](tasks.md) | Every task required to complete the project, with status and gates. |
| [reviews.md](reviews.md) | Findings from three review passes, with what was accepted and what was rejected and why. |
| [plan-before-review.md](plan-before-review.md) | Revision 3, kept only so the reviews' effect can be diffed. Superseded. |
| [diagrams/](diagrams/) | Mermaid sources, one diagram per file: `architecture.mmd` (runtime topology, Lambda internals, build path), `design.mmd` (the 12-table data model), `workflow.mmd` (incident status machine), `security.mmd` (trust boundaries, auth chain, credentials, admin path). |
| [diagrams/*.html](diagrams/) | The same diagrams redrawn as self-contained HTML/SVG with the diagram-design skill: `architecture-overview.html` and `architecture-lambda.html` (from `architecture.mmd`), `design.html`, `workflow.html`, `security-boundaries.html` and `security-auth-chain.html` (from `security.mmd`). Open in a browser; the `.mmd` files remain the editable source. |

## Reading order for `plan.md`

| Section | Why |
|---|---|
| What the repo dictates | 13 constraints, each cited to a file and line. If a row is wrong, everything downstream is wrong — check this first. |
| Target design | File tree, data model, workflow state machine, row-level scoping, error envelope, dependencies. |
| Security corrections | S1 and S2 are blocking. |
| Revised commit sequence | 17 commits, 4 gates. |
| Decisions closed | The eight choices already made. |

To see what the reviews changed:

```sh
diff -u docs/design/plan-before-review.md docs/design/plan.md
```

## Status

Implemented and deployed (2026-09-23). Every endpoint in `api.md` exists and answers through
CloudFront; the task list records what each deploy verified and the few items left open.
