# API design — ACME Facility Incident Management

The complete HTTP contract for all three services: every endpoint, who may call it, what it takes,
what it returns, and how it fails. [`plan.md`](plan.md) explains *why* the platform is shaped the way
it is; this file is what the backend implements and the frontend codes against.

**Status:** accepted 2026-09-22. The decisions in §7 are closed with the recommended option.

---

## 1. Conventions

### 1.1 Services and paths

CloudFront routes `/api/<service>*` to the Lambda of the same name (`infra/cloudfront.tf:58`), and
the Vite proxy forwards `/api` unrewritten, so **the first path segment after `/api` is the service**
and is identical locally and in the cloud.

| Service | Prefix | Owns |
|---|---|---|
| `auth` | `/api/auth` | Identity, sessions, user administration |
| `facilities` | `/api/facilities` | Buildings, floors, seats, categories, engineer profiles |
| `incidents` | `/api/incidents` | Incidents, workflow, notes, history, escalations, reports |

All three share one schema and the `acme_core` kernel: a modular monolith whose deployment split is
imposed by the platform (plan A14). A service may read another's tables directly; it never calls
another service over HTTP.

Every service also exposes, from `create_app()`:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/<svc>/healthz` | none | Liveness. Builds no DB engine. |
| GET | `/api/<svc>/readyz` | none | DB reachable and migrations applied; memoised 30 s. `503` otherwise. |
| GET | `/api/<svc>/docs` | none | Swagger UI. |
| GET | `/api/<svc>/openapi.json` | none | OpenAPI schema. |

These four are omitted from the per-service tables below.

### 1.2 Authentication

- Every endpoint except `register`, `login`, `refresh`, `logout` and the four above requires a
  bearer access token, in `X-Acme-Authorization: Bearer <access_token>` or in the standard
  `Authorization` header. The browser client sends the former: on AWS, CloudFront's origin access
  control signs every request to the Lambda function URLs and **overwrites the viewer's
  `Authorization` header** with its own SigV4 signature, so a token sent there never reaches the
  API (found on the first deploy, T123). The standard header still works locally, from curl and
  from the Swagger page. When both are present the ACME header wins, since behind CloudFront the
  other one is the edge's signature.
- Access tokens live **30 min**, refresh tokens **7 days** (`config.py:37-38`).
- On every authenticated request `current_user` loads the user row and takes `role` and `is_active`
  **from the database, not the token** (S7). A token issued before `users.sessions_valid_from` is
  rejected, so logout-all, a role change or deactivation takes effect on the very next request.
- Every `401` carries `WWW-Authenticate: Bearer`.

### 1.3 Roles

| Short | Role value | Summary |
|---|---|---|
| **EMP** | `Employee` | Reports incidents; sees only their own. Default for self-registration. |
| **ENG** | `Engineer` | Works incidents; sees only those assigned to them by an admin. |
| **ADM** | `Facility Admin` | Sees and manages everything, including users and facilities. |
| **ANY** | — | Any authenticated user. |

Role gates run **before** any row lookup, so a `403` from a role gate never reveals whether a
resource exists. Row visibility is separate (§1.5).

### 1.4 Requests and responses

- JSON in, JSON out, `Content-Type: application/json`. Every response carries `X-Request-Id`.
- IDs are UUIDs. Timestamps are ISO 8601 with offset, always UTC (`2026-09-22T17:47:52Z`).
- Enum values are the display strings: `"In Progress"`, `"Facility Admin"`, `"Critical"`.
- Request bodies are **strict** (`extra="forbid"`): an unknown field is `400`, never silently ignored.
  No request body contains a server-controlled field (`id`, `reporter_id`, `status`, stamps…).
- **`PUT` is a partial update.** Omitted fields are unchanged; an explicit `null` clears a nullable
  field and is rejected (`400`) for a required one. The rubric asks for `PUT`, and every update schema
  is all-optional, so this is PATCH semantics on the PUT verb — stated here rather than discovered.
  Implementation reads `model_dump(exclude_unset=True)` so "omitted" and "null" stay distinguishable.

| Outcome | Status | Body |
|---|---|---|
| Read / update | `200` | The resource |
| Create | `201` | The created resource, plus `Location` header |
| Delete, logout | `204` | Empty |
| Accepted, outcome not disclosed | `202` | `{"message": ...}` (register only) |

### 1.5 Visibility: 404, not 403

Incidents and everything beneath them (notes, history, escalations) are read through
`scope_incidents`. A row outside the caller's scope is **filtered out**, so asking for it returns
exactly what a nonexistent id returns: `404 not_found`. No code path can emit a `403` that confirms
the row exists (`scoping.py`). Children are reachable only through a join to a scoped parent; no
repository calls `session.get()` on a child (S6).

A `403` is returned only when the caller **can already see** the resource but may not perform this
action on it — e.g. an employee editing the priority of their own incident.

### 1.6 Collections

Every list endpoint returns the same envelope and takes the same paging parameters:

```json
{ "items": [ ... ], "total": 42, "limit": 25, "offset": 0 }
```

| Param | Default | Rule |
|---|---|---|
| `limit` | `25` | `1..100` |
| `offset` | `0` | `≥ 0` |
| `sort` | per endpoint | Literal allowlist per endpoint; anything else is `400`. Never a raw column name. |
| `order` | `desc` | `asc` \| `desc` |

`total` counts rows visible **to this caller**, computed through the same scoping helper as `items`.

### 1.7 Errors

One envelope everywhere (`errors.py`):

```json
{ "error": "validation_error",
  "message": "Request validation failed.",
  "details": [{"field": "building_id", "message": "Building does not exist."}],
  "request_id": "8f2e…" }
```

`details` is always a list of `{field, message}` — built from an allowlist, never by spreading
Pydantic's errors, so a rejected password is never echoed (S3).

| `error` | Status | Meaning |
|---|---|---|
| `validation_error` | 400 | Malformed body/query, failed constraint, **or a reference to an entity that does not exist** |
| `unauthenticated` | 401 | Missing, invalid or revoked token; bad credentials |
| `token_expired` | 401 | Access token expired — client should refresh |
| `wrong_token_type` | 401 | Refresh token used as access token, or vice versa |
| `forbidden` | 403 | Visible resource, action not permitted for this caller |
| `not_found` | 404 | No such resource **or not visible to this caller** |
| `conflict` | 409 | Uniqueness, still-referenced delete, or state that forbids the action |
| `refresh_token_reused` | 401 | A rotated refresh token was replayed; the whole family is revoked — sign in again |
| `invalid_transition` | 409 | No workflow edge from the current status to the target |
| `internal_error` | 500 | Anything unexpected; message scrubbed |

A reference in the **body** to a missing entity (`building_id` that does not exist) is `400` with a
field detail — the request is invalid. A missing entity in the **path** is `404` — the resource is.

---

## 2. `auth` service — `/api/auth`

| # | Method | Path | Roles | Success | Task |
|---|---|---|---|---|---|
| A1 | POST | `/register` | public | 202 | T39 |
| A2 | POST | `/login` | public | 200 `TokenPair` | T40 |
| A3 | POST | `/refresh` | public (refresh token) | 200 `TokenPair` | T41 |
| A4 | POST | `/logout` | public (refresh token) | 204 | T43 |
| A5 | POST | `/logout-all` | ANY | 204 | T43 |
| A6 | GET | `/me` | ANY | 200 `MeOut` | T42 |
| A7 | POST | `/me/password` | ANY | 204 | T119 |
| A8 | GET | `/users` | ADM | 200 `Page[UserOut]` | T44 |
| A9 | POST | `/users` | ADM | 201 `UserOut` | T44 |
| A10 | GET | `/users/{user_id}` | ADM | 200 `UserOut` | T44 |
| A11 | PUT | `/users/{user_id}` | ADM | 200 `UserOut` | T44 |
| A12 | DELETE | `/users/{user_id}` | ADM | 204 | T44 |

### A1 `POST /register`

Self-registration. Always creates an **Employee**.

```json
{ "email": "jane@acme.inc", "password": "correct horse battery", "full_name": "Jane Doe",
  "occupation": "Financial Analyst", "date_of_birth": "1995-01-30" }
```

- `occupation` is required: self-registration always creates an Employee, and every Employee has
  one. `date_of_birth` is required and may not be after today (UTC) or before 1900-01-01.
- `email` must be exactly `@acme.inc` (case-insensitive, trimmed); `…@acme.inc.evil.com` and
  `…@sub.acme.inc` are rejected. Password 12 chars minimum, 72 **bytes** maximum.
- A `role` field is a `400` (strict body), not a silently ignored escalation attempt.
- **Response is identical whether or not the email is already registered:**
  `202 {"message": "If this address can be registered, the account is ready. Sign in to continue."}`.
  The existing-email path still runs a bcrypt hash so timing does not differ either (S8).
- **Decision D1:** `202` rather than `201`, because `201` would claim a creation that, for an
  existing email, did not happen. The client routes to sign-in either way.

Errors: `400` validation.

### A2 `POST /login`

```json
{ "email": "jane@acme.inc", "password": "correct horse battery" }
```

→ `200`
```json
{ "access_token": "eyJ…", "refresh_token": "eyJ…", "token_type": "bearer", "expires_in": 1800 }
```

- Unknown email, wrong password, deactivated account and locked account all return **the same**
  `401 unauthenticated` with the message *"Invalid email or password, or the account is temporarily
  locked."* An unknown email is compared against a module-level dummy hash so timing matches (S8).
- **Lockout is per account, never per IP** (the caller controls `X-Forwarded-For` on the Function
  URL): 5 consecutive failures set `locked_until = now + 15 min`; success resets the counter.
- Each login starts a new refresh-token **family**.

Errors: `400` validation, `401 unauthenticated`.

### A3 `POST /refresh`

```json
{ "refresh_token": "eyJ…" }
```

→ `200 TokenPair`. The presented token is revoked and a new one issued in the same family (rotation).
Only a hash of each refresh token is stored.

| Case | Response |
|---|---|
| Unknown, expired, or user inactive | `401 unauthenticated` |
| An access token was sent | `401 wrong_token_type` (or a stolen 30-min token becomes a 7-day one) |
| Any **revoked** token is presented — rotated, or retired by logout | Family revoked → `401 refresh_token_reused`. A logged-out token is indistinguishable from a stolen one without a revocation-reason column; both end in sign-in, so the client needs no second rule |
| Issued before `sessions_valid_from` | `401 unauthenticated` |

### A4 `POST /logout`

`{ "refresh_token": "eyJ…" }` → `204`. Revokes that token's family (this device). Does **not** require
an access token, so a user whose access token has already expired can still sign out. Always `204`,
even for an unknown token — it is not an oracle.

### A5 `POST /logout-all`

No body → `204`. Bumps `sessions_valid_from` to now and revokes every refresh token for the user.
Every outstanding access token dies on its next use.

### A6 `GET /me`

→ `200 MeOut`: `UserOut` plus `engineer_profile` (or `null`) for engineers. The frontend calls this
on load to learn the caller's id and role. A refresh token presented here is `401 wrong_token_type`.

### A7 `POST /me/password` (T119)

`{ "current_password": "…", "new_password": "…" }` → `204`. Wrong current password is
`400 validation_error` on `current_password` (the caller is already authenticated, so this discloses
nothing). Bumps `sessions_valid_from` — S7 already requires that on password change, but no endpoint
performs one yet. The client must log in again.

### A8 `GET /users` — admin

Query: paging, plus `role`, `is_active`, `email` (exact, case-insensitive — how an admin finds the
one person to promote), `search` (substring of email or name, ≤200 chars).
`sort ∈ {created_at, email, full_name, role}`, default `created_at desc`.

The admin assignment picker uses `GET /users?role=Engineer&is_active=true`. To promote someone, an
admin looks them up with `GET /users?email=jane@acme.inc` — an empty page, not a 404, when nobody
matches — then `PUT /users/{id}` with the new role.

### A9 `POST /users` — admin

```json
{ "email": "sam@acme.inc", "password": "…", "full_name": "Sam Lee",
  "role": "Engineer", "specialty": "HVAC", "date_of_birth": "1990-05-05" }
```

→ `201 UserOut`, `Location: /api/auth/users/{id}`.
- The only place a role can be chosen.
- `specialty` is **required** when `role` is `Engineer` (creates the `EngineerProfile` in the same
  transaction) and **rejected** for other roles.
- `occupation` is **required** when `role` is `Employee` and **rejected** for other roles.
- `date_of_birth` is required for every role, same rule as registration.
- Duplicate email → `409 conflict`. Unlike registration, admins are trusted and need to know.
- **Decision D5:** the `@acme.inc` domain rule applies here too.

### A10 `GET /users/{user_id}` — admin

→ `200 UserOut`; unknown id → `404`.

### A11 `PUT /users/{user_id}` — admin

Body: any of `full_name`, `role`, `is_active`, `specialty`, `occupation`, `date_of_birth`.

- Changing `role` or setting `is_active=false` bumps `sessions_valid_from` — the demotion is
  effective on the target's next request, not in 30 minutes.
- Changing the role **to** Engineer requires `specialty` unless a profile already exists (`400`).
- Changing the role **to** Employee requires `occupation` (`400`); changing it **away** from Employee
  clears the occupation, so "an occupation exactly when Employee" holds for every row. An
  `occupation` for any other role is `400`.
- `date_of_birth` may be corrected, never into the future.
- An admin may not demote or deactivate **themselves** → `409 conflict`. This guarantees at least
  one admin always remains able to undo mistakes.
- Demoting an Engineer who is the assignee of any non-closed incident → `409 conflict`, with the count
  in the message. Otherwise those incidents strand: no one holds `assigned_engineer` on them.

### A12 `DELETE /users/{user_id}` — admin

**Soft delete**: sets `is_active=false`, bumps `sessions_valid_from`, revokes refresh tokens → `204`.
A hard delete would orphan the incidents that reference the user. Same self and assignee guards as
A11. Deleting an already-inactive user is `204` (idempotent).

---

## 3. `facilities` service — `/api/facilities`

Reads are open to **ANY** authenticated user because the incident form needs the building → floor →
seat cascade. Writes are **ADM** only. Non-admins see only active records; admins may pass
`include_inactive=true`.

Mutations and single reads use **flat** paths (`/floors/{id}`); listing a parent's children uses
**nested** paths (`/buildings/{id}/floors`). Creation is flat with the parent id in the body, which
matches the existing `FloorCreate` / `SeatCreate` schemas.

| # | Method | Path | Roles | Success | Task |
|---|---|---|---|---|---|
| F1 | GET | `/buildings` | ANY | 200 `Page[BuildingOut]` | T66 |
| F2 | POST | `/buildings` | ADM | 201 `BuildingOut` | T66 |
| F3 | GET | `/buildings/{building_id}` | ANY | 200 `BuildingOut` | T66 |
| F4 | PUT | `/buildings/{building_id}` | ADM | 200 `BuildingOut` | T66 |
| F5 | DELETE | `/buildings/{building_id}` | ADM | 204 | T66, T72 |
| F6 | GET | `/buildings/{building_id}/floors` | ANY | 200 `Page[FloorOut]` | T71 |
| F7 | POST | `/floors` | ADM | 201 `FloorOut` | T67 |
| F8 | GET | `/floors/{floor_id}` | ANY | 200 `FloorOut` | T67 |
| F9 | PUT | `/floors/{floor_id}` | ADM | 200 `FloorOut` | T67 |
| F10 | DELETE | `/floors/{floor_id}` | ADM | 204 | T67, T72 |
| F11 | GET | `/floors/{floor_id}/seats` | ANY | 200 `Page[SeatOut]` | T71 |
| F12 | POST | `/seats` | ADM | 201 `SeatOut` | T68 |
| F13 | GET | `/seats/{seat_id}` | ANY | 200 `SeatOut` | T68 |
| F14 | PUT | `/seats/{seat_id}` | ADM | 200 `SeatOut` | T68 |
| F15 | DELETE | `/seats/{seat_id}` | ADM | 204 | T68, T72 |
| F16 | GET | `/categories` | ANY | 200 `Page[CategoryOut]` | T69 |
| F17 | POST | `/categories` | ADM | 201 `CategoryOut` | T69 |
| F18 | GET | `/categories/{category_id}` | ANY | 200 `CategoryOut` | T69 |
| F19 | PUT | `/categories/{category_id}` | ADM | 200 `CategoryOut` | T69 |
| F20 | DELETE | `/categories/{category_id}` | ADM | 204 | T69, T72 |
| F21 | GET | `/engineers` | ADM | 200 `Page[EngineerOut]` | T70 |
| F22 | GET | `/engineers/{user_id}` | ADM | 200 `EngineerOut` | T70 |
| F23 | PUT | `/engineers/{user_id}` | ADM | 200 `EngineerOut` | T70 |

### Buildings (F1–F5)

- **List** filters: `search` (code or name), `include_inactive`. `sort ∈ {code, name, created_at}`,
  default `code asc`.
- **Create** `{code, name, address?}`. Duplicate `code` → `409`.
- **Update** `{name?, address?, is_active?}`. `code` is immutable — it is printed on signage.
- **Delete** only when nothing references the building: any floor or any incident → `409 conflict`
  with *"Building has 3 floors and 12 incidents; deactivate it instead."*
  The FK from `floors` is `ON DELETE CASCADE`, so the database would **silently delete every floor
  and seat** — the service must check for children *before* deleting, not rely on the constraint.
  The FK from `incidents` is `RESTRICT`; its `IntegrityError` is mapped to `409`, never `500`.
  Deactivation (`is_active=false`) is the normal way to retire a building.

### Floors (F6–F10)

- **Nested list** `sort ∈ {level, name}`, default `level asc`. Unknown or inactive-to-you building → `404`.
- **Create** `{building_id, level, name?}`. Levels are signed (basements). Missing building → `400`
  on `building_id`; duplicate `(building, level)` → `409` (T67).
- **Update** `{level?, name?}`. Moving a floor to another building is not supported.
- **Delete** → `409` if it has seats or incidents reference it.

### Seats (F11–F15)

- **Nested list** filters `search` (code or label); `sort ∈ {code, label}`, default `code asc`.
- **Create** `{floor_id, code, label?}`. Duplicate `(floor, code)` → `409` (T68).
- **Update** `{code?, label?, is_active?}`.
- **Delete** → `409` if incidents reference it; deactivate instead.

### Categories (F16–F20)

A two-level tree: roots (`parent_id = null`) and their children.

- **List** filters: `parent_id` (children of one root), `roots_only=true`, `include_inactive`.
  `sort ∈ {name}`. Returns a flat list; the client builds the tree from `parent_id`.
- **Create** `{name, parent_id?, description?}`. The parent must exist and must itself be a root
  (`400` otherwise — the tree has two levels). Sibling names unique → `409`.
- **Update** `{name?, description?, is_active?}`. Re-parenting is not supported.
- **Delete** → `409` if it has children or incidents reference it.

### Engineer profiles (F21–F23)

Profiles are created with the user (A9) and live as long as the user, so there is no POST or DELETE
here. Paths are keyed by **user id**, which the client already has, not by profile id.

- **List** filters: `specialty`, `is_available`. Each item embeds the user summary and
  `open_assignments` (count of non-closed incidents assigned), so the admin can assign by load.
  `sort ∈ {full_name, specialty, open_assignments}`.
- **Update** `{specialty?, max_concurrent_incidents?, is_available?}`. `max_concurrent_incidents ≥ 1`.
- A user who is not an engineer → `404`.

---

## 4. `incidents` service — `/api/incidents`

| # | Method | Path | Roles | Success | Task |
|---|---|---|---|---|---|
| I1 | POST | `` (collection root) | ANY | 201 `IncidentOut` | T50 |
| I2 | GET | `` | ANY (scoped) | 200 `Page[IncidentOut]` | T51 |
| I3 | GET | `/{incident_id}` | ANY (scoped) | 200 `IncidentDetailOut` | T52 |
| I4 | PUT | `/{incident_id}` | ANY (scoped, field rules) | 200 `IncidentOut` | T53 |
| I5 | DELETE | `/{incident_id}` | ADM | 204 | T54 |
| I6 | POST | `/{incident_id}/transition` | ANY (scoped, workflow rules) | 200 `IncidentOut` | T55 |
| I7 | GET | `/workflow` | ANY | 200 `WorkflowOut` | T56 |
| I8 | GET | `/{incident_id}/history` | ANY (scoped) | 200 `Page[StatusHistoryOut]` | T55 |
| I9 | GET | `/{incident_id}/notes` | ANY (scoped) | 200 `Page[NoteOut]` | T57 |
| I10 | POST | `/{incident_id}/notes` | ANY (scoped) | 201 `NoteOut` | T57 |
| I11 | GET | `/{incident_id}/escalations` | ANY (scoped) | 200 `Page[EscalationOut]` | T58 |
| I12 | POST | `/{incident_id}/escalations` | reporter, assigned ENG | 201 `EscalationOut` | T58 |
| I13 | GET | `/escalations` | ADM | 200 `Page[EscalationOut]` | T58 |
| I14 | POST | `/escalations/{escalation_id}/decision` | ADM | 200 `EscalationOut` | T58 |
| I15 | GET | `/reports/summary` | ADM | 200 `SummaryReport` | T59 |
| I16 | GET | `/reports/sla` | ADM | 200 `SlaReport` | T59 |
| I17 | GET | `/reports/volume` | ADM | 200 `VolumeReport` | T59 |
| I18 | GET | `/reports/buildings` | ADM | 200 `BuildingsReport` | T124 |
| I19 | GET | `/reports/engineers` | ADM | 200 `EngineersReport` | T124 |
| I20 | GET | `/notifications` | ANY (own rows) | 200 `NotificationPage` | T125 |
| I21 | POST | `/notifications/read-all` | ANY (own rows) | 204 | T125 |
| I22 | POST | `/notifications/{notification_id}/read` | ANY (own rows) | 200 `NotificationOut` | T125 |

**Route order matters.** `/workflow`, `/escalations`, `/notifications` and `/reports/*` must be
registered **before** `/{incident_id}`. The typed UUID parameter would reject them anyway, but as a confusing `400` rather
than a match.

### How work actually flows (read this before I1–I6)

Scoping shows an engineer nothing but the incidents assigned to them
(`test_an_engineer_does_not_see_unassigned_work`, `test_an_engineer_does_not_see_incidents_they_reported`),
and the `Open → In Progress` edge is open to an `assigned_engineer` only. Assignment itself is an
admin's act: an engineer may not name an assignee on any transition, themselves included
(`test_5_an_engineer_may_not_assign_anyone`). The flow is therefore **admin triage**, matching the
brief ("facility admins assign work"):

1. Employee reports → `Open`, unassigned.
2. Admin assigns via `PUT {assignee_id}` while still `Open` (or assigns and starts in one step via
   the transition, passing `assignee_id`).
3. The assigned engineer, who can now see it, starts work: `Open → In Progress`.
4. Engineer blocks/unblocks and resolves; the reporter (or admin) confirms-and-closes or reopens.

**Decision D6:** keep this. The alternative — an engineer "pick-up queue" showing unassigned work —
means widening `scope_incidents`, which is the most security-sensitive function in the codebase.

### I1 `POST /api/incidents`

```json
{ "title": "Aircon dripping", "description": "Water on desk 3-14 since 9am",
  "priority": "Medium", "category_id": "…",
  "building_id": "…", "floor_id": "…", "seat_id": "…" }
```

→ `201 IncidentOut`, status `Open`, and an initial history row (`from_status = null → Open`).

- `reporter_id` comes from the principal; `status` from the workflow. Neither can be sent.
- Reference validation, all `400` with a field detail: building exists and is active; floor belongs
  to that building; seat belongs to that floor; `seat_id` requires `floor_id`; category exists and
  is active.
- **Decision D7:** employees may set `priority` at creation (their own view of urgency); only admins
  may change it afterwards. The alternative — force `Medium` and let admins triage — is simpler but
  loses the reporter's signal.

### I2 `GET /api/incidents`

Filters: `status`, `priority`, `building_id`, `category_id`, `assignee_id`, `created_from` and
`created_to` (inclusive UTC dates on `created_at`, `400` when inverted), `search` (title and
description, ≤200 chars). `sort ∈ {created_at, priority, status, title}`, default `created_at desc`.

Every filter is applied **inside** the scope, so no filter can widen it — an employee passing
`assignee_id` of some engineer still sees only their own incidents. `total` goes through the same
helper. An engineer's whole view is already their work; `?assignee_id=<own id>` is a no-op for them.

### I3 `GET /api/incidents/{incident_id}`

→ `200 IncidentDetailOut`: `IncidentOut` plus **`allowed_transitions`** for *this caller, right now*:

```json
"allowed_transitions": [
  { "to": "Resolved", "label": "Resolve", "requires": ["resolution_note"] },
  { "to": "Blocked",  "label": "Block on an external dependency", "requires": ["blocked_reason"] }
]
```

Computed from `workflow.allowed_targets`. The UI renders exactly these buttons, so it cannot offer an
action the API will reject (T86). Out of scope or nonexistent → `404`.

### I4 `PUT /api/incidents/{incident_id}`

Edits details. **Status is not settable here** — only via I6. Scoped `SELECT … FOR UPDATE`, then
field-level rules:

| Field | Reporter | Assigned ENG | ADM |
|---|---|---|---|
| `title`, `description`, `category_id` | while `Open` | — | yes |
| `priority` | — | — | yes |
| `assignee_id` | — | — | yes |

- A field the caller may not change → `403 forbidden` (they can see the incident, so this leaks
  nothing). The whole request is rejected; no partial apply.
- `assignee_id` must be an **active Engineer** → `400` otherwise. `null` unassigns, allowed only while
  `Open` — `In Progress` requires an assignee.
- A `Closed` incident is immutable → `409 conflict`.

### I5 `DELETE /api/incidents/{incident_id}` — admin

→ `204`. Notes, history and escalations cascade. The role gate runs before the lookup, so a
non-admin gets `403` whether or not the id exists.

### I6 `POST /api/incidents/{incident_id}/transition`

The **only** way status changes.

```json
{ "target_status": "Resolved", "resolution_note": "Replaced condensate pump." }
```

→ `200 IncidentOut`.

Order of checks, each with its own error, pinned by tests (plan, *Decisions closed*):

| Step | Failure |
|---|---|
| 1. Scoped `SELECT … FOR UPDATE` | `404 not_found` |
| 2. Edge exists (`current → target`) | `409 invalid_transition` — includes everything out of `Closed` |
| 3. Caller holds an allowed actor | `403 forbidden` |
| 4. Required fields present, non-blank | `400 validation_error` with field details |
| 5. `assignee_id`, if given, is named by an **admin** and is an active Engineer | `403` / `400` |

On success, in one transaction: apply the payload, write stamps from `stamps_for` (first-occurrence
for `acknowledged_at`/`assigned_at`, latest for `resolved_at`/`closed_at`), and append a history row
whose `note` is the `resolution_note` or `blocked_reason` and whose `assignee` is the engineer the
move handed the incident to (null when the assignee did not change). Leaving `Blocked` clears
`blocked_reason`; the history row keeps it.

The legal edges (from `workflow.TRANSITIONS`):

| From | To | Who | Requires |
|---|---|---|---|
| Open | In Progress | ADM, any ENG | an assignee (existing or in payload) |
| Open | Closed | ADM | `resolution_note` |
| In Progress | Blocked | ADM, assigned ENG | `blocked_reason` |
| Blocked | In Progress | ADM, assigned ENG | — |
| In Progress | Resolved | ADM, assigned ENG | `resolution_note` |
| Resolved | Closed | ADM, reporter | — |
| Resolved | In Progress | ADM, reporter | — (reopen) |

### I7 `GET /api/incidents/workflow`

→ `200` the output of `workflow.describe()`: every status and every edge with its label, allowed
actors and required fields. Static per deploy; the client may cache it for the session. I3's
`allowed_transitions` is the per-incident answer; this is the whole map.

### I8 `GET /api/incidents/{incident_id}/history`

→ `Page[StatusHistoryOut]`, `sort = created_at`, default **`asc`** (a timeline reads forwards).
Append-only; there is no write endpoint — rows are produced only by I1, I4 and I6. An assignment
through I4 (`assignee_id` changed to an engineer, status untouched) writes a row with
`from_status == to_status` and `assignee` set, so the timeline says which admin handed the incident
to whom; re-saving the same assignee writes nothing.

### I9–I10 Notes

- **List** applies `scope_notes`: employees see only `public` notes; staff see both. Default
  `created_at asc`.
- **Create** `{body, visibility?}` → `201`. An employee requesting `visibility: "internal"` →
  `403` — silently downgrading it to public would publish something the author meant to keep private.
  Notes on a `Closed` incident → `409`.
- Notes are **append-only**: no edit, no delete. They are part of the audit trail.

### I11–I14 Escalations

An escalation is a request to raise an incident's priority, decided by an admin.

- **Create (I12)** `{reason}` — by the **reporter** or the **assigned engineer**. Rejected with `409`
  when the incident is `Resolved` or `Closed`, is already `Critical`, or already has a `Pending`
  escalation (one at a time).
- **List for an incident (I11)** — anyone who can see the incident.
- **Admin queue (I13)** — all escalations, filter `status` (default `Pending`), oldest first.
  Each `EscalationOut` carries `incident_title`, `incident_status` and `incident_priority` as they
  are **now** (properties on the model read through the eager-loaded incident), so the queue page
  names and ranks each request without a fetch per incident, and an approval is visible on the
  row (T128).
- **Decide (I14)** `{decision: "Approved" | "Rejected", decision_note?}`.
  Approval raises priority **one level** (Low → Medium → High → Critical) in the same transaction and
  stamps `decided_by_id` / `decided_at`. Deciding an already-decided escalation → `409`.
  The field is `decision`, not `status`: `status` is on the server-controlled list and the schema
  test would (rightly) reject it.

### I15–I19 Reports — admin

All five share query parameters: `from`, `to` (dates, inclusive; default the last 30 days; range at
most 366 days, else `400`) and an optional `building_id`. Each is a single `GROUP BY` over the
stamped timestamps on `incidents` — no window functions, no scan of the history table (plan).

- **`/reports/summary`** — counts by status, by priority, and the open backlog by age bucket
  (`<1d`, `1–3d`, `3–7d`, `>7d`).
- **`/reports/sla?group_by=priority|building|category`** — per group: count, mean and p90
  time-to-acknowledge (`acknowledged_at − created_at`) and time-to-resolve (`resolved_at −
  created_at`), and the share resolved within target. p90 uses `percentile_cont`, an ordered-set
  aggregate that works with `GROUP BY`. **Decision D8:** targets Critical 4 h, High 24 h,
  Medium 3 d, Low 7 d, as constants in code.
- **`/reports/volume?interval=day|week&group_by=status|priority|category`** — incidents created per
  bucket via `date_trunc`, for the dashboard charts (T89).
- **`/reports/buildings`** — per building: incidents in the window, how many are still open (not
  Resolved or Closed) and how many are Critical, busiest first. An outer join from `buildings` with
  the window on the join, so every active building appears even at zero; a retired building only
  while it still has incidents in the window.
- **`/reports/engineers`** — per engineer: their `specialty` (the role from the engineer profile,
  outer-joined so a profile-less Engineer reads as null), incidents in the window assigned to them
  now, how many are still open, how many they completed (Resolved or Closed **with** `resolved_at`,
  so an incident closed without work counts for nobody) and the mean report-to-resolution over
  those, most completed first. Same outer-join shape: every active engineer appears even idle, a
  deactivated one only while they still hold incidents.

### I20–I22 Notifications (T125)

In-app only: nothing leaves the platform, since no mail or push channel exists in the deployment.
A `notifications` row is written **in the same transaction** as the action it announces, so a
notification can never describe a change that rolled back, and a change cannot commit without it.

Four events produce one:

- **`Reported`** — `POST /api/incidents` (I1) writes one row per **active Facility Admin**, except
  the reporter when they are an admin themselves.
- **`Assigned`** — a change of hands through `PUT` (I4) or a transition carrying `assignee_id` (I6)
  writes one row for the **new** assignee. Re-saving the same assignee says nothing new. A refused
  assignment (inactive engineer, 400) leaves no row, because the whole request rolls back.
- **`Resolved`** and **`Closed`** (T129, migration `d7a1c3e5f209`) — a transition into either
  status writes one row for the **reporter** and one per **active Facility Admin**, skipping
  whoever took the step (a reporter who confirms and closes already knows; so does the admin who
  closed it). The reporter is told the outcome without polling the incident, the admins see work
  land, and the bell now shows for every role.

The recipient is the only reader. Every query filters on the caller's id before anything else, so
someone else's notification is `404`, never `403` (§1.5). `NotificationOut` carries the kind, the
incident id, a **snapshot** of its title (so the line still reads after an edit, and listing needs no
join), the actor as a `UserSummary`, `read_at` and `created_at`; the client phrases it.

- **`GET /notifications?unread=true|false&limit&offset`** — newest first; `NotificationPage` is a
  `Page` plus `unread_count`, the caller's unread total over every row (not only the page or the
  filter), so one round trip serves both the badge and the list.
- **`POST /notifications/read-all`** — every unread row becomes read; `204` even when there was
  nothing to do.
- **`POST /notifications/{id}/read`** — idempotent; a second call keeps the first `read_at`.

The client polls I20 once a minute while the tab is visible and on focus. **Decision D9:** poll
rather than push — WebSockets need API Gateway, which is not in the Terraform, and a one-minute lag
on an internal ticketing tool costs nothing.

Both feed the admin overview on the landing page (T124). The "Download CSV" beside the list is
the ordinary list (I2) walked page by page under its current filters; `created_from` /
`created_to` on I2 use the same inclusive UTC dates as the reports, for a client that wants
exactly the rows a report counted.

---

## 5. Permission matrix

What each role may do, at a glance. "own" = reported by the caller; "assigned" = assigned to them.

| Capability | EMP | ENG | ADM |
|---|---|---|---|
| Register / login / refresh / logout | ✓ | ✓ | ✓ |
| Manage users | | | ✓ |
| Read facilities & categories (active) | ✓ | ✓ | ✓ |
| Write facilities & categories, manage engineer profiles | | | ✓ |
| Report an incident | ✓ | ✓ | ✓ |
| See incidents | own | assigned | all |
| Edit title / description / category | own, while Open | | ✓ |
| Change priority or assignee | | | ✓ |
| Delete an incident | | | ✓ |
| Transition | per workflow (reporter edges) | per workflow | per workflow (admin bypass, never creates an edge) |
| Read internal notes / write them | | ✓ | ✓ |
| Request an escalation | own | assigned | |
| Decide an escalation | | | ✓ |
| Reports | | | ✓ |

---

## 6. Schema changes this design needs

Landed in T118. None of it contains a server-controlled field unless it is admin-only and the
schema test exempts it explicitly, with a justification.

**New**

| Schema | Used by |
|---|---|
| `UpdateModel` base — `CLEARABLE` allowlist, `changes()` | every `PUT` (§1.4) |
| `TimelineParams` (paging, oldest first) | I8, I9, I11 |
| `RegisterAccepted` (`{message}`) | A1 |
| `MeOut` (`UserOut` + `engineer_profile: EngineerProfileOut`) | A6 |
| `ChangePasswordRequest` | A7 |
| `UserFilters` | A8 |
| `UserSummary` (`{id, full_name, role}` — no email) | embedded wherever a user is referenced |
| `BuildingFilters`, `FloorFilters`, `SeatFilters`, `CategoryFilters` | F1, F6, F11, F16 |
| `FloorUpdate`, `SeatUpdate`, `CategoryUpdate` | F9, F14, F19 |
| `EngineerOut` (profile + user + `open_assignments`), `EngineerProfileUpdate`, `EngineerFilters` | F21–F23 |
| `IncidentDetailOut`, `TransitionOption` | I3 |
| `WorkflowOut`, `WorkflowTransitionOut` (`from` on the wire) | I7 |
| `EscalationCreate`, `EscalationDecision`, `EscalationOut`, `EscalationFilters` | I11–I14 |
| `ReportRange`, `SlaParams`, `VolumeParams` (`from`/`to` on the wire) | I15–I17 |
| `SummaryReport`, `SlaReport`, `VolumeReport`, `CountBucket`, `SlaRow`, `SlaTarget`, `VolumeRow` | I15–I17 |
| `NotificationOut`, `NotificationPage` (`Page` + `unread_count`), `NotificationFilters` — T125, with the `notifications` table (migration `c49f04286e46`) | I20–I22 |

SLA targets and the report range bounds live in `acme_core/reporting.py`, not in a schema. `IncidentNote`,
`IncidentStatusHistory` and `EscalationRequest` gained the `author`, `actor`, `requested_by` and
`decided_by` relationships the summaries load from — ORM-only, no migration.

**Changed**

| Schema | Change | Why |
|---|---|---|
| `AdminUpdateUserRequest` | add `specialty` | role change to Engineer needs a profile (A11) |
| `AdminCreateUserRequest` | `@acme.inc` check; `specialty` required iff Engineer | A9, D5 |
| `IncidentOut` | embed `reporter` and `assignee` as `UserSummary` | employees cannot call `/users`, so an id alone cannot be rendered as a name |
| `NoteOut` | embed `author` | same |
| `StatusHistoryOut` | embed `actor` | same |
| `IncidentFilters` | add `category_id` | I2 |
| every `*Update` | now an `UpdateModel`: explicit `null` is refused unless the field is in `CLEARABLE` | §1.4 partial-update rule |
| `BuildingUpdate`, `IncidentUpdate` | moved onto `UpdateModel`; `address` / `category_id`, `assignee_id` clearable | same |

Facility references on an incident stay as ids: facilities are readable by everyone, so the client
resolves them from a cached lookup instead of every incident row repeating building and floor names.

---

## 7. Decisions (closed)

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| D1 | Register response | `202` with a generic message, identical for new and existing emails | `201` + body — leaks existence |
| D2 | `PUT` semantics | Partial update, `null` clears | True replacement — every client sends every field |
| D3 | Password change endpoint (A7) | Add it; S7 already assumes one exists | Leave out; admin reset only |
| D4 | `refresh_token_reused` status | **Done: `401`.** `plan.md` contradicted itself and the code had 409. The client's refresh interceptor now needs one rule: any 401 from `/refresh` → sign out | — |
| D5 | Admin-created users domain | Enforce `@acme.inc` too | Allow any domain for contractors |
| D6 | Engineer visibility of unassigned work | Keep admin triage; do not widen scoping. **Tightened 2026-09-23:** engineers see assigned work only (not their own reports) and cannot assign, even to themselves | Add a pick-up queue |
| D7 | Priority at creation | Reporter may set it; only admin changes it later | Force `Medium` |
| D8 | SLA targets | 4 h / 24 h / 3 d / 7 d constants | Configurable per category (needs a table) |
| D9 | Notification delivery | In-app rows, polled once a minute | Email (no sender configured) or WebSockets (needs API Gateway) |

## 8. Totals

| Service | Endpoints | + health/docs |
|---|---|---|
| `auth` | 12 | 4 |
| `facilities` | 23 | 4 |
| `incidents` | 22 | 4 |
| **Total** | **57** | **12** |
