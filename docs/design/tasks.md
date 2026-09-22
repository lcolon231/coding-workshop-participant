# Task list — ACME Facility Incident Management

Every task required to complete the project, not just the current vertical slice.
Derived from the brief, the rubric in [`../full-stack.md`](../full-stack.md), and the findings in
[`reviews.md`](reviews.md). Design rationale lives in [`plan.md`](plan.md); the HTTP contract every endpoint
task implements is [`api.md`](api.md); this file is the backlog.

Task numbers are stable identifiers, not an order: tasks added later take the next free number and
are placed in the phase where they belong.

**Status:** `[x]` done · `[~]` in progress · `[ ]` not started · `[!]` blocked or needs a decision

| Phase | Scope | Done |
|---|---|---|
| 0 | Tooling foundation | 6 / 6 |
| 1 | `acme_core` shared kernel | 30 / 30 |
| 2 | `auth` service | 15 / 16 |
| 3 | `incidents` service | 1 / 16 |
| 4 | `facilities` service | 0 / 10 |
| 5 | Frontend | 5 / 24 |
| 6 | Cloud, CI and operations | 0 / 12 |
| 7 | Documentation and handover | 0 / 7 |
| | **Total** | **56 / 120** |

---

## Phase 0 — Tooling foundation ✅

- [x] **T1** `pyproject.toml`: pytest (`importlib` import mode, markers, `filterwarnings=error`) and coverage (branch, package-scoped `source`, ratchet).
- [x] **T2** `tools/sync-shared.sh`: mirrors Terraform's discovery glob, `rsync --delete`, purges nested `__pycache__`, writes `_build_stamp.py`.
- [x] **T3** `tools/verify-sync.sh` + `tools/db.sh`: staleness guard and synchronous admin-invoke wrapper.
- [x] **T4** `Makefile` with 16 targets; `deploy` depends on `sync` + `verify-sync`.
- [x] **T5** `backend/auth` stub, `.gitignore`, `pyrightconfig.json` excluding vendored copies.
- [x] **T121** `tools/devserver.py` combined mode — `make serve` runs every discovered service in one process behind a prefix dispatcher, so the single Vite proxy rule (T75) reaches `/api/incidents` locally as CloudFront does in the cloud; `SERVICE=<name>` keeps the one-Lambda shape.

## Phase 1 — `acme_core` shared kernel ✅

- [x] **T6** `config.py` — `Settings`, single `in_lambda()` discriminator, URL builder, password masking.
- [x] **T7** `db/engine.py` — locked lazy engine, `pool_size=1`, `pre_ping`, `get_db()`, `dispose_engine()`.
- [x] **T8** `db/base.py` — `DeclarativeBase` with naming convention, UUID and timestamp mixins.
- [x] **T9** Tests for T6–T8 + the no-I/O guard fixture. *(44 tests, 98.5%)*
- [x] **T10** `errors.py` — `AppError` hierarchy, flat `{error, message, details, request_id}` envelope, code→status table, FastAPI handlers. `details[]` built from an explicit allowlist, never by spreading `exc.errors()`.
- [x] **T11** `logging_config.py` — JSON logs, `request_id` ContextVar, denylist for `password`/`authorization`/`*_token`.
- [x] **T12** `api.py` — `create_app(service)`; routes at `/api/<service>`; `docs_url`/`openapi_url` under the prefix; `/healthz` (must build **no** engine) and `/readyz`; **no** `CORSMiddleware`.
- [x] **T13** Tests: error envelope shape, 422→400 override, `WWW-Authenticate` on 401s, `request_id` isolation, no secret ever logged, `/healthz` engine-free. *(151 tests, 97.5%)*
- [x] **T14** `models/enums.py` — `Role`, `IncidentStatus`, `Priority`, `NoteVisibility`.
- [x] **T15** `models/user.py` — `users` (+`is_active`, `sessions_valid_from`, `failed_login_count`, `locked_until`), `engineer_profiles` (1:1), `refresh_tokens`.
- [x] **T16** `models/facility.py` — `buildings`, `floors` (uq `building+level`), `seats` (uq `floor+code`).
- [x] **T17** `models/catalog.py` — `categories` (self-referential parent).
- [x] **T18** `models/incident.py` — `incidents` (required `building_id`; nullable `floor_id`/`seat_id`; four stamped timestamps), `incident_notes`, `incident_status_history`, `escalation_requests`.
- [x] **T19** `app_secrets` table — carrier for the random JWT secret.
- [x] **T20** Alembic (also adds the migrations-pending check to `/readyz`, deferred from T12): `env.py`, `script.py.mako`, `alembic.ini` above `acme_core/`, `db/migrate.py` building `Config` programmatically (`%`→`%%`).
- [x] **T21** `0001_initial` migration; review generated DDL by hand.
- [x] **T22** `tests/integration/conftest.py` — throwaway `acme_test_<pid>`, real `upgrade_head()`, savepoint rollback, `verify_session`, stale-DB sweep, correct dispose ordering.
- [x] **T23** `test_migrations.py` — upgrade → **downgrade base → upgrade**; **no pending autogenerate diff**; 12 tables; naming convention applied.
- [x] **T24** `test_model_constraints.py` — uniqueness, dangling FKs, stamp defaults NULL, enum round-trip.
- [x] **T25** `workflow.py` — `TransitionRule`, 7-edge `TRANSITIONS`, `actors_for`, `validate_transition` (edge → actor → fields), `allowed_targets`, **per-field** `STAMP_ON_ENTER`.
- [x] **T26** Workflow tests — hand-written oracle, 300-cell cross product, `actors_for` oracle, admin bypass pair, required fields incl. whitespace-only, `allowed_targets`, stamps incl. reopen.
- [x] **T27** `security/passwords.py` — bcrypt direct, reject >72 **bytes**, module-level dummy hash for constant-time login.
- [x] **T28** `security/secret.py` — 32 random bytes via `INSERT ... ON CONFLICT DO NOTHING`, cached in a module global.
- [x] **T29** `security/tokens.py` — PyJWT, pinned `algorithms=["HS256"]`, `typ`/`iss`/`aud`/`jti`/`iat`, reject absent `typ`.
- [x] **T30** Token and password tests — `alg:none`, wrong secret, expired, missing `sub`, malformed, >72 bytes, salt.
- [x] **T31** `security/principal.py` + `scoping.py` — `Principal`, `require_roles()`, `scope_incidents`, `scope_notes`.
- [x] **T32** `schemas/` — `StrictModel` (`extra="forbid"`), auth, facility, incident schemas; `Page[T]` for pagination.
- [x] **T33** Schema tests — `@acme.inc` gate incl. `…@acme.inc.evil.com`, case, whitespace; `role` in body; **no request schema contains a server-controlled field**.
- [x] **T34** `lambda_entry.py` — pure `classify(event)`; positive `source` marker, no HTTP keys, allowlisted action, fail closed. *(76 tests, 100%)*
- [x] **T118** Schema changes from [`api.md` §6](api.md#6-schema-changes-this-design-needs) — **before T35**. `UserSummary` embedded as `reporter`/`assignee`/`author`/`actor` (loaded with `selectinload`, no N+1); `MeOut`, `ChangePasswordRequest`, `UserFilters`; `AdminCreateUserRequest` gets the `@acme.inc` check and `specialty` required iff Engineer; `AdminUpdateUserRequest` gets `specialty`; facility `*Update` schemas; engineer-profile, escalation (`decision`, never `status`), workflow, detail and report schemas; every `*Update` rejects explicit `null` on required fields. *(95 tests, 100%)*

## Phase 2 — `auth` service

- [x] **T35** `requirements.txt` full pinned set + `function.py` with **lazily** constructed Mangum. *(`function.py` classifies first; Mangum built on first HTTP event)*
- [x] **T36** `auth_service/repository.py` — all user/token queries; no `session.get()` on children; no bare `update()`/`delete()`.
- [x] **T37** `auth_service/service.py` — register, authenticate, rotate refresh, admin user CRUD.
- [x] **T38** `auth_service/dependencies.py` — `current_user` (role and `is_active` read **from the DB row**, not the claim), `require_admin`, pagination params. *(moved to `acme_core/dependencies.py`: all three services authenticate the same way)*
- [x] **T39** `POST /register` — `@acme.inc` gate, always Employee, identical response whether or not the email exists.
- [x] **T40** `POST /login` — constant-time against a dummy hash; account lockout (`failed_login_count`, `locked_until`); **never** IP-based.
- [x] **T41** `POST /refresh` — rotation, hashed storage, reuse detection revoking the family (`401 refresh_token_reused`).
- [x] **T42** `GET /me` — rejects a refresh token with `wrong_token_type`.
- [x] **T43** `POST /logout` and logout-all bumping `sessions_valid_from`.
- [x] **T44** `/users` admin CRUD — Engineer/Admin creation with `EngineerProfile`, soft delete, 204, sort allowlist, pagination.
- [x] **T119** `POST /me/password` — verify current password, bump `sessions_valid_from`, revoke refresh tokens, 204 *(api.md A7)*.
- [x] **T120** User profile fields — `occupation` (required iff Employee, cleared on leaving Employee) and `date_of_birth` (required for every user, never after today, not before 1900); migration `8c235859e485`; exact `email` filter on `GET /users` so an admin can find a user to promote.
- [x] **T45** `admin_actions.py` — `migrate` / `seed` / `db-current`; `seed` requires `confirm == APP_ID`.
- [~] **T46** `seed.py` — idempotent `uuid5` get-or-create, password **from payload**, strictly additive, histories replayed through `validate_transition`. *(users done; facilities, categories and incident histories land with their services)*
- [x] **T47** Integration tests — register, login, refresh, me, admin users, `test_route_contract`, `test_error_envelope`, `test_seed`, `test_readyz_migrations`. *(79 API + 11 seed tests; route contract driven from the OpenAPI schema)*
- [x] **T48** `tests/e2e/test_auth_journey.py` — real uvicorn, real commits across connections. *(throwaway `acme_e2e_<pid>` database, `tools.devserver:app` as a child process, every persistence assertion over a fresh `NullPool` connection; 7 tests, ~9 s)*

## Phase 3 — `incidents` service

- [x] **T49** Service scaffold: `requirements.txt`, `function.py`, `incidents_service/` package. *(no alembic: migrations stay auth-only, so `function.py` refuses admin commands by name; `make serve SERVICE=incidents` now exports `ACME_SERVICE_NAME`)*
- [ ] **T50** `POST /api/incidents` — reporter from principal, never from the body.
- [ ] **T51** `GET /api/incidents` — filters (status, priority, building, assignee, free-text) + pagination, all through `scope_incidents`; `total` counted through the same helper.
- [ ] **T52** `GET /api/incidents/{id}` — scoped read, **404 not 403**.
- [ ] **T53** `PUT /api/incidents/{id}` — scoped `SELECT ... FOR UPDATE` then mutate; status **not** settable here.
- [ ] **T54** `DELETE /api/incidents/{id}` — 204, admin only.
- [ ] **T55** `POST /api/incidents/{id}/transition` — the only status path; applies `validate_transition` and the stamp policy; writes `incident_status_history`.
- [ ] **T56** `GET /api/incidents/workflow` — serialises `TRANSITIONS` so the client renders only legal actions.
- [ ] **T57** Notes — create/list; internal notes hidden from non-staff; child reachable only via a scoped parent join.
- [ ] **T58** Escalation requests — create, list, approve/reject.
- [ ] **T59** Reporting endpoints — SLA and volume aggregates over the four stamped timestamps (`GROUP BY`, not window functions).
- [ ] **T60** Integration tests for every endpoint above, both roles, both scope outcomes.
- [ ] **T61** `test_scoping_db.py` — real rows, all three roles, the 404/200 pair on the **same** id.
- [ ] **T62** Transition integration tests — each legal edge end to end, plus history rows and stamp values. Includes the full **admin-triage journey**: employee reports → admin assigns while Open → the engineer (who could not see it before) now can, and starts work *(api.md §4)*.
- [ ] **T63** Filter/pagination tests incl. sort allowlist rejection.
- [ ] **T64** Deploy and smoke-test the service.

## Phase 4 — `facilities` service

- [ ] **T65** Service scaffold.
- [ ] **T66** Buildings CRUD.
- [ ] **T67** Floors CRUD — uniqueness per building+level surfaced as 409.
- [ ] **T68** Seats CRUD — uniqueness per floor+code.
- [ ] **T69** Categories CRUD incl. sub-categories.
- [ ] **T70** Engineer profiles CRUD — admin only.
- [ ] **T71** Nested listings (`/buildings/{id}/floors`, `/floors/{id}/seats`).
- [ ] **T72** Referential-integrity handling — deleting a building with floors is 409, not 500. The FKs are `ON DELETE CASCADE`, so the service checks for children **before** deleting; tests assert the floors and seats **still exist** after the rejected delete, not only the status code.
- [ ] **T73** Integration tests for all of the above.
- [ ] **T74** Deploy and smoke-test.

## Phase 5 — Frontend

Currently one line of work is allocated. **Roughly 2.5 of the rubric's 5 competencies score here.**

- [x] **T75** `vite.config.js` — `server.proxy` `/api` → `:8000`, **unrewritten**, so local and cloud paths match.
- [x] **T76** Fix `eslint.config.js` — it references two plugins missing from `package.json`, so `npm run lint` fails on a clean install. *(plugins installed; fast-refresh rule scoped off test files)*
- [x] **T77** Add a real `npm test` script — there is none today, so `npm test` fails outright. *(`vitest run`)*
- [~] **T78** Install MUI, React Router, React Responsive. *(MUI 9 + React Router 7 installed with the auth screens; React Responsive lands with T90)*
- [~] **T79** API client — bearer injection, refresh-on-401 with rotation, and the **content-type guard** (CloudFront rewrites API 404s to `200 index.html`). *(`services/api.js`: envelope parsing, content-type guard and network errors done; refresh-on-401 pending)*
- [~] **T80** Auth context and protected routes. *(`services/session.js` + `RequireSession` redirect in `App.jsx`; the context itself pending)*
- [x] **T81** Login and registration screens with inline field errors from `details[]`. *(`lib/formErrors.js` routes known fields inline and the rest to a form-level alert; 27 component and client tests)*
- [ ] **T82** App shell — responsive navigation, role-aware menu.
- [ ] **T83** Incident list — filters, pagination, empty/loading/error states.
- [ ] **T84** Incident detail — notes, history timeline, internal notes hidden for employees.
- [ ] **T85** Incident create form — building/floor/seat cascade, client validation before submit.
- [ ] **T86** Transition controls driven by `GET /api/incidents/workflow` — only legal actions rendered, required fields prompted.
- [ ] **T87** Admin screens — user management, role assignment.
- [ ] **T88** Facilities management screens.
- [ ] **T89** Reporting dashboard — SLA and volume charts.
- [ ] **T90** Responsive behaviour via React Responsive; verify at mobile, tablet, desktop.
- [ ] **T91** Accessibility — labels, focus order, keyboard navigation, contrast, ARIA on dynamic regions.
- [ ] **T92** Consistent loading / success / failure feedback across every mutation.
- [ ] **T93** "Waking the database" state for the Aurora resume case, rather than a generic spinner.
- [ ] **T94** PWA — manifest, service worker, offline shell *(rubric §5)*.
- [x] **T95** Vitest + React Testing Library setup. *(jsdom, `src/test/setup.js`, router-aware `renderPage` helper)*
- [ ] **T96** Component tests to **80%+** *(rubric)*.
- [ ] **T97** Playwright config + proxy spec (`/api/auth/login` → 400, proving the proxy wiring).
- [ ] **T98** E2E on critical paths — login → create incident → transition → resolve *(rubric wants 100% of critical paths)*.

## Phase 6 — Cloud, CI and operations

- [ ] **T99** First AWS deploy of the `auth` service; record `Max Memory Used`, cold start and Aurora resume in NOTES.md.
- [ ] **T100** `make migrate-cloud` against Aurora.
- [ ] **T101** `make seed-cloud` with a payload-supplied password.
- [ ] **T102** Characterise the CloudFront 404 rewrite empirically; confirm whether it caches.
- [ ] **T103** Verify `/api/auth/docs` is reachable through CloudFront.
- [ ] **T104** Test whether an absolute path in `requirements.txt` lets Terraform vendor `acme_core` — if it works it **deletes the rsync bug class** rather than detecting it.
- [ ] **T105** `unzip -l` the built artifact; confirm nothing pip-installs into the service dir (justifies the simplified `.gitignore`).
- [ ] **T106** Deploy the frontend via `bin/deploy-frontend.sh aws`; verify the CloudFront URL end to end.
- [ ] **T107** CI test job — pytest + coverage with a PostgreSQL service container, `htmlcov` uploaded as an artifact. Today CI runs bandit and `npm audit` only.
- [ ] **T108** CI frontend job — lint plus Vitest.
- [ ] **T109** Raise the coverage ratchet to its final value once all services exist.
- [ ] **T110** Re-verify `./bin/cleanup-environment.sh` still works against everything deployed.

## Phase 7 — Documentation and handover

- [ ] **T111** `NOTES.md` — assumptions, trade-offs, **measured** numbers, known gaps table.
- [ ] **T112** Root `README.md` backend section — architecture, the modular-monolith framing, `make` commands.
- [ ] **T113** Document that `make serve` supersedes `bin/start-dev.sh`, and why *(the rubric scores "runs locally from documented commands")*.
- [ ] **T114** API reference — link the live `/api/auth/docs`, plus an endpoint table.
- [ ] **T115** Test-artifacts section — commands, results, and known gaps per tier *(rubric bullet, explicitly).*
- [ ] **T116** Security notes — the pet-name password finding, the public Function URL, `@acme.inc` as validation not authentication, the IAM caveat.
- [ ] **T117** Demo script — the exact sequence to run in front of a reviewer, including the warm-up invoke.

---

## Cross-cutting gates

Do not advance past these.

| Gate | Condition |
|---|---|
| G1 | `make migrate` builds 12 tables locally *(after T21)* |
| G2 | All acceptance curls pass against uvicorn *(after T47)* |
| G3 | The same curls pass against CloudFront **and memory is measured** *(after T99)* |
| G4 | `make cov` ≥ 80% backend *(after T60)* |
| G5 | Frontend coverage ≥ 80% and critical-path E2E green *(after T98)* |
| G6 | Full CRUD demonstrable in both local and cloud *(rubric "Implementation")* |

## Accepted gaps

Real limitations, recorded rather than silently carried. Each belongs in NOTES.md.

| Gap | Why it stands |
|---|---|
| Burst connection exhaustion | Needs `reserved_concurrent_executions` — a Terraform change, which is out of scope. |
| CloudFront rewrites API 404s to `200 index.html` | Distribution-level `custom_error_response`; handled on the client instead. |
| First cloud request may 504 | Aurora resume can exceed CloudFront's 30 s origin timeout. Mitigated by a warm-up, not fixed. |
| Function URL is public and bypasses CloudFront | `authorization_type = "NONE"` is set in Terraform. No edge control is a security boundary. |
| `@acme.inc` is validation, not authentication | No email verification. Anyone may assert an address they do not control. |
| Session credentials expire | `ENVIRONMENT.config` holds STS tokens; cloud work needs `./bin/setup-participant.sh` re-run. |
| `bin/start-dev.sh` is unused | It hard-exits without LocalStack. `make serve` replaces it; documented in T113. |
