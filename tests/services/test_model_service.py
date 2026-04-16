"""Unit tests for ModelService."""

import pytest

from memory_mcp.config import settings
from memory_mcp.container import Container
from memory_mcp.db.connection import get_connection
from memory_mcp.exceptions import ModelNotFoundError


@pytest.fixture
def container():
    return Container()


@pytest.fixture
def project(container, project_slug):
    container.project_repo.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


class TestInfo:
    def test_info_lists_presets(self, container):
        info = container.model_service.info()
        assert "english" in info["presets"]
        assert "multilingual" in info["presets"]
        assert info["current_model"] == settings.embedding_model


class TestSetModel:
    def test_unknown_preset_raises(self, container):
        with pytest.raises(ModelNotFoundError):
            container.model_service.set_model("banana")

    def test_same_model_noop(self, container):
        current = settings.embedding_model
        preset = settings.model_preset
        result = container.model_service.set_model(preset, confirm=True)
        assert "Already using" in result.get("message", "") or result["status"] == "ok"
        assert settings.embedding_model == current

    def test_confirmation_needed_without_confirm(self, container):
        other = "english" if settings.model_preset == "multilingual" else "multilingual"
        result = container.model_service.set_model(other, confirm=False)
        assert result["status"] == "confirmation_needed"
        # Model unchanged
        assert settings.model_preset != other
