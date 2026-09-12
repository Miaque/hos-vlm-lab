"""工作台输入及模型输出的严格契约。"""

import json
import math
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LabError(ValueError):
    def __init__(
        self, message: str, status: int = 422, code: str = "invalid_input", details=None
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details or []


class Controls(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    thinking: bool
    thinking_budget: Annotated[int, Field(gt=0)] | None = None
    max_tokens: Annotated[int, Field(gt=0)]
    temperature: float

    @model_validator(mode="after")
    def validate_budget(self):
        if not self.thinking and self.thinking_budget is not None:
            raise ValueError("关闭思考时预算须为空")
        if self.thinking_budget is not None and self.thinking_budget >= self.max_tokens:
            raise ValueError("思考预算必须小于总生成上限")
        return self


class RoundRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)
    image_ids: list[str] = Field(min_length=1, max_length=20)
    model_keys: list[str] = Field(min_length=1, max_length=5)
    prompt_text: str = Field(min_length=1, max_length=200000)
    controls: Controls

    @model_validator(mode="after")
    def validate_inputs(self):
        if len(set(self.image_ids)) != len(self.image_ids) or len(
            set(self.model_keys)
        ) != len(self.model_keys):
            raise ValueError("图片和模型不能重复")
        parse_prompt(self.prompt_text)
        return self


class RetryRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    request_id: str = Field(min_length=1, max_length=128)


def _json(text: str):
    def reject_constant(value):
        raise ValueError(f"非法 JSON 数值：{value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON 数值超出有限范围")
        return number

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"重复 JSON 字段：{key}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        parse_float=finite_float,
        object_pairs_hook=unique_pairs,
    )


def parse_prompt(text: str) -> dict[str, str]:
    data = _json(text)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("events"), list)
        or not data["events"]
    ):
        raise ValueError("提示词必须是包含非空 events 数组的 JSON 对象")
    result = {}
    for event in data["events"]:
        if not isinstance(event, dict):
            raise ValueError("事件必须是对象")
        code, name = event.get("code"), event.get("name")
        if (
            not isinstance(code, str)
            or not code.strip()
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise ValueError("事件须包含非空 code 和 name")
        if code in result:
            raise ValueError("事件 code 不能重复")
        if "tile_detection" in event and type(event["tile_detection"]) is not bool:
            raise ValueError("事件 tile_detection 必须为布尔值")
        result[code] = name
    return result


class Event(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    canonical_event_code: str
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def nonblank(self):
        if not self.evidence.strip():
            raise ValueError("证据不能为空白")
        return self


def parse_events(text: str, allowed: dict[str, str]) -> list[dict]:
    wrapped = re.fullmatch(r"\s*(```|`)(?:json)?[ \t]*\r?\n(.*?)\r?\n\1\s*", text, re.DOTALL | re.IGNORECASE)
    if wrapped:
        text = wrapped.group(2)
    data = _json(text)
    if (
        not isinstance(data, dict)
        or set(data) != {"events"}
        or not isinstance(data["events"], list)
    ):
        raise ValueError("响应必须仅包含 events 数组")
    events = [Event.model_validate(item).model_dump() for item in data["events"]]
    codes = [item["canonical_event_code"] for item in events]
    if len(set(codes)) != len(codes) or any(code not in allowed for code in codes):
        raise ValueError("响应包含重复或未定义事件编码")
    return events
