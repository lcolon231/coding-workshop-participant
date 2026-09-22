# Design review findings

Three review passes were run against `plan-before-review.md` using the agent personas from
`agent-skills/agents/`: **security-auditor**, **test-engineer** and **code-reviewer**. This file
consolidates their findings, records which were accepted, and — more usefully — which were
**rejected and why**.

This is a consolidation written from the three reports, not a verbatim transcript. Severity labels
are the reviewers' own. Every claim marked *verified* was independently checked against the repo
files before being accepted.

---

## Blocking findings

### B1 · JWT secret derivation was unsound — VERIFIED, ACCEPTED

*Raised independently by security-auditor (CRIT-2) and code-reviewer (C3).*

The pre-review plan derived `JWT_SECRET = sha256(f"{APP_ID}:{POSTGRES_PASS}")` because no Lambda
environment variable can be added without editing Terraform.

The flaw is entropy, not location:

```hcl
# infra/main.tf:9-11
resource "random_pet" "this" {
  length    = 3
  separator = "-"
}
# infra/rds.tf:15
master_password = random_pet.this.id
```

The Aurora master password is a **three-word pet name** — on the order of 2³⁰ candidates. `APP_ID`
is the participant id, which appears in the Lambda function name, the tfstate bucket name, every
ARN and the resource tags; it is an identifier, not a secret. The derivation formula would be in
committed source.

A JWT signature is verifiable offline. Anyone can self-register (the `@acme.inc` check is a string
comparison), obtain a token, and use it as an oracle to enumerate the pet-name space against
HMAC-SHA256 — minutes on commodity hardware, no rate limit involved. That yields an Admin-minting
key **and** recovers the Aurora master password in cleartext as a side effect.

**Accepted fix:** an `app_secrets` table added in `0001_initial`. On first use,
`INSERT ... ON CONFLICT DO NOTHING` a `secrets.token_bytes(32)`, then re-select (race-safe across
concurrent cold starts) and cache in a module global. 256 bits of real entropy, no Terraform, no env
var, shared correctly across all three services, and it decouples token validity from the DB
password — which also retires the plan's own "rotating the DB password invalidates all live tokens"
risk.

**Alternatives considered and rejected:**
- *Asymmetric keys with the public key in code* — rejected. The private key faces the identical
  storage problem. It only helps when signing and verification live in different services, which is
  not this topology.
- *Derive from something else already in the environment* — rejected. `infra/locals.tf:98-114` lists
  every injected variable; all are either public or the same petname. `MONGO_PASS` is empty
  (DocumentDB is disabled by default). `AWS_SESSION_TOKEN` is high-entropy but rotates, so tokens
  would die mid-session.
- *scrypt-stretch the derivation* — rejected as the primary fix. It raises per-candidate cost by
  ~10⁵ but is a mitigation, not a fix, and costs cold-start CPU on a 128 MB Lambda.

### B2 · Seed credentials would ship to production — ACCEPTED

*security-auditor CRIT-1, reinforced by code-reviewer R4.*

`seed.py` lives in `acme_core/`, which is rsynced into every service directory and zipped into the
Lambda. `run_admin_action("seed")` is production-invocable and the plan's own verification block
runs `make seed-cloud`. Any password literal in `seed.py` is therefore a published admin credential
— readable in the repo, in any fork, and in the workshop's GitHub.

Separately, `bandit` rule **B105** (`hardcoded_password_string`) fires on any string literal assigned
to a name matching `password|passwd|pwd|secret|token`. `backend/_shared/` is inside `./backend`, so
`bandit -r ./backend` scans it and CI goes red.

**Accepted fix:** seeded users take their password from the **invoke payload**
(`{"action":"seed","options":{"admin_password":"..."}}`), which travels over the signed
`lambda:InvokeFunction` API rather than git, and the action fails loudly if it is absent.
`run_admin_action` refuses `seed` unless `options["confirm"] == APP_ID`. Seeding is strictly
additive — never truncating — so a rogue invoke cannot wipe data. Any unavoidable literal carries
`# nosec B105` with a NOTES.md reference.

---

## Findings that would have broken the cloud deliverable

### C1 · The migrate path would OOM — ACCEPTED

*code-reviewer C2.*

The pre-review `function.py` built `Mangum(app)` at module scope, so a `{"action":"migrate"}` invoke
imports FastAPI, all routes and the entire model graph *before* the admin branch is reached, then
lazily adds `alembic` + `Mako` + `MarkupSafe` on top.

The reviewer's RSS estimate — python3.13 baseline 38–42 MB, pydantic+pydantic_core 18–24, FastAPI
stack 12–18, SQLAlchemy 18–25, psycopg[binary] 8–14, bcrypt 3–5 — totals **~100–130 MB at import**
against a hardcoded 128 MB (`infra/lambda.tf:11`). The plan's own "~70–95 MB" was ~30 MB optimistic.
The web path is marginal; the migrate path, at 125–150 MB, is not. And migrate-in-Lambda is the
*only* way to create the Aurora schema, so it would take the whole cloud deliverable with it.

**Accepted fix:** build `_asgi` lazily inside `handler`, with `from mangum import Mangum` moved
inside too, so an admin invoke never imports the web stack (~55–70 MB). Plus a **measurement gate**:
record `Max Memory Used` from the CloudWatch REPORT line at the deploy checkpoint rather than
trusting any estimate.

**Fallback ladder if measurement exceeds ~110 MB:** SQLAlchemy Core instead of ORM (−10–15 MB, keeps
Alembic autogenerate and keeps `scoping.py` working, since generative `Select` is a Core feature);
then raw psycopg (−25 MB); hand-rolled router only as a last resort.

**Explicitly rejected: dropping FastAPI.** SQLAlchemy is the larger line item, and FastAPI earns
rubric marks for validation, the `details[]` array straight from `exc.errors()`, and OpenAPI docs.
Cut SQLAlchemy before FastAPI.

### C2 · Health and docs endpoints unreachable in cloud — VERIFIED, ACCEPTED

*security-auditor MED-3 and code-reviewer R1.*

`infra/cloudfront.tf:58` creates exactly one behaviour per service, `path_pattern = "/api/<name>*"`.
Anything mounted at root — `/healthz`, `/readyz`, `/docs`, `/openapi.json` — falls through to the S3
default behaviour and is then rewritten to `index.html` with a **200**. The "loud, self-diagnosing
failure" for pending migrations silently did not exist in the environment it was designed for.

**Accepted fix:** mount them under the service prefix and pass `docs_url="/api/auth/docs"`,
`openapi_url="/api/auth/openapi.json"`. Four lines — and it makes a live, interactive API reference
demoable at the CloudFront URL, which the reviewer rated the highest points-per-character change
available.

### C3 · CloudFront rewrites every API 404 — VERIFIED, ACCEPTED WITH A CORRECTION

*security-auditor MED-2.*

```hcl
# infra/cloudfront.tf:42-47 — distribution-level, applies to ALL behaviours
custom_error_response {
  error_code            = 404
  error_caching_min_ttl = 300
  response_code         = 200
  response_page_path    = "/index.html"
}
```

**Correction to the reviewer's framing:** the reviewer implied this undoes the 404-not-403 security
property. It does not. Out-of-scope and nonexistent rows both return 404, so both are rewritten
identically — existence is still not confirmed. What breaks is *functional*: the client receives HTML
with a 200 instead of the error envelope.

**Decision taken:** keep returning 404 with the envelope, and have the API client treat a non-JSON
response on an `/api` path as not-found. The reviewer's suggestion of remapping to 403 was rejected
because it contradicts the explicit brief requirement ("Return 404, not 403, for out-of-scope reads")
for a problem that is presentational, not security-relevant.

---

## Correctness findings

| # | Finding | Status |
|---|---|---|
| A1 | `bin/deploy-backend.sh` is `terraform apply` only and never calls the sync, so the repo's own documented deploy command ships a Lambda with **no `acme_core`** (it is gitignored), and a sync-once-then-edit cycle deploys silently stale code. `git clean -xfd` before a demo removes it with no warning. | **Accepted** — `sync-shared.sh` writes `_build_stamp.py` (git sha, dirty flag, timestamp) returned by `/api/auth/healthz`; `make verify-sync` diffs the copies and gates `make deploy`. |
| A2 | `STAMP_ON_ENTER` "set only when NULL" is right for `acknowledged_at` but wrong for `resolved_at`/`closed_at`: with a `Resolved → In Progress` reopen edge it permanently records the *first* resolution, so every reopened ticket reports a wrong time-to-resolve — exactly what the brief wants these stamps for. | **Accepted** — per-field FIRST/LATEST policy, plus the reopen case added to the stamp tests. |
| A3 | Two environment discriminators (`IS_LOCAL` and `AWS_LAMBDA_FUNCTION_NAME`) can disagree in a dev shell, where `IS_LOCAL` is unset. | **Accepted** — single `IN_LAMBDA` discriminator for both the host rewrite and `sslmode`. |
| A4 | A bare `assert claims["typ"] == "access"` is stripped under `python -O`, raises `AssertionError` into the 500 handler instead of returning `401 wrong_token_type`, and trips **bandit B101**, failing CI. | **Accepted** — explicit `if ... raise`. |
| A5 | `from __future__ import annotations` was listed as a memory mitigation. It is not one, and stringized annotations are a known footgun with SQLAlchemy `Mapped[]` and Pydantic v2. | **Accepted** — removed from the mitigation list. |
| A6 | `pool_size=2, max_overflow=0` reasoning conflated Lambda's one-request-per-environment property with memory, and the real blast radius is `concurrency × pool_size` — unbounded without `reserved_concurrent_executions`, against an Aurora at 0.5 ACU (~189 connections). | **Accepted** — `pool_size=1`, `pool_timeout=5`, `connect_timeout=10`, `threading.Lock` on engine init, and an honest NOTES.md entry that burst exhaustion is an accepted gap needing Terraform. |
| A7 | A duplicate `Access-Control-Allow-Origin` — FastAPI's `CORSMiddleware` plus the Function URL's own CORS config (`lambda.tf:44-51`) — makes browsers reject the response outright. Both environments are same-origin anyway. | **Accepted** — drop `CORSMiddleware`. |
| A8 | `sync-shared.sh` excluded `__pycache__` from the rsync but did not purge it from the target. `pythonpath` includes `backend/auth`, so running the suite creates `backend/auth/auth_service/__pycache__/`, which the anchored zip patterns do not exclude. | **Accepted** — purge in the target before rsync. |
| A9 | The admin dispatch discriminator is fail-open: "anything not HTTP is an admin command". Safe against HTTP today (Function URL payload format 2.0 always populates `requestContext`, and the body never merges into the top-level event), but any future SQS/EventBridge/DLQ-redrive invocation has no `requestContext`. An unrecognised action also fell through into Mangum and died with an opaque `KeyError`. | **Accepted** — positive marker `source == "acme.admin.v1"`, absence of every HTTP key, allowlisted action, and raise on anything unrecognised. |
| A10 | `seed.py`, `migrations/` and `admin_actions.py` ship to all three services — three doors to a schema rewrite where one suffices. | **Accepted** — per-service `--exclude` list in the sync script. |
| A11 | The `.gitignore` allowlist (`*` plus negations) was justified by `pip --target` vendoring into the service dir — which was `start-dev.sh`'s behaviour, and LocalStack is now dropped. An allowlist silently swallows every new file added later. | **Accepted** — collapses to `/acme_core/` + `__pycache__/`. The `auth_service/` package is **kept**, but for the correct reason: dependencies unzip to the zip *root* alongside `function.py`, so a top-level `app.py` genuinely can be shadowed. |
| A12 | Aurora resume from `min_capacity = 0.0` takes ~15–30 s, on top of a cold start, against CloudFront's default 30 s origin read timeout — so the first demo request can 504 even though the Lambda succeeds. | **Accepted** — warm-up invoke before demos (admin invokes bypass CloudFront), plus an explicit "waking the database" UI state. |

---

## Security findings (non-blocking)

| # | Finding | Status |
|---|---|---|
| S1 | `exc.errors()` in Pydantic v2 carries an `input` key holding the submitted value — so a password failing a length rule is echoed into the response body *and* the JSON log, permanently, in CloudWatch. | **Accepted**, and hardened beyond the suggestion: `details[]` is built from an explicit `{field, message}` allowlist rather than relying on `include_input=False`, which could not be verified locally (pydantic is not installed). Safe either way. |
| S2 | Mass assignment is unaddressed outside `register`. `Incident(**payload.model_dump())` lets a client set `reporter_id`, `status` or `role`. | **Accepted** — `StrictModel` base with `extra="forbid"`; request schemas omit server-controlled fields entirely; a test asserts the intersection is empty. |
| S3 | `scope_incidents` is `Select -> Select`, so `update()`/`delete()` bypass it structurally; and `session.get(Note, nid)` on a child ignores both parent and principal (IDOR). | **Accepted** — no bare `update()`/`delete()` in repositories; mutations do a scoped `SELECT ... FOR UPDATE` first; children only reachable via a join to a scoped parent. |
| S4 | No revocation path: no logout, and access tokens outlive role changes and deletion by up to 30 minutes. A demoted admin keeps Admin. | **Accepted** — `iat` + `users.sessions_valid_from`; `role`/`is_active` read from the DB row, not the claim; `POST /logout`; soft-delete. |
| S5 | No rate limiting on a public, `authorization_type = "NONE"` Function URL, with open self-registration. bcrypt at ~0.5–1 s per attempt is also a financial-DoS lever. | **Accepted** — account-based lockout. Explicitly **not IP-based**: the client controls `X-Forwarded-For` on the Function URL, and via CloudFront the source IP is an edge node, so IP limiting is bypassable by construction and would give false confidence. |
| S6 | User enumeration: `register` returns 409 vs 201; and `login` skipping bcrypt on user-not-found is a ~0.5 s timing oracle. | **Accepted** — identical register responses; constant-time login against a module-level dummy hash. |
| S7 | JWT claim hygiene: pin `algorithms=["HS256"]` as a constant (never derive from the token header), add `iss`/`aud`/`jti`/`iat`, reject a token whose `typ` is **absent** rather than defaulting, and verify `typ` on `/refresh` too. | **Accepted.** |
| S8 | "72-byte truncation guard" is ambiguous — truncating silently means `"A"*72 + anything` all authenticate identically. The limit is also in **bytes**, so a 30-character emoji/CJK password exceeds it. | **Accepted** — reject, never truncate; measured in bytes; enforced in the schema so it is a 400 not a 500. |
| S9 | No password policy stated. | **Accepted** — minimum 12 characters, maximum 72 bytes. Composition rules deliberately omitted (they push users toward `Password1!`). |
| S10 | Sort/filter params: `text(f"{col} {dir}")` is injectable and `getattr(Model, param)` allows attribute traversal. | **Accepted** — literal allowlist dict; `Literal[...]` query params. |
| S11 | `/readyz` returning the Alembic revision maps to a public git commit, and its unauthenticated DB round-trip wakes a scale-to-zero Aurora. | **Accepted** — boolean only, memoised 30–60 s. |
| S12 | `allow_origins = ["*"]` is **not** the vulnerability it appears to be, because `allow_credentials = false` means no ambient credentials are sent. The real cost is being pushed toward bearer tokens in `localStorage`, where any XSS is total account takeover including the 7-day refresh token. Since both environments are same-origin, an HttpOnly `SameSite=Strict` cookie scoped to `/api/auth/refresh` is viable. | **Noted, deferred** to the frontend task. Recorded because the reasoning is right and the option is real. |

---

## Testing findings

| # | Finding | Status |
|---|---|---|
| T1 | **The plan's coverage reasoning was backwards.** It worried the unwired incident/facility domain would drag coverage down. Coverage counts *executed* statements, and SQLAlchemy declarative bodies and Pydantic models execute at **import** — so that ~29% of statements is ~95% covered for free. It is why 80% is comfortable, not a threat to it. | **Accepted.** The real sinkholes are imperative: `db/engine.py` (whose `get_db()` body never runs because every integration test overrides it), `seed.py`, `admin_actions.py`, `logging_config.py`, and the `errors.py` handler *bodies* — registering a handler covers the decorator line, not the body. |
| T2 | `function.py` sits outside the coverage `source`, so the riskiest logic in the codebase was both untested and unmeasured. | **Accepted** — `classify()` extracted to `acme_core/lambda_entry.py` as a pure function. Writing its test immediately exposed a real bug: `{}`, `None`, or the AWS console's default test payload fell through to Mangum and died with an opaque `KeyError`. |
| T3 | Scheduling `--cov-fail-under=80` at the final commit *is* the fake-the-number failure mode with a date on it. | **Accepted** — ratchet from commit 2, raising each commit. |
| T4 | **Silent-green hazard.** Anything opening its own session (`seed`, `admin_actions`, `/readyz`) bypasses `dependency_overrides[get_db]` and connects to the local dev database — a database that exists and accepts writes. Tests pass while mutating the dev DB. | **Accepted** — root `conftest.py` sets the test DB before any `acme_core` import and calls `get_settings.cache_clear()`; an autouse assertion checks the engine URL starts with `acme_test_`; and an autouse fixture in `tests/unit/` monkeypatches `create_engine` to raise, making "the unit tier is DB-free" an enforced property rather than a claim. |
| T5 | **Confusing-red hazard.** With `join_transaction_mode="create_savepoint"`, an app-side `session.rollback()` — e.g. the 409 duplicate-email path — rolls back *to the savepoint* and destroys fixture data. | **Accepted** — always `commit()` fixture data before issuing the request, stated as a comment in the fixture. |
| T6 | `expire_on_commit=False` means post-request assertions read the identity map, not the database, so an UPDATE that never reached PG still passes. | **Accepted** — a `verify_session` fixture bound to the same connection for every persistence assertion. |
| T7 | Fixture mechanics: the outer `begin()` must precede `Session` construction and the Session must bind to the **Connection**, not the Engine, or the flag is silently a no-op. `DROP DATABASE ... WITH (FORCE)` cannot terminate your own connection, so teardown order matters. Stale `acme_test_%` databases leak on SIGKILL. | **Accepted.** |
| T8 | A workflow test that derives legality from `TRANSITIONS` proves nothing about `TRANSITIONS`. | **Accepted** — a ~12-line hand-written `EXPECTED` oracle asserted equal to the table makes the generated 300-cell cross product (5×5 statuses × 3 roles × 4 relationships) non-circular. That product then proves Closed-is-terminal and every unlisted edge's rejection for free. `actors_for` gets its own 12-row oracle. |
| T9 | FastAPI's default validation status is **422**, but the plan maps to 400 — and `/docs` will still advertise 422 unless the OpenAPI responses are patched. A grader reading the docs page sees the mismatch. | **Accepted.** |
| T10 | Missing tests, especially on error paths where the rubric wants 90%: `test_lambda_dispatch`, `test_admin_actions`, `test_engine`, `test_api_factory` (including that `/healthz` builds no engine), `test_readyz_migrations`, `test_route_contract` (every route authenticated bar an allowlist), `test_error_envelope` (keys are exactly `{error, message, details, request_id}` — that one test *is* what the rubric means by "consistent error format"). Refresh needs its own file: rotation, reuse → family revoked, expired ≠ reused, and the raw token appearing in no column. Login must assert wrong-password and unknown-email responses are **byte-identical**. | **Accepted.** |
| T11 | `test_migrations` should add downgrade-to-base and a no-pending-autogenerate-diff assertion, which catches model/migration drift — the classic way this design rots. | **Accepted.** |
| T12 | E2E: no placeholder `cypress/` folder — a grader opens it, finds nothing, and it costs credibility. But zero is avoidable, because a critical path exists today. | **Accepted** — `test_auth_journey.py` drives a real uvicorn over HTTP, proving the one thing the savepoint fixture structurally cannot (that data actually commits across connections); `test_cloud_smoke.py` is the only automated proof that Mangum's event translation works. Plus a real `npm test` script, since `npm test` fails outright today, and a CI test job, since `.github/workflows/` runs bandit and `npm audit` only. |
| T13 | Config: `--import-mode=importlib` (same-named files in `unit/` and `integration/`), `branch = true` (a 90% error-handling target is meaningless without it), `pytest-randomly` as the cheapest detector for the shared-fixture bugs above. Do not chase coverage across the e2e subprocess boundary. | **Accepted.** |

---

## Rejected suggestions

Recorded because the reasoning matters as much as the decisions.

| Suggestion | Source | Why rejected |
|---|---|---|
| **Remap not-found from 404 to 403** so the envelope survives CloudFront. | security-auditor MED-2 | The brief explicitly requires "404, not 403, for out-of-scope reads". The security property survives the rewrite intact; only presentation breaks. Solved on the client instead. |
| **Drop refresh-token reuse detection** to free budget for the frontend. | code-reviewer O4 | The brief asks for refresh handling with rotation, and reuse detection is what makes rotation meaningful. Kept, with the budget tension noted instead. |
| **Keep the repository signature-introspection test.** | plan (pre-review) | Rejected by *two* reviewers independently: asserting a function *takes* `principal` does not prove it *uses* it. A function can accept it, never reference it, and the test stays green while the endpoint returns every row — worse than no test, because it reads like coverage. Replaced with a real integration test. |
| **Dialect-compiled SQL assertions as primary scoping evidence.** | plan (pre-review) | Demoted to a cheap extra. It tests SQLAlchemy's codegen as much as our rule, and changes between minor versions. Primary evidence is now an integration test asserting a non-admin gets 404 and an admin gets 200 for the *same* id — the only construction that actually proves 404-not-403. |
| **Write ~400 test cases across 20 unit files.** | test-engineer | Partially adopted. The structural items (the oracle, the engine guard, the fixture rules, the missing error-path tests) are in; the long tail is trimmed. This is a scaffold plus one service, not a reference test suite. |
| **`from __future__ import annotations` everywhere as a memory mitigation.** | plan (pre-review) | It saves essentially nothing at runtime and is a footgun with `Mapped[]` and Pydantic v2. Removed. |
| **Hand-rolled router instead of FastAPI** to save memory. | code-reviewer C2 (as last rung) | Kept as the last resort only. SQLAlchemy is the larger line item and FastAPI earns rubric marks; cut SQLAlchemy first. |
| **Re-budget commits from backend to frontend.** | code-reviewer rubric section | Surfaced to the user as an explicit decision; the user chose to keep this task backend-only as briefed. The scoring risk is recorded in the plan's NOTES.md section as a deliberate trade-off. |

---

## Items still unverified

Empirical checks scheduled into commit 1 and the deploy gate. These are *unverified*, not
*undesigned* — each has a designed outcome either way.

1. **Whether an absolute path entry in `requirements.txt` lets Terraform's `pip_requirements = true`
   do the vendoring.** If it works it deletes the entire rsync/stale-copy bug class rather than
   detecting it. ~10 minutes to test. Could not be checked here because `infra/.terraform` is not
   initialised.
2. **Actual `Max Memory Used`** against the 128 MB ceiling. The fallback ladder is designed; which
   rung is needed depends on the measurement.
3. **`unzip -l` on the built artifact**, to confirm nothing pip-installs into the service directory
   now that LocalStack is dropped — this is what justifies simplifying the `.gitignore`.
4. **How the CloudFront 404 rewrite behaves in practice**, including whether
   `error_caching_min_ttl = 300` actually caches against a CachingDisabled policy.
5. **Whether `exc.errors()` accepts `include_input=False`** in the pinned Pydantic version. The fix
   was designed not to depend on it.
