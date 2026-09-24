# Testing

Every automated test in the repository and what it covers, generated on 2026-09-24 at commit `d73016a`.

Regenerate with:

```sh
.venv/bin/pytest --cov --cov-report=json:cov.json          # backend, needs local PostgreSQL
.venv/bin/pytest --collect-only -q                         # the backend inventory
cd frontend && npx vitest run --coverage                   # unit tests and coverage
cd frontend && npx vitest list                             # the frontend inventory
cd frontend && npx playwright test --list                  # the end-to-end inventory
```

## At a glance

| Suite | Runner | Tests | Coverage | Gate |
|---|---|---|---|---|
| Backend (`tests/`) | pytest | 1777 cases from 872 test functions in 37 files; last run 1741 passed, 36 skipped (the skips are parametrized schema cases that do not apply to a given schema) | 99.9% of 3157 statements, branches included | `fail_under = 98` in `pyproject.toml` |
| Frontend (`frontend/src`) | vitest | 214 tests in 41 files, 241 passed on the last run (a table-driven test lists once but runs per row) | 92.7% statements, 84.3% branches, 90.9% functions, 93.3% lines | statements 90, lines 90, functions 88, branches 80 in `vite.config.js` |
| End to end (`frontend/e2e`) | Playwright | 4 tests in 2 files | not measured; drives the built app and a live backend | none |

Backend coverage counts branches as well as statements, so its figure is not directly comparable to the frontend's statement figure. A parametrized backend test counts once per case in the first column; the table below lists each test function once with its case count.

## Backend coverage by module

| Module | Statements | Missed | Branches | Partial | Covered |
|---|---|---|---|---|---|
| `backend/_shared/acme_core/__init__.py` | 9 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/admin_actions.py` | 40 | 0 | 10 | 0 | 100.0% |
| `backend/_shared/acme_core/api.py` | 99 | 0 | 14 | 0 | 100.0% |
| `backend/_shared/acme_core/config.py` | 57 | 0 | 4 | 0 | 100.0% |
| `backend/_shared/acme_core/db/__init__.py` | 4 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/db/base.py` | 14 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/db/engine.py` | 36 | 0 | 8 | 2 | 95.5% |
| `backend/_shared/acme_core/db/migrate.py` | 57 | 0 | 10 | 0 | 100.0% |
| `backend/_shared/acme_core/dependencies.py` | 46 | 0 | 10 | 0 | 100.0% |
| `backend/_shared/acme_core/errors.py` | 54 | 0 | 2 | 0 | 100.0% |
| `backend/_shared/acme_core/exceptions.py` | 66 | 0 | 8 | 0 | 100.0% |
| `backend/_shared/acme_core/lambda_entry.py` | 55 | 0 | 20 | 0 | 100.0% |
| `backend/_shared/acme_core/logging_config.py` | 46 | 0 | 10 | 0 | 100.0% |
| `backend/_shared/acme_core/models/__init__.py` | 9 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/catalog.py` | 17 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/enums.py` | 28 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/facility.py` | 35 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/incident.py` | 86 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/notification.py` | 23 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/types.py` | 5 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/models/user.py` | 54 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/pagination.py` | 17 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/reporting.py` | 27 | 0 | 6 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/__init__.py` | 8 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/auth.py` | 120 | 0 | 16 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/common.py` | 35 | 0 | 2 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/engineer.py` | 19 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/facility.py` | 93 | 0 | 2 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/incident.py` | 149 | 0 | 6 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/notification.py` | 18 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/schemas/report.py` | 84 | 0 | 8 | 0 | 100.0% |
| `backend/_shared/acme_core/scoping.py` | 24 | 0 | 8 | 0 | 100.0% |
| `backend/_shared/acme_core/security/__init__.py` | 5 | 0 | 0 | 0 | 100.0% |
| `backend/_shared/acme_core/security/passwords.py` | 25 | 0 | 6 | 0 | 100.0% |
| `backend/_shared/acme_core/security/principal.py` | 44 | 0 | 8 | 0 | 100.0% |
| `backend/_shared/acme_core/security/secret.py` | 29 | 1 | 4 | 1 | 93.9% |
| `backend/_shared/acme_core/security/tokens.py` | 61 | 0 | 4 | 0 | 100.0% |
| `backend/_shared/acme_core/seed.py` | 221 | 0 | 48 | 0 | 100.0% |
| `backend/_shared/acme_core/workflow.py` | 77 | 0 | 18 | 0 | 100.0% |
| `backend/auth/auth_service/__init__.py` | 0 | 0 | 0 | 0 | 100.0% |
| `backend/auth/auth_service/app.py` | 4 | 0 | 0 | 0 | 100.0% |
| `backend/auth/auth_service/repository.py` | 44 | 0 | 10 | 0 | 100.0% |
| `backend/auth/auth_service/routes.py` | 61 | 0 | 0 | 0 | 100.0% |
| `backend/auth/auth_service/service.py` | 187 | 0 | 66 | 0 | 100.0% |
| `backend/facilities/facilities_service/__init__.py` | 0 | 0 | 0 | 0 | 100.0% |
| `backend/facilities/facilities_service/app.py` | 4 | 0 | 0 | 0 | 100.0% |
| `backend/facilities/facilities_service/repository.py` | 127 | 0 | 38 | 0 | 100.0% |
| `backend/facilities/facilities_service/routes.py` | 100 | 0 | 0 | 0 | 100.0% |
| `backend/facilities/facilities_service/service.py` | 182 | 0 | 32 | 0 | 100.0% |
| `backend/incidents/incidents_service/__init__.py` | 0 | 0 | 0 | 0 | 100.0% |
| `backend/incidents/incidents_service/app.py` | 4 | 0 | 0 | 0 | 100.0% |
| `backend/incidents/incidents_service/repository.py` | 177 | 0 | 38 | 0 | 100.0% |
| `backend/incidents/incidents_service/routes.py` | 103 | 0 | 0 | 0 | 100.0% |
| `backend/incidents/incidents_service/service.py` | 268 | 0 | 92 | 1 | 99.7% |
| **Total** | 3157 | 1 | 508 | 4 | **99.9%** |

## Backend tests

### Unit (1303 cases in 27 files)

#### `tests/unit/test_principal.py` (20 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestSessionRevocation::test_a_token_issued_before_the_cutoff_is_rejected` | 1 | This is what makes logout-all and a role change take effect at once. |
| `TestSessionRevocation::test_a_token_issued_in_the_same_second_is_accepted` | 1 | `iat` is a whole number of seconds; sub-second drift must not log out. |
| `TestSessionRevocation::test_a_token_issued_after_the_cutoff_is_accepted` | 1 |  |
| `TestSessionRevocation::test_a_naive_cutoff_is_treated_as_utc` | 1 | A driver or migration can hand back a naive datetime; comparing it |
| `TestActiveAccounts::test_a_deactivated_account_is_rejected` | 1 |  |
| `TestActiveAccounts::test_deactivation_is_indistinguishable_from_absence` | 1 | Otherwise the error message becomes an account-existence oracle. |
| `TestActiveAccounts::test_an_active_account_passes` | 1 |  |
| `TestRoleProperties::test_classification` | 3 |  |
| `TestFromUser::test_role_comes_from_the_row_not_a_claim` | 1 | A demoted admin must lose access now, not when their token expires. |
| `TestFromUser::test_carries_identity_and_role` | 1 |  |
| `TestRoleGates::test_staff_gate_rejects_an_employee` | 1 |  |
| `TestRoleGates::test_admin_gate_admits_an_admin` | 1 |  |
| `TestRoleGates::test_staff_gate_admits_staff` | 2 |  |
| `TestRoleGates::test_admin_gate_rejects_everyone_else` | 2 | Engineers are staff but not administrators; both must be refused. |
| `TestRoleGates::test_an_empty_gate_admits_nobody` | 1 | Fail closed: a gate listing no roles must not become a gate that passes. |
| `TestRoleGates::test_custom_gate` | 1 |  |

#### `tests/unit/test_schemas.py` (154 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestResponses::test_user_out_carries_no_password_hash` | 1 |  |
| `TestResponses::test_user_out_carries_no_lockout_counters` | 1 | Operational state; exposing it lets a client probe lockout status. |
| `TestResponses::test_admin_create_may_choose_a_role` | 1 |  |
| `TestResponses::test_incident_out_exposes_all_four_stamps` | 1 | The client renders an SLA timeline from these. |
| `TestResponses::test_note_out_reports_visibility` | 1 | So the UI can mark an internal note as such. |
| `TestResponses::test_responses_read_from_orm_objects` | 1 |  |
| `TestIncidentCreation::test_a_seat_with_its_floor_is_accepted` | 1 |  |
| `TestIncidentCreation::test_an_unknown_priority_is_rejected` | 1 |  |
| `TestIncidentCreation::test_floor_and_seat_are_optional` | 1 |  |
| `TestIncidentCreation::test_priority_defaults_to_medium` | 1 |  |
| `TestIncidentCreation::test_a_seat_requires_its_floor` | 1 | A seat with no floor breaks the UI cascade and means nothing. |
| `TestIncidentCreation::test_building_is_required` | 1 |  |
| `TestMassAssignment::test_filter_schemas_cannot_be_used_to_assign` | 36 | A filter schema must never be passed to a constructor. |
| `TestMassAssignment::test_no_request_schema_assigns_a_server_controlled_field` | 36 | Closes mass assignment for every endpoint at once, present and future. |
| `TestMassAssignment::test_every_request_schema_forbids_extra_fields` | 36 | Without this an ignored field returns 201 and looks like it worked. |
| `TestMassAssignment::test_incident_create_takes_no_reporter` | 1 | Otherwise one employee can file an incident as another. |
| `TestMassAssignment::test_incident_update_cannot_set_status` | 1 | Status moves only through the transition endpoint, which applies |
| `TestTransitionRequest::test_optional_fields_default_to_none` | 1 | Which is required depends on the edge; the workflow decides, not this. |
| `TestTransitionRequest::test_requires_a_target` | 1 |  |
| `TestTransitionRequest::test_an_unknown_status_is_rejected` | 1 |  |
| `TestLogin::test_accepts_any_domain` | 1 | The domain rule gates registration, not sign-in. |
| `TestLogin::test_normalises_the_email` | 1 |  |
| `TestLogin::test_does_not_impose_the_strength_rule` | 1 | A password policy tightened later must not lock out existing users. |
| `TestRegistration::test_accepts_a_company_address` | 1 |  |
| `TestRegistration::test_rejects_a_short_password` | 1 |  |
| `TestRegistration::test_rejects_an_empty_name` | 1 |  |
| `TestRegistration::test_rejects_other_domains` | 4 | The suffix cases matter: a naive endswith check accepts the middle two. |
| `TestRegistration::test_supplying_a_role_is_a_validation_error` | 1 | Not silently ignored: the client is told it was refused. |
| `TestRegistration::test_has_no_role_field_at_all` | 1 | Self-registration always creates an Employee. |
| `TestRegistration::test_lowercases_and_trims` | 1 | So the unique index is effectively case-insensitive. |
| `TestPage::test_an_empty_page_is_not_more` | 1 |  |
| `TestPage::test_reports_totals_and_window` | 1 |  |
| `TestPage::test_knows_when_it_is_the_last_page` | 1 |  |
| `TestFilters::test_permitted_sorts_are_accepted` | 4 |  |
| `TestFilters::test_defaults_are_sensible` | 1 |  |
| `TestFilters::test_sort_is_an_allowlist` | 4 | ORDER BY cannot be parameterised, so a free-text sort is injectable, |
| `TestFilters::test_negative_offset_is_rejected` | 1 |  |
| `TestFilters::test_page_size_is_bounded` | 1 | An unbounded limit is a way to pull the whole table in one request. |
| `TestFilters::test_order_is_an_allowlist` | 1 |  |
| `TestFilters::test_status_filter_accepts_only_real_statuses` | 1 |  |

#### `tests/unit/test_admin_actions.py` (14 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestSeedRefusals::test_with_the_wrong_confirmation` | 4 |  |
| `TestSeedRefusals::test_without_app_id_in_the_environment` | 1 |  |
| `TestSeedRefusals::test_without_a_password` | 3 |  |
| `TestSeedRefusals::test_a_refusal_never_echoes_the_password` | 1 |  |
| `TestMigrate::test_upgrades_then_drops_the_pool` | 1 | The next request must not reuse a connection opened on the old schema. |
| `TestDispatch::test_an_unknown_action_is_refused` | 1 | Unreachable through classify(); kept so the function is safe on its own. |
| `TestDispatch::test_options_are_never_logged` | 1 |  |
| `TestSeedCli::test_seeds_and_commits_with_a_password` | 1 |  |
| `TestSeedCli::test_refuses_to_run_without_a_password` | 1 |  |

#### `tests/unit/test_tokens.py` (30 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestRefreshTokenStorage::test_the_token_is_not_recoverable_from_the_hash` | 1 | A database disclosure must not hand over usable credentials. |
| `TestRefreshTokenStorage::test_hash_is_stable` | 1 |  |
| `TestRefreshTokenStorage::test_different_tokens_hash_differently` | 1 |  |
| `TestTokenTypeSeparation::test_a_missing_typ_claim_fails_closed` | 1 | Absent must be rejected, never defaulted to access. |
| `TestTokenTypeSeparation::test_an_access_token_is_rejected_at_refresh` | 1 | The other direction: a 30-minute token must not become a 7-day one. |
| `TestTokenTypeSeparation::test_each_type_is_accepted_at_its_own_endpoint` | 1 |  |
| `TestTokenTypeSeparation::test_an_unrecognised_typ_is_rejected` | 1 |  |
| `TestTokenTypeSeparation::test_a_refresh_token_is_rejected_at_a_protected_endpoint` | 1 | Otherwise a stolen 7-day token authenticates API calls for a week. |
| `TestLifetimes::test_an_expired_token_is_rejected_distinctly` | 1 | token_expired and unauthenticated call for different client behaviour. |
| `TestLifetimes::test_access_tokens_are_short` | 1 |  |
| `TestLifetimes::test_skew_beyond_the_leeway_is_still_rejected` | 1 | Leeway is a tolerance, not a hole: an hour ahead is not drift. |
| `TestLifetimes::test_a_token_from_the_future_is_still_usable` | 1 | Modest clock skew must not log people out. |
| `TestLifetimes::test_refresh_tokens_are_long` | 1 |  |
| `TestRoundTrip::test_type_survives` | 1 |  |
| `TestRoundTrip::test_claims_are_returned_at_issue_time` | 1 | So a caller can persist jti and expiry without decoding its own token. |
| `TestRoundTrip::test_subject_survives` | 1 |  |
| `TestRoundTrip::test_each_token_has_a_unique_jti` | 1 | Needed to identify a rotation chain, and to blocklist one token. |
| `TestClaimBinding::test_a_wrong_issuer_is_rejected` | 1 |  |
| `TestClaimBinding::test_iat_is_exposed_for_session_revocation` | 1 | Compared against users.sessions_valid_from to invalidate old tokens. |
| `TestClaimBinding::test_a_wrong_audience_is_rejected` | 1 | Stops a token minted for something else being replayed here. |
| `TestClaimBinding::test_a_non_uuid_subject_is_rejected` | 1 |  |
| `TestSignatureAttacks::test_a_different_algorithm_is_rejected` | 1 | HS512 with the same key must not be accepted where HS256 is expected. |
| `TestSignatureAttacks::test_malformed_input_is_rejected_not_crashed` | 5 |  |
| `TestSignatureAttacks::test_a_tampered_payload_is_rejected` | 1 |  |
| `TestSignatureAttacks::test_a_token_signed_with_another_key_is_rejected` | 1 |  |
| `TestSignatureAttacks::test_algorithm_is_never_taken_from_the_token` | 1 | The classic break: alg:none makes any payload verify. |

#### `tests/unit/test_logging_config.py` (33 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestJsonShape::test_emits_valid_json` | 1 |  |
| `TestJsonShape::test_exception_is_rendered` | 1 |  |
| `TestJsonShape::test_extras_are_included` | 1 |  |
| `TestJsonShape::test_unserialisable_extras_do_not_raise` | 1 | A UUID or datetime in `extra` must never break logging itself. |
| `TestJsonShape::test_carries_level_and_logger` | 1 |  |
| `TestConfigureLogging::test_replaces_existing_handlers` | 1 | The Lambda runtime installs its own; two handlers means double logs. |
| `TestOverMatching::test_over_matching_is_accepted` | 1 | Documents the trade-off rather than leaving it to be rediscovered. |
| `TestOverMatching::test_the_injected_platform_variable_is_caught` | 1 | infra/locals.tf:108 injects POSTGRES_PASS, not POSTGRES_PASSWORD. |
| `TestRequestCorrelation::test_included_in_every_line` | 1 |  |
| `TestRequestCorrelation::test_prefers_the_lambda_request_id` | 1 | Lets a log line be matched against the platform's own REPORT record. |
| `TestRequestCorrelation::test_handles_a_context_without_the_attribute` | 1 |  |
| `TestRequestCorrelation::test_falls_back_to_a_uuid` | 1 |  |
| `TestRequestCorrelation::test_absent_by_default` | 1 |  |
| `TestRequestCorrelation::test_round_trip` | 1 |  |
| `TestRedaction::test_non_secret_values_survive` | 1 |  |
| `TestRedaction::test_credential_keys_are_detected` | 9 |  |
| `TestRedaction::test_ordinary_keys_are_not` | 4 |  |
| `TestRedaction::test_nested_value_is_replaced` | 1 |  |
| `TestRedaction::test_secret_nested_in_an_extra_never_reaches_output` | 1 |  |
| `TestRedaction::test_top_level_value_is_replaced` | 1 |  |
| `TestRedaction::test_inside_a_list` | 1 |  |
| `TestRedaction::test_secret_extra_never_reaches_output` | 1 | The property that matters: a credential cannot reach CloudWatch. |

#### `tests/unit/test_auth_function.py` (9 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestAdmin::test_dispatches_an_admin_command` | 1 |  |
| `TestAdmin::test_an_admin_command_never_builds_the_adapter` | 1 | The web stack is imported at module scope now (init-phase CPU), but |
| `TestHttp::test_serves_a_function_url_request` | 1 | /healthz builds no engine, so this runs under the unit tier's no-I/O guard. |
| `TestHttp::test_builds_the_adapter_once_and_reuses_it` | 1 |  |
| `TestRefusal::test_anything_else_fails_loudly` | 4 |  |
| `TestRefusal::test_the_error_never_echoes_the_event` | 1 |  |

#### `tests/unit/test_migrate_cli.py` (10 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestCommandDispatch::test_downgrade_defaults_to_base` | 1 |  |
| `TestCommandDispatch::test_downgrade_accepts_a_target` | 1 |  |
| `TestCommandDispatch::test_pending` | 1 |  |
| `TestCommandDispatch::test_current` | 1 |  |
| `TestCommandDispatch::test_upgrade` | 1 |  |
| `TestCommandDispatch::test_upgrade_is_the_default` | 1 |  |
| `TestCommandDispatch::test_unknown_action_exits_non_zero` | 1 |  |
| `TestCommandDispatch::test_current_reports_none_when_unmigrated` | 1 |  |
| `TestScriptLocation::test_resolves_inside_the_package` | 1 | Must survive the rsync into a service directory, where no ini exists. |
| `TestScriptLocation::test_alembic_is_not_imported_at_module_scope` | 1 | Alembic drags in Mako and MarkupSafe; the request path never needs them. |

#### `tests/unit/test_devserver.py` (17 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestDiscovery::test_finds_every_deployable_service` | 1 |  |
| `TestCombinedDocs::test_the_schema_holds_every_service_and_groups_by_it` | 1 |  |
| `TestCombinedDocs::test_one_page_over_every_service` | 1 |  |
| `TestCombinedDocs::test_a_conflicting_schema_name_is_renamed_not_overwritten` | 1 |  |
| `TestCombined::test_an_unmounted_prefix_gets_the_same_envelope` | 4 | `/api/authz` must not be mistaken for `/api/auth`. |
| `TestCombined::test_each_prefix_reaches_its_own_service` | 3 | /healthz builds no engine, so this runs under the unit tier's no-I/O guard. |
| `TestCombined::test_each_service_keeps_its_own_docs` | 3 |  |
| `TestCombined::test_a_service_404_is_the_service_envelope` | 1 |  |
| `TestSingle::test_a_service_without_a_package_gets_the_shared_routes` | 1 |  |
| `TestSingle::test_naming_a_service_serves_only_that_one` | 1 |  |

#### `tests/unit/test_workflow_spec.py` (11 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestDescribe::test_lists_every_edge` | 1 |  |
| `TestDescribe::test_each_edge_carries_what_a_client_needs` | 1 |  |
| `TestDescribe::test_lists_every_status` | 1 |  |
| `TestDescribe::test_requirements_are_reported_so_the_ui_can_prompt` | 1 | Without this the client cannot know to ask for a resolution note. |
| `TestDescribe::test_is_json_serialisable` | 1 | It is returned straight from a route; enums would not survive. |
| `test_no_self_loops` | 1 |  |
| `test_exactly_seven_edges` | 1 |  |
| `test_every_status_is_reachable_from_open` | 1 | A status nothing can reach is dead weight in the model. |
| `test_the_table_matches_the_specification` | 1 | The single assertion the other ~400 workflow cases rest on. |
| `test_closed_is_terminal_by_omission` | 1 | Not by a special case. Nothing in the module names CLOSED as an exception. |
| `test_no_duplicate_edges` | 1 |  |

#### `tests/unit/test_engine.py` (15 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestDisposal::test_dispose_releases_and_resets` | 1 |  |
| `TestDisposal::test_dispose_also_resets_the_session_factory` | 1 | A factory bound to a disposed engine would hand out dead sessions. |
| `TestDisposal::test_dispose_is_safe_when_never_built` | 1 |  |
| `TestGuardFixture::test_unit_tier_cannot_build_a_real_engine` | 1 | The autouse guard is what makes 'no I/O' enforced, not merely intended. |
| `TestPoolConfiguration::test_pool_timeout_fails_fast` | 1 | Beats SQLAlchemy's 30s default, which outlives most request deadlines. |
| `TestPoolConfiguration::test_recycle_below_common_idle_timeout` | 1 |  |
| `TestPoolConfiguration::test_pre_ping_enabled` | 1 | Aurora scales to zero capacity and drops idle connections. |
| `TestPoolConfiguration::test_pool_is_minimal` | 1 | One request per execution environment: a second connection is waste. |
| `TestPoolConfiguration::test_url_comes_from_settings` | 1 |  |
| `TestGetDb::test_rolls_back_and_reraises` | 1 |  |
| `TestGetDb::test_always_closes` | 1 | A leaked session holds a pooled connection; the pool has exactly one. |
| `TestGetDb::test_commits_on_success` | 1 |  |
| `TestLaziness::test_memoised` | 1 |  |
| `TestLaziness::test_built_on_first_use` | 1 |  |
| `TestLaziness::test_importing_does_not_build_an_engine` | 1 | Cold starts must not pay for a pool that may never be used. |

#### `tests/unit/test_workflow_stamps.py` (19 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestPolicyTable::test_every_stamped_column_is_on_the_incident_model` | 1 |  |
| `TestPolicyTable::test_acknowledgement_is_first_and_resolution_is_latest` | 1 | The distinction the whole module exists for. |
| `TestPolicyTable::test_defaults_to_now_when_no_instant_given` | 1 |  |
| `TestUnstamped::test_only_declared_columns_are_touched` | 5 | A bug that sets the right stamp while clobbering another must fail. |
| `TestUnstamped::test_entering_a_status_writes_its_stamps` | 5 |  |
| `TestFirstOccurrence::test_an_existing_value_is_preserved` | 2 |  |
| `TestFirstOccurrence::test_returning_from_blocked_does_not_reset_acknowledgement` | 1 | Blocked -> In Progress is a normal part of one piece of work. |
| `TestLatestOccurrence::test_closing_again_overwrites` | 1 |  |
| `TestLatestOccurrence::test_reopening_and_resolving_again_overwrites` | 1 | Keeping the first value would report a time-to-resolve that silently |
| `TestFullLifecycle::test_a_reopened_ticket_reports_honest_timings` | 1 | The end-to-end reason the per-field policy exists. |

#### `tests/unit/test_scoping_sql.py` (13 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestIncidentScoping::test_an_unknown_role_fails_closed` | 1 | A role added without deciding its visibility must not see everything. |
| `TestIncidentScoping::test_composes_with_existing_filters` | 1 | Successive where() clauses AND together, so a filter cannot widen scope. |
| `TestIncidentScoping::test_admin_is_unfiltered` | 1 |  |
| `TestIncidentScoping::test_employee_filters_on_reporter_only` | 1 |  |
| `TestIncidentScoping::test_composes_after_ordering_and_limits` | 1 |  |
| `TestIncidentScoping::test_engineer_filters_on_assignee_only` | 1 |  |
| `TestIncidentScoping::test_returns_a_new_statement` | 1 | Generative, so a caller cannot mutate the original by accident. |
| `TestNoteScoping::test_the_filter_names_the_public_value` | 1 |  |
| `TestNoteScoping::test_employees_see_only_public_notes` | 1 |  |
| `TestNoteScoping::test_staff_see_internal_notes` | 2 |  |
| `TestSubqueryHelper::test_admin_subquery_is_unfiltered` | 1 |  |
| `TestSubqueryHelper::test_builds_a_scoped_id_select` | 1 | Used to scope children whose own table has no reporter column. |

#### `tests/unit/test_incidents_function.py` (9 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestHttp::test_docs_live_under_the_service_prefix` | 1 |  |
| `TestHttp::test_serves_a_function_url_request` | 1 | /healthz builds no engine, so this runs under the unit tier's no-I/O guard. |
| `TestHttp::test_builds_the_adapter_once_and_reuses_it` | 1 |  |
| `TestRefusal::test_anything_else_fails_loudly` | 4 |  |
| `TestRefusal::test_an_admin_command_is_refused_by_name` | 1 | Only the auth function migrates or seeds; this one must not even try. |
| `TestRefusal::test_the_error_never_echoes_the_event` | 1 |  |

#### `tests/unit/test_models_metadata.py` (99 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestReferentialPolicy::test_assignee_is_nulled_not_cascaded` | 1 | An engineer leaving must not delete the work they were assigned. |
| `TestReferentialPolicy::test_children_cascade_with_their_parent` | 7 |  |
| `TestReferentialPolicy::test_reporter_cannot_be_deleted_away` | 1 | RESTRICT, not CASCADE: deleting a user must not erase incident history. |
| `TestReferentialPolicy::test_building_deletion_is_restricted` | 1 | Deleting a building with incidents must be a 409, not silent data loss. |
| `TestRevocationSupport::test_users_carry_a_session_cutoff` | 1 | Lets a role change take effect immediately, not in up to 30 minutes. |
| `TestRevocationSupport::test_refresh_tokens_are_revocable` | 1 |  |
| `TestRevocationSupport::test_users_carry_lockout_state` | 1 |  |
| `TestRevocationSupport::test_users_are_soft_deletable` | 1 |  |
| `TestNamingConvention::test_primary_keys_are_named` | 1 |  |
| `TestNamingConvention::test_foreign_keys_are_named` | 1 |  |
| `TestNamingConvention::test_unique_constraints_are_named` | 1 |  |
| `TestMetadataCompleteness::test_every_table_compiles_for_postgresql` | 13 |  |
| `TestMetadataCompleteness::test_every_expected_table_is_registered` | 1 | A model module nothing imports is invisible to Alembic autogenerate. |
| `TestMetadataCompleteness::test_thirteen_tables` | 1 |  |
| `TestTimestamps::test_no_naive_timestamps_anywhere` | 13 | Mixing naive and aware timestamps makes SLA arithmetic silently wrong. |
| `TestTimestamps::test_stamps_start_null` | 4 | A stamp must mean "this happened", so it cannot default to now(). |
| `TestTimestamps::test_incidents_carry_the_four_stamps` | 1 | Denormalised so SLA reporting is a GROUP BY, not a window function. |
| `TestAppSecrets::test_name_is_the_primary_key` | 1 | Makes INSERT ... ON CONFLICT DO NOTHING the race-safe write. |
| `TestAppSecrets::test_table_exists` | 1 | Carrier for the JWT signing key; no Lambda env var can be added. |
| `TestScopingSupport::test_scoped_columns_are_indexed` | 2 | Row-level scoping filters on these on every list query. |
| `TestScopingSupport::test_refresh_token_family_is_indexed` | 1 | Reuse detection revokes a whole family, which reads every row for it. |
| `TestEnumConstraints::test_every_member_appears_in_a_check` | 6 | create_constraint defaults to False; without it this is a free-text column. |
| `TestEnumConstraints::test_checks_are_actually_emitted` | 1 |  |
| `TestEnumConstraints::test_values_are_stored_not_names` | 1 | Rows must read naturally in psql: 'Facility Admin', not 'FACILITY_ADMIN'. |
| `TestLocationRules::test_seat_is_unique_per_floor_code` | 1 |  |
| `TestLocationRules::test_floor_and_seat_are_optional` | 2 | A lobby has no seat; a lift has no floor. |
| `TestLocationRules::test_building_is_required` | 1 | Every incident happens somewhere. |
| `TestLocationRules::test_floor_is_unique_per_building_level` | 1 |  |
| `TestCredentialHandling::test_users_store_only_a_hash` | 1 |  |
| `TestCredentialHandling::test_engineer_profile_is_one_to_one` | 1 |  |
| `TestCredentialHandling::test_refresh_tokens_store_only_a_hash` | 1 | A database disclosure must not yield usable credentials. |
| `TestCredentialHandling::test_email_is_unique` | 1 |  |
| `TestCredentialHandling::test_token_hash_is_unique` | 1 |  |
| `TestRepresentations::test_repr_leaks_no_credential` | 13 | bandit scans for exactly this, and a traceback carries it to CloudWatch. |
| `TestRepresentations::test_repr_is_readable` | 13 |  |

#### `tests/unit/test_config.py` (25 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestHostResolution::test_container_host_rewritten_on_the_host` | 2 | 172.17.0.1 is the Docker bridge; from the host it routes nowhere. |
| `TestHostResolution::test_aurora_endpoint_never_rewritten` | 1 |  |
| `TestHostResolution::test_blank_host_falls_back` | 1 |  |
| `TestHostResolution::test_container_host_preserved_inside_lambda` | 1 |  |
| `TestJwtFallback::test_deterministic` | 1 |  |
| `TestJwtFallback::test_differs_per_service` | 1 |  |
| `TestJwtFallback::test_does_not_derive_from_the_database_password` | 1 |  |
| `TestSecretMasking::test_real_url_still_contains_it` | 1 | Masking is for logs only; the driver needs the real value. |
| `TestSecretMasking::test_repr_masks_the_password` | 1 |  |
| `TestSecretMasking::test_safe_url_masks_the_password` | 1 |  |
| `TestEnvironmentDiscriminator::test_is_local_is_ignored` | 1 | IS_LOCAL must not influence anything. |
| `TestEnvironmentDiscriminator::test_present_inside_lambda` | 1 |  |
| `TestEnvironmentDiscriminator::test_absent_outside_lambda` | 1 |  |
| `TestDatabaseUrl::test_database_url_env_var_is_ignored` | 1 | A hand-set DATABASE_URL must never win over the injected settings. |
| `TestDatabaseUrl::test_sslmode_absent_locally` | 1 | Local PostgreSQL has no TLS; requesting it would fail every connect. |
| `TestDatabaseUrl::test_sslmode_required_only_inside_lambda` | 1 |  |
| `TestDatabaseUrl::test_carries_connect_timeout` | 1 | Aurora resumes from zero capacity; never wait on the OS default. |
| `TestDatabaseUrl::test_special_characters_in_password_are_quoted` | 1 |  |
| `TestDatabaseUrl::test_uses_psycopg3_driver` | 1 |  |
| `TestDefaults::test_token_lifetimes` | 1 |  |
| `TestDefaults::test_defaults_match_the_injected_local_values` | 1 | Host tooling must work with no exported variables at all. |
| `TestDefaults::test_unparseable_port_falls_back` | 1 |  |
| `TestCaching::test_cache_clear_picks_up_changes` | 1 |  |
| `TestCaching::test_settings_are_cached` | 1 |  |

#### `tests/unit/test_workflow_required.py` (19 cases)

| Test | Cases | What it checks |
|---|---|---|
| `test_the_missing_field_is_named` | 3 | The client renders these against the right input box. |
| `test_blank_values_are_rejected` | 12 | A whitespace-only blocked_reason is the one everybody's code accepts. |
| `test_a_real_value_is_accepted` | 3 |  |
| `test_unknown_payload_keys_are_ignored` | 1 | The workflow judges the fields it declares; schemas reject the rest. |

#### `tests/unit/test_facilities_function.py` (9 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestHttp::test_docs_live_under_the_service_prefix` | 1 |  |
| `TestHttp::test_builds_the_adapter_once_and_reuses_it` | 1 |  |
| `TestHttp::test_serves_a_function_url_request` | 1 | /healthz builds no engine, so this runs under the unit tier's no-I/O guard. |
| `TestRefusal::test_anything_else_fails_loudly` | 4 |  |
| `TestRefusal::test_an_admin_command_is_refused_by_name` | 1 | Only the auth function migrates or seeds; this one must not even try. |
| `TestRefusal::test_the_error_never_echoes_the_event` | 1 |  |

#### `tests/unit/test_workflow_admin.py` (19 cases)

| Test | Cases | What it checks |
|---|---|---|
| `test_admin_bypasses_the_actor_constraint` | 7 | An admin may take every edge without holding any relationship to it. |
| `test_admin_does_not_bypass_required_fields` | 3 | The half that matters. Same edges, same admin, fields omitted. |
| `test_admin_cannot_invent_an_edge` | 7 | The bypass is over actors only; the table still bounds what is possible. |
| `test_an_assignee_supplied_in_the_request_satisfies_it` | 1 | Which is what an admin assigning and starting in one step does. |
| `test_admin_still_needs_an_assignee_to_start_work` | 1 | required_state is not bypassed either: unassigned means unassigned. |

#### `tests/unit/test_workflow_rules.py` (335 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestCheckOrdering::test_a_wrong_actor_beats_a_missing_field` | 1 | Reporting the missing field first would leak which edges exist. |
| `TestCheckOrdering::test_a_missing_edge_beats_a_wrong_actor` | 1 |  |
| `TestTerminalState::test_nothing_leaves_closed` | 15 | Including an admin: the bypass is over actors, never over edges. |
| `TestErrorTypes::test_missing_field_is_a_validation_error` | 1 |  |
| `TestErrorTypes::test_wrong_actor_is_forbidden` | 1 |  |
| `TestErrorTypes::test_unknown_edge_is_a_conflict` | 1 |  |
| `TestActorDerivation::test_relationships_are_derived_correctly` | 12 |  |
| `TestActorDerivation::test_an_admin_is_not_implicitly_the_assignee` | 1 | The bypass adds ADMIN only; it never fakes another relationship. |
| `TestActorDerivation::test_an_employee_assignee_is_not_an_assigned_engineer` | 1 | Assignment does not confer engineer powers on an employee. |
| `TestActorDerivation::test_unassigned_incident_grants_nobody_assigned_engineer` | 1 |  |
| `test_cell_is_accepted_exactly_when_the_spec_allows` | 300 | The whole state machine, decided by the hand-written specification. |

#### `tests/unit/test_errors.py` (61 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestEnvelopeShape::test_status_matches_the_class` | 10 |  |
| `TestEnvelopeShape::test_framework_errors_map_to_the_generic_code` | 5 | Several classes share a status; the framework must get the generic one. |
| `TestEnvelopeShape::test_every_error_produces_the_same_keys` | 10 | This test is what "one consistent error format" actually means. |
| `TestEnvelopeShape::test_framework_404_uses_the_envelope_too` | 1 | Routing failures come from Starlette, not from us. |
| `TestEnvelopeShape::test_details_are_carried_through` | 1 |  |
| `TestEnvelopeShape::test_method_not_allowed_uses_the_envelope` | 1 |  |
| `TestEnvelopeShape::test_details_default_to_an_empty_list` | 1 | Never null: the client can iterate unconditionally. |
| `TestBuildEnvelope::test_uses_the_default_message` | 1 |  |
| `TestBuildEnvelope::test_accepts_an_override` | 1 |  |
| `TestBuildEnvelope::test_shape` | 1 |  |
| `TestAuthChallenge::test_401_carries_www_authenticate` | 4 |  |
| `TestAuthChallenge::test_other_statuses_do_not` | 1 |  |
| `TestValidationHandling::test_field_names_drop_the_location_prefix` | 1 | Pydantic reports ('body', 'attempts'); the client wants 'attempts'. |
| `TestValidationHandling::test_submitted_values_are_never_echoed` | 1 | The security property of this module. |
| `TestValidationHandling::test_absent_body_is_handled` | 1 |  |
| `TestValidationHandling::test_details_carry_only_field_and_message` | 1 |  |
| `TestValidationHandling::test_validation_is_400_not_fastapi_default_422` | 1 |  |
| `TestUnhandledExceptions::test_returns_500_in_the_envelope` | 1 |  |
| `TestUnhandledExceptions::test_request_id_is_kept` | 1 | Scrubbing must not cost debuggability: the id is the CloudWatch key. |
| `TestUnhandledExceptions::test_message_is_scrubbed` | 1 | An exception message can contain a connection string. |
| `TestDetailsFromValidation::test_root_level_error_is_labelled` | 1 |  |
| `TestDetailsFromValidation::test_nested_field_path_is_joined` | 1 |  |
| `TestCatalogIntegrity::test_status_mapping` | 10 |  |
| `TestCatalogIntegrity::test_a_subclass_without_a_code_is_rejected_at_definition` | 1 | Structural, not a convention: this fails at import, not at the first 500. |
| `TestCatalogIntegrity::test_a_subclass_without_a_status_is_rejected_at_definition` | 1 |  |
| `TestCatalogIntegrity::test_catalog_covers_every_class` | 1 | Guards against adding an error that no handler can map to a status. |
| `TestCatalogIntegrity::test_every_class_has_a_unique_code` | 1 |  |

#### `tests/unit/test_workflow_allowed.py` (126 cases)

| Test | Cases | What it checks |
|---|---|---|
| `test_agrees_with_validate_transition` | 60 | The two must never disagree: one renders the button, the other honours it. |
| `test_matches_the_specification` | 60 | Derived from the hand-written spec, not from the transition table. |
| `test_closed_offers_nothing_to_anyone` | 3 |  |
| `test_an_unassigned_open_incident_cannot_be_started` | 1 |  |
| `test_can_transition_never_raises` | 1 | It is a predicate; raising would make call sites defensive. |
| `test_missing_required_fields_withdraw_the_option` | 1 | Without a note there is nothing to render for close-without-work. |

#### `tests/unit/test_reporting.py` (17 cases)

| Test | Cases | What it checks |
|---|---|---|
| `test_due_at_is_creation_plus_the_priority_target` | 4 |  |
| `test_open_work_is_graded_against_the_clock` | 7 |  |
| `test_at_risk_starts_at_the_same_share_of_every_target` | 4 |  |
| `test_finished_work_is_graded_by_when_it_finished_not_by_now` | 1 | A resolved incident stays "met" however long ago that was. |
| `test_finishing_exactly_on_the_deadline_meets_it` | 1 |  |

#### `tests/unit/test_lambda_entry.py` (76 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestDecision::test_is_immutable` | 1 |  |
| `TestDecision::test_every_rejection_has_a_reason` | 1 |  |
| `TestDecision::test_accepted_decisions_carry_no_reason` | 1 |  |
| `TestDecision::test_a_rejection_never_echoes_the_event` | 1 | Reasons are logged; a seed payload carries a password. |
| `TestDecision::test_default_options_are_not_shared` | 1 |  |
| `TestAdmin::test_each_allowlisted_action` | 3 |  |
| `TestAdmin::test_options_are_passed_through` | 1 |  |
| `TestAdmin::test_null_options_become_empty` | 1 |  |
| `TestAdmin::test_absent_options_become_empty` | 1 |  |
| `TestAdmin::test_options_are_copied_not_shared` | 1 |  |
| `TestHttp::test_requires_payload_version_2` | 4 |  |
| `TestHttp::test_headers_alone_are_not_a_request` | 1 |  |
| `TestHttp::test_requires_an_http_method` | 6 |  |
| `TestHttp::test_a_body_naming_an_admin_action_is_still_http` | 1 | The body is a string; it never merges into the top-level event. |
| `TestHttp::test_function_url_request` | 1 |  |
| `TestHttp::test_requires_a_request_context` | 1 |  |
| `TestDrift::test_allowlist_matches_tools_db_sh` | 1 | The CLI and the dispatcher must agree on what can be invoked. |
| `TestDrift::test_marker_matches_tools_db_sh` | 1 |  |
| `TestFailClosed::test_other_invocation_sources` | 4 |  |
| `TestFailClosed::test_actions_outside_the_allowlist` | 8 |  |
| `TestFailClosed::test_the_marker_inside_an_eventbridge_envelope` | 1 |  |
| `TestFailClosed::test_the_marker_must_match_exactly` | 5 |  |
| `TestFailClosed::test_non_objects` | 6 |  |
| `TestFailClosed::test_the_marker_on_an_http_shaped_event` | 17 |  |
| `TestFailClosed::test_options_that_are_not_an_object` | 4 |  |
| `TestFailClosed::test_a_missing_action` | 1 |  |
| `TestFailClosed::test_the_marker_on_a_real_function_url_event` | 1 |  |
| `TestFailClosed::test_an_action_without_the_marker` | 1 | The regression S11 fixed: the old negative test dispatched this. |

#### `tests/unit/test_passwords.py` (15 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestLengthLimits::test_a_long_passphrase_is_not_silently_equal_to_its_prefix` | 1 | The property rejection buys: distinct long passwords stay distinct. |
| `TestLengthLimits::test_rejects_a_short_password` | 1 |  |
| `TestLengthLimits::test_accepts_exactly_the_byte_limit` | 1 |  |
| `TestLengthLimits::test_limit_is_bytes_not_characters` | 1 | A 30-character CJK password is 90 bytes and would be truncated. |
| `TestLengthLimits::test_accepts_exactly_the_minimum` | 1 |  |
| `TestLengthLimits::test_rejects_rather_than_truncates_a_long_password` | 1 | Truncating would make "A"*72 + anything authenticate identically. |
| `TestNonEnumeration::test_a_missing_hash_verifies_as_false` | 1 |  |
| `TestNonEnumeration::test_a_corrupt_hash_returns_false_rather_than_raising` | 1 | A truncated row is a failed login, not a 500. |
| `TestNonEnumeration::test_an_empty_hash_returns_false` | 1 |  |
| `TestNonEnumeration::test_a_missing_hash_still_runs_bcrypt` | 1 | Skipping the comparison would make "no such user" ~300ms faster. |
| `TestHashing::test_rejects_a_wrong_password` | 1 |  |
| `TestHashing::test_is_salted` | 1 | Identical passwords must not produce identical hashes. |
| `TestHashing::test_plaintext_never_appears_in_the_hash` | 1 |  |
| `TestHashing::test_verifies_its_own_hash` | 1 |  |
| `TestHashing::test_produces_a_bcrypt_hash` | 1 |  |

#### `tests/unit/test_api_factory.py` (30 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestMigrationProbe::test_failure_to_check_is_reported_as_unknown` | 1 | A probe that cannot determine state must not claim the service is fine. |
| `TestMigrationProbe::test_pending_migrations_make_readyz_503` | 1 |  |
| `TestReadiness::test_failure_is_not_cached` | 1 | Recovery must be noticed promptly; only success is worth caching. |
| `TestReadiness::test_does_not_expose_the_migration_revision` | 1 | A revision maps to a public commit, advertising known issues. |
| `TestReadiness::test_reachable_database_is_200` | 1 |  |
| `TestReadiness::test_success_is_cached` | 1 | Unauthenticated and public: uncached it is a cost-amplification lever. |
| `TestReadiness::test_unreachable_database_is_503` | 1 | The guard fixture makes the engine raise, standing in for an outage. |
| `TestReadiness::test_undeterminable_migration_state_is_null_not_false` | 1 | Null and false are different: one is "behind", one is "unknown". |
| `TestDocumentation::test_schema_documents_400_not_422` | 1 | Our handler returns 400; FastAPI would otherwise publish its own 422. |
| `TestDocumentation::test_root_docs_are_not_served` | 1 |  |
| `TestDocumentation::test_docs_are_under_the_prefix` | 1 | At the root these are unreachable through CloudFront. |
| `TestDocumentation::test_openapi_is_under_the_prefix` | 1 |  |
| `TestPublishedDocumentation::test_examples_describe_states_the_code_can_actually_produce` | 1 | Field-level examples compose independently into impossible objects. |
| `TestPublishedDocumentation::test_responses_have_a_real_schema` | 2 | Without a response_model this documents `{"additionalProp1": {}}`. |
| `TestPublishedDocumentation::test_description_does_not_leak_docstring_sections` | 2 | FastAPI renders the whole docstring, so Args:/Returns: would show up. |
| `TestPublishedDocumentation::test_failure_example_differs_from_the_success_example` | 1 | A 503 documented with the 200's body teaches a reader nothing. |
| `TestPublishedDocumentation::test_error_envelope_is_documented_for_reuse` | 1 |  |
| `TestPublishedDocumentation::test_readyz_documents_its_failure_mode` | 1 | An endpoint whose purpose is to go 503 must document the 503. |
| `TestRequestCorrelation::test_response_carries_the_header` | 1 |  |
| `TestRequestCorrelation::test_each_request_gets_a_fresh_id` | 1 | Isolation comes from setting a new id per request, not from clearing. |
| `TestCors::test_no_cors_middleware_is_installed` | 1 | infra/lambda.tf:44-51 already sets CORS at the Function URL layer. |
| `TestLiveness::test_healthz_reports_build_provenance` | 1 | Turns "is the deployed code current?" into one curl. |
| `TestLiveness::test_healthz_builds_no_engine` | 1 | A liveness probe that touches a scale-to-zero Aurora would flap. |
| `TestLiveness::test_healthz_is_ok` | 1 |  |
| `TestLiveness::test_healthz_names_the_service` | 1 |  |
| `TestRoutingPrefix::test_routes_mount_under_the_service_prefix` | 1 | CloudFront routes only /api/<name>*; an unprefixed route is unreachable. |
| `TestRoutingPrefix::test_unprefixed_path_is_not_served` | 1 |  |
| `TestRoutingPrefix::test_prefix_follows_the_service_name` | 1 |  |

#### `tests/unit/test_build_stamp.py` (4 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestBuildStamp::test_surfaces_a_dirty_tree` | 1 | A dirty deploy is the one most likely to differ from any commit. |
| `TestBuildStamp::test_version_is_exported` | 1 |  |
| `TestBuildStamp::test_reports_the_generated_values` | 1 |  |
| `TestBuildStamp::test_reports_source_when_unstamped` | 1 | Running from the source tree, where sync has not generated a stamp. |

#### `tests/unit/test_schemas_api.py` (114 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestAdminUserSchemas::test_user_filters_permitted_sorts` | 4 |  |
| `TestAdminUserSchemas::test_user_filters_sort_is_an_allowlist` | 1 |  |
| `TestAdminUserSchemas::test_only_an_engineer_may_have_a_specialty` | 2 | Rejected rather than dropped, so the client sees its mistake. |
| `TestAdminUserSchemas::test_create_enforces_the_company_domain` | 2 | D5: admins get no exemption from the domain rule. |
| `TestAdminUserSchemas::test_an_engineer_needs_a_specialty` | 1 |  |
| `TestAdminUserSchemas::test_an_engineer_with_a_specialty_is_accepted` | 1 |  |
| `TestAdminUserSchemas::test_update_accepts_a_specialty` | 1 |  |
| `TestAdminUserSchemas::test_create_normalises_the_email` | 1 |  |
| `TestFacilitySchemas::test_inactive_records_are_hidden_by_default` | 1 |  |
| `TestFacilitySchemas::test_floors_and_seats_cannot_change_parent` | 1 |  |
| `TestFacilitySchemas::test_sorts_are_allowlists` | 4 |  |
| `TestFacilitySchemas::test_roots_only_and_parent_cannot_combine` | 1 |  |
| `TestFacilitySchemas::test_building_code_cannot_be_renamed` | 1 | It is printed on signage and asset tags. |
| `TestFacilitySchemas::test_categories_cannot_be_reparented` | 1 |  |
| `TestOccupation::test_summaries_expose_neither` | 1 | A birth date is personal data; summaries are shown to every viewer. |
| `TestOccupation::test_users_expose_both_fields` | 1 |  |
| `TestOccupation::test_registration_requires_it` | 1 |  |
| `TestOccupation::test_admin_create_refuses_it_for_other_roles` | 2 |  |
| `TestOccupation::test_admin_create_requires_it_for_an_employee` | 1 |  |
| `TestOccupation::test_it_cannot_be_blank` | 1 |  |
| `TestWorkflowOut::test_round_trips_describe_exactly` | 1 | The endpoint validates describe() through this and must emit it unchanged. |
| `TestWorkflowOut::test_the_wire_name_is_from` | 1 |  |
| `TestEngineerSchemas::test_engineer_filter_sort_is_an_allowlist` | 1 |  |
| `TestEngineerSchemas::test_engineer_out_embeds_the_user_and_load` | 1 |  |
| `TestEngineerSchemas::test_concurrency_limit_is_bounded` | 2 |  |
| `TestDateOfBirth::test_it_is_required_for_every_role_on_admin_create` | 3 |  |
| `TestDateOfBirth::test_a_mistyped_ancient_year_is_refused` | 1 |  |
| `TestDateOfBirth::test_the_future_rule_applies_to_updates_too` | 1 |  |
| `TestDateOfBirth::test_the_earliest_permitted_date_is_accepted` | 1 |  |
| `TestDateOfBirth::test_tomorrow_is_refused` | 1 |  |
| `TestDateOfBirth::test_it_is_required_at_registration` | 1 |  |
| `TestDateOfBirth::test_an_update_may_correct_it` | 1 |  |
| `TestDateOfBirth::test_today_is_accepted` | 1 |  |
| `TestEscalations::test_a_verdict_is_accepted` | 2 |  |
| `TestEscalations::test_a_reason_is_required` | 1 |  |
| `TestEscalations::test_pending_is_not_a_decision` | 1 |  |
| `TestEscalations::test_the_decision_is_not_called_status` | 1 | `status` is server-controlled; the mass-assignment test would refuse it. |
| `TestEscalations::test_the_queue_defaults_to_pending_oldest_first` | 1 |  |
| `TestEscalations::test_out_embeds_requester_and_decider` | 1 |  |
| `TestUpdateModel::test_null_clears_every_clearable_field` | 7 |  |
| `TestUpdateModel::test_an_empty_body_changes_nothing` | 7 |  |
| `TestUpdateModel::test_null_is_refused_on_every_non_clearable_field` | 7 | Otherwise a null reaches a NOT NULL column and surfaces as a 500. |
| `TestUpdateModel::test_clearable_names_real_fields` | 7 | A typo in CLEARABLE would silently make the intended field un-clearable. |
| `TestUpdateModel::test_changes_carries_only_what_was_sent` | 1 |  |
| `TestUpdateModel::test_the_null_message_says_what_to_do` | 1 |  |
| `TestUpdateModel::test_the_catalog_found_the_update_schemas` | 1 | Guards the parametrised tests below against silently testing nothing. |
| `TestUpdateModel::test_values_are_still_validated` | 1 |  |
| `TestIncidentShapes::test_unassigned_incident_has_a_null_assignee` | 1 |  |
| `TestIncidentShapes::test_incident_embeds_reporter_and_assignee` | 1 | An employee cannot call /users, so an id alone is unrenderable. |
| `TestIncidentShapes::test_timeline_reads_oldest_first` | 1 |  |
| `TestIncidentShapes::test_note_embeds_its_author` | 1 |  |
| `TestIncidentShapes::test_incident_filters_accept_a_category` | 1 |  |
| `TestIncidentShapes::test_embedded_users_never_carry_an_email` | 1 |  |
| `TestIncidentShapes::test_history_embeds_its_actor` | 1 |  |
| `TestIncidentShapes::test_detail_lists_the_callers_actions` | 1 | Built from the same function the transition endpoint validates with. |
| `TestReportRange::test_reports_echo_the_window_under_the_wire_names` | 1 |  |
| `TestReportRange::test_grouping_is_an_allowlist` | 3 |  |
| `TestReportRange::test_unknown_parameters_are_refused` | 1 |  |
| `TestReportRange::test_accepts_the_wire_names` | 1 |  |
| `TestReportRange::test_one_day_more_is_refused` | 1 |  |
| `TestReportRange::test_the_maximum_range_is_accepted` | 1 |  |
| `TestReportRange::test_a_backwards_range_is_refused` | 1 |  |
| `TestReportRange::test_defaults_to_the_last_thirty_days` | 1 |  |
| `TestSlaTargets::test_more_urgent_means_a_tighter_target` | 1 |  |
| `TestSlaTargets::test_every_priority_has_a_target` | 1 |  |
| `TestFindByEmail::test_it_is_optional` | 1 |  |
| `TestFindByEmail::test_the_email_filter_is_normalised` | 1 | So an admin pasting `Jane@ACME.inc ` still finds jane@acme.inc. |
| `TestPasswordChange::test_a_no_op_change_is_refused` | 1 | It would still revoke every session, to no purpose. |
| `TestPasswordChange::test_the_new_password_meets_the_strength_rule` | 1 |  |
| `TestPasswordChange::test_accepts_a_valid_change` | 1 |  |
| `TestPasswordChange::test_the_current_password_is_not_held_to_the_new_rule` | 1 | A policy tightened later must not stop a user from changing a weak one. |
| `TestUserShapes::test_register_response_is_only_a_message` | 1 | Returning the user would confirm whether the address was new. |
| `TestUserShapes::test_summary_carries_no_email` | 1 | Embedded wherever a user appears; an address is not every viewer's business. |
| `TestUserShapes::test_me_profile_is_null_for_non_engineers` | 1 |  |
| `TestUserShapes::test_me_carries_an_engineer_profile` | 1 |  |

### Integration (467 cases in 9 files)

#### `tests/integration/test_facilities_api.py` (117 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestCategoryList::test_roots_only_and_children_of_a_parent` | 1 |  |
| `TestCategoryList::test_include_inactive_is_honoured_for_admins_only` | 1 |  |
| `TestCategoryList::test_roots_only_and_parent_id_cannot_combine` | 1 |  |
| `TestCategoryList::test_an_unknown_parent_filter_is_an_empty_page` | 1 |  |
| `TestCategoryList::test_non_admins_see_active_categories_flat_by_name` | 1 |  |
| `TestCategoryList::test_search_matches_the_name` | 1 |  |
| `TestCategoryCreate::test_non_admins_are_refused` | 1 |  |
| `TestCategoryCreate::test_the_parent_must_be_an_existing_root` | 2 |  |
| `TestCategoryCreate::test_a_duplicate_sibling_name_is_a_conflict` | 1 |  |
| `TestCategoryCreate::test_a_child_may_share_a_name_with_a_root` | 1 | Sibling names must differ; the same name under a different parent is fine. |
| `TestCategoryCreate::test_a_duplicate_root_name_is_a_conflict` | 1 | Roots have a NULL parent, which the unique constraint cannot see; the service must. |
| `TestCategoryCreate::test_creates_a_child_of_a_root` | 1 |  |
| `TestCategoryCreate::test_creates_a_root_and_points_at_it` | 1 |  |
| `TestCategoryUpdate::test_renaming_to_its_own_name_is_fine` | 1 |  |
| `TestCategoryUpdate::test_renaming_a_child_onto_a_sibling_is_a_conflict` | 1 |  |
| `TestCategoryUpdate::test_an_unknown_category_is_not_found` | 1 |  |
| `TestCategoryUpdate::test_rejects_a_null_name_and_re_parenting` | 2 |  |
| `TestCategoryUpdate::test_renaming_a_root_onto_another_root_is_a_conflict` | 1 |  |
| `TestCategoryUpdate::test_renames_and_clears_the_description` | 1 |  |
| `TestCategoryUpdate::test_deactivating_a_root_hides_it_but_not_its_children` | 1 | Documented, not cascaded: the client builds the tree from active roots. |
| `TestBuildingDelete::test_an_empty_building_is_deleted` | 1 |  |
| `TestBuildingDelete::test_a_building_with_floors_is_refused_and_its_floors_survive` | 1 | T72: the FK would cascade, so the service must refuse before the database sees it. |
| `TestBuildingDelete::test_a_building_with_incidents_is_refused` | 1 |  |
| `TestBuildingDelete::test_the_database_restriction_is_a_conflict_too` | 1 | Miss the pre-check on purpose: the RESTRICT foreign key must still surface as 409. |
| `TestBuildingDelete::test_an_unknown_building_is_not_found` | 1 |  |
| `TestFloorGet::test_returns_the_floor` | 1 |  |
| `TestFloorGet::test_a_floor_is_as_visible_as_its_building` | 1 |  |
| `TestSeatCreate::test_non_admins_are_refused` | 1 |  |
| `TestSeatCreate::test_a_duplicate_code_is_a_conflict` | 1 |  |
| `TestSeatCreate::test_creates_and_points_at_the_new_row` | 1 |  |
| `TestSeatCreate::test_the_same_code_on_another_floor_is_fine` | 1 |  |
| `TestSeatCreate::test_an_unknown_floor_is_a_validation_error_on_the_field` | 1 |  |
| `TestSeatUpdate::test_deactivating_hides_it_from_non_admins` | 1 |  |
| `TestSeatUpdate::test_renaming_onto_an_existing_code_is_a_conflict` | 1 |  |
| `TestSeatUpdate::test_a_required_field_cannot_be_nulled` | 1 |  |
| `TestSeatUpdate::test_changes_code_and_clears_label` | 1 |  |
| `TestSeatUpdate::test_an_unknown_seat_is_not_found` | 1 |  |
| `TestEngineerGet::test_an_unknown_id_is_not_found` | 1 |  |
| `TestEngineerGet::test_returns_the_profile_with_its_load` | 1 |  |
| `TestEngineerGet::test_anyone_who_is_not_an_active_engineer_is_not_found` | 4 | Including the demoted user, whose profile row outlived their role. |
| `TestEngineerGet::test_a_non_admin_is_refused` | 1 |  |
| `TestSeatGet::test_the_404_200_pair_on_a_seat_nobody_should_be_offered` | 2 | A retired seat, and an active seat in a retired building, look alike to an employee. |
| `TestSeatGet::test_returns_the_seat` | 1 |  |
| `TestFloorDelete::test_a_floor_named_by_an_incident_is_refused_and_the_incident_keeps_it` | 1 | The FK is SET NULL, so only this check stands between the delete and a lost location. |
| `TestFloorDelete::test_a_floor_with_seats_is_refused_and_its_seats_survive` | 1 |  |
| `TestFloorDelete::test_an_empty_floor_is_deleted` | 1 |  |
| `TestFloorDelete::test_a_non_admin_is_refused_before_the_lookup` | 1 |  |
| `TestFloorDelete::test_an_unknown_floor_is_not_found` | 1 |  |
| `TestEngineerList::test_only_admins_may_look` | 1 |  |
| `TestEngineerList::test_open_assignments_counts_non_closed_incidents_and_sorts_by_load` | 1 |  |
| `TestEngineerList::test_sorts_by_specialty_and_pages` | 1 |  |
| `TestEngineerList::test_filters_by_specialty_case_insensitively_and_by_availability` | 1 |  |
| `TestEngineerList::test_lists_active_engineers_with_their_user_by_name` | 1 | Not the employee, not the demoted user with a stale profile, not the inactive one. |
| `TestBuildingCreate::test_a_duplicate_code_is_a_conflict` | 1 |  |
| `TestBuildingCreate::test_creates_and_points_at_the_new_row` | 1 |  |
| `TestBuildingCreate::test_the_body_is_strict` | 1 |  |
| `TestBuildingUpdate::test_a_required_field_cannot_be_nulled` | 1 |  |
| `TestBuildingUpdate::test_the_code_is_immutable` | 1 |  |
| `TestBuildingUpdate::test_an_unknown_building_is_not_found` | 1 |  |
| `TestBuildingUpdate::test_deactivating_hides_it_from_non_admins` | 1 |  |
| `TestBuildingUpdate::test_omitted_fields_are_unchanged_and_null_clears` | 1 |  |
| `TestEngineerUpdate::test_a_demoted_user_cannot_be_edited_here` | 1 |  |
| `TestEngineerUpdate::test_edits_the_scheduling_fields` | 1 |  |
| `TestEngineerUpdate::test_rejects_zero_capacity_nulls_and_unknown_fields` | 3 |  |
| `TestEngineerUpdate::test_a_non_admin_is_refused_before_the_lookup` | 1 |  |
| `TestCategoryGet::test_returns_the_category` | 1 |  |
| `TestCategoryGet::test_the_404_200_pair_on_the_same_retired_id` | 1 |  |
| `TestBuildingList::test_search_matches_code_or_name_with_wildcards_escaped` | 1 |  |
| `TestBuildingList::test_include_inactive_is_honoured_for_admins_only` | 1 |  |
| `TestBuildingList::test_non_admins_see_active_buildings_in_code_order` | 1 |  |
| `TestBuildingList::test_admins_see_active_only_by_default` | 1 |  |
| `TestBuildingList::test_sorting_by_name_descending_with_paging` | 1 |  |
| `TestBuildingList::test_sort_is_an_allowlist` | 1 |  |
| `TestCategoryDelete::test_an_unknown_category_is_not_found` | 1 |  |
| `TestCategoryDelete::test_a_category_carried_by_an_incident_is_refused` | 1 |  |
| `TestCategoryDelete::test_a_non_admin_is_refused_before_the_lookup` | 1 |  |
| `TestCategoryDelete::test_a_parent_is_refused_and_its_children_keep_their_parent` | 1 |  |
| `TestCategoryDelete::test_a_leaf_is_deleted` | 1 |  |
| `TestCategoryDelete::test_the_database_restriction_is_a_conflict_too` | 2 | Miss a pre-check on purpose: both RESTRICT foreign keys must still surface as 409. |
| `TestRouteContract::test_a_write_by_a_non_admin_is_refused_before_any_lookup` | 3 | The role gate answers 403 whether or not the id exists. |
| `TestRouteContract::test_every_other_route_rejects_an_anonymous_caller` | 1 |  |
| `TestFloorUpdate::test_an_unknown_floor_is_not_found` | 1 |  |
| `TestFloorUpdate::test_rejects_a_null_level_and_re_parenting` | 2 |  |
| `TestFloorUpdate::test_moving_onto_an_existing_level_is_a_conflict` | 1 |  |
| `TestFloorUpdate::test_changes_level_and_clears_name` | 1 |  |
| `TestFloorList::test_sorts_by_name_on_request` | 1 |  |
| `TestFloorList::test_an_unknown_building_is_not_found` | 1 |  |
| `TestFloorList::test_lists_a_buildings_floors_lowest_first` | 1 |  |
| `TestFloorList::test_a_retired_buildings_floors_are_for_admins_only` | 1 |  |
| `TestFloorCreate::test_a_duplicate_level_is_a_conflict` | 1 |  |
| `TestFloorCreate::test_creates_and_points_at_the_new_row` | 1 |  |
| `TestFloorCreate::test_an_unknown_building_is_a_validation_error_on_the_field` | 1 |  |
| `TestFloorCreate::test_non_admins_are_refused` | 1 |  |
| `TestBuildingGet::test_an_unknown_id_is_not_found` | 1 |  |
| `TestBuildingGet::test_an_active_building_is_visible_to_everyone` | 1 |  |
| `TestBuildingGet::test_the_404_200_pair_on_the_same_retired_id` | 1 |  |
| `TestSeatList::test_include_inactive_is_honoured_for_admins_only` | 1 |  |
| `TestSeatList::test_search_matches_code_or_label_and_sort_by_label` | 1 |  |
| `TestSeatList::test_a_floor_in_a_retired_building_is_for_admins_only` | 1 |  |
| `TestSeatList::test_non_admins_see_active_seats_in_code_order` | 1 |  |
| `TestSeatList::test_an_unknown_floor_is_not_found` | 1 |  |
| `TestSeatDelete::test_a_seat_named_by_an_incident_is_refused_and_the_incident_keeps_it` | 1 | The FK is SET NULL, so only this check stands between the delete and a lost location. |
| `TestSeatDelete::test_an_unused_seat_is_deleted` | 1 |  |
| `TestSeatDelete::test_an_unknown_seat_is_not_found` | 1 |  |
| `TestSeatDelete::test_a_non_admin_is_refused_before_the_lookup` | 1 |  |

#### `tests/integration/test_auth_api.py` (100 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestRefresh::test_an_access_token_is_refused` | 1 | Or a stolen 30-minute token becomes a 7-day one. |
| `TestRefresh::test_rotates_the_pair` | 1 |  |
| `TestRefresh::test_an_expired_refresh_token_says_sign_in` | 1 | `token_expired` would tell the client to refresh -- which is what just failed. |
| `TestRefresh::test_replaying_a_rotated_token_revokes_the_family` | 1 | The thief and the victim both hold descendants; both must die. |
| `TestRefresh::test_stores_only_a_hash` | 1 |  |
| `TestRefresh::test_garbage_is_refused` | 1 |  |
| `TestRefresh::test_a_deactivated_user_cannot_refresh` | 1 |  |
| `TestEdges::test_losing_a_registration_race_still_looks_like_success` | 1 | The existence check can pass and the insert still collide; the unique index decides. |
| `TestEdges::test_an_engineer_without_open_work_can_be_deactivated` | 1 |  |
| `TestEdges::test_a_token_for_a_user_that_no_longer_exists_is_refused` | 1 |  |
| `TestEdges::test_deactivating_and_reactivating_through_put` | 1 |  |
| `TestEdges::test_a_valid_but_unissued_refresh_token_is_refused` | 1 | Correctly signed, but no row backs it -- e.g. minted before a key rotation. |
| `TestEdges::test_filters_by_activity` | 1 |  |
| `TestEdges::test_an_engineers_specialty_can_be_changed` | 1 |  |
| `TestEdges::test_renaming_an_engineer_keeps_their_profile` | 1 |  |
| `TestEdges::test_updating_an_unknown_user_is_404` | 1 |  |
| `TestEdges::test_losing_an_admin_create_race_is_a_conflict` | 1 |  |
| `TestMe::test_a_refresh_token_is_refused` | 1 |  |
| `TestMe::test_a_malformed_x_acme_authorization_is_refused` | 4 | Present but not `Bearer <token>`: refused, never silently ignored. |
| `TestMe::test_the_token_may_travel_in_x_acme_authorization` | 1 | The header the browser sends: CloudFront overwrites `Authorization`. |
| `TestMe::test_no_token_is_401_in_the_envelope` | 1 |  |
| `TestMe::test_x_acme_authorization_wins_over_the_edge_signature` | 1 | What the Lambda actually receives through CloudFront: both headers. |
| `TestMe::test_returns_the_caller` | 1 |  |
| `TestMe::test_a_deactivated_user_is_locked_out_immediately` | 1 |  |
| `TestMe::test_role_comes_from_the_database_not_the_token` | 1 | S7: a token carries no authority of its own. |
| `TestMe::test_an_expired_access_token_says_so` | 1 | So the client knows to refresh rather than sign in. |
| `TestMe::test_an_engineer_sees_their_profile` | 1 |  |
| `TestLogin::test_every_failure_looks_the_same` | 3 |  |
| `TestLogin::test_five_failures_lock_the_account` | 1 |  |
| `TestLogin::test_an_expired_lock_lets_the_user_back_in` | 1 |  |
| `TestLogin::test_the_email_is_case_insensitive` | 1 |  |
| `TestLogin::test_failures_are_persisted_despite_the_401` | 1 | The request rolls back on error; the counter must not roll back with it. |
| `TestLogin::test_returns_a_token_pair` | 1 |  |
| `TestLogin::test_success_resets_the_counter` | 1 |  |
| `TestChangePassword::test_changes_it_and_ends_every_session` | 1 |  |
| `TestChangePassword::test_a_wrong_current_password_is_a_field_error` | 1 |  |
| `TestChangePassword::test_requires_authentication` | 1 |  |
| `TestLogout::test_ends_this_device` | 1 |  |
| `TestLogout::test_an_unknown_token_is_still_204` | 1 | Not an oracle for which tokens exist. |
| `TestLogout::test_other_devices_survive` | 1 |  |
| `TestCreateUser::test_an_engineer_without_a_specialty_is_refused` | 1 |  |
| `TestCreateUser::test_creates_an_engineer_with_a_profile` | 1 |  |
| `TestCreateUser::test_a_duplicate_email_is_a_conflict` | 1 |  |
| `TestCreateUser::test_the_new_user_can_sign_in` | 1 |  |
| `TestRouteContract::test_every_other_route_rejects_an_anonymous_caller` | 1 | A route added without the auth dependency fails here, not in production. |
| `TestRouteContract::test_the_public_list_matches_reality` | 1 | A stale allowlist entry would silently exempt a future route of that name. |
| `TestRegister::test_a_taken_email_gets_the_identical_response` | 1 | No account enumeration: body and status match the new-account case. |
| `TestRegister::test_the_email_is_normalised` | 1 |  |
| `TestRegister::test_other_domains_are_refused` | 2 |  |
| `TestRegister::test_creates_an_employee` | 1 |  |
| `TestRegister::test_supplying_a_role_is_refused` | 1 |  |
| `TestRegister::test_the_taken_path_does_not_change_the_existing_account` | 1 |  |
| `TestRegister::test_a_password_over_72_bytes_is_refused` | 1 | 30 emoji is 30 characters but 120 bytes: bcrypt would silently truncate it. |
| `TestRegister::test_a_short_password_is_refused_without_echoing_it` | 1 |  |
| `TestDeactivateUser::test_an_admin_cannot_delete_themselves` | 1 |  |
| `TestDeactivateUser::test_soft_deletes` | 1 |  |
| `TestDeactivateUser::test_the_user_can_no_longer_sign_in_or_use_old_tokens` | 1 |  |
| `TestDeactivateUser::test_is_idempotent` | 1 |  |
| `TestDeactivateUser::test_an_unknown_id_is_404` | 1 |  |
| `TestUserAdminAccess::test_non_admins_are_forbidden` | 2 |  |
| `TestUserAdminAccess::test_forbidden_does_not_depend_on_the_target_existing` | 1 | The role gate runs before the lookup, so 403 confirms nothing. |
| `TestUpdateUser::test_an_admin_cannot_demote_themselves` | 1 |  |
| `TestUpdateUser::test_renames` | 1 |  |
| `TestUpdateUser::test_an_admin_cannot_deactivate_themselves` | 1 |  |
| `TestUpdateUser::test_promotion_to_engineer_needs_a_specialty` | 1 |  |
| `TestUpdateUser::test_promotion_with_a_specialty_creates_the_profile` | 1 |  |
| `TestUpdateUser::test_a_role_change_ends_the_targets_sessions` | 1 | A demoted admin must lose access now, not in thirty minutes. |
| `TestUpdateUser::test_an_engineer_with_open_work_cannot_be_demoted` | 1 | Their incidents would strand: nobody would hold assigned_engineer on them. |
| `TestUpdateUser::test_a_specialty_for_a_non_engineer_is_refused` | 1 |  |
| `TestUpdateUser::test_null_on_a_required_field_is_refused` | 1 |  |
| `TestGetUser::test_returns_the_user` | 1 |  |
| `TestGetUser::test_an_unknown_id_is_404` | 1 |  |
| `TestGetUser::test_a_malformed_id_is_400` | 1 |  |
| `TestFindByEmail::test_no_match_is_an_empty_page_not_a_404` | 1 |  |
| `TestFindByEmail::test_finds_exactly_one_user` | 1 |  |
| `TestFindByEmail::test_find_then_promote` | 1 | The whole admin journey: look up by email, promote, and the change bites. |
| `TestFindByEmail::test_is_case_insensitive` | 1 |  |
| `TestProfileFields::test_demotion_to_employee_needs_an_occupation` | 1 |  |
| `TestProfileFields::test_registration_stores_both` | 1 |  |
| `TestProfileFields::test_admin_create_stores_both` | 1 |  |
| `TestProfileFields::test_promotion_clears_the_occupation` | 1 | "Occupation exactly when Employee" must survive a role change. |
| `TestProfileFields::test_me_shows_both` | 1 |  |
| `TestProfileFields::test_an_admin_can_correct_a_birth_date_but_not_into_the_future` | 1 |  |
| `TestProfileFields::test_a_future_birth_date_is_a_field_error` | 1 |  |
| `TestProfileFields::test_an_occupation_for_an_engineer_is_refused` | 1 |  |
| `TestProfileFields::test_an_employee_can_change_occupation` | 1 |  |
| `TestLogoutAll::test_signing_in_again_works_at_once` | 1 | A new token issued in the same second as the cutoff must not be born revoked. |
| `TestLogoutAll::test_kills_every_token` | 1 |  |
| `TestListUsers::test_an_unknown_query_parameter_is_refused` | 1 |  |
| `TestListUsers::test_filters_by_role` | 1 |  |
| `TestListUsers::test_pages_with_a_total` | 1 |  |
| `TestListUsers::test_an_unknown_sort_is_refused` | 1 |  |
| `TestListUsers::test_search_matches_name_or_email_and_escapes_wildcards` | 1 |  |

#### `tests/integration/test_migrations.py` (9 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestConstraints::test_enum_columns_carry_a_check` | 1 |  |
| `TestConstraints::test_no_naive_timestamp_columns` | 1 | Mixing naive and aware timestamps makes SLA arithmetic wrong. |
| `TestConstraints::test_constraint_names_are_unique_within_each_table` | 1 | Two columns sharing an enum in one table collide on the CHECK name. |
| `TestConstraints::test_naming_convention_was_applied` | 1 | An auto-named constraint cannot be reliably dropped on downgrade. |
| `TestReversibility::test_downgrade_then_upgrade_is_clean` | 1 | An autogenerated downgrade is usually the part nobody checks. |
| `TestAppliedSchema::test_nothing_pending` | 1 |  |
| `TestAppliedSchema::test_every_expected_table_exists` | 1 |  |
| `TestAppliedSchema::test_alembic_stamped_at_head` | 1 |  |
| `TestNoModelDrift::test_no_pending_autogenerate_diff` | 1 | Catches the classic rot: a model edited without a migration. |

#### `tests/integration/test_scoping_db.py` (15 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestInternalNotes::test_staff_see_both` | 2 |  |
| `TestInternalNotes::test_an_employee_sees_only_public_notes` | 1 |  |
| `TestInternalNotes::test_the_internal_body_never_reaches_an_employee` | 1 |  |
| `TestSingleItemReads::test_a_nonexistent_id_is_indistinguishable` | 1 | Both produce None, so the caller cannot tell them apart. |
| `TestSingleItemReads::test_an_out_of_scope_read_returns_nothing` | 1 |  |
| `TestSingleItemReads::test_an_admin_reading_the_same_id_succeeds` | 1 | The pair that proves it: same id, one caller sees it, one does not. |
| `TestCountsAndFilters::test_a_filter_cannot_widen_scope` | 1 | Successive where() clauses AND, so a user filter stays inside scope. |
| `TestCountsAndFilters::test_a_count_does_not_leak_out_of_scope_rows` | 1 | Pagination totals must go through the same helper, or the number |
| `TestWhoSeesWhat::test_an_engineer_does_not_see_unassigned_work` | 1 | Assignment, not the Engineer role, is what grants visibility. |
| `TestWhoSeesWhat::test_an_employee_does_not_see_another_employees` | 1 |  |
| `TestWhoSeesWhat::test_an_employee_sees_only_their_own` | 1 |  |
| `TestWhoSeesWhat::test_an_engineer_does_not_see_incidents_they_reported` | 1 | Reporting grants an engineer nothing; only an admin's assignment does. |
| `TestWhoSeesWhat::test_an_admin_sees_everything` | 1 |  |
| `TestWhoSeesWhat::test_an_engineer_sees_assigned_work` | 1 |  |

#### `tests/integration/test_readyz.py` (4 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestReadyz::test_recovers_once_migrated` | 1 |  |
| `TestReadyz::test_migrated_database_is_ready` | 1 |  |
| `TestReadyz::test_never_exposes_the_revision` | 1 | A revision id maps to a public commit. |
| `TestReadyz::test_pending_migrations_report_503` | 1 | A forgotten migrate-cloud should be loud, not a later UndefinedTable. |

#### `tests/integration/test_seed.py` (15 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestSeedAction::test_db_current_reports_head` | 1 |  |
| `TestSeedAction::test_seeds_with_matching_confirmation` | 1 |  |
| `TestSeedAction::test_the_result_never_echoes_the_password` | 1 |  |
| `TestSeed::test_covers_every_role` | 1 |  |
| `TestSeed::test_uses_the_supplied_password` | 1 |  |
| `TestSeed::test_is_strictly_additive` | 1 | Re-seeding must not undo an admin's changes or reset a chosen password. |
| `TestSeed::test_creates_every_demo_account` | 1 |  |
| `TestSeed::test_is_idempotent` | 1 |  |
| `TestSeed::test_skips_an_address_someone_registered_first` | 1 |  |
| `TestSeed::test_refuses_a_weak_password` | 1 |  |
| `TestSeed::test_engineers_get_profiles` | 1 |  |
| `TestSeed::test_creates_the_facilities_and_categories` | 1 |  |
| `TestSeed::test_creates_incidents_with_legal_histories` | 1 | Every history is a chain of real edges ending at the stored status. |
| `TestSeed::test_stamps_follow_the_workflow_policy` | 1 |  |
| `TestSeed::test_incidents_follow_an_account_registered_first` | 1 | A reporter who registered before the seed keeps their id; incidents use it. |

#### `tests/integration/test_model_constraints.py` (29 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestDeletePolicy::test_reporter_cannot_be_deleted` | 1 | RESTRICT: deleting a user must never erase incident history. |
| `TestDeletePolicy::test_notes_cascade_with_their_incident` | 1 |  |
| `TestUniqueness::test_floor_level_unique_per_building` | 1 |  |
| `TestUniqueness::test_seat_code_unique_per_floor` | 1 |  |
| `TestUniqueness::test_engineer_profile_is_one_to_one` | 1 |  |
| `TestUniqueness::test_same_level_allowed_in_another_building` | 1 | Every building has a third floor; that must not collide. |
| `TestUniqueness::test_email_is_unique` | 1 |  |
| `TestUniqueness::test_same_seat_code_allowed_on_another_floor` | 1 |  |
| `TestUniqueness::test_sibling_categories_cannot_share_a_name` | 1 |  |
| `TestUniqueness::test_refresh_token_hash_is_unique` | 1 |  |
| `TestStampDefaults::test_created_at_is_populated_and_aware` | 1 |  |
| `TestStampDefaults::test_stamps_start_null` | 4 | A stamp must mean "this happened", never "this row was created". |
| `TestPersistenceRoundTrip::test_writes_are_visible_to_a_second_session` | 1 | Guards the identity-map trap: expire_on_commit=False can mask a |
| `TestPersistenceRoundTrip::test_app_secret_upsert_is_race_safe` | 1 | Two cold Lambdas can reach the secret bootstrap at the same time. |
| `TestIncidentLocation::test_dangling_building_is_rejected` | 1 |  |
| `TestIncidentLocation::test_floor_and_seat_may_be_omitted` | 1 | A lobby has no seat and a lift has no floor. |
| `TestIncidentLocation::test_building_is_required` | 1 |  |
| `TestEnumChecks::test_every_priority_is_accepted` | 4 |  |
| `TestEnumChecks::test_orm_rejects_an_invalid_role_before_the_database` | 1 | validate_strings catches it client-side: the first of two defences. |
| `TestEnumChecks::test_every_declared_role_is_accepted` | 3 |  |
| `TestEnumChecks::test_database_check_rejects_an_invalid_role` | 1 | Raw SQL bypasses the ORM type, so this proves the CHECK really exists. |

#### `tests/integration/test_incidents_api.py` (170 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestTransitionEdges::test_an_engineer_cannot_pick_up_their_own_report` | 1 | Reporting it does not make it theirs: 404 until an admin assigns it. |
| `TestTransitionEdges::test_an_admin_takes_engineer_edges_but_cannot_invent_one` | 1 |  |
| `TestTransitionEdges::test_the_admin_triage_journey` | 1 | Employee reports; the engineer cannot see it until the admin assigns it. |
| `TestTransitionEdges::test_reopen_keeps_first_stamps_and_re_resolve_overwrites_the_latest` | 1 |  |
| `TestTransitionEdges::test_the_assigned_engineer_starts_work_themselves` | 1 |  |
| `TestTransitionEdges::test_resolve_close_and_the_stamps` | 1 |  |
| `TestTransitionEdges::test_open_to_in_progress_stamps_and_assigns` | 1 |  |
| `TestTransitionEdges::test_block_and_unblock` | 1 |  |
| `TestTransitionEdges::test_open_to_closed_without_work` | 1 |  |
| `TestNotifications::test_only_your_own_are_listed` | 1 |  |
| `TestNotifications::test_reassigning_tells_the_new_engineer_only` | 1 |  |
| `TestNotifications::test_assigning_through_edit_tells_the_engineer` | 1 |  |
| `TestNotifications::test_the_reporter_closing_their_own_incident_tells_the_admins_only` | 1 |  |
| `TestNotifications::test_an_admin_reporting_is_not_told_about_their_own` | 1 |  |
| `TestNotifications::test_marking_one_read` | 1 |  |
| `TestNotifications::test_saving_the_same_assignee_again_says_nothing_new` | 1 |  |
| `TestNotifications::test_a_failed_assignment_leaves_no_notification` | 1 |  |
| `TestNotifications::test_every_active_admin_is_told_about_a_report` | 1 |  |
| `TestNotifications::test_assigning_through_a_transition_tells_the_engineer` | 1 |  |
| `TestNotifications::test_someone_elses_notification_is_404_not_403` | 1 |  |
| `TestNotifications::test_deleting_the_incident_removes_its_notifications` | 1 |  |
| `TestNotifications::test_resolving_tells_the_reporter_and_the_admins` | 1 |  |
| `TestNotifications::test_an_admin_closing_tells_the_reporter_but_not_themselves` | 1 |  |
| `TestNotifications::test_the_list_is_newest_first_with_the_unread_total` | 1 |  |
| `TestNotifications::test_marking_all_read` | 1 |  |
| `TestHistory::test_says_who_assigned_whom` | 1 | Each hand-over names the engineer; a re-save of the same one is silent. |
| `TestHistory::test_pages` | 1 |  |
| `TestHistory::test_reads_forwards_by_default_and_backwards_on_request` | 1 |  |
| `TestHistory::test_is_scoped_like_its_parent` | 1 |  |
| `TestWorkflow::test_serialises_the_whole_state_machine` | 1 |  |
| `TestDelete::test_a_missing_id_is_404` | 1 |  |
| `TestDelete::test_removes_the_incident_and_everything_beneath_it` | 1 |  |
| `TestDelete::test_non_admins_are_forbidden_whether_or_not_it_exists` | 2 |  |
| `TestGet::test_an_employee_has_no_moves_on_their_open_incident` | 1 |  |
| `TestGet::test_the_reporter_may_close_or_reopen_a_resolved_incident` | 1 |  |
| `TestGet::test_the_404_200_pair_on_the_same_id` | 1 | T61 at the HTTP layer: one id, one caller sees it, one does not. |
| `TestGet::test_a_malformed_id_is_a_400` | 1 |  |
| `TestGet::test_the_assigned_engineer_sees_block_and_resolve` | 1 |  |
| `TestGet::test_an_existing_assignee_is_not_asked_for_again` | 1 |  |
| `TestGet::test_an_admin_is_offered_both_open_edges_with_their_requirements` | 1 |  |
| `TestGet::test_a_nonexistent_id_is_indistinguishable` | 1 |  |
| `TestTransitionOrderOfChecks::test_4_starting_work_needs_an_assignee` | 1 |  |
| `TestTransitionOrderOfChecks::test_2_nothing_leaves_closed` | 4 |  |
| `TestTransitionOrderOfChecks::test_5_the_assignee_must_be_an_active_engineer` | 1 |  |
| `TestTransitionOrderOfChecks::test_3_an_unassigned_engineer_may_not_block` | 1 | The other engineer cannot even see it: 404, not 403 (scoping first). |
| `TestTransitionOrderOfChecks::test_1_out_of_scope_is_404` | 1 |  |
| `TestTransitionOrderOfChecks::test_4_a_required_note_must_be_present_and_non_blank` | 3 |  |
| `TestTransitionOrderOfChecks::test_an_unknown_target_is_400` | 1 |  |
| `TestTransitionOrderOfChecks::test_3_wrong_actor_is_403_before_fields_are_checked` | 1 | The employee omits the note too; the actor check fires first. |
| `TestTransitionOrderOfChecks::test_3_only_the_reporter_or_admin_closes` | 1 |  |
| `TestTransitionOrderOfChecks::test_5_an_employee_may_not_reassign_on_reopen` | 1 |  |
| `TestTransitionOrderOfChecks::test_2_no_edge_is_409_even_for_an_admin` | 3 |  |
| `TestTransitionOrderOfChecks::test_5_an_engineer_may_not_assign_anyone` | 2 | Not even themselves: assignment is an admin's act, full stop. |
| `TestUpdate::test_omitted_fields_are_unchanged_and_null_clears` | 1 |  |
| `TestUpdate::test_the_assignee_must_be_an_active_engineer` | 3 |  |
| `TestUpdate::test_an_outsider_gets_404_not_403` | 1 |  |
| `TestUpdate::test_null_on_a_required_field_is_refused` | 1 |  |
| `TestUpdate::test_an_empty_body_is_a_no_op` | 1 |  |
| `TestUpdate::test_the_reporter_may_not_touch_priority_or_assignee` | 2 |  |
| `TestUpdate::test_a_closed_incident_is_immutable` | 1 |  |
| `TestUpdate::test_the_assigned_engineer_may_not_edit_the_text` | 1 |  |
| `TestUpdate::test_the_reporter_edits_the_text_while_open` | 1 |  |
| `TestUpdate::test_status_is_not_settable_here` | 1 |  |
| `TestUpdate::test_an_admin_changes_priority_and_assignee` | 1 |  |
| `TestUpdate::test_the_reporter_may_not_edit_once_work_started` | 1 |  |
| `TestUpdate::test_unassigning_is_allowed_only_while_open` | 1 |  |
| `TestEscalationQueue::test_approval_raises_priority_one_level_and_stamps_the_decision` | 1 |  |
| `TestEscalationQueue::test_pending_is_not_a_decision` | 1 |  |
| `TestEscalationQueue::test_an_unknown_escalation_is_404` | 1 |  |
| `TestEscalationQueue::test_rejection_leaves_priority_alone` | 1 |  |
| `TestEscalationQueue::test_deciding_twice_is_409` | 1 |  |
| `TestEscalationQueue::test_pending_oldest_first_by_default` | 1 |  |
| `TestEscalationQueue::test_a_second_approval_cannot_pass_critical` | 1 | Approve at High -> Critical, then a request made before that lands on Critical. |
| `TestEscalationQueue::test_the_queue_filters_by_status` | 1 |  |
| `TestEscalationQueue::test_the_queue_and_decisions_are_admin_only` | 2 |  |
| `TestEscalationQueue::test_the_queue_can_span_every_status_when_asked_in_code` | 1 | No query string can clear the default; a future "all" view calls this directly. |
| `TestEscalationQueue::test_each_row_names_the_incident_as_it_is_now` | 1 | The queue is read without a fetch per incident, and reflects an approval. |
| `TestCreate::test_sets_the_location_header` | 1 |  |
| `TestCreate::test_a_bad_category_is_refused` | 2 |  |
| `TestCreate::test_every_role_may_report` | 2 |  |
| `TestCreate::test_every_bad_reference_is_reported_at_once` | 1 |  |
| `TestCreate::test_an_unknown_building_is_a_field_error` | 1 |  |
| `TestCreate::test_a_server_controlled_field_is_refused` | 3 |  |
| `TestCreate::test_opens_an_incident_with_its_first_history_row` | 1 |  |
| `TestCreate::test_a_seat_off_the_floor_is_refused` | 1 |  |
| `TestCreate::test_a_floor_of_another_building_is_refused` | 1 |  |
| `TestCreate::test_an_inactive_building_is_refused` | 1 |  |
| `TestCreate::test_a_seat_without_a_floor_is_refused` | 1 |  |
| `TestList::test_filters` | 4 |  |
| `TestList::test_pages_with_a_scoped_total` | 1 |  |
| `TestList::test_an_admin_sees_everything` | 1 |  |
| `TestList::test_every_row_carries_its_target_and_where_it_stands` | 1 | `due_at` is creation plus the D8 target; a fresh incident is on track. |
| `TestList::test_a_filter_cannot_widen_scope` | 1 |  |
| `TestList::test_filters_by_building_category_and_assignee` | 1 |  |
| `TestList::test_sort_by_due_orders_by_target_not_by_age` | 1 | A Critical reported last is due first; a Low reported first is due last. |
| `TestList::test_rejects_anything_off_the_allowlist` | 6 |  |
| `TestList::test_search_escapes_wildcards` | 1 |  |
| `TestList::test_an_employee_sees_only_their_own` | 1 |  |
| `TestList::test_default_order_is_newest_first` | 1 |  |
| `TestList::test_sorts_by_title_and_status` | 1 |  |
| `TestList::test_filters_by_creation_date` | 1 |  |
| `TestList::test_overdue_is_open_work_past_its_target` | 1 | Backdating puts a Critical past 4 h; resolving it takes it out of overdue. |
| `TestList::test_an_engineer_sees_only_what_is_assigned_to_them` | 1 | Not even their own report, until an admin assigns it to them. |
| `TestList::test_sorts_priority_by_urgency_not_alphabet` | 1 |  |
| `TestNotes::test_the_reporter_adds_a_public_note` | 1 |  |
| `TestNotes::test_a_blank_note_is_refused` | 1 |  |
| `TestNotes::test_notes_are_scoped_like_their_parent` | 1 |  |
| `TestNotes::test_an_employee_asking_for_internal_is_refused_not_downgraded` | 1 |  |
| `TestNotes::test_internal_notes_are_hidden_from_the_employee_and_shown_to_staff` | 1 |  |
| `TestNotes::test_a_closed_incident_takes_no_notes` | 1 |  |
| `TestReports::test_buildings_busiest_first_with_quiet_active_ones` | 1 |  |
| `TestReports::test_engineers_most_completed_first` | 1 |  |
| `TestReports::test_admin_only` | 10 |  |
| `TestReports::test_volume_per_day_and_week` | 1 |  |
| `TestReports::test_bad_parameters_are_400` | 5 |  |
| `TestReports::test_summary_counts_and_backlog_age` | 1 |  |
| `TestReports::test_engineers_with_nothing_still_appear` | 1 |  |
| `TestReports::test_sla_by_priority` | 1 |  |
| `TestReports::test_sla_by_building_and_category` | 2 |  |
| `TestReports::test_the_window_and_building_filter_apply` | 1 |  |
| `TestRouteContract::test_static_paths_are_not_swallowed_by_the_id_route` | 1 | `/workflow` must match its own route, not `/{incident_id}` as a bad UUID. |
| `TestRouteContract::test_every_other_route_rejects_an_anonymous_caller` | 1 |  |
| `TestEscalations::test_critical_cannot_go_higher` | 1 |  |
| `TestEscalations::test_finished_work_cannot_be_escalated` | 2 |  |
| `TestEscalations::test_an_admin_who_can_see_it_but_did_not_report_it_is_forbidden` | 1 |  |
| `TestEscalations::test_one_pending_request_at_a_time` | 1 |  |
| `TestEscalations::test_listing_for_an_incident_is_scoped` | 1 |  |
| `TestEscalations::test_the_assigned_engineer_requests_one` | 1 |  |
| `TestEscalations::test_the_reporter_requests_one` | 1 |  |
| `TestEscalations::test_an_outsider_gets_404` | 1 |  |

#### `tests/integration/test_jwt_secret.py` (8 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestSecrecy::test_tokens_signed_with_it_verify` | 1 | End to end: the provisioned key actually works for its purpose. |
| `TestSecrecy::test_the_secret_is_never_in_a_repr` | 1 |  |
| `TestProvisioning::test_creates_a_secret_on_first_use` | 1 |  |
| `TestProvisioning::test_is_stable_across_calls` | 1 | A key that changed per call would invalidate every issued token. |
| `TestProvisioning::test_concurrent_provisioning_converges` | 1 | Two cold Lambdas can reach this together; the loser must take the |
| `TestProvisioning::test_is_cached_after_the_first_read` | 1 | One query per cold start, not one per request. |
| `TestProvisioning::test_an_existing_secret_is_reused_not_replaced` | 1 | A second cold start must adopt the first one's key. |
| `TestProvisioning::test_has_real_entropy` | 1 | The whole reason this exists rather than deriving from POSTGRES_PASS, |

### End to end over HTTP (7 cases in 1 file)

#### `tests/e2e/test_auth_journey.py` (7 cases)

| Test | Cases | What it checks |
|---|---|---|
| `TestRegistration::test_the_row_is_visible_on_a_new_connection` | 1 |  |
| `TestRegistration::test_a_second_registration_changes_nothing` | 1 | The response is identical and the stored account is untouched. |
| `TestServer::test_an_unauthenticated_request_carries_the_challenge` | 1 |  |
| `TestServer::test_identifies_itself` | 1 |  |
| `TestJourney::test_logout_retires_the_device_and_logout_all_retires_the_user` | 1 |  |
| `TestJourney::test_register_login_me_refresh_and_replay` | 1 |  |
| `TestJourney::test_password_change_invalidates_every_earlier_session` | 1 |  |

## Frontend coverage by file

| File | Statements | Branches | Functions | Lines |
|---|---|---|---|---|
| `src/App.jsx` | 92.3% | 87.5% | 100.0% | 91.7% |
| `src/auth/AuthContext.js` | 80.0% | 50.0% | 100.0% | 100.0% |
| `src/auth/AuthProvider.jsx` | 97.0% | 85.0% | 100.0% | 100.0% |
| `src/auth/RequireRole.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/AppShell.jsx` | 71.4% | 75.0% | 57.1% | 69.2% |
| `src/components/AuthLayout.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/ConfirmDialog.jsx` | 100.0% | 78.6% | 100.0% | 100.0% |
| `src/components/ErrorBoundary.jsx` | 90.0% | 100.0% | 83.3% | 88.9% |
| `src/components/Field.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/IncidentChips.jsx` | 100.0% | 70.0% | 100.0% | 100.0% |
| `src/components/Notice.jsx` | 85.7% | 92.8% | 100.0% | 83.3% |
| `src/components/NotificationBell.jsx` | 95.5% | 90.0% | 83.3% | 97.6% |
| `src/components/OfflineBanner.jsx` | 100.0% | 50.0% | 100.0% | 100.0% |
| `src/components/PageState.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/PasswordField.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/RecordDialog.jsx` | 83.1% | 80.9% | 86.7% | 80.3% |
| `src/components/RouteFocus.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/SelectField.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/SkipLink.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/ThemeToggle.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/WakingBanner.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/admin/IncidentOverview.jsx` | 100.0% | 90.5% | 100.0% | 100.0% |
| `src/components/admin/UserDialog.jsx` | 81.2% | 77.8% | 100.0% | 82.8% |
| `src/components/charts/BarList.jsx` | 100.0% | 50.0% | 100.0% | 100.0% |
| `src/components/charts/PieChart.jsx` | 100.0% | 86.7% | 100.0% | 100.0% |
| `src/components/charts/StackedBars.jsx` | 94.4% | 81.2% | 89.7% | 95.2% |
| `src/components/charts/StackedColumns.jsx` | 83.0% | 56.0% | 66.7% | 84.9% |
| `src/components/charts/StatTile.jsx` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/components/facilities/BuildingsPanel.jsx` | 82.2% | 79.3% | 78.1% | 82.7% |
| `src/components/facilities/CategoriesPanel.jsx` | 80.4% | 82.7% | 77.3% | 77.5% |
| `src/components/facilities/EngineersPanel.jsx` | 82.1% | 70.6% | 68.8% | 82.1% |
| `src/components/facilities/RecordList.jsx` | 94.1% | 100.0% | 90.0% | 94.1% |
| `src/components/incident/EscalationDecisionDialog.jsx` | 100.0% | 78.9% | 100.0% | 100.0% |
| `src/components/incident/EscalationPanel.jsx` | 79.1% | 71.4% | 83.3% | 81.6% |
| `src/components/incident/HistoryList.jsx` | 100.0% | 78.6% | 100.0% | 100.0% |
| `src/components/incident/NotesSection.jsx` | 76.9% | 59.1% | 83.3% | 80.0% |
| `src/components/incident/TransitionDialog.jsx` | 85.4% | 61.4% | 88.9% | 87.5% |
| `src/components/incident/TriagePanel.jsx` | 95.8% | 65.7% | 100.0% | 95.5% |
| `src/config.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/charts.js` | 100.0% | 50.0% | 100.0% | 100.0% |
| `src/lib/download.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/formErrors.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/format.js` | 92.1% | 90.3% | 100.0% | 96.5% |
| `src/lib/incidents.js` | 96.2% | 91.3% | 100.0% | 100.0% |
| `src/lib/notifications.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/reports.js` | 100.0% | 96.4% | 100.0% | 100.0% |
| `src/lib/useLoad.js` | 100.0% | 89.5% | 100.0% | 100.0% |
| `src/lib/usePageTitle.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/useViewport.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/useWidth.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/lib/users.js` | 100.0% | 83.3% | 100.0% | 100.0% |
| `src/pages/EscalationsPage.jsx` | 93.1% | 91.7% | 85.7% | 92.6% |
| `src/pages/FacilitiesPage.jsx` | 82.3% | 75.0% | 71.4% | 80.0% |
| `src/pages/IncidentPage.jsx` | 93.2% | 69.1% | 90.3% | 96.6% |
| `src/pages/IncidentsPage.jsx` | 95.6% | 96.0% | 90.5% | 95.1% |
| `src/pages/LandingPage.jsx` | 100.0% | 93.3% | 100.0% | 100.0% |
| `src/pages/LoginPage.jsx` | 100.0% | 85.7% | 100.0% | 100.0% |
| `src/pages/NewIncidentPage.jsx` | 97.7% | 82.2% | 100.0% | 97.2% |
| `src/pages/RegisterPage.jsx` | 98.0% | 91.2% | 100.0% | 97.6% |
| `src/pages/ReportsPage.jsx` | 95.5% | 88.6% | 94.3% | 94.8% |
| `src/pages/UsersPage.jsx` | 86.1% | 92.7% | 78.0% | 87.8% |
| `src/pwa.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/services/api.js` | 98.8% | 92.8% | 100.0% | 100.0% |
| `src/services/auth.js` | 88.9% | 100.0% | 88.9% | 88.9% |
| `src/services/facilities.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/services/incidents.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/services/notifications.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/services/readiness.js` | 97.9% | 84.6% | 100.0% | 100.0% |
| `src/services/reports.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/services/session.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| `src/theme.js` | 100.0% | 100.0% | 100.0% | 100.0% |
| **Total** | **92.7%** | **84.3%** | **90.9%** | **93.3%** |

## Frontend tests (214 in 41 files)

#### `frontend/src/App.test.jsx` (4)

- **App, signed out**
  - shows the landing page at the root
  - still sends a deep link to sign in
- **App, while the account loads**
  - shows the frame of the page rather than a flash of the sign-in screen
  - explains a failed account load and offers to retry or sign out

#### `frontend/src/pwa.test.js` (3)

- **registerServiceWorker**
  - registers the offline shell after load in a production build, and swallows a refusal
  - does nothing in development, where a worker would fight hot reload
  - does nothing where the browser has no service workers

#### `frontend/src/auth/AuthProvider.test.jsx` (7)

- **AuthProvider**
  - is anonymous without a stored session and never calls the API
  - loads the user from /me when a session is stored, rather than decoding the token
  - clears a session the API rejects, which makes the app anonymous
  - reports any other failure and retries from the stored session
  - retrying without a session lands on anonymous
  - signs out locally first and revokes the refresh token best-effort
  - loads the user when a session appears later, and keeps them across a rotation

#### `frontend/src/auth/RequireRole.test.jsx` (2)

- **RequireRole**
  - renders the screen for a listed role
  - sends anyone else to the incident list

#### `frontend/src/components/AppShell.test.jsx` (4)

- **AppShell**
  - shows the management links to an admin
  - shows only the incident list to everyone else
  - gives everyone a notification bell, since reporters hear about outcomes too
  - starts with a skip link that targets the main landmark

#### `frontend/src/components/ErrorBoundary.test.jsx` (3)

- **ErrorBoundary**
  - renders its children while nothing throws
  - replaces a throwing tree with an alert and logs the error
  - tries again by remounting the children

#### `frontend/src/components/IncidentChips.test.jsx` (4)

- **slaLabel**
  - counts down while open, says how late once breached, and grades finished work
  - trusts the clock over a stale on_track when the deadline has since passed
- **SlaChip**
  - draws nothing for a row without the field
  - carries the deadline as its tooltip

#### `frontend/src/components/Notice.test.jsx` (3)

- **Notice**
  - announces a success politely
  - announces a failure as an alert that stays until dismissed
  - renders nothing without a notice

#### `frontend/src/components/NotificationBell.test.jsx` (6)

- **NotificationBell**
  - loads on mount and shows the unread count
  - opens a menu that phrases each notification and marks it read on the way to the incident
  - marks everything read from the menu
  - says when there is nothing
  - polls while the tab is visible and refreshes on focus
  - keeps what it last showed when a poll fails

#### `frontend/src/components/OfflineBanner.test.jsx` (2)

- **OfflineBanner**
  - stays quiet while online and speaks up when the connection drops
  - starts shown when the page loads offline

#### `frontend/src/components/RouteFocus.test.jsx` (2)

- **RouteFocus**
  - leaves focus alone on the first render
  - moves focus to the page after a navigation

#### `frontend/src/components/ThemeToggle.test.jsx` (3)

- **ThemeToggle**
  - offers the dark theme when the app is light
  - switches the scheme and remembers the choice
  - starts from a remembered dark choice

#### `frontend/src/components/WakingBanner.test.jsx` (1)

- **WakingBanner**
  - shows while the API client waits for the database and counts the seconds

#### `frontend/src/lib/formErrors.test.js` (6)

- **humanise**
  - strips the Pydantic prefix and makes a sentence
  - leaves a finished sentence alone
  - falls back when the message is missing
- **splitDetails**
  - routes known fields inline and the rest to the form
  - keeps only the first message per field
  - tolerates a missing details list

#### `frontend/src/lib/format.test.js` (5)

- **formatDuration**
  - shows an em dash when nothing was measured
  - picks the two largest units that matter
- **formatPercent**
  - rounds a ratio to whole percent and dashes the unknown
- **dates**
  - turns any date into the API form in UTC
  - formats a calendar day without sliding across a timezone

#### `frontend/src/lib/notifications.test.js` (5)

- **describeNotification**
  - names who assigned the work
  - names who reported the incident
  - still reads when the actor is gone
  - tells the reporter about the outcome
  - falls back to the title for a kind it does not know

#### `frontend/src/lib/reports.test.js` (14)

- **ranges**
  - counts the inclusive days ending today
  - recognises a preset by its exact range
- **buildSeries**
  - keeps the domain order and slot for statuses even when some are absent
  - sorts categories and folds the tail into Other
- **bucketStarts**
  - lists every day inclusive
  - aligns weeks to the Monday on or before the start, as the API does
- **pivotVolume**
  - zero-fills buckets and folds unknown groups into Other
  - drops a group that is neither a series nor foldable
- **summary helpers**
  - counts everything not closed as backlog
- **csv export**
  - quotes only the cells that need it
  - writes a header and one CRLF-terminated row per incident with building names
  - walks pages until the total is reached and stops on an empty page
- **overview bars**
  - splits a building into finished and open, longest first, keeping critical aside
  - adds the unresolved series only when an assigned incident was closed without a fix

#### `frontend/src/lib/usePageTitle.test.jsx` (2)

- **usePageTitle**
  - formats a page title after the app name, or just the app name
  - sets the document title and follows changes

#### `frontend/src/lib/useViewport.test.jsx` (3)

- **useViewport**
  - reads the theme breakpoints on a desktop
  - is narrow on a phone
  - asks for the breakpoint in pixels

#### `frontend/src/lib/useWidth.test.jsx` (2)

- **useWidth**
  - reports the initial width where ResizeObserver is missing
  - follows the observed element and ignores a zero width, then disconnects

#### `frontend/src/lib/users.test.js` (1)

- **loadLevel**
  - %i open of %i is %s

#### `frontend/src/pages/EscalationsPage.test.jsx` (5)

- **EscalationsPage**
  - lists pending requests with the incident they are about
  - approves with a note, tells the admin the new priority and reloads
  - rejects without a note and keeps the dialog open on a refusal
  - filters by status from the URL and shows decided requests read-only
  - offers a retry when the queue fails to load

#### `frontend/src/pages/FacilitiesPage.test.jsx` (9)

- **FacilitiesPage**
  - drills from buildings to floors to seats through the URL
  - adds a floor to the selected building
  - edits a building without its immutable code and sends only changes
  - retires from the row menu and shows a delete refusal inline
  - shows categories as a two-level tree and adds a sub-category under its root
  - edits a category from its row menu and deletes one after confirming
  - lists engineers with their load and edits a profile
  - shows one column at a time on a phone, with a way back
  - shows a failed list with a retry

#### `frontend/src/pages/IncidentPage.test.jsx` (11)

- **IncidentPage**
  - shows the incident, its notes, history and location
  - renders exactly the transitions the API allows and prompts for what they require
  - lets the assigned engineer start work without naming an assignee
  - never offers an engineer an assignee field, even if the API asked for one
  - shows the transition error from the API inside the dialog
  - hides the internal-note toggle from employees and adds a note
  - lets an admin triage the assignee and priority through PUT
  - offers escalation to the reporter and sends the reason
  - lets an admin approve a pending escalation from the incident
  - shows a pending escalation to its reporter without decision buttons
  - says when an incident cannot be found

#### `frontend/src/pages/IncidentsPage.test.jsx` (13)

- **IncidentsPage**
  - lists incidents with links to each one
  - stacks the rows on a phone
  - offers to report the first incident when there are none
  - puts filters in the URL and the request
  - shows each row against its response target and filters to the overdue ones
  - offers the overdue filter through the URL and sorts by due date
  - debounces the search box into the request
  - explains an empty filtered result and can clear the filters
  - shows the API message on failure and retries
  - gives admins the overview and a CSV of the filtered list, and nobody else
  - reports an export that failed instead of saving a partial file
  - offers "Assigned to me" to engineers only
  - shows the confirmation a page arrived with

#### `frontend/src/pages/LandingPage.test.jsx` (3)

- **LandingPage**
  - leads with the pitch and the two actions a visitor has
  - explains the workflow, the roles and the response targets
  - states the registration rule so nobody tries a personal address

#### `frontend/src/pages/LoginPage.test.jsx` (9)

- **LoginPage**
  - labels every input and offers registration
  - validates required fields before calling the API
  - shows the API message on bad credentials
  - maps details[] onto the fields on a 400
  - stores the session and goes home on success
  - returns to where the user was going
  - shows the notice carried over from registration
  - disables the button while the request is in flight
  - reveals the password on request

#### `frontend/src/pages/NewIncidentPage.test.jsx` (5)

- **NewIncidentPage**
  - validates before calling the API
  - cascades building to floor to seat and resets downstream choices
  - submits the report and returns to the incidents list
  - maps details[] onto the fields on a 400
  - says when the buildings cannot be loaded and can retry

#### `frontend/src/pages/RegisterPage.test.jsx` (7)

- **RegisterPage**
  - labels every input, with helper text, and links to sign-in
  - checks the domain and password length before calling the API
  - clears a field error as soon as the field changes
  - maps details[] onto the fields on a 400
  - surfaces a detail for an unknown field at form level
  - sends a normalised body and hands the notice to the sign-in screen
  - reports a network failure without losing the form

#### `frontend/src/pages/ReportsPage.test.jsx` (7)

- **ReportsPage**
  - asks for the last 30 days and shows the headline numbers
  - renders response times with formatted durations and the targets
  - draws the volume with a legend and swaps to a table
  - puts the preset, the building and the split in the URL and the requests
  - warns about an inverted range instead of asking the API
  - keeps the other sections when one report fails, and retries it
  - says when the range is empty rather than drawing nothing

#### `frontend/src/pages/UsersPage.test.jsx` (10)

- **UsersPage**
  - lists users with the default sort and marks the signed-in admin
  - puts the status filter in the URL and the request
  - creates an engineer with a specialty and reloads
  - validates before sending and shows a conflict in the dialog
  - edits a user and sends only what changed
  - locks role and active state when an admin edits themselves
  - deactivates after confirmation and shows the API refusal otherwise
  - reactivates in one click
  - stacks the rows on a phone and explains an empty filter
  - shows the API message on failure and retries

#### `frontend/src/services/api.auth.test.js` (6)

- **authedRequest**
  - attaches the bearer token in the header CloudFront leaves alone
  - refuses without a session, without calling the API
  - refreshes once on a 401 and retries with the new token
  - shares one refresh between concurrent 401s
  - ends the session when the refresh is refused
  - keeps the session when the refresh cannot reach the server

#### `frontend/src/services/api.test.js` (8)

- **request**
  - sends JSON and returns the parsed body
  - hashes the body for CloudFront-signed origin requests
  - sends no payload hash without a body
  - still sends the request where Web Crypto is unavailable
  - resolves null on 204
  - raises the envelope on a non-2xx status
  - refuses a non-JSON body even with a 200 status
  - reports a network failure in plain words

#### `frontend/src/services/api.waking.test.js` (7)

- **request while the database wakes**
  - classifies edge timeouts, service failures and no answer as possibly waking
  - waits for readiness after a CloudFront 504 and then retries a GET
  - retries a POST only when it never reached the server
  - refuses to replay a POST the server may have acted on, once the API is back
  - surfaces the original failure when the API never becomes ready
  - treats a failure while the API was ready all along as final, without a retry
  - leaves a genuine refusal alone

#### `frontend/src/services/facilities.test.js` (1)

- **facilities service**
  - %s sends %s %s

#### `frontend/src/services/readiness.test.js` (4)

- **waitUntilReady**
  - resolves at once, and silently, when the API was ready all along
  - announces the wait, polls until ready, then clears it
  - gives up at the deadline and clears the wait
  - shares one wait between concurrent callers

#### `frontend/src/services/session.test.js` (4)

- **session**
  - stores a token pair with its expiry and reads it back
  - tells subscribers on save and on clear, until they unsubscribe
  - survives storage that throws: the session is returned to the caller, not persisted
  - reads null when the stored value is not JSON

#### `frontend/src/test/a11y.test.jsx` (10)

- **accessibility (axe)**
  - landing page
  - sign in and register
  - app shell with the bell
  - incident list
  - incident detail
  - report form
  - users
  - escalation queue
  - facilities
  - reports, including their failed-load states

#### `frontend/src/components/admin/IncidentOverview.test.jsx` (8)

- **IncidentOverview**
  - charts each building as finished and open, busiest first, over the last 30 days
  - charts each engineer's completed and open work with their role, and tables the detail
  - lists who is available right now, with role and load, regardless of the range
  - lists what is overdue right now, worst first, with a link to the rest
  - says when nothing is overdue
  - says when nobody is available
  - reloads both halves for another range
  - says when there is nothing, and keeps one half when the other fails

#### `frontend/src/components/charts/PieChart.test.jsx` (3)

- **PieChart**
  - draws only the slices with a value, largest first, and reads each one out
  - shows the numbers of the hovered or focused slice in a tooltip, with its detail rows
  - folds the tail past seven slices into "Other" rather than inventing hues

#### `frontend/src/components/charts/StackedBars.test.jsx` (2)

- **StackedBars**
  - draws one labelled, focusable bar per row with a legend
  - swaps the picture for a table with the extras as columns

## End-to-end tests (4)

Playwright, `frontend/e2e`, run alone with `npm run test:e2e` (not alongside the backend suite).

| File | Line | Browser | Test |
|---|---|---|---|
| `frontend/e2e/critical-path.spec.js` | 40 | chromium | an incident goes from report to closed through the roles that own each step |
| `frontend/e2e/critical-path.spec.js` | 113 | chromium | a stranger cannot read someone else's incident |
| `frontend/e2e/proxy.spec.js` | 10 | chromium | the Vite proxy hands /api to the backend, unrewritten |
| `frontend/e2e/proxy.spec.js` | 21 | chromium | the health routes of every service are reachable through the proxy |
