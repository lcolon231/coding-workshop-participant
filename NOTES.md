# NOTES — ACME Facility Incident Management

What was built, what was assumed, what was traded away, what was measured, and what is still open.
The how-to (run, deploy, test, endpoint table) is in the root [`README.md`](README.md); the design
that the code follows is under [`docs/design/`](docs/design/README.md).

## What it is

Employees report facility incidents against a building, floor and seat. Facility Admins triage
them, assign engineers and watch the numbers. Engineers work them through a fixed status machine.
Three Python services (`auth`, `incidents`, `facilities`) share one package, `acme_core`, and one
PostgreSQL schema; a React app in front of them; CloudFront, Lambda and Aurora Serverless v2
underneath in the cloud, uvicorn and a local PostgreSQL on a laptop.

## Assumptions

- **Only ACME staff use it.** Registration accepts `@acme.inc` addresses and creates Employees;
  Engineer and Facility Admin accounts are created by an admin. There is no email verification, so
  the domain check is validation, not authentication (see Security).
- **Admins triage.** An engineer sees only the incidents an admin has assigned to them, not even
  their own reports until then, and cannot assign anyone, themselves included (decision D6 in
  `api.md`, tightened on 2026-09-23). Unassigned work is therefore invisible to engineers and an
  admin hands it out. A pick-up queue would widen row-level scoping, the most security-sensitive
  function in the codebase.
- **The status machine is data.** Every legal move, who may take it and what it requires lives in
  one table in `acme_core/workflow.py`; nothing else branches on a status name.
- **Response targets are constants.** Critical 4 h, High 24 h, Medium 3 d, Low 7 d (D8). Making
  them configurable needs a table and an admin screen that nobody asked for.
- **Notifications are in-app.** The deployment has no mail sender and no push channel, and
  WebSockets would need API Gateway, so a bell polls once a minute (D9).

## Trade-offs

| Chose | Over | Why |
|---|---|---|
| A modular monolith: one shared package vendored into three Lambdas | One Lambda, or three repos | One schema, one auth dependency, one migration history; still one function per service so blast radius and cold starts stay per service |
| `rsync` vendoring at deploy (`make sync`) | A pip-installable package | The Terraform packager zips exactly one directory; symlinks are not followed. `make verify-sync` refuses a stale copy |
| Row-level scoping as one function every query passes through | Per-endpoint checks | A hidden row is filtered out, never refused, so no code path can answer 403 and confirm it exists |
| Role and `is_active` read from the database on every request | Trusting token claims | A demotion or deactivation takes effect on the next request, not when the token expires |
| Offset pagination with a total | Cursors | The UI wants "showing 1 to 25 of 128"; the tables are small |
| Stamped timestamps on `incidents` plus an append-only history table | History only | SLA reporting is a `GROUP BY`, not a window function; the history stays the audit trail |
| The JWT key generated once and kept in the database | Deriving it from the DB password | The Aurora password is a three-word pet name; see Security |
| Poll for notifications | Push | No API Gateway in the Terraform; a one-minute lag on an internal tool costs nothing |
| A bearer token in `X-Acme-Authorization` | The standard header | CloudFront's origin access control overwrites the viewer's `Authorization` header with its own signature; the standard header is still honoured locally |
| Import the web stack at module scope | Lazily in the handler | Lambda's init phase gets a full CPU, the invoke phase a fraction; the lazy form was a workaround for a 128 MB ceiling the functions no longer have |

## Measured numbers

All on 2026-09-23, from CloudWatch `REPORT` lines and `curl` through the CloudFront URL unless
stated. Numbers are what the log said, not what the design hoped.

**Tests**

| Tier | Command | Result |
|---|---|---|
| Backend unit + integration | `make lint && make cov` | 1716 passed, 36 skipped; 99.83 % coverage against a 98 % ratchet; ruff and bandit clean |
| Frontend unit + component | `npm run lint && npm run test:coverage` | 153 passed; 88.1 % statements, 81.4 % branches, 84.9 % functions (floors 80 / 75 / 80) |
| End to end | `npm run test:e2e` | 4 Playwright specs in about 1.4 min against a throwaway backend it starts itself |

**Cloud latency**

| What | Before | After | Change |
|---|---|---|---|
| Cold environment, first request (incidents) | 12.3 s at 512 MB; 45–60 s at 128 MB | 2.9–3.0 s init + 1.8 s first request (includes the first TLS connection to Aurora) | Web stack imported at module scope (PR #24) |
| Warm request, any service | 150–550 ms at 128 MB | 13–95 ms | 128 → 512 MB (PR #23) |
| Login (bcrypt cost 12) | 4–6 s at 128 MB | 1.1 s warm, 2.5 s on the first call | same |
| Memory used | 105–113 MB of 128 | 140–142 MB of 512 | same |
| First request after Aurora paused | 45–60 s, longer than CloudFront's 30 s origin timeout | none: `min_capacity` 0.5 keeps it awake | PR #23, demo day only |
| Readiness probe | – | 0.1 s warm | – |

**Package**: 852 `.py` files and 5 `.pyc` in the deployed zip. The packager installs with pip's
`--no-compile`, which is why the compile had to move into the init phase rather than be avoided.

**Size**: 57 endpoints (auth 12, facilities 23, incidents 22) plus health and docs routes on each;
13 tables; 3 migrations.

## Known gaps

| Gap | Why it stands | What would close it |
|---|---|---|
| No email verification | `@acme.inc` is a format check; anyone can assert an address they do not control | An outbound mail channel and a verification token |
| Cold start of about 5 s per fresh environment | The package ships no bytecode and each service's first request also opens its own TLS connection to Aurora | `compileall --invalidation-mode unchecked-hash` in the packaging step; provisioned concurrency or SnapStart for the demo |
| A page that fires several requests at once can hit several cold environments | Lambda scales by spawning environments; the Reports page fires three requests | Same as above |
| Aurora floor of 0.5 costs about six cents an hour | Set so the demo never waits on a resume | Put `min_capacity` back to 0.0 in `infra/rds.tf` after the demo |
| Burst connection exhaustion | `pool_size=1` per environment and no `reserved_concurrent_executions`; a burst can open more connections than a 0.5-unit cluster likes | A reserved-concurrency cap, or RDS Proxy |
| CloudFront rewrites an S3 404 to `200 index.html` for every origin | Distribution-level `custom_error_response`; the client's content-type guard turns an API 404 that came back as HTML into a clear error | A separate distribution or behaviour-level error handling |
| Session credentials expire | `ENVIRONMENT.config` holds STS tokens | Re-run `./bin/setup-participant.sh` |
| `bin/start-dev.sh` is unused | It hard-exits without LocalStack | `make serve` replaces it (README) |
| Load test not run | Time went to the deploy-day findings above instead (T122 was "if time allows") | One Artillery run against login and the incident list |

## Security notes

- **The Aurora password is a three-word pet name.** `infra/main.tf` configures `random_pet` with
  length 3 and `infra/rds.tf` uses it as the master password: roughly 2³⁰ candidates. It is never
  used as key material. The JWT signing key is 32 random bytes generated on first use and stored in
  `app_secrets`, because no Lambda environment variable can be added without editing Terraform.
  Deriving the key from that password would let anyone who can self-register brute-force it
  offline against a single token.
- **The Function URLs require IAM and only CloudFront may invoke them** (T123, an origin access
  control of type `lambda`). That closes "the URL is public and bypasses CloudFront". It is still
  not an authorization boundary: CloudFront authenticates itself to Lambda, not the user, and the
  same control overwrites the viewer's `Authorization` header, which is why the app sends its token
  in `X-Acme-Authorization`. Every authorization decision stays in the process, on the database
  row, on every request.
- **`@acme.inc` is validation, not authentication.** There is no verification mail. The rule stops
  typos and outsiders from registering by accident; it does not prove anyone owns an address.
  Privilege never follows from the domain: self-registration only ever creates an Employee.
- **Lockout is per account, not per IP.** Through CloudFront the source address is an edge node
  and on the Function URL the caller controls `X-Forwarded-For`, so an IP counter is bypassable by
  construction. Failed attempts count against the account and lock it for a period.
- **Passwords are bcrypt (cost 12); refresh tokens are stored hashed and rotate per use**, with a
  reused token revoking its whole family. Access tokens live 30 minutes; a role change, deactivation,
  password change or logout-all bumps `sessions_valid_from` and invalidates earlier tokens at once.
- **Deletes are soft for users** (incidents keep their reporter) and the API never answers 403 for
  a row outside the caller's scope, only 404, so an id cannot be confirmed by guessing.
- **The seed password is never in the repository.** Locally it comes from `ACME_SEED_PASSWORD`; in
  the cloud from the invoke payload of a synchronous Lambda call that only the participant's IAM
  identity can make, and the seed never resets a password that has since been changed.

## Demo script

About eight minutes. The site is `https://d2vhcnyywug95j.cloudfront.net`; the five demo accounts
share the seed password chosen at `make seed-cloud`.

**Warm-up, two minutes before.** Open the site, sign in as `admin@acme.inc`, open the Reports tab
and the Facilities tab, sign out. Each service now has a warm environment and the database is awake,
so nothing in front of the reviewer waits on a cold start.

1. **Landing page.** Open the site signed out. What it is, the three steps, the roles, the response
   targets. Click *Create an account*: registration accepts an `@acme.inc` address only.
2. **Report an incident as an employee.** Sign in as `employee@acme.inc`. *Report an incident*:
   pick Headquarters, a floor and a seat (the cascade), a category, a title, High priority. Submit.
   The detail page shows it Open, unassigned, with the history's first row.
3. **The admin is told.** In a second window sign in as `admin@acme.inc`. The bell in the top bar
   shows one unread; open it: "Eve Employee reported …". Click through to the incident.
4. **Triage.** On the incident, *Acknowledge and start work*, choosing Hank Vance as the assignee
   (or set the assignee in the triage panel first). Show the admin's landing page: buildings ranked
   by incidents, engineers by workload, the critical list, and *Download CSV* beside the filters.
5. **The engineer is told and works it.** Sign in as `hvac.engineer@acme.inc`. The bell shows the
   assignment; click it. *Block on an external dependency* with a reason, *Unblock*, then *Resolve*
   with a resolution note. An internal note is visible to staff only: add one, then show that the
   employee's window does not list it.
6. **The reporter confirms.** Back as the employee: the incident is Resolved. *Confirm and close*
   it, or *Reopen - not actually fixed* first to show that only the moves the workflow allows are
   ever offered.
7. **Visibility.** As `second.employee@acme.inc`, paste the incident's URL: "Incident not found",
   the same answer as a bad id.
8. **Reports.** As the admin, the Reports tab: counts and backlog age, SLA against the targets, the
   volume chart. Then Users: create an engineer, deactivate a user and show the "open assignments"
   refusal.
9. **Under the hood, if asked.** `/api/auth/docs` through the same URL is the live Swagger page;
   `make cov` and `npm run test:coverage` for the numbers above; the CloudWatch `REPORT` lines for
   the cold-start story.

**Afterwards:** set `min_capacity` back to `0.0` in `infra/rds.tf` and run `make deploy`.
