# ACME Facility Incident Management — Scaffold + `auth` Vertical Slice

## Context

The workshop repo contains **no deployable backend service** — only `backend/_examples/`, which
Terraform ignores. We are building ACME Facility Incident Management: employees report facility
issues, facility admins define facilities and assign work, engineers resolve tickets. Evaluation is
`docs/full-stack.md` (Implementation, Design, Code, Testing, Experience; 80%+ backend coverage; a
README explaining architecture and trade-offs).

This task delivers the shared package, the full data model, and **one service working end to end
(`auth`)** — deliberately not three empty shells. `backend/incidents/` and `backend/facilities/`
are **not created yet**: an empty service dir becomes a real Lambda and dilutes the slice.

### Environments — LocalStack is not used

| | Local | Cloud |
|---|---|---|
| Backend | **uvicorn on :8000**, host Python | Lambda + Mangum, via `bin/deploy-backend.sh aws` |
| Database | native Postgres on `localhost:5432` | Aurora PostgreSQL 17.7 |
| Frontend | Vite :3000, `server.proxy` `/api` → `:8000` | S3 + CloudFront |
| Request path seen by app | `/api/auth/login` | `/api/auth/login` |

`bin/start-dev.sh` and `bin/proxy-server.js` are **not used** — `start-dev.sh` hard-exits without
LocalStack (`exit 1` after a 30 s poll), and the CORS proxy exists only to work around a LocalStack
bug. `bin/deploy-backend.sh aws` and `bin/deploy-frontend.sh aws` are used unmodified.

**The payoff:** because the Vite proxy forwards `/api` *without rewriting*, uvicorn receives exactly
the path CloudFront delivers. One path shape in both environments, so routes are mounted once with
`prefix="/api/auth"` and **no path middleware is needed**. (An earlier revision of this plan carried
a middleware to repair a `//login` double-slash and a missing CloudFront prefix strip; both were
artifacts of the LocalStack proxy and are now moot.)

### What the repo dictates (all verified by reading the files)

| Constraint | Source | Consequence |
|---|---|---|
| Services auto-discovered by `backend/*/requirements.txt`, one level deep, `_`/`.` skipped | `infra/locals.tf:23-26` | `_shared/` is invisible to Terraform — what we want |
| `handler` hardcoded `function.handler`, runtime `python3.13` | `infra/locals.tf:56-57` | service needs `function.py` exposing `handler` |
| `source_path` is a single-element list | `infra/lambda.tf:20-25` | shared code cannot be a second path → rsync |
| Lambda memory **128 MB**, no way to add env vars | `infra/lambda.tf:11`, `locals.tf:98-114` | cold-start RSS is the risk; **no `JWT_SECRET` var exists** |
| CloudFront has **no `origin_path`** | `infra/cloudfront.tf` (grep: zero matches) | Lambda receives the full `/api/auth/login` |
| Aurora **not** publicly accessible, `min_capacity = 0.0` | `infra/rds.tf` | only an in-VPC Lambda can reach it → migrations must run there |
| Zip patterns `["!__pycache__/.*", "!\\..*"]` are anchored | `infra/locals.tf:59` | **nested** `__pycache__` still gets zipped |
| CI runs `bandit -r ./backend` | `.github/workflows/python.actions.yml` | tests live outside `backend/` |
| DCO sign-off required | `CONTRIBUTING.md` | every commit uses `git commit -s` |

### Decisions taken (all confirmed with the user)

1. **Service dirs** `auth`, `incidents`, `facilities`; workflow at `/api/incidents/workflow`.
2. **Shared code** vendored by rsync from `backend/_shared/acme_core/`; copies gitignored.
3. **FastAPI + Mangum**; `function.py` is a thin adapter, uvicorn serves the same `app` locally.
4. **No LocalStack**: uvicorn + local Postgres for dev, Vite proxy for the frontend.
5. **Cloud migrations** via Lambda task-event invoke; IAM is the authz.
6. **Flat error envelope** `{error, message, details[], request_id}`.

---

## File tree

```
Makefile                      # venv/serve/migrate/seed/test/cov/sync/deploy/migrate-cloud
pyproject.toml                # pytest + coverage config only (no build backend)
requirements-dev.txt          # uvicorn, pytest, pytest-cov, httpx, freezegun, ruff, bandit
NOTES.md                      # assumptions, trade-offs, known gaps — a deliverable
tools/sync-shared.sh          # rsync acme_core -> each discovered service dir (pre-deploy)
tools/db.sh                   # aws lambda invoke wrapper for migrate/seed

backend/_shared/
  alembic.ini                 # host-only; sits ABOVE acme_core/ so it is never rsynced
  acme_core/
    config.py                 # Settings from POSTGRES_*/IS_LOCAL; host-vs-Lambda resolution
    errors.py                 # AppError hierarchy + handlers + flat envelope
    api.py                    # create_app(service_name): CORS, handlers, /healthz, /readyz,
                              #   and include_router(prefix=f"/api/{service_name}")
    logging_config.py         # JSON logs + aws_request_id in a ContextVar
    workflow.py               # the single transition table + validators
    scoping.py                # scope_incidents() / scope_notes()
    seed.py                   # idempotent seed
    admin_actions.py          # run_admin_action("migrate"|"seed"|"db-current")
    db/  base.py engine.py migrate.py
    models/  enums.py user.py facility.py catalog.py incident.py
    schemas/ common.py auth.py facility.py incident.py
    security/ passwords.py tokens.py principal.py
    migrations/ env.py script.py.mako versions/0001_initial.py

backend/auth/
  .gitignore  README.md  requirements.txt
  function.py                 # admin-event dispatch + Mangum(app)
  auth_service/               # a PACKAGE, not loose modules (see below)
    app.py dependencies.py routes.py service.py repository.py
  acme_core/                  # rsynced build artifact, gitignored

tests/                        # repo ROOT — bandit scans ./backend, and service dirs get zipped
  conftest.py  factories.py
  unit/         test_config, test_tokens, test_passwords, test_workflow_*, test_scoping, test_errors
  integration/  conftest.py, test_auth_*, test_admin_users, test_migrations, test_seed
```

**Why `auth_service/` is a package:** Terraform's `pip_requirements = true` vendors dependencies
*flat into the service directory* at zip time. Top-level module names like `app`, `routes`,
`service` can be shadowed by a transitive dependency. A package also makes `--cov=auth_service`
precise, whereas `--cov=backend/auth` would fold FastAPI and SQLAlchemy into the denominator.

## Key designs

**Host vs Lambda, for free.** The Lambda runtime sets `AWS_LAMBDA_FUNCTION_NAME`; a developer shell
does not. When not in Lambda, rewrite container-only hosts (`172.17.0.1`, `host.docker.internal`) to
`localhost`. Defaults in `config.py` are the local values from `infra/locals.tf`, so uvicorn,
Alembic and the seed all work with **zero exported env vars**. Never reads `DATABASE_URL`; appends
`sslmode=require` when `IS_LOCAL != "true"`.

**`JWT_SECRET` has no home.** `local.env_vars` has no such key and adding one means editing
Terraform. Derive it deterministically: `sha256(f"{APP_ID}:{POSTGRES_PASS}")` — stable across cold
starts and all three services, never committed. A workshop-grade compromise; production answer is
Secrets Manager.

**Lazy engine.** Module-global `_engine` built on first use; `pool_size=2, max_overflow=0,
pool_pre_ping=True, pool_recycle=280`. `pre_ping` covers Aurora scaling to zero; `max_overflow=0`
caps blast radius since a 128 MB Lambda serves one request at a time. `dispose_engine()` for tests.

**One app, two servers.** `auth_service/app.py` builds the FastAPI instance via
`create_app("auth")`, which mounts routers at `/api/auth`. `uvicorn auth_service.app:app` serves it
locally; `function.py` wraps the same object in `Mangum(app, lifespan="off")` for Lambda. Routes are
declared once and the only untested-until-deploy surface is Mangum's event translation — which is
why the plan deploys at commit 11 rather than at the end.

**`workflow.py`** — a frozen `TransitionRule` dataclass and a `TRANSITIONS` tuple of the 7 legal
edges keyed into `_BY_EDGE`. Rules are written in terms of an `Actor` *relationship*
(`ADMIN`/`ASSIGNED_ENGINEER`/`ANY_ENGINEER`/`REPORTER`), not a role; `actors_for(ctx)` derives which
the caller satisfies. `validate_transition` checks **edge → actor → required fields** in that order,
which makes "admin bypasses the actor check but *not* required fields" fall out structurally rather
than as a special case. `Closed` is terminal purely because no rule has `source == CLOSED`. A
separate `STAMP_ON_ENTER` map sets the four timestamps only when currently NULL, so re-entering
In Progress from Blocked never rewrites `acknowledged_at`. `allowed_targets()` drives React button
state and is what `GET /api/incidents/workflow` will serve.

**`scoping.py`** — `scope_incidents(stmt, principal) -> Select` returns a *new* statement
(SQLAlchemy 2.0 selects are generative), so it chains anywhere. Admin unchanged; Engineer
`or_(assignee_id, reporter_id)`; Employee `reporter_id`. Single-item reads use the same helper then
`.one_or_none()` → `NotFound`, making **404-not-403 structural**: an out-of-scope row is filtered
out, so no code path can leak a 403 confirming existence. Backed by an introspection test asserting
every repository function takes a keyword-only `principal`, plus a no-DB test compiling the
statement against the postgresql dialect and asserting the WHERE clause per role.

**`security/`** — `bcrypt` called directly (passlib 1.7.4 reads `bcrypt.__about__.__version__`,
removed in bcrypt ≥4.1 — a known footgun), with a 72-byte truncation guard. `PyJWT` with a `typ`
claim; the protected-endpoint dependency asserts `typ == "access"`, so a refresh token is rejected.
Refresh tokens stored **hashed** with `revoked_at` for rotation and reuse detection.

**`function.py`** — a Function URL event always carries `requestContext`; an `aws lambda invoke`
payload does not. That is the discriminator:

```python
def handler(event=None, context=None):
    if isinstance(event, dict) and "requestContext" not in event:
        if event.get("action") in _ADMIN_ACTIONS:        # migrate | seed | db-current
            from acme_core.admin_actions import run_admin_action   # lazy: keeps cold start lean
            return run_admin_action(event["action"], event.get("options") or {})
    return _asgi(event, context)
```

Authz is `lambda:InvokeFunction` (real AWS credentials), never a secret on a Function URL whose
`authorization_type` is `NONE`. **This is the only way to create the Aurora schema**, since the
cluster is not publicly accessible.

**Alembic.** `migrations/` lives *inside* `acme_core/` so it rsyncs into the Lambda. No `alembic.ini`
in any service dir — `Config` is built programmatically from the package path. Escape `%` as `%%`:
Alembic's `Config` is a ConfigParser and chokes otherwise. `env.py` takes its URL from
`get_settings()` with an `-x url=...` override for tests. `backend/_shared/alembic.ini` exists only
for `alembic -c backend/_shared/alembic.ini revision --autogenerate` and sits one level above
`acme_core/` so rsync never carries it into a service.

**`/readyz`** compares `current_revision()` to head and returns 503 `migrations_pending`. It
*detects*, never applies — a forgotten `make migrate-cloud` becomes a loud, self-diagnosing failure
instead of a mysterious `UndefinedTable`.

**Error envelope** (the chosen flat shape). `error` is a **stable machine code**, not prose, so the
client can switch on `token_expired` vs `refresh_token_reused` — both 401, very different UX.

```json
{ "error": "validation_error",
  "message": "Request validation failed.",
  "details": [{"field": "email", "message": "must be an @acme.inc address"}],
  "request_id": "8f2e-a11c" }
```

`details[]` maps mechanically from Pydantic v2's `exc.errors()`. `request_id` is
`context.aws_request_id` in Lambda and a generated uuid4 under uvicorn, carried in a ContextVar.
Registered once in `create_app()`, so all three services share it with no per-service code.
Codes: `validation_error` 400 · `unauthenticated`/`token_expired`/`wrong_token_type` 401 +
`WWW-Authenticate` · `forbidden` 403 · `not_found` 404 · `conflict`/`refresh_token_reused`/
`invalid_transition` 409 · `internal_error` 500 (message scrubbed, `request_id` kept).

**`tools/sync-shared.sh`** mirrors Terraform's discovery glob and `_`/`.` skip rule exactly so it
cannot drift, rsyncs with `--delete` (without it, a module deleted from `_shared` lingers in the
copy and keeps satisfying imports), and excludes `__pycache__`/`*.pyc` — the anchored zip patterns
do not. It runs as a prerequisite of `make deploy`; that is the entire reason the Makefile exists.
Local dev needs no sync: `PYTHONPATH` points at `backend/_shared` directly.

**`.gitignore`** (per service) — an allowlist, since vendored dependency directory names cannot be
enumerated and change with every `requirements.txt` edit:

```gitignore
*
!.gitignore
!README.md
!requirements.txt
!function.py
!auth_service/
!auth_service/**
```

## Dependencies — `backend/auth/requirements.txt`

`fastapi` · `mangum` · `pydantic` · `SQLAlchemy>=2.0` · `alembic` · `psycopg[binary]==3.2.3` ·
`PyJWT` · `bcrypt` — all `==` pinned. `uvicorn` goes in `requirements-dev.txt`, not here: it is the
local server, not Lambda payload.

`psycopg[binary]==3.2.3` is the **identical pin** already proven in
`backend/_examples/python-service/requirements.txt`. Deliberately excluded: `passlib` (broken against
bcrypt 4.x), `python-jose` (unmaintained, CVEs), `python-multipart` (login is JSON),
`pydantic-settings` (`os.getenv` directly keeps `Settings` importable with zero env vars — exactly
the host-Alembic case). `alembic` *is* a runtime dep because migrations run in-Lambda, but is
imported lazily so it costs zip bytes, not cold-start memory.

~45 MB unzipped / ~15 MB zipped, far inside the limits. **Memory, not wheels, is the risk**: that
import set lands ~70–95 MB RSS against a hardcoded 128 MB. Mitigations are code-only —
`from __future__ import annotations` everywhere, lazy imports of `alembic`/`seed`, never importing
`migrations` from `app.py`, `pool_size=2`, `lifespan="off"`.

Wheel/arch risk is low: the VDI is linux-x86_64 on CPython **3.13.15**, an exact match for the
`python3.13`/`x86_64` runtime, and Terraform builds with `build_in_docker = false` on that same
host. Deploying from an Apple Silicon Mac would silently ship arm64 wheels and fail at import with
`invalid ELF header` — noted in NOTES.md rather than solved, since it cannot happen on this VDI.

## Testing

Unit tier touches no database and carries most of the coverage: `workflow.py` is pure data and hits
~100% from one parametrised table over every `(from, to, role, actor)` cell; `config`, `tokens`,
`passwords`, `errors`, `scoping` are all DB-free.

Integration tier: a session fixture creates `acme_test_<pid>` (pid-suffixed so `pytest -n auto`
works later), runs the **real** `upgrade_head()` so a broken migration fails the suite, and drops it
with `WITH (FORCE)`. A function fixture opens a connection + outer transaction and binds a Session
with `join_transaction_mode="create_savepoint"` — application code calls `commit()` normally, it
lands on a savepoint, the outer rollback wipes it. Real commit paths, milliseconds per test, no
truncation. `app.dependency_overrides[get_db]` pins the TestClient to that session.

```toml
[tool.coverage.run]
source = ["acme_core", "auth_service"]      # packages, NOT backend/auth (vendored deps live there)
omit   = ["*/migrations/versions/*"]

[tool.pytest.ini_options]
pythonpath = ["backend/_shared", "backend/auth"]
```

Tests import `acme_core` from the **source of truth**, never a synced copy, so they cannot pass
against a stale artifact.

## Files to create/modify

- **Create**: everything in the tree above.
- **Modify**: `frontend/vite.config.js` — add `server.proxy` for `/api` → `http://localhost:8000`,
  no rewrite. That is the only existing file touched.
- **Do not touch**: anything under `infra/`, and all of `bin/`. `bin/start-dev.sh` and
  `bin/proxy-server.js` are unused; `bin/deploy-backend.sh` / `bin/deploy-frontend.sh` are called
  unmodified.

## Commit sequence (`git commit -s`)

1. `chore(backend): add shared-code sync tooling, Makefile and tooling config`
2. `feat(core): add settings, lazy engine and declarative base`
3. `feat(core): add error envelope and the shared app factory`
4. `feat(core): add the full incident-management data model`
5. `feat(core): add Alembic scaffolding and the initial migration`
6. `feat(core): add the incident workflow transition table`
7. `feat(core): add password hashing and JWT token handling`
8. `feat(core): add Principal, role gates and row-level scoping`
9. `feat(core): add shared Pydantic v2 schemas`
10. `feat(auth): add the auth service with register, login, refresh and me`
11. `chore(frontend): proxy /api to the local backend in dev`
12. `feat(auth): add admin user management endpoints`
13. `feat(core): add the idempotent database seed`
14. `feat(auth): support migrate and seed admin invocations`
15. `test: raise backend coverage above the 80% gate`
16. `docs: NOTES.md plus architecture, trade-offs and commands`

Commit 10 adds `requirements.txt` and `function.py` together, making `auth` the first
Terraform-discoverable service. **Deploy to AWS immediately after commit 10**, before building more
— Mangum's event translation and the `/api/auth` prefix are the only things uvicorn cannot verify,
and finding a problem there at commit 10 is cheap.

Seed detail: deterministic `uuid5` natural keys + get-or-create, with incident histories generated by
**replaying real `workflow.py` transitions**, so seeded data is provably reachable through the state
machine and the seed doubles as a workflow integration test.

## Task list

**Phase 0 — tooling foundation**
- [ ] 1. `pyproject.toml` (pytest `pythonpath`, coverage `source` = packages), `requirements-dev.txt`
- [ ] 2. `tools/sync-shared.sh` (mirrors Terraform's glob + `_`/`.` skip, `--delete`, excludes `__pycache__`)
- [ ] 3. `Makefile`: `venv serve migrate seed test cov sync deploy migrate-cloud seed-cloud`
- [ ] 4. `backend/auth/.gitignore` allowlist; verify with `git status --ignored`
- [ ] 5. `make venv` runs clean — **commit 1**

**Phase 1 — `acme_core` foundation**
- [ ] 6. `config.py`: `Settings`, `AWS_LAMBDA_FUNCTION_NAME` host resolution, `sslmode=require`, derived `JWT_SECRET`
- [ ] 7. `db/engine.py`: lazy engine, `pool_size=2`, `pool_pre_ping`, `get_db()`, `dispose_engine()`
- [ ] 8. `db/base.py`: `DeclarativeBase` + naming convention + timestamp/UUID mixins
- [ ] 9. `tests/unit/test_config.py` → **commit 2**
- [ ] 10. `errors.py`: `AppError` hierarchy, flat envelope, handlers, status/code table
- [ ] 11. `logging_config.py`: JSON logs + `request_id` ContextVar
- [ ] 12. `api.py`: `create_app(service_name)`, CORS, `/healthz`, `/readyz`, `prefix=/api/{service}`
- [ ] 13. `tests/unit/test_errors.py` → **commit 3**

**Phase 2 — domain**
- [ ] 14. `models/`: all 11 tables; `floors` uq(building,level), `seats` uq(floor,code), 4 stamped timestamps on `incidents` → **commit 4**
- [ ] 15. `migrations/env.py` + `script.py.mako` + `alembic.ini`; `db/migrate.py` (programmatic Config, `%`→`%%`)
- [ ] 16. Autogenerate `0001_initial`; review the generated DDL by hand
- [ ] 17. `tests/integration/conftest.py` (throwaway DB, savepoint rollback) + `test_migrations.py` → **commit 5**
- [ ] 18. `workflow.py`: `TransitionRule`, `TRANSITIONS`, `actors_for`, `validate_transition`, `allowed_targets`, `STAMP_ON_ENTER`
- [ ] 19. `test_workflow_{rules,required,stamps}.py` — parametrised over every (from,to,role,actor) cell → **commit 6**
- [ ] 20. `security/passwords.py` (bcrypt direct, 72-byte guard) + `security/tokens.py` (`typ` claim)
- [ ] 21. `test_passwords.py`, `test_tokens.py` incl. wrong-`typ` rejection → **commit 7**
- [ ] 22. `security/principal.py` + `scoping.py`; `test_scoping.py` (dialect-compiled SQL, no DB) → **commit 8**
- [ ] 23. `schemas/` — common, auth, facility, incident → **commit 9**

**Phase 3 — the `auth` service**
- [ ] 24. `backend/auth/requirements.txt` + `function.py` (**same commit** — Terraform + handler)
- [ ] 25. `auth_service/{app,dependencies,repository,service,routes}.py`
- [ ] 26. register (@acme.inc gate, always Employee), login, refresh (rotation + reuse detection), me
- [ ] 27. `test_auth_{register,login_refresh,me}.py` → **commit 10**
- [ ] 28. **Deploy checkpoint**: `make deploy && make migrate-cloud`, curl the CloudFront URL
- [ ] 29. `frontend/vite.config.js` — `server.proxy` `/api` → `:8000`, no rewrite → **commit 11**
- [ ] 30. `/users` admin CRUD + `EngineerProfile`; 403 non-admin, 204 delete; `test_admin_users.py` → **commit 12**

**Phase 4 — data, ops, docs**
- [ ] 31. `seed.py`: `uuid5` natural keys, get-or-create, histories replayed through `workflow.py`
- [ ] 32. `test_seed.py` — run twice, assert identical counts (2/6/40/3/1/3/~30) → **commit 13**
- [ ] 33. `admin_actions.py` + `function.py` dispatch + `tools/db.sh` + `/readyz` migrations-pending → **commit 14**
- [ ] 34. Close coverage gaps; turn on `--cov-fail-under=80` → **commit 15**
- [ ] 35. `NOTES.md` + README architecture/trade-offs, incl. that `make serve` supersedes `bin/start-dev.sh` → **commit 16**

**Gates** — do not advance past these:
- After 17: `make migrate` builds 11 tables on local Postgres.
- After 27: all five acceptance curls pass against uvicorn.
- After 28: the same curls pass against CloudFront. *Deploy here, not at the end — Mangum's event translation is the one thing local testing cannot exercise.*
- After 34: `make cov` reports ≥80%.

## Verification

```sh
# 0. one-time
make venv                    # .venv + requirements.txt + requirements-dev.txt

# 1. start the local environment
make serve                   # uvicorn auth_service.app:app --reload --port 8000
                             # expect: "Uvicorn running on http://127.0.0.1:8000"
curl -s localhost:8000/healthz                                   # {"status":"ok"}
(cd frontend && npm install && npm run dev)                      # Vite on :3000, /api -> :8000

# 2. migrations
make migrate                 # alembic upgrade head -> "Running upgrade -> 0001"
psql -h localhost -U postgres -c '\dt'                           # 11 tables

# 3. seed  (re-run to prove idempotency: second run creates 0 rows)
make seed                    # 2 buildings, 6 floors, 40 seats, 7 users, ~30 incidents

# 4. register + login
curl -sX POST localhost:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"demo@acme.inc","password":"S3cret!23","full_name":"Demo"}'        # 201
curl -sX POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"demo@acme.inc","password":"S3cret!23"}'                            # 200 + pair
curl -s localhost:8000/api/auth/me -H "Authorization: Bearer $ACCESS"              # 200 Employee

# negative checks that must hold
#   @gmail.com address           -> 400 validation_error
#   role=admin in register body  -> still creates an Employee
#   /me with the REFRESH token   -> 401 wrong_token_type
#   another user's incident id   -> 404, never 403

# 5. tests with coverage
make cov                     # pytest --cov --cov-report=term-missing --cov-fail-under=80
```

Cloud, after commit 10:

```sh
source ENVIRONMENT.config
make deploy                  # tools/sync-shared.sh && ./bin/deploy-backend.sh aws
make migrate-cloud           # aws lambda invoke --payload '{"action":"migrate"}'
make seed-cloud
curl -s "$(terraform -chdir=infra output -raw website_url)/api/auth/me" -H "Authorization: Bearer $T"
```

## Risks for NOTES.md

- **AWS credentials in `ENVIRONMENT.config` are session tokens and expire.** Cloud steps need a
  re-run of `./bin/setup-participant.sh`. The file is gitignored; never echo or commit it.
- Mangum's Function-URL event translation is not exercised by uvicorn or the test suite — hence the
  deploy checkpoint at commit 10.
- 128 MB Lambda + Aurora `min_capacity = 0.0`: the first cold request can take several seconds.
- `JWT_SECRET` derived from `APP_ID` + `POSTGRES_PASS` because no env var can be added — rotating
  the DB password invalidates all live tokens.
- Deploying from a non-linux-x86_64 host would ship wrong-arch wheels after a *successful*
  `terraform apply`. Deploy from the VDI.
- The docs' env table (`backend/README.md`, `docs/full-stack.md`) claims local `POSTGRES_*` are
  empty; `infra/locals.tf` injects `postgres`/`postgres`/`postgres123`. Terraform wins.
- `bin/start-dev.sh` remains the repo's documented entry point and no longer matches how we run
  things. NOTES.md must say so explicitly, since the rubric scores "runs locally from documented
  commands".
- Frontend has none of the rubric's required libraries (MUI, React Responsive, Router) or test
  tooling, and `eslint.config.js` references two plugins missing from `package.json`. Next task.
