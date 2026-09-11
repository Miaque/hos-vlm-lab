"""环境连接配置；能力未确证时拒绝运行，不静默丢弃控制项。"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import Controls, LabError, _json


@dataclass(frozen=True)
class ModelConfig:
    key: str
    label: str
    api_url: str
    api_key: str = field(repr=False)
    model_id: str
    profile: str
    pricing: dict | None = None

    def identity(self):
        return {
            "key": self.key,
            "label": self.label,
            "api_url": self.api_url,
            "model_id": self.model_id,
            "profile": self.profile,
        }


@dataclass(frozen=True)
class Config:
    models: tuple[ModelConfig, ...]
    data_dir: Path = Path("data")
    simulation: bool = False


def load_config() -> Config:
    models = []
    for prefix, label in (
        ("DEEPSEEK", "DeepSeek V4.1 Flash"),
        ("QWEN36", "Qwen3.6 Flash"),
        ("QWEN38", "Qwen3.8 Flash"),
        ("KIMI", "Kimi 2.6"),
        ("QWEN36_27B", "Qwen3.6 27B"),
    ):
        connection_prefix = "QWEN36_27B" if prefix == "QWEN36_27B" else "VLM"
        base_url = os.environ.get(f"{connection_prefix}_BASE_URL", "").strip()
        values = [
            base_url.rstrip("/") + "/chat/completions" if base_url else "",
            os.environ.get(f"{connection_prefix}_API_KEY", ""),
            os.environ.get(f"{prefix}_MODEL_ID", ""),
            os.environ.get(f"{prefix}_PROFILE", ""),
        ]
        price_text = os.environ.get(f"{prefix}_PRICING_JSON", "")
        try:
            pricing = _json(price_text) if price_text else None
            if pricing is not None and not isinstance(pricing, dict):
                raise ValueError()
        except ValueError:
            raise LabError(f"{prefix}_PRICING_JSON 必须为 JSON 对象") from None
        models.append(ModelConfig(prefix.lower(), label, *values, pricing))
    return Config(tuple(models), Path(os.environ.get("VLM_DATA_DIR", "data")))


def build_parameters(model: ModelConfig, controls: Controls) -> dict:
    if not all((model.api_url, model.api_key, model.model_id, model.profile)):
        raise LabError(f"{model.label}：连接配置不完整")
    if (
        model.profile == "deepseek"
        and model.model_id == "deepseek-flash"
        and model.api_url
        in {
            "https://api.deepseek.com/chat/completions",
            "https://api.deepseek.com/v1/chat/completions",
        }
    ):
        if controls.thinking:
            raise LabError(f"{model.label}：思考模式不支持可比的数值预算及温度")
        if not 0 <= controls.temperature <= 2:
            raise LabError(f"{model.label}：temperature 必须在 0–2 之间")
        # 官方文档总输出上限 384K，证据链接保存在 model-compatibility.md。
        if controls.max_tokens > 384 * 1024:
            raise LabError(f"{model.label}：MAX_TOKENS 超过总输出上限 384K")
        return {
            "thinking": {"type": "disabled"},
            "temperature": controls.temperature,
            "max_tokens": controls.max_tokens,
        }
    raise LabError(f"{model.label}：该端点与模型的参数范围尚未完成确证，暂不可运行")
