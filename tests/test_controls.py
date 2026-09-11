from dataclasses import replace

import pytest

from hos_vlm_lab.config import ModelConfig, build_parameters
from hos_vlm_lab.models import Controls, LabError


def model(profile="deepseek"):
    return ModelConfig(
        "one",
        "测试",
        "https://api.deepseek.com/chat/completions",
        "secret",
        "deepseek-flash",
        profile,
    )


def test_deepseek_non_thinking_mapping():
    result = build_parameters(
        model(), Controls(thinking=False, temperature=0.6, max_tokens=1000)
    )
    assert result == {
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
        "max_tokens": 1000,
    }


def test_deepseek_thinking_has_no_equal_budget():
    with pytest.raises(LabError):
        build_parameters(
            model(),
            Controls(
                thinking=True, thinking_budget=1000, max_tokens=4000, temperature=0.6
            ),
        )


def test_unknown_profile_or_endpoint_rejected():
    for m in [
        model("unknown"),
        replace(model(), api_url="https://proxy.example/chat/completions"),
    ]:
        with pytest.raises(LabError):
            build_parameters(
                m, Controls(thinking=False, max_tokens=1000, temperature=0.6)
            )


def test_kimi_unknown_output_upper_limit_rejected():
    m = ModelConfig(
        "kimi",
        "Kimi",
        "https://api.moonshot.ai/v1/chat/completions",
        "s",
        "kimi-k2.6",
        "moonshot",
    )
    with pytest.raises(LabError):
        build_parameters(m, Controls(thinking=False, max_tokens=1000, temperature=0.6))


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_deepseek_temperature_out_of_range(temperature):
    with pytest.raises(LabError):
        build_parameters(
            model(), Controls(thinking=False, max_tokens=1000, temperature=temperature)
        )


def test_deepseek_output_limit():
    with pytest.raises(LabError):
        build_parameters(
            model(), Controls(thinking=False, max_tokens=393217, temperature=0.6)
        )
