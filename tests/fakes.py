"""显式注入的测试网关：不创建 HTTP 客户端，不读取环境。"""

import asyncio

from hos_vlm_lab.config import Config, ModelConfig


def fake_config(data_dir):
    return Config(
        tuple(
            ModelConfig(
                key, "模拟 · " + label, "https://fake.invalid", "test-only", key, "test"
            )
            for key, label in (
                ("detected", "检出"),
                ("empty", "未检出"),
                ("failure", "调用失败"),
                ("slow", "慢响应"),
            )
        ),
        data_dir,
        True,
    )


def fake_parameters(model, controls):
    return controls.model_dump(exclude_none=True)


class FakeGateway:
    def __init__(self, delay=0):
        self.calls = []
        self.delay = delay

    async def call(self, model, image, prompt, parameters, events):
        self.calls.append((model.key, image, prompt, parameters))
        await asyncio.sleep(self.delay * (4 if model.key == "slow" else 1))
        if model.key == "failure":
            return {
                "status": "failed",
                "error": {"code": "simulated", "message": "模拟调用失败"},
                "raw_response": "模拟失败",
            }
        items = (
            []
            if model.key == "empty"
            else [
                {
                    "canonical_event_code": next(iter(events)),
                    "confidence": 0.8,
                    "evidence": "模拟结果，不代表真实图像识别",
                }
            ]
        )
        return {
            "status": "succeeded",
            "parsed_events": items,
            "raw_response": "模拟响应",
            "usage": None,
            "cost": None,
        }
