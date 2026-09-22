# ACME Facility Incident Management — Scaffold + `auth` Vertical Slice

> Revision 4. Findings from three persona reviews (security-auditor, test-engineer, code-reviewer)
> folded in. All decisions closed — see **Decisions closed** at the end.

## Context

The workshop repo contains **no deployable backend service** — only `backend/_examples/`, which
Terraform ignores. We are building ACME Facility Incident Management: employees report facility
issues, facility admins define facilities and assign work, engineers resolve tickets. Evaluation is
`docs/full-stack.md` (Implementation, Design, Code, Testing, Experience; 80%+ backend coverage).

This task delivers the shared package, the full data model, and **one service end to end (`auth`)**.
`backend/incidents/` and `backend/facilities/` are not created yet.

### Environments — LocalStack is not used

| | Local | Cloud |
|---|---|---|
| Backend | uvicorn :8000 | Lambda + Mangum behind CloudFront |
| Database | native Postgres `localhost:5432` | Aurora PG 17.7 |
| Frontend | Vite :3000, `server.proxy` `/api` → `:8000` | S3 + CloudFront |
| Path the app sees | `/api/auth/login` | `/api/auth/login` |

`bin/start-dev.sh` and `bin/proxy-server.js` are unused (`start-dev.sh` hard-exits without
LocalStack). Because the Vite proxy forwards `/api` **unrewritten**, both environments deliver the
same path — routes mount once at `prefix="/api/auth"` and **no path middleware is needed**.

### What the repo dictates (every row verified by reading the file)

| Constraint | Source | Consequence |
|---|---|---|
| Discovery globs `backend/*/requirements.txt`, one level, `_`/`.` skipped | `locals.tf:23-26` | `_shared/` invisible to Terraform |
| `handler` hardcoded `function.handler`, `python3.13` | `locals.tf:56-57` | service needs `function.py` |
| `source_path` is a single-element list | `lambda.tf:20-25` | shared code cannot be a 2nd path → rsync |
| Lambda **128 MB**, no env var can be added | `lambda.tf:11`, `locals.tf:98-114` | memory is *the* risk; **no `JWT_SECRET` var** |
| CloudFront has **no `origin_path`** | `cloudfront.tf` | Lambda receives full `/api/auth/login` |
| Only `/api/<name>*` routes to Lambda | `cloudfront.tf:58` | **root-mounted paths are unreachable in cloud** |
| `custom_error_response` 404 → **200 `/index.html`**, ttl 300 | `cloudfront.tf:42-47` | distribution-level; rewrites API 404s |
| `master_password = random_pet(length=3)` | `rds.tf:15`, `main.tf:9-11` | **DB password ≈ 2³⁰ — never a KDF input** |
| Aurora not public, `min_capacity = 0.0` | `rds.tf` | migrations must run in-Lambda; slow resume |
| CloudFront origin read timeout defaults 30 s | `cloudfront.tf:22-40` | Aurora resume can 504 the first request |
| Zip patterns are anchored regexes | `locals.tf:59` | **nested** `__pycache__` gets zipped |
| CI runs `bandit -r ./backend`, no test job | `.github/workflows/` | tests outside `backend/`; no `assert`, no literal secrets |
| DCO sign-off required | `CONTRIBUTING.md` | `git commit -s` |

### Decisions confirmed with the user

1. Service dirs `auth`, `incidents`, `facilities`; workflow at `/api/incidents/workflow`.
2. Shared code rsynced from `backend/_shared/acme_core/`; copies gitignored.
3. FastAPI + Mangum; uvicorn serves the same `app` locally.
4. No LocalStack; uvicorn + Vite proxy.
5. Cloud migrations via Lambda task-event invoke; IAM is the authz.
6. Flat error envelope `{error, message, details[], request_id}`.

---

## Target design (what the corrections below apply to)

### File tree

```
Makefile                      # venv serve migrate seed test cov sync verify-sync deploy *-cloud
pyproject.toml                # pytest + coverage config only (no build backend)
requirements-dev.txt          # uvicorn, pytest, pytest-cov, pytest-randomly, httpx, freezegun, ruff, bandit
pyrightconfig.json            # exclude backend/*/acme_core so the IDE never resolves into a vendored copy
NOTES.md                      # assumptions, trade-offs, measured numbers, known gaps — a deliverable
tools/sync-shared.sh          # rsync + __pycache__ purge + _build_stamp.py + per-service excludes
tools/db.sh                   # synchronous `aws lambda invoke` wrapper; checks the build stamp first

backend/_shared/
  alembic.ini                 # host-only, sits ABOVE acme_core/ so it is never rsynced or zipped
  acme_core/
    config.py                 # Settings; IN_LAMBDA discriminator; sslmode; never reads DATABASE_URL
    db/ base.py engine.py migrate.py
    errors.py                 # AppError hierarchy, flat envelope, handlers, code->status table
    api.py                    # create_app(service): routes at /api/<service>, docs_url, healthz, readyz
    logging_config.py         # JSON logs, request_id ContextVar, secret denylist
    lambda_entry.py           # classify(event) -> Decision   (pure, unit-tested, inside coverage)
    admin_actions.py          # run_admin_action: migrate | seed | db-current      [auth only]
    seed.py                   # idempotent, additive, password from payload        [auth only]
    workflow.py               # TRANSITIONS table + validators + per-field stamp policy
    scoping.py                # scope_incidents / scope_notes
    security/ passwords.py tokens.py principal.py secret.py
    models/  enums.py user.py facility.py catalog.py incident.py
    schemas/ common.py auth.py facility.py incident.py
    migrations/ env.py script.py.mako versions/0001_initial.py   [auth only]

backend/auth/
  .gitignore                  # /acme_core/ and __pycache__/  (see A12)
  README.md  requirements.txt
  function.py                 # classify -> admin action | lazy Mangum   (see A2)
  auth_service/               # a PACKAGE: deps unzip to the zip root and can shadow top-level names
    app.py dependencies.py routes.py service.py repository.py
  acme_core/                  # rsynced build artifact, gitignored

tests/                        # repo ROOT: bandit scans ./backend, and service dirs get zipped
  conftest.py  factories.py
  unit/  config, engine, errors, logging, api_factory, lambda_dispatch, admin_actions,
         passwords, tokens, workflow_{spec,rules,actors,admin,required,allowed,stamps},
         scoping_sql, schemas_auth, models_metadata
  integration/  conftest, migrations, readyz_migrations, model_constraints, scoping_db,
                route_contract, error_envelope, auth_{register,login,refresh,me},
                admin_users, seed
  e2e/  test_auth_journey.py (real uvicorn)  test_cloud_smoke.py (@cloud, needs API_BASE_URL)
```

### Data model

11 domain tables — `users` · `buildings` · `floors` (uq `building_id+level`) · `seats`
(uq `floor_id+code`) · `categories` · `engineer_profiles` (1:1 users) · `incidents` ·
`incident_notes` · `incident_status_history` · `escalation_requests` · `refresh_tokens` — **plus
`app_secrets`** (S1), so 12 in total. `incidents.building_id` is required; `floor_id`/`seat_id` are
nullable (a lobby has no seat). `incidents` carries `acknowledged_at`, `assigned_at`, `resolved_at`,
`closed_at` alongside the history table, so SLA reporting is a `GROUP BY` rather than a window
function. `users` additionally carries `is_active`, `sessions_valid_from`, `failed_login_count`,
`locked_until` (S7, S8).

### Config and engine

`Settings` reads `POSTGRES_HOST/PORT/NAME/USER/PASS`, builds `postgresql+psycopg://…`, and appends
`sslmode=require` iff `IN_LAMBDA`. Defaults are the local values from `infra/locals.tf`, so host-run
Alembic and the seed work with zero exported env vars. The engine is a module global built on first
use behind a `threading.Lock`, `pool_size=1, max_overflow=0, pool_timeout=5, pool_pre_ping=True,
pool_recycle=280, connect_args={"connect_timeout": 10}` (A4, A5).

### `workflow.py` — one data structure

A frozen `TransitionRule` dataclass and a `TRANSITIONS` tuple of the 7 legal edges, indexed by
`(source, target)`. Rules are written in terms of an `Actor` **relationship**
(`ADMIN` / `ASSIGNED_ENGINEER` / `ANY_ENGINEER` / `REPORTER`), not a role; `actors_for(ctx)` derives
which ones the caller satisfies. `validate_transition` checks **edge → actor → required fields** in
that order, which is what makes "admin bypasses the actor check but *not* required fields" fall out
structurally rather than as a special case. `Closed` is terminal purely because no rule has
`source == CLOSED` — there is no special case for it. A separate per-field `STAMP_ON_ENTER` policy
(A9) sets the four timestamps. `allowed_targets()` drives React button state and is what
`GET /api/incidents/workflow` will serve.

### `scoping.py` — row-level access

`scope_incidents(stmt, principal) -> Select` returns a **new** statement (SQLAlchemy 2.0 selects are
generative), so it chains anywhere in construction. Admin unchanged; Engineer
`or_(assignee_id, reporter_id)`; Employee `reporter_id`. Single-item reads use the same helper then
`.one_or_none()` → `NotFound`, making **404-not-403 structural**: the out-of-scope row is filtered
out, so no code path can emit a 403 that confirms existence. Writes and child resources are covered
by S6.

### Alembic

`migrations/` lives inside `acme_core/` so it rsyncs into the Lambda; `Config` is built
programmatically from the package path (no `alembic.ini` at runtime), with `%` escaped as `%%`
because `Config` is a ConfigParser. `env.py` takes its URL from `get_settings()` with an
`-x url=...` override for tests. `backend/_shared/alembic.ini` exists only for
`alembic revision --autogenerate` and sits above `acme_core/` so it is never carried into a service.

### Error envelope

```json
{ "error": "validation_error",
  "message": "Request validation failed.",
  "details": [{"field": "email", "message": "must be an @acme.inc address"}],
  "request_id": "8f2e-a11c" }
```

`error` is a **stable machine code**, not prose, so the client can switch on `token_expired` vs
`refresh_token_reused` — both 401, very different UX. `details[]` is built from an explicit allowlist
(S3). `request_id` is `context.aws_request_id` in Lambda and a uuid4 under uvicorn. Registered once
in `create_app()`, so all three services share it with no per-service code. Codes: `validation_error`
400 · `unauthenticated` / `token_expired` / `wrong_token_type` / `refresh_token_reused` 401 +
`WWW-Authenticate` · `forbidden` 403 · `not_found` 404 · `conflict` / `invalid_transition` 409 ·
`internal_error` 500 (message scrubbed, `request_id` kept).

### Dependencies — `backend/auth/requirements.txt`

`fastapi` · `mangum` · `pydantic` · `SQLAlchemy>=2.0` · `alembic` · `psycopg[binary]==3.2.3` ·
`PyJWT` · `bcrypt`, all `==` pinned. `uvicorn` is dev-only. `psycopg[binary]==3.2.3` is the identical
pin already proven in `backend/_examples/python-service/requirements.txt`. Deliberately excluded:
`passlib` (broken against bcrypt ≥4.1), `python-jose` (unmaintained, CVEs), `python-multipart`
(login is JSON), `pydantic-settings` (`os.getenv` keeps `Settings` importable with zero env vars).
Wheel risk is low — the VDI is linux-x86_64 on CPython 3.13.15, an exact match for the runtime.

## Security corrections (all three reviews; two are blocking)

**S1 — The JWT secret derivation was a break, not a compromise.** Deriving from `POSTGRES_PASS` is
unsound because that password is a **three-word pet name** (`main.tf:9-11` → `rds.tf:15`), ~2³⁰
candidates against a single unsalted SHA-256. One self-registered account yields a token that acts
as an offline oracle; cracking it mints Admin *and* recovers the Aurora password in cleartext.
**Fix:** an `app_secrets` table in `0001_initial`; on first use `INSERT ... ON CONFLICT DO NOTHING`
a `secrets.token_bytes(32)`, re-select, cache in a module global. Real entropy, no Terraform, shared
correctly across services, and it decouples token validity from the DB password.

**S2 — The seed must not carry credentials.** `seed.py` ships inside the Lambda and
`make seed-cloud` runs it against Aurora. A password literal in committed source is a published
admin credential. **Fix:** seed users get their password from the **invoke payload**
(`{"action":"seed","options":{"admin_password":...}}`), failing loudly if absent; `run_admin_action`
refuses `seed` unless `options["confirm"] == APP_ID`; seeding is strictly additive, never truncating.
Any remaining literal carries `# nosec B105` with a NOTES.md reference, because `bandit -r ./backend`
scans `backend/_shared/` and B105 would otherwise fail CI.

**S3 — Never spread `exc.errors()` into the response.** Pydantic v2 error dicts carry an `input` key
holding the submitted value, so a password failing a length rule is echoed into the response body
*and* the JSON log. **Fix:** build `details[]` from an explicit allowlist — `{"field": ..., "message":
...}` only — rather than relying on `include_input=False` (which I could not verify locally). Add a
key denylist (`password`, `authorization`, `*_token`) in `logging_config.py`, and never log auth
request bodies.

**S4 — `assert` is not an authorization check.** A bare `assert claims["typ"] == "access"` is
stripped under `python -O`, raises `AssertionError` into the 500 handler instead of returning
`401 wrong_token_type`, and trips **bandit B101**, failing CI. Use `if ... raise WrongTokenType()`.

**S5 — Mass assignment.** A `StrictModel` base with `model_config = ConfigDict(extra="forbid")` for
every *request* schema, and request schemas must not contain server-controlled fields at all
(`reporter_id` comes from `principal`, `status` from the workflow). Unit test asserts
`set(Schema.model_fields) & SERVER_CONTROLLED == set()`.

**S6 — Scoping holes beyond the read path.** `scope_incidents` is `Select -> Select`, so `update()`
and `delete()` bypass it structurally, and child resources fetched via `session.get(Note, nid)`
ignore both the parent and the principal. **Fix:** repositories never call `session.get()` on a
child and never issue bare `update()`/`delete()` — every mutation does a scoped
`SELECT ... FOR UPDATE` → `NotFound`, then mutates the ORM object. Children are only reachable via a
join to a scoped parent.

**S7 — Revocation.** Add `iat` to access tokens and `users.sessions_valid_from`; reject when
`iat < sessions_valid_from`, and bump it on logout-all, password change, role change and deactivate.
Take `role` and `is_active` **from the database row, not the claim** — the request already hits the
DB — so a demoted admin loses Admin immediately instead of up to 30 minutes later. Add
`POST /api/auth/logout`. Soft-delete users (`is_active = false`) rather than hard-delete.

**S8 — Login/registration hygiene.** Always run a bcrypt comparison against a module-level dummy
hash on the user-not-found path, so timing does not disclose existence (bcrypt is ~0.5–1 s at
128 MB — an unmissable signal otherwise). `register` returns the same response whether or not the
email exists. Account-based lockout in Postgres (`failed_login_count`, `locked_until`) — **never
IP-based**: on the Function URL the client controls `X-Forwarded-For`, and via CloudFront the source
IP is an edge node, so IP limiting is bypassable by construction.

**S9 — JWT claim hygiene.** Hardcode `algorithms=["HS256"]` as a constant (never derive it from the
token header); set and verify `iss`/`aud`; add `jti`; reject a token whose `typ` claim is **absent**
rather than defaulting; verify `typ` on `/refresh` too, or a stolen 30-minute access token becomes a
7-day one.

**S10 — bcrypt limits.** Reject passwords over **72 bytes** (measured in bytes, not characters — a
30-character emoji/CJK password exceeds it), never silently truncate. Enforce the same bound in the
schema so it surfaces as `validation_error`, not a 500. Password policy: minimum 12 characters.

**S11 — Admin dispatch must fail closed.** The current discriminator is a *negative* test ("anything
not HTTP is an admin command"). It is safe against HTTP today — Function URL payload format 2.0
always populates `requestContext`, and the body never merges into the top-level event — but it is
fail-open by design: any future SQS/EventBridge/DLQ-redrive invocation has no `requestContext`.
Invert to a positive assertion requiring `event["source"] == "acme.admin.v1"` **and** the absence of
every HTTP key **and** an allowlisted action, then raise on anything unrecognised rather than falling
through into Mangum. Invoke **synchronously** so payloads never reach the DLQ.

**S12 — `/readyz` must not serve the revision hash** (it maps to a public git commit) and must
memoise its DB check for 30–60 s, or it becomes an unauthenticated cost-amplification lever against
a scale-to-zero Aurora.

**Worth knowing, not fixable here:** the Function URL is public and bypasses CloudFront, so no edge
control is a security boundary; `@acme.inc` is input validation, not authentication; and if the
workshop IAM policy grants `lambda:InvokeFunction` on `*`, any participant could run `seed` against
another's database. All three go in NOTES.md.

## Architecture & correctness corrections

**A1 — `bin/deploy-backend.sh` never calls the sync.** It is `terraform apply` only, so the repo's
own documented deploy command ships a Lambda with **no `acme_core`** (it is gitignored), and a
sync-once-then-edit cycle deploys silently stale code. **Fix:** `sync-shared.sh` writes
`acme_core/_build_stamp.py` (git sha, dirty flag, timestamp) which `/api/auth/healthz` returns;
`make verify-sync` diffs the copies and is a prerequisite of `make deploy`; `tools/db.sh` checks it
too. *Before committing to rsync, spend 10 minutes testing whether an absolute path entry in
`requirements.txt` lets `pip_requirements = true` do the vendoring — that would delete this whole
bug class rather than detect it.*

**A2 — Memory: the migrate path OOMs as designed.** `Mangum(app)` at module scope imports FastAPI +
all routes + the model graph before the admin branch is reached, then lazily adds alembic — plausibly
125–150 MB against a hard 128. **Fix:** build `_asgi` lazily *inside* `handler`, with
`from mangum import Mangum` moved in too, so an admin invoke never imports the web stack:

```python
_asgi = None

def handler(event=None, context=None):
    decision = classify(event)                 # acme_core.lambda_entry, pure + unit-tested
    if decision.is_admin:
        from acme_core.admin_actions import run_admin_action
        return run_admin_action(decision.action, decision.options)
    if not decision.is_http:
        raise RuntimeError("unrecognised invocation")   # fail closed, no Mangum fall-through
    global _asgi
    if _asgi is None:
        from mangum import Mangum
        from auth_service.app import app
        _asgi = Mangum(app, lifespan="off")
    return _asgi(event, context)
```

Extracting `classify()` into `acme_core/lambda_entry.py` also moves the riskiest logic *inside* the
coverage `source` — as written it sat in `backend/auth/function.py`, outside it, untested. Writing
its test immediately exposes a real bug in the earlier draft: `{}`, `None`, or the console's default
test payload fell through to Mangum and died with an opaque `KeyError`.

Expected RSS is ~100–130 MB at import, not the 70–95 MB previously claimed. **Fallback ladder if
measurement exceeds ~110 MB:** SQLAlchemy Core instead of ORM (−10–15 MB, keeps Alembic and keeps
`scoping.py`, since generative `Select` is Core); then raw psycopg (−25 MB); hand-rolled router only
as a last resort. **Cut SQLAlchemy before FastAPI** — SQLAlchemy is the larger line item, and FastAPI
earns rubric marks for validation, the `details[]` array and OpenAPI.

**A3 — `/healthz`, `/readyz`, `/docs`, `/openapi.json` are unreachable in cloud.** CloudFront routes
only `/api/auth*`; everything else hits S3 and gets rewritten to `index.html` with a **200**. Mount
them under the prefix and pass `docs_url="/api/auth/docs"`, `openapi_url="/api/auth/openapi.json"`.
Four lines, and it makes a live interactive API reference demoable at the CloudFront URL — the
highest points-per-character change available.

**A4 — One environment discriminator, not two.** `IS_LOCAL` is injected only by Terraform and is
unset in a dev shell, so two discriminators can disagree. Use `IN_LAMBDA =
"AWS_LAMBDA_FUNCTION_NAME" in os.environ` for **both** the host rewrite and `sslmode=require`; drop
the `IS_LOCAL` read entirely. Unit-test with `monkeypatch.delenv` on both.

**A5 — Pool sizing, with honest reasoning.** `pool_size=1` (one request per execution environment
makes a second connection waste), `max_overflow=0`, `pool_timeout=5`, `pool_recycle=280` (frozen
containers hold dead TCP), `connect_args={"connect_timeout": 10}`. Guard the lazy engine with a
`threading.Lock` — under uvicorn, `def` endpoints run in a threadpool and can race. NOTES.md states
the real limit plainly: burst blast radius is `concurrency × pool_size`, unbounded without
`reserved_concurrent_executions`, which needs Terraform — an accepted gap, not a solved problem.

**A6 — Endpoints are `def`, not `async def`.** Sync SQLAlchemy inside `async def` blocks the event
loop and serialises every local request. State it once so it is not decided per file.

**A7 — `from __future__ import annotations` is not a memory mitigation** and is a known footgun with
SQLAlchemy `Mapped[]` and Pydantic v2 (unresolvable stringized annotations at class creation).
Removed from the mitigation list; use it stylistically or not at all.

**A8 — Drop `CORSMiddleware`.** Both environments are same-origin, and `lambda.tf:44-51` already sets
CORS at the Function URL layer. A second `Access-Control-Allow-Origin` makes browsers reject the
response outright.

**A9 — `STAMP_ON_ENTER` "only when NULL" is wrong for two of three fields.** It is right for
`acknowledged_at`, but with a `Resolved → In Progress` reopen edge it permanently records the *first*
resolution, so every reopened ticket reports a wrong time-to-resolve — and the brief specifically
wants these stamps for SLA reporting. Make the policy per-field (`FIRST` vs `LATEST`) and add the
reopen case to the stamp tests; it is the one behaviour the table-driven test misses by construction.

**A10 — Ship `seed.py`, `migrations/` and `admin_actions.py` only to `auth`.** Five `--exclude` lines
in `sync-shared.sh` keyed on the target dir. Not about zip bytes (those are free) but blast radius:
three doors to a schema rewrite where one suffices.

**A11 — `sync-shared.sh` must purge `__pycache__` in the target**, not merely exclude it from the
rsync. `pythonpath` includes `backend/auth`, so running the suite creates
`backend/auth/auth_service/__pycache__/`, which the anchored zip patterns do not exclude and which
Python will load in preference to source.

**A12 — The `.gitignore` allowlist is now unnecessary.** It was justified by `pip --target` vendoring
into the service dir — which was `start-dev.sh`'s behaviour, and LocalStack is gone. Terraform's
packager installs into a temp build dir. So the file collapses to `/acme_core/` + `__pycache__/`,
avoiding an allowlist that silently swallows every new file added later. *(Confirm with `unzip -l` on
the artifact at the commit-1 deploy.)* Keep the `auth_service/` package — dependencies unzip to the
zip **root** alongside `function.py`, so a top-level `app.py` genuinely can be shadowed.

**A13 — Aurora resume vs CloudFront's 30 s origin timeout.** Resume from `min_capacity = 0.0` takes
~15–30 s on top of a cold start, so the first demo request through CloudFront can 504 even though the
Lambda succeeds. Code-only mitigations: a warm-up invoke before any demo (`migrate-cloud`/`seed-cloud`
go via `aws lambda invoke`, bypassing the 30 s ceiling), plus an explicit "waking the database" UI
state rather than a generic spinner — which also scores the rubric's loading/failure-feedback bullet.

**A14 — Framing to write down.** Three Lambdas, one bounded context, one schema: a **modular monolith
whose deployment topology is imposed by the platform**. `acme_core` is the module boundary; the Lambda
split is not. Splitting the model graph per service would force cross-service HTTP joins at 128 MB
through CloudFront against a scale-to-zero database — strictly worse. Saying this converts what a
reviewer might read as accidental coupling into a defended decision.

## Testing corrections

**T1 — My coverage reasoning was backwards.** Coverage counts *executed* statements, and SQLAlchemy
declarative bodies and Pydantic models execute at **import**. The unwired incident/facility domain is
~29% of statements at ~95% covered **for free** — it is why 80% is comfortable, not a threat. The real
sinkholes are imperative and mine: `db/engine.py` (whose `get_db()` body never runs because every
integration test overrides it), `seed.py`, `admin_actions.py`, `logging_config.py`, and the
`errors.py` handler **bodies** (registering a handler covers the decorator line, not the body).

**T2 — Omit only what is honestly verified elsewhere:** `*/migrations/*` (proven by executing
upgrade/downgrade) and `backend/*/acme_core/*` (stale rsync copies). **Never** omit `models/`,
`schemas/`, `seed.py`, `db/` — omitting the declarative bulk would be both dishonest and
self-defeating.

**T3 — Ratchet `fail_under` from commit 2**, raising it each commit. Scheduling `--cov-fail-under=80`
at commit 15, as the previous revision did, is the fake-the-number failure mode with a date on it.

**T4 — The unit tier must be DB-free by construction.** An autouse fixture in `tests/unit/`
monkeypatches `sqlalchemy.create_engine` to raise. Otherwise the lazy module-global engine is a
**silent-green** hazard: anything opening its own session (`seed`, `admin_actions`, `/readyz`)
bypasses `dependency_overrides` and connects to the local dev database — a database that
exists and accepts writes. Root `conftest.py` sets the test DB env before any `acme_core` import and
calls `get_settings.cache_clear()`; an autouse assertion checks the engine URL starts with
`acme_test_`.

**T5 — Two integration-fixture bugs to pre-empt.** (a) With `join_transaction_mode="create_savepoint"`,
an app-side `session.rollback()` — e.g. the 409 duplicate-email path — rolls back **to the savepoint**
and destroys fixture data, so **always `commit()` fixture data before issuing the request**.
(b) `expire_on_commit=False` means post-request assertions read the identity map, not the database,
so an UPDATE that never reached PG still passes; provide a `verify_session` fixture bound to the same
connection for every persistence assertion. Also: the outer `begin()` must precede `Session`
construction and the Session must bind to the **Connection**, not the Engine, or the flag is silently
a no-op. Teardown order is `dispose_engine()` → dispose fixture engine → connect to the maintenance
DB → drop, or `DROP DATABASE ... WITH (FORCE)` hangs on your own connection.

**T6 — The workflow table needs a hand-written oracle.** A test that derives legality from
`TRANSITIONS` proves nothing about `TRANSITIONS`. A ~12-line `EXPECTED` frozenset, written by hand
and asserted equal to the table, makes the generated 300-cell cross product (5×5 statuses × 3 roles ×
4 relationships) non-circular. That product then proves Closed-is-terminal and every unlisted edge's
rejection for free. `actors_for` gets its own 12-row oracle. Pin down what an *actor* failure returns
(403 vs 409) — the design never said, and it is different UX. Admin bypass gets an explicit
bypasses-actor / does-**not**-bypass-fields pair over all 7 edges so the halves cannot drift.

**T7 — Replace the signature-introspection test.** Asserting a repository function *takes*
`principal` does not prove it *uses* it; the test reads like coverage while an endpoint returns every
row. Primary evidence is instead an integration test: seed two employees' incidents, `GET` the other
user's id, assert **404 with `{"error": "not_found"}`** — and assert the admin gets 200 for the same
id in the same test, which is the only construction that actually proves 404-not-403. Keep the
dialect-compiled SQL test only as a cheap extra, never as sole evidence (it tests SQLAlchemy's
codegen as much as our rule).

**T8 — Missing high-value tests:** `test_lambda_dispatch` (incl. `{}`/`None` → clean error),
`test_admin_actions`, `test_engine`, `test_api_factory` (prefix is `/api/auth`; **`/healthz` builds no
engine**), `test_readyz_migrations` (downgrade → 503 → upgrade → 200), a `test_route_contract` that
iterates `app.routes` asserting every route is authenticated bar an explicit allowlist, and
`test_error_envelope` parametrised over ~10 error sources asserting the keys are exactly
`{error, message, details, request_id}` — that one test *is* what the rubric means by "consistent
error format". Split `test_auth_refresh` out: rotation, reuse → family revoked, expired ≠ reused,
and **the raw token appears in no column**. Login must assert wrong-password and unknown-email
responses are **byte-identical**. `test_migrations` adds downgrade-to-base and a no-pending-
autogenerate-diff assertion (catches model/migration drift). `test_seed` asserts identical **ids**,
not just counts, and that every generated history validates through `validate_transition`.

**T9 — Config:** `--import-mode=importlib` (same-named files in `unit/` and `integration/`),
`branch = true` (a 90% error-handling target is meaningless without it), `xfail_strict`,
`filterwarnings = ["error"]`, and `pytest-randomly` — the cheapest possible detector for the
shared-fixture bugs in T5. Do **not** chase coverage across the e2e uvicorn subprocess.

**T10 — E2E without a frontend.** No placeholder `cypress/` folder — a grader opens it and it costs
credibility. But zero is avoidable: a real auth journey exists today.
`tests/e2e/test_auth_journey.py` spawns real uvicorn against a real migrated DB and drives
register → login → me → refresh → replay-old-refresh over HTTP, proving the one thing the savepoint
fixture structurally cannot — that data actually commits across connections.
`test_cloud_smoke.py` (skipped unless `API_BASE_URL` is set) runs the same journey against
CloudFront and is the **only** automated proof that Mangum's event translation works. Add a real
`npm test` script (there is none today, so `npm test` fails outright) and one Playwright spec
asserting `POST /api/auth/login` through the Vite proxy returns 400 — which is the only test of the
proxy wiring. Add a CI test job; today `.github/workflows/` runs bandit and `npm audit` only.

---

## Revised commit sequence (`git commit -s`, on a feature branch)

| # | Commit | Notes |
|---|---|---|
| 1 | `chore: tooling, sync script, Makefile` | + **throwaway `auth` stub deployed to AWS**: proves the zip builds, the vendored import resolves at `/var/task`, `/api/auth*` routes, and gives a **baseline `Max Memory Used`**. Ten minutes now vs. discovering it at commit 10. |
| 2 | `feat(core): settings, lazy engine, declarative base` | `IN_LAMBDA` single discriminator; locked engine; `fail_under` ratchet starts |
| 3 | `feat(core): error envelope and app factory` | allowlisted `details[]`; log denylist; no CORSMiddleware; `/api/auth/{healthz,readyz,docs}` |
| 4 | `feat(core): full data model` | 11 tables **+ `app_secrets`** |
| 5 | `feat(core): alembic + initial migration` | integration conftest with the T5 guards |
| 6 | `feat(core): workflow transition table` | oracle first, then the 300-cell product; per-field stamp policy |
| 7 | `feat(core): passwords and JWT` | random secret from `app_secrets`; pinned `alg`; `iss`/`aud`/`jti`/`iat`; byte-limit reject |
| 8 | `feat(core): principal, role gates, row scoping` | scoped writes; no `session.get()` on children |
| 9 | `feat(core): pydantic schemas` | `StrictModel` + server-controlled-field test |
| 10 | `feat(auth): register, login, refresh, me, logout` | `requirements.txt` + `function.py` together; lazy `_asgi`; constant-time login; lockout; **pagination from day one** |
| 11 | **Deploy checkpoint** | record `Max Memory Used`, cold start, Aurora resume in NOTES.md; verify the CloudFront 404 rewrite empirically |
| 12 | `chore(frontend): proxy /api to local backend` | + real `npm test` script |
| 13 | `feat(auth): admin user management` | 404-not-403 pair test; soft delete; sort allowlist |
| 14 | `feat(core): idempotent seed` | password from payload; `confirm == APP_ID` |
| 15 | `feat(auth): migrate/seed admin invocations` | positive marker, fail closed, synchronous invoke |
| 16 | `test: e2e journey + cloud smoke + CI test job` | |
| 17 | `docs: NOTES.md, architecture and trade-offs` | modular-monolith framing; measured numbers; known gaps table |

**Gates:** after 5, `make migrate` builds 12 tables · after 10, all acceptance curls pass against
uvicorn · after 11, the same curls pass against CloudFront **and memory is measured** · after 16,
`make cov` ≥ 80%.

## Verification

```sh
make venv                    # one-time: .venv + requirements + dev requirements
make serve                   # uvicorn :8000 ; curl localhost:8000/api/auth/healthz -> {"status":"ok", "build": ...}
make migrate                 # alembic upgrade head -> 12 tables
make seed                    # re-run -> 0 rows created (idempotent)
curl -sX POST localhost:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"demo@acme.inc","password":"correct-horse-battery","full_name":"Demo"}'   # 201
curl -sX POST localhost:8000/api/auth/login  ... # 200 + token pair
curl -s localhost:8000/api/auth/me -H "Authorization: Bearer $ACCESS"                     # 200 Employee
make cov                     # pytest --cov --cov-fail-under=<current ratchet>
```

Negative checks that must hold: `@gmail.com` → 400 · `role:"admin"` in body → Employee · refresh
token at `/me` → 401 `wrong_token_type` · another user's incident → 404 · wrong password and unknown
email → **byte-identical** responses.

Cloud: `make deploy && make migrate-cloud && make seed-cloud`, then the same curls against the
CloudFront URL, plus `curl -i "$CF_URL/api/auth/nope"` compared against uvicorn to characterise the
404 rewrite.

## Risks for NOTES.md

Aurora password is a 3-word pet name and must never be a KDF input · the Function URL is public and
bypasses CloudFront, so no edge control is a security boundary · `@acme.inc` is validation, not
authentication · burst connection exhaustion needs `reserved_concurrent_executions` (Terraform) and
is an accepted gap · CloudFront rewrites API 404s to `200 index.html` · first cloud request can 504
on Aurora resume · AWS session credentials in `ENVIRONMENT.config` expire · deploying from non-x86-64
ships wrong-arch wheels · the docs' env table contradicts `locals.tf` · `bin/start-dev.sh` is the
repo's documented entry point and we no longer use it.

---

## Decisions closed

**D1 — CloudFront 404 rewrite: keep 404, guard on the client.** `cloudfront.tf:42-47` rewrites every
404 to `200 /index.html` at distribution level. The backend keeps returning 404 with the envelope
exactly as briefed; the API client treats a non-JSON response on an `/api` path as not-found. The
security property was never at risk (out-of-scope and nonexistent are rewritten identically, so
existence is still not confirmed) — only the client's ability to read the envelope. One interceptor,
documented in NOTES.md, plus a note that CloudFront may cache the rewrite for 300 s.

**D2 — Scope stays backend-only.** This task delivers the scaffold, `acme_core`, and the `auth`
slice end to end, as specified. The frontend gap is recorded prominently in NOTES.md — roughly 2.5 of
the rubric's 5 competencies (Design, part of Testing, part of Experience) score on a frontend that
this task does not build — and is planned as the next task with its own budget: Router, MUI, React
Responsive, a login screen, an incident list with loading/success/error states, Vitest + RTL, and
Playwright. The one frontend change here remains `vite.config.js` (the `/api` proxy) plus a real
`npm test` script, since `npm test` currently fails outright.

**Minor design call taken without asking:** a workflow *actor* failure returns **403 `forbidden`**;
an unknown edge returns **409 `invalid_transition`**; a missing required field returns **400
`validation_error`**. The ordering edge → actor → fields is what makes these distinguishable, and
two tests pin the precedence.
