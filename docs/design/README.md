# Design documents — ACME Facility Incident Management

Design artifacts for the backend scaffold and the `auth` vertical slice.
**No implementation code exists yet**; these are planning documents.

| File | What it is |
|---|---|
| [plan.md](plan.md) | The implementation plan. Current, revision 4. Start here. |
| [api.md](api.md) | The HTTP contract for all three services: 52 endpoints, roles, errors, and decisions to confirm. |
| [tasks.md](tasks.md) | Every task required to complete the project, with status and gates. |
| [reviews.md](reviews.md) | Findings from three review passes, with what was accepted and what was rejected and why. |
| [plan-before-review.md](plan-before-review.md) | Revision 3, kept only so the reviews' effect can be diffed. Superseded. |
| [diagrams/](diagrams/) | Mermaid sources, one diagram per file: `architecture.mmd` (runtime topology, Lambda internals, build path), `design.mmd` (the 12-table data model), `workflow.mmd` (incident status machine), `security.mmd` (trust boundaries, auth chain, credentials, admin path). |

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

Design complete. Five items remain empirically unverified rather than undesigned — listed at the end
of [reviews.md](reviews.md) — and are scheduled into commit 1 and the deploy gate.
