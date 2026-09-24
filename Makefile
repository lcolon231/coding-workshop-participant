# ACME Facility Incident Management -- developer entrypoints.
#
# LocalStack is not used. Local development is uvicorn against the native
# PostgreSQL on :5432; the cloud target is Lambda behind CloudFront.
# bin/start-dev.sh is NOT used (it hard-exits without LocalStack).
#
# `deploy` depends on `sync` because bin/deploy-backend.sh is plain
# `terraform apply` and never vendors the shared package itself.

.PHONY: help venv serve migrate downgrade db-current db-pending revision \
        seed test cov lint audit sync verify-sync deploy migrate-cloud \
        seed-cloud clean

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
SERVICE ?= auth
PORT    ?= 8000

# acme_core is read from _shared, never from a vendored copy, so local runs and
# tests can never pass against a stale artifact.
export PYTHONPATH := backend/_shared:backend/$(SERVICE)

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

venv: ## Create .venv and install runtime + dev dependencies
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements-dev.txt
	test -s backend/$(SERVICE)/requirements.txt && $(PIP) install --quiet -r backend/$(SERVICE)/requirements.txt || true
	@echo "venv ready: $(VENV)"

# Plain `make serve` runs every service in one process, one origin for the
# Vite proxy, as CloudFront gives the browser in the cloud. Naming a SERVICE
# on the command line runs that one alone, the shape its Lambda has.
serve: export ACME_SERVICE_NAME := $(if $(filter command line,$(origin SERVICE)),$(SERVICE),all)
serve: ## Run every service locally on one port (:8000), or one:  make serve SERVICE=incidents
	$(VENV)/bin/uvicorn --factory tools.devserver:app --reload --port $(PORT)

migrate: ## Apply migrations to the local database
	$(PY) -m acme_core.db.migrate upgrade

downgrade: ## Revert migrations:  make downgrade [TO=base|<revision>]
	$(PY) -m acme_core.db.migrate downgrade $(or $(TO),base)

db-current: ## Print the revision the local database is stamped with
	$(PY) -m acme_core.db.migrate current

db-pending: ## Is the local database behind the code?
	$(PY) -m acme_core.db.migrate pending

revision: ## Autogenerate a migration:  make revision M="add widgets"
	$(VENV)/bin/alembic -c backend/_shared/alembic.ini revision --autogenerate -m "$(M)"

seed: migrate ## Seed demo users locally: ACME_SEED_PASSWORD=... make seed (idempotent)
	$(PY) -m acme_core.seed

test: ## Run the test suite
	$(PYTEST)

cov: ## Run tests with coverage against the current ratchet (report in backend/coverage, like frontend/coverage)
	$(PYTEST) --cov --cov-report=term-missing --cov-report=html

lint: ## Ruff + bandit, matching what CI runs
	$(VENV)/bin/ruff check backend tests tools
	# Exclude only the VENDORED copies. '*/acme_core/*' would also match
	# backend/_shared/acme_core and silently skip the real source.
	$(VENV)/bin/bandit -q -r ./backend -x './backend/auth/acme_core,./backend/incidents/acme_core,./backend/facilities/acme_core'

audit: ## Report known vulnerabilities in pinned runtime dependencies
	$(PIP) install --quiet pip-audit && $(VENV)/bin/pip-audit -r backend/$(SERVICE)/requirements.txt

sync: ## Vendor acme_core into each service directory
	./tools/sync-shared.sh

verify-sync: ## Fail if any vendored copy is stale
	./tools/verify-sync.sh

deploy: sync verify-sync ## Vendor, verify, then deploy to AWS
	./bin/deploy-backend.sh aws

migrate-cloud: ## Apply migrations inside the deployed Lambda
	./tools/db.sh migrate

seed-cloud: ## Seed the deployed database (requires ADMIN_PASSWORD and confirm)
	@test -n "$(ADMIN_PASSWORD)" || (echo "set ADMIN_PASSWORD=... (never committed)" >&2; exit 1)
	./tools/db.sh seed '{"admin_password":"$(ADMIN_PASSWORD)","confirm":"$(PARTICIPANT_ID)"}'

clean: ## Remove vendored copies, caches and coverage output
	find backend -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/*/acme_core .pytest_cache backend/coverage
