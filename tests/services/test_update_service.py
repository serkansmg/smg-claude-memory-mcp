"""Unit tests for UpdateService."""

from unittest.mock import patch

import pytest

from memory_mcp.services.update_service import UpdateService


@pytest.fixture
def service():
    return UpdateService()


class TestSemverCompare:
    def test_parse_semver(self):
        from memory_mcp.services.update_service import _parse_semver
        assert _parse_semver("v1.2.3") == (1, 2, 3)
        assert _parse_semver("1.2.3") == (1, 2, 3)
        assert _parse_semver("0.4.0") == (0, 4, 0)
        assert _parse_semver("v1.2") == (1, 2, 0)
        assert _parse_semver("broken") is None

    def test_version_gt(self):
        from memory_mcp.services.update_service import _version_tuple_gt
        assert _version_tuple_gt((0, 5, 0), (0, 4, 0))
        assert _version_tuple_gt((1, 0, 0), (0, 9, 9))
        assert not _version_tuple_gt((0, 4, 0), (0, 4, 0))
        assert not _version_tuple_gt((0, 3, 9), (0, 4, 0))


class TestCheck:
    def test_returns_structured_result(self, service):
        """check() always returns the expected keys."""
        # Mock both network calls to return None (no releases, no git)
        with patch("memory_mcp.services.update_service._fetch_github_json", return_value=None):
            with patch.object(service, "_check_via_git", return_value=None):
                result = service.check()

        assert "current_version" in result
        assert "source" in result
        assert "update_available" in result
        assert "how_to_update" in result
        assert result["source"] == "unknown"
        assert result["update_available"] is False

    def test_github_release_newer_triggers_update_available(self, service):
        fake_release = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/foo/bar/releases/tag/v99.0.0",
            "body": "- Added X\n- Fixed Y",
            "published_at": "2026-04-01T00:00:00Z",
        }
        with patch("memory_mcp.services.update_service._fetch_github_json", return_value=fake_release):
            result = service.check()

        assert result["source"] == "github_releases"
        assert result["update_available"] is True
        assert result["latest_version"] == "99.0.0"
        assert result["release_url"] == fake_release["html_url"]
        assert len(result["how_to_update"]) > 0

    def test_github_release_same_version_no_update(self, service):
        from memory_mcp import __version__
        fake_release = {
            "tag_name": f"v{__version__}",
            "html_url": "https://github.com/foo/bar",
            "body": "",
            "published_at": "2026-04-01T00:00:00Z",
        }
        with patch("memory_mcp.services.update_service._fetch_github_json", return_value=fake_release):
            result = service.check()

        assert result["update_available"] is False
        assert result["how_to_update"] == []

    def test_update_steps_reference_install_dir(self, service):
        fake_release = {"tag_name": "v99.0.0", "html_url": "x", "body": ""}
        with patch("memory_mcp.services.update_service._fetch_github_json", return_value=fake_release):
            result = service.check()

        steps_joined = " ".join(result["how_to_update"])
        assert "git pull" in steps_joined
        assert "uv sync" in steps_joined
        assert "Restart Claude Code" in steps_joined or "restart" in steps_joined.lower()
