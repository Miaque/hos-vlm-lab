import pytest

from hos_vlm_lab.config import build_parameters, load_config
from hos_vlm_lab.models import Controls, LabError


@pytest.mark.parametrize("base", ["https://independent.test/v1", "https://independent.test/v1/"])
def test_27b_independent_connection(monkeypatch, base):
    monkeypatch.setenv("VLM_API_KEY", "shared-secret")
    monkeypatch.setenv("VLM_BASE_URL", "https://shared.test/v1")
    monkeypatch.setenv("QWEN36_27B_BASE_URL", base)
    monkeypatch.setenv("QWEN36_27B_API_KEY", "27b-secret")
    monkeypatch.setenv("QWEN36_27B_MODEL_ID", "qwen3.6-27b")
    monkeypatch.setenv("QWEN36_27B_PROFILE", "independent")
    config = load_config()
    assert len(config.models) == 5
    model = next(m for m in config.models if m.key == "qwen36_27b")
    assert model.api_url == "https://independent.test/v1/chat/completions"
    assert model.api_key == "27b-secret"
    assert "27b-secret" not in str(model.identity())
    assert build_parameters(model, Controls(thinking=False, max_tokens=1000, temperature=0.6))["enable_thinking"] is False
    monkeypatch.delenv("QWEN36_27B_API_KEY")
    model = next(m for m in load_config().models if m.key == "qwen36_27b")
    assert model.api_key == ""
    with pytest.raises(LabError, match="连接配置不完整"):
        build_parameters(model, Controls(thinking=False, max_tokens=1000, temperature=0.6))


@pytest.mark.parametrize("base", ["https://shared.test/v1", "https://shared.test/v1/"])
def test_four_models_share_connection(monkeypatch, base):
    monkeypatch.setenv("VLM_BASE_URL", base)
    monkeypatch.setenv("VLM_API_KEY", "shared-secret")
    prefixes = ("DEEPSEEK", "QWEN36", "QWEN38", "KIMI")
    for prefix in prefixes:
        monkeypatch.setenv(f"{prefix}_API_URL", "https://obsolete.test/chat/completions")
        monkeypatch.setenv(f"{prefix}_API_KEY", "obsolete-secret")
        monkeypatch.setenv(f"{prefix}_MODEL_ID", prefix.lower())
        monkeypatch.setenv(f"{prefix}_PROFILE", "test-profile")
    models = load_config().models[:4]
    assert [m.model_id for m in models] == [p.lower() for p in prefixes]
    assert all(m.profile == "" for m in models)
    assert all(m.api_url == "https://shared.test/v1/chat/completions" for m in models)
    assert all(m.api_key == "shared-secret" for m in models)
    assert "shared-secret" not in str([m.identity() for m in models])
    monkeypatch.delenv("VLM_API_KEY")
    monkeypatch.delenv("VLM_BASE_URL")
    assert all(not m.api_key and not m.api_url for m in load_config().models[:4])
