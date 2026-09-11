from dataclasses import replace

import pytest

from hos_vlm_lab.config import ModelConfig, build_parameters
from hos_vlm_lab.models import Controls, LabError


def model(key="deepseek"):
    return ModelConfig(key, key, "https://new-api.test/v1/chat/completions", "secret", key)


def test_new_api_without_profile():
    assert build_parameters(model(), Controls(thinking=False, temperature=0.6, max_tokens=1000)) == {
        "thinking": {"type": "disabled"}, "temperature": 0.6, "max_tokens": 1000,
    }


@pytest.mark.parametrize("key", ["qwen36", "qwen38", "qwen36_27b"])
def test_qwen_thinking_mapping(key):
    parameters = build_parameters(model(key), Controls(thinking=True, thinking_budget=100, max_tokens=1000, temperature=0.6))
    assert parameters == {"enable_thinking": True, "thinking_budget": 100, "max_completion_tokens": 1000, "temperature": 0.6}
    parameters = build_parameters(model(key), Controls(thinking=False, max_tokens=1000, temperature=0.6))
    assert parameters == {"enable_thinking": False, "max_tokens": 1000, "temperature": 0.6}


@pytest.mark.parametrize("key", ["deepseek", "kimi"])
def test_unsupported_numeric_budget_rejected(key):
    with pytest.raises(LabError, match="数值思考预算"):
        build_parameters(model(key), Controls(thinking=True, thinking_budget=100, max_tokens=1000, temperature=0.6))


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_temperature_out_of_range(temperature):
    with pytest.raises(LabError):
        build_parameters(model(), Controls(thinking=False, max_tokens=1000, temperature=temperature))


@pytest.mark.parametrize("field", ["api_url", "api_key", "model_id"])
def test_missing_connection_rejected(field):
    with pytest.raises(LabError, match="连接配置不完整"):
        build_parameters(replace(model(), **{field: ""}), Controls(thinking=False, max_tokens=1000, temperature=0.6))
