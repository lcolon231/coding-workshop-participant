"""Deployment provenance reporting.

The stamp is what turns "is the deployed Lambda running my latest shared code?"
into one curl. bin/deploy-backend.sh is plain `terraform apply` and never runs
the sync, so a stale or absent vendored copy is a real and quiet failure mode.
"""

from __future__ import annotations

import sys
import types

import pytest

import acme_core

pytestmark = pytest.mark.unit


class TestBuildStamp:
    def test_reports_source_when_unstamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running from the source tree, where sync has not generated a stamp."""
        monkeypatch.setitem(sys.modules, "acme_core._build_stamp", None)
        monkeypatch.delattr(acme_core, "_build_stamp", raising=False)
        stamp = acme_core.build_stamp()
        assert stamp["git_sha"] == "source"
        assert stamp["dirty"] is None

    def test_reports_the_generated_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = types.ModuleType("acme_core._build_stamp")
        fake.GIT_SHA = "deadbee"  # type: ignore[attr-defined]
        fake.DIRTY = False  # type: ignore[attr-defined]
        fake.STAMPED_AT = "2026-09-22T00:00:00Z"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "acme_core._build_stamp", fake)
        assert acme_core.build_stamp() == {
            "git_sha": "deadbee",
            "dirty": False,
            "stamped_at": "2026-09-22T00:00:00Z",
        }

    def test_surfaces_a_dirty_tree(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dirty deploy is the one most likely to differ from any commit."""
        fake = types.ModuleType("acme_core._build_stamp")
        fake.GIT_SHA = "deadbee"  # type: ignore[attr-defined]
        fake.DIRTY = True  # type: ignore[attr-defined]
        fake.STAMPED_AT = "2026-09-22T00:00:00Z"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "acme_core._build_stamp", fake)
        assert acme_core.build_stamp()["dirty"] is True

    def test_version_is_exported(self) -> None:
        assert acme_core.__version__
