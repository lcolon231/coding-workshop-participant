# Coding Workshop

The goal of this coding workshop is to enable and assess the hands-on skills
of participants through development of a practical technical solution that
solves a theoretical business problem.

## The solution: ACME Facility Incident Management

Employees report facility incidents against a building, floor and seat; Facility Admins triage,
assign engineers and read the reports; Engineers work each incident through a fixed status machine.
Delivered as three Python services behind CloudFront and one React app, on AWS Lambda and Aurora
Serverless v2. This section is the operator's guide. Assumptions, trade-offs, measured numbers,
known gaps, security notes and the demo script are in [`NOTES.md`](NOTES.md); the design the code
follows is under [`docs/design/`](docs/design/README.md).

### Architecture

A **modular monolith**: one shared package, `backend/_shared/acme_core` (models, schemas, the
workflow table, row-level scoping, auth dependencies, migrations), used by three thin services that
each own their routes, service rules and queries:

| Service | Prefix | Owns |
|---|---|---|
| `auth` | `/api/auth` | Registration, login, token refresh and rotation, `/me`, user administration, and the only door to migrations and seeding |
| `incidents` | `/api/incidents` | Incidents, the status workflow, notes, escalations, notifications, reports |
| `facilities` | `/api/facilities` | Buildings, floors, seats, categories, engineer profiles |

They share one PostgreSQL schema (13 tables, Alembic migrations) and one JWT signing key kept in
the database. In the cloud each service is one Lambda behind a Function URL that only the CloudFront
distribution may invoke; the React build is served from S3 through the same distribution, so the
browser sees one origin. Locally, `make serve` runs all three in one uvicorn process and Vite proxies
`/api` to it, so paths are identical in both places. `make deploy` copies `acme_core` into each
service directory before Terraform zips it (`make sync`), and refuses a stale copy (`make verify-sync`).

Diagrams: [`docs/design/diagrams/`](docs/design/diagrams/) (architecture, data model, workflow,
security), each as Mermaid source and as a self-contained HTML page.

### Run it locally

Prerequisites: Python 3.13, Node 24 and a local PostgreSQL (`bin/setup-environment.sh` installs
one; CI and Aurora run PostgreSQL 17, a laptop may run 18). Then, from the repository root:

```sh
make venv                                   # .venv with runtime and dev dependencies
make migrate                                # apply the migrations to the local database
ACME_SEED_PASSWORD='choose-12-plus-chars' make seed   # five demo accounts, buildings, categories
make serve                                  # every service on http://localhost:8000
```

and in a second terminal:

```sh
cd frontend && npm ci && npm run dev        # http://localhost:3000, proxies /api to :8000
```

`make serve` **supersedes `bin/start-dev.sh`**, which hard-exits when LocalStack is absent; nothing
here uses LocalStack. `make serve SERVICE=incidents` runs one service alone, the shape its Lambda
has. The merged Swagger page for all three services is `http://localhost:8000/api/docs` (local
only; CloudFront routes nothing at that path). `make help` lists every target.

Demo accounts, all with the seed password: `admin@acme.inc` (Facility Admin), `hvac.engineer@acme.inc`
and `it.engineer@acme.inc` (Engineers), `employee@acme.inc` and `second.employee@acme.inc`.

### Deploy it

```sh
./bin/setup-participant.sh && source ENVIRONMENT.config   # temporary AWS credentials; re-run when they expire
make deploy                                 # vendor acme_core, verify, terraform apply (backend + CloudFront + Aurora)
make migrate-cloud                          # run the migrations inside the deployed auth Lambda
ADMIN_PASSWORD='choose-12-plus-chars' make seed-cloud    # demo data; the password never touches the repo
./bin/deploy-frontend.sh aws                # build, upload to S3, invalidate CloudFront
```

The first invoke after a quiet spell may time out while Aurora resumes; run it again. `make
migrate-cloud` and `make seed-cloud` are synchronous invokes of the auth Lambda with an allowlisted
admin payload, authorised by the caller's IAM identity, because Aurora is not reachable from outside
the VPC. `./tools/db.sh db-current` prints the revision the cloud database is stamped with.

### API reference

Every route is documented live: `/api/auth/docs`, `/api/incidents/docs` and `/api/facilities/docs`
(Swagger, with `openapi.json` beside each) work both locally and through the CloudFront URL. The
contract behind them, with the rules per endpoint and the decisions taken, is
[`docs/design/api.md`](docs/design/api.md). Authenticated routes take the access token in
`X-Acme-Authorization: Bearer <token>` (the browser's header, because CloudFront overwrites
`Authorization` with its own signature) or in `Authorization` (curl, Swagger, tests). Roles:
**ANY** signed-in user, **ADM** Facility Admin, **ENG** Engineer.

| Service | Method | Path | Roles | What |
|---|---|---|---|---|
| auth | POST | `/api/auth/register` | public | Self-register an Employee with an `@acme.inc` address (202 either way) |
| auth | POST | `/api/auth/login` | public | Token pair |
| auth | POST | `/api/auth/refresh` | public | Rotate the refresh token; reuse revokes the family |
| auth | POST | `/api/auth/logout`, `/api/auth/logout-all` | public / ANY | Revoke one refresh token / every session |
| auth | GET | `/api/auth/me` | ANY | The caller, with the engineer profile when there is one |
| auth | POST | `/api/auth/me/password` | ANY | Change password; ends other sessions |
| auth | GET, POST | `/api/auth/users` | ADM | List and filter users; create an Engineer or Admin |
| auth | GET, PUT, DELETE | `/api/auth/users/{user_id}` | ADM | Read, edit (role, specialty, profile fields), deactivate |
| facilities | GET, POST | `/api/facilities/buildings` | ANY / ADM | Buildings; admins may include retired ones |
| facilities | GET, PUT, DELETE | `/api/facilities/buildings/{id}` | ANY / ADM | One building; delete is 409 while referenced |
| facilities | GET | `/api/facilities/buildings/{id}/floors` | ANY | A building's floors |
| facilities | POST · GET, PUT, DELETE | `/api/facilities/floors` · `/floors/{id}` | ADM / ANY | Floors, unique per building and level |
| facilities | GET | `/api/facilities/floors/{id}/seats` | ANY | A floor's seats |
| facilities | POST · GET, PUT, DELETE | `/api/facilities/seats` · `/seats/{id}` | ADM / ANY | Seats, unique per floor and code |
| facilities | GET, POST · GET, PUT, DELETE | `/api/facilities/categories` · `/categories/{id}` | ANY / ADM | Two-level category tree |
| facilities | GET · GET, PUT | `/api/facilities/engineers` · `/engineers/{user_id}` | ADM | Engineer profiles with open-assignment counts |
| incidents | POST, GET | `/api/incidents` | ANY (scoped) | Report; list with filters (incl. `overdue`), sort (incl. `due_at`), paging and date range; every row carries `due_at` and `sla_state` |
| incidents | GET, PUT, DELETE | `/api/incidents/{id}` | ANY (scoped) / ADM delete | Detail with the caller's allowed transitions; partial edit |
| incidents | POST | `/api/incidents/{id}/transition` | ANY (workflow rules) | The only way status changes |
| incidents | GET | `/api/incidents/{id}/history` | ANY (scoped) | Append-only status history |
| incidents | GET, POST | `/api/incidents/{id}/notes` | ANY (scoped) | Notes; internal ones for staff only |
| incidents | GET, POST | `/api/incidents/{id}/escalations` | ANY (scoped) / reporter or assignee | Request a priority raise |
| incidents | GET · POST | `/api/incidents/escalations` · `/escalations/{id}/decision` | ADM | The queue; approve or reject |
| incidents | GET | `/api/incidents/workflow` | ANY | The whole state machine |
| incidents | GET · POST · POST | `/api/incidents/notifications` · `/read-all` · `/{id}/read` | ANY (own rows) | In-app notifications with the unread count |
| incidents | GET | `/api/incidents/reports/{summary,sla,volume,buildings,engineers}` | ADM | Reports over a date range |

Out-of-scope rows answer **404, never 403**, so an id cannot be confirmed by guessing. Every list
returns `{items, total, limit, offset}`; every error `{error, message, details[], request_id}`.

### Tests

| Tier | Command | What it proves | Latest result |
|---|---|---|---|
| Backend lint | `make lint` | ruff and bandit, exactly what CI runs | clean |
| Backend unit + integration | `make cov` | Every endpoint for every role against a throwaway PostgreSQL database it creates, migrates and drops; the 404-not-403 pair on the same id; every workflow edge with its history rows and stamps; model-versus-migration drift | 1741 passed, 99.86 % coverage, ratchet 98 % |
| Frontend lint | `cd frontend && npm run lint` | ESLint | clean |
| Frontend unit + component | `cd frontend && npm test` / `npm run test:coverage` | Vitest with React Testing Library against a stubbed API | 241 passed; 92.7 % statements, 84.3 % branches, 90.9 % functions (floors 90 / 80 / 88) |
| End to end | `cd frontend && npm run test:e2e` | Playwright drives the real UI against a real backend it starts on its own throwaway database: register, report, assign, block, resolve, close, and the stranger who gets 404 | 4 passed in about 1.5 min |

Results above were measured on 2026-09-24. Both coverage commands write an HTML report next to the
code they measure: `backend/coverage/index.html` and `frontend/coverage/index.html`.

CI runs the first four on every push and pull request (`.github/workflows/python.tests.yml`,
`react.tests.yml`) with a PostgreSQL 17 service container, and uploads both folders as the
`backend-coverage` and `frontend-coverage` artifacts. Known gaps per tier: the end-to-end run needs
a local PostgreSQL and `.venv`, so it is not in CI, and it times out if started while `make cov` is
saturating the machine; the unit tier cannot see what only a server shows, so uniqueness and cascade
rules are asserted in the integration tier; no load test was run (see `NOTES.md`).

### Security

The findings and what was done about them are in [`NOTES.md`](NOTES.md#security-notes): the
pet-name database password and why the JWT key is not derived from it, the IAM-only Function URLs
behind CloudFront and why that is still not an authorization boundary, `@acme.inc` as validation
rather than authentication, per-account lockout, hashed rotating refresh tokens, and soft deletes.

---

## Getting Started

Navigate to [Coding Workshop - Main Guide](./docs/README.md) to get started.

## Coding Workshop Example

Coding workshop organizer(s) will provide instructions to follow by email. Here
below is a real example of requirements and expectations for participant(s):

### Requirements: Business Problem

Our company ACME Inc. is going through a massive organizational transformation
to become a more data-driven organization. Information about teams structure
and performance is currently scattered across multiple systems, making it
difficult to get a comprehensive view of team dynamics and achievements.

We are struggling to answer simple questions like:

* Who are the members of each team?
* Where are the teams located?
* What are the key achievements of each team on a monthly basis?
* How many teams have team leader not co-located with team members?
* How many teams have team leader as a non-direct staff?
* How many teams have non-direct staff to employees ratio above 20%?
* How many teams are reporting to an organization leader?

### Requirements: Technical Solution

As part of this transformation, we are looking to build a centralized team
management tool that will allow us to track team members, team locations,
monthly team achievements, as well as individual-level and team-level metadata.
Initial focus is to provide a self-service capability without any integrations
with other tools such as Employee Directory, Project Tracking, or Performance
Management.

The technical solution involves developing a stand-alone web application using
modern technologies. The application will have the following features:

* User authentication and authorization
* Role-based access control
* CRUD operations for individuals, teams, achievements and metadata
* Search and filter functionality
* Responsive design for mobile and desktop usage

### Requirements: Technology Stack

The following technologies are required to build the application:

* Frontend: HTML, CSS, React.js with React Responsive and Material UI Components
* Backend: Python
* Database: PostgreSQL

The following technologies are good to know, as they are used to manage and
deploy code:

* Version Control: Git, GitHub
* Infrastructure: Terraform
* Deployment Mode: Shell Scripts
* Deployment Target: AWS Serverless (e.g. S3, CloudFront, Lambda, RDS)

### Expectations: Value-Based Outcomes

By the end of the workshop, participants will have developed a functional
web application that meets the requirements outlined above. The application
will be deployed to a cloud environment and accessible via a web browser.
Participants will also gain hands-on experience with modern web development
technologies and best practices.

## Contributing

See the [CONTRIBUTING](./CONTRIBUTING.md) resource for more details.

## License

This library is licensed under the MIT-0 License.
See the [LICENSE](./LICENSE) resource for more details.

## Roadmap

See the
[open issues](https://github.com/citi/coding-workshop-participant/issues)
for a list of proposed roadmap features (and known issues).

## Security

See the
[Security Issue Notifications](./CONTRIBUTING.md#security-issue-notifications)
resource for more details.

## Authors

The following people have contributed to this workshop:

* Colin Heilman - [@heilmancs](https://github.com/heilmancs)
* Eugene Istrati - [@eistrati](https://github.com/eistrati)
* Isaiah Cornelius Smith - [@corneliusmith](https://github.com/corneliusmith)
* Juan Arevalo - [@jparevalo27](https://github.com/jparevalo27)
* Michael Annucci - [@michael-annucci](https://github.com/michael-annucci)

## Feedback

We'd love to hear your feedback! Please:

* ⭐ Star the repository if you find it helpful
* 🐛 Report issues on GitHub
* 💡 Suggest improvements
* 📝 Share your experience
