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
| 2 | `auth` service | 16 / 16 |
| 3 | `incidents` service | 17 / 17 |
| 4 | `facilities` service | 10 / 10 |
| 5 | Frontend | 23 / 25 |
| 6 | Cloud, CI and operations | 4 / 14 |
| 7 | Documentation and handover | 7 / 7 |
| | **Total** | **91 / 123** |

---

## Phase 0 — Tooling foundation ✅

- [x] **T1** `pyproject.toml`: pytest (`importlib` import mode, markers, `filterwarnings=error`) and coverage (branch, package-scoped `source`, ratchet).
- [x] **T2** `tools/sync-shared.sh`: mirrors Terraform's discovery glob, `rsync --delete`, purges nested `__pycache__`, writes `_build_stamp.py`.
- [x] **T3** `tools/verify-sync.sh` + `tools/db.sh`: staleness guard and synchronous admin-invoke wrapper.
- [x] **T4** `Makefile` with 16 targets; `deploy` depends on `sync` + `verify-sync`.
- [x] **T5** `backend/auth` stub, `.gitignore`, `pyrightconfig.json` excluding vendored copies.
- [x] **T121** `tools/devserver.py` combined mode — `make serve` runs every discovered service in one process behind a prefix dispatcher, so the single Vite proxy rule (T75) reaches `/api/incidents` locally as CloudFront does in the cloud; `SERVICE=<name>` keeps the one-Lambda shape. `/api/docs` is one Swagger page over every service (merged schema; local only, since CloudFront routes nothing at that path).

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
- [x] **T46** `seed.py` — idempotent `uuid5` get-or-create, password **from payload**, strictly additive, histories replayed through `validate_transition`. *(two buildings with floors and seats, a two-level category tree, six incidents across every status; reporters resolved by email so a pre-registered account keeps its id)*
- [x] **T47** Integration tests — register, login, refresh, me, admin users, `test_route_contract`, `test_error_envelope`, `test_seed`, `test_readyz_migrations`. *(79 API + 11 seed tests; route contract driven from the OpenAPI schema)*
- [x] **T48** `tests/e2e/test_auth_journey.py` — real uvicorn, real commits across connections. *(throwaway `acme_e2e_<pid>` database, `tools.devserver:app` as a child process, every persistence assertion over a fresh `NullPool` connection; 7 tests, ~9 s)*

## Phase 3 — `incidents` service

- [x] **T49** Service scaffold: `requirements.txt`, `function.py`, `incidents_service/` package. *(no alembic: migrations stay auth-only, so `function.py` refuses admin commands by name; `make serve SERVICE=incidents` now exports `ACME_SERVICE_NAME`)*
- [x] **T50** `POST /api/incidents` — reporter from principal, never from the body. *(building/floor/seat nesting and category checked together, every problem reported in one `details[]`)*
- [x] **T51** `GET /api/incidents` — filters (status, priority, building, assignee, free-text) + pagination, all through `scope_incidents`; `total` counted through the same helper. *(priority and status sort by rank, not by display string)*
- [x] **T52** `GET /api/incidents/{id}` — scoped read, **404 not 403**. *(`allowed_transitions` omits a requirement the incident already satisfies, e.g. an existing assignee)*
- [x] **T53** `PUT /api/incidents/{id}` — scoped `SELECT ... FOR UPDATE` then mutate; status **not** settable here. *(one disallowed field rejects the whole request; unassigning only while Open)*
- [x] **T54** `DELETE /api/incidents/{id}` — 204, admin only.
- [x] **T55** `POST /api/incidents/{id}/transition` — the only status path; applies `validate_transition` and the stamp policy; writes `incident_status_history`. *(history rows carry an explicit timestamp: `now()` is the transaction start, so two rows in one transaction would tie)*
- [x] **T56** `GET /api/incidents/workflow` — serialises `TRANSITIONS` so the client renders only legal actions.
- [x] **T57** Notes — create/list; internal notes hidden from non-staff; child reachable only via a scoped parent join.
- [x] **T58** Escalation requests — create, list, approve/reject. *(approval raises priority one level in the same transaction; queue defaults to Pending, oldest first)*
- [x] **T59** Reporting endpoints — SLA and volume aggregates over the four stamped timestamps (`GROUP BY`, not window functions). *(p90 via `percentile_cont`; `date_trunc` in UTC explicitly)*
- [x] **T60** Integration tests for every endpoint above, both roles, both scope outcomes. *(`test_incidents_api.py`, 140 tests)*
- [x] **T61** `test_scoping_db.py` — real rows, all three roles, the 404/200 pair on the **same** id. *(plus the same pair over HTTP in `TestGet`)*
- [x] **T62** Transition integration tests — each legal edge end to end, plus history rows and stamp values. Includes the full **admin-triage journey**: employee reports → admin assigns while Open → the engineer (who could not see it before) now can, and starts work *(api.md §4)*. *(the five-step order of checks is pinned one test per step)*
- [x] **T63** Filter/pagination tests incl. sort allowlist rejection.
- [x] **T64** Deploy and smoke-test the service. *(2026-09-23: every route answers through CloudFront. Two findings, both fixed: the origin access control overwrote the bearer header (T123 note) and a cold environment took 12 s because the web stack was imported inside the invoke phase with no shipped bytecode; the import now runs at module scope, in the init phase, which gets a full CPU.)*
- [x] **T125** In-app notifications — an engineer is told when an incident is assigned to them, every active admin when one is reported *(api.md I20–I22, D9)*. *(`notifications` table, migration `c49f04286e46`; rows written in the same transaction as the report or the assignment, by `PUT` and by transition alike, only on a real change of hands and never to the actor themselves; the recipient is the only reader, structurally, so another user's row is 404. `NotificationPage` carries `unread_count` so the badge and the list are one round trip. Frontend: `components/NotificationBell.jsx` in the app bar for staff only, polling once a minute while visible and on focus, a menu that phrases each row and marks it read on the way to the incident, "Mark all as read". 14 backend tests, 12 frontend tests)*

## Phase 4 — `facilities` service

- [x] **T65** Service scaffold. *(discovered automatically once `requirements.txt` exists; pytest, coverage, ruff, pyright, bandit and CI each needed a line; the dev-server fallback test had used `facilities` as its example of a service with no package)*
- [x] **T66** Buildings CRUD. *(`include_inactive` is honoured for admins only, ignored rather than refused for everyone else, so an employee's incident form never offers a retired building)*
- [x] **T67** Floors CRUD — uniqueness per building+level surfaced as 409. *(on update as well as create, flushed inside a savepoint so the session survives; a floor is exactly as visible as its building)*
- [x] **T68** Seats CRUD — uniqueness per floor+code. *(a non-admin sees a seat only when it and its building are active; the single read joins both)*
- [x] **T69** Categories CRUD incl. sub-categories. *(two things the database cannot enforce: root names are checked by the service because NULL parents are distinct under the unique constraint, and `passive_deletes` on `Category.children` stops the ORM nulling a child's parent before the RESTRICT key can refuse. Deactivating a root does not cascade; the client builds the tree from active roots)*
- [x] **T70** Engineer profiles CRUD — admin only. *(read and update only, keyed by user id; "engineer" means the user's role is Engineer and they are active, because a demotion leaves the profile row behind; `open_assignments` is a correlated subquery so it can be sorted on, since the pager keeps only the first column)*
- [x] **T71** Nested listings (`/buildings/{id}/floors`, `/floors/{id}/seats`). *(the parent's visibility is checked first; a retired parent is 404 to non-admins)*
- [x] **T72** Referential-integrity handling — deleting a building with floors is 409, not 500. The FKs are `ON DELETE CASCADE`, so the service checks for children **before** deleting; tests assert the floors and seats **still exist** after the rejected delete, not only the status code. *(also `incidents.floor_id` and `seat_id` are `SET NULL`, so the database would not refuse those deletes either; the service counts incident references for every resource. Where the database does refuse, the delete is flushed inside a savepoint and the `IntegrityError` maps to the same 409; tests miss each pre-check on purpose to prove it)*
- [x] **T73** Integration tests for all of the above. *(`test_facilities_api.py`, 118 tests, both roles, the 404/200 pair on one retired id per resource)*
- [x] **T74** Deploy and smoke-test. *(2026-09-23: answers through CloudFront; same cold-start fix as T64.)*

## Phase 5 — Frontend

Currently one line of work is allocated. **Roughly 2.5 of the rubric's 5 competencies score here.**

- [x] **T75** `vite.config.js` — `server.proxy` `/api` → `:8000`, **unrewritten**, so local and cloud paths match.
- [x] **T76** Fix `eslint.config.js` — it references two plugins missing from `package.json`, so `npm run lint` fails on a clean install. *(plugins installed; fast-refresh rule scoped off test files)*
- [x] **T77** Add a real `npm test` script — there is none today, so `npm test` fails outright. *(`vitest run`)*
- [x] **T78** Install MUI, React Router, React Responsive. *(MUI 9 and React Router 7 with the auth screens; React Responsive 10 with T90, behind `lib/useViewport.js`)*
- [x] **T79** API client — bearer injection, refresh-on-401 with rotation, and the **content-type guard** (CloudFront rewrites API 404s to `200 index.html`). *(`services/api.js`: `authedRequest` attaches the bearer, rotates once on 401 with concurrent callers sharing the rotation, never replays a retired refresh token, and ends the session only on an API refusal, not a network failure)*
- [x] **T80** Auth context and protected routes. *(`auth/AuthProvider.jsx` loads `GET /me` whenever a session appears, so role and name come from the server; `RequireUser` in `App.jsx` shows a frame while loading, redirects when anonymous, offers retry on failure)*
- [x] **T81** Login and registration screens with inline field errors from `details[]`. *(`lib/formErrors.js` routes known fields inline and the rest to a form-level alert; 27 component and client tests)*
- [x] **T82** App shell — responsive navigation, role-aware menu. *(`components/AppShell.jsx`: one 64px bar, wordmark, primary links, report action, account menu showing name and role; report action collapses to an icon on phones)*
- [x] **T83** Incident list — filters, pagination, empty/loading/error states. *(`pages/IncidentsPage.jsx`: filters and page live in the URL, search debounced, table above `md` and stacked rows below, engineers get "Assigned to me"; 8 tests)*
- [x] **T84** Incident detail — notes, history timeline, internal notes hidden for employees. *(`pages/IncidentPage.jsx`: notes with a staff-only visibility toggle, history, details with facility names resolved when the facilities service answers, escalation requests, admin triage of assignee and priority through `PUT`; 404 and per-section failures handled; 8 tests)*
- [x] **T85** Incident create form — building/floor/seat cascade, client validation before submit. *(`pages/NewIncidentPage.jsx` against api.md §3; written before the facilities service (T65-T71) landed, against the same contract; 5 tests)*
- [x] **T86** Transition controls driven by the workflow — only legal actions rendered, required fields prompted. *(driven by `allowed_transitions` on the incident, the per-incident answer api.md I3 prescribes for the UI; `TransitionDialog` prompts for exactly `requires`, engineers self-assign, admins choose from active engineers)*
- [x] **T87** Admin screens — user management, role assignment. *(`pages/UsersPage.jsx` behind `RequireRole`; filters and page in the URL, one dialog creates or edits, creating is the only place a role is chosen, editing sends only what changed and shows the role-specific field the API requires; the signed-in admin cannot change their own role or deactivate themselves; deactivation confirms and shows the "open assignments" 409 inline; 10 tests)*
- [x] **T88** Facilities management screens. *(`pages/FacilitiesPage.jsx`: buildings → floors → seats side by side above `md` and one at a time below, selection and "Show retired" in the URL; row menus edit, retire or restore, and delete with the API's "still referenced" refusal shown inline; categories as the two-level tree; engineer profiles with load against maximum; one generic `RecordDialog` for every record; 8 tests)*
- [x] **T89** Reporting dashboard — SLA and volume charts. *(`pages/ReportsPage.jsx` over I15–I17: range presets, dates and building in the URL; KPI tiles and one-hue bar lists from the summary, an SLA table with within-target meters and the D8 targets, and a stacked-column volume chart drawn as inline SVG with fixed colour slots, legend, hover and keyboard tooltip, and a table view; each report loads and retries on its own; no chart library added; 7 tests)*
- [x] **T124** Admin landing page: buildings, engineers and every incident as a file. *(I18 `/reports/buildings` and I19 `/reports/engineers`, one outer-join `GROUP BY` each so a quiet building or an idle engineer shows as zero rather than vanishing; `created_from`/`created_to` on the incident list. `components/admin/IncidentOverview.jsx` sits above the list on `/` for a Facility Admin: buildings ranked by incidents, still open and critical; engineers ranked by completed and by open workload as one horizontal stacked-bar chart each (`components/charts/StackedBars.jsx`: finished then open, whole-number axis, total at the tip, hover and keyboard tooltip, table view), critical as a one-hue list beside the buildings, and the workload table of assigned / open / completed / mean time to resolve; last 7, 30 or 90 days. "Download CSV" beside the list's filters walks every page the current filters match, oldest first, into one RFC 4180 file. 6 backend tests, 9 frontend tests)*
- [x] **T90** Responsive behaviour via React Responsive; verify at mobile, tablet, desktop. *(`lib/useViewport.js` wraps React Responsive's `useMediaQuery` over the theme breakpoints and replaces MUI's hook on every screen that switches layout at `md`; swept all ten screens at 390, 820 and 1440 px with Playwright, measuring `scrollWidth` against the viewport and every element's right edge: two phone overflows found and fixed, the engineers table (now scrolls sideways) and the report's building select (now sized to its row); the test setup's `matchMedia` mock is one stable function with swappable behaviour, because React Responsive captures it at import)*
- [x] **T91** Accessibility — labels, focus order, keyboard navigation, contrast, ARIA on dynamic regions. *(Audited 2026-09-23. Already in place: every field a real `<label for>` with helper and error text in `aria-describedby`; every icon button named; menus, dialogs and native selects from MUI for keyboard use; charts with keyboard tooltips and table views; notices as `status` or `alert`; lists `aria-busy` while loading; no click handler on a non-interactive element. Contrast computed for every theme pair, all above 5:1 in both schemes. Added: a "Skip to content" link first on every page targeting `main` (`id="main"`, `tabIndex={-1}`); focus moves to `main` after a route change so a screen reader announces the new page and the next Tab lands in it (`RouteFocus`); each page sets its own document title (`usePageTitle`). An axe pass (`src/test/a11y.test.jsx`, vitest-axe) renders every screen and fails on any violation; contrast is excluded there because jsdom lays nothing out.)*
- [x] **T92** Consistent loading / success / failure feedback across every mutation. *(audited every mutation: forms and dialogs own `submitting` + an in-flight button label + inline `details[]` and form-level errors; lists and pages mark `aria-busy` and dim; after-the-fact outcomes all go through one `components/Notice.jsx`, a success announced as `status` that fades, a failure announced as `alert` that stays until dismissed. Fixed the three one-click actions (reactivate, retire, restore) that had reported failures through the success toast)*
- [x] **T93** "Waking the database" state for the Aurora resume case, rather than a generic spinner. *(`services/readiness.js` polls `/api/auth/readyz` every 3 s for up to 90 s and publishes its progress; `services/api.js` treats a 0/500/502/503/504 as possibly-waking, waits, and retries once, except a POST the server may already have acted on, which is refused with a "check, then try again" error rather than replayed; `components/WakingBanner.jsx` sits above the routes and says what is happening with an elapsed count, so every page's own loading state simply lasts longer. First probe is silent, so a genuine 500 never shows the banner)*
- [x] **T94** PWA — manifest, service worker, offline shell *(rubric §5)*. *(`public/manifest.webmanifest` with 192, 512 and maskable icons plus an Apple touch icon, theme colour and description in `index.html`; `public/sw.js` precaches the shell and the hashed bundles it reads off `index.html`, serves navigations network-first with the cached `index.html` as fallback, bundles cache-first, and never touches `/api`; registered in production builds only from `src/pwa.js`; `components/OfflineBanner.jsx` says when the browser is offline. Proven against `vite preview` with Playwright: worker active, cache filled, a fresh navigation offline renders the app with the offline banner, back online it clears)*
- [x] **T126** Public landing page — what an anonymous visitor sees at `/` before signing in. *(`pages/LandingPage.jsx`: the pitch with a real incident card over the lobby photo, the three-step workflow, one card per role, the D8 response targets stated as constants, and sign-in / registration as the only actions; `RequireUser` shows it for an anonymous visitor at the root and still sends a deep link to `/login` with `from`. Mockup agreed on a design canvas first. 5 tests)*
- [x] **T95** Vitest + React Testing Library setup. *(jsdom, `src/test/setup.js`, router-aware `renderPage` helper)*
- [x] **T96** Component tests to **80%+** *(rubric)*. *(100 Vitest tests over 15 files; 85.9% statements, 79.9% branches measured 2026-09-23; `vite.config.js` now fails `test:coverage`, and so CI, below 80% statements/lines/functions and 75% branches)*
- [x] **T97** Playwright config + proxy spec (`/api/auth/login` → 400, proving the proxy wiring). *(`frontend/playwright.config.js` starts its own backend, `tools/e2e_backend.py`: a throwaway `acme_e2e_ui` database, migrated and seeded with `ACME_SEED_PASSWORD`, served on :8100 by the same devserver as `make serve`; Vite on :3100 proxies `/api` there via `VITE_API_PROXY`. `e2e/proxy.spec.js` proves the empty login is the API's own 400 envelope and every service's `healthz` answers through the proxy. `npm run test:e2e`; needs local PostgreSQL and `.venv`, not wired into CI)*
- [x] **T98** E2E on critical paths — login → create incident → transition → resolve *(rubric wants 100% of critical paths)*. *(`e2e/critical-path.spec.js`: a new employee registers and signs in, reports an incident against seeded facilities, the seed admin acknowledges it assigning Hank Vance and resolves it, the reporter confirms and closes, and the list shows Closed; a second spec proves another employee gets "Incident not found" for it, the 404-not-403 rule)*

## Phase 6 — Cloud, CI and operations

- [x] **T99** First AWS deploy of the `auth` service; record `Max Memory Used`, cold start and Aurora resume in NOTES.md. *(2026-09-23: auth, facilities and incidents all deployed; the numbers live in NOTES.md "Measured numbers": 2.9–3.0 s init plus 1.8 s for the first request, 141–142 MB of 512 used, login 1.1 s warm; Aurora resume was 45–60 s on the first `migrate-cloud` invoke, now avoided by `min_capacity` 0.5 for the demo)*
- [x] **T100** `make migrate-cloud` against Aurora. *(2026-09-23: Aurora stamped at `c49f04286e46`; the first invoke times out while a paused cluster resumes, the second connects)*
- [x] **T101** `make seed-cloud` with a payload-supplied password. *(2026-09-23: `ADMIN_PASSWORD=… make seed-cloud`; CloudWatch shows `admin_action_started` / `admin_action_finished` for `action: seed` inside the auth Lambda; the password went in the invoke payload and never touched the repo; the demo signs in against that seed)*
- [x] **T102** Characterise the CloudFront 404 rewrite empirically; confirm whether it caches. *(2026-09-23, probed through the distribution: `custom_error_response` turns a 404 from **any** origin into `200 index.html`, so `/api/auth/no-such-route` answers 200 HTML while a 401 passes through untouched; it **does cache**: `error_caching_min_ttl = 300`, and a never-requested path answers `x-cache: Error from cloudfront` with `age: 305` on its very first hit, because the rewritten page is one cached object shared by every 404 path; real API responses stay uncached under the CachingDisabled policy. The client's content-type guard is the mitigation, NOTES.md known gaps)*
- [x] **T103** Verify `/api/auth/docs` is reachable through CloudFront. *(2026-09-23: `/api/auth/docs`, `/api/incidents/docs` and each `openapi.json` answer 200 through the distribution)*
- [x] **T104** Test whether an absolute path in `requirements.txt` lets Terraform vendor `acme_core` — if it works it **deletes the rsync bug class** rather than detecting it. *(2026-09-23: it does not. pip refuses a bare directory, "Neither 'setup.py' nor 'pyproject.toml' found"; making `acme_core` a package would fix that but would ship `migrations`, `seed.py` and `admin_actions.py` to every service, the split `tools/sync-shared.sh` `AUTH_ONLY` exists to prevent, and lose the build stamp. rsync plus `verify-sync` stays)*
- [x] **T105** `unzip -l` the built artifact; confirm nothing pip-installs into the service dir (justifies the simplified `.gitignore`). *(2026-09-23: newest zip is 1236 entries, 47.6 MB unzipped, 5 `.pyc`; top level is the service package, `acme_core`, and pip's site-packages (sqlalchemy, pydantic, psycopg, fastapi, …). `git status --ignored` on the three service dirs shows only the vendored `acme_core/` copy and `__pycache__/`: pip installs into `infra/builds`, nothing into the service dir)*
- [x] **T106** Deploy the frontend via `bin/deploy-frontend.sh aws`; verify the CloudFront URL end to end. *(2026-09-23, redeployed after PR #28: the live bundle `index-B54SSUZE.js` carries the skip link; through CloudFront a fresh employee registers (202), logs in (200), reads `/me` (200) and the incident list (200))*
- [x] **T107** CI test job — pytest + coverage with a PostgreSQL service container, `htmlcov` uploaded as an artifact. *(`.github/workflows/python.tests.yml`: Python 3.13, `postgres:17` service, `make lint` + `make cov` verbatim, `backend-coverage` artifact kept 14 days even on a red run)*
- [x] **T108** CI frontend job — lint plus Vitest. *(`.github/workflows/react.tests.yml`: Node 24, `npm ci` cached on the lockfile, lint → test → `test:coverage`, `frontend-coverage` artifact kept 14 days; no threshold yet, 84.77% statements measured for T96)*
- [x] **T109** Raise the coverage ratchet to its final value once all services exist. *(decided 2026-09-22: the final value is the current 98. Measured 99.8% with all three services against a rubric goal of 80%, so the gate already over-delivers and the time goes to deploy day instead)*
- [x] **T110** Re-verify `./bin/cleanup-environment.sh` still works against everything deployed. *(2026-09-23, as a dry run: `terraform plan -destroy` against the live state plans 43 resources to destroy with no errors, and the script's backup-to-S3 step still targets the tfstate bucket; the destroy itself was not run because the demo is 2026-09-24)*
- [x] **T123** Function URLs require IAM on AWS. An origin access control of type `lambda` makes CloudFront sign every origin request with SigV4; `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction` are granted to this distribution and nothing else; the URL-level CORS block applies only under LocalStack, where the browser calls the URLs directly. The API client sends `x-amz-content-sha256` with every request body, because Lambda refuses a signed request whose payload hash is missing. *(Terraform validates and the client tests pass; the diagrams are updated. Closes the "Function URL is public" accepted gap.)* **Verified on the first deploy, 2026-09-23, with one finding:** the OAC also overwrites the viewer's `Authorization` header with its signature, so every authenticated call was a 401 while login and refresh, which carry the token in the body, worked. The access token now travels in `X-Acme-Authorization` (api.md §1.2); `Authorization` is still honoured for curl, Swagger and the tests.
- [x] **T122** Load test on deploy day, **if time allows**: one Artillery run against the deployed login and incident-list endpoints at modest concurrency; record p95, error rate and any connection errors in NOTES.md next to the cold-start and memory numbers. Expected finding: `pool_size=1` per Lambda with no `reserved_concurrent_executions` (plan known-gaps table) — state the limit rather than fix it. *(rubric "Performance Testing"; not a coverage item)* *(2026-09-23: Artillery 2, 60 s at 5 new users/s, 4:1 incident list to login, from the VDI through CloudFront. 300 requests, 300 × 200, 0 failed. Incident list median 32 ms, p95 50 ms, max 63 ms, every one warm. Login median 1.06 s, p95 4.07 s, max 6.0 s: the burst spawned four auth environments (init 2.4–3.0 s) and each paid bcrypt plus its first TLS connection. No connection errors, so the `pool_size=1` / no-reserved-concurrency limit was not reached at this rate; it stands as a known gap, not a fix)*

## Phase 7 — Documentation and handover

- [x] **T111** `NOTES.md` — assumptions, trade-offs, **measured** numbers, known gaps table. *(root `NOTES.md`; every number is from CloudWatch `REPORT` lines or a `curl` through CloudFront on 2026-09-23)*
- [x] **T112** Root `README.md` backend section — architecture, the modular-monolith framing, `make` commands. *("The solution" section at the top of the root README)*
- [x] **T113** Document that `make serve` supersedes `bin/start-dev.sh`, and why *(the rubric scores "runs locally from documented commands")*. *(README "Run it locally")*
- [x] **T114** API reference — link the live `/api/auth/docs`, plus an endpoint table. *(README "API reference": the three live Swagger pages and a 27-row table over all 57 endpoints)*
- [x] **T115** Test-artifacts section — commands, results, and known gaps per tier *(rubric bullet, explicitly).* *(README "Tests")*
- [x] **T116** Security notes — the pet-name password finding, the Function URL (IAM-only behind CloudFront since T123; still no edge control is an authorization boundary), `@acme.inc` as validation not authentication, the IAM caveat. *(`NOTES.md` "Security notes")*
- [x] **T117** Demo script — the exact sequence to run in front of a reviewer, including the warm-up invoke. *(`NOTES.md` "Demo script": a two-minute warm-up, nine steps, and the Aurora floor to revert afterwards)*

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
| First cloud request may 504 | Aurora resume can exceed CloudFront's 30 s origin timeout (measured 45-60 s). Mitigated by a warm-up; for demo day `min_capacity` is 0.5 so it never pauses, to be put back to 0 afterwards. |
| `@acme.inc` is validation, not authentication | No email verification. Anyone may assert an address they do not control. |
| Session credentials expire | `ENVIRONMENT.config` holds STS tokens; cloud work needs `./bin/setup-participant.sh` re-run. |
| `bin/start-dev.sh` is unused | It hard-exits without LocalStack. `make serve` replaces it; documented in T113. |
