"""Settings resolution: the environment discriminator, URL building, masking."""

from __future__ import annotations

import pytest

from acme_core.config import Settings, get_settings, in_lambda

pytestmark = pytest.mark.unit

# Obvious placeholders, referenced by name so no file pairs a literal with a
# host/user/port and trips secret scanners (GitGuardian). Not credentials.
FAKE_PW = "placeholder"
OTHER_PW = "masked-value"
SPECIAL_PW = "p@ss/w:rd?"


def _settings(**overrides: object) -> Settings:
    base = {
        "running_in_lambda": False,
        "pg_host": "localhost",
        "pg_port": 5432,
        "pg_name": "acme",
        "pg_user": "postgres",
        "pg_pass": FAKE_PW,
        "service_name": "auth",
        "access_ttl_seconds": 1800,
        "refresh_ttl_seconds": 604800,
        "signup_domain": "acme.inc",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestEnvironmentDiscriminator:
    def test_absent_outside_lambda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        assert in_lambda() is False

    def test_present_inside_lambda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "coding-workshop-auth-abcd1234")
        assert in_lambda() is True

    def test_is_local_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """IS_LOCAL must not influence anything.

        It is injected only by Terraform, so it is absent in a developer shell.
        Honouring it would give two discriminators that disagree locally.
        """
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        monkeypatch.setenv("IS_LOCAL", "false")
        get_settings.cache_clear()
        assert get_settings().running_in_lambda is False


class TestHostResolution:
    @pytest.mark.parametrize("container_host", ["172.17.0.1", "host.docker.internal"])
    def test_container_host_rewritten_on_the_host(
        self, monkeypatch: pytest.MonkeyPatch, container_host: str
    ) -> None:
        """172.17.0.1 is the Docker bridge; from the host it routes nowhere."""
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        monkeypatch.delenv("ACME_PG_HOST", raising=False)
        monkeypatch.setenv("POSTGRES_HOST", container_host)
        get_settings.cache_clear()
        assert get_settings().pg_host == "localhost"

    def test_container_host_preserved_inside_lambda(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "fn")
        monkeypatch.delenv("ACME_PG_HOST", raising=False)
        monkeypatch.setenv("POSTGRES_HOST", "172.17.0.1")
        get_settings.cache_clear()
        assert get_settings().pg_host == "172.17.0.1"

    def test_aurora_endpoint_never_rewritten(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "fn")
        monkeypatch.delenv("ACME_PG_HOST", raising=False)
        monkeypatch.setenv("POSTGRES_HOST", "acme.cluster-abc.us-east-2.rds.amazonaws.com")
        get_settings.cache_clear()
        assert get_settings().pg_host.endswith(".rds.amazonaws.com")

    def test_blank_host_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ACME_PG_HOST", raising=False)
        monkeypatch.setenv("POSTGRES_HOST", "   ")
        get_settings.cache_clear()
        assert get_settings().pg_host == "localhost"


class TestDatabaseUrl:
    def test_sslmode_required_only_inside_lambda(self) -> None:
        assert "sslmode=require" in _settings(running_in_lambda=True).database_url

    def test_sslmode_absent_locally(self) -> None:
        """Local PostgreSQL has no TLS; requesting it would fail every connect."""
        assert "sslmode" not in _settings(running_in_lambda=False).database_url

    def test_uses_psycopg3_driver(self) -> None:
        assert _settings().database_url.startswith("postgresql+psycopg://")

    def test_database_url_env_var_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A hand-set DATABASE_URL must never win over the injected settings."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://evil@elsewhere/other")
        get_settings.cache_clear()
        assert "elsewhere" not in get_settings().database_url

    def test_special_characters_in_password_are_quoted(self) -> None:
        url = _settings(pg_pass=SPECIAL_PW).database_url
        assert SPECIAL_PW not in url
        assert "p%40ss%2Fw%3Ard%3F" in url

    def test_carries_connect_timeout(self) -> None:
        """Aurora resumes from zero capacity; never wait on the OS default."""
        assert "connect_timeout=10" in _settings().database_url


class TestSecretMasking:
    def test_repr_masks_the_password(self) -> None:
        assert OTHER_PW not in repr(_settings(pg_pass=OTHER_PW))

    def test_safe_url_masks_the_password(self) -> None:
        s = _settings(pg_pass=OTHER_PW)
        assert OTHER_PW not in s.safe_database_url
        assert "***" in s.safe_database_url

    def test_real_url_still_contains_it(self) -> None:
        """Masking is for logs only; the driver needs the real value."""
        assert OTHER_PW in _settings(pg_pass=OTHER_PW).database_url


class TestCaching:
    def test_settings_are_cached(self) -> None:
        get_settings.cache_clear()
        assert get_settings() is get_settings()

    def test_cache_clear_picks_up_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_settings.cache_clear()
        first = get_settings().pg_name
        monkeypatch.setenv("ACME_PG_NAME", "something_else")
        get_settings.cache_clear()
        assert get_settings().pg_name == "something_else" != first


class TestDefaults:
    def test_defaults_match_the_injected_local_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Host tooling must work with no exported variables at all."""
        for var in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_NAME",
                    "POSTGRES_USER", "POSTGRES_PASS", "ACME_PG_HOST", "ACME_PG_NAME"):
            monkeypatch.delenv(var, raising=False)
        get_settings.cache_clear()
        s = get_settings()
        assert (s.pg_host, s.pg_port, s.pg_name, s.pg_user) == (
            "localhost", 5432, "postgres", "postgres",
        )

    def test_unparseable_port_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_PORT", "not-a-number")
        get_settings.cache_clear()
        assert get_settings().pg_port == 5432

    def test_token_lifetimes(self) -> None:
        s = _settings()
        assert s.access_ttl_seconds == 30 * 60
        assert s.refresh_ttl_seconds == 7 * 24 * 60 * 60


class TestJwtFallback:
    """The local-only signing key.

    The production key is 32 random bytes persisted in app_secrets. This
    fallback exists solely so host tooling can run before the database is
    reachable, and deliberately derives from nothing secret -- deriving a real
    key from POSTGRES_PASS would be unsound, because infra/rds.tf:15 sets the
    Aurora password to a three-word random_pet value.
    """

    def test_deterministic(self) -> None:
        assert _settings().jwt_secret_fallback() == _settings().jwt_secret_fallback()

    def test_does_not_derive_from_the_database_password(self) -> None:
        a = _settings(pg_pass="one").jwt_secret_fallback()
        b = _settings(pg_pass="two").jwt_secret_fallback()
        assert a == b

    def test_differs_per_service(self) -> None:
        a = _settings(service_name="auth").jwt_secret_fallback()
        b = _settings(service_name="incidents").jwt_secret_fallback()
        assert a != b
